import argparse
import operator
import os
import re
import time
import traceback
from typing import Any, Literal, Optional

import uvicorn
import yaml
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
from pydantic import BaseModel, Field
from tools import *
from typing_extensions import Annotated, TypedDict

app = FastAPI()


class InferenceRequest(BaseModel):
    command: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    include_trace: bool = False


class ToolInvokeRequest(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


AGENT_CONFIG_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../config/agent.yaml")
)


def load_agent_config() -> dict:
    if not os.path.exists(AGENT_CONFIG_FILE):
        return {}
    with open(AGENT_CONFIG_FILE) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


AGENT_CONFIG = load_agent_config()
AGENT_ROLE = os.getenv("AGENT_ROLE", AGENT_CONFIG.get("ROLE", "worker")).strip().lower()
VLLM_URL = os.getenv(
    "AGENT_LLM_URL", AGENT_CONFIG.get("LLM_URL", "http://10.130.35.2:8111/v1")
)
INFERENCE_AGENT_HOST = os.getenv(
    "INFERENCE_AGENT_HOST", AGENT_CONFIG.get("HOST", "10.130.35.2")
)
INFERENCE_AGENT_PORT = int(
    os.getenv("INFERENCE_AGENT_PORT", str(AGENT_CONFIG.get("PORT", 8899)))
)
# AGENT_MAX_TOKENS = 8192

os.environ["OPENAI_API_KEY"] = "EMPTY"

llm = init_chat_model(
    model="model_medical_20250630",
    model_provider="openai",
    api_key="empty",
    base_url=VLLM_URL,
)
# max_tokens=AGENT_MAX_TOKENS,


