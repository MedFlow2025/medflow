import argparse
import operator
import os
from typing import Literal

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
from tools import (
    available_tests,
    check_config,
    config_keys,
    config_restore,
    config_show,
    config_update,
    gpu_status,
    list_model,
    log_context,
    port_status,
    recommend_gpu_allocation,
    search_logs,
    service_logs,
    service_restart,
    service_start,
    service_status,
    service_stop,
    service_test,
    service_test_all,
)
from typing_extensions import Annotated, TypedDict

app = FastAPI()


class InferenceRequest(BaseModel):
    command: str


VLLM_URL = "http://10.130.35.2:8000/v1"
INFERENCE_AGENT_HOST = "10.130.35.2"
INFERENCE_AGENT_PORT = 8899

os.environ["OPENAI_API_KEY"] = "EMPTY"

llm = init_chat_model(
    model="model_medical_20250630",
    model_provider="openai",
    api_key="empty",
    base_url=VLLM_URL,
)


tools = [
    service_status,
    port_status,
    gpu_status,
    service_start,
    service_stop,
    service_restart,
    config_show,
    config_update,
    config_keys,
    config_restore,
    list_model,
    check_config,
    recommend_gpu_allocation,
    service_logs,
    search_logs,
    log_context,
    available_tests,
    service_test,
    service_test_all,
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

    response = model_with_tools.invoke(system_msg + state["messages"])

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
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])

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

        config_result = tools_by_name["check_config"].invoke({})
        if not config_result["ok"]:
            return False, (config_result["msg"])

    if action == "service_test":
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


def run_service_agent(command: str):
    messages = [HumanMessage(content=command)]

    result = agent.invoke(
        {
            "messages": messages,
            "llm_calls": 0,
            "tool_calls": 0,
        },
        {"configurable": {"thread_id": "api"}},
    )

    new_messages = result["messages"]

    for m in reversed(new_messages):
        if m.type == "ai":
            # return m.content
            return m.content.split("</think>")[-1].strip()

    return "no response"


@app.post("/inference_agent")
def run_inference_agent(req: InferenceRequest):
    result = run_service_agent(req.command)

    return {"status": "ok", "result": result}


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
    parser.add_argument('--mode', type=str, choices=['cli', 'api'], default='api')
    args = parser.parse_args()

    if args.mode == "cli":
        main()
    else:
        uvicorn.run(
            app="inference_agent:app", host=INFERENCE_AGENT_HOST, port=INFERENCE_AGENT_PORT
        )
