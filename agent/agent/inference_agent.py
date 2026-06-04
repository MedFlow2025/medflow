import argparse
import operator
import os
import re
import time
import traceback
from typing import Literal, Optional

import uvicorn
from fastapi import FastAPI
from langchain.chat_models import init_chat_model
from langchain.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import BaseModel
from tools import *
from typing_extensions import Annotated, TypedDict

app = FastAPI()


class InferenceRequest(BaseModel):
    command: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    include_trace: bool = False


VLLM_URL = "http://10.130.35.2:8000/v1"
INFERENCE_AGENT_HOST = "10.130.35.2"
INFERENCE_AGENT_PORT = 8899
#AGENT_MAX_TOKENS = 8192

os.environ["OPENAI_API_KEY"] = "EMPTY"

llm = init_chat_model(
    model="model_medical_20250630",
    model_provider="openai",
    api_key="empty",
    base_url=VLLM_URL,
)
    #max_tokens=AGENT_MAX_TOKENS,


tools = [
    service_status,
    port_status,
    gpu_status,
    service_start,
    service_start_status,
    service_stop,
    service_restart,
    config_show,
    config_update,
    config_keys,
    # config_restore,
    model_list,
    config_check,
    gpu_recommend_allocation,
    service_log_runs,
    service_log_tail,
    service_log_search,
    service_log_context,
    service_test_list,
    service_test_run,
    service_test_status,
    service_test_stop,
    service_test_run_all,
    benchmark_list,
    benchmark_inspect,
    benchmark_run,
    benchmark_report,
    benchmark_jobs,
    benchmark_stop,
]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = llm.bind_tools(tools)

MAX_LLM_CALLS = 30
MAX_TOOL_CALLS = 20


class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    tool_calls: int


def llm_node(state: MessagesState):
    """LLM decides whether to call a tool or not."""

    if state.get("llm_calls", 0) >= MAX_LLM_CALLS:
        return {"messages": [AIMessage(content="LLM 调用次数超过限制，任务已终止。")]}
    system_msg = [
        SystemMessage(
            content=(
                "你是生产级运维智能体。使用中文进行回答。\n"
                "规则：\n"
                "1. 当需要执行系统操作时必须调用工具。\n"
                "2. 不要假设工具执行成功，必须等待 Tool 返回。\n"
                "3. 不允许编造执行结果。"
            )
        )
    ]

    try:
        response = model_with_tools.invoke(system_msg + state["messages"])
    except Exception as e:
        print("[LLM_ERROR] model invocation failed")
        print(traceback.format_exc())
        error_type = type(e).__name__
        error_msg = str(e).strip() or "模型调用失败"
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"[LLM_ERROR] 模型调用失败: {error_type}: {error_msg}\n"
                        "请检查推理服务状态、模型服务端口和网络连接后重试。"
                    )
                )
            ],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def tool_node(state: MessagesState):
    """Performs the tool call."""

    if state.get("tool_calls", 0) >= MAX_TOOL_CALLS:
        return {"messages": [AIMessage(content="Tools 调用次数超过限制，任务已终止。")]}
    results = []

    last = state["messages"][-1]

    tool_calls = getattr(last, "tool_calls", [])

    for tool_call in tool_calls:
        #tool = tools_by_name[tool_call["name"]]
        #observation = tool.invoke(tool_call["args"])

        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool = tools_by_name.get(tool_name)
        if tool is None:
            observation = (
                f"[TOOL_ERROR]\n"
                f"name={tool_name}\n"
                f"args={tool_args}\n"
                "error=Unknown tool. Please choose one of the registered tools."
            )
        else:
            try:
                observation = tool.invoke(tool_args)
            except Exception as e:
                observation = (
                    f"[TOOL_ERROR]\n"
                    f"name={tool_name}\n"
                    f"args={tool_args}\n"
                    f"error_type={type(e).__name__}\n"
                    f"error={e}\n"
                    "请向用户说明工具调用失败的原因，并根据错误提示调整参数后重试；"
                    "不要编造工具执行结果。"
                )

        results.append(
            ToolMessage(
                content=str(observation),
                tool_call_id=tool_call["id"],
            )
        )

    return {
        "messages": results,
        "tool_calls": state.get("tool_calls", 0) + len(tool_calls),
    }