worker_tools = [
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

controller_tools = [
    node_list,
    node_enable,
    node_disable,
    node_service_status,
    node_gpu_status,
    node_config_show,
    node_config_keys,
    node_config_update,
    node_recommend_start_target,
    node_service_start,
    node_service_start_status,
    node_service_stop,
    node_service_restart,
    node_port_status,
    node_model_list,
    node_config_check,
    node_gpu_recommend_allocation,
    node_service_log_runs,
    node_service_log_tail,
    node_service_log_search,
    node_service_log_context,
    node_service_test_list,
    node_service_test_run,
    node_service_test_run_all,
    node_service_test_status,
    node_service_test_stop,
    node_benchmark_list,
    node_benchmark_inspect,
    node_benchmark_run,
    node_benchmark_report,
    node_benchmark_jobs,
    node_benchmark_stop,
    #node_tool_call,
]

if AGENT_ROLE in {"controller", "both"}:
    tools = controller_tools
else:
    tools = worker_tools

worker_tools_by_name = {tool.name: tool for tool in worker_tools}
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = llm.bind_tools(tools)

MAX_LLM_CALLS = 30
MAX_TOOL_CALLS = 20
TOOL_RESULT_LOG_CHARS = 2000


def get_llm_finish_reason(message: AnyMessage) -> str:
    for attr in ("response_metadata", "generation_info", "additional_kwargs"):
        metadata = getattr(message, attr, None) or {}
        if not isinstance(metadata, dict):
            continue
        finish_reason = metadata.get("finish_reason")
        if finish_reason:
            return str(finish_reason)
        nested = metadata.get("token_usage") or metadata.get("usage_metadata") or {}
        if isinstance(nested, dict) and nested.get("finish_reason"):
            return str(nested["finish_reason"])
    return ""


def empty_response_data() -> dict:
    return {
        "config": None,
        "services": None,
        "nodes": {},
    }


def merge_response_data(left: Optional[dict], right: Optional[dict]) -> dict:
    data = empty_response_data()

    if isinstance(left, dict):
        data["config"] = left.get("config")
        data["services"] = left.get("services")
        if isinstance(left.get("nodes"), dict):
            data["nodes"] = dict(left["nodes"])

    if not isinstance(right, dict):
        return data

    if right.get("config") is not None:
        data["config"] = right["config"]
    if right.get("services") is not None:
        data["services"] = right["services"]

    nodes = right.get("nodes")
    if isinstance(nodes, dict):
        for node, node_data in nodes.items():
            if not isinstance(node_data, dict):
                continue
            merged_node = data["nodes"].get(node)
            if not isinstance(merged_node, dict):
                merged_node = {}
            else:
                merged_node = dict(merged_node)
            if node_data.get("config") is not None:
                merged_node["config"] = node_data["config"]
            if node_data.get("services") is not None:
                merged_node["services"] = node_data["services"]
            data["nodes"][node] = merged_node

    return data


def split_tool_observation(observation) -> tuple[str, dict]:
    if isinstance(observation, dict) and "_tool_text" in observation:
        return (
            str(observation.get("_tool_text") or ""),
            merge_response_data(empty_response_data(), observation.get("_response_data")),
        )
    return str(observation), empty_response_data()


def controller_response_data(data: Optional[dict]) -> dict:
    merged = merge_response_data(empty_response_data(), data)
    return {
        "nodes": merged["nodes"],
    }


class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    tool_calls: int
    response_data: dict


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
    response_data = merge_response_data(empty_response_data(), state.get("response_data"))

    for tool_call in tool_calls:
        # tool = tools_by_name[tool_call["name"]]
        # observation = tool.invoke(tool_call["args"])

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

        tool_text, tool_response_data = split_tool_observation(observation)
        response_data = merge_response_data(response_data, tool_response_data)

        results.append(
            ToolMessage(
                content=tool_text,
                tool_call_id=tool_call["id"],
            )
        )

    return {
        "messages": results,
        "tool_calls": state.get("tool_calls", 0) + len(tool_calls),
        "response_data": response_data,
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


def policy_precheck(action: str, tool_map: Optional[dict] = None) -> tuple[bool, str]:
    """
    Centralized execution policy layer.
    Returns:
        (True, "")  → allow execution
        (False, msg) → block execution with reason
    """

    tool_map = tool_map or tools_by_name

    if action == "service_start":
        status_text, _ = split_tool_observation(tool_map["service_status"].invoke({}))
        if "RUNNING" in status_text:
            return False, (
                "检测到已有服务运行，已自动跳过启动。\n\n当前状态：\n"
                + status_text
            )

        config_result = tool_map["config_check"].invoke({})
        if not config_result["ok"]:
            return False, (config_result["msg"])

    if action in ["service_test_run", "service_test_run_all", "benchmark_run"]:
        status_text, _ = split_tool_observation(tool_map["service_status"].invoke({}))
        if "STOPPED" in status_text:
            task_name = "benchmark" if action == "benchmark_run" else "test"
            return False, (
                f"检测到服务未运行，已跳过 {task_name}。\n\n当前状态：\n"
                + status_text
            )
        return True, ""

    if action in ["config_update", "config_restore"]:
        status_text, _ = split_tool_observation(tool_map["service_status"].invoke({}))
        if "RUNNING" in status_text:
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


def build_trace(messages: list[AnyMessage]) -> list[dict]:
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
                        "content_preview": message.content,
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
                    "output_preview": content,
                    "output_truncated": False,
                }
            )
            trace.append(item)

    for item in pending_tool_calls.values():
        trace.append(item)

    return trace


def preview_tool_result(result) -> str:
    text = str(result).replace("\n", "\\n")
    if len(text) > TOOL_RESULT_LOG_CHARS:
        return text[:TOOL_RESULT_LOG_CHARS] + "... truncated ..."
    return text


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
            "response_data": empty_response_data(),
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
        "data": controller_response_data(result.get("response_data")),
    }
    if include_trace:
        response["usage"] = build_usage(turn_messages)
        response["trace"] = build_trace(turn_messages)

    return response


