import argparse
import concurrent.futures
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
from langchain_core.runnables import RunnableConfig
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


def patch_openai_reasoning_passthrough() -> None:
    """Keep vLLM/OpenAI-compatible message.reasoning on LangChain AIMessage."""
    try:
        import langchain_openai.chat_models.base as openai_chat_base
    except Exception:
        return

    original = getattr(openai_chat_base, "_convert_dict_to_message", None)
    if original is None or getattr(original, "_medflow_reasoning_patch", False):
        return

    def _convert_dict_to_message_with_reasoning(message_dict):
        message = original(message_dict)
        if isinstance(message, AIMessage):
            reasoning = message_dict.get("reasoning")
            if reasoning is None:
                reasoning = message_dict.get("reasoning_content")
            if reasoning is not None:
                message.additional_kwargs["reasoning"] = reasoning
        return message

    _convert_dict_to_message_with_reasoning._medflow_reasoning_patch = True
    openai_chat_base._convert_dict_to_message = _convert_dict_to_message_with_reasoning


patch_openai_reasoning_passthrough()


class InferenceRequest(BaseModel):
    command: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    include_trace: bool = False


class ToolInvokeRequest(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    thread_id: Optional[str] = None


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
LLM_MODEL = os.getenv(
    "AGENT_LLM_MODEL", AGENT_CONFIG.get("LLM_MODEL", "Qwen3.6-27B")
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
    model=LLM_MODEL,
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
    service_instance_list,
    service_instance_status,
    service_instance_tasks,
    service_instance_stop,
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
    node_service_instance_list,
    node_service_instance_status,
    node_service_instance_tasks,
    node_service_instance_stop,
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
AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "900"))
AGENT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)

MEMORY_CONFIG = AGENT_CONFIG.get("MEMORY", {}) if isinstance(AGENT_CONFIG.get("MEMORY"), dict) else {}
MEMORY_BACKEND = os.getenv(
    "MEDFLOW_AGENT_MEMORY_BACKEND",
    str(MEMORY_CONFIG.get("BACKEND", "memory")),
).strip().lower()
REDIS_URL = os.getenv(
    "MEDFLOW_AGENT_REDIS_URL",
    str(MEMORY_CONFIG.get("REDIS_URL", "redis://127.0.0.1:6379/0")),
)
REDIS_TTL_MINUTES = int(
    os.getenv(
        "MEDFLOW_AGENT_REDIS_TTL_MINUTES",
        str(MEMORY_CONFIG.get("TTL_MINUTES", 60 * 24 * 7)),
    )
)
if REDIS_TTL_MINUTES < 0:
    raise ValueError("MEMORY.TTL_MINUTES must be 0 or a positive integer")
REDIS_CHECKPOINT_PREFIX = os.getenv(
    "MEDFLOW_AGENT_REDIS_CHECKPOINT_PREFIX",
    str(MEMORY_CONFIG.get("CHECKPOINT_PREFIX", "medflow_inference_checkpoint")),
)
REDIS_CHECKPOINT_WRITE_PREFIX = os.getenv(
    "MEDFLOW_AGENT_REDIS_CHECKPOINT_WRITE_PREFIX",
    str(
        MEMORY_CONFIG.get(
            "CHECKPOINT_WRITE_PREFIX", "medflow_inference_checkpoint_write"
        )
    ),
)