def route_by_tool(
    state: MessagesState,
) -> Literal["policy_node", END]:
    """Route to policy_node or end."""

    last = state["messages"][-1]

    if last.tool_calls:
        return "policy_node"

    return END


def policy_node(state: MessagesState) -> Command[Literal["tool_node", END]]:
    """Centralized policy enforcement."""

    last = state["messages"][-1]

    tool_call = last.tool_calls[0]
    action = tool_call["name"]

    allowed, message = policy_precheck(action)

    if not allowed:
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=message)]},
        )

    return Command(goto="tool_node")


def policy_precheck(action: str) -> tuple[bool, str]:
    """
    Centralized execution policy layer.
    Returns:
        (True, "")  → allow execution
        (False, msg) → block execution with reason
    """

    if action == "service_start":
        status_result = tools_by_name["service_status"].invoke({})
        if "RUNNING" in str(status_result):
            return False, (
                "检测到已有服务运行，已自动跳过启动。\n\n当前状态：\n"
                + str(status_result)
            )

        config_result = tools_by_name["config_check"].invoke({})
        if not config_result["ok"]:
            return False, (config_result["msg"])

    if action == "service_restart":
        config_result = tools_by_name["config_check"].invoke({})
        if not config_result["ok"]:
            return False, (config_result["msg"])

    if action in ["service_test_run", "service_test_run_all"]:
        status_result = tools_by_name["service_status"].invoke({})
        if "STOPPED" in str(status_result):
            return False, (
                "检测到服务未运行，已跳过 test。\n\n当前状态：\n" + str(status_result)
            )
        return True, ""

    if action in ["config_update", "config_restore"]:
        status_result = tools_by_name["service_status"].invoke({})
        if "RUNNING" in str(status_result):
            return False, ("检测到服务正在运行，禁止修改配置。\n请先停止服务。")
        return True, ""

    return True, ""


agent_builder = StateGraph(MessagesState)
agent_builder.add_node("llm_node", llm_node)
agent_builder.add_node("policy_node", policy_node)
agent_builder.add_node("tool_node", tool_node)
agent_builder.add_edge(START, "llm_node")
agent_builder.add_conditional_edges(
    "llm_node",
    route_by_tool,
    ["policy_node", END],
)
agent_builder.add_edge("policy_node", "tool_node")
agent_builder.add_edge("tool_node", "llm_node")
agent = agent_builder.compile(checkpointer=InMemorySaver())


def log_preview(text: str, limit: int = 300) -> str:
    text = str(text).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "... truncated ..."


def normalize_thread_part(value: Optional[str], default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    text = re.sub(r"[^A-Za-z0-9_.:@-]+", "_", text)
    return text[:120] or default


def resolve_thread_id(req: InferenceRequest) -> str:
    explicit_thread_id = normalize_thread_part(req.thread_id)
    if explicit_thread_id:
        return explicit_thread_id

    user_id = normalize_thread_part(req.user_id)
    session_id = normalize_thread_part(req.session_id)
    if user_id and session_id:
        return f"user:{user_id}:session:{session_id}"
    if user_id:
        return f"user:{user_id}"
    if session_id:
        return f"session:{session_id}"
    return "api"


def build_trace(messages: list[AnyMessage], preview_limit: int = 4000) -> list[dict]:
    trace = []
    pending_tool_calls = {}

    for message in messages:
        if isinstance(message, HumanMessage) or isinstance(message, SystemMessage):
            continue

        if isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", []) or []
            for tool_call in tool_calls:
                pending_tool_calls[tool_call["id"]] = {
                    "type": "tool_call",
                    "name": tool_call.get("name"),
                    "args": tool_call.get("args", {}),
                    "tool_call_id": tool_call.get("id"),
                }
            if message.content:
                trace.append(
                    {
                        "type": "ai",
                        "content_preview": log_preview(message.content, preview_limit),
                    }
                )
            continue

        if isinstance(message, ToolMessage):
            item = pending_tool_calls.pop(
                message.tool_call_id,
                {
                    "type": "tool_call",
                    "name": None,
                    "args": {},
                    "tool_call_id": message.tool_call_id,
                },
            )
            content = str(message.content)
            item.update(
                {
                    "output_preview": log_preview(content, preview_limit),
                    "output_truncated": len(content) > preview_limit,
                }
            )
            trace.append(item)

    for item in pending_tool_calls.values():
        trace.append(item)

    return trace


def build_response_data(messages: list[AnyMessage]) -> dict:
    data = {
        "config": None,
        "services": None,
    }

    pending_tool_calls = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in getattr(message, "tool_calls", []) or []:
                pending_tool_calls[tool_call["id"]] = tool_call.get("name")
            continue
        if not isinstance(message, ToolMessage):
            continue

        name = pending_tool_calls.pop(message.tool_call_id, None)
        if name in {"config_show", "config_update"}:
            data["config"] = show_public_config()
        elif name == "service_status":
            data["services"] = service_status_data()["services"]

    return data


def latest_turn_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i:]
    return messages