@app.post("/worker/tool")
def run_inference_agent_tool(req: ToolInvokeRequest):
    request_id = f"tool-{int(time.time() * 1000)}"
    tool_name = str(req.tool or "").strip()
    tool_args = req.args or {}
    start = time.time()
    print(
        f"\n[worker-tool-api][{request_id}] request role={AGENT_ROLE} "
        f"tool={tool_name} args={tool_args}",
        flush=True,
    )

    if AGENT_ROLE not in {"worker", "both"}:
        return {
            "status": "error",
            "role": AGENT_ROLE,
            "tool": tool_name,
            "result": "当前进程不是 worker/both 角色，不提供 /worker/tool 工具执行接口。",
            "data": empty_response_data(),
        }

    tool = worker_tools_by_name.get(tool_name)
    if tool is None:
        response = {
            "status": "error",
            "tool": tool_name,
            "result": (
                f"Unknown worker tool: {tool_name}. "
                f"Available tools: {', '.join(sorted(worker_tools_by_name))}"
            ),
            "data": empty_response_data(),
        }
        duration = time.time() - start
        print(
            f"[worker-tool-api][{request_id}] response role={AGENT_ROLE} "
            f"tool={tool_name} status=error duration={duration:.3f}s "
            f"result={preview_tool_result(response['result'])}",
            flush=True,
        )
        return response

    allowed, message = policy_precheck(tool_name, worker_tools_by_name)
    if not allowed:
        response = {
            "status": "blocked",
            "tool": tool_name,
            "result": message,
            "data": empty_response_data(),
        }
        duration = time.time() - start
        print(
            f"[worker-tool-api][{request_id}] response role={AGENT_ROLE} "
            f"tool={tool_name} status=blocked duration={duration:.3f}s "
            f"result={preview_tool_result(response['result'])}",
            flush=True,
        )
        return response

    try:
        result = tool.invoke(tool_args)
        result_text, response_data = split_tool_observation(result)
        status = "ok"
    except Exception as e:
        print(
            f"[worker-tool-api][{request_id}] error role={AGENT_ROLE} "
            f"tool={tool_name} invocation failed",
            flush=True,
        )
        print(traceback.format_exc())
        result = (
            f"[TOOL_ERROR]\n"
            f"name={tool_name}\n"
            f"args={tool_args}\n"
            f"error_type={type(e).__name__}\n"
            f"error={e}"
        )
        result_text = result
        response_data = empty_response_data()
        status = "error"

    duration = time.time() - start
    print(
        f"[worker-tool-api][{request_id}] response role={AGENT_ROLE} "
        f"tool={tool_name} status={status} duration={duration:.3f}s "
        f"result={preview_tool_result(result_text)}",
        flush=True,
    )
    return {
        "status": status,
        "tool": tool_name,
        "result": result_text,
        "data": response_data,
    }


@app.post("/inference_agent")
def run_inference_agent(req: InferenceRequest):
    request_id = f"ctrl-{int(time.time() * 1000)}"
    thread_id = resolve_thread_id(req)
    start = time.time()
    print(
        f"\n[controller-api][{request_id}] request role={AGENT_ROLE} "
        f"thread_id={thread_id} command={req.command}",
        flush=True,
    )

    if AGENT_ROLE == "worker":
        return {
            "status": "error",
            "role": AGENT_ROLE,
            "thread_id": thread_id,
            "result": "当前进程是 worker 角色，只提供 /worker/tool 内部工具接口。",
            "data": controller_response_data(empty_response_data()),
        }

    try:
        agent_result = run_service_agent(req.command, thread_id, req.include_trace)
    except Exception as e:
        duration = time.time() - start
        print(
            f"[controller-api][{request_id}] failed role={AGENT_ROLE} "
            f"duration={duration:.3f}s error={e}",
            flush=True,
        )
        raise

    duration = time.time() - start
    print(
        f"[controller-api][{request_id}] response role={AGENT_ROLE} "
        f"thread_id={thread_id} duration={duration:.3f}s "
        f"result_len={len(str(agent_result['result']))} result={agent_result['result']}",
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