def build_checkpointer():
    if MEMORY_BACKEND in {"", "memory", "inmemory", "in_memory"}:
        print("[memory] backend=memory checkpointer=InMemorySaver", flush=True)
        return InMemorySaver()

    if MEMORY_BACKEND == "redis":
        from langgraph.checkpoint.redis import RedisSaver

        redis_options = {
            "redis_url": REDIS_URL,
            "checkpoint_prefix": REDIS_CHECKPOINT_PREFIX,
            "checkpoint_write_prefix": REDIS_CHECKPOINT_WRITE_PREFIX,
        }
        if REDIS_TTL_MINUTES > 0:
            redis_options["ttl"] = {
                "default_ttl": REDIS_TTL_MINUTES,
                "refresh_on_read": True,
            }

        checkpointer = RedisSaver(
            **redis_options,
        )
        checkpointer.setup()
        ttl_text = str(REDIS_TTL_MINUTES) if REDIS_TTL_MINUTES else "disabled"
        print(
            "[memory] backend=redis "
            f"url={REDIS_URL} ttl_minutes={ttl_text} "
            f"checkpoint_prefix={REDIS_CHECKPOINT_PREFIX}",
            flush=True,
        )
        return checkpointer

    raise ValueError(
        "Unsupported memory backend: "
        f"{MEMORY_BACKEND}. Use memory or redis."
    )


def run_with_timeout(fn, timeout_seconds: int, timeout_message: str):
    future = AGENT_EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError as exc:
        raise TimeoutError(timeout_message) from exc


def empty_response_data() -> dict:
    return {
        "config": None,
        "services": None,
        "benchmark": None,
        "nodes": {},
    }


def merge_response_data(left: Optional[dict], right: Optional[dict]) -> dict:
    data = empty_response_data()

    if isinstance(left, dict):
        data["config"] = left.get("config")
        data["services"] = left.get("services")
        data["benchmark"] = left.get("benchmark")
        if isinstance(left.get("nodes"), dict):
            data["nodes"] = dict(left["nodes"])

    if not isinstance(right, dict):
        return data

    if right.get("config") is not None:
        data["config"] = right["config"]
    if right.get("services") is not None:
        data["services"] = right["services"]
    if right.get("benchmark") is not None:
        data["benchmark"] = right["benchmark"]

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
            if node_data.get("benchmark") is not None:
                merged_node["benchmark"] = node_data["benchmark"]
            data["nodes"][node] = merged_node

    return data


def split_tool_observation(observation) -> tuple[str, dict]:
    if isinstance(observation, dict) and "_tool_text" in observation:
        return (
            str(observation.get("_tool_text") or ""),
            merge_response_data(empty_response_data(), observation.get("_response_data")),
        )
    return str(observation), empty_response_data()


def get_reasoning_text(message: AnyMessage) -> str:
    reasoning = None
    for attr in ("additional_kwargs", "response_metadata"):
        data = getattr(message, attr, None)
        if isinstance(data, dict) and data.get("reasoning"):
            reasoning = data.get("reasoning")
            break
    if not reasoning:
        return ""
    return str(reasoning).strip()


def pretty_print_cli_message(message: AnyMessage) -> None:
    reasoning = get_reasoning_text(message)
    if not reasoning or not isinstance(message, AIMessage):
        message.pretty_print()
        return

    original_content = message.content
    content = str(original_content or "").strip()
    message.content = f"<think>\n{reasoning}\n</think>"
    if content:
        message.content += f"\n\n{content}"
    try:
        message.pretty_print()
    finally:
        message.content = original_content


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


def graph_request_user_id(config: RunnableConfig) -> str:
    current = current_request_user_id()
    if current:
        return current
    configurable = config.get("configurable", {})
    request_user_id = str(configurable.get("request_user_id") or "").strip()
    if request_user_id:
        return request_user_id
    thread_id = str(configurable.get("thread_id") or "").strip()
    return f"studio:{thread_id}" if thread_id else ""


def graph_thread_id(config: RunnableConfig) -> str:
    return str(config.get("configurable", {}).get("thread_id") or "").strip()


def reset_turn_state(state: MessagesState) -> dict:
    """Reset counters and response data once at the start of each graph run."""
    return {
        "llm_calls": 0,
        "tool_calls": 0,
        "response_data": empty_response_data(),
    }


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
                "3. 不允许编造执行结果。\n"
                "4. 工具返回后，必须用中文向用户总结工具结果；不要返回空内容。"
            )
        )
    ]

    try:
        response = run_with_timeout(
            lambda: model_with_tools.invoke(system_msg + state["messages"]),
            AGENT_TIMEOUT_SECONDS,
            "请求处理超时",
        )
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