def build_usage(messages: list[AnyMessage]) -> dict:
    return {
        "llm_calls": sum(1 for message in messages if isinstance(message, AIMessage)),
        "tool_calls": sum(
            1 for message in messages if isinstance(message, ToolMessage)
        ),
    }


def run_service_agent(
    command: str, thread_id: str = "api", include_trace: bool = False
):
    messages = [HumanMessage(content=command)]

    result = agent.invoke(
        {
            "messages": messages,
            "llm_calls": 0,
            "tool_calls": 0,
        },
        {"configurable": {"thread_id": thread_id}},
    )

    new_messages = result["messages"]
    turn_messages = latest_turn_messages(new_messages)

    final_answer = "no response"
    for m in reversed(turn_messages):
        if m.type == "ai":
            # return m.content
            final_answer = m.content.split("</think>")[-1].strip()
            break

    response = {
        "result": final_answer,
        "data": build_response_data(turn_messages),
    }
    if include_trace:
        response["usage"] = build_usage(turn_messages)
        response["trace"] = build_trace(turn_messages)

    return response


@app.post("/inference_agent")
def run_inference_agent(req: InferenceRequest):
    request_id = f"{int(time.time() * 1000)}"
    thread_id = resolve_thread_id(req)
    start = time.time()
    print(
        f"[api][{request_id}] request thread_id={thread_id} command={log_preview(req.command)}",
        flush=True,
    )

    try:
        agent_result = run_service_agent(req.command, thread_id, req.include_trace)
    except Exception as e:
        duration = time.time() - start
        print(
            f"[api][{request_id}] failed duration={duration:.3f}s error={log_preview(e)}",
            flush=True,
        )
        raise

    duration = time.time() - start
    print(
        f"[api][{request_id}] response thread_id={thread_id} duration={duration:.3f}s "
        f"result_len={len(str(agent_result['result']))} result={log_preview(agent_result['result'])}",
        flush=True,
    )

    response = {
        "status": "ok",
        "thread_id": thread_id,
        "result": agent_result["result"],
        "data": agent_result["data"],
    }
    if req.include_trace:
        response["usage"] = agent_result["usage"]
        response["trace"] = agent_result["trace"]
    return response


def main():
    print("\n🟢 Inference Service Agent")
    print("Type: start / stop / status / test / logs / exit\n")

    while True:
        user_input = input("> ").strip()

        if user_input.lower() in ["exit", "quit"]:
            print("Bye 👋")
            break

        messages = [HumanMessage(content=str(user_input))]

        result = agent.invoke(
            {"messages": messages, "llm_calls": 0, "tool_calls": 0},
            {"configurable": {"thread_id": "1"}},
        )

        new_messages = result["messages"]

        target_index = -1
        for i in range(len(new_messages) - 1, -1, -1):
            if isinstance(new_messages[i], HumanMessage):
                target_index = i
                break

        for m in new_messages[target_index:]:
            m.pretty_print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, choices=["cli", "api"], default="api")
    args = parser.parse_args()

    if args.mode == "cli":
        main()
    else:
        uvicorn.run(
            app="inference_agent:app",
            host=INFERENCE_AGENT_HOST,
            port=INFERENCE_AGENT_PORT,
        )