def tool_node(
    state: MessagesState, config: RunnableConfig
) -> Command[Literal["llm_node", END]]:
    user_token = set_current_request_user_id(graph_request_user_id(config))
    thread_token = set_current_request_thread_id(graph_thread_id(config))
    try:
        return _tool_node(state)
    finally:
        reset_current_request_thread_id(thread_token)
        reset_current_request_user_id(user_token)


def _tool_node(state: MessagesState):
    """Performs the tool call."""

    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", [])
    completed_tool_calls = state.get("tool_calls", 0)
    if completed_tool_calls + len(tool_calls) > MAX_TOOL_CALLS:
        return Command(
            goto=END,
            update={
                "messages": [AIMessage(content="Tools 调用次数超过限制，任务已终止。")]
            },
        )

    results = []
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

    return Command(
        goto="llm_node",
        update={
            "messages": results,
            "tool_calls": completed_tool_calls + len(tool_calls),
            "response_data": response_data,
        },
    )


def route_by_tool(
    state: MessagesState,
) -> Literal["policy_node", END]:
    """Route to policy_node or end."""

    last = state["messages"][-1]

    if last.tool_calls:
        return "policy_node"

    return END


def policy_node(
    state: MessagesState, config: RunnableConfig
) -> Command[Literal["tool_node", END]]:
    user_token = set_current_request_user_id(graph_request_user_id(config))
    thread_token = set_current_request_thread_id(graph_thread_id(config))
    try:
        return _policy_node(state)
    finally:
        reset_current_request_thread_id(thread_token)
        reset_current_request_user_id(user_token)


def _policy_node(state: MessagesState) -> Command[Literal["tool_node", END]]:
    """Centralized policy enforcement."""

    last = state["messages"][-1]

    tool_call = last.tool_calls[0]
    action = tool_call["name"]

    allowed, message = policy_precheck(action, tool_args=tool_call.get("args", {}))

    if not allowed:
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=message)]},
        )

    return Command(goto="tool_node")


def policy_precheck(
    action: str,
    tool_map: Optional[dict] = None,
    tool_args: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    """
    Centralized execution policy layer.
    Returns:
        (True, "")  → allow execution
        (False, msg) → block execution with reason
    """

    tool_map = tool_map or tools_by_name
    tool_args = tool_args or {}

    if action in ["service_test_run", "service_test_run_all", "benchmark_run"]:
        instance_id = str(tool_args.get("instance_id") or "latest").strip() or "latest"
        status_tool = tool_map.get("service_instance_status")
        if status_tool is not None:
            instance_status, _ = split_tool_observation(
                status_tool.invoke({"instance_id": instance_id})
            )
        else:
            instance_status = ""
        if "status=running" not in instance_status:
            task_name = "benchmark" if action == "benchmark_run" else "test"
            return False, (
                f"检测到目标推理服务实例未运行，已跳过 {task_name}。\n\n当前实例状态：\n"
                + instance_status
            )
        return True, ""

    if action == "service_stop":
        benchmark_msg = running_benchmark_jobs_text()
        if benchmark_msg:
            return False, benchmark_msg
        return True, ""

    if action in ["config_update", "config_restore"]:
        status_text, _ = split_tool_observation(tool_map["service_status"].invoke({}))
        if "RUNNING" in status_text:
            return False, ("检测到服务正在运行，禁止修改配置。\n请先停止服务。")
        return True, ""

    return True, ""


agent_builder = StateGraph(MessagesState)
agent_builder.add_node("reset_turn_state", reset_turn_state)
agent_builder.add_node("llm_node", llm_node)
agent_builder.add_node("policy_node", policy_node)
agent_builder.add_node("tool_node", tool_node)
agent_builder.add_edge(START, "reset_turn_state")
agent_builder.add_edge("reset_turn_state", "llm_node")
agent_builder.add_conditional_edges(
    "llm_node",
    route_by_tool,
    ["policy_node", END],
)
agent = agent_builder.compile(checkpointer=build_checkpointer())


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
    command: str,
    thread_id: str = "api",
    include_trace: bool = False,
    user_id: Optional[str] = None,
):
    user_token = set_current_request_user_id(user_id or thread_id)
    thread_token = set_current_request_thread_id(thread_id)
    messages = [HumanMessage(content=command)]

    try:
        result = agent.invoke(
            {
                "messages": messages,
                "response_data": empty_response_data(),
            },
            {
                "configurable": {
                    "thread_id": thread_id,
                    "request_user_id": user_id or thread_id,
                }
            },
        )
    finally:
        reset_current_request_thread_id(thread_token)
        reset_current_request_user_id(user_token)

    new_messages = result["messages"]
    turn_messages = latest_turn_messages(new_messages)

    final_answer = "操作已执行，但模型未生成最终回复。请稍后重试或查看状态。"
    for m in reversed(turn_messages):
        if isinstance(m, AIMessage):
            content = str(m.content or "").split("</think>")[-1].strip()
            if not content:
                continue
            final_answer = content
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
    user_token = set_current_request_user_id(req.user_id or "")
    thread_token = set_current_request_thread_id(req.thread_id or "")
    start = time.time()
    try:
        return _run_inference_agent_tool(req, request_id, tool_name, tool_args, start)
    finally:
        reset_current_request_thread_id(thread_token)
        reset_current_request_user_id(user_token)


def _run_inference_agent_tool(
    req: ToolInvokeRequest,
    request_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    start: float,
):
    print(
        f"\n[worker-tool-api][{request_id}] request role={AGENT_ROLE} "
        f"thread_id={current_request_thread_id()} tool={tool_name} args={tool_args}",
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
            f"thread_id={current_request_thread_id()} "
            f"tool={tool_name} status=error duration={duration:.3f}s "
            f"result={preview_tool_result(response['result'])}",
            flush=True,
        )
        return response

    allowed, message = policy_precheck(
        tool_name, worker_tools_by_name, tool_args=tool_args
    )
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
            f"thread_id={current_request_thread_id()} "
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
            f"thread_id={current_request_thread_id()} "
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
        f"thread_id={current_request_thread_id()} "
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
        agent_result = run_with_timeout(
            lambda: run_service_agent(
                req.command,
                thread_id,
                req.include_trace,
                req.user_id,
            ),
            AGENT_TIMEOUT_SECONDS,
            "请求处理超时",
        )
    except TimeoutError as e:
        duration = time.time() - start
        result_text = "请求处理时间较长，本次操作尚未完成，请稍后再试。"
        print(
            f"[controller-api][{request_id}] timeout role={AGENT_ROLE} "
            f"thread_id={thread_id} duration={duration:.3f}s "
            f"timeout={AGENT_TIMEOUT_SECONDS}s error={e}",
            flush=True,
        )
        return {
            "status": "timeout",
            "thread_id": thread_id,
            "result": result_text,
            "data": controller_response_data(empty_response_data()),
        }
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

        cli_thread_id = "cli:1"
        user_token = set_current_request_user_id(cli_thread_id)
        try:
            result = agent.invoke(
                {
                    "messages": messages,
                    "response_data": empty_response_data(),
                },
                {"configurable": {"thread_id": cli_thread_id}},
            )
        finally:
            reset_current_request_user_id(user_token)

        new_messages = result["messages"]

        target_index = -1
        for i in range(len(new_messages) - 1, -1, -1):
            if isinstance(new_messages[i], HumanMessage):
                target_index = i
                break

        for m in new_messages[target_index:]:
            pretty_print_cli_message(m)


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
