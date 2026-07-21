import ast
import copy
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, Optional

import psutil
import yaml
from langchain.tools import tool

CONFIG_FILE = "../config/service.yaml"
DEFAULT_CONFIG_FILE = "../config/service.default.yaml"
NODES_CONFIG_FILE = "../config/nodes.yaml"
AGENT_CONFIG_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../config/agent.yaml")
)
WHITELIST = {
    "PORTS.VLLM_OPENAI_PORT",
    "PORTS.INFERENCE_PORT",
    "PORTS.UI_PORT",
    "PORTS.DATA_ANNOTATION_PORT",
    "ENV.CUDA_VISIBLE_DEVICES",
    "ENV.MASTER_PORT",
    "ENV.MODEL_NAME",
    "ENV.MODEL_PARAM_B",
    "RUNTIME.TENSOR_PARALLEL_SIZE",
    "RUNTIME.MAX_TOKENS",
    "RUNTIME.GPU_MEMORY_UTILIZATION",
    "RUNTIME.GPU_UTILIZATION_THRESHOLD",
}
LOG_FILES = {
    "start": "start-service.log",
    "vllm": "vllm.log",
    "inference": "inference.log",
    "ui": "web.log",
    "web": "web.log",
    "case2chat": "case2chat.log",
}
MAX_OUTPUT_CHARS = 3000
MAX_LOG_LINES = 80
MAX_LOG_CONTEXT_WINDOW = 40
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
PROGRESS_UPDATE_INTERVAL = 5
NODE_AGENT_TIMEOUT = int(os.getenv("NODE_AGENT_TIMEOUT", "300"))
BENCHMARK_SUBMIT_LOCK_TTL = int(os.getenv("BENCHMARK_SUBMIT_LOCK_TTL", "600"))
# Request-scoped identity for service instance ownership checks.
CURRENT_REQUEST_USER_ID: ContextVar[str] = ContextVar(
    "CURRENT_REQUEST_USER_ID", default=""
)
CURRENT_REQUEST_THREAD_ID: ContextVar[str] = ContextVar(
    "CURRENT_REQUEST_THREAD_ID", default=""
)
CURRENT_REQUEST_RESOURCE_CONTEXT: ContextVar[Optional[dict]] = ContextVar(
    "CURRENT_REQUEST_RESOURCE_CONTEXT", default=None
)
PORT_ALLOCATION_LOCK = threading.Lock()
PENDING_INSTANCE_PORTS: set[int] = set()
PENDING_PORT_LEASE_TTL = 900
PORT_LISTENER_CACHE_LOCK = threading.Lock()
PORT_LISTENER_CACHE = {"time": 0.0, "listeners": {}, "scan_failed": False}
PORT_LISTENER_CACHE_TTL = 0.5


def safe_output(text, limit: int = MAX_OUTPUT_CHARS):
    text = str(text)
    if len(text) > limit:
        return (
            text[:limit]
            + "\n... truncated ...\n"
            "输出已截断，请缩小 service、keyword、lines 或 window 后继续查看。"
        )
    return text


def clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def parse_time_sort_value(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt, length in (("%Y-%m-%d %H:%M:%S", 19), ("%Y%m%d_%H%M%S", 15)):
        try:
            return time.mktime(time.strptime(text[:length], fmt))
        except Exception:
            continue
    try:
        return float(text.split("_", 1)[0])
    except Exception:
        return 0.0


def status_sort_rank(status: object) -> int:
    value = str(status or "").strip().lower()
    order = {
        "submitting": 0,
        "running": 0,
        "starting": 1,
        "degraded": 2,
        "pending": 2,
        "failed": 3,
        "unknown_finished": 4,
        "stopped": 5,
        "finished": 6,
    }
    return order.get(value, 9)


def set_current_request_user_id(user_id: str):
    return CURRENT_REQUEST_USER_ID.set(str(user_id or "").strip())


def reset_current_request_user_id(token) -> None:
    CURRENT_REQUEST_USER_ID.reset(token)


def current_request_user_id() -> str:
    return CURRENT_REQUEST_USER_ID.get().strip()


def set_current_request_thread_id(thread_id: str):
    return CURRENT_REQUEST_THREAD_ID.set(str(thread_id or "").strip())


def reset_current_request_thread_id(token) -> None:
    CURRENT_REQUEST_THREAD_ID.reset(token)


def current_request_thread_id() -> str:
    return CURRENT_REQUEST_THREAD_ID.get().strip()


def set_current_request_resource_context(resource_context: Optional[dict]):
    value = dict(resource_context) if isinstance(resource_context, dict) else None
    return CURRENT_REQUEST_RESOURCE_CONTEXT.set(value)


def reset_current_request_resource_context(token) -> None:
    CURRENT_REQUEST_RESOURCE_CONTEXT.reset(token)


def current_request_resource_context() -> dict:
    value = CURRENT_REQUEST_RESOURCE_CONTEXT.get()
    return dict(value) if isinstance(value, dict) else {}


def parse_resource_pool_enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("RESOURCE_POOL.ENABLED must be true or false")


def load_resource_pool_enabled() -> bool:
    configured = False
    if os.path.exists(AGENT_CONFIG_FILE):
        with open(AGENT_CONFIG_FILE) as f:
            agent_config = yaml.safe_load(f) or {}
        resource_config = agent_config.get("RESOURCE_POOL", {})
        if isinstance(resource_config, dict):
            configured = parse_resource_pool_enabled(
                resource_config.get("ENABLED", False)
            )
    environment_value = os.getenv("MEDFLOW_RESOURCE_POOL_ENABLED")
    if environment_value is not None:
        return parse_resource_pool_enabled(environment_value)
    return configured


RESOURCE_POOL_ENABLED = load_resource_pool_enabled()


def resource_pool_managed() -> bool:
    return RESOURCE_POOL_ENABLED


def _resource_gpu_ids(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [item.strip() for item in str(value or "").split(",")]
    return list(dict.fromkeys(item for item in items if item))


def resource_context_nodes(resource_context: Optional[dict] = None) -> list[dict]:
    """Return normalized node allocations, including the legacy single-node form."""
    context = resource_context or current_request_resource_context()
    raw_nodes = context.get("nodes")
    if isinstance(raw_nodes, list):
        nodes = []
        for item in raw_nodes:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("runtime_node_id") or "").strip()
            if not node_id:
                continue
            node = dict(item)
            node["runtime_node_id"] = node_id
            node["assigned_gpus"] = _resource_gpu_ids(
                item.get("assigned_gpus", item.get("cuda_visible_devices"))
            )
            nodes.append(node)
        if nodes:
            return nodes

    node_id = str(context.get("runtime_node_id") or "").strip()
    if not node_id:
        return []
    return [
        {
            "runtime_node_id": node_id,
            "assigned_gpus": _resource_gpu_ids(
                context.get("assigned_gpus", context.get("cuda_visible_devices"))
            ),
            "tensor_parallel_size": context.get("tensor_parallel_size"),
            "gpus_per_node": context.get("gpus_per_node"),
            "is_master": True,
        }
    ]


def resource_context_gpu_ids(resource_context: Optional[dict] = None) -> list[str]:
    context = resource_context or current_request_resource_context()
    direct = _resource_gpu_ids(
        context.get("assigned_gpus", context.get("cuda_visible_devices"))
    )
    if direct:
        return direct
    nodes = resource_context_nodes(context)
    return list(nodes[0].get("assigned_gpus") or []) if len(nodes) == 1 else []


def managed_resource_error(
    require_gpus: bool = False, require_reservation: bool = False
) -> str:
    if not resource_pool_managed():
        return ""
    context = current_request_resource_context()
    nodes = resource_context_nodes(context)
    missing = []
    if not nodes:
        missing.append("nodes/runtime_node_id")
    if require_reservation and not str(context.get("reservation_id") or "").strip():
        missing.append("reservation_id")
    if require_gpus and (
        not nodes or any(not node.get("assigned_gpus") for node in nodes)
    ):
        missing.append("assigned_gpus")
    if not missing:
        return ""
    return (
        "资源池托管模式缺少必要的资源上下文，已拒绝执行。\n"
        f"missing={','.join(missing)}"
    )


def load_template_config() -> dict:
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def apply_node_managed_config(cfg: dict) -> dict:
    """Overlay worker-owned values from this worker's service.yaml."""
    effective = copy.deepcopy(cfg)
    template = load_template_config()
    template_env = template.get("ENV") or {}
    effective.setdefault("ENV", {})["HOST_IP"] = str(
        template_env.get("HOST_IP") or ""
    ).strip()
    return effective


def write_user_draft_config(path: str, cfg: dict) -> None:
    write_runtime_config(path, apply_node_managed_config(cfg))


def sync_worker_service_host_ip() -> dict:
    """Persist this worker's detected IP in its node-local service.yaml."""
    cfg = load_template_config()
    env = cfg.setdefault("ENV", {})
    configured_ip = str(env.get("HOST_IP") or "").strip()
    worker_ip = get_local_ip()
    changed = configured_ip != worker_ip
    if changed:
        env["HOST_IP"] = worker_ip
        write_runtime_config(CONFIG_FILE, cfg)
    return {
        "changed": changed,
        "configured_ip": configured_ip,
        "worker_ip": worker_ip,
        "config_file": CONFIG_FILE,
    }


def service_log_root_from_config(cfg: dict) -> str:
    log_dir = cfg["ENV"]["LOG_DIR"]
    if os.path.isabs(log_dir):
        return os.path.normpath(log_dir)
    return os.path.normpath(f"../{log_dir}")


def get_service_log_root() -> str:
    return service_log_root_from_config(load_template_config())


def get_agent_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_nodes_config() -> dict:
    if not os.path.exists(NODES_CONFIG_FILE):
        return {}
    with open(NODES_CONFIG_FILE) as f:
        data = yaml.safe_load(f) or {}
    nodes = data.get("NODES", {})
    return nodes if isinstance(nodes, dict) else {}


def is_node_enabled(node: dict) -> bool:
    value = node.get("ENABLED", True)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off", "disabled"}
    return bool(value)


def enabled_nodes() -> dict:
    return {
        name: node
        for name, node in load_nodes_config().items()
        if is_node_enabled(node)
    }


def node_identity_matches(node_cfg: dict, key: str) -> bool:
    return (
        str(node_cfg.get("NAME", "")).strip() == key
        or str(node_cfg.get("HOST", "")).strip() == key
        or str(node_cfg.get("RESOURCE_NODE_ID", "")).strip() == key
    )


def managed_resource_node_ids() -> set[str]:
    if not resource_pool_managed():
        return set()
    return {
        str(node.get("runtime_node_id") or "").strip()
        for node in resource_context_nodes()
        if str(node.get("runtime_node_id") or "").strip()
    }


def managed_resource_node_id() -> str:
    return next(iter(managed_resource_node_ids()), "")


def node_matches_resource(node_key: str, node_cfg: dict) -> bool:
    resource_node_ids = managed_resource_node_ids()
    if not resource_node_ids:
        return not resource_pool_managed()
    identities = {
        str(node_key).strip(),
        str(node_cfg.get("RESOURCE_NODE_ID") or "").strip(),
        str(node_cfg.get("NAME") or "").strip(),
        str(node_cfg.get("HOST") or "").strip(),
    }
    return bool(resource_node_ids.intersection(identities))


def resource_context_for_node(
    node_key: str,
    node_cfg: dict,
    resource_context: Optional[dict] = None,
) -> dict:
    """Narrow a managed multi-node context to one worker allocation."""
    context = resource_context or current_request_resource_context()
    if not resource_pool_managed() or not context:
        return dict(context)
    identities = {
        str(node_key).strip(),
        str(node_cfg.get("RESOURCE_NODE_ID") or "").strip(),
        str(node_cfg.get("NAME") or "").strip(),
        str(node_cfg.get("HOST") or "").strip(),
    }
    matched = next(
        (
            node
            for node in resource_context_nodes(context)
            if str(node.get("runtime_node_id") or "").strip() in identities
        ),
        None,
    )
    if not matched:
        return {}
    narrowed = {
        key: value
        for key, value in context.items()
        if key
        not in {
            "nodes",
            "runtime_node_id",
            "assigned_gpus",
            "cuda_visible_devices",
            "tensor_parallel_size",
            "gpus_per_node",
        }
    }
    narrowed.update(matched)
    narrowed["assigned_gpus"] = ",".join(matched.get("assigned_gpus") or [])
    return narrowed


def resource_allowed_nodes() -> dict:
    nodes = enabled_nodes()
    if not resource_pool_managed():
        return nodes
    return {
        key: value
        for key, value in nodes.items()
        if node_matches_resource(key, value)
    }


def resolve_node_config(node: str, require_enabled: bool = True) -> tuple[str, dict]:
    key = str(node or "").strip()
    if not key and resource_pool_managed():
        matches = list(resource_allowed_nodes().items())
        if len(matches) == 1:
            key = matches[0][0]
    if not key:
        raise ValueError("node is required")

    nodes = load_nodes_config()
    if key in nodes:
        node_cfg = nodes[key]
        node_key = key
    else:
        matches = [
            (name, item)
            for name, item in nodes.items()
            if node_identity_matches(item, key)
        ]
        if len(matches) != 1:
            available = []
            for name, item in enabled_nodes().items():
                available.append(name)
            available_text = ", ".join(available) or "none"
            raise ValueError(
                f"Unknown node: {node or key}. Available enabled nodes: {available_text}"
            )
        node_key, node_cfg = matches[0]

    if require_enabled and not is_node_enabled(node_cfg):
        raise ValueError(f"Node disabled: {node_key}")
    if not node_cfg.get("TOOL_URL") and not node_cfg.get("URL"):
        raise ValueError(f"Node URL missing: {node_key}")
    if resource_pool_managed() and not node_matches_resource(node_key, node_cfg):
        runtime_node_ids = ",".join(sorted(managed_resource_node_ids())) or "missing"
        raise ValueError(
            f"Node outside resource boundary: node={node_key}, "
            f"runtime_node_ids={runtime_node_ids}"
        )
    return node_key, node_cfg


def save_nodes_config(nodes: dict) -> None:
    with open(NODES_CONFIG_FILE, "w") as f:
        yaml.safe_dump(
            {"NODES": nodes},
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def set_node_enabled(node: str, enabled: bool) -> str:
    if resource_pool_managed():
        return "资源池托管模式下禁止通过 Agent 修改全局节点启停状态。"
    nodes = load_nodes_config()
    if not nodes:
        return f"暂无节点配置: {NODES_CONFIG_FILE}"

    node_key, _ = resolve_node_config(node, require_enabled=False)
    current_enabled = is_node_enabled(nodes[node_key])
    if current_enabled == enabled:
        status = "启用" if enabled else "禁用"
        return f"节点已处于{status}状态: {node_key}"

    nodes[node_key]["ENABLED"] = bool(enabled)
    save_nodes_config(nodes)
    status = "启用" if enabled else "禁用"
    return f"节点已{status}: {node_key}\n配置文件: {NODES_CONFIG_FILE}"


def get_node_tool_url(node_url: str) -> str:
    url = str(node_url or "").rstrip("/")
    if url.endswith("/worker") or url.endswith("/inference_agent"):
        return f"{url}/tool"
    if url.endswith("/worker/tool") or url.endswith("/inference_agent/tool"):
        return url
    return f"{url}/worker/tool"


def call_node_tool(
    node: str,
    tool_name: str,
    args: Optional[dict] = None,
    timeout: int = NODE_AGENT_TIMEOUT,
) -> dict:
    node_key, node_cfg = resolve_node_config(node)
    tool_url = node_cfg.get("TOOL_URL") or get_node_tool_url(node_cfg.get("URL", ""))
    payload = {
        "tool": tool_name,
        "args": args or {},
    }
    user_id = current_request_user_id()
    if user_id:
        payload["user_id"] = user_id
    thread_id = current_request_thread_id()
    if thread_id:
        payload["thread_id"] = thread_id
    resource_context = current_request_resource_context()
    if resource_context:
        if resource_pool_managed():
            resource_context = resource_context_for_node(
                node_key, node_cfg, resource_context
            )
            if not resource_context:
                raise RuntimeError(
                    f"Node outside resource boundary: node={node_key}"
                )
        payload["resource_context"] = resource_context
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        tool_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Node tool HTTP error: node={node_key}, tool={tool_name}, "
            f"status={e.code}, body={error_body}"
        )
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Node tool connection error: node={node_key}, url={tool_url}, error={e}"
        )
    except TimeoutError:
        raise RuntimeError(
            f"Node tool request timeout: node={node_key}, tool={tool_name}, timeout={timeout}s"
        )

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Node tool returned invalid JSON: node={node_key}, body={body[:1000]}"
        )

    result["_node_key"] = node_key
    result["_node_tool_url"] = tool_url
    return result


def format_node_tool_response(node: str, response: dict) -> str:
    lines = [
        f"node={response.get('_node_key', node)}",
        f"tool_url={response.get('_node_tool_url', '')}",
        f"tool={response.get('tool', '')}",
        f"status={response.get('status', '')}",
        "",
        str(response.get("result", "")),
    ]
    return "\n".join(lines).strip()


def build_node_tool_response(node: str, response: dict) -> dict:
    payload = response.get("data") if isinstance(response, dict) else {}
    if not isinstance(payload, dict):
        payload = {}

    node_key = response.get("_node_key", node) if isinstance(response, dict) else node
    node_data = {}
    if payload.get("config_draft") is not None:
        node_data["config_draft"] = payload["config_draft"]
    if payload.get("service_instances") is not None:
        node_data["service_instances"] = payload["service_instances"]
    if payload.get("benchmark_reports"):
        node_data["benchmark_reports"] = payload["benchmark_reports"]

    response_data = {"nodes": {}}
    if node_data:
        response_data["nodes"][node_key] = node_data

    return {
        "_tool_text": format_node_tool_response(node, response),
        "_response_data": response_data,
    }


def node_tool_text(node: str, tool_name: str, args: Optional[dict] = None) -> str:
    return format_node_tool_response(node, call_node_tool(node, tool_name, args))


def node_tool_structured(node: str, tool_name: str, args: Optional[dict] = None) -> dict:
    return build_node_tool_response(node, call_node_tool(node, tool_name, args))


def append_start_target_hint(text: str, node: str) -> str:
    lowered = str(text).lower()
    if (
        "insufficient_memory" not in lowered
        and "显存不足" not in str(text)
        and "低于最低需求" not in str(text)
    ):
        return text
    hint = (
        f"\n\n提示: 如果该节点资源不足，可调用 "
        f"node_recommend_start_target(target_node='{node}') 推荐其他可用节点。"
    )
    if "node_recommend_start_target" in str(text):
        return text
    return str(text) + hint


def node_is_worker(node_cfg: dict) -> bool:
    role = str(node_cfg.get("ROLE", "worker")).strip().lower()
    return "worker" in role or role in {"", "both"}


def response_result_text(response: dict) -> str:
    result = response.get("result", "")
    if isinstance(result, dict):
        return str(result.get("analysis", result))
    return str(result)


def parse_recommend_result(response: dict) -> dict:
    result = response.get("result", {})
    if not isinstance(result, dict):
        return {
            "ok": False,
            "current_ok": False,
            "recommended_gpus": "",
            "recommended_tp": "",
            "analysis": str(result),
        }
    return {
        "ok": bool(result.get("ok")),
        "current_ok": bool(result.get("current_ok")),
        "recommended_gpus": str(result.get("recommended_gpus") or ""),
        "recommended_tp": result.get("recommended_tp") or "",
        "analysis": str(result.get("analysis") or ""),
    }


def format_agent_relative_path(path: str, base_dir: Optional[str] = None) -> str:
    if not path:
        return path
    abs_path = (
        path
        if os.path.isabs(path)
        else os.path.abspath(os.path.join(base_dir or os.getcwd(), path))
    )
    try:
        rel_path = os.path.relpath(abs_path, get_agent_root())
    except ValueError:
        return path
    if rel_path == "." or rel_path.startswith(".." + os.sep) or rel_path == "..":
        return path
    return rel_path


def load_json_file(path: str, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default
    return data if data is not None else default


@contextmanager
def json_file_lock(path: str):
    """Serialize read-modify-write operations for one JSON state file."""
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def iter_json_records(root: str, filename: str):
    if not os.path.isdir(root):
        return
    for record_id in os.listdir(root):
        path = os.path.join(root, record_id, filename)
        if not os.path.isfile(path):
            continue
        data = load_json_file(path)
        if isinstance(data, dict):
            yield record_id, path, data


def get_service_run_log_root() -> str:
    return os.path.join(get_service_log_root(), "services")


def get_service_instance_root() -> str:
    return os.path.join(get_service_run_log_root(), "runs")


def get_legacy_service_instance_root() -> str:
    return os.path.join(get_service_run_log_root(), "instances")


def get_service_instance_dir(instance_id: str) -> str:
    if "/" in str(instance_id) or ".." in str(instance_id):
        raise ValueError("Invalid instance_id")
    return os.path.join(get_service_instance_root(), str(instance_id))


def get_service_instance_meta_path(instance_id: str) -> str:
    return os.path.join(get_service_instance_dir(instance_id), "meta.json")


def list_service_instance_ids() -> list[str]:
    root = get_service_instance_root()
    if not os.path.isdir(root):
        return []
    return sorted(
        [
            name
            for name in os.listdir(root)
            if os.path.isdir(os.path.join(root, name))
            and os.path.exists(os.path.join(root, name, "meta.json"))
        ],
        key=lambda name: os.path.getmtime(os.path.join(root, name, "meta.json")),
        reverse=True,
    )


def load_service_instance(instance_id: str) -> dict:
    path = get_service_instance_meta_path(instance_id)
    if not os.path.exists(path):
        return {}
    data = load_json_file(path, {})
    return data if isinstance(data, dict) else {}


def save_service_instance(meta: dict) -> None:
    instance_id = str(meta.get("instance_id") or "")
    if not instance_id:
        raise ValueError("instance_id is required")
    os.makedirs(get_service_instance_dir(instance_id), exist_ok=True)
    atomic_write_json(get_service_instance_meta_path(instance_id), meta)


def get_service_log_dir(run_id: str = "latest") -> str:
    log_root = get_service_run_log_root()
    if run_id == "all":
        run_id = "latest"
    if not run_id or run_id == "latest":
        current_latest = resolve_service_instance_id(
            "latest", scope="mine", require_running=False
        )
        if current_latest:
            instance_dir = get_service_instance_dir(current_latest)
            if os.path.exists(instance_dir):
                return instance_dir
        latest_dir = os.path.join(log_root, "latest")
        if os.path.exists(latest_dir):
            return latest_dir
        legacy_latest_dir = os.path.join(get_service_log_root(), "latest")
        if os.path.exists(legacy_latest_dir):
            return legacy_latest_dir
        return log_root

    if "/" in run_id or ".." in run_id:
        raise ValueError("Invalid run_id")
    run_dir = os.path.join(log_root, "runs", run_id)
    if os.path.exists(run_dir):
        return run_dir
    legacy_instance_dir = os.path.join(get_legacy_service_instance_root(), run_id)
    if os.path.exists(legacy_instance_dir):
        return legacy_instance_dir
    legacy_run_dir = os.path.join(get_service_log_root(), "runs", run_id)
    if os.path.exists(legacy_run_dir):
        return legacy_run_dir
    return run_dir


def get_log_paths(service: str, run_id: str = "latest"):
    log_dir = get_service_log_dir(run_id)
    if service == "all":
        return list(dict.fromkeys(os.path.join(log_dir, f) for f in LOG_FILES.values()))
    if service not in LOG_FILES:
        raise ValueError(
            f"Invalid service: {service}. Valid options: {list(LOG_FILES.keys())}"
        )

    return [os.path.join(log_dir, LOG_FILES[service])]


def get_latest_service_log_run() -> str:
    current_latest = resolve_service_instance_id(
        "latest", scope="mine", require_running=False
    )
    if current_latest:
        return current_latest

    log_root = get_service_run_log_root()
    latest_path = os.path.join(log_root, "latest")
    if not os.path.exists(latest_path):
        latest_path = os.path.join(get_service_log_root(), "latest")
    if os.path.islink(latest_path):
        target = os.readlink(latest_path)
        return os.path.basename(target.rstrip(os.sep))
    if os.path.isdir(latest_path):
        return os.path.basename(os.path.realpath(latest_path))
    return ""


def refresh_service_latest_pointer() -> str:
    """Point service latest files to the newest remaining instance."""
    log_root = get_service_run_log_root()
    latest_link = os.path.join(log_root, "latest")
    latest_json = get_service_start_latest_path()
    instance_ids = list_service_instance_ids()

    if not instance_ids:
        for path in (latest_link, latest_json):
            try:
                if os.path.lexists(path):
                    if os.path.isdir(path) and not os.path.islink(path):
                        shutil.rmtree(path)
                    else:
                        os.unlink(path)
            except OSError:
                pass
        return ""

    instance_id = instance_ids[0]
    instance_dir = get_service_instance_dir(instance_id)
    meta = load_service_instance(instance_id)
    status_file = str(meta.get("status_file") or os.path.join(instance_dir, "status.json"))

    try:
        if os.path.lexists(latest_link):
            os.unlink(latest_link)
        os.symlink(instance_dir, latest_link)
    except OSError:
        pass

    atomic_write_json(
        latest_json,
        {
            "run_id": str(meta.get("run_id") or instance_id),
            "instance_id": instance_id,
            "status_file": status_file,
        },
    )
    return instance_id


def list_service_log_runs_text(limit: int = 10, instance_id: str = "") -> str:
    limit = clamp_int(limit, 10, 1, MAX_LIST_LIMIT)
    log_root = get_service_run_log_root()
    runs_dir = os.path.join(log_root, "runs")
    instances_dir = get_service_instance_root()
    legacy_instances_dir = get_legacy_service_instance_root()
    if not os.path.isdir(runs_dir):
        legacy_runs_dir = os.path.join(get_service_log_root(), "runs")
        if os.path.isdir(legacy_runs_dir):
            runs_dir = legacy_runs_dir
    latest_run = get_latest_service_log_run()

    entries = []
    resolved_instance_id = ""
    if instance_id:
        access_error = service_instance_access_error(instance_id, "查看日志")
        if access_error:
            return access_error
        resolved_instance_id = resolve_service_instance_id(
            instance_id, scope="mine", require_running=False
        )
        if not resolved_instance_id:
            return f"未找到推理服务实例: {instance_id}"

    if os.path.isdir(instances_dir):
        for instance_id in os.listdir(instances_dir):
            if resolved_instance_id and instance_id != resolved_instance_id:
                continue
            instance_dir = os.path.join(instances_dir, instance_id)
            if not os.path.isdir(instance_dir) or not os.path.exists(
                os.path.join(instance_dir, "meta.json")
            ):
                continue
            entries.append(("instance", instance_id, instance_dir))

    if not resolved_instance_id and os.path.isdir(runs_dir):
        for run_id in os.listdir(runs_dir):
            run_dir = os.path.join(runs_dir, run_id)
            if not os.path.isdir(run_dir):
                continue
            if os.path.exists(os.path.join(run_dir, "meta.json")):
                continue
            entries.append(("run", run_id, run_dir))

    if os.path.isdir(legacy_instances_dir):
        for legacy_instance_id in os.listdir(legacy_instances_dir):
            if resolved_instance_id and legacy_instance_id != resolved_instance_id:
                continue
            legacy_instance_dir = os.path.join(legacy_instances_dir, legacy_instance_id)
            if not os.path.isdir(legacy_instance_dir):
                continue
            entries.append(("legacy_instance", legacy_instance_id, legacy_instance_dir))

    if not entries:
        if resolved_instance_id:
            return f"该实例暂无服务日志记录: instance_id={resolved_instance_id}"
        return (
            "暂无服务启动日志。\n"
            f"runs_dir={format_agent_relative_path(runs_dir)}"
        )

    entries.sort(key=lambda item: os.path.getmtime(item[2]), reverse=True)

    lines = ["服务日志启动记录:"]
    if resolved_instance_id:
        lines.append(f"instance_id={resolved_instance_id}")
    if latest_run:
        lines.append(f"latest -> {latest_run}")
    else:
        lines.append("latest -> 未设置")

    visible_entries = entries[:limit]
    lines.append(f"显示 {len(visible_entries)} / {len(entries)} 条，limit={limit}")
    if len(entries) > limit:
        lines.append(f"还有 {len(entries) - limit} 条未显示，可增大 limit 查看。")

    for entry_type, run_id, run_dir in visible_entries:
        mtime = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(run_dir))
        )
        log_names = sorted(
            name for name in os.listdir(run_dir) if name.endswith(".log")
        )
        marker = " *latest*" if run_id == latest_run else ""
        instance_note = ""
        if entry_type == "instance":
            meta = load_service_instance(run_id)
            instance_note = (
                f" | status={meta.get('status', '')}"
                f" | gpus={meta.get('actual_gpus', '')}"
                f" | owner={service_instance_owner(meta)}"
            )
        lines.append(
            f"- {run_id}{marker} | type={entry_type}{instance_note} | {mtime} | logs: "
            + (", ".join(log_names) if log_names else "none")
        )

    return "\n".join(lines)


def get_service_start_latest_path() -> str:
    return os.path.join(get_service_run_log_root(), "latest.json")


def get_legacy_service_start_latest_path() -> str:
    return os.path.join(get_service_log_root(), "service_start_latest.json")


def service_start_status_text(run_id: str = "latest") -> str:
    log_root = get_service_run_log_root()
    if not run_id or run_id == "latest":
        current_latest = resolve_service_instance_id(
            "latest", scope="mine", require_running=False
        )
        if current_latest:
            instance_meta = load_service_instance(current_latest)
            run_id = str(instance_meta.get("run_id") or current_latest)
            status_file = str(
                instance_meta.get("status_file")
                or os.path.join(get_service_instance_dir(current_latest), "status.json")
            )
        else:
            latest_path = get_service_start_latest_path()
            if not os.path.exists(latest_path):
                legacy_latest_path = get_legacy_service_start_latest_path()
                if os.path.exists(legacy_latest_path):
                    latest_path = legacy_latest_path
                    log_root = get_service_log_root()
                else:
                    return f"暂无启动状态记录: {latest_path}"
            with open(latest_path, "r") as f:
                latest = json.load(f)
            run_id = latest.get("run_id", "latest")
            if latest.get("status_file"):
                status_file = latest.get("status_file")
            elif run_id and run_id != "latest":
                status_file = os.path.join(log_root, "runs", run_id, "status.json")
            else:
                status_file = latest.get("status_file")
    else:
        if "/" in run_id or ".." in run_id:
            return "Invalid run_id"
        status_file = os.path.join(get_service_log_dir(run_id), "status.json")

    if not status_file or not os.path.exists(status_file):
        return f"启动状态文件不存在: {status_file}"

    try:
        with open(status_file, "r") as f:
            meta = json.load(f)
    except json.JSONDecodeError as e:
        return f"启动状态文件不是合法 JSON: {status_file}\n错误: {e}"

    script_pid = int(meta.get("script_pid") or 0)
    script_running = is_process_running(script_pid) if script_pid else False
    ports = meta.get("ports", {})
    port_lines = []
    all_running = True
    for name, port in ports.items():
        running = check_port_status(int(port))
        all_running = all_running and running
        mark = "RUNNING" if running else "STOPPED"
        port_lines.append(f"- {name}: {port} {mark}")

    stored_status = meta.get("status", "unknown")
    if stored_status == "finished" and all_running:
        status_value = "finished"
    elif script_running:
        status_value = "starting"
    elif all_running:
        status_value = "finished"
    else:
        status_value = "failed"

    lines = [
        "服务启动状态:",
        f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"status={status_value}",
        f"stored_status={stored_status}",
        f"run_id={meta.get('run_id', run_id)}",
        f"script_pid={script_pid}",
        f"script_running={script_running}",
        f"started_at={meta.get('started_at')}",
        f"finished_at={meta.get('finished_at')}",
        f"log_dir={meta.get('log_dir')}",
        f"status_file={status_file}",
        "ports:",
        *port_lines,
    ]

    error = meta.get("error")
    if error:
        lines.append(f"error={error}")

    if status_value == "starting":
        lines.append(
            "note=服务仍在后台启动中。请把当前启动状态告知用户，不要连续调用 "
            "service_start_status、service_status 或日志工具轮询；用户稍后询问时再查询。"
        )

    return "\n".join(lines)


def user_config_key(user_id: str) -> str:
    digest = hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:12]
    return f"user_{digest}"


def get_user_config_dir(user_id: str = "") -> str:
    user_id = user_id or current_request_user_id()
    return os.path.join(get_service_log_root(), "configs", "users", user_config_key(user_id))


def get_user_draft_config_path(user_id: str = "") -> str:
    user_id = user_id or current_request_user_id()
    return os.path.join(get_user_config_dir(user_id), "service.draft.yaml")


def get_user_config_meta_path(user_id: str = "") -> str:
    user_id = user_id or current_request_user_id()
    return os.path.join(get_user_config_dir(user_id), "meta.json")


def ensure_user_draft_config() -> str:
    user_id = current_request_user_id()
    if not user_id:
        return CONFIG_FILE

    draft_path = get_user_draft_config_path(user_id)
    if os.path.exists(draft_path):
        with open(draft_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
        synchronized = apply_node_managed_config(existing)
        if synchronized != existing:
            write_runtime_config(draft_path, synchronized)
        return draft_path

    os.makedirs(os.path.dirname(draft_path), exist_ok=True)
    cfg = load_template_config()
    write_user_draft_config(draft_path, cfg)
    atomic_write_json(
        get_user_config_meta_path(user_id),
        {
            "user_id": user_id,
            "user_key": user_config_key(user_id),
            "source_config": CONFIG_FILE,
            "draft_config": draft_path,
            "created_at": current_time_text(),
            "updated_at": current_time_text(),
        },
    )
    return draft_path


def show_config() -> dict:
    """Show effective config: user draft plus worker-owned node values."""
    with open(ensure_user_draft_config()) as f:
        cfg = yaml.safe_load(f) or {}
    return apply_node_managed_config(cfg)


def show_public_config() -> dict:
    """Show service config fields intended for normal display."""
    cfg = copy.deepcopy(show_config())
    env = cfg.get("ENV")
    if isinstance(env, dict):
        for key in list(env.keys()):
            if str(key).startswith("HUMANEVAL") or str(key).startswith("LCB_"):
                env.pop(key, None)
    return cfg


def run_command(cmd: str) -> str:
    """Run shell command safely and return output."""
    try:
        out = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT
        ).decode()
        return out
    except subprocess.CalledProcessError as e:
        return f"[ERROR]\n{e.output.decode()}"


def check_port(port: int, timeout: float = 0.3) -> bool:
    """Return True when a local TCP service accepts connections on the port."""
    hosts = []
    try:
        hosts.append(get_local_ip())
    except OSError:
        pass
    hosts.append("127.0.0.1")

    for host in dict.fromkeys(hosts):
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except (OSError, TypeError, ValueError):
            continue
    return False


DEFAULT_PORT_POOLS = {
    "VLLM_OPENAI_PORT": (7111, 7199),
    "INFERENCE_PORT": (7013, 7099),
    "UI_PORT": (7860, 7899),
    "DATA_ANNOTATION_PORT": (7216, 7299),
    "MASTER_PORT": (50121, 50200),
}

SERVICE_INSTANCE_PORT_NAMES = (
    "vllm",
    "inference",
    "ui",
    "case2chat",
    "master",
)


def process_service_run_id(pid: int) -> str:
    """Return SERVICE_RUN_ID for a live process, or empty when unavailable."""
    try:
        return str(psutil.Process(int(pid)).environ().get("SERVICE_RUN_ID") or "").strip()
    except (psutil.Error, OSError, TypeError, ValueError):
        return ""


def invalidate_port_listener_cache() -> None:
    with PORT_LISTENER_CACHE_LOCK:
        PORT_LISTENER_CACHE["time"] = 0.0
        PORT_LISTENER_CACHE["listeners"] = {}
        PORT_LISTENER_CACHE["scan_failed"] = False


def cached_tcp_listeners() -> tuple[dict[int, set[int]], bool]:
    """Return a short-lived snapshot of local TCP listener PIDs."""
    now = time.monotonic()
    with PORT_LISTENER_CACHE_LOCK:
        if now - float(PORT_LISTENER_CACHE["time"]) <= PORT_LISTENER_CACHE_TTL:
            return (
                {
                    port: set(pids)
                    for port, pids in PORT_LISTENER_CACHE["listeners"].items()
                },
                bool(PORT_LISTENER_CACHE["scan_failed"]),
            )

        listeners = {}
        scan_failed = False
        try:
            connections = psutil.net_connections(kind="tcp")
        except (psutil.Error, OSError):
            connections = []
            scan_failed = True
        for connection in connections:
            if connection.status != psutil.CONN_LISTEN or not connection.laddr:
                continue
            port = int(connection.laddr.port)
            listeners.setdefault(port, set())
            if connection.pid:
                listeners[port].add(int(connection.pid))

        PORT_LISTENER_CACHE["time"] = now
        PORT_LISTENER_CACHE["listeners"] = listeners
        PORT_LISTENER_CACHE["scan_failed"] = scan_failed
        return (
            {port: set(pids) for port, pids in listeners.items()},
            scan_failed,
        )


def listening_port_pids(ports: set[int]) -> tuple[dict[int, set[int]], set[int]]:
    """Return listener PIDs and ports whose listener ownership is unavailable."""
    requested = set()
    for value in ports:
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if port > 0:
            requested.add(port)
    if not requested:
        return {}, set()
    snapshot, scan_failed = cached_tcp_listeners()
    listeners = {port: set(snapshot.get(port) or set()) for port in requested}
    unresolved = set()
    for port in requested:
        if port in snapshot and not listeners[port]:
            unresolved.add(port)
        elif scan_failed and check_port(port):
            unresolved.add(port)
        elif not listeners[port] and check_port(port):
            unresolved.add(port)
    return listeners, unresolved


def service_instance_port_ownership(
    meta: dict,
    listener_snapshot: Optional[tuple[dict[int, set[int]], set[int]]] = None,
) -> dict[str, list[dict]]:
    """Classify recorded ports as owned, reused, unverified, or closed."""
    instance_id = str(meta.get("instance_id") or meta.get("run_id") or "").strip()
    configured_ports = {}
    for name, value in (meta.get("ports") or {}).items():
        if name not in SERVICE_INSTANCE_PORT_NAMES:
            continue
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if port > 0:
            configured_ports[str(name)] = port

    if listener_snapshot is None:
        listeners, unresolved_ports = listening_port_pids(
            set(configured_ports.values())
        )
    else:
        listeners, unresolved_ports = listener_snapshot
    result = {"owned": [], "reused": [], "unverified": [], "closed": []}
    for name, port in configured_ports.items():
        pids = sorted(listeners.get(port) or [])
        entry = {"name": name, "port": port, "pids": pids}
        if not pids:
            category = "unverified" if port in unresolved_ports else "closed"
        else:
            run_ids = {pid: process_service_run_id(pid) for pid in pids}
            entry["run_ids"] = run_ids
            if any(run_id == instance_id for run_id in run_ids.values()):
                category = "owned"
            elif any(not run_id for run_id in run_ids.values()):
                category = "unverified"
            else:
                category = "reused"
        result[category].append(entry)
    return result


def service_instance_process_ownership(
    meta: dict,
    port_ownership: Optional[dict[str, list[dict]]] = None,
    tracked_pids: Optional[list[int]] = None,
) -> dict[str, list[int]]:
    """Classify live recorded and port-listener PIDs by SERVICE_RUN_ID."""
    instance_id = str(meta.get("instance_id") or meta.get("run_id") or "").strip()
    candidates = set(service_instance_recorded_pids(meta))
    script_pid = int(meta.get("script_pid") or 0)
    if script_pid:
        candidates.add(script_pid)
    for value in tracked_pids or []:
        try:
            pid = int(value)
        except (TypeError, ValueError):
            continue
        if pid > 0:
            candidates.add(pid)

    port_ownership = port_ownership or service_instance_port_ownership(meta)
    port_categories = {}
    for category in ("owned", "reused", "unverified"):
        for entry in port_ownership[category]:
            for pid in entry.get("pids") or []:
                candidates.add(int(pid))
                port_categories[int(pid)] = category

    result = {"owned": [], "reused": [], "unverified": []}
    for pid in sorted(candidates):
        if not pid_is_alive(pid):
            continue
        run_id = process_service_run_id(pid)
        if run_id == instance_id:
            category = "owned"
        elif run_id:
            category = "reused"
        else:
            category = port_categories.get(pid, "unverified")
        result[category].append(pid)
    return result


def terminate_instance_owned_processes(meta: dict, timeout: float = 3.0) -> dict:
    """Terminate only processes whose SERVICE_RUN_ID matches the instance."""
    ownership = service_instance_process_ownership(meta)
    root_processes = []
    for pid in ownership["owned"]:
        try:
            root_processes.append(psutil.Process(pid))
        except (psutil.Error, OSError):
            continue

    processes = {}
    for process in root_processes:
        try:
            for child in process.children(recursive=True):
                processes[child.pid] = child
        except (psutil.Error, OSError):
            pass
        processes[process.pid] = process

    errors = []
    for process in processes.values():
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            continue
        except (psutil.Error, OSError) as exc:
            errors.append({"pid": process.pid, "error": str(exc)})

    _, alive = psutil.wait_procs(list(processes.values()), timeout=timeout)
    killed = []
    for process in alive:
        try:
            process.kill()
            killed.append(process.pid)
        except psutil.NoSuchProcess:
            continue
        except (psutil.Error, OSError) as exc:
            errors.append({"pid": process.pid, "error": str(exc)})
    invalidate_port_listener_cache()
    return {
        "matched_pids": sorted(processes),
        "force_killed_pids": sorted(killed),
        "errors": errors,
    }


def configured_port_pool(cfg: dict, key: str) -> tuple[int, int]:
    pools = cfg.get("PORT_POOLS") or {}
    pool = pools.get(key) if isinstance(pools, dict) else None
    default_start, default_end = DEFAULT_PORT_POOLS[key]
    if isinstance(pool, dict):
        start = int(pool.get("START") or pool.get("start") or default_start)
        end = int(pool.get("END") or pool.get("end") or default_end)
        return start, end
    if isinstance(pool, list) and len(pool) >= 2:
        return int(pool[0]), int(pool[1])
    configured = None
    if key == "MASTER_PORT":
        configured = cfg.get("ENV", {}).get("MASTER_PORT")
    else:
        configured = cfg.get("PORTS", {}).get(key)
    if configured:
        base = int(configured)
        return base, max(base, default_end)
    return default_start, default_end


def service_instance_holds_port_lease(
    meta: dict,
    listener_snapshot: Optional[tuple[dict[int, set[int]], set[int]]] = None,
) -> bool:
    """Return whether an instance must keep its recorded ports reserved."""
    status = str(meta.get("status") or "").strip().lower()
    if status in {"allocating", "starting", "running", "degraded"}:
        return True
    if status not in {"stopped", "failed"}:
        return True

    port_ownership = service_instance_port_ownership(meta, listener_snapshot)
    process_ownership = service_instance_process_ownership(meta, port_ownership)
    if process_ownership["owned"] or process_ownership["unverified"]:
        return True
    return bool(port_ownership["owned"] or port_ownership["unverified"])


def used_instance_ports() -> set[int]:
    ports = set()
    instances = [
        load_service_instance(instance_id)
        for instance_id in list_service_instance_ids()
    ]
    configured_ports = set()
    for meta in instances:
        for value in (meta.get("ports") or {}).values():
            try:
                configured_ports.add(int(value))
            except (TypeError, ValueError):
                continue
    listener_snapshot = listening_port_pids(configured_ports)

    for meta in instances:
        if not meta or not service_instance_holds_port_lease(
            meta, listener_snapshot
        ):
            continue
        meta_ports = meta.get("ports") or {}
        if not isinstance(meta_ports, dict):
            continue
        for port in meta_ports.values():
            try:
                ports.add(int(port))
            except (TypeError, ValueError):
                continue
    return ports


def allocate_free_port(cfg: dict, key: str, reserved: set[int]) -> int:
    start, end = configured_port_pool(cfg, key)
    for port in range(start, end + 1):
        if port in reserved:
            continue
        if check_port(port):
            continue
        reserved.add(port)
        return port
    raise RuntimeError(f"No free port for {key} in range {start}-{end}")


def pending_port_lease_dir() -> str:
    return os.path.join(get_service_log_root(), "port-leases")


def pending_port_lease_path(instance_id: str) -> str:
    return os.path.join(pending_port_lease_dir(), f"{instance_id}.json")


def load_pending_instance_ports() -> set[int]:
    lease_dir = pending_port_lease_dir()
    if not os.path.isdir(lease_dir):
        return set()
    now = time.time()
    ports = set()
    for name in os.listdir(lease_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(lease_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                lease = json.load(f) or {}
            created_at = float(lease.get("created_at") or 0)
            instance_id = str(lease.get("instance_id") or "")
            if instance_id and load_service_instance(instance_id):
                os.unlink(path)
                continue
            if (
                created_at
                and now - created_at > PENDING_PORT_LEASE_TTL
            ):
                os.unlink(path)
                continue
            for value in (lease.get("ports") or {}).values():
                ports.add(int(value))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return ports


def allocate_instance_ports(cfg: dict, instance_id: str) -> dict:
    instance_id = str(instance_id or "").strip()
    if not instance_id:
        raise ValueError("instance_id is required for port allocation")
    lease_dir = pending_port_lease_dir()
    os.makedirs(lease_dir, exist_ok=True)
    lock_path = os.path.join(lease_dir, ".allocation.lock")
    with PORT_ALLOCATION_LOCK:
        with open(lock_path, "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            reserved = (
                used_instance_ports()
                | load_pending_instance_ports()
                | PENDING_INSTANCE_PORTS
            )
            allocated = {
                "vllm": allocate_free_port(cfg, "VLLM_OPENAI_PORT", reserved),
                "inference": allocate_free_port(cfg, "INFERENCE_PORT", reserved),
                "ui": allocate_free_port(cfg, "UI_PORT", reserved),
                "case2chat": allocate_free_port(
                    cfg, "DATA_ANNOTATION_PORT", reserved
                ),
                "master": allocate_free_port(cfg, "MASTER_PORT", reserved),
            }
            atomic_write_json(
                pending_port_lease_path(instance_id),
                {
                    "instance_id": instance_id,
                    "created_at": time.time(),
                    "ports": allocated,
                },
            )
            PENDING_INSTANCE_PORTS.update(allocated.values())
            return allocated


def release_pending_instance_ports(instance_id: str, ports: dict) -> None:
    lease_dir = pending_port_lease_dir()
    os.makedirs(lease_dir, exist_ok=True)
    lock_path = os.path.join(lease_dir, ".allocation.lock")
    with PORT_ALLOCATION_LOCK:
        with open(lock_path, "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                os.unlink(pending_port_lease_path(instance_id))
            except FileNotFoundError:
                pass
            for port in ports.values():
                try:
                    PENDING_INSTANCE_PORTS.discard(int(port))
                except (TypeError, ValueError):
                    continue


def service_status_data() -> dict:
    """Summarize current inference service status."""
    cfg = show_config()
    template_services = []
    for name, port in cfg["PORTS"].items():
        running = check_port(port)
        mark = "RUNNING" if running else "STOPPED"
        template_services.append(
            {
                "name": name,
                "port": int(port),
                "status": "running" if running else "stopped",
                "rawStatus": mark,
            }
        )

    current = current_request_user_id()
    all_instances = []
    for instance_id in list_service_instance_ids():
        meta = visible_service_instance_meta(instance_id)
        if not meta:
            continue
        owner_user_id = str(meta.get("owner_user_id") or "")
        owner = "self" if current and owner_user_id == current else "other"
        ports = meta.get("ports") or {}
        all_instances.append(
            {
                "instance_id": instance_id,
                "owner": owner,
                "status": str(meta.get("status") or ""),
                "gpus": str(meta.get("actual_gpus") or ""),
                "model": str(meta.get("model") or ""),
                "ports": ports,
                "started_at": str(meta.get("started_at") or ""),
                "finished_at": str(meta.get("finished_at") or ""),
                "log_dir": format_agent_relative_path(meta.get("log_dir", "")),
            }
        )
    all_instances.sort(
        key=lambda item: (
            -parse_time_sort_value(item["started_at"]),
            status_sort_rank(item["status"]),
            item["instance_id"],
        )
    )

    active_instances = [
        item
        for item in all_instances
        if item["status"] in {"running", "starting", "degraded"}
    ]
    self_active = [item for item in active_instances if item["owner"] == "self"]
    other_active = [item for item in active_instances if item["owner"] != "self"]
    recent_inactive = [
        item
        for item in all_instances
        if item["status"] not in {"running", "starting", "degraded"}
    ][:3]

    self_instances = [item for item in all_instances if item["owner"] == "self"]
    status_counts = {
        "starting": 0,
        "running": 0,
        "degraded": 0,
        "failed": 0,
        "stopped": 0,
    }
    for item in self_instances:
        status = item["status"] or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    always_returned = [
        copy.deepcopy(item)
        for item in self_instances
        if item["status"] in {"starting", "running", "degraded"}
    ]
    recent_failed = [
        copy.deepcopy(item)
        for item in self_instances
        if item["status"] == "failed"
    ][:5]
    recent_stopped = [
        copy.deepcopy(item)
        for item in self_instances
        if item["status"] == "stopped"
    ][:5]
    structured_items = always_returned + recent_failed + recent_stopped
    structured_items.sort(
        key=lambda item: (
            status_sort_rank(item["status"]),
            -parse_time_sort_value(item["started_at"]),
            item["instance_id"],
        )
    )
    for item in structured_items:
        item.pop("owner", None)
        item["gpus"] = [
            int(gpu) if str(gpu).isdigit() else str(gpu)
            for gpu in parse_visible_gpus(item.get("gpus", ""))
        ]

    service_instances = {
        "operation": "status",
        "summary": {
            "total": len(self_instances),
            **status_counts,
        },
        "returned": len(structured_items),
        "items": structured_items,
        "limits": {
            "failed": 5,
            "stopped": 5,
        },
    }

    lines = [
        "\n======== 推理服务状态 ========",
        f"current_time={current_time_text()}",
        "mode=multi_instance" if all_instances else "mode=template_ports_only",
    ]

    if all_instances:
        lines.append("")
        lines.append(f"当前用户活跃实例: {len(self_active)}")
        if self_active:
            for item in self_active:
                ports = item["ports"]
                lines.append(
                    "- "
                    f"instance_id={item['instance_id']} "
                    f"status={item['status']} "
                    f"gpus={item['gpus']} "
                    f"model={item['model']} "
                    f"vllm={ports.get('vllm', '')} "
                    f"inference={ports.get('inference', '')} "
                    f"ui={ports.get('ui', '')} "
                    f"started_at={item['started_at']}"
                )
        else:
            lines.append("- none")

        lines.append("")
        lines.append(f"其他用户活跃实例: {len(other_active)}")
        if other_active:
            for item in other_active:
                ports = item["ports"]
                lines.append(
                    "- "
                    f"instance_id={item['instance_id']} "
                    f"owner={item['owner']} "
                    f"status={item['status']} "
                    f"gpus={item['gpus']} "
                    f"inference={ports.get('inference', '')} "
                    f"ui={ports.get('ui', '')} "
                    f"started_at={item['started_at']}"
                )
        else:
            lines.append("- none")

        if recent_inactive:
            lines.append("")
            lines.append(f"最近非活跃实例: {len(recent_inactive)}")
            for item in recent_inactive:
                lines.append(
                    "- "
                    f"instance_id={item['instance_id']} "
                    f"owner={item['owner']} "
                    f"status={item['status']} "
                    f"gpus={item['gpus']} "
                    f"started_at={item['started_at']} "
                    f"finished_at={item['finished_at']}"
                )
    else:
        lines.append("当前没有推理服务实例记录。")

    lines.append("")
    lines.append("当前用户配置草稿端口状态(service.draft.yaml，仅用于下次启动/兼容旧模式):")
    for item in template_services:
        lines.append(
            f"- {item['name']} ({item['port']}): {item['rawStatus']}"
        )

    lines.append("============================\n")
    return {
        "service_instances": service_instances,
        "instances": {
            "active": active_instances,
            "self_active": self_active,
            "other_active": other_active,
            "recent_inactive": recent_inactive,
            "total": len(all_instances),
        },
        "text": "\n".join(lines),
    }


def build_local_tool_response(tool_text, response_data: Optional[dict] = None) -> dict:
    return {
        "_tool_text": str(tool_text),
        "_response_data": response_data or {},
    }


def check_port_status(port: int) -> str:
    """Check port status."""
    running = check_port(port)
    return running


def check_gpu_status() -> str:
    """Show GPU usage status (memory, utilization, process)."""

    bus_id_to_idx = {}
    resource_error = managed_resource_error(require_gpus=True)
    if resource_error:
        return resource_error
    allowed_gpus = (
        set(resource_context_gpu_ids()) if resource_pool_managed() else None
    )

    cmd = (
        "nvidia-smi --query-gpu=index,name,gpu_bus_id,memory.used,memory.total,utilization.gpu "
        "--format=csv,noheader,nounits"
    )

    output = run_command(cmd)

    if "[ERROR]" in output:
        return "无法获取 GPU 状态，请确认 nvidia-smi 是否可用。"

    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]

    result = ["\n====== GPU Status ======"]

    for line in lines:
        parts = [x.strip() for x in line.split(",")]
        if len(parts) != 6:
            result.append(f"Skip unparsable GPU line: {line}")
            continue
        idx, name, gpu_bus_id, used, total, util = parts
        if allowed_gpus is not None and idx not in allowed_gpus:
            continue

        bus_id_to_idx[gpu_bus_id] = idx
        result.append(
            f"GPU {idx} ({name}) | Bus-Id: {gpu_bus_id} | Memory-Usage: {used}/{total} MiB | GPU-Util: {util}%"
        )

    cmd_process = (
        "nvidia-smi --query-compute-apps=gpu_bus_id,pid,name,used_memory "
        "--format=csv,noheader,nounits"
    )
    process_output = run_command(cmd_process)

    result.append("\n====== GPU Processes ======")
    process_lines = [
        line.strip() for line in process_output.strip().splitlines() if line.strip()
    ]
    if (
        not process_lines
        or "[ERROR]" in process_output
        or any("No running processes found" in line for line in process_lines)
    ):
        result.append("No running GPU processes found.")
        result.append("========================\n")
        return "\n".join(result)

    for line in process_lines:
        parts = [x.strip() for x in line.split(",")]
        if len(parts) != 4:
            result.append(f"Skip unparsable process line: {line}")
            continue
        gpu_bus_id, pid, name, used = parts
        if gpu_bus_id not in bus_id_to_idx:
            continue
        result.append(
            f"GPU: {bus_id_to_idx.get(gpu_bus_id, 'Unknown')} | PID: {pid} {name} | GPU Memory Usage: {used} MiB"
        )

    result.append("========================\n")
    return "\n".join(result)


def get_local_ip():
    """Get local IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


def parse_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_model_config(model_dir: str) -> dict:
    config_path = os.path.join(model_dir, "config.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_text_model_config(model_cfg: dict) -> tuple[dict, list[str]]:
    notes = []
    if isinstance(model_cfg.get("text_config"), dict):
        text_cfg = dict(model_cfg["text_config"])
        notes.append("检测到嵌套 text_config，显存/参数估算按文本主干配置计算。")
        if "tie_word_embeddings" not in text_cfg and "tie_word_embeddings" in model_cfg:
            text_cfg["tie_word_embeddings"] = model_cfg["tie_word_embeddings"]
        return text_cfg, notes
    return model_cfg, notes


def model_architecture_notes(root_cfg: dict, text_cfg: dict) -> tuple[list[str], bool]:
    notes = []
    uncertain = False
    if root_cfg.get("vision_config") and root_cfg.get("language_model_only") is False:
        notes.append("检测到多模态模型，估算只覆盖文本主干，视觉模块和额外 runtime 开销未精确计入。")
        uncertain = True

    layer_types = text_cfg.get("layer_types")
    if isinstance(layer_types, list) and layer_types:
        full_count = sum(1 for item in layer_types if item == "full_attention")
        linear_count = sum(1 for item in layer_types if item == "linear_attention")
        if linear_count:
            notes.append(
                f"检测到混合 attention 结构: full_attention={full_count}, "
                f"linear_attention={linear_count}，KV cache 只能给参考值。"
            )
            uncertain = True
    return notes, uncertain


def normalize_precision(value: Optional[str]) -> str:
    text = str(value or "bf16").strip().lower()
    if text in {"bfloat16", "torch.bfloat16"}:
        return "bf16"
    if text in {"float16", "torch.float16", "half"}:
        return "fp16"
    if text in {"float32", "torch.float32"}:
        return "fp32"
    return text


def detect_quantization(model_cfg: dict, env: dict) -> str:
    explicit = str(env.get("QUANTIZATION", "") or "").strip().lower()
    if explicit and explicit not in {"none", "null"}:
        return explicit
    quant_cfg = model_cfg.get("quantization_config")
    if isinstance(quant_cfg, dict):
        method = quant_cfg.get("quant_method") or quant_cfg.get("quantization_method")
        if method:
            return str(method).lower()
        if quant_cfg.get("bits"):
            return f"int{quant_cfg['bits']}"
    if model_cfg.get("quantization_method"):
        return str(model_cfg["quantization_method"]).lower()
    return ""


def bytes_per_param_for_model(precision: str, quantization: str = "") -> float:
    quant = str(quantization or "").lower()
    if "4" in quant or "awq" in quant or "gptq" in quant:
        return 0.5
    if "8" in quant or "fp8" in quant:
        return 1
    bytes_map = {
        "fp32": 4,
        "fp16": 2,
        "bf16": 2,
        "fp8": 1,
        "int8": 1,
        "int4": 0.5,
    }
    return bytes_map.get(normalize_precision(precision), 2)


def bytes_per_kv_cache(precision: str) -> float:
    dtype = normalize_precision(precision)
    bytes_map = {
        "fp32": 4,
        "fp16": 2,
        "bf16": 2,
        "fp8": 1,
        "int8": 1,
    }
    return bytes_map.get(dtype, 2)


def estimate_params_from_config(model_cfg: dict) -> Optional[float]:
    if not model_cfg:
        return None

    hidden = parse_float(model_cfg.get("hidden_size"))
    layers = parse_float(model_cfg.get("num_hidden_layers"))
    vocab = parse_float(model_cfg.get("vocab_size"), 0)
    intermediate = parse_float(model_cfg.get("intermediate_size"))
    if intermediate is None and hidden:
        intermediate = hidden * 4

    if not hidden or not layers or not intermediate:
        return None

    attention_heads = parse_float(model_cfg.get("num_attention_heads"))
    kv_heads = parse_float(model_cfg.get("num_key_value_heads"), attention_heads)
    head_dim = parse_float(model_cfg.get("head_dim"))
    if head_dim is None and hidden and attention_heads:
        head_dim = hidden / attention_heads

    if attention_heads and kv_heads and head_dim:
        q_params = hidden * attention_heads * head_dim
        kv_params = 2 * hidden * kv_heads * head_dim
        o_params = attention_heads * head_dim * hidden
        attention_params = q_params + kv_params + o_params
    else:
        attention_params = 4 * hidden * hidden

    num_experts = parse_float(model_cfg.get("num_experts") or model_cfg.get("n_routed_experts"))
    moe_intermediate = parse_float(
        model_cfg.get("moe_intermediate_size")
        or model_cfg.get("moe_ffn_hidden_size")
        or model_cfg.get("intermediate_size")
    )
    if num_experts and moe_intermediate:
        mlp_params = num_experts * 3 * hidden * moe_intermediate
    else:
        mlp_params = 3 * hidden * intermediate

    per_layer = attention_params + mlp_params
    embedding_params = vocab * hidden
    total = layers * per_layer + embedding_params
    if model_cfg.get("tie_word_embeddings") is False:
        total += embedding_params
    return total / 1e9


def get_model_max_len(model_cfg: dict, runtime: dict) -> tuple[int, str]:
    for key in ["MAX_MODEL_LEN", "MODEL_MAX_LEN", "MAX_SEQ_LEN"]:
        value = parse_float(runtime.get(key))
        if value:
            return int(value), f"service.yaml RUNTIME.{key}"

    for key in [
        "max_position_embeddings",
        "model_max_length",
        "max_sequence_length",
        "seq_length",
    ]:
        value = parse_float(model_cfg.get(key))
        if value:
            return int(value), f"model config.json {key}"

    return 4096, "default fallback"


def estimate_kv_cache_mib(model_cfg: dict, profile: dict) -> tuple[int, str]:
    hidden = parse_float(model_cfg.get("hidden_size"))
    layers = parse_float(model_cfg.get("num_hidden_layers"))
    attention_heads = parse_float(model_cfg.get("num_attention_heads"))
    kv_heads = parse_float(model_cfg.get("num_key_value_heads"), attention_heads)
    head_dim = parse_float(model_cfg.get("head_dim"))
    if head_dim is None and hidden and attention_heads:
        head_dim = hidden / attention_heads

    if not layers or not kv_heads or not head_dim:
        return 0, "KV cache 估算缺少 num_hidden_layers/num_key_value_heads/head_dim，未计入。"

    max_model_len = int(profile["max_model_len"])
    effective_layers = layers
    layer_types = model_cfg.get("layer_types")
    if isinstance(layer_types, list) and layer_types:
        full_attention_layers = sum(1 for item in layer_types if item == "full_attention")
        linear_attention_layers = sum(
            1 for item in layer_types if item == "linear_attention"
        )
        if linear_attention_layers and full_attention_layers:
            effective_layers = full_attention_layers
        elif linear_attention_layers and not full_attention_layers:
            effective_layers = 0

    kv_bytes = (
        2
        * effective_layers
        * max_model_len
        * kv_heads
        * head_dim
        * float(profile["kv_cache_bytes"])
    )
    kv_mib = int(kv_bytes / 1024 / 1024)
    note = (
        "KV cache 按每张卡估算，包含 K/V、层数、KV heads、head_dim "
        f"和 max_model_len={max_model_len}。"
    )
    if effective_layers != layers:
        note += (
            f" 检测到非标准 attention 层，KV cache 仅按 full_attention 层数 "
            f"{int(effective_layers)}/{int(layers)} 给参考值。"
        )
    return kv_mib, note


def get_model_memory_profile(cfg: dict) -> dict:
    env = cfg.get("ENV", {})
    runtime = cfg.get("RUNTIME", {})
    model_dir = os.path.join(env.get("MODEL_PATH", ""), env.get("MODEL_NAME", ""))
    root_model_cfg = load_model_config(model_dir)
    model_cfg, config_notes = get_text_model_config(root_model_cfg)
    arch_notes, architecture_uncertain = model_architecture_notes(
        root_model_cfg, model_cfg
    )

    explicit_param = parse_float(env.get("MODEL_PARAM_B"))
    estimated_param = estimate_params_from_config(model_cfg)
    if explicit_param:
        param_billion = explicit_param
        param_source = "service.yaml ENV.MODEL_PARAM_B"
    elif estimated_param:
        param_billion = estimated_param
        param_source = "model config.json estimate"
    else:
        param_billion = None
        param_source = "unavailable"

    precision = normalize_precision(
        env.get("PRECISION") or model_cfg.get("torch_dtype") or model_cfg.get("dtype")
    )
    quantization = detect_quantization(model_cfg, env)
    buffer_ratio = parse_float(env.get("GPU_MEMORY_BUFFER_RATIO"), 0.2)
    bytes_per_param = bytes_per_param_for_model(precision, quantization)
    kv_cache_dtype = normalize_precision(
        env.get("KV_CACHE_DTYPE") or env.get("VLLM_KV_CACHE_DTYPE") or precision
    )
    max_model_len, max_model_len_source = get_model_max_len(model_cfg, runtime)

    profile = {
        "model_dir": model_dir,
        "root_model_cfg": root_model_cfg,
        "model_cfg": model_cfg,
        "architecture_notes": config_notes + arch_notes,
        "architecture_uncertain": architecture_uncertain,
        "param_billion": param_billion,
        "param_source": param_source,
        "precision": precision,
        "quantization": quantization,
        "bytes_per_param": bytes_per_param,
        "buffer_ratio": buffer_ratio,
        "kv_cache_dtype": kv_cache_dtype,
        "kv_cache_bytes": bytes_per_kv_cache(kv_cache_dtype),
        "max_model_len": max_model_len,
        "max_model_len_source": max_model_len_source,
    }
    kv_cache_mib, kv_cache_note = estimate_kv_cache_mib(model_cfg, profile)
    profile["kv_cache_mib"] = kv_cache_mib
    profile["kv_cache_note"] = kv_cache_note
    return profile


def unknown_model_size_analysis(profile: dict) -> str:
    return (
        "无法识别模型参数规模，已停止 GPU 推荐。\n"
        f"模型路径: {profile.get('model_dir', '')}\n"
        "未从模型 config.json 中读取到完整的 hidden_size、"
        "num_hidden_layers 和 intermediate_size 等结构字段。\n"
        "请先向用户确认模型规模，然后设置 "
        "ENV.MODEL_PARAM_B（单位为 B，例如 32B 模型填写 32 或 32.76），"
        "再重新调用 gpu_recommend_allocation。"
    )


def memory_margin_mib(profile: dict) -> int:
    if profile.get("architecture_uncertain"):
        return 20480
    return 10240


def estimate_required_memory_mib(profile: dict, tp_size: int) -> tuple[int, int]:
    total_weight_bytes = (
        float(profile["param_billion"]) * 1e9 * float(profile["bytes_per_param"])
    )
    total_weight_mib = int(total_weight_bytes / 1024 / 1024)
    per_gpu_mib = total_weight_mib / max(int(tp_size), 1)
    weight_with_buffer_mib = int(
        per_gpu_mib * (1 + float(profile.get("buffer_ratio", 0.2)))
    )
    required_mib = weight_with_buffer_mib + int(profile.get("kv_cache_mib", 0))
    return required_mib, total_weight_mib


def get_gpu_memory_map() -> tuple[Optional[Dict[str, tuple]], Optional[str]]:
    cmd = (
        "nvidia-smi --query-gpu=index,memory.used,memory.total "
        "--format=csv,noheader,nounits"
    )
    output = run_command(cmd)
    if "[ERROR]" in output:
        return None, "无法获取 GPU 信息，请确认 nvidia-smi 可用"

    gpu_memory: Dict[str, tuple] = {}
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) != 3:
            continue
        idx, used, total = parts
        gpu_memory[idx] = (int(used), int(total))
    return gpu_memory, None


def get_gpu_utilization_map(
    samples: int = 3, interval_seconds: float = 0.5
) -> tuple[Optional[Dict[str, float]], Optional[str]]:
    measurements: Dict[str, list[float]] = {}
    for sample_index in range(samples):
        output = run_command(
            "nvidia-smi --query-gpu=index,utilization.gpu "
            "--format=csv,noheader,nounits"
        )
        if "[ERROR]" in output:
            return None, "无法获取 GPU 利用率，请确认 nvidia-smi 可用"

        for line in output.strip().splitlines():
            parts = [item.strip() for item in line.split(",")]
            if len(parts) != 2:
                continue
            gpu_id, utilization = parts
            try:
                measurements.setdefault(gpu_id, []).append(float(utilization))
            except ValueError:
                continue

        if sample_index < samples - 1:
            time.sleep(interval_seconds)

    if not measurements:
        return None, "未获取到有效的 GPU 利用率数据"
    return {
        gpu_id: sum(values) / len(values)
        for gpu_id, values in measurements.items()
        if values
    }, None


def generate_tp_candidates(max_gpus: int) -> list[int]:
    candidates = []
    for tp in [1, 2, 4, 8]:
        if tp <= max_gpus and tp not in candidates:
            candidates.append(tp)
    return candidates or [1]


def parse_visible_gpus(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        return [str(item).strip() for item in ast.literal_eval(text)]
    return [item.strip() for item in text.split(",") if item.strip()]


def describe_model_profile(profile: dict) -> list[str]:
    lines = [
        "模型摘要:",
        f"- path={profile['model_dir']}",
        (
            f"- size≈{profile['param_billion']:.2f}B({profile['param_source']}), "
            f"dtype={profile['precision']}, quant={profile['quantization'] or 'none'}"
        ),
        (
            f"- max_model_len={profile['max_model_len']}({profile['max_model_len_source']}), "
            f"kv_cache≈{profile['kv_cache_mib']} MiB/卡"
        ),
    ]
    for note in profile.get("architecture_notes", []):
        lines.append(f"注意: {note}")
    lines.append(f"建议额外冗余: {memory_margin_mib(profile)} MiB/卡")
    return lines


def gpu_eval_status_text(item: dict) -> str:
    if item.get("busy"):
        return f"计算繁忙({item.get('utilization', 0):.1f}%)"
    if item.get("recommended_ok"):
        return "满足保守预算"
    if item.get("ok"):
        return "满足最低需求"
    return "低于最低需求"


def format_gpu_budget_table(
    gpu_memory: Dict[str, tuple],
    mem_util: float,
    gpu_utilization: Optional[Dict[str, float]] = None,
    utilization_threshold: int = 50,
) -> list[str]:
    lines = ["GPU预算:"]
    gpu_utilization = gpu_utilization or {}
    for idx, (used, total) in gpu_memory.items():
        planned_limit = gpu_vllm_planned_limit_mib(total, mem_util)
        budget = gpu_vllm_budget_mib(gpu_memory, idx, mem_util)
        utilization = gpu_utilization.get(idx, 0.0)
        status = "busy" if utilization >= utilization_threshold else "available"
        lines.append(
            f"- GPU {idx}: total={total} MiB, used={used} MiB, "
            f"vllm_limit={planned_limit} MiB, budget={budget} MiB, "
            f"avg_util={utilization:.1f}%, status={status}"
        )
    return lines


def reserve_instance_gpu_memory(gpu_memory: Dict[str, tuple]) -> tuple[Dict[str, tuple], list[str]]:
    adjusted = dict(gpu_memory)
    reserved = []
    for instance_id in list_service_instance_ids():
        meta = visible_service_instance_meta(instance_id)
        if meta.get("status") not in {"starting", "running"}:
            continue
        for gid in parse_visible_gpus(meta.get("actual_gpus", "")):
            if gid not in adjusted:
                continue
            used, total = adjusted[gid]
            adjusted[gid] = (max(used, total), total)
            reserved.append(gid)
    return adjusted, sorted(set(reserved), key=lambda x: int(x) if x.isdigit() else x)


def gpu_vllm_budget_mib(
    gpu_memory: Dict[str, tuple], gpu_id: str, mem_util: float
) -> int:
    used, total = gpu_memory[gpu_id]
    planned_limit = int(total * mem_util)
    return planned_limit - used


def gpu_vllm_planned_limit_mib(total_mib: int, mem_util: float) -> int:
    return int(total_mib * mem_util)


def evaluate_gpu_selection(
    gpu_ids: list[str],
    tp_size: int,
    gpu_memory: Dict[str, tuple],
    profile: dict,
    mem_util: float,
    gpu_utilization: Optional[Dict[str, float]] = None,
    utilization_threshold: int = 50,
) -> dict:
    required_mib, total_mib = estimate_required_memory_mib(profile, tp_size)
    margin_mib = memory_margin_mib(profile)
    missing = [gid for gid in gpu_ids if gid not in gpu_memory]
    if missing:
        return {
            "ok": False,
            "reason": "gpu_not_exist",
            "required_mib": required_mib,
            "recommended_mib": required_mib + margin_mib,
            "margin_mib": margin_mib,
            "total_mib": total_mib,
            "analysis": f"GPU 不存在: {','.join(missing)}",
        }

    details = []
    gpu_utilization = gpu_utilization or {}
    ok = True
    has_busy_gpu = False
    for gid in gpu_ids:
        used, total = gpu_memory[gid]
        planned_limit = gpu_vllm_planned_limit_mib(total, mem_util)
        budget = gpu_vllm_budget_mib(gpu_memory, gid, mem_util)
        utilization = gpu_utilization.get(gid, 0.0)
        busy = utilization >= utilization_threshold
        if busy:
            has_busy_gpu = True
        if budget < required_mib or busy:
            ok = False
        details.append(
            {
                "gpu": gid,
                "used_mib": used,
                "total_mib": total,
                "vllm_planned_limit_mib": planned_limit,
                "vllm_budget_mib": budget,
                "recommended_mib": required_mib + margin_mib,
                "utilization": utilization,
                "busy": busy,
                "ok": budget >= required_mib and not busy,
                "recommended_ok": budget >= required_mib + margin_mib and not busy,
            }
        )

    return {
        "ok": ok,
        "reason": "" if ok else ("gpu_busy" if has_busy_gpu else "insufficient_memory"),
        "required_mib": required_mib,
        "recommended_mib": required_mib + margin_mib,
        "margin_mib": margin_mib,
        "total_mib": total_mib,
        "details": details,
    }


def recommend_gpu_for_config(
    cfg: Optional[dict] = None,
    reserve_instances: bool = True,
    allowed_gpus: Optional[list[str]] = None,
) -> dict:
    """
    Intelligently evaluate and recommend GPU resources.

    Returns:
        {
            "ok": bool,
            "recommended_gpus": str,
            "recommended_tp": int,
            "analysis": str
        }
    """

    cfg = cfg or show_config()

    mem_util = float(cfg["RUNTIME"].get("GPU_MEMORY_UTILIZATION", 0.9))
    utilization_threshold = clamp_int(
        cfg["RUNTIME"].get("GPU_UTILIZATION_THRESHOLD"), 50, 1, 100
    )
    configured_visible = cfg["ENV"].get("CUDA_VISIBLE_DEVICES", "")
    configured_gpus = parse_visible_gpus(configured_visible)
    configured_tp = int(cfg["RUNTIME"].get("TENSOR_PARALLEL_SIZE", len(configured_gpus) or 1))
    profile = get_model_memory_profile(cfg)
    if profile.get("param_billion") is None:
        return {
            "ok": False,
            "current_ok": False,
            "reason": "model_size_unknown",
            "analysis": unknown_model_size_analysis(profile),
        }

    gpu_memory, error = get_gpu_memory_map()
    if error:
        return {"ok": False, "analysis": error}
    gpu_utilization, utilization_error = get_gpu_utilization_map()
    if utilization_error:
        return {"ok": False, "analysis": utilization_error}

    if allowed_gpus is None and resource_pool_managed():
        allowed_gpus = resource_context_gpu_ids()
    if allowed_gpus is not None:
        allowed = set(str(item) for item in allowed_gpus)
        gpu_memory = {
            gpu_id: value for gpu_id, value in gpu_memory.items() if gpu_id in allowed
        }
        gpu_utilization = {
            gpu_id: value
            for gpu_id, value in gpu_utilization.items()
            if gpu_id in allowed
        }
        if not allowed:
            return {
                "ok": False,
                "current_ok": False,
                "reason": "resource_context_missing_gpus",
                "analysis": "资源池未提供可用 GPU 边界，无法进行自动分配。",
            }
    if reserve_instances:
        gpu_memory, reserved_gpus = reserve_instance_gpu_memory(gpu_memory)
    else:
        reserved_gpus = []

    analysis_lines = describe_model_profile(profile)
    if allowed_gpus is not None:
        analysis_lines.append(
            f"资源池 GPU 边界: assigned_gpus={','.join(allowed_gpus)}"
        )
    if reserved_gpus:
        analysis_lines.append(
            f"实例预占用: GPU {','.join(reserved_gpus)} 已被 starting/running 实例占用。"
        )
    if not gpu_memory:
        return {
            "ok": False,
            "current_ok": False,
            "analysis": "\n".join(analysis_lines) + "\n没有可用于推荐的 GPU。",
        }

    analysis_lines.append("")
    analysis_lines.append(
        f"当前配置: CUDA_VISIBLE_DEVICES={','.join(configured_gpus) or '(empty)'}, "
        f"TP={configured_tp}"
    )

    current_ok = False
    current_eval = None
    if not configured_gpus:
        analysis_lines.append("- 当前配置不可用: CUDA_VISIBLE_DEVICES 为空")
    elif configured_tp != len(configured_gpus):
        analysis_lines.append(
            f"- 当前配置不可用: TP={configured_tp} 与 GPU 数量={len(configured_gpus)} 不一致"
        )
    else:
        current_eval = evaluate_gpu_selection(
            configured_gpus,
            configured_tp,
            gpu_memory,
            profile,
            mem_util,
            gpu_utilization,
            utilization_threshold,
        )
        current_ok = bool(current_eval["ok"])
        analysis_lines.append(
            f"- 状态: {'可用' if current_ok else '不可用'} | "
            f"单卡最低需求≈{current_eval['required_mib']} MiB | "
            f"保守预算≈{current_eval['recommended_mib']} MiB"
        )
        gpu_status = ", ".join(
            f"GPU{item['gpu']}:{gpu_eval_status_text(item)}"
            for item in current_eval.get("details", [])
        )
        if gpu_status:
            analysis_lines.append(f"- 当前GPU: {gpu_status}")

    analysis_lines.append("")
    analysis_lines.append(
        f"GPU繁忙阈值: 连续3次采样平均利用率达到 {utilization_threshold}% 时不参与分配。"
    )
    analysis_lines.extend(
        format_gpu_budget_table(
            gpu_memory, mem_util, gpu_utilization, utilization_threshold
        )
    )

    candidates = []
    for idx, (used, total) in gpu_memory.items():
        planned_limit = gpu_vllm_planned_limit_mib(total, mem_util)
        budget = gpu_vllm_budget_mib(gpu_memory, idx, mem_util)
        if budget > 0 and gpu_utilization.get(idx, 0.0) < utilization_threshold:
            candidates.append((idx, budget, planned_limit, total))

    candidates.sort(key=lambda x: x[1], reverse=True)
    if not candidates:
        return {
            "ok": False,
            "current_ok": current_ok,
            "analysis": "\n".join(analysis_lines) + "\n没有可用 GPU。",
        }

    current_recommended_ok = False
    if current_ok and current_eval:
        min_budget = min(
            item["vllm_budget_mib"] for item in current_eval.get("details", [])
        )
        current_recommended_ok = min_budget >= current_eval["recommended_mib"]

    for tp in generate_tp_candidates(len(candidates)):
        required, total_weight = estimate_required_memory_mib(profile, tp)
        recommended_need = required + memory_margin_mib(profile)
        top_tp = candidates[:tp]
        min_budget = min(item[1] for item in top_tp)
        min_planned_limit = min(item[2] for item in top_tp)

        if min_budget >= required:
            recommended_ids = [item[0] for item in top_tp]
            recommendation_status = (
                "满足保守预算" if min_budget >= recommended_need else "满足最低启动需求，但低于保守推荐预算"
            )
            analysis_lines.append("")
            analysis_lines.append("推荐:")
            analysis_lines.append(f"- GPU={','.join(recommended_ids)}, TP={tp}")
            analysis_lines.append(f"- 状态: {recommendation_status}")
            analysis_lines.append(
                f"- 权重总需求≈{total_weight} MiB, "
                f"单卡最低需求≈{required} MiB, "
                f"保守预算≈{recommended_need} MiB, "
                f"组合最小budget≈{min_budget} MiB"
            )
            analysis_lines.append(
                f"- 预计占用: nvidia-smi 通常接近 vLLM规划上限≈{min_planned_limit} MiB/卡，"
                "并可能因 CUDA/NCCL/runtime 开销略高。"
            )
            analysis_lines.append("结论: 以上为启动前粗略分析，不代表一定可启动；最终以 vLLM 启动日志和 service_start_status 为准。")

            return {
                "ok": True,
                "current_ok": current_ok,
                "recommended_gpus": ",".join(recommended_ids),
                "recommended_tp": tp,
                "analysis": "\n".join(analysis_lines),
            }

    if current_ok and current_eval:
        min_budget = min(
            item["vllm_budget_mib"] for item in current_eval.get("details", [])
        )
        min_planned_limit = min(
            item["vllm_planned_limit_mib"] for item in current_eval.get("details", [])
        )
        recommendation_status = (
            "满足保守预算"
            if current_recommended_ok
            else "满足最低启动需求，但低于保守推荐预算"
        )
        analysis_lines.append("")
        analysis_lines.append("推荐:")
        analysis_lines.append(f"- GPU={','.join(configured_gpus)}, TP={configured_tp}")
        analysis_lines.append("- 理由: 当前配置满足最低启动需求，且没有更少 GPU 的可行组合。")
        analysis_lines.append(f"- 状态: {recommendation_status}")
        analysis_lines.append(
            f"- 权重总需求≈{current_eval['total_mib']} MiB, "
            f"单卡最低需求≈{current_eval['required_mib']} MiB, "
            f"保守预算≈{current_eval['recommended_mib']} MiB, "
            f"组合最小budget≈{min_budget} MiB"
        )
        analysis_lines.append(
            f"- 预计占用: nvidia-smi 通常接近 vLLM规划上限≈{min_planned_limit} MiB/卡，"
            "并可能因 CUDA/NCCL/runtime 开销略高。"
        )
        analysis_lines.append("结论: 以上为启动前粗略分析，不代表一定可启动；最终以 vLLM 启动日志和 service_start_status 为准。")

        return {
            "ok": True,
            "current_ok": current_ok,
            "recommended_gpus": ",".join(configured_gpus),
            "recommended_tp": configured_tp,
            "analysis": "\n".join(analysis_lines),
        }

    analysis_lines.append("")
    analysis_lines.append("所有 GPU 组合均无法满足显存需求。")
    for tp in generate_tp_candidates(len(candidates)):
        required, _ = estimate_required_memory_mib(profile, tp)
        recommended_need = required + memory_margin_mib(profile)
        top_tp = candidates[:tp]
        min_budget = min(item[1] for item in top_tp) if top_tp else 0
        analysis_lines.append(
            f"- TP={tp}: 单卡最低需求≈{required} MiB, "
            f"保守预算≈{recommended_need} MiB, 当前组合最小budget≈{min_budget} MiB"
        )
    analysis_lines.append("结论: 以上为启动前粗略分析，不代表一定可启动；最终以 vLLM 启动日志和 service_start_status 为准。")

    return {
        "ok": False,
        "current_ok": current_ok,
        "analysis": "\n".join(analysis_lines),
    }


def recommend_gpu() -> dict:
    """Recommend GPU allocation for the current user's draft config."""
    resource_error = managed_resource_error(require_gpus=True)
    if resource_error:
        return {
            "ok": False,
            "current_ok": False,
            "reason": "resource_context_missing",
            "analysis": resource_error,
        }
    return recommend_gpu_for_config(show_config())


def check_service_start_static_config(cfg: dict) -> dict:
    env = cfg.get("ENV", {})
    model_path = env.get("MODEL_PATH", "")
    model_name = env.get("MODEL_NAME", "")
    start_script = env.get("START_SCRIPT", "")
    target_ip = env.get("HOST_IP", "")

    full_path = os.path.join(model_path, model_name)
    if not os.path.exists(full_path):
        return {
            "ok": False,
            "reason": "file_not_found",
            "analysis": f"ENV.MODEL_NAME 不存在: {model_name}。\nUse model_list() to see all available models.",
        }

    if not os.path.exists(start_script):
        return {
            "ok": False,
            "reason": "file_not_found",
            "analysis": f"ENV.START_SCRIPT 不存在: {start_script}",
        }

    host_ip = get_local_ip()
    if target_ip != host_ip:
        return {
            "ok": False,
            "reason": "ip_error",
            "analysis": f"ENV.HOST_IP 错误: {target_ip} 应改为 {host_ip}",
        }

    return {"ok": True, "analysis": "启动静态配置检查通过。"}


def apply_runtime_host_ip(runtime_cfg: dict) -> tuple[str, str]:
    """Inject this worker's IP into an instance config without changing its draft."""
    env = runtime_cfg.setdefault("ENV", {})
    configured_ip = str(env.get("HOST_IP") or "").strip()
    worker_ip = get_local_ip()
    env["HOST_IP"] = worker_ip
    return configured_ip, worker_ip


def apply_auto_gpu_allocation(runtime_cfg: dict) -> tuple[bool, str, dict]:
    recommendation = recommend_gpu_for_config(
        runtime_cfg,
        reserve_instances=True,
        allowed_gpus=(resource_context_gpu_ids() if resource_pool_managed() else None),
    )
    if not recommendation.get("ok"):
        return (
            False,
            "自动 GPU 分配失败。\n" + str(recommendation.get("analysis") or ""),
            {},
        )

    gpus = str(recommendation.get("recommended_gpus") or "").strip()
    tp = int(recommendation.get("recommended_tp") or 0)
    if not gpus or tp <= 0:
        return (
            False,
            "自动 GPU 分配失败：未生成有效的 GPU 或 TP 推荐。\n"
            + str(recommendation.get("analysis") or ""),
            {},
        )

    runtime_cfg.setdefault("ENV", {})["CUDA_VISIBLE_DEVICES"] = gpus
    runtime_cfg.setdefault("RUNTIME", {})["TENSOR_PARALLEL_SIZE"] = tp
    allocation = {
        "mode": "auto",
        "recommended_gpus": gpus,
        "recommended_tp": tp,
        "current_ok": bool(recommendation.get("current_ok")),
        "analysis": str(recommendation.get("analysis") or ""),
    }
    return True, "", allocation


def apply_requested_gpu_allocation(
    runtime_cfg: dict,
    gpu_ids: str = "",
    tensor_parallel_size: int = 0,
    fallback_to_auto: bool = False,
) -> tuple[bool, str, dict]:
    requested_text = str(gpu_ids or "").strip()
    try:
        requested_tp = int(tensor_parallel_size or 0)
    except (TypeError, ValueError):
        return False, "TENSOR_PARALLEL_SIZE 必须是非负整数。", {}

    if not requested_text:
        if requested_tp:
            return False, "指定 tensor_parallel_size 时必须同时指定 gpu_ids。", {}
        return apply_auto_gpu_allocation(runtime_cfg)

    try:
        requested_gpus = parse_visible_gpus(requested_text)
    except (SyntaxError, ValueError) as exc:
        return False, f"gpu_ids 格式错误: {exc}", {}
    if not requested_gpus:
        return False, "gpu_ids 不能为空。", {}
    if any(not gpu_id.isdigit() for gpu_id in requested_gpus):
        return False, "gpu_ids 必须是逗号分隔的非负整数，例如 4,5。", {}
    if len(set(requested_gpus)) != len(requested_gpus):
        return False, "gpu_ids 不能包含重复 GPU。", {}

    requested_tp = requested_tp or len(requested_gpus)
    if requested_tp != len(requested_gpus):
        return (
            False,
            f"TP={requested_tp} 与指定 GPU 数量={len(requested_gpus)} 不一致。",
            {},
        )

    allowed_gpus = None
    if resource_pool_managed():
        allowed_gpus = resource_context_gpu_ids()
        outside = [gpu_id for gpu_id in requested_gpus if gpu_id not in allowed_gpus]
        if outside:
            return (
                False,
                "指定 GPU 超出资源池边界。\n"
                f"assigned_gpus={','.join(allowed_gpus)}\n"
                f"outside_gpus={','.join(outside)}",
                {},
            )

    requested_cfg = copy.deepcopy(runtime_cfg)
    requested_cfg.setdefault("ENV", {})["CUDA_VISIBLE_DEVICES"] = ",".join(
        requested_gpus
    )
    requested_cfg.setdefault("RUNTIME", {})[
        "TENSOR_PARALLEL_SIZE"
    ] = requested_tp
    recommendation = recommend_gpu_for_config(
        requested_cfg,
        reserve_instances=True,
        allowed_gpus=allowed_gpus,
    )
    if not recommendation.get("current_ok"):
        if fallback_to_auto:
            return apply_auto_gpu_allocation(runtime_cfg)
        return (
            False,
            "指定 GPU 当前不可用于启动，未自动更换 GPU。\n"
            + str(recommendation.get("analysis") or ""),
            {},
        )

    runtime_cfg.setdefault("ENV", {})["CUDA_VISIBLE_DEVICES"] = ",".join(
        requested_gpus
    )
    runtime_cfg.setdefault("RUNTIME", {})["TENSOR_PARALLEL_SIZE"] = requested_tp
    allocation = {
        "mode": "manual",
        "requested_gpus": ",".join(requested_gpus),
        "requested_tp": requested_tp,
        "recommended_gpus": ",".join(requested_gpus),
        "recommended_tp": requested_tp,
        "current_ok": True,
        "fallback_to_auto": bool(fallback_to_auto),
        "analysis": str(recommendation.get("analysis") or ""),
    }
    return True, "", allocation


def check_config_validity() -> dict:
    """
    Pre-startup configuration validity check.

    If the current configuration meets the running conditions, ok=True.
    If not, ok=False and return the reason for failure.
    """

    cfg = copy.deepcopy(show_config())
    configured_ip, runtime_ip = apply_runtime_host_ip(cfg)

    visible = cfg["ENV"]["CUDA_VISIBLE_DEVICES"]
    model_path = cfg["ENV"]["MODEL_PATH"]
    model_name = cfg["ENV"]["MODEL_NAME"]
    start_script = cfg["ENV"]["START_SCRIPT"]
    tp_size = int(cfg["RUNTIME"]["TENSOR_PARALLEL_SIZE"])
    mem_util = float(cfg["RUNTIME"].get("GPU_MEMORY_UTILIZATION", 0.9))
    utilization_threshold = clamp_int(
        cfg["RUNTIME"].get("GPU_UTILIZATION_THRESHOLD"), 50, 1, 100
    )
    profile = get_model_memory_profile(cfg)

    # ------------------------------------------------
    # 1. PATH check
    # ------------------------------------------------
    full_path = os.path.join(model_path, model_name)
    if not os.path.exists(full_path):
        return {
            "ok": False,
            "reason": "file_not_found",
            "analysis": f"""ENV.MODEL_NAME 不存在: {model_name}。\nUse model_list() to see all available models.""",
        }

    if not os.path.exists(start_script):
        return {
            "ok": False,
            "reason": "file_not_found",
            "analysis": f"ENV.START_SCRIPT 不存在: {start_script}",
        }

    if profile.get("param_billion") is None:
        return {
            "ok": False,
            "reason": "model_size_unknown",
            "analysis": unknown_model_size_analysis(profile),
        }

    # ------------------------------------------------
    # 2. GPU List
    # ------------------------------------------------
    if not visible:
        return {
            "ok": False,
            "reason": "no_gpu_configured",
            "analysis": "CUDA_VISIBLE_DEVICES 为空。\nUse gpu_status() to view the current GPU status and memory usage.",
        }

    try:
        target_gpus = parse_visible_gpus(visible)
    except Exception:
        return {
            "ok": False,
            "reason": "gpu_value_error",
            "analysis": "CUDA_VISIBLE_DEVICES 格式错误，应使用逗号分隔，例如 '0,1,2,3'",
        }

    # ------------------------------------------------
    # 4. Driver check
    # ------------------------------------------------
    gpu_memory, gpu_error = get_gpu_memory_map()
    if gpu_error:
        return {
            "ok": False,
            "reason": "nvidia_smi_failed",
            "analysis": gpu_error,
        }
    gpu_utilization, utilization_error = get_gpu_utilization_map()
    if utilization_error:
        return {
            "ok": False,
            "reason": "nvidia_smi_failed",
            "analysis": utilization_error,
        }

    # ------------------------------------------------
    # 5. GPU status
    # ------------------------------------------------
    for gid in target_gpus:
        if gid not in gpu_memory:
            return {
                "ok": False,
                "reason": "gpu_not_exist",
                "analysis": f"CUDA_VISIBLE_DEVICES={','.join(target_gpus)}，但 GPU {gid} 不存在。"
                + "\nUse gpu_status() to view the current GPU status and memory usage.",
            }

    # ------------------------------------------------
    # 6. GPU VS TP
    # ------------------------------------------------
    if tp_size != len(target_gpus):
        return {
            "ok": False,
            "reason": "tp_gpu_mismatch",
            "analysis": (
                f"TENSOR_PARALLEL_SIZE={tp_size} "
                f"但 CUDA_VISIBLE_DEVICES={','.join(target_gpus)}"
            ),
        }

    # ------------------------------------------------
    # 7. GPU Memory Estimate
    # ------------------------------------------------
    current_eval = evaluate_gpu_selection(
        target_gpus,
        tp_size,
        gpu_memory,
        profile,
        mem_util,
        gpu_utilization,
        utilization_threshold,
    )
    required_mib = current_eval["required_mib"]
    total_mib = current_eval["total_mib"]

    analysis_lines = []
    if configured_ip != runtime_ip:
        analysis_lines.append(
            f"HOST_IP: 启动实例时自动使用当前 worker IP {runtime_ip} "
            f"(draft 配置值 {configured_ip or 'empty'} 不会被修改)"
        )
    analysis_lines.append(f"模型路径: {profile['model_dir']}")
    analysis_lines.append(
        f"模型 {profile['param_billion']:.2f}B ({profile['param_source']})"
        f" | 精度 {profile['precision']} | 量化 {profile['quantization'] or 'none'}"
    )
    analysis_lines.append(
        f"max_model_len={profile['max_model_len']} ({profile['max_model_len_source']})"
        f" | 单卡 KV cache ≈ {profile['kv_cache_mib']} MiB"
    )
    analysis_lines.append(
        f"采用 {tp_size} 张卡 | 权重总量 ≈ {total_mib} MiB "
        f"| 单卡需求(权重分片+缓冲+KV cache) ≈ {required_mib} MiB"
    )
    analysis_lines.append(
        f"说明: {profile['kv_cache_note']} 实际显存以 vLLM 启动结果为准。"
    )

    for item in current_eval.get("details", []):
        analysis_lines.append(
            f"GPU {item['gpu']}: 总 {item['total_mib']} MiB | 已用 {item['used_mib']} MiB "
            f"| vLLM规划上限 {item['vllm_planned_limit_mib']} MiB "
            f"| vLLM剩余预算 {item['vllm_budget_mib']} MiB "
            f"| 平均利用率 {item['utilization']:.1f}% "
            f"| {gpu_eval_status_text(item)}"
        )

    if not current_eval["ok"]:
        recommendation = recommend_gpu()
        recommendation_text = str(recommendation.get("analysis", "")).strip()
        return {
            "ok": False,
            "reason": current_eval["reason"] or "insufficient_memory",
            "analysis": "\n".join(analysis_lines)
            + "\n\n推荐分析:\n"
            + (recommendation_text or "当前未能生成 GPU 推荐。"),
        }

    # ----------------------------
    # All passed
    # ----------------------------
    return {"ok": True, "analysis": "\n".join(analysis_lines)}


def build_instance_runtime_config(cfg: dict, ports: dict) -> dict:
    runtime_cfg = copy.deepcopy(cfg)
    runtime_cfg.setdefault("PORTS", {})
    runtime_cfg.setdefault("ENV", {})
    runtime_cfg["PORTS"]["VLLM_OPENAI_PORT"] = int(ports["vllm"])
    runtime_cfg["PORTS"]["INFERENCE_PORT"] = int(ports["inference"])
    runtime_cfg["PORTS"]["UI_PORT"] = int(ports["ui"])
    runtime_cfg["PORTS"]["DATA_ANNOTATION_PORT"] = int(ports["case2chat"])
    runtime_cfg["ENV"]["MASTER_PORT"] = int(ports["master"])
    return runtime_cfg


def write_runtime_config(path: str, cfg: dict) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, path)


def instance_ports_from_runtime_config(cfg: dict) -> dict:
    ports = cfg.get("PORTS", {})
    env = cfg.get("ENV", {})
    return {
        "vllm": int(ports["VLLM_OPENAI_PORT"]),
        "inference": int(ports["INFERENCE_PORT"]),
        "ui": int(ports["UI_PORT"]),
        "case2chat": int(ports["DATA_ANNOTATION_PORT"]),
        "master": int(env.get("MASTER_PORT") or 50121),
    }


def openai_api_ready_error(cfg: dict, instance_id: str = "") -> str:
    env = cfg.get("ENV", {})
    ports = cfg.get("PORTS", {})
    host = str(env.get("HOST_IP") or "127.0.0.1").strip()
    port = int(ports.get("VLLM_OPENAI_PORT") or 0)
    if not port:
        return "VLLM_OPENAI_PORT 为空，无法运行 benchmark。"

    url = f"http://{host}:{port}/v1/models"
    try:
        request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer EMPTY"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            if 200 <= response.status < 300:
                return ""
            return f"vLLM OpenAI API 未就绪: url={url}, status={response.status}"
    except Exception as e:
        return (
            "vLLM OpenAI API 暂不可用，已跳过 benchmark。\n"
            f"instance_id={instance_id}\n"
            f"base_url=http://{host}:{port}/v1\n"
            f"error={e}\n"
            "说明: 端口监听不代表模型 API 已完成加载。请稍后查看 "
            "service_instance_status/service_log_tail，确认 vLLM ready 后再运行 benchmark。"
        )


def current_time_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def pid_is_alive(pid: object) -> bool:
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    return bool(value and is_process_running(value))


def service_instance_recorded_pids(meta: dict) -> list[int]:
    pid_dir = str(meta.get("pid_dir") or "")
    if not pid_dir or not os.path.isdir(pid_dir):
        return []
    pids = []
    for name in os.listdir(pid_dir):
        if not name.endswith(".pid"):
            continue
        try:
            with open(os.path.join(pid_dir, name), "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if pid > 0:
                pids.append(pid)
        except (OSError, TypeError, ValueError):
            continue
    return pids


def service_instance_recorded_pid(meta: dict, service: str) -> int:
    pid_dir = str(meta.get("pid_dir") or "")
    if not pid_dir:
        return 0
    try:
        with open(os.path.join(pid_dir, f"{service}.pid"), "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        return pid if pid > 0 else 0
    except (OSError, TypeError, ValueError):
        return 0


def mark_meta_stale_fixed(meta: dict, reason: str, **extra) -> None:
    meta["stale_status_fixed"] = {
        "reason": reason,
        "time": current_time_text(),
        **extra,
    }


def finish_meta_if_missing(meta: dict, key: str = "finished_at") -> None:
    if not meta.get(key):
        meta[key] = current_time_text()


def write_meta_if_changed(path: str, meta: dict, changed: bool) -> dict:
    if changed:
        atomic_write_json(path, meta)
    return meta


def refresh_service_instance_status(meta: dict) -> dict:
    if not meta:
        return {}
    status_file = meta.get("status_file")
    script_pid = int(meta.get("script_pid") or 0)
    start_script_pid = service_instance_recorded_pid(meta, "start-service")
    vllm_pid = service_instance_recorded_pid(meta, "vllm")
    port_ownership = service_instance_port_ownership(meta)
    process_ownership = service_instance_process_ownership(meta, port_ownership)
    instance_runtime_pids = set(process_ownership["owned"])
    instance_runtime_pids.update(process_ownership["unverified"])
    launcher_running = script_pid in instance_runtime_pids or start_script_pid in instance_runtime_pids
    vllm_running = vllm_pid in instance_runtime_pids
    auxiliary_running = any(
        service_instance_recorded_pid(meta, service) in instance_runtime_pids
        for service in ("inference", "case2chat", "ui", "web")
    )
    old_status = str(meta.get("status") or "")
    script_status = ""
    if status_file and os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status_meta = json.load(f) or {}
            script_status = str(status_meta.get("status") or "")
            if status_meta.get("finished_at"):
                meta["script_finished_at"] = status_meta.get("finished_at")
            if status_meta.get("error") is not None:
                meta["error"] = status_meta.get("error")
        except Exception:
            pass

    service_port_names = {"vllm", "inference", "ui", "case2chat"}
    owned_ports = {item["name"] for item in port_ownership["owned"]}
    unverified_ports = {item["name"] for item in port_ownership["unverified"]}
    reused_ports = {item["name"] for item in port_ownership["reused"]}
    running_ports = owned_ports | unverified_ports

    new_status = old_status
    was_active = old_status in {"starting", "running", "degraded"}
    all_ports_running = service_port_names.issubset(running_ports)
    residual_runtime = auxiliary_running or bool(running_ports - {"vllm"})
    if script_status == "stopped":
        new_status = "stopped"
    elif vllm_running and all_ports_running:
        new_status = "running"
    elif launcher_running or vllm_running:
        new_status = "starting"
    elif residual_runtime and was_active:
        new_status = "degraded"
    elif old_status not in {"stopped", "failed"}:
        if script_status == "finished":
            new_status = "failed"
        elif script_status == "starting":
            new_status = "failed"
        elif old_status in {"starting", "running"}:
            new_status = "failed"
        else:
            new_status = old_status or "unknown"

    if new_status != old_status:
        meta["status"] = new_status
        mark_meta_stale_fixed(
            meta,
            "service_status_refresh",
            old_status=old_status,
            new_status=new_status,
            script_pid=script_pid,
            vllm_pid=vllm_pid,
            running_ports=sorted(running_ports),
            reused_ports=sorted(reused_ports),
        )
    if meta.get("status") == "failed":
        finish_meta_if_missing(meta)
    meta["updated_at"] = current_time_text()
    return meta


def start_service(
    gpu_ids: str = "",
    tensor_parallel_size: int = 0,
    fallback_to_auto: bool = False,
) -> str:
    """Start inference service stack."""
    if not current_request_user_id():
        return "当前请求缺少用户身份，已拒绝启动推理服务。"
    resource_error = managed_resource_error(
        require_gpus=True, require_reservation=True
    )
    if resource_error:
        return resource_error
    draft_config_path = ensure_user_draft_config()
    CONFIG = show_config()
    runtime_source = copy.deepcopy(CONFIG)
    configured_ip, runtime_ip = apply_runtime_host_ip(runtime_source)
    static_check = check_service_start_static_config(runtime_source)
    if not static_check["ok"]:
        return (
            "检查不通过。\n"
            f"原因：{static_check['reason']}\n"
            f"分析：{static_check['analysis']}"
        )

    if configured_ip != runtime_ip:
        print(
            "[service-start] runtime HOST_IP adjusted "
            f"{configured_ip or 'empty'} -> {runtime_ip}; draft unchanged",
            flush=True,
        )
    run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    instance_id = run_id
    instance_dir = get_service_instance_dir(instance_id)
    log_root = get_service_run_log_root()
    os.makedirs(instance_dir, exist_ok=True)
    allocated_ports = allocate_instance_ports(runtime_source, instance_id)
    runtime_config = build_instance_runtime_config(runtime_source, allocated_ports)
    allocation_ok, allocation_error, gpu_allocation = apply_requested_gpu_allocation(
        runtime_config,
        gpu_ids=gpu_ids,
        tensor_parallel_size=tensor_parallel_size,
        fallback_to_auto=fallback_to_auto,
    )
    if not allocation_ok:
        release_pending_instance_ports(instance_id, allocated_ports)
        return allocation_error

    runtime_config_path = os.path.join(instance_dir, "service.runtime.yaml")
    write_runtime_config(runtime_config_path, runtime_config)
    ports = runtime_config["PORTS"]
    runtime_env = runtime_config["ENV"]
    run_log_dir = instance_dir
    pid_dir = os.path.join(run_log_dir, "pids")
    status_file = os.path.join(run_log_dir, "status.json")
    meta_file = os.path.join(instance_dir, "meta.json")
    os.makedirs(run_log_dir, exist_ok=True)
    os.makedirs(pid_dir, exist_ok=True)
    latest_link = os.path.join(log_root, "latest")
    try:
        if os.path.lexists(latest_link):
            os.unlink(latest_link)
        os.symlink(run_log_dir, latest_link)
    except OSError:
        pass
    proc_env = os.environ.copy()
    proc_env["SERVICE_RUN_ID"] = run_id
    proc_env["SERVICE_RUN_LOG_DIR"] = run_log_dir
    proc_env["SERVICE_PID_DIR"] = pid_dir
    try:
        proc = subprocess.Popen(
            ["bash", runtime_env["START_SCRIPT"], "start", runtime_config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=proc_env,
            start_new_session=True,
        )
    except Exception:
        release_pending_instance_ports(instance_id, allocated_ports)
        raise
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    instance_meta = {
        "instance_id": instance_id,
        "run_id": run_id,
        "owner_user_id": current_request_user_id(),
        "actual_gpus": ",".join(
            parse_visible_gpus(runtime_env.get("CUDA_VISIBLE_DEVICES", ""))
        ),
        "gpu_allocation": gpu_allocation,
        "status": "starting",
        "script_pid": proc.pid,
        "model": str(runtime_env.get("MODEL_NAME") or ""),
        "model_path": str(runtime_env.get("MODEL_PATH") or "")
        + str(runtime_env.get("MODEL_NAME") or ""),
        "ports": {
            "vllm": allocated_ports["vllm"],
            "inference": allocated_ports["inference"],
            "ui": allocated_ports["ui"],
            "case2chat": allocated_ports["case2chat"],
            "master": allocated_ports["master"],
        },
        "runtime_config": runtime_config_path,
        "draft_config": draft_config_path,
        "log_dir": run_log_dir,
        "pid_dir": pid_dir,
        "status_file": status_file,
        "meta_file": meta_file,
        "started_at": started_at,
        "finished_at": None,
    }
    resource_context = current_request_resource_context()
    if resource_pool_managed():
        instance_meta["resource"] = {
            "mode": "managed",
            "runtime_node_id": str(resource_context.get("runtime_node_id") or ""),
            "reservation_id": str(resource_context.get("reservation_id") or ""),
            "resource_group_id": str(resource_context.get("resource_group_id") or ""),
            "training_pool_id": str(resource_context.get("training_pool_id") or ""),
            "expires_at": str(resource_context.get("expires_at") or ""),
            "assigned_gpus": resource_context_gpu_ids(resource_context),
            "actual_gpus": parse_visible_gpus(
                runtime_env.get("CUDA_VISIBLE_DEVICES", "")
            ),
        }
    save_service_instance(instance_meta)
    release_pending_instance_ports(instance_id, allocated_ports)
    status_payload = {
        "run_id": run_id,
        "instance_id": instance_id,
        "status": "starting",
        "script_pid": proc.pid,
        "config_profile": "runtime",
        "config_file": runtime_config_path,
        "draft_config": draft_config_path,
        "log_dir": run_log_dir,
        "pid_dir": pid_dir,
        "started_at": started_at,
        "finished_at": None,
        "ports": {
            "vllm": allocated_ports["vllm"],
            "inference": allocated_ports["inference"],
            "ui": allocated_ports["ui"],
            "case2chat": allocated_ports["case2chat"],
            "master": allocated_ports["master"],
        },
        "error": None,
        "gpu_allocation": gpu_allocation,
    }
    if resource_pool_managed():
        status_payload["resource"] = instance_meta["resource"]
    atomic_write_json(status_file, status_payload)
    atomic_write_json(
        get_service_start_latest_path(),
        {
            "run_id": run_id,
            "status_file": status_file,
        },
    )
    allocation_mode = str(gpu_allocation.get("mode") or "auto")
    allocation_text = (
        "用户指定本次实例 GPU，不修改全局 service.yaml 或用户 draft"
        if allocation_mode == "manual"
        else "自动选择本次实例可用 GPU，不修改全局 service.yaml 或用户 draft"
    )
    return (
        "启动任务已提交，正在后台启动。\n"
        f"instance_id: {instance_id}\n"
        f"run_id: {run_id}\n"
        f"模型: {runtime_env['MODEL_NAME']}\n"
        f"模型路径: {runtime_env['MODEL_PATH']}{runtime_env['MODEL_NAME']}\n"
        f"HOST_IP: {runtime_env['HOST_IP']}\n"
        f"GPU分配: {allocation_text}\n"
        f"GPU: {runtime_env.get('CUDA_VISIBLE_DEVICES', '')}\n"
        f"TP: {runtime_config['RUNTIME'].get('TENSOR_PARALLEL_SIZE')}\n"
        "端口:\n"
        f"- vLLM OpenAI API: {allocated_ports['vllm']}\n"
        f"- Inference Server: {allocated_ports['inference']}\n"
        f"- Web UI: {allocated_ports['ui']}\n"
        f"- Case2Chat: {allocated_ports['case2chat']}\n"
        f"- MASTER_PORT: {allocated_ports['master']}\n"
        f"runtime_config: {format_agent_relative_path(runtime_config_path)}\n"
        f"draft_config: {format_agent_relative_path(draft_config_path)}\n"
        f"log_dir: {format_agent_relative_path(run_log_dir)}\n"
        "启动任务已提交不代表服务已启动完成。\n"
        "除非用户明确要求继续执行其他操作，否则请直接返回以上信息，不要继续调用 service_status、service_start_status 或日志工具。"
    )
    # f"- Voice: {ports.get('VOICE_PORT', 9007)}"
    # "您可以稍后调用 service_start_status() 查看推理启动状态。"


def stop_service() -> str:
    """Stop inference service stack."""
    active_instances = active_service_instance_candidates(scope="mine")
    if len(active_instances) > 1:
        return instance_stop_choice_required_text(active_instances)
    if len(active_instances) == 1:
        instance_id = str(
            active_instances[0].get("instance_id")
            or active_instances[0].get("run_id")
            or ""
        )
        if instance_id:
            return stop_service_instance(instance_id)

    own_latest = resolve_service_instance_id("latest", scope="mine", require_running=False)
    if own_latest:
        return stop_service_instance(own_latest)
    if list_service_instance_ids():
        return (
            "未找到当前用户可停止的推理服务实例。\n"
            "当前节点存在实例记录，但这些实例不属于当前用户；不会执行旧的全局 stop。"
        )

    CONFIG = show_config()
    run_command(f"bash {CONFIG['ENV']['START_SCRIPT']} stop")
    return "Service stopped!"


def service_instance_owner(meta: dict) -> str:
    owner = str(meta.get("owner_user_id") or "").strip()
    current = current_request_user_id()
    if owner and current and owner == current:
        return "self"
    if owner:
        return "other"
    return "unknown"


def task_owner_user_id(meta: dict) -> str:
    owner = str(meta.get("owner_user_id") or "").strip()
    if owner:
        return owner

    instance_id = str(meta.get("service_instance_id") or "").strip()
    if instance_id:
        instance_meta = load_service_instance(instance_id)
        return str(instance_meta.get("owner_user_id") or "").strip()
    return ""


def task_owner_label(meta: dict) -> str:
    owner = task_owner_user_id(meta)
    current = current_request_user_id()
    if owner and current and owner == current:
        return "self"
    if owner:
        return "other"
    return "unknown"


def task_visible_for_scope(meta: dict, scope: str = "mine") -> bool:
    scope = str(scope or "mine").strip().lower()
    if scope == "all":
        return True
    current = current_request_user_id()
    if not current:
        return False
    return bool(task_owner_user_id(meta) == current)


def visible_service_instance_meta(instance_id: str) -> dict:
    meta = refresh_service_instance_status(load_service_instance(instance_id))
    if meta:
        save_service_instance(meta)
    return meta


def service_instance_access_error(instance_id: str, action: str = "操作") -> str:
    requested = str(instance_id or "").strip()
    if not requested or requested == "latest" or requested not in list_service_instance_ids():
        return ""
    meta = visible_service_instance_meta(requested)
    if not meta:
        return ""
    owner = str(meta.get("owner_user_id") or "").strip()
    current = current_request_user_id()
    if not current:
        return (
            f"当前请求缺少用户身份，已拒绝{action}推理服务实例。\n"
            f"instance_id={requested}"
        )
    if not owner:
        return (
            f"推理服务实例没有有效的所有者记录，已拒绝{action}。\n"
            f"instance_id={requested}\n"
            "请通过服务器运维方式处理该历史实例。"
        )
    if owner != current:
        return (
            f"推理服务实例存在，但属于其他用户，已拒绝{action}。\n"
            f"instance_id={requested}\n"
            f"owner=other\n"
            "当前用户只能操作自己的推理服务实例。\n"
            '可调用 service_instance_list(scope="mine") 查看当前用户可用实例。'
        )
    return ""


def resolve_service_instance_id(
    instance_id: str = "latest",
    scope: str = "mine",
    require_running: bool = False,
) -> str:
    requested = str(instance_id or "latest").strip()
    ids = list_service_instance_ids()
    current = current_request_user_id()
    if scope == "mine" and not current:
        return ""

    if requested not in {"", "latest"}:
        if requested not in ids:
            return ""
        meta = visible_service_instance_meta(requested)
        if not meta:
            return ""
        if scope == "mine" and current and str(meta.get("owner_user_id") or "") != current:
            return ""
        if require_running and meta.get("status") not in {"running", "starting"}:
            return ""
        return requested

    candidates = []
    for item in ids:
        meta = visible_service_instance_meta(item)
        if not meta:
            continue
        if scope == "mine" and current and str(meta.get("owner_user_id") or "") != current:
            continue
        if require_running and meta.get("status") not in {"running", "starting"}:
            continue
        candidates.append(item)
    return candidates[0] if candidates else ""


def running_service_instance_candidates(scope: str = "mine") -> list[dict]:
    current = current_request_user_id()
    if scope == "mine" and not current:
        return []
    candidates = []
    for instance_id in list_service_instance_ids():
        meta = visible_service_instance_meta(instance_id)
        if not meta:
            continue
        if scope == "mine" and current and str(meta.get("owner_user_id") or "") != current:
            continue
        if meta.get("status") != "running":
            continue
        candidates.append(meta)
    candidates.sort(
        key=lambda meta: (
            -parse_time_sort_value(meta.get("started_at")),
            str(meta.get("instance_id") or meta.get("run_id") or ""),
        )
    )
    return candidates


def active_service_instance_candidates(scope: str = "mine") -> list[dict]:
    current = current_request_user_id()
    if scope == "mine" and not current:
        return []
    candidates = []
    for instance_id in list_service_instance_ids():
        meta = visible_service_instance_meta(instance_id)
        if not meta:
            continue
        if scope == "mine" and current and str(meta.get("owner_user_id") or "") != current:
            continue
        if meta.get("status") not in {"running", "starting"}:
            continue
        candidates.append(meta)
    candidates.sort(
        key=lambda meta: (
            status_sort_rank(meta.get("status")),
            -parse_time_sort_value(meta.get("started_at")),
            str(meta.get("instance_id") or meta.get("run_id") or ""),
        )
    )
    return candidates


def instance_choice_required_text(candidates: list[dict], task_name: str) -> str:
    lines = [
        f"当前用户有多个运行中的推理服务实例，暂不能自动选择实例运行 {task_name}。",
        "请指定 instance_id 后重试。",
        "",
        "可用实例:",
    ]
    for meta in candidates:
        ports = meta.get("ports") or {}
        lines.append(
            "- "
            f"instance_id={meta.get('instance_id') or meta.get('run_id')} "
            f"status={meta.get('status', '')} "
            f"gpus={meta.get('actual_gpus', '')} "
            f"model={meta.get('model', '')} "
            f"inference={ports.get('inference', '')} "
            f"ui={ports.get('ui', '')} "
            f"started_at={meta.get('started_at', '')}"
        )
    return "\n".join(lines)


def instance_stop_choice_required_text(candidates: list[dict]) -> str:
    lines = [
        "当前用户有多个活跃的推理服务实例，暂不能自动选择要停止的实例。",
        "请指定 instance_id 后重试，例如 service_instance_stop(instance_id=...)。",
        "",
        "可停止实例:",
    ]
    for meta in candidates:
        ports = meta.get("ports") or {}
        lines.append(
            "- "
            f"instance_id={meta.get('instance_id') or meta.get('run_id')} "
            f"status={meta.get('status', '')} "
            f"gpus={meta.get('actual_gpus', '')} "
            f"model={meta.get('model', '')} "
            f"inference={ports.get('inference', '')} "
            f"ui={ports.get('ui', '')} "
            f"started_at={meta.get('started_at', '')}"
        )
    return "\n".join(lines)


def resolve_task_service_instance_id(
    instance_id: str = "latest", task_name: str = "task"
) -> str | None:
    requested = str(instance_id or "latest").strip()
    if requested not in {"", "latest"}:
        resolved = resolve_service_instance_id(
            requested, scope="mine", require_running=True
        )
        return resolved or requested

    candidates = running_service_instance_candidates(scope="mine")
    if not candidates:
        return None
    if len(candidates) > 1:
        raise ValueError(instance_choice_required_text(candidates, task_name))
    return str(candidates[0].get("instance_id") or candidates[0].get("run_id") or "")


def get_running_service_instance_config(
    instance_id: str = "latest",
) -> tuple[str, dict, dict] | tuple[None, None, None]:
    resolved = resolve_service_instance_id(
        instance_id, scope="mine", require_running=True
    )
    if not resolved:
        return None, None, None

    meta = visible_service_instance_meta(resolved)
    if meta.get("status") != "running":
        return None, None, meta

    runtime_config = str(meta.get("runtime_config") or "")
    if not runtime_config or not os.path.exists(runtime_config):
        return None, None, meta

    with open(runtime_config, "r") as f:
        cfg = yaml.safe_load(f) or {}
    return resolved, cfg, meta


def require_running_service_instance_config(
    instance_id: str = "latest",
) -> tuple[str, dict, dict] | str:
    if not current_request_user_id():
        return "当前请求缺少用户身份，已拒绝运行测试或 benchmark。"
    access_error = service_instance_access_error(instance_id, "运行测试或 benchmark")
    if access_error:
        return access_error

    resolved, cfg, meta = get_running_service_instance_config(instance_id)
    if resolved and cfg:
        return resolved, cfg, meta

    if meta and meta.get("status") == "starting":
        return (
            "当前用户的推理服务实例仍在启动中，暂不能运行测试或 benchmark。\n"
            f"instance_id={meta.get('instance_id') or meta.get('run_id')}\n"
            "请稍后查看启动状态，确认服务启动完成后再重试。"
        )
    if meta:
        return (
            "当前用户没有运行中的推理服务实例，暂不能运行测试或 benchmark。\n"
            f"instance_id={meta.get('instance_id') or meta.get('run_id')}\n"
            f"status={meta.get('status')}"
        )
    return "未找到当前用户运行中的推理服务实例，请先启动推理服务。"


def list_service_instances_text(scope: str = "mine", limit: int = DEFAULT_LIST_LIMIT) -> str:
    scope = str(scope or "mine").strip().lower()
    if scope not in {"mine", "all"}:
        return "Invalid scope. Use mine or all."
    limit = clamp_int(limit, DEFAULT_LIST_LIMIT, 1, MAX_LIST_LIMIT)

    ids = list_service_instance_ids()
    if not ids:
        return "暂无推理服务实例。"

    lines = [f"推理服务实例列表(scope={scope}):"]
    items = []
    for instance_id in ids:
        meta = visible_service_instance_meta(instance_id)
        if not meta:
            continue
        owner = service_instance_owner(meta)
        if scope == "mine" and owner != "self":
            continue
        items.append((instance_id, owner, meta))

    items.sort(
        key=lambda item: (
            -parse_time_sort_value(item[2].get("started_at")),
            status_sort_rank(item[2].get("status")),
            item[0],
        )
    )

    visible_items = items[:limit]
    lines.append(f"显示 {len(visible_items)} / {len(items)} 条，limit={limit}")
    if scope == "all":
        owner_counts = {"self": 0, "other": 0, "unknown": 0}
        for _, owner, _ in items:
            owner_counts[owner if owner in owner_counts else "unknown"] += 1
        lines.append(
            "owner统计: "
            f"self={owner_counts['self']}, "
            f"other={owner_counts['other']}, "
            f"unknown={owner_counts['unknown']}"
        )
    if len(items) > limit:
        lines.append(f"还有 {len(items) - limit} 条未显示，可增大 limit 查看。")

    for instance_id, owner, meta in visible_items:
        ports = meta.get("ports") or {}
        lines.append(
            " | ".join(
                [
                    f"instance_id={instance_id}",
                    f"owner={owner}",
                    f"status={meta.get('status', '')}",
                    f"gpus={meta.get('actual_gpus', '')}",
                    f"model={meta.get('model', '')}",
                    f"vllm={ports.get('vllm', '')}",
                    f"inference={ports.get('inference', '')}",
                    f"ui={ports.get('ui', '')}",
                    f"started_at={meta.get('started_at', '')}",
                ]
            )
        )
    if not items:
        return "暂无当前用户的推理服务实例。" if scope == "mine" else "暂无推理服务实例。"
    return "\n".join(lines)


def service_instance_status_text(instance_id: str = "latest") -> str:
    access_error = service_instance_access_error(instance_id, "查看状态")
    if access_error:
        return access_error

    resolved = resolve_service_instance_id(instance_id, scope="mine")
    if not resolved:
        return f"未找到推理服务实例: {instance_id}"

    meta = visible_service_instance_meta(resolved)
    if not meta:
        return f"推理服务实例不存在: {resolved}"

    ports = meta.get("ports") or {}
    lines = [
        "推理服务实例状态:",
        f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"instance_id={resolved}",
        f"owner={service_instance_owner(meta)}",
        f"status={meta.get('status', '')}",
        f"model={meta.get('model', '')}",
        f"gpus={meta.get('actual_gpus', '')}",
        f"started_at={meta.get('started_at', '')}",
        f"finished_at={meta.get('finished_at', '')}",
        f"runtime_config={format_agent_relative_path(meta.get('runtime_config', ''))}",
        f"log_dir={format_agent_relative_path(meta.get('log_dir', ''))}",
        "ports:",
    ]
    for name in ("vllm", "inference", "ui", "case2chat", "master"):
        port = ports.get(name, "")
        if name == "master":
            mark = "RESERVED"
        else:
            try:
                mark = "RUNNING" if check_port(int(port)) else "STOPPED"
            except (TypeError, ValueError):
                mark = "UNKNOWN"
        lines.append(f"- {name}: {port} {mark}")
    return "\n".join(lines)


def running_tasks_for_service_instance(instance_id: str) -> dict:
    benchmark_items = []
    for job_id, meta_path, meta in iter_json_records(get_benchmark_log_dir(), "meta.json"):
        meta = refresh_benchmark_job_meta(job_id, meta_path, meta)
        if str(meta.get("service_instance_id") or "") != instance_id:
            continue
        if meta.get("status") != "running":
            continue
        benchmark_items.append(
            {
                "job_id": meta.get("job_id", job_id),
                "dataset": meta.get("dataset", ""),
                "mode": meta.get("mode", ""),
                "start_time": meta.get("start_time", ""),
                "output": format_agent_relative_path(meta.get("output", "")),
            }
        )

    test_items = []
    runs_dir = os.path.join(get_test_log_root(), "runs")
    for test_run_id, status_file, meta in iter_json_records(runs_dir, "status.json"):
        meta = refresh_test_run_meta(test_run_id, status_file, meta)
        if str(meta.get("service_instance_id") or "") != instance_id:
            continue
        if meta.get("status") != "running":
            continue

        tests = meta.get("tests") or {}
        if tests:
            active_scripts = [
                name
                for name, item in tests.items()
                if item.get("status") in {"running", "pending"}
            ]
            test_items.append(
                {
                    "test_run_id": meta.get("test_run_id", test_run_id),
                    "test_name": meta.get("test_name", ""),
                    "scripts": ",".join(active_scripts) or "all",
                    "started_at": meta.get("started_at", ""),
                    "log_file": format_test_path(meta.get("log_file", "")),
                }
            )
            continue

        script_pid = int(meta.get("script_pid") or 0)
        if script_pid and is_process_running(script_pid):
            test_items.append(
                {
                    "test_run_id": meta.get("test_run_id", test_run_id),
                    "test_name": meta.get("test_name", ""),
                    "scripts": meta.get("test_name", ""),
                    "started_at": meta.get("started_at", ""),
                    "log_file": format_test_path(
                        meta.get("response_log_file") or meta.get("log_file", "")
                    ),
                }
            )

    return {
        "benchmark": sorted(
            benchmark_items, key=lambda item: item.get("start_time", ""), reverse=True
        ),
        "tests": sorted(
            test_items, key=lambda item: item.get("started_at", ""), reverse=True
        ),
    }


def running_instance_tasks_block_text(instance_id: str, tasks: dict) -> str:
    benchmark_items = tasks.get("benchmark") or []
    test_items = tasks.get("tests") or []
    if not benchmark_items and not test_items:
        return ""

    lines = [
        "检测到该推理服务实例下仍有任务正在运行，暂不停止实例。",
        f"instance_id={instance_id}",
        "请先向用户确认是否停止以下任务；未经用户明确确认，不要调用 benchmark_stop、service_test_stop，也不要继续停止该实例。",
    ]

    if benchmark_items:
        lines.append("")
        lines.append("运行中的 benchmark:")
        for item in benchmark_items:
            lines.append(
                "- "
                f"job_id={item['job_id']} "
                f"dataset={item['dataset']} "
                f"mode={item['mode']} "
                f"start_time={item['start_time']} "
                f"output={item['output']}"
            )

    if test_items:
        lines.append("")
        lines.append("运行中的功能测试:")
        for item in test_items:
            lines.append(
                "- "
                f"test_run_id={item['test_run_id']} "
                f"test_name={item['test_name']} "
                f"scripts={item['scripts']} "
                f"started_at={item['started_at']} "
                f"log_file={item['log_file']}"
            )

    return "\n".join(lines)


def service_instance_runtime_active(
    meta: dict, tracked_pids: list[int] | None = None
) -> bool:
    """Return whether an instance owns or may own a live process or port."""
    port_ownership = service_instance_port_ownership(meta)
    process_ownership = service_instance_process_ownership(
        meta, port_ownership, tracked_pids=tracked_pids
    )
    return bool(
        process_ownership["owned"]
        or process_ownership["unverified"]
        or port_ownership["owned"]
        or port_ownership["unverified"]
    )


def service_instance_is_active(meta: dict) -> bool:
    status = str(meta.get("status") or "").lower()
    return status in {"starting", "running"} and service_instance_runtime_active(meta)


def stop_service_instance_runtime(meta: dict) -> str:
    """Stop one instance after the caller has completed authorization checks."""
    instance_id = str(meta.get("instance_id") or meta.get("run_id") or "").strip()
    runtime_config = str(meta.get("runtime_config") or "")
    if not runtime_config or not os.path.exists(runtime_config):
        ownership_cleanup = terminate_instance_owned_processes(meta)
        meta = refresh_service_instance_status(meta)
        if service_instance_runtime_active(meta):
            save_service_instance(meta)
            return (
                "推理服务实例停止失败：runtime_config 不存在，但仍检测到存活进程或端口。\n"
                f"instance_id={instance_id}\n"
                f"runtime_config={runtime_config}\n"
                f"status={meta.get('status', '')}\n"
                f"ownership_cleanup={ownership_cleanup}"
            )
        meta["status"] = "stopped"
        meta["finished_at"] = current_time_text()
        meta["stop_result"] = "runtime_config missing; no live process or port detected"
        save_service_instance(meta)
        return (
            f"推理服务实例已停止（未检测到存活进程或端口）: {instance_id}\n"
            f"runtime_config={runtime_config}"
        )

    tracked_pids = service_instance_recorded_pids(meta)
    try:
        with open(runtime_config, "r", encoding="utf-8") as f:
            runtime_cfg = yaml.safe_load(f) or {}
        start_script = str(runtime_cfg.get("ENV", {}).get("START_SCRIPT") or "")
        if not start_script:
            raise ValueError("ENV.START_SCRIPT is missing")
        completed = subprocess.run(
            ["bash", start_script, "stop", runtime_config],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
        )
        result = completed.stdout.strip()
        return_code = completed.returncode
    except (OSError, ValueError, yaml.YAMLError) as exc:
        result = f"{type(exc).__name__}: {exc}"
        return_code = -1
    except subprocess.TimeoutExpired as exc:
        result = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        result = f"停止命令执行超时。{result}".strip()
        return_code = -1

    ownership_cleanup = terminate_instance_owned_processes(meta)
    if ownership_cleanup["matched_pids"]:
        result = (
            f"{result}\ninstance_owned_process_cleanup={ownership_cleanup}"
        ).strip()

    meta["stop_result"] = result
    meta["stop_return_code"] = return_code
    for _ in range(10):
        meta = refresh_service_instance_status(meta)
        if not service_instance_runtime_active(meta, tracked_pids):
            break
        time.sleep(0.5)

    meta = refresh_service_instance_status(meta)
    stopped = not service_instance_runtime_active(meta, tracked_pids)
    if stopped:
        meta["status"] = "stopped"
        finish_meta_if_missing(meta)
    save_service_instance(meta)

    if not stopped:
        return (
            "推理服务实例未完全停止。\n"
            f"instance_id={instance_id}\n"
            f"status={meta.get('status', '')}\n"
            f"stop_return_code={return_code}\n"
            f"stop_result={result or '(empty)'}"
        )
    response = (
        f"推理服务实例已停止: instance_id={instance_id}\n"
        f"gpus={meta.get('actual_gpus', '')}\n"
        f"log_dir={format_agent_relative_path(meta.get('log_dir', ''))}"
    )
    if return_code != 0:
        response += f"\n停止命令返回码={return_code}，但已确认相关 PID 和端口均已释放。"
    return response


def stop_service_instance(instance_id: str, confirm: bool = False) -> str:
    meta = visible_service_instance_meta(instance_id)
    if not meta:
        return f"推理服务实例不存在: {instance_id}"

    current = current_request_user_id()
    owner = str(meta.get("owner_user_id") or "").strip()
    if not current:
        return (
            "当前请求缺少用户身份，已拒绝停止推理服务实例。\n"
            f"instance_id={instance_id}"
        )
    if not owner:
        return (
            "该推理服务实例没有有效的所有者记录，已拒绝停止。\n"
            f"instance_id={instance_id}\n"
            "请通过服务器运维方式处理该历史实例。"
        )
    if owner != current:
        return (
            "该推理服务实例属于其他用户，已拒绝停止。\n"
            f"instance_id={instance_id}\n"
            f"status={meta.get('status', '')}\n"
            "普通工具只允许停止当前用户自己的实例；如需处理残留实例，请由管理员单独处理。"
        )

    block_text = running_instance_tasks_block_text(
        instance_id, running_tasks_for_service_instance(instance_id)
    )
    if block_text:
        return block_text
    return stop_service_instance_runtime(meta)


def list_service_instance_tasks_text(instance_id: str = "latest") -> str:
    access_error = service_instance_access_error(instance_id, "查看关联任务")
    if access_error:
        return access_error

    resolved = resolve_service_instance_id(instance_id, scope="mine")
    if not resolved:
        return f"未找到推理服务实例: {instance_id}"

    lines = [
        "推理服务实例任务:",
        f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"instance_id={resolved}",
    ]

    benchmark_items = []
    benchmark_root = get_benchmark_log_dir()
    for job_id, _, meta in iter_json_records(benchmark_root, "meta.json"):
        if str(meta.get("service_instance_id") or "") != resolved:
            continue
        benchmark_items.append(
            {
                "job_id": meta.get("job_id", job_id),
                "dataset": meta.get("dataset", ""),
                "mode": meta.get("mode", ""),
                "status": meta.get("status", ""),
                "start_time": meta.get("start_time", ""),
                "end_time": meta.get("end_time", ""),
                "log": format_agent_relative_path(meta.get("log", "")),
                "output": format_agent_relative_path(meta.get("output", "")),
            }
        )
    benchmark_items.sort(
        key=lambda item: (
            status_sort_rank(item.get("status")),
            -parse_time_sort_value(item.get("start_time")),
            str(item.get("job_id") or ""),
        )
    )

    test_items = []
    test_runs_dir = os.path.join(get_test_log_root(), "runs")
    for test_run_id, _, meta in iter_json_records(test_runs_dir, "status.json"):
        if str(meta.get("service_instance_id") or "") != resolved:
            continue
        test_items.append(
            {
                "test_run_id": meta.get("test_run_id", test_run_id),
                "test_name": meta.get("test_name", ""),
                "status": meta.get("status", ""),
                "started_at": meta.get("started_at", ""),
                "finished_at": meta.get("finished_at", ""),
                "log_file": format_test_path(meta.get("log_file", "")),
                "response_log_file": format_test_path(
                    meta.get("response_log_file", "")
                ),
            }
        )
    test_items.sort(
        key=lambda item: (
            status_sort_rank(item.get("status")),
            -parse_time_sort_value(item.get("started_at")),
            str(item.get("test_run_id") or ""),
        )
    )

    lines.append("")
    lines.append(f"Benchmark任务: {len(benchmark_items)}")
    if benchmark_items:
        for item in benchmark_items:
            lines.append(
                "- "
                f"job_id={item['job_id']} "
                f"dataset={item['dataset']} "
                f"mode={item['mode']} "
                f"status={item['status']} "
                f"start_time={item['start_time']} "
                f"end_time={item['end_time']} "
                f"log={item['log']} "
                f"output={item['output']}"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append(f"功能测试任务: {len(test_items)}")
    if test_items:
        for item in test_items:
            lines.append(
                "- "
                f"test_run_id={item['test_run_id']} "
                f"test_name={item['test_name']} "
                f"status={item['status']} "
                f"started_at={item['started_at']} "
                f"finished_at={item['finished_at']} "
                f"log_file={item['log_file']} "
                f"response_log_file={item['response_log_file']}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def running_benchmark_jobs() -> list[dict]:
    """Return benchmark jobs whose meta.json status is running."""
    base = get_benchmark_log_dir()

    jobs = []
    for job_id, meta_path, meta in iter_json_records(base, "meta.json"):
        meta = refresh_benchmark_job_meta(job_id, meta_path, meta)
        if meta.get("status") != "running":
            continue
        jobs.append(
            {
                "job_id": meta.get("job_id", job_id),
                "dataset": meta.get("dataset", ""),
                "mode": meta.get("mode", ""),
                "model": meta.get("model", ""),
                "start_time": meta.get("start_time", ""),
                "output": format_agent_relative_path(meta.get("output", "")),
            }
        )

    return sorted(
        jobs,
        key=lambda item: (
            -parse_time_sort_value(item.get("start_time")),
            str(item.get("job_id") or ""),
        ),
    )


def refresh_benchmark_job_meta(
    job_id: str, meta_path: str, meta: dict, persist: bool = True
) -> dict:
    if meta.get("status") != "running":
        return meta

    pid = int(meta.get("pid") or 0)
    if pid_is_alive(pid):
        return meta

    old_status = str(meta.get("status") or "")
    return_code = meta.get("return_code")
    output = str(meta.get("output") or "")
    has_output = bool(output and os.path.exists(output))
    if return_code == 0:
        meta["status"] = "finished"
    elif return_code is not None:
        meta["status"] = "failed"
    elif has_output:
        meta["status"] = "unknown_finished"
    else:
        meta["status"] = "failed"
        meta["return_code"] = -1
    finish_meta_if_missing(meta, "end_time")
    mark_meta_stale_fixed(
        meta,
        "benchmark_pid_not_running",
        job_id=job_id,
        pid=pid,
        old_status=old_status,
        new_status=meta.get("status"),
    )
    return write_meta_if_changed(meta_path, meta, persist)


def running_benchmark_jobs_text() -> str:
    jobs = running_benchmark_jobs()
    if not jobs:
        return ""

    lines = [
        "检测到 benchmark 任务正在运行，暂不停止推理服务。",
        "停止 benchmark 会中断正在运行的评测任务。",
        "请先向用户确认是否停止以下 benchmark 任务；未经用户明确确认，不要调用 benchmark_stop，也不要继续停止推理服务：",
    ]
    for job in jobs:
        lines.append(
            "- "
            f"job_id={job['job_id']} "
            f"dataset={job['dataset']} "
            f"mode={job['mode']} "
            f"model={job['model']} "
            f"start_time={job['start_time']} "
            f"output={job['output']}"
        )
    return "\n".join(lines)


def tail_logs(service: str = "start", lines: int = 30, run_id: str = "latest") -> str:
    """Summarize important messages in log."""
    lines = clamp_int(lines, 30, 1, MAX_LOG_LINES)
    paths = get_log_paths(service, run_id)
    existing_paths = [path for path in paths if os.path.exists(path)]
    if not existing_paths:
        return f"Log file not found: {', '.join(paths)}"
    path = " ".join(shlex.quote(path) for path in existing_paths)
    cmd = f"""
    echo "\n========= ERRORS =========";
    grep -inE "error|exception|fail|traceback|timeout|critical" {path} | tail -n 20;

    echo "\n========= WARNINGS =========";
    grep -in warn {path} | tail -n 20;

    echo "\n========= LAST LOG =========";
    grep -n "" {path} | tail -n {lines};
    """
    return safe_output(run_command(cmd))


def logs_search(
    keyword: str = "error",
    service: str = "all",
    limit: int = 20,
    run_id: str = "latest",
) -> str:
    """Search keyword in logs."""
    limit = clamp_int(limit, 20, 1, MAX_LOG_LINES)
    paths = get_log_paths(service, run_id)
    existing_paths = [path for path in paths if os.path.exists(path)]
    if not existing_paths:
        return f"Log file not found: {', '.join(paths)}"
    path = " ".join(shlex.quote(path) for path in existing_paths)
    cmd = f"grep -inE {shlex.quote(keyword)} {path} | tail -n {limit}"
    result = safe_output(run_command(cmd)).strip()
    if not result:
        return (
            f"No log entries matched keyword={keyword!r} "
            f"service={service!r} run_id={run_id!r}."
        )
    return result


def context_log(
    service: str, index: int, window: int = 20, run_id: str = "latest"
) -> str:
    """Show log context around a specific line."""
    index = clamp_int(index, 1, 1, 10**9)
    window = clamp_int(window, 20, 0, MAX_LOG_CONTEXT_WINDOW)
    if service == "all":
        return 'service="all" is not supported for context_log'
    paths = get_log_paths(service, run_id)
    path = paths[0]
    if not os.path.exists(path):
        return f"Log file not found: {path}"
    start = max(index - window, 1)
    end = index + window
    return safe_output(run_command(f"sed -n '{start},{end}p' {shlex.quote(path)}"))


def list_tests() -> str:
    """List all available test scripts."""
    CONFIG = show_config()
    TEST_DIR = CONFIG["ENV"]["TEST_DIR"]
    if not os.path.isdir(TEST_DIR):
        return f"测试脚本目录不存在: {TEST_DIR}"
    scripts = sorted(name for name in os.listdir(TEST_DIR) if name.endswith(".sh"))
    if not scripts:
        return "暂无功能测试脚本。"
    return "\n".join(scripts)


def get_test_log_root() -> str:
    return os.path.join(get_service_log_root(), "tests")


def get_test_latest_path() -> str:
    return os.path.join(get_test_log_root(), "test_latest.json")


def get_test_status_path(test_run_id: str) -> str:
    if "/" in test_run_id or ".." in test_run_id:
        raise ValueError("Invalid test_run_id")
    return os.path.join(get_test_log_root(), "runs", test_run_id, "status.json")


def resolve_test_run_id(test_run_id: str = "latest", scope: str = "mine") -> str:
    if test_run_id and test_run_id != "latest":
        return test_run_id
    scope = str(scope or "mine").strip().lower()
    runs_dir = os.path.join(get_test_log_root(), "runs")
    if os.path.isdir(runs_dir):
        candidates = []
        for item_id, status_file, meta in iter_json_records(runs_dir, "status.json"):
            meta = refresh_test_run_meta(item_id, status_file, meta)
            if not task_visible_for_scope(meta, scope):
                continue
            candidates.append(
                (
                    parse_time_sort_value(meta.get("started_at")) or os.path.getmtime(status_file),
                    item_id,
                )
            )
        if candidates:
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][1]
    latest_path = get_test_latest_path()
    if not os.path.exists(latest_path):
        raise FileNotFoundError(f"暂无测试状态记录: {latest_path}")
    with open(latest_path, "r") as f:
        latest = json.load(f)
    return latest.get("test_run_id", "latest")


def resolve_test_runtime_path(path: str) -> str:
    if not path or os.path.isabs(path):
        return path
    test_dir = show_config()["ENV"]["TEST_DIR"]
    return os.path.abspath(os.path.join(test_dir, path))


def format_test_path(path: str) -> str:
    return format_agent_relative_path(resolve_test_runtime_path(path))


def _refresh_test_run_meta_value(test_run_id: str, meta: dict) -> tuple[dict, bool]:
    if meta.get("status") != "running":
        return meta, False

    tests = meta.get("tests") or {}
    changed = False
    old_status = str(meta.get("status") or "")
    if tests:
        active_found = False
        for item in tests.values():
            item_status = item.get("status")
            pid = int(item.get("pid") or 0)
            if item_status == "pending":
                active_found = True
                continue
            if item_status == "running":
                if pid_is_alive(pid):
                    active_found = True
                else:
                    item["status"] = "unknown_finished"
                    finish_meta_if_missing(item)
                    changed = True
        if not active_found:
            statuses = {item.get("status") for item in tests.values()}
            if "failed" in statuses:
                meta["status"] = "failed"
            elif "unknown_finished" in statuses:
                meta["status"] = "unknown_finished"
            else:
                meta["status"] = "finished"
            finish_meta_if_missing(meta)
            changed = True
    else:
        script_pid = int(meta.get("script_pid") or 0)
        if not pid_is_alive(script_pid):
            meta["status"] = "unknown_finished"
            finish_meta_if_missing(meta)
            changed = True

    if changed:
        mark_meta_stale_fixed(
            meta,
            "test_pid_not_running",
            test_run_id=test_run_id,
            old_status=old_status,
            new_status=meta.get("status"),
        )
    return meta, changed


def refresh_test_run_meta(
    test_run_id: str, status_file: str, meta: dict, persist: bool = True
) -> dict:
    if not persist:
        return _refresh_test_run_meta_value(test_run_id, meta)[0]

    with json_file_lock(status_file):
        current = load_json_file(status_file, None)
        if not isinstance(current, dict) or not current:
            return meta
        current, changed = _refresh_test_run_meta_value(test_run_id, current)
        return write_meta_if_changed(status_file, current, changed)


def running_tests_text(
    instance_id: str = "", limit: int = DEFAULT_LIST_LIMIT, scope: str = "mine"
) -> str:
    runs_dir = os.path.join(get_test_log_root(), "runs")
    if not os.path.isdir(runs_dir):
        return f"暂无功能测试运行记录: {runs_dir}"
    limit = clamp_int(limit, DEFAULT_LIST_LIMIT, 1, MAX_LIST_LIMIT)
    scope = str(scope or "mine").strip().lower()
    if scope not in {"mine", "all"}:
        return "Invalid scope. Use mine or all."

    resolved_instance_id = ""
    if instance_id:
        access_error = (
            service_instance_access_error(instance_id, "查看功能测试")
            if scope != "all"
            else ""
        )
        if access_error:
            return access_error
        resolved_instance_id = resolve_service_instance_id(
            instance_id, scope=scope, require_running=False
        )
        if not resolved_instance_id:
            return f"未找到推理服务实例: {instance_id}"

    running_items = []
    records = sorted(
        iter_json_records(runs_dir, "status.json"),
        key=lambda item: item[0],
        reverse=True,
    )
    for test_run_id, status_file, meta in records:
        meta = refresh_test_run_meta(test_run_id, status_file, meta)
        if (
            resolved_instance_id
            and str(meta.get("service_instance_id") or "") != resolved_instance_id
        ):
            continue
        if not task_visible_for_scope(meta, scope):
            continue
        if meta.get("status") != "running":
            continue

        tests = meta.get("tests") or {}
        if tests:
            for name, item in tests.items():
                if item.get("status") == "running":
                    running_items.append(
                        {
                            "test_run_id": test_run_id,
                            "test_name": meta.get("test_name"),
                            "script": name,
                            "pid": item.get("pid"),
                            "port": item.get("port"),
                            "started_at": item.get("started_at"),
                            "log_file": format_test_path(item.get("log_file")),
                            "run_started_at": meta.get("started_at"),
                            "owner": task_owner_label(meta),
                        }
                    )
        else:
            script_pid = int(meta.get("script_pid") or 0)
            if script_pid and is_process_running(script_pid):
                running_items.append(
                    {
                        "test_run_id": test_run_id,
                        "test_name": meta.get("test_name"),
                        "script": meta.get("test_name"),
                        "pid": script_pid,
                        "port": None,
                        "started_at": meta.get("started_at"),
                        "log_file": format_test_path(
                            meta.get("response_log_file") or meta.get("log_file")
                        ),
                        "run_started_at": meta.get("started_at"),
                        "owner": task_owner_label(meta),
                    }
                )

    if not running_items:
        if resolved_instance_id:
            return (
                "当前实例没有正在运行的功能测试脚本。\n"
                f"instance_id={resolved_instance_id}\n"
                f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        return (
            "当前没有正在运行的功能测试脚本。\n"
            f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    running_items.sort(
        key=lambda item: (
            -parse_time_sort_value(item.get("started_at") or item.get("run_started_at")),
            str(item.get("test_run_id") or ""),
            str(item.get("script") or ""),
        )
    )

    visible_items = running_items[:limit]
    lines = [
        f"正在运行的功能测试脚本(scope={scope}):",
        f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"running={len(running_items)}",
        f"显示 {len(visible_items)} / {len(running_items)} 条，limit={limit}",
    ]
    if scope == "all":
        owner_counts = {"self": 0, "other": 0, "unknown": 0}
        for item in running_items:
            owner = item.get("owner") if item.get("owner") in owner_counts else "unknown"
            owner_counts[owner] += 1
        lines.append(
            "owner统计: "
            f"self={owner_counts['self']}, "
            f"other={owner_counts['other']}, "
            f"unknown={owner_counts['unknown']}"
        )
    if len(running_items) > limit:
        lines.append(f"还有 {len(running_items) - limit} 条未显示，可增大 limit 查看。")
    if resolved_instance_id:
        lines.append(f"instance_id={resolved_instance_id}")
    for item in visible_items:
        lines.append(
            "- "
            f"test_run_id={item['test_run_id']}, "
            f"test_name={item.get('test_name')}, "
            f"owner={item.get('owner')}, "
            f"script={item.get('script')}, "
            f"pid={item.get('pid')}, "
            f"port={item.get('port')}, "
            f"started_at={item.get('started_at')}, "
            f"log_file={item.get('log_file')}"
        )
    return "\n".join(lines)


def monitor_test_job(test_run_id: str, proc: subprocess.Popen, status_file: str):
    exit_code = proc.wait()

    def finish(meta):
        if meta.get("status") != "running":
            return
        meta["status"] = "finished" if exit_code == 0 else "failed"
        meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["exit_code"] = exit_code

    update_all_test_status(status_file, finish)


def update_all_test_status(status_file: str, update_fn):
    with json_file_lock(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        update_fn(meta)
        atomic_write_json(status_file, meta)
        return meta


def mark_remaining_tests(tests: dict, status: str):
    for item in tests.values():
        if item.get("status") in {"pending", "running"}:
            item["status"] = status
            item["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def run_all_test_job(
    scripts: list,
    host: str,
    ports: dict,
    test_cwd: str,
    status_file: str,
    log_file: str,
    response_log_dir: str,
):
    failed = False
    for script_name in scripts:
        def prepare(meta):
            if meta.get("status") != "running":
                mark_remaining_tests(meta.get("tests", {}), "stopped")
                meta["finished_at"] = meta.get("finished_at") or time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

        meta = update_all_test_status(status_file, prepare)
        if meta.get("status") != "running":
            return

        port = (
            ports["DATA_ANNOTATION_PORT"]
            if script_name == "case2chat.sh"
            else ports["INFERENCE_PORT"]
        )
        response_log_file = os.path.join(
            response_log_dir, f"{os.path.splitext(script_name)[0]}.log"
        )
        proc_env = os.environ.copy()
        proc_env["TEST_LOG_FILE"] = response_log_file

        with open(log_file, "a") as f:
            f.write(f"\n===== Running {script_name} =====\n")
            proc = subprocess.Popen(
                ["bash", script_name, host, str(port)],
                stdout=f,
                stderr=subprocess.STDOUT,
                env=proc_env,
                cwd=test_cwd,
                start_new_session=True,
            )

        def mark_running(meta):
            if meta.get("status") != "running":
                return
            item = meta["tests"][script_name]
            item["status"] = "running"
            item["pid"] = proc.pid
            item["port"] = port
            item["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        meta = update_all_test_status(status_file, mark_running)
        if meta.get("status") != "running":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            return
        exit_code = proc.wait()

        def finish_script(meta):
            item = meta["tests"][script_name]
            if meta.get("status") != "running":
                item["status"] = "stopped"
                item["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                item["exit_code"] = None
                mark_remaining_tests(meta.get("tests", {}), "stopped")
                meta["finished_at"] = meta.get("finished_at") or time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                return
            item["status"] = "finished" if exit_code == 0 else "failed"
            item["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            item["exit_code"] = exit_code
            item["pid"] = proc.pid

        meta = update_all_test_status(status_file, finish_script)
        if meta.get("status") != "running":
            return
        failed = failed or exit_code != 0

    def finish_all(meta):
        if meta.get("status") != "running":
            return
        meta["status"] = "failed" if failed else "finished"
        meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["exit_code"] = 1 if failed else 0

    update_all_test_status(status_file, finish_all)


def start_test_job(
    test_name: str = "basicmedicalrecord.sh",
    run_all: bool = False,
    instance_id: str = "latest",
) -> str:
    try:
        resolved_task_instance_id = resolve_task_service_instance_id(
            instance_id, "功能测试"
        )
    except ValueError as e:
        return str(e)
    if resolved_task_instance_id:
        instance_id = resolved_task_instance_id

    instance_config = require_running_service_instance_config(instance_id)
    if isinstance(instance_config, str):
        return instance_config
    resolved_instance_id, CONFIG, instance_meta = instance_config

    TEST_DIR = CONFIG["ENV"]["TEST_DIR"]
    test_cwd = os.path.abspath(TEST_DIR)
    host = CONFIG["ENV"]["HOST_IP"]

    if not run_all and ("/" in test_name or ".." in test_name):
        return "Invalid test name"

    if run_all:
        selected_test = "all"
        script = None
        scripts = sorted(f for f in os.listdir(test_cwd) if f.endswith(".sh"))
        if not scripts:
            return f"Test script not found in: {test_cwd}"
    else:
        selected_test = test_name
        script = os.path.join(test_cwd, test_name)
        if not os.path.exists(script):
            return f"Test script not found: {test_name}"

    test_run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run_dir = os.path.abspath(os.path.join(get_test_log_root(), "runs", test_run_id))
    run_dir_rel = os.path.relpath(run_dir, test_cwd)
    os.makedirs(run_dir, exist_ok=True)
    log_file = os.path.join(run_dir, "test.log")
    log_file_rel = os.path.join(run_dir_rel, "test.log")
    status_file = os.path.join(run_dir, "status.json")
    status_file_rel = os.path.join(run_dir_rel, "status.json")
    proc_env = os.environ.copy()
    if run_all:
        response_log_dir = os.path.join(run_dir_rel, "responses")
        response_log_file = None
    else:
        response_log_dir = run_dir_rel
        response_log_name = f"{os.path.splitext(test_name)[0]}.log"
        response_log_file = os.path.join(run_dir_rel, response_log_name)
        proc_env["TEST_LOG_FILE"] = response_log_file

    if run_all:
        tests = {
            name: {
                "status": "pending",
                "pid": None,
                "port": (
                    CONFIG["PORTS"]["DATA_ANNOTATION_PORT"]
                    if name == "case2chat.sh"
                    else CONFIG["PORTS"]["INFERENCE_PORT"]
                ),
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "log_file": os.path.join(
                    response_log_dir, f"{os.path.splitext(name)[0]}.log"
                ),
            }
            for name in scripts
        }
    else:
        port = (
            CONFIG["PORTS"]["INFERENCE_PORT"]
            if test_name != "case2chat.sh"
            else CONFIG["PORTS"]["DATA_ANNOTATION_PORT"]
        )
        popen_args = ["bash", os.path.basename(script), host, str(port)]

    with open(log_file, "a") as f:
        f.write(f"\n===== Test Run: {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        f.write(f"===== Running {selected_test} =====\n")
        if not run_all:
            proc = subprocess.Popen(
                popen_args,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=proc_env,
                cwd=test_cwd,
                start_new_session=True,
            )

    meta = {
        "test_run_id": test_run_id,
        "status": "running",
        "script_pid": None if run_all else proc.pid,
        "controller_pid": os.getpid() if run_all else None,
        "test_name": selected_test,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "exit_code": None,
        "log_file": log_file_rel,
        "response_log_dir": response_log_dir,
        "response_log_file": response_log_file,
        "status_file": status_file_rel,
        "service_instance_id": resolved_instance_id,
        "service_run_id": instance_meta.get("run_id"),
        "owner_user_id": instance_meta.get("owner_user_id") or current_request_user_id(),
        "service_ports": instance_ports_from_runtime_config(CONFIG),
    }
    if run_all:
        meta["tests"] = tests
    atomic_write_json(status_file, meta)
    atomic_write_json(
        get_test_latest_path(),
        {
            "test_run_id": test_run_id,
            "status_file": status_file,
        },
    )
    if run_all:
        threading.Thread(
            target=run_all_test_job,
            args=(
                scripts,
                host,
                CONFIG["PORTS"],
                test_cwd,
                status_file,
                log_file,
                response_log_dir,
            ),
            daemon=True,
        ).start()
    else:
        threading.Thread(
            target=monitor_test_job,
            args=(test_run_id, proc, status_file),
            daemon=True,
        ).start()

    return (
        "测试任务已提交，正在后台运行。\n"
        f"test_run_id: {test_run_id}\n"
        f"service_instance_id: {resolved_instance_id}\n"
        f"test_name: {selected_test}\n"
        f"script_pid: {None if run_all else proc.pid}\n"
        f"log_file: {format_agent_relative_path(log_file)}\n"
        "可调用 service_test_status(test_run_id) 查看测试状态。"
    )


def test_status_text(
    test_run_id: str = "latest",
    lines: int = 30,
    instance_id: str = "",
    limit: int = DEFAULT_LIST_LIMIT,
    scope: str = "mine",
) -> str:
    if test_run_id == "all":
        return running_tests_text(instance_id, limit, scope)
    scope = str(scope or "mine").strip().lower()
    if scope not in {"mine", "all"}:
        return "Invalid scope. Use mine or all."

    try:
        test_run_id = resolve_test_run_id(test_run_id, scope)
    except FileNotFoundError as e:
        return str(e)

    try:
        status_file = get_test_status_path(test_run_id)
    except ValueError:
        return "Invalid test_run_id"

    if not os.path.exists(status_file):
        return f"测试状态文件不存在: {status_file}"

    with open(status_file, "r") as f:
        meta = json.load(f)
    meta = refresh_test_run_meta(test_run_id, status_file, meta)
    if not task_visible_for_scope(meta, scope):
        return (
            "该功能测试任务属于其他用户，默认不显示。\n"
            f"test_run_id={test_run_id}\n"
            "如需只读查看全部任务，请使用 scope=all。"
        )

    script_pid = int(meta.get("script_pid") or 0)
    script_running = is_process_running(script_pid) if script_pid else False
    status_value = meta.get("status", "unknown")
    if status_value == "running" and not script_running and not meta.get("tests"):
        status_value = "unknown_finished"

    test_lines = []
    tests = meta.get("tests") or {}
    if tests:
        status_counts = {}
        for item in tests.values():
            item_status = item.get("status", "unknown")
            status_counts[item_status] = status_counts.get(item_status, 0) + 1
        test_lines = [
            "",
            "脚本统计:",
            f"total={len(tests)}",
            f"finished={status_counts.get('finished', 0)}",
            f"running={status_counts.get('running', 0)}",
            f"pending={status_counts.get('pending', 0)}",
            f"failed={status_counts.get('failed', 0)}",
            f"stopped={status_counts.get('stopped', 0)}",
            "",
            "各脚本状态:",
        ]
        for name, item in tests.items():
            test_lines.append(
                "- "
                f"{name}: status={item.get('status')}, "
                f"pid={item.get('pid')}, "
                f"port={item.get('port')}, "
                f"exit_code={item.get('exit_code')}, "
                f"log_file={format_test_path(item.get('log_file'))}"
            )

    response_log_file = meta.get("response_log_file")
    log_file = meta.get("log_file")

    return safe_output(
        "\n".join(
            [
                "功能测试状态:",
                f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"status={status_value}",
                f"stored_status={meta.get('status')}",
                f"test_run_id={meta.get('test_run_id', test_run_id)}",
                f"test_name={meta.get('test_name')}",
                f"owner={task_owner_label(meta)}",
                f"service_instance_id={meta.get('service_instance_id', '')}",
                f"service_run_id={meta.get('service_run_id', '')}",
                f"script_pid={script_pid}",
                f"script_running={script_running}",
                f"exit_code={meta.get('exit_code')}",
                f"started_at={meta.get('started_at')}",
                f"finished_at={meta.get('finished_at')}",
                f"log_file={format_test_path(log_file)}",
                f"response_log_dir={format_test_path(meta.get('response_log_dir'))}",
                f"response_log_file={format_test_path(response_log_file)}",
                *test_lines,
            ]
        )
    )


def test_run_is_active(meta: dict) -> bool:
    if meta.get("status") != "running":
        return False
    tests = meta.get("tests") or {}
    if tests:
        for item in tests.values():
            if item.get("status") == "running" and pid_is_alive(item.get("pid")):
                return True
        return False
    script_pid = int(meta.get("script_pid") or 0)
    return bool(script_pid and pid_is_alive(script_pid))


def stop_test_run_runtime(test_run_id: str, status_file: str, meta: dict) -> str:
    """Stop one test run after the caller has completed authorization checks."""
    with json_file_lock(status_file):
        meta = load_json_file(status_file, {})
        status = meta.get("status")
        script_pid = int(meta.get("script_pid") or 0)
        if status != "running":
            return (
                f"测试任务无需停止: status={status}, test_run_id={test_run_id}, "
                f"log_file={format_test_path(meta.get('log_file'))}"
            )

        tests = meta.get("tests") or {}
        stopped_pid = None
        if tests:
            for item in tests.values():
                if item.get("status") == "running" and item.get("pid"):
                    stopped_pid = int(item["pid"])
                    try:
                        os.killpg(os.getpgid(stopped_pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    except Exception as e:
                        return (
                            f"停止测试失败: test_run_id={test_run_id}, "
                            f"pid={stopped_pid}, error={e}"
                        )
                    break
            mark_remaining_tests(tests, "stopped")
        elif script_pid and is_process_running(script_pid):
            try:
                os.killpg(os.getpgid(script_pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as e:
                return (
                    f"停止测试失败: test_run_id={test_run_id}, "
                    f"pid={script_pid}, error={e}"
                )

        meta["status"] = "stopped"
        meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["exit_code"] = None
        atomic_write_json(status_file, meta)

    if tests:
        return (
            f"测试任务已停止: test_run_id={test_run_id}, pid={stopped_pid}\n"
            f"log_file={format_test_path(meta.get('log_file'))}"
        )
    if not script_pid or not is_process_running(script_pid):
        return f"测试进程已不存在，状态已标记为 stopped: test_run_id={test_run_id}"
    return (
        f"测试任务已停止: test_run_id={test_run_id}, pid={script_pid}\n"
        f"log_file={format_test_path(meta.get('log_file'))}"
    )


def test_stop_text(
    test_run_id: str = "latest", confirm: bool = False, scope: str = "mine"
) -> str:
    try:
        test_run_id = resolve_test_run_id(test_run_id, scope)
        status_file = get_test_status_path(test_run_id)
    except FileNotFoundError as e:
        return str(e)
    except ValueError:
        return "Invalid test_run_id"

    if not os.path.exists(status_file):
        return f"测试状态文件不存在: {status_file}"

    with open(status_file, "r") as f:
        meta = json.load(f)
    meta = refresh_test_run_meta(test_run_id, status_file, meta)

    status = meta.get("status")
    owner = task_owner_user_id(meta)
    current = current_request_user_id()
    if not current:
        return "当前请求缺少用户身份，已拒绝停止功能测试任务。"
    if not owner:
        return (
            "该功能测试任务没有有效的所有者记录，已拒绝停止。\n"
            f"test_run_id={test_run_id}"
        )
    if owner != current:
        return (
            "该功能测试任务属于其他用户，已拒绝停止。\n"
            f"test_run_id={test_run_id}\n"
            f"status={status}\n"
            "普通工具只允许停止当前用户自己的功能测试任务。"
        )

    return stop_test_run_runtime(test_run_id, status_file, meta)


def start_single_test(test_name: str, instance_id: str = "latest") -> str:
    """Run a specific test script."""
    return start_test_job(test_name=test_name, run_all=False, instance_id=instance_id)


def start_all_tests(instance_id: str = "latest") -> str:
    """Run all test scripts in test directory."""
    return start_test_job(run_all=True, instance_id=instance_id)


def restart_service_stack() -> str:
    """Restart the current user's latest inference service instance."""
    stop_result = stop_service()
    if any(
        marker in stop_result
        for marker in (
            "暂不能自动选择",
            "暂不停止",
            "已拒绝",
            "不能停止",
        )
    ):
        return f"停止结果:\n{stop_result}\n\n未继续重新启动。"
    time.sleep(10)
    start_result = start_service()
    return f"停止结果:\n{stop_result}\n\n重新启动结果:\n{start_result}"


def flatten_config_keys(d, prefix=""):
    """Flatten nested config dict into dot-separated key paths."""
    keys = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(flatten_config_keys(v, full))
        else:
            keys.append(full)
    return keys


def update_config(key: str, value: str) -> dict:
    """Update current user's draft service config value."""
    if not current_request_user_id():
        return "当前请求缺少 user_id，拒绝修改全局配置。"
    config_path = ensure_user_draft_config()
    cfg = show_config()
    current = cfg
    parts = key.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
        if not isinstance(current, dict):
            return f"Invalid key path: {key}"
    old_value = current.get(parts[-1])
    new_value = value
    if isinstance(old_value, bool):
        new_value = str(value).strip().lower() in {"1", "true", "yes", "on"}
    elif isinstance(old_value, int) and not isinstance(old_value, bool):
        try:
            new_value = int(value)
        except (TypeError, ValueError):
            return f"Invalid integer value for {key}: {value}"
    elif isinstance(old_value, float):
        try:
            new_value = float(value)
        except (TypeError, ValueError):
            return f"Invalid float value for {key}: {value}"
    current[parts[-1]] = new_value
    write_user_draft_config(config_path, cfg)

    user_id = current_request_user_id()
    if user_id:
        meta_path = get_user_config_meta_path(user_id)
        meta = load_json_file(meta_path, {})
        if not isinstance(meta, dict):
            meta = {}
        meta.update(
            {
                "user_id": user_id,
                "user_key": user_config_key(user_id),
                "source_config": CONFIG_FILE,
                "draft_config": config_path,
                "updated_at": current_time_text(),
            }
        )
        if "created_at" not in meta:
            meta["created_at"] = current_time_text()
        atomic_write_json(meta_path, meta)

    return f"更新当前用户配置草稿 {config_path}: .{key} = {new_value}"


def get_config_value(cfg: dict, key: str):
    current = cfg
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def config_value_equal(current, value) -> bool:
    if isinstance(current, (int, float)) and str(value).strip():
        try:
            return float(current) == float(value)
        except ValueError:
            return False
    return str(current) == str(value)


def restore_default_config() -> str:
    """Restore current user's draft config from default backup."""
    user_id = current_request_user_id()
    if not user_id:
        return "当前请求缺少 user_id，拒绝恢复全局配置。"
    draft_path = get_user_draft_config_path(user_id)
    os.makedirs(os.path.dirname(draft_path), exist_ok=True)
    with open(DEFAULT_CONFIG_FILE) as f:
        cfg = yaml.safe_load(f) or {}
    write_user_draft_config(draft_path, cfg)
    atomic_write_json(
        get_user_config_meta_path(user_id),
        {
            "user_id": user_id,
            "user_key": user_config_key(user_id),
            "source_config": DEFAULT_CONFIG_FILE,
            "draft_config": draft_path,
            "created_at": current_time_text(),
            "updated_at": current_time_text(),
        },
    )
    return f"当前用户配置草稿已恢复默认: {draft_path}"


def model_list_text() -> str:
    """List all available models."""
    CONFIG = show_config()
    return run_command(f"ls {CONFIG['ENV']['MODEL_PATH']}")


def list_medical_choice_benchmarks() -> str:
    """List medical choice benchmark datasets."""
    dataset_dir = get_medical_choice_dir()

    if not os.path.exists(dataset_dir):
        return f"[ERROR]: Dataset directory not found: {dataset_dir}"

    files = sorted(f for f in os.listdir(dataset_dir) if f.endswith(".json"))
    if not files:
        return "医疗选择题数据集目录为空。"

    return "医疗选择题数据集:\n" + "\n".join(f"  - {f}" for f in files)


def get_general_benchmark_dir() -> str:
    cfg = show_config()
    return cfg["ENV"].get("GENERAL_BENCHMARK_DIR", "../benchmark/general")


def get_medical_benchmark_dir() -> str:
    cfg = show_config()
    return cfg["ENV"]["BENCHMARK_DIR"]


def get_benchmark_log_dir() -> str:
    return os.path.join(get_service_log_root(), "benchmark")


def get_medical_choice_dir() -> str:
    return os.path.join(get_medical_benchmark_dir(), "choice")


def get_medbench_dir() -> str:
    return os.path.join(get_medical_benchmark_dir(), "medbench")


def get_general_runner_path() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../benchmark/general_runner.py")
    )


def run_general_runner(args: list[str]) -> str:
    cmd = [sys.executable, get_general_runner_path(), *args]
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as e:
        return f"[ERROR]\n{e.output.decode()}"


def resolve_benchmark_path(base_dir: str, relative_path: str) -> str:
    """Resolve a user-provided benchmark path under a configured benchmark dir."""
    base = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base, relative_path))

    if target != base and not target.startswith(base + os.sep):
        raise ValueError("Invalid benchmark path")

    return target


def format_dataset_candidates(files: list[str], query: str, limit: int = 40) -> str:
    query = query.strip().lower()
    matches = [f for f in files if query and query in f.lower()]
    shown = matches or files
    shown = shown[:limit]
    if not shown:
        return "当前目录下没有可用数据集。"
    lines = ["可用候选:"]
    lines.extend(f"- {f}" for f in shown)
    if len(files) > len(shown):
        lines.append(f"... 还有 {len(files) - len(shown)} 个")
    return "\n".join(lines)


def resolve_medical_choice_dataset_path(
    dataset: str, benchmark_dir: Optional[str] = None
) -> str:
    benchmark_dir = benchmark_dir or get_medical_benchmark_dir()
    dataset = dataset.strip()
    if dataset.startswith("medical/choice/"):
        dataset = dataset.split("/", 2)[2]
    if dataset.startswith("medical_choice/"):
        dataset = dataset.split("/", 1)[1]
    if dataset.startswith("choice/"):
        dataset = dataset.split("/", 1)[1]

    relative = os.path.join("choice", dataset)
    path = resolve_benchmark_path(benchmark_dir, relative)
    if os.path.exists(path) or dataset.endswith(".json"):
        return path

    return resolve_benchmark_path(benchmark_dir, relative + ".json")


def medical_choice_candidates(dataset: str, benchmark_dir: Optional[str] = None) -> str:
    choice_dir = (
        os.path.join(benchmark_dir, "choice")
        if benchmark_dir
        else get_medical_choice_dir()
    )
    if not os.path.isdir(choice_dir):
        return f"医疗选择题目录不存在: {choice_dir}"
    files = sorted(f for f in os.listdir(choice_dir) if f.endswith(".json"))
    return format_dataset_candidates(files, dataset)


def medbench_candidates(dataset: str, benchmark_dir: Optional[str] = None) -> str:
    medbench_dir = (
        os.path.join(benchmark_dir, "medbench")
        if benchmark_dir
        else get_medbench_dir()
    )
    if not os.path.isdir(medbench_dir):
        return f"MedBench目录不存在: {medbench_dir}"
    files = sorted(f for f in os.listdir(medbench_dir) if f.endswith(".jsonl"))
    return format_dataset_candidates(files, dataset)


def is_process_running(pid: int) -> bool:
    """Check if the process is running and not a zombie."""
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def monitor_job(job_id: str, proc: subprocess.Popen, meta_path: str):
    """Background thread checks if the job is finished."""
    return_code = proc.wait()

    try:
        with open(meta_path, "r") as f:
            meta = json.load(f)
    except Exception:
        return

    if meta.get("status") != "running":
        return

    meta["status"] = "finished" if return_code == 0 else "failed"
    meta["return_code"] = return_code
    meta["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    atomic_write_json(meta_path, meta)


def make_benchmark_job_paths(output_name: str = "result.json", output_is_dir: bool = False) -> dict:
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"
    job_dir = os.path.join(get_benchmark_log_dir(), job_id)
    os.makedirs(job_dir, exist_ok=True)

    output_path = os.path.join(job_dir, output_name)
    if output_is_dir:
        os.makedirs(output_path, exist_ok=True)

    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "meta_file": os.path.join(job_dir, "meta.json"),
        "log_file": os.path.join(job_dir, "run.log"),
        "output": output_path,
        "start_time": start_time,
    }


def start_benchmark_process(cmd: list[str], log_file: str) -> subprocess.Popen:
    log_f = open(log_file, "w")
    return subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def benchmark_service_meta(
    resolved_instance_id: str, cfg: dict, instance_meta: dict
) -> dict:
    return {
        "owner_user_id": instance_meta.get("owner_user_id") or current_request_user_id(),
        "service_instance_id": resolved_instance_id,
        "service_run_id": instance_meta.get("run_id"),
        "service_ports": instance_ports_from_runtime_config(cfg),
    }


def benchmark_submit_key(
    instance_id: str, benchmark_type: str, dataset: str, split: str
) -> str:
    normalized = [
        str(instance_id or "").strip(),
        normalize_benchmark_type(benchmark_type),
        str(dataset or "").strip().lower(),
        str(split or "default").strip().lower(),
    ]
    return "|".join(normalized)


def benchmark_submit_lock_path(submit_key: str) -> str:
    lock_dir = os.path.join(get_benchmark_log_dir(), "submit_locks")
    os.makedirs(lock_dir, exist_ok=True)
    name = hashlib.sha1(submit_key.encode("utf-8")).hexdigest()
    return os.path.join(lock_dir, f"{name}.json")


def benchmark_duplicate_message(meta: dict) -> str:
    return (
        "检测到相同 benchmark 任务已存在，已跳过重复提交。\n"
        f"job_id={meta.get('job_id')}\n"
        f"status={meta.get('status')}\n"
        f"dataset={meta.get('dataset')}\n"
        f"service_instance_id={meta.get('service_instance_id')}\n"
        f"log_file={format_agent_relative_path(meta.get('log', ''))}\n"
        f"output={format_agent_relative_path(meta.get('output', ''))}\n"
        "可调用 benchmark_report(job_id) 查看进度和结果。"
    )


def benchmark_submit_lock_message(lock: dict) -> str:
    return (
        "检测到相同 benchmark 任务正在提交中，已跳过重复提交。\n"
        f"dataset={lock.get('dataset')}\n"
        f"benchmark_type={lock.get('benchmark_type')}\n"
        f"split={lock.get('split')}\n"
        f"service_instance_id={lock.get('instance_id')}\n"
        f"created_at={lock.get('created_at')}\n"
        "请稍后调用 benchmark_jobs 或 benchmark_report 查看任务。"
    )


def find_existing_benchmark_submit(submit_key: str) -> Optional[dict]:
    base = get_benchmark_log_dir()
    for job_id, meta_path, meta in iter_json_records(base, "meta.json"):
        if str(meta.get("submit_key") or "") != submit_key:
            continue
        meta = refresh_benchmark_job_meta(job_id, meta_path, meta)
        status = str(meta.get("status") or "").lower()
        if status in {"running", "submitting"}:
            return meta
    return None


def acquire_benchmark_submit_lock(
    submit_key: str,
    dataset: str,
    benchmark_type: str,
    split: str,
    instance_id: str,
) -> tuple[bool, str]:
    existing = find_existing_benchmark_submit(submit_key)
    if existing:
        return False, benchmark_duplicate_message(existing)

    lock_path = benchmark_submit_lock_path(submit_key)
    now = time.time()
    payload = {
        "submit_key": submit_key,
        "dataset": dataset,
        "benchmark_type": benchmark_type,
        "split": split,
        "instance_id": instance_id,
        "owner_user_id": current_request_user_id(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_ts": now,
    }
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            with open(lock_path, "r") as f:
                lock = json.load(f)
            created_ts = float(lock.get("created_ts") or 0)
        except Exception:
            created_ts = 0
            lock = {}
        if created_ts and now - created_ts < BENCHMARK_SUBMIT_LOCK_TTL:
            return False, benchmark_submit_lock_message(lock)
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass
        return acquire_benchmark_submit_lock(
            submit_key, dataset, benchmark_type, split, instance_id
        )

    with os.fdopen(fd, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return True, ""


def release_benchmark_submit_lock(submit_key: str):
    try:
        os.remove(benchmark_submit_lock_path(submit_key))
    except FileNotFoundError:
        pass


def run_medical_choice_benchmark(
    dataset: str,
    max_workers: int = 5,
    save_every: int = 2,
    instance_id: str = "latest",
    submit_key: str = "",
    instance_context: Optional[tuple[str, dict, dict]] = None,
) -> str:
    """Start a benchmark evaluation job (runs asynchronously in the background)."""

    instance_config = instance_context or require_running_service_instance_config(
        instance_id
    )
    if isinstance(instance_config, str):
        return instance_config
    resolved_instance_id, cfg, instance_meta = instance_config

    model = cfg["ENV"]["MODEL_NAME"]
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"
    dataset_path = resolve_medical_choice_dataset_path(dataset, benchmark_dir)

    if not os.path.exists(dataset_path):
        return (
            f"Benchmark dataset not found: {dataset}\n"
            + medical_choice_candidates(dataset, benchmark_dir)
        )
    if not os.path.isfile(dataset_path):
        return f"Benchmark dataset is not a file: {dataset}"

    job = make_benchmark_job_paths()
    job_id = job["job_id"]
    meta_file = job["meta_file"]
    log_file = job["log_file"]
    output_file = job["output"]

    cmd = [
        sys.executable,
        "-u",
        # f"{benchmark_dir}/eval_runner.py",
        "../benchmark/eval_runner.py",
        "--mode",
        "eval",
        "--base-url",
        base_url,
        "--model",
        model,
        "--dataset",
        dataset_path,
        "--output",
        output_file,
        "--max-workers",
        str(max_workers),
        "--save-every",
        str(save_every),
    ]
    proc = start_benchmark_process(cmd, log_file)

    pid = proc.pid

    meta = {
        "job_id": job_id,
        "pid": pid,
        "model": model,
        "dataset": dataset,
        "submit_key": submit_key,
        **benchmark_service_meta(resolved_instance_id, cfg, instance_meta),
        "mode": "eval",
        "log": log_file,
        "output": output_file,
        "start_time": job["start_time"],
        "status": "running",
        "return_code": None,
        "end_time": "",
    }
    atomic_write_json(meta_file, meta)

    threading.Thread(
        target=monitor_job, args=(job_id, proc, meta_file), daemon=True
    ).start()

    return (
        "Benchmark任务已启动:\n"
        f"job_id={job_id}\n"
        f"pid={pid}\n"
        f"model={model}\n"
        f"dataset={dataset}\n"
        f"service_instance_id={resolved_instance_id}\n"
        "benchmark_type=medical_choice\n"
        f"log_file={format_agent_relative_path(log_file)}\n"
        f"output={format_agent_relative_path(output_file)}\n"
        "可调用 benchmark_report(job_id) 查看进度和结果。"
    )


def list_benchmark_jobs_text(
    instance_id: str = "", limit: int = DEFAULT_LIST_LIMIT, scope: str = "mine"
) -> str:
    """List all benchmark jobs with their current status."""

    base = get_benchmark_log_dir()
    limit = clamp_int(limit, DEFAULT_LIST_LIMIT, 1, MAX_LIST_LIMIT)
    scope = str(scope or "mine").strip().lower()
    if scope not in {"mine", "all"}:
        return "Invalid scope. Use mine or all."
    resolved_instance_id = ""
    if instance_id:
        access_error = (
            service_instance_access_error(instance_id, "查看 benchmark 任务")
            if scope != "all"
            else ""
        )
        if access_error:
            return access_error
        resolved_instance_id = resolve_service_instance_id(
            instance_id, scope=scope, require_running=False
        )
        if not resolved_instance_id:
            return f"未找到推理服务实例: {instance_id}"

    jobs = []

    for job_id, meta_path, meta in iter_json_records(base, "meta.json"):
        meta = refresh_benchmark_job_meta(job_id, meta_path, meta)
        if (
            resolved_instance_id
            and str(meta.get("service_instance_id") or "") != resolved_instance_id
        ):
            continue
        if not task_visible_for_scope(meta, scope):
            continue
        start_time = meta.get("start_time", "")
        sort_time = parse_time_sort_value(start_time)
        if not sort_time:
            sort_time = parse_time_sort_value(meta.get("job_id", job_id))
        if not sort_time:
            sort_time = os.path.getmtime(meta_path)
        jobs.append((sort_time, status_sort_rank(meta.get("status")), meta))

    lock_dir = os.path.join(base, "submit_locks")
    if os.path.isdir(lock_dir):
        now = time.time()
        for filename in os.listdir(lock_dir):
            if not filename.endswith(".json"):
                continue
            lock_path = os.path.join(lock_dir, filename)
            lock = load_json_file(lock_path, {})
            if not isinstance(lock, dict):
                continue
            try:
                created_ts = float(lock.get("created_ts") or 0)
            except (TypeError, ValueError):
                created_ts = 0
            if created_ts and now - created_ts >= BENCHMARK_SUBMIT_LOCK_TTL:
                try:
                    os.remove(lock_path)
                except FileNotFoundError:
                    pass
                continue
            if (
                resolved_instance_id
                and str(lock.get("instance_id") or "") != resolved_instance_id
            ):
                continue
            if not task_visible_for_scope(lock, scope):
                continue
            lock_id = os.path.splitext(filename)[0][:12]
            meta = {
                "job_id": f"submitting:{lock_id}",
                "model": "",
                "dataset": lock.get("dataset", ""),
                "status": "submitting",
                "owner_user_id": lock.get("owner_user_id", ""),
                "service_instance_id": lock.get("instance_id", ""),
                "output": "",
                "start_time": lock.get("created_at", ""),
            }
            sort_time = created_ts or os.path.getmtime(lock_path)
            jobs.append((sort_time, status_sort_rank("submitting"), meta))

    if not jobs:
        if resolved_instance_id:
            return f"该实例暂无 benchmark 任务: instance_id={resolved_instance_id}"
        return "暂无当前用户的 benchmark 任务。" if scope == "mine" else "暂无任务"

    sorted_jobs = sorted(
        jobs, key=lambda item: (-item[0], item[1], str(item[2].get("job_id", "")))
    )
    visible_jobs = sorted_jobs[:limit]
    lines = [
        f"Benchmark任务列表(scope={scope}): 显示 {len(visible_jobs)} / {len(sorted_jobs)} 条，limit={limit}"
    ]
    if scope == "all":
        owner_counts = {"self": 0, "other": 0, "unknown": 0}
        for _, _, meta in sorted_jobs:
            owner = task_owner_label(meta)
            owner_counts[owner if owner in owner_counts else "unknown"] += 1
        lines.append(
            "owner统计: "
            f"self={owner_counts['self']}, "
            f"other={owner_counts['other']}, "
            f"unknown={owner_counts['unknown']}"
        )
    if len(sorted_jobs) > limit:
        lines.append(f"还有 {len(sorted_jobs) - limit} 条未显示，可增大 limit 查看。")

    for idx, (_, _, meta) in enumerate(
        visible_jobs,
        start=1,
    ):
        latest = " latest_by_time" if idx == 1 else ""
        lines.append(
            f"#{idx}{latest} | {meta.get('job_id')} | {meta.get('start_time', '')} | "
            f"{meta.get('model')} | {meta.get('dataset')} | {meta.get('status')} | "
            f"owner={task_owner_label(meta)} | "
            f"instance={meta.get('service_instance_id', '')} | "
            f"output={format_agent_relative_path(meta.get('output', ''))}"
        )

    return "\n".join(lines)


def stop_benchmark_job_runtime(job_id: str, meta_file: str, meta: dict) -> str:
    """Stop one benchmark after the caller has completed authorization checks."""
    pid = int(meta.get("pid") or 0)
    if meta.get("status") != "running":
        return (
            f"benchmark任务无需停止: status={meta.get('status')}, job_id={job_id}, "
            f"pid={pid}, output={format_agent_relative_path(meta.get('output', ''))}"
        )

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)

        meta["status"] = "stopped"
        meta["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

        if "progress" in meta and "files" in meta["progress"]:
            for file_stat in meta["progress"]["files"].values():
                if file_stat.get("status") == "running":
                    file_stat["status"] = "stopped"

        atomic_write_json(meta_file, meta)
        return f"stopped successfully: job_id={job_id} pid={pid}"
    except ProcessLookupError:
        meta = refresh_benchmark_job_meta(job_id, meta_file, meta)
        return (
            "benchmark进程已不存在，状态已同步: "
            f"status={meta.get('status')}, job_id={job_id}, pid={pid}"
        )
    except Exception as exc:
        return f"error: {exc}"


def stop_benchmark_job(job_id: str, confirm: bool = False) -> str:
    """Stop a running benchmark job."""

    job_dir = os.path.join(get_benchmark_log_dir(), job_id)
    meta_file = os.path.join(job_dir, "meta.json")

    if not os.path.exists(meta_file):
        return f"not found: {meta_file}"

    with open(meta_file, "r") as f:
        meta = refresh_benchmark_job_meta(job_id, meta_file, json.load(f))
    pid = int(meta.get("pid") or 0)
    owner = task_owner_user_id(meta)
    current = current_request_user_id()
    if not current:
        return "当前请求缺少用户身份，已拒绝停止 benchmark 任务。"
    if not owner:
        return (
            "该 benchmark 任务没有有效的所有者记录，已拒绝停止。\n"
            f"job_id={job_id}"
        )
    if owner != current:
        return (
            "该 benchmark 任务属于其他用户，已拒绝停止。\n"
            f"job_id={job_id}\n"
            f"status={meta.get('status', '')}\n"
            "普通工具只允许停止当前用户自己的 benchmark 任务。"
        )

    if meta.get("status") != "running":
        return (
            f"benchmark任务无需停止: status={meta.get('status')}, job_id={job_id}, "
            f"pid={pid}, output={format_agent_relative_path(meta.get('output', ''))}"
        )
    return stop_benchmark_job_runtime(job_id, meta_file, meta)


def medbench_list():
    """List available MedBench datasets and jsonl files."""

    dataset_dir = get_medbench_dir()

    if not os.path.exists(dataset_dir):
        return f"[ERROR]: Dataset directory not found: {dataset_dir}."

    try:
        files = [f for f in os.listdir(dataset_dir) if f.endswith(".jsonl")]
    except Exception as e:
        return f"[ERROR]: Failed to list dataset: {str(e)}."

    files.sort()

    if not files:
        return "medical/medbench/ (empty)"

    lines = []
    lines.append(f"medical/medbench/ (共 {len(files)} 个文件):")

    for f in files:
        lines.append(f"  - {f}")

    return "\n".join(lines)


def inspect_json_samples(
    path: str, sample_limit: int = 3
) -> tuple[int, list[str], list]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        total = len(data)
        samples = data[:sample_limit]
    elif isinstance(data, dict):
        sample_list = next((v for v in data.values() if isinstance(v, list)), [])
        total = len(sample_list)
        samples = sample_list[:sample_limit] if sample_list else [data]
    else:
        total = 0
        samples = []

    sample = samples[0] if samples else {}
    fields = list(sample.keys()) if isinstance(sample, dict) else []
    return total, fields, samples


def inspect_jsonl_file(path: str, sample_limit: int = 3) -> tuple[int, list[str], list]:
    total = 0
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            if len(samples) < sample_limit:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    samples.append({"raw": line.strip()})

    sample = samples[0] if samples else {}
    fields = list(sample.keys()) if isinstance(sample, dict) else []
    return total, fields, samples


def inspect_medical_choice_dataset(dataset: str) -> str:
    path = resolve_medical_choice_dataset_path(dataset)
    if not os.path.isfile(path):
        return f"医疗选择题数据集不存在: {dataset}\n" + medical_choice_candidates(
            dataset
        )

    try:
        total, fields, samples = inspect_json_samples(path)
    except Exception as e:
        return f"医疗选择题数据集读取失败: {dataset}\npath={path}\nerror={e}"

    return json.dumps(
        {
            "dataset": dataset,
            "benchmark_type": "medical_choice",
            "path": path,
            "total": total,
            "fields": fields,
            "samples": samples,
        },
        ensure_ascii=False,
        indent=2,
    )


def inspect_medbench_dataset(dataset: str) -> str:
    try:
        path = resolve_medbench_dataset_path(get_medical_benchmark_dir(), dataset)
    except ValueError:
        return f"Invalid MedBench dataset path: {dataset}"
    if not os.path.exists(path):
        return (
            f"MedBench数据集不存在: {dataset}\n"
            "如果用户想查看 MedBench 整体结构，请使用 dataset=medical/medbench 或 dataset=medbench。\n"
            + medbench_candidates(dataset)
        )

    if os.path.isfile(path):
        try:
            total, fields, samples = inspect_jsonl_file(path)
        except Exception as e:
            return f"MedBench数据集读取失败: {dataset}\npath={path}\nerror={e}"
        return json.dumps(
            {
                "dataset": dataset,
                "benchmark_type": "medbench",
                "type": "file",
                "path": path,
                "total": total,
                "fields": fields,
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        )

    files = sorted(f for f in os.listdir(path) if f.endswith(".jsonl"))
    total = 0
    summaries = []
    fields = []
    for fname in files:
        file_path = os.path.join(path, fname)
        try:
            count, file_fields, _ = inspect_jsonl_file(file_path)
        except Exception:
            count, file_fields = 0, []
        total += count
        if not fields and file_fields:
            fields = file_fields
        if len(summaries) < 40:
            summaries.append({"file": fname, "total": count})

    return json.dumps(
        {
            "dataset": dataset,
            "benchmark_type": "medbench",
            "type": "directory",
            "path": path,
            "files": len(files),
            "total": total,
            "fields": fields,
            "file_summary": summaries,
            "truncated_files": max(0, len(files) - len(summaries)),
        },
        ensure_ascii=False,
        indent=2,
    )


def resolve_medbench_dataset_path(benchmark_dir: str, dataset: str) -> str:
    """Resolve MedBench dataset path with backward-compatible names."""
    dataset = dataset.strip()

    if dataset in ["MedBench_LLM", "medbench", "medical/medbench"]:
        relative = "medbench"
    elif dataset.startswith("MedBench_LLM/"):
        relative = os.path.join("medbench", dataset.split("/", 1)[1])
    elif dataset.startswith("medical/medbench/"):
        relative = os.path.join("medbench", dataset.split("/", 2)[2])
    elif "/" not in dataset:
        relative = os.path.join("medbench", dataset)
        path = resolve_benchmark_path(benchmark_dir, relative)
        if os.path.exists(path) or dataset.endswith(".jsonl"):
            return path
        return resolve_benchmark_path(benchmark_dir, relative + ".jsonl")
    else:
        relative = dataset

    return resolve_benchmark_path(benchmark_dir, relative)


def run_medbench_benchmark(
    dataset: str,
    max_workers: int = 5,
    instance_id: str = "latest",
    submit_key: str = "",
    instance_context: Optional[tuple[str, dict, dict]] = None,
) -> str:
    """Start a medbench evaluation job (runs asynchronously in the background)."""

    instance_config = instance_context or require_running_service_instance_config(
        instance_id
    )
    if isinstance(instance_config, str):
        return instance_config
    resolved_instance_id, cfg, instance_meta = instance_config

    model = cfg["ENV"]["MODEL_NAME"]
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"

    try:
        dataset_path = resolve_medbench_dataset_path(benchmark_dir, dataset)
    except ValueError:
        return f"Invalid dataset path: {dataset}"

    if not os.path.exists(dataset_path):
        return (
            f'Not Found: {dataset_path}. Please use `benchmark_list(benchmark_type="medbench")` to check available MedBench jsonl files, \
            or run the entire dataset: medical/medbench.\n'
            + medbench_candidates(dataset, benchmark_dir)
        )
    if dataset.endswith(".jsonl"):
        # dataset_type = "file"
        files = [os.path.basename(dataset_path)]
    else:
        # dataset_type = "folder"
        files = [f for f in os.listdir(dataset_path) if f.endswith(".jsonl")]

    job = make_benchmark_job_paths("results", output_is_dir=True)
    job_id = job["job_id"]
    meta_file = job["meta_file"]
    log_file = job["log_file"]
    output_dir = job["output"]

    cmd = [
        sys.executable,
        "-u",
        # f"{benchmark_dir}/eval_runner.py",
        "../benchmark/eval_runner.py",
        "--mode",
        "medbench",
        "--base-url",
        base_url,
        "--model",
        model,
        "--dataset",
        dataset_path,
        "--output",
        output_dir,
        "--max-workers",
        str(max_workers),
    ]
    proc = start_benchmark_process(cmd, log_file)

    pid = proc.pid

    meta = {
        "job_id": job_id,
        "pid": pid,
        "model": model,
        "mode": "medbench",
        "dataset": dataset,
        "submit_key": submit_key,
        **benchmark_service_meta(resolved_instance_id, cfg, instance_meta),
        "input_dir": dataset_path
        if os.path.isdir(dataset_path)
        else os.path.dirname(dataset_path),
        # "dataset_type": dataset_type,
        "files": files,
        "log": log_file,
        "output": output_dir,
        "start_time": job["start_time"],
        "status": "running",
        "return_code": None,
        "end_time": "",
    }
    atomic_write_json(meta_file, meta)

    threading.Thread(
        target=monitor_medbench_job, args=(job_id, proc, meta_file), daemon=True
    ).start()

    return (
        "MedBench任务已启动:\n"
        f"job_id={job_id}\n"
        f"pid={pid}\n"
        f"model={model}\n"
        f"dataset={dataset}\n"
        f"service_instance_id={resolved_instance_id}\n"
        "benchmark_type=medbench\n"
        f"log_file={format_agent_relative_path(log_file)}\n"
        f"output={format_agent_relative_path(output_dir)}\n"
        "可调用 benchmark_report(job_id) 查看进度和结果。"
    )


def monitor_medbench_job(job_id: str, proc: subprocess.Popen, meta_path: str):
    """Background thread: monitor job status + update progress."""

    last_progress_update = 0
    pid = proc.pid

    while True:
        now = time.time()

        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
        except:
            time.sleep(2)
            continue

        updated = False

        if now - last_progress_update > 5:
            if update_progress(meta):
                updated = True
            last_progress_update = now

        return_code = proc.poll()
        if return_code is not None:
            if meta.get("status") == "running":
                meta["status"] = "finished" if return_code == 0 else "failed"
                meta["return_code"] = return_code
                meta["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                updated = True

            update_progress(meta)

            if updated:
                atomic_write_json(meta_path, meta)

            break

        if updated:
            atomic_write_json(meta_path, meta)

        time.sleep(5)


def update_progress(meta: dict) -> bool:
    """Update meta['progress'] and return whether progress was updated."""

    files = meta.get("files", [])
    input_dir = meta.get("input_dir")
    output_dir = meta.get("output")

    if not files or not output_dir:
        return False

    cfg = show_config()
    benchmark_dir = get_medical_benchmark_dir()
    if not input_dir:
        dataset = meta.get("dataset", "").split("/")[0]
        input_dir = os.path.join(benchmark_dir, dataset)

    progress = meta.setdefault("progress", {})
    file_stats = progress.setdefault("files", {})

    changed = False
    completed_files = 0

    for f in files:
        input_path = os.path.join(input_dir, f)
        output_path = os.path.join(output_dir, f)

        stat = file_stats.setdefault(f, {"total": None, "done": 0, "status": "pending"})

        if stat["total"] is None:
            try:
                with open(input_path, "r", encoding="utf-8") as fin:
                    stat["total"] = sum(1 for _ in fin)
                changed = True
            except:
                stat["total"] = 0

        try:
            if os.path.exists(output_path):
                with open(output_path, "r", encoding="utf-8") as fout:
                    done = sum(1 for _ in fout)
            else:
                done = 0
        except:
            done = stat["done"]

        if done != stat["done"]:
            stat["done"] = done
            changed = True

        if stat["total"] > 0 and stat["done"] >= stat["total"]:
            if stat["status"] == "running":
                stat["status"] = "finished"
                changed = True
        else:
            if stat["status"] == "pending":
                stat["status"] = "running"
                changed = True

        if stat["status"] == "finished":
            completed_files += 1

    progress["total_files"] = len(files)
    progress["completed_files"] = completed_files

    return changed


def atomic_write_json(path: str, data: dict):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def medbench_progress_text(job_id: str) -> str:
    """Get MedBench job progress summary."""

    meta_file = os.path.join(get_benchmark_log_dir(), job_id, "meta.json")

    if not os.path.exists(meta_file):
        return f"未找到任务: {job_id}"

    with open(meta_file, "r") as f:
        meta = json.load(f)

    status = meta.get("status", "unknown")
    dataset = meta.get("dataset", "")
    model = meta.get("model", "")
    pid = meta.get("pid", "")
    return_code = meta.get("return_code")
    # dataset_type = meta.get("dataset_type", "")
    start_time = meta.get("start_time", "")
    end_time = meta.get("end_time", "")
    progress = meta.get("progress", {})
    files = progress.get("files", [])
    log = meta.get("log", "")
    output = meta.get("output", "")
    service_instance_id = meta.get("service_instance_id", "")
    service_run_id = meta.get("service_run_id", "")

    if not files:
        return f"""任务 {job_id}
状态: {status}
PID: {pid}
返回码: {return_code}
数据集: {dataset}
服务实例: {service_instance_id}
服务启动任务: {service_run_id}
日志位置: {format_agent_relative_path(log)}
结果位置: {format_agent_relative_path(output)}
（暂无进度信息）"""

    total_files = progress.get("total_files", len(files))
    completed_files = progress.get("completed_files", 0)

    total_samples = 0
    done_samples = 0

    running_files = []
    finished_files = []

    for fname, stat in files.items():
        total = stat.get("total", 0)
        done = stat.get("done", 0)

        total_samples += total
        done_samples += done

        if stat.get("status") == "running":
            running_files.append((fname, done, total))

        if stat.get("status") == "finished":
            finished_files.append((fname, done, total))

    percent = (done_samples / total_samples * 100) if total_samples > 0 else 0

    lines = []
    lines.append(f"任务: {job_id}")
    lines.append(f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"状态: {status}")
    lines.append(f"模型: {model}")
    lines.append(f"数据集: {dataset}")
    lines.append(f"服务实例: {service_instance_id}")
    lines.append(f"服务启动任务: {service_run_id}")
    lines.append(f"PID: {pid}")
    lines.append(f"返回码: {return_code}")
    lines.append(f"开始时间: {start_time}")
    lines.append(f"结束时间: {end_time}")
    lines.append(f"日志位置: {format_agent_relative_path(log)}")
    lines.append(f"结果位置: {format_agent_relative_path(output)}")
    lines.append(f"详细信息: {format_agent_relative_path(meta_file)}")
    lines.append(f"文件进度: {completed_files}/{total_files}")
    lines.append(f"样本进度: {done_samples}/{total_samples} ({percent:.1f}%)")
    # lines.append(f"开始时间: {start_time}")

    # if status == "finished":
    #    lines.append(f"结束时间: {end_time}")

    # if status == "stopped":
    #    lines.append(f"终止时间: {end_time}")

    if running_files:
        lines.append("\n运行中文件:")

        for fname, done, total in running_files[:]:
            p = (done / total * 100) if total > 0 else 0
            lines.append(f"- {fname}: {done}/{total} ({p:.1f}%)")

    if finished_files:
        lines.append("\n已完成文件:")

        for fname, done, total in finished_files[:]:
            p = (done / total * 100) if total > 0 else 0
            lines.append(f"- {fname}: {done}/{total} ({p:.1f}%)")

    return "\n".join(lines)


def medical_benchmark_list() -> str:
    """List medical choice and MedBench datasets."""
    lines = ["医疗评测数据集:"]
    lines.append("\n[medical_choice]")
    lines.append(list_medical_choice_benchmarks())
    lines.append("\n[medbench]")
    lines.append(medbench_list())
    return "\n".join(lines)


def general_benchmark_list() -> str:
    """List supported public benchmark datasets."""
    output = run_general_runner(
        [
            "--action",
            "list",
            "--dataset-root",
            get_general_benchmark_dir(),
        ]
    )
    return safe_output(output)


def general_benchmark_inspect(
    dataset: str, split: str = "default", dataset_root: Optional[str] = None
) -> str:
    """Inspect a supported public benchmark dataset."""
    output = run_general_runner(
        [
            "--action",
            "inspect",
            "--dataset-root",
            dataset_root or get_general_benchmark_dir(),
            "--dataset",
            dataset,
            "--split",
            split,
        ]
    )
    return safe_output(output)


def run_general_benchmark_job(
    dataset: str,
    split: str = "default",
    max_workers: int = 5,
    limit: Optional[int] = None,
    save_every: int = 2,
    instance_id: str = "latest",
    submit_key: str = "",
    instance_context: Optional[tuple[str, dict, dict]] = None,
) -> str:
    """Start a public benchmark job (runs asynchronously in the background)."""
    instance_config = instance_context or require_running_service_instance_config(
        instance_id
    )
    if isinstance(instance_config, str):
        return instance_config
    resolved_instance_id, cfg, instance_meta = instance_config

    model = cfg["ENV"]["MODEL_NAME"]
    general_dir = cfg["ENV"].get("GENERAL_BENCHMARK_DIR", "../benchmark/general")
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"

    if not os.path.exists(general_dir):
        return f"GENERAL_BENCHMARK_DIR not found: {general_dir}"

    inspect_output = general_benchmark_inspect(dataset, split, general_dir)
    if inspect_output.startswith("[ERROR]"):
        return inspect_output

    humaneval_executor = str(cfg["ENV"].get("HUMANEVAL_EXECUTOR", "docker"))
    humaneval_image = str(
        cfg["ENV"].get("HUMANEVAL_DOCKER_IMAGE", "qingnang-evaluator:local")
    )
    lcb_executor = str(cfg["ENV"].get("LCB_EXECUTOR", "record_only"))
    lcb_image = str(cfg["ENV"].get("LCB_DOCKER_IMAGE", "qingnang-evaluator:local"))
    if dataset.strip().lower() in {"humaneval", "human-eval"}:
        if humaneval_executor == "docker":
            try:
                subprocess.run(
                    ["docker", "image", "inspect", humaneval_image],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                    check=True,
                )
            except FileNotFoundError:
                return "Docker executor unavailable: docker command not found"
            except subprocess.TimeoutExpired:
                return f"Docker executor unavailable: image inspect timed out: {humaneval_image}"
            except subprocess.CalledProcessError as e:
                error = (e.stderr or e.stdout or "").strip()
                if "permission denied" in error.lower():
                    return (
                        "Docker executor unavailable: docker permission denied; "
                        "add the service user to the docker group"
                    )
                return f"Docker executor unavailable: Docker image not found: {humaneval_image}"
    job = make_benchmark_job_paths()
    job_id = job["job_id"]
    meta_file = job["meta_file"]
    log_file = job["log_file"]
    output_file = job["output"]

    cmd = [
        sys.executable,
        "-u",
        get_general_runner_path(),
        "--action",
        "run",
        "--base-url",
        base_url,
        "--model",
        model,
        "--dataset-root",
        general_dir,
        "--dataset",
        dataset,
        "--split",
        split,
        "--output",
        output_file,
        "--max-workers",
        str(max_workers),
        "--save-every",
        str(save_every),
        "--humaneval-executor",
        humaneval_executor,
        "--humaneval-docker-image",
        humaneval_image,
        "--humaneval-timeout",
        str(cfg["ENV"].get("HUMANEVAL_TIMEOUT", 5)),
        "--humaneval-memory",
        str(cfg["ENV"].get("HUMANEVAL_MEMORY", "512m")),
        "--humaneval-cpus",
        str(cfg["ENV"].get("HUMANEVAL_CPUS", 1)),
        "--humaneval-pids-limit",
        str(cfg["ENV"].get("HUMANEVAL_PIDS_LIMIT", 64)),
        "--lcb-executor",
        lcb_executor,
        "--lcb-docker-image",
        lcb_image,
        "--lcb-timeout",
        str(cfg["ENV"].get("LCB_TIMEOUT", 8)),
        "--lcb-num-process",
        str(cfg["ENV"].get("LCB_NUM_PROCESS", 1)),
        "--lcb-memory",
        str(cfg["ENV"].get("LCB_MEMORY", "1g")),
        "--lcb-cpus",
        str(cfg["ENV"].get("LCB_CPUS", 1)),
        "--lcb-pids-limit",
        str(cfg["ENV"].get("LCB_PIDS_LIMIT", 128)),
    ]
    if limit is not None and limit > 0:
        cmd.extend(["--limit", str(limit)])

    proc = start_benchmark_process(cmd, log_file)

    pid = proc.pid

    dataset_key = dataset.strip().lower().replace("_", "-")
    meta = {
        "job_id": job_id,
        "pid": pid,
        "model": model,
        "dataset": dataset,
        "submit_key": submit_key,
        "split": split,
        "mode": "general",
        **benchmark_service_meta(resolved_instance_id, cfg, instance_meta),
        "log": log_file,
        "output": output_file,
        "start_time": job["start_time"],
        "status": "running",
        "return_code": None,
        "end_time": "",
    }
    if dataset_key in {"humaneval", "human-eval"}:
        meta.update(
            {
                "humaneval_executor": humaneval_executor,
                "humaneval_docker_image": humaneval_image,
            }
        )
    elif dataset_key in {"livecodebench", "live-code-bench", "lcb"}:
        meta.update(
            {
                "lcb_executor": lcb_executor,
                "lcb_docker_image": lcb_image,
            }
        )

    atomic_write_json(meta_file, meta)

    threading.Thread(
        target=monitor_job, args=(job_id, proc, meta_file), daemon=True
    ).start()

    return (
        f"通用Benchmark任务已启动:\n"
        f"job_id={job_id}\n"
        f"pid={pid}\n"
        f"model={model}\n"
        f"dataset={dataset}\n"
        f"split={split}\n"
        f"service_instance_id={resolved_instance_id}\n"
        "benchmark_type=general\n"
        f"log_file={format_agent_relative_path(log_file)}\n"
        f"output={format_agent_relative_path(output_file)}\n"
        "任务已在后台运行。请先把 job_id 和输出路径告知用户；只有用户询问进度或结果时再调用 benchmark_report。"
    )


def normalize_benchmark_type(benchmark_type: str) -> str:
    value = (benchmark_type or "auto").strip().lower().replace("-", "_")
    aliases = {
        "medical": "medical_choice",
        "choice": "medical_choice",
        "medical_choice": "medical_choice",
        "medbench": "medbench",
        "medical_generation": "medbench",
        "generation": "medbench",
        "general": "general",
        "public": "general",
        "all": "all",
        "auto": "auto",
    }
    return aliases.get(value, value)


def infer_benchmark_type(
    dataset: str,
    split: str = "default",
    medical_dir: Optional[str] = None,
    general_dir: Optional[str] = None,
) -> str:
    name = dataset.strip()
    lowered = name.lower()

    if lowered.endswith(".jsonl") or "medbench" in lowered:
        return "medbench"
    if lowered.endswith(".json") or lowered.startswith(("medical/choice/", "medical_choice/", "choice/")):
        return "medical_choice"

    choice_path = resolve_medical_choice_dataset_path(name, medical_dir)
    if os.path.isfile(choice_path):
        return "medical_choice"

    inspect_output = general_benchmark_inspect(name, split, general_dir)
    if not inspect_output.startswith("[ERROR]"):
        return "general"

    try:
        medbench_path = resolve_medbench_dataset_path(
            medical_dir or get_medical_benchmark_dir(), name
        )
        if os.path.exists(medbench_path):
            return "medbench"
    except ValueError:
        pass

    return "unknown"


def correct_benchmark_type(
    dataset: str,
    benchmark_type: str,
    split: str = "default",
    medical_dir: Optional[str] = None,
    general_dir: Optional[str] = None,
):
    inferred = infer_benchmark_type(dataset, split, medical_dir, general_dir)
    if benchmark_type in {"auto", "unknown"}:
        return inferred, ""
    if inferred in {"medical_choice", "medbench"} and inferred != benchmark_type:
        return (
            inferred,
            f"note=benchmark_type={benchmark_type} 与数据集不匹配，已自动改为 {inferred}。\n",
        )
    return benchmark_type, ""


def benchmark_list_unified(benchmark_type: str = "all") -> str:
    """List benchmark datasets by type."""
    benchmark_type = normalize_benchmark_type(benchmark_type)
    if benchmark_type == "all":
        return "\n\n".join(
            [
                medical_benchmark_list(),
                "通用评测数据集:\n" + general_benchmark_list(),
            ]
        )
    if benchmark_type == "medical_choice":
        return list_medical_choice_benchmarks()
    if benchmark_type == "medbench":
        return medbench_list()
    if benchmark_type == "general":
        return general_benchmark_list()
    return "Unsupported benchmark_type. Use all, general, medical_choice, or medbench."


def benchmark_inspect_unified(
    dataset: str, benchmark_type: str = "auto", split: str = "default"
) -> str:
    """Inspect a benchmark dataset before running."""
    benchmark_type = normalize_benchmark_type(benchmark_type)
    benchmark_type, correction_note = correct_benchmark_type(
        dataset, benchmark_type, split
    )

    if benchmark_type == "general":
        return correction_note + general_benchmark_inspect(dataset, split)

    if benchmark_type == "medical_choice":
        return correction_note + inspect_medical_choice_dataset(dataset)

    if benchmark_type == "medbench":
        return correction_note + inspect_medbench_dataset(dataset)

    return (
        f"无法识别 benchmark_type: {benchmark_type}。"
        "请先调用 benchmark_list 查看可用数据集。"
    )


def benchmark_run_unified(
    dataset: str,
    benchmark_type: str = "auto",
    split: str = "default",
    max_workers: int = 5,
    limit: int = 0,
    save_every: int = 2,
    instance_id: str = "latest",
) -> str:
    """Run a benchmark job by unified type."""
    try:
        resolved_task_instance_id = resolve_task_service_instance_id(
            instance_id, "benchmark"
        )
    except ValueError as e:
        return str(e)
    if resolved_task_instance_id:
        instance_id = resolved_task_instance_id

    instance_config = require_running_service_instance_config(instance_id)
    if isinstance(instance_config, str):
        return instance_config
    resolved_instance_id, cfg, instance_meta = instance_config
    instance_context = (resolved_instance_id, cfg, instance_meta)
    ready_error = openai_api_ready_error(cfg, resolved_instance_id)
    if ready_error:
        return ready_error

    medical_dir = cfg["ENV"]["BENCHMARK_DIR"]
    general_dir = cfg["ENV"].get("GENERAL_BENCHMARK_DIR", "../benchmark/general")

    benchmark_type = normalize_benchmark_type(benchmark_type)
    benchmark_type, correction_note = correct_benchmark_type(
        dataset, benchmark_type, split, medical_dir, general_dir
    )
    if benchmark_type not in {"general", "medical_choice", "medbench"}:
        return (
            f"无法识别数据集类型: dataset={dataset}, benchmark_type={benchmark_type}。\n"
            "请先调用 benchmark_list 或显式指定 benchmark_type=general/medical_choice/medbench。"
        )

    submit_key = benchmark_submit_key(
        resolved_instance_id, benchmark_type, dataset, split
    )
    lock_acquired, lock_message = acquire_benchmark_submit_lock(
        submit_key, dataset, benchmark_type, split, resolved_instance_id
    )
    if not lock_acquired:
        return correction_note + lock_message

    try:
        if benchmark_type == "general":
            return correction_note + run_general_benchmark_job(
                dataset,
                split,
                max_workers,
                limit if limit > 0 else None,
                save_every,
                instance_id,
                submit_key,
                instance_context,
            )

        if benchmark_type == "medical_choice":
            return correction_note + run_medical_choice_benchmark(
                dataset,
                max_workers,
                save_every,
                instance_id,
                submit_key,
                instance_context,
            )

        if benchmark_type == "medbench":
            return correction_note + run_medbench_benchmark(
                dataset,
                max_workers,
                instance_id,
                submit_key,
                instance_context,
            )
    finally:
        release_benchmark_submit_lock(submit_key)


def benchmark_report_text(job_id: str, scope: str = "mine") -> str:
    """Return benchmark status, progress and available result metrics."""
    scope = str(scope or "mine").strip().lower()
    if scope not in {"mine", "all"}:
        return "Invalid scope. Use mine or all."
    meta_path = os.path.join(get_benchmark_log_dir(), job_id, "meta.json")
    if not os.path.exists(meta_path):
        return f"job_id 不存在: {job_id}"

    with open(meta_path, "r") as f:
        meta = refresh_benchmark_job_meta(job_id, meta_path, json.load(f))
    if not task_visible_for_scope(meta, scope):
        return (
            "该 benchmark 任务属于其他用户，默认不显示。\n"
            f"job_id={job_id}\n"
            "如需只读查看全部任务，请使用 scope=all。"
        )
    mode = meta.get("mode")

    if mode == "medbench":
        return (
            "Benchmark报告:\n"
            "note=MedBench 任务只生成模型输出，不计算准确率。\n\n"
            + medbench_progress_text(job_id)
        )

    lines = [
        "Benchmark报告:",
        f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"job_id={job_id}",
        f"status={meta.get('status')}",
        f"mode={mode}",
        f"dataset={meta.get('dataset')}",
        f"model={meta.get('model')}",
        f"owner={task_owner_label(meta)}",
        f"service_instance_id={meta.get('service_instance_id', '')}",
        f"service_run_id={meta.get('service_run_id', '')}",
        f"pid={meta.get('pid')}",
        f"return_code={meta.get('return_code')}",
        f"start_time={meta.get('start_time')}",
        f"end_time={meta.get('end_time')}",
        f"log={format_agent_relative_path(meta.get('log'))}",
        f"output={format_agent_relative_path(meta.get('output'))}",
    ]

    output_file = meta.get("output")
    if not output_file or not os.path.exists(output_file):
        lines.append("progress=暂无中间结果")
        lines.append("note=结果文件尚未生成，可稍后再查。")
        return "\n".join(lines)

    if os.path.isdir(output_file):
        lines.append(f"result_dir={format_agent_relative_path(output_file)}")
        return "\n".join(lines)

    try:
        data = json.load(open(output_file))
    except Exception as e:
        lines.append(f"result_error={e}")
        return "\n".join(lines)

    summary = data.get("summary", {})
    lines.extend(
        [
            f"total={summary.get('total')}",
            f"processed={summary.get('processed')}",
            f"progress={summary.get('progress')}",
        ]
    )

    if mode == "general":
        lines.append(f"split={summary.get('split')}")
        lines.append(f"task_type={summary.get('task_type')}")
        metrics = summary.get("metrics", {})
        if metrics:
            lines.append("metrics:")
            for key, value in metrics.items():
                lines.append(f"- {key}={value}")
    else:
        for key in ["correct", "accuracy", "avg_f1", "invalid", "invalid_rate"]:
            if key in summary:
                value = summary[key]
                if isinstance(value, float):
                    lines.append(f"{key}={value:.4f}")
                else:
                    lines.append(f"{key}={value}")

    if meta.get("status") == "running":
        lines.append(
            "note=任务仍在后台运行，以上为当前已保存的中间结果。"
            "不要连续轮询；请把当前进度、job_id 和输出路径告知用户，用户需要时再查询。"
        )
    else:
        lines.append("note=任务已结束，以上为最终结果。")

    return "\n".join(lines)


def benchmark_type_from_mode(mode: str) -> str:
    return "medical_choice" if mode == "eval" else mode


def benchmark_report_data(job_id: str, scope: str = "mine") -> dict:
    """Build structured benchmark report data from the same files as report text."""
    data = {
        "action": "report",
        "job_id": job_id,
        "current_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_path = os.path.join(get_benchmark_log_dir(), job_id, "meta.json")
    if not os.path.exists(meta_path):
        data.update(
            {
                "status": "not_found",
                "error": f"job_id 不存在: {job_id}",
            }
        )
        return data

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        data.update(
            {
                "status": "error",
                "error": f"读取 meta.json 失败: {e}",
                "artifacts": {
                    "meta": format_agent_relative_path(meta_path),
                },
            }
        )
        return data

    scope = str(scope or "mine").strip().lower()
    if scope not in {"mine", "all"}:
        data.update({"status": "error", "error": "Invalid scope. Use mine or all."})
        return data
    if not task_visible_for_scope(meta, scope):
        data.update(
            {
                "status": "forbidden",
                "error": "该 benchmark 任务属于其他用户，默认不返回结构化结果。",
            }
        )
        return data

    mode = meta.get("mode")
    output_file = meta.get("output")
    data.update(
        {
            "status": meta.get("status"),
            "mode": mode,
            "benchmark_type": benchmark_type_from_mode(mode),
            "dataset": meta.get("dataset"),
            "model": meta.get("model"),
            "service_instance_id": meta.get("service_instance_id"),
            "service_run_id": meta.get("service_run_id"),
            "service_ports": meta.get("service_ports"),
            "pid": meta.get("pid"),
            "return_code": meta.get("return_code"),
            "start_time": meta.get("start_time"),
            "end_time": meta.get("end_time"),
            "artifacts": {
                "log": format_agent_relative_path(meta.get("log")),
                "output": format_agent_relative_path(output_file),
                "meta": format_agent_relative_path(meta_path),
            },
        }
    )

    if mode == "medbench":
        data["note"] = "MedBench 任务只生成模型输出，不计算准确率。"
        progress = meta.get("progress")
        if isinstance(progress, dict):
            data["progress_detail"] = progress
            files = progress.get("files", {})
            if isinstance(files, dict):
                total_samples = 0
                done_samples = 0
                for stat in files.values():
                    if not isinstance(stat, dict):
                        continue
                    total_samples += int(stat.get("total") or 0)
                    done_samples += int(stat.get("done") or 0)
                data["file_progress"] = {
                    "total_files": progress.get("total_files", len(files)),
                    "completed_files": progress.get("completed_files", 0),
                }
                data["sample_progress"] = {
                    "total_samples": total_samples,
                    "done_samples": done_samples,
                    "percent": round(done_samples / total_samples * 100, 4)
                    if total_samples
                    else 0,
                }
        return data

    if not output_file or not os.path.exists(output_file):
        data["progress"] = None
        data["note"] = "结果文件尚未生成，可稍后再查。"
        return data

    if os.path.isdir(output_file):
        data["artifacts"]["result_dir"] = format_agent_relative_path(output_file)
        return data

    try:
        with open(output_file, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        data["result_error"] = str(e)
        return data

    summary = result.get("summary", {})
    if isinstance(summary, dict):
        normalized_summary = dict(summary)
        normalized_summary.pop("dataset", None)
        metrics = normalized_summary.get("metrics")
        if not isinstance(metrics, dict):
            normalized_summary.pop("metrics", None)
            metric_keys = [
                "correct",
                "accuracy",
                "avg_f1",
                "invalid",
                "invalid_rate",
            ]
            metrics = {
                key: normalized_summary.pop(key)
                for key in metric_keys
                if key in normalized_summary
            }
            if metrics:
                normalized_summary["metrics"] = metrics
        data["summary"] = normalized_summary

    if meta.get("status") == "running":
        data["note"] = (
            "任务仍在后台运行，以上为当前已保存的中间结果。"
            "不要连续轮询；请把当前进度、job_id 和输出路径告知用户，用户需要时再查询。"
        )
    else:
        data["note"] = "任务已结束，以上为最终结果。"
    return data


@tool
def config_show() -> dict:
    """Show current service config"""
    config = show_public_config()
    return build_local_tool_response(
        config,
        {
            "config_draft": {
                "operation": "show",
                "applies_to": "new_instances",
                "values": config,
            }
        },
    )


@tool
def service_status() -> dict:
    """Check current inference service status.

    The structured response contains only the current user's instances:
    starting/running/degraded instances in full, plus the five most recent
    failed and stopped instances. If the user asks whether one background
    startup has completed, use service_start_status instead.
    """
    status = service_status_data()
    return build_local_tool_response(
        status["text"],
        {"service_instances": status["service_instances"]},
    )


@tool
def port_status(port: int) -> str:
    """Check port status."""
    return check_port_status(port)


@tool
def gpu_status() -> str:
    """Show GPU usage status."""
    return check_gpu_status()


@tool
def gpu_recommend_allocation() -> dict:
    """Recommend GPU allocation for starting a future new instance from the current user's draft config."""
    return recommend_gpu()


@tool
def config_check() -> dict:
    """Check the current user's draft config before starting a future new instance."""
    config_msg = check_config_validity()
    if config_msg["ok"]:
        return {"ok": True, "msg": f"检查通过。\n分析：{config_msg['analysis']}"}
    else:
        return {
            "ok": False,
            "msg": f"检查不通过。\n原因：{config_msg['reason']}\n分析：{config_msg['analysis']}",
        }


@tool
def service_start(
    gpu_ids: str = "",
    tensor_parallel_size: int = 0,
    fallback_to_auto: bool = False,
) -> str:
    """Start a new inference service instance.

    Existing instances do not need to be stopped first. When gpu_ids is empty,
    this tool selects GPUs automatically. When users explicitly request GPUs,
    pass the physical indexes through gpu_ids, for example "4,5". The requested
    GPUs are strictly validated and written only to the new instance runtime
    config; do not call config_update for a one-time GPU selection.

    Args:
    - gpu_ids: comma-separated physical GPU indexes, or empty for automatic
      allocation.
    - tensor_parallel_size: defaults to the number of specified GPUs. If set,
      it must equal the number of gpu_ids.
    - fallback_to_auto: set true only when the user explicitly permits using
      other GPUs if the requested GPUs are unavailable.

    Startup runs asynchronously. Do not immediately call service_status after
    this tool. Use service_start_status or service_instance_status after a short
    wait or when the user asks for startup progress.
    """

    return start_service(gpu_ids, tensor_parallel_size, fallback_to_auto)


@tool
def service_start_status(run_id: str = "latest") -> str:
    """Check background service startup status.

    Use this when users ask whether startup has finished, whether the service has
    started successfully, or what the startup progress is.

    Args:
    - run_id: startup run id, service instance id, or "latest" for the current
      user's latest startup.
    """

    return service_start_status_text(run_id)


@tool
def service_stop() -> str:
    """Stop the current user's active inference service instance.

    If the current user has multiple active instances, this tool asks for an
    explicit instance_id instead of choosing one automatically. Use
    service_instance_stop(instance_id=...) after the target instance is known.
    """
    return stop_service()


@tool
def service_instance_list(
    scope: str = "mine", limit: int = DEFAULT_LIST_LIMIT
) -> str:
    """
    List inference service instances on this node.

    Args:
    - scope: "mine" shows only current user's instances; "all" shows all
      instances for resource visibility. Other users' instances are visible but
      cannot be stopped or modified by the current user.
    - limit: maximum instances to show, default 20, max 100.
    """

    return list_service_instances_text(scope, limit)


@tool
def service_instance_status(instance_id: str = "latest") -> str:
    """
    Show one inference service instance status.

    Args:
    - instance_id: instance id returned by service_start/service_instance_list,
      or latest for the current user's latest instance.
    """

    return service_instance_status_text(instance_id)


@tool
def service_instance_tasks(instance_id: str = "latest") -> str:
    """
    List benchmark and service-test tasks associated with one service instance.

    Args:
    - instance_id: instance id returned by service_start/service_instance_list,
      or latest for the current user's latest instance.
    """

    return list_service_instance_tasks_text(instance_id)


@tool
def service_instance_stop(instance_id: str = "latest") -> str:
    """
    Stop one inference service instance.

    Default behavior:
    - Stop current user's own instance.
    - Refuse to stop any instance owned by another user.

    Args:
    - instance_id: instance id returned by service_start/service_instance_list,
      or latest for the current user's latest instance.
    """

    access_error = service_instance_access_error(instance_id, "停止")
    if access_error:
        return access_error

    resolved = resolve_service_instance_id(instance_id, scope="mine")
    if not resolved:
        return f"未找到当前用户可停止的推理服务实例: {instance_id}"
    return stop_service_instance(resolved)


@tool
def service_restart() -> str:
    """Restart the current user's latest inference service instance.

    This stops the current user's latest instance, waits briefly, then starts a
    new instance with automatic GPU and port allocation. It does not restart
    other users' instances.
    """

    return restart_service_stack()


@tool
def service_log_runs(limit: int = 10, instance_id: str = "") -> str:
    """
    List recent service log runs.

    Purpose:
    - Discover available service startup run IDs.
    - Check which run ID "latest" points to before calling service_log_tail,
      service_log_search, or service_log_context with a specific run_id.
    - Use this before service_log_tail/service_log_search/service_log_context
      when the user asks for historical logs or run_id is unknown.
    - In multi-instance scenarios, prefer passing instance_id to list logs for
      the selected service instance. Without instance_id, latest resolves to
      the current user's latest instance when possible.

    Args:
        limit: maximum number of recent runs to list, max 100.
        instance_id: optional service instance id. When provided, only logs for
                     that instance are listed.
    """

    return list_service_log_runs_text(limit, instance_id)


@tool
def service_log_tail(
    service: str = "start",
    lines: int = 30,
    run_id: str = "latest",
    instance_id: str = "",
) -> str:
    """
    Summarize important messages in log.

    Shows three sections:
    - ERRORS: grep for error|exception|fail|traceback|timeout|critical (last 20 matches)
    - WARNINGS: grep for warn (last 20 matches)
    - LAST LOG: last N lines with line numbers

    In multi-instance scenarios, pass instance_id whenever the user refers to a
    specific service instance. If the user asks for historical logs or provides
    no clear run_id/instance_id, call service_log_runs first to discover valid
    IDs. Use run_id="latest" only when the user asks for the latest/current
    service logs; latest resolves to the current user's latest instance when
    possible.

    Args:
        service: one of ["start","vllm","inference","ui","web","case2chat"]
        lines: number of recent log lines to show (default: 30, max: 80)
        run_id: service startup run id, or "latest" for the current user's
                newest run when possible.
                Do not use "all" here; use service="all" to search all service logs.
        instance_id: service instance id. If provided, it overrides run_id.
    """

    if instance_id:
        access_error = service_instance_access_error(instance_id, "查看日志")
        if access_error:
            return access_error
        run_id = instance_id
    return tail_logs(service, lines, run_id)


@tool
def service_log_search(
    keyword: str = "error",
    service: str = "all",
    lines: int = 20,
    run_id: str = "latest",
    instance_id: str = "",
) -> str:
    """
    Search keyword or extended regex in logs with case-insensitive matching.

    In multi-instance scenarios, pass instance_id whenever the user refers to a
    specific service instance. If the user asks for historical logs or provides
    no clear run_id/instance_id, call service_log_runs first to discover valid
    IDs. Use run_id="latest" only when the user asks for the latest/current
    service logs; latest resolves to the current user's latest instance when
    possible.

    Args:
        keyword: search text or extended regex, case-insensitive
                 (e.g., error, exception, "runtime|memory|permission denied", etc.)
        service: specific service or "all"
        lines: number of matching results (default: 20, max: 80)
        run_id: service startup run id, or "latest" for the current user's
                newest run when possible.
                Do not use "all" here; use service="all" to search all service logs.
        instance_id: service instance id. If provided, it overrides run_id.
    """

    if instance_id:
        access_error = service_instance_access_error(instance_id, "搜索日志")
        if access_error:
            return access_error
        run_id = instance_id
    return logs_search(keyword, service, lines, run_id)


@tool
def service_log_context(
    service: str,
    index: int,
    window: int = 20,
    run_id: str = "latest",
    instance_id: str = "",
) -> str:
    """
    Show log context around a specific line.

    In multi-instance scenarios, pass instance_id whenever the user refers to a
    specific service instance. If the user asks for historical logs or provides
    no clear run_id/instance_id, call service_log_runs first to discover valid
    IDs. Use run_id="latest" only when the user asks for the latest/current
    service logs; latest resolves to the current user's latest instance when
    possible.

    Args:
        service: log name
        index: line number
        window: lines before and after (default: 20, max: 40)
        run_id: service startup run id, or "latest" for the current user's
                newest run when possible.
                Do not use "all" here.
        instance_id: service instance id. If provided, it overrides run_id.
    """

    if instance_id:
        access_error = service_instance_access_error(instance_id, "查看日志上下文")
        if access_error:
            return access_error
        run_id = instance_id
    return context_log(service, index, window, run_id)


@tool
def service_test_list() -> str:
    """
    List service function test scripts, not benchmark evaluation datasets.

    Use this tool when the user asks about service tests, function tests, or
    shell scripts such as basicmedicalrecord.sh. Do not use this for model
    benchmark/evaluation datasets; use benchmark_list instead.
    """
    return list_tests()


@tool
def service_test_run(
    test_name: str = "basicmedicalrecord.sh", instance_id: str = "latest"
) -> str:
    """
    Run a specific test script.

    This function runs an individual test script and returns the execution results.
    By default, it runs the basic medical record test if no test name is specified.

    Args:
        test_name (str, optional): Name of the test script to execute.
                                   Defaults to "basicmedicalrecord.sh".
                                   Example: "diagnosis.sh", "inpatient.sh"
        instance_id: Service instance id, or latest for the current user's
                     latest running instance. If the current user has multiple
                     running instances, pass a specific instance_id.

    """

    return start_single_test(test_name, instance_id)


@tool
def service_test_run_all(instance_id: str = "latest") -> str:
    """Run all test scripts using the current user's running service instance."""
    return start_all_tests(instance_id)


@tool
def service_test_status(
    test_run_id: str = "latest",
    lines: int = 30,
    instance_id: str = "",
    limit: int = DEFAULT_LIST_LIMIT,
    scope: str = "mine",
) -> str:
    """
    Check background service test status.

    Args:
        test_run_id: test run id, or "latest" for the latest submitted test.
                     Use "all" to list all currently running test scripts.
        lines: number of recent log lines to include.
        instance_id: When test_run_id="all", filter running tests by service instance id.
        limit: When test_run_id="all", maximum running tests to show, default 20, max 100.
        scope: mine shows current user's tasks by default; all shows all users' tasks read-only.
    """

    if test_run_id == "all":
        return running_tests_text(instance_id, limit, scope)
    return test_status_text(test_run_id, lines, instance_id, limit, scope)


@tool
def service_test_stop(test_run_id: str = "latest", scope: str = "mine") -> str:
    """
    Stop a running background service test.

    Args:
        test_run_id: test run id, or "latest" for the latest submitted test.
        scope: mine resolves latest within current user's tasks; all allows selecting
               latest across all users.
    """

    return test_stop_text(test_run_id, False, scope)


@tool
def config_keys() -> str:
    """
    Return all valid current-user draft config keys that can be updated.
    LLM must choose one of these keys before calling config_update.

    This updates the current user's service.draft.yaml for future new instances only; it does not modify
    a running instance's service.runtime.yaml.
    """

    cfg = show_config()
    keys = [key for key in flatten_config_keys(cfg) if key != "ENV.HOST_IP"]
    return "\n".join(keys)


@tool
def config_update(key: str, value: str) -> dict | str:
    """
    Update the current user's service.draft.yaml config value. Key must be one of config_keys().
    This affects future new instances only; it does not modify already running
    service.runtime.yaml files.
    CUDA_VISIBLE_DEVICES GPU count must equal RUNTIME.TENSOR_PARALLEL_SIZE.
    """

    cfg = show_config()
    valid = [key for key in flatten_config_keys(cfg) if key != "ENV.HOST_IP"]

    if key not in valid:
        # suffix match
        matches = [k for k in valid if k.endswith(f".{key}")]

        if len(matches) == 1:
            key = matches[0]
        else:
            return f"Invalid key: {key} \nUse config_keys() to see all valid keys."

    if key not in WHITELIST:
        return f"Key not in whitelist: {key} \nAllowed keys: {', '.join(sorted(WHITELIST))}"

    if key == "ENV.CUDA_VISIBLE_DEVICES" and value.startswith("["):
        value = ",".join(map(str, ast.literal_eval(value)))
    if key == "ENV.CUDA_VISIBLE_DEVICES":
        try:
            parse_visible_gpus(value)
        except Exception:
            return "CUDA_VISIBLE_DEVICES 格式错误，应使用逗号分隔，例如 '0,1,2,3'"
    current_value = get_config_value(cfg, key)
    if config_value_equal(current_value, value):
        text = f"配置未变化，无需更新: {ensure_user_draft_config()}: .{key} = {value}"
        return build_local_tool_response(
            text,
            {
                "config_draft": {
                    "operation": "update",
                    "applies_to": "new_instances",
                    "values": show_public_config(),
                }
            },
        )
    text = update_config(key, value)
    return build_local_tool_response(
        text,
        {
            "config_draft": {
                "operation": "update",
                "applies_to": "new_instances",
                "values": show_public_config(),
            }
        },
    )


@tool
def config_restore() -> str:
    """Restore service.yaml to default configuration."""
    return restore_default_config()


@tool
def model_list() -> str:
    """List all available models."""
    return model_list_text()


@tool
def benchmark_list(benchmark_type: str = "all") -> str:
    """
    List available benchmark evaluation datasets, not service test scripts.

    Use this tool when the user asks about:
    - benchmark datasets
    - model evaluation datasets
    - medical/general evaluation benchmarks
    - datasets that can be passed to benchmark_run

    Do not use this for service function tests such as basicmedicalrecord.sh.
    Use service_test_list for service test scripts.

    Call this before benchmark_run unless the user has already provided an exact
    dataset name copied from a recent benchmark_list or benchmark_inspect result.
    For medical_choice datasets, use the exact file name shown in the list,
    e.g. step1.json, not medical_choice/step1.json.

    Args:
    - benchmark_type: all, general, medical_choice, or medbench.
    """

    return benchmark_list_unified(benchmark_type)


@tool
def benchmark_inspect(
    dataset: str, benchmark_type: str = "auto", split: str = "default"
) -> str:
    """
    Inspect one benchmark dataset before running.

    Args:
    - dataset: Dataset key or file name, e.g. mmlu, humaneval, 2024.json,
      step1.json, MedDiag.jsonl. For medical_choice, use the exact file name
      from benchmark_list, not medical_choice/step1.json. To inspect the overall MedBench structure, use
      dataset="medical/medbench" or dataset="medbench"; do not invent a
      MedBench file name before calling benchmark_list.
      For TruthfulQA, dataset="truthfulqa" means the default generation task;
      do not replace it with truthfulqa-mc1 or truthfulqa-mc2 unless the user
      explicitly asks for that mode.
    - benchmark_type: auto, general, medical_choice, or medbench.
    - split: General benchmark split. Use default unless needed.
    """

    return benchmark_inspect_unified(dataset, benchmark_type, split)


@tool
def benchmark_run(
    dataset: str,
    benchmark_type: str = "auto",
    split: str = "default",
    max_workers: int = 5,
    limit: int = 0,
    save_every: int = 2,
    instance_id: str = "latest",
) -> str:
    """
    Run a benchmark evaluation job asynchronously.

    This runs model evaluation on benchmark datasets, not service function tests.

    Requirements before calling:
    - Do not invent dataset names.
    - Call benchmark_list first unless the dataset name was copied exactly from a
      recent benchmark_list or benchmark_inspect result.
    - If benchmark_type or split is unclear, call benchmark_inspect first.
    - The dataset argument must be a dataset key or file name from
      benchmark_list/benchmark_inspect output.
    - For medical_choice, dataset must be the exact file name such as
      step1.json; do not add medical_choice/ prefix.
    - If service_start was just submitted and the service is still starting,
      do not call this tool yet; ask the user to retry after startup is ready.
    - The tool checks the selected instance's /v1/models endpoint before
      submitting the job. If the API is not ready, report the message to the
      user and ask them to retry later.
    - If the current user has multiple running service instances, pass a
      specific instance_id. Do not rely on latest.
    - For TruthfulQA, if the user says only "truthfulqa" without specifying a
      mode, pass dataset="truthfulqa" unchanged. Do not infer mc1 or mc2 from
      conversation context. Use truthfulqa-mc1 only when the user explicitly
      asks for MC1, single-choice, multiple-choice accuracy, or choice
      accuracy. Use truthfulqa-mc2 only when the user explicitly asks for MC2,
      multi-select, or F1/partial-credit evaluation.

    Args:
    - dataset: Dataset key or file name.
    - benchmark_type: auto, general, medical_choice, or medbench.
    - split: General benchmark split.
    - max_workers: Concurrent model requests.
    - limit: Optional sample limit for general benchmarks. Use 0 for full dataset.
    - save_every: Save partial result every N completed samples.
    - instance_id: Service instance id, or latest for the current user's latest
      running instance.
    """

    return benchmark_run_unified(
        dataset, benchmark_type, split, max_workers, limit, save_every, instance_id
    )


@tool
def benchmark_report(job_id: str, scope: str = "mine") -> str:
    """
    Retrieve benchmark report by job_id.

    The report includes status, progress, partial results, final metrics, log path
    and output path. Use this for user requests about benchmark progress, result,
    score, completion state, or "how is this job going".
    scope: mine shows current user's report by default; all allows read-only
    viewing of all users' benchmark reports.
    """

    text = benchmark_report_text(job_id, scope)
    return build_local_tool_response(
        text,
        {
            "benchmark_reports": [
                benchmark_report_data(job_id, scope)
            ]
        },
    )


@tool
def benchmark_jobs(
    instance_id: str = "", limit: int = DEFAULT_LIST_LIMIT, scope: str = "mine"
) -> str:
    """
    List all benchmark jobs with their current status.

    Purpose:
    - Provide an overview of all submitted benchmark tasks.
    - Help users identify job_id for further operations.

    Returns:
    - A formatted string where each line represents a job, including:
       - job_id
       - model name
       - dataset name
       - status (running / finished / stopped / failed / not found)
       - service instance id

    Args:
        instance_id: optional service instance id. When provided, only jobs
                     associated with that instance are listed.
        limit: maximum jobs to show, default 20, max 100.
        scope: mine shows current user's jobs by default; all shows all users'
               jobs read-only.
    """

    return list_benchmark_jobs_text(instance_id, limit, scope)


@tool
def benchmark_stop(job_id: str) -> str:
    """
    Stop a running benchmark job by terminating its process.

    Purpose:
    - Terminate a long-running benchmark task manually
    - Free system resources (CPU/GPU/memory)
    - Handle incorrect or unnecessary job executions

    Args:
        job_id (str): Unique identifier of the benchmark job.

    Returns:
        str: Status message indicating result.

    Notes:
    - This operation is irreversible
    - Partial results (if any) may be incomplete or discarded
    - After stopping, benchmark result files may be incomplete
    - Only call this when the user explicitly confirms stopping the benchmark.
      Do not call it automatically just because service_stop was blocked.
    """

    return stop_benchmark_job(job_id)


@tool
def node_list(show_disabled: bool = False) -> str:
    """
    List configured inference agent nodes for multi-node multi-instance deployment.

    This is a controller-side read-only tool. It only reads nodes.yaml and does
    not call remote nodes, start services, stop services, or modify config.

    Args:
        show_disabled: include disabled nodes when true.
    """

    nodes = load_nodes_config()
    if not nodes:
        return f"暂无节点配置: {NODES_CONFIG_FILE}"

    if resource_pool_managed():
        resource_error = managed_resource_error()
        if resource_error:
            return resource_error

    lines = ["多节点推理 Agent 配置:"]
    for key, node in nodes.items():
        enabled = is_node_enabled(node)
        if not enabled and not show_disabled:
            continue
        if resource_pool_managed() and not node_matches_resource(key, node):
            continue
        lines.append(
            " | ".join(
                [
                    f"node={key}",
                    f"name={node.get('NAME', key)}",
                    f"enabled={enabled}",
                    f"role={node.get('ROLE', '')}",
                    f"host={node.get('HOST', '')}",
                    f"resource_node_id={node.get('RESOURCE_NODE_ID', key)}",
                    f"tool_url={node.get('TOOL_URL') or get_node_tool_url(node.get('URL', ''))}",
                ]
            )
        )

    if len(lines) == 1:
        return "暂无启用节点。可设置 show_disabled=true 查看禁用节点。"
    return "\n".join(lines)


@tool
def node_enable(node: str) -> str:
    """
    Enable one configured node for controller routing.

    This only updates nodes.yaml on the controller. It does not start the remote
    inference_agent or remote inference service. Use node_service_start to start
    service on a node.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    return set_node_enabled(node, True)


@tool
def node_disable(node: str) -> str:
    """
    Disable one configured node from controller routing.

    This only updates nodes.yaml on the controller. It does not stop the remote
    inference_agent or remote inference service. If the remote node currently has
    inference services running, this tool refuses to disable it; use
    node_service_stop first.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    node_key, node_cfg = resolve_node_config(node, require_enabled=False)
    role = str(node_cfg.get("ROLE", "")).strip().lower()
    if "controller" in role:
        return (
            f"节点 {node_key} 是 controller 节点，不能禁用。\n"
            "如果需要停止该节点上的推理服务，请使用 node_service_stop。"
        )

    if not is_node_enabled(load_nodes_config()[node_key]):
        return f"节点已处于禁用状态: {node_key}"

    response = call_node_tool(node_key, "service_status")
    status_text = str(response.get("result", ""))
    if "RUNNING" in status_text:
        return (
            f"节点 {node_key} 上仍有推理服务运行，不能禁用。\n"
            "请先调用 node_service_stop 停止该节点服务，再禁用节点。\n\n"
            f"当前状态：\n{status_text}"
        )

    return set_node_enabled(node_key, False)


@tool
def node_service_status(node: str = "") -> str:
    """
    Check one remote node's local inference service status.

    Use this controller-side tool when the user explicitly specifies a node
    such as node1/main or asks for multi-node service status. This reports the
    remote node's current running/stopped port status.

    Do not use this to check whether a submitted background startup has
    completed; use node_service_start_status for startup progress.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    return node_tool_structured(node, "service_status")


@tool
def node_gpu_status(node: str = "") -> str:
    """
    Check one remote node's local GPU status.

    Use this controller-side tool when the user explicitly specifies a node
    such as node1/main or asks for multi-node GPU status. This only reports GPU
    usage on the selected remote node; it does not modify config or start
    service.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    return node_tool_text(node, "gpu_status")


@tool
def node_config_show(node: str = "") -> str:
    """
    Show one remote node's local inference service config.

    Use this controller-side tool when the user explicitly specifies a node
    such as node1/main or asks for multi-node config. This reads the remote
    node's service.yaml and returns its public service config.

    Use node_config_update to modify config. Use node_config_keys first if the
    exact key name is unclear.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    return node_tool_structured(node, "config_show")


@tool
def node_config_keys(node: str = "") -> str:
    """
    Return config keys that can be updated on one remote node.

    Call this before node_config_update when the user gives an imprecise key
    name such as "GPU", "TP", "model", or "port". The update key must be one of
    the returned keys or a unique suffix accepted by the remote worker.
    """

    return node_tool_text(node, "config_keys")


@tool
def node_config_update(node: str = "", key: str = "", value: str = "") -> str:
    """
    Update one whitelisted config key on a remote node.

    Use this controller-side tool only when the user explicitly specifies a node
    and a config key/value. The remote node still enforces its own whitelist and
    running-service checks.
    CUDA_VISIBLE_DEVICES GPU count must equal RUNTIME.TENSOR_PARALLEL_SIZE.

    Use this before node_service_start when the user asks to start a node with
    specific runtime settings, such as:
    - CUDA_VISIBLE_DEVICES / GPU ids
    - RUNTIME.TENSOR_PARALLEL_SIZE / TP
    - ENV.MODEL_NAME
    - PORTS.*

    For example, if the user says "start node1 with GPU 0 and TP=1", call:
    - node_config_update(node1, "ENV.CUDA_VISIBLE_DEVICES", "0")
    - node_config_update(node1, "RUNTIME.TENSOR_PARALLEL_SIZE", "1")
    - node_service_start(node1)

    Args:
        node: node key/name/host from nodes.yaml.
        key: config key, e.g. PORTS.VLLM_OPENAI_PORT.
        value: new value as string.
    """

    return node_tool_structured(node, "config_update", {"key": key, "value": value})


@tool
def node_port_status(node: str = "", port: int = 0) -> str:
    """
    Check one port status on one remote node.

    Use this for a specific remote port such as VLLM, inference API, UI, or data
    annotation port. Use node_service_status when the user wants the full remote
    service status.
    """

    return node_tool_text(node, "port_status", {"port": port})


@tool
def node_model_list(node: str = "") -> str:
    """
    List available models on one remote node.

    Use this before node_config_update when the user wants to switch model but
    has not provided the exact model name/path available on that node.
    """

    return node_tool_text(node, "model_list")


@tool
def node_config_check(node: str = "") -> str:
    """
    Check whether one remote node's service config is valid before startup.

    This validates the selected node's current user's draft config, model path, GPU
    allocation, tensor parallel size, and ports. It does not start, stop, or
    modify anything.
    """

    return node_tool_text(node, "config_check")


@tool
def node_gpu_recommend_allocation(node: str = "") -> str:
    """
    Recommend GPU allocation for one remote node.

    Use this when deciding which GPUs and tensor parallel size to use on that
    node. This is analysis only: it does not update CUDA_VISIBLE_DEVICES, does
    not update TENSOR_PARALLEL_SIZE, and does not start service. After choosing
    a recommendation, call node_config_update for the required config keys, then
    node_service_start.
    """

    return node_tool_text(node, "gpu_recommend_allocation")


@tool
def node_recommend_start_target(target_node: str = "auto") -> str:
    """
    Recommend which enabled worker node should start inference service.

    This controller-side tool only analyzes nodes. It does not modify config,
    stop service, or start service. Use it when a requested node cannot start
    or when the user asks which node/GPU should be used. Use this after
    node_service_start fails because the requested node has insufficient GPU
    memory.

    Args:
        target_node: preferred node key/name/host, or auto.
    """

    nodes = load_nodes_config()
    if not nodes:
        return f"暂无节点配置: {NODES_CONFIG_FILE}"
    if resource_pool_managed():
        resource_error = managed_resource_error(require_gpus=True)
        if resource_error:
            return resource_error

    target_text = str(target_node or "auto").strip()
    preferred_key = ""

    if target_text.lower() not in {"", "auto"}:
        try:
            preferred_key, _ = resolve_node_config(target_text)
        except Exception as e:
            return f"目标节点无效: {target_text}\nerror={e}"

    candidates = []
    skipped = []

    for node_key, node_cfg in nodes.items():
        if not is_node_enabled(node_cfg):
            skipped.append(f"{node_key}: disabled")
            continue
        if not node_is_worker(node_cfg):
            skipped.append(f"{node_key}: not worker")
            continue
        if resource_pool_managed() and not node_matches_resource(node_key, node_cfg):
            skipped.append(f"{node_key}: outside resource boundary")
            continue
        try:
            recommend_response = call_node_tool(node_key, "gpu_recommend_allocation")
            recommend = parse_recommend_result(recommend_response)
            if not recommend["ok"]:
                skipped.append(f"{node_key}: no usable GPU recommendation")
                candidates.append(
                    {
                        "node": node_key,
                        "ok": False,
                        "current_ok": False,
                        "reason": "gpu recommendation failed",
                        "analysis": recommend["analysis"],
                    }
                )
                continue

            candidates.append(
                {
                    "node": node_key,
                    "ok": True,
                    "current_ok": recommend["current_ok"],
                    "recommended_gpus": recommend["recommended_gpus"],
                    "recommended_tp": recommend["recommended_tp"],
                    "analysis": recommend["analysis"],
                }
            )
        except Exception as e:
            skipped.append(f"{node_key}: error={e}")

    usable = [item for item in candidates if item.get("ok")]
    if not usable:
        lines = ["没有找到可推荐的启动节点。"]
        if skipped:
            lines.append("节点情况:")
            lines.extend(f"- {item}" for item in skipped)
        for item in candidates:
            if item.get("analysis"):
                lines.append(f"\n{item['node']} 分析:\n{item['analysis']}")
        return "\n".join(lines)

    def rank(item: dict) -> tuple[int, int, str]:
        if preferred_key and item["node"] == preferred_key and item.get("current_ok"):
            return (0, 0, item["node"])
        if item.get("current_ok"):
            return (1, 0 if item["node"] == preferred_key else 1, item["node"])
        return (2, 0 if item["node"] == preferred_key else 1, item["node"])

    best = sorted(usable, key=rank)[0]

    lines = ["启动节点推荐:"]
    if preferred_key:
        target = next((item for item in candidates if item["node"] == preferred_key), None)
        if target:
            lines.append(
                f"- 用户指定节点 {preferred_key}: "
                f"{'当前配置可启动' if target.get('current_ok') else '当前配置不适合作为首选'}"
            )
        else:
            lines.append(f"- 用户指定节点 {preferred_key}: 未进入可用候选")

    lines.append(f"- 推荐节点: {best['node']}")
    lines.append(
        f"- 预计自动分配: GPU={best['recommended_gpus']}, "
        f"TP={best['recommended_tp']}"
    )
    lines.append(
        "- 说明: node_service_start 会为新实例自动选择 GPU 和端口，"
        "不要为了使用推荐 GPU 而调用 node_config_update。"
    )

    lines.append("")
    lines.append("后续操作建议:")
    lines.append(f"1. node_service_start(node='{best['node']}')")
    lines.append(f"2. node_service_start_status(node='{best['node']}', run_id='latest')")

    lines.append("")
    lines.append("候选节点摘要:")
    for item in usable:
        status = "template_ok" if item.get("current_ok") else "auto_allocation_available"
        lines.append(
            f"- {item['node']}: {status}, gpu={item.get('recommended_gpus')}, "
            f"tp={item.get('recommended_tp')}"
        )
    if skipped:
        lines.append("跳过节点:")
        lines.extend(f"- {item}" for item in skipped)

    return "\n".join(lines)


@tool
def node_service_start(
    node: str = "",
    gpu_ids: str = "",
    tensor_parallel_size: int = 0,
    fallback_to_auto: bool = False,
) -> str:
    """
    Start one remote node's local inference service.

    Use this controller-side tool only when the user explicitly specifies a node
    such as node1/main. The remote node will run its own service_start policy
    checks before starting.

    This tool starts from the remote current user's draft config. For a one-time
    GPU selection, pass gpu_ids directly instead of calling node_config_update.
    The worker writes the selection only to the new instance runtime config.

    Use node_config_update first only for persistent settings such as model name,
    memory utilization, max tokens, or other draft configuration.

    If this tool returns blocked/insufficient_memory, call
    node_recommend_start_target with the same node to find another available
    node.

    Startup runs asynchronously. Do not immediately call node_service_status
    after this tool. Use node_service_start_status after a short wait or when
    the user asks for startup progress.

    Args:
        node: node key/name/host from nodes.yaml.
        gpu_ids: comma-separated physical GPU indexes, or empty for automatic
            allocation.
        tensor_parallel_size: defaults to the number of specified GPUs and must
            match that count when provided.
        fallback_to_auto: set true only when the user explicitly permits using
            other GPUs if the requested GPUs are unavailable.
    """

    response = call_node_tool(
        node,
        "service_start",
        {
            "gpu_ids": gpu_ids,
            "tensor_parallel_size": tensor_parallel_size,
            "fallback_to_auto": fallback_to_auto,
        },
    )
    return append_start_target_hint(format_node_tool_response(node, response), node)


@tool
def node_service_start_status(
    node: str = "", run_id: str = "latest", instance_id: str = ""
) -> str:
    """
    Check one remote node's latest service start task status.

    Use this after node_service_start or node_service_restart when the user asks
    whether startup has finished, whether startup succeeded, or what the startup
    progress is.

    Args:
        node: node key/name/host from nodes.yaml.
        run_id: service start run_id on that node, service instance id, or latest.
        instance_id: service instance id. If provided, it overrides run_id.
    """

    if instance_id:
        run_id = instance_id
    return node_tool_text(node, "service_start_status", {"run_id": run_id})


@tool
def node_service_stop(node: str = "") -> str:
    """
    Stop the current user's active inference service instance on one remote node.

    Use this controller-side tool when the user explicitly specifies a node such
    as node1/main or asks to stop service on a remote node. If that remote node
    has multiple active instances for the current user, the worker asks for an
    explicit instance_id. Use node_service_instance_stop(instance_id=...) after
    the target instance is known. This does not disable the node in nodes.yaml.
    Use node_disable separately if the user wants to disable routing.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    return node_tool_text(node, "service_stop")


@tool
def node_service_instance_list(
    node: str = "", scope: str = "mine", limit: int = DEFAULT_LIST_LIMIT
) -> str:
    """
    List inference service instances on one remote node.

    Args:
        node: node key/name/host from nodes.yaml.
        scope: mine or all.
        limit: maximum instances to show, default 20, max 100.
    """

    return node_tool_text(
        node, "service_instance_list", {"scope": scope, "limit": limit}
    )


@tool
def node_service_instance_status(node: str = "", instance_id: str = "latest") -> str:
    """
    Show one inference service instance status on a remote node.

    Args:
        node: node key/name/host from nodes.yaml.
        instance_id: instance id, or latest for current user's latest instance.
    """

    return node_tool_text(
        node, "service_instance_status", {"instance_id": instance_id}
    )


@tool
def node_service_instance_tasks(node: str = "", instance_id: str = "latest") -> str:
    """
    List benchmark and service-test tasks associated with one remote service instance.

    Args:
        node: node key/name/host from nodes.yaml.
        instance_id: instance id, or latest for current user's latest instance.
    """

    return node_tool_text(
        node, "service_instance_tasks", {"instance_id": instance_id}
    )


@tool
def node_service_instance_stop(node: str = "", instance_id: str = "latest") -> str:
    """
    Stop one current-user-owned inference service instance on a remote node.

    Cross-user stop is not allowed by ordinary tools.

    Args:
        node: node key/name/host from nodes.yaml.
        instance_id: instance id, or latest for current user's latest instance.
    """

    return node_tool_text(
        node, "service_instance_stop", {"instance_id": instance_id}
    )


@tool
def node_service_restart(node: str = "") -> str:
    """
    Restart one remote node's local inference service.

    Use this controller-side tool when the user explicitly specifies a node such
    as node1/main. The remote node restarts with its current user's draft config.

    This tool does not modify GPU, TP, model, or port config. If the user asks
    to change config and restart, call node_config_update for every requested
    change first, then call node_service_restart. Use node_service_start_status
    afterwards to check startup progress.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    return node_tool_text(node, "service_restart")


@tool
def node_service_log_runs(
    node: str = "", limit: int = 10, instance_id: str = ""
) -> str:
    """
    List recent service log runs on one remote node.

    Use this to discover valid run_id values before calling
    node_service_log_tail, node_service_log_search, or node_service_log_context
    for historical logs. Use run_id="latest" only for the newest/current logs.
    In multi-instance scenarios, prefer instance_id to avoid reading the wrong
    instance logs.

    Args:
        node: node key/name/host from nodes.yaml.
        limit: maximum number of recent runs to list, max 100.
        instance_id: optional service instance id. When provided, only logs for
          that instance are listed.
    """

    return node_tool_text(
        node, "service_log_runs", {"limit": limit, "instance_id": instance_id}
    )


@tool
def node_service_log_tail(
    node: str = "",
    service: str = "all",
    lines: int = 80,
    run_id: str = "latest",
    instance_id: str = "",
) -> str:
    """
    Summarize important service log messages on one remote node.

    Use this to inspect errors, warnings, and recent log lines for one remote
    startup run. If the user asks for historical logs and no run_id is clear,
    call node_service_log_runs first.
    In multi-instance scenarios, pass instance_id whenever the user refers to a
    specific service instance.

    Args:
        node: node key/name/host from nodes.yaml.
        service: one of start, vllm, inference, ui, web, case2chat, or all.
        lines: number of recent lines to include (max: 80).
        run_id: service startup run id, or latest.
        instance_id: service instance id. If provided, it overrides run_id.
    """

    return node_tool_text(
        node,
        "service_log_tail",
        {
            "service": service,
            "lines": lines,
            "run_id": run_id,
            "instance_id": instance_id,
        },
    )


@tool
def node_service_log_search(
    node: str = "",
    keyword: str = "error",
    service: str = "all",
    lines: int = 20,
    run_id: str = "latest",
    instance_id: str = "",
) -> str:
    """
    Search service logs on one remote node.

    The keyword can be plain text or an extended regex and is matched
    case-insensitively. Use service="all" to search all service logs on that
    node. If the user asks for historical logs and no run_id is clear, call
    node_service_log_runs first.
    In multi-instance scenarios, pass instance_id whenever the user refers to a
    specific service instance.

    Args:
        lines: number of matching results (max: 80).
    """

    return node_tool_text(
        node,
        "service_log_search",
        {
            "keyword": keyword,
            "service": service,
            "lines": lines,
            "run_id": run_id,
            "instance_id": instance_id,
        },
    )


@tool
def node_service_log_context(
    node: str = "",
    service: str = "start",
    index: int = 1,
    window: int = 20,
    run_id: str = "latest",
    instance_id: str = "",
) -> str:
    """
    Show service log context around a line number on one remote node.

    Use this after node_service_log_tail or node_service_log_search returns a
    specific line number and the user wants surrounding lines.
    In multi-instance scenarios, pass instance_id whenever the user refers to a
    specific service instance.

    Args:
        window: lines before and after the target line (max: 40).
    """

    return node_tool_text(
        node,
        "service_log_context",
        {
            "service": service,
            "index": index,
            "window": window,
            "run_id": run_id,
            "instance_id": instance_id,
        },
    )


@tool
def node_service_test_list(node: str = "") -> str:
    """
    List service function test scripts on one remote node.

    These are service tests such as basicmedicalrecord.sh, not benchmark
    evaluation datasets. Use node_benchmark_list for benchmark datasets.
    """

    return node_tool_text(node, "service_test_list")


@tool
def node_service_test_run(
    node: str = "",
    test_name: str = "basicmedicalrecord.sh",
    instance_id: str = "latest",
) -> str:
    """
    Run one service function test script on one remote node.

    This starts a background test job for scripts such as
    basicmedicalrecord.sh. It is not a benchmark evaluation. Use
    node_service_test_status to check progress/result and node_service_test_stop
    to stop it.
    """

    return node_tool_text(
        node,
        "service_test_run",
        {"test_name": test_name, "instance_id": instance_id},
    )


@tool
def node_service_test_run_all(node: str = "", instance_id: str = "latest") -> str:
    """
    Run all service function test scripts on one remote node.

    This submits a background test-all job. Use node_service_test_status to
    check per-script progress/result and node_service_test_stop to stop it.
    Do not use this for benchmark datasets.
    """

    return node_tool_text(node, "service_test_run_all", {"instance_id": instance_id})


@tool
def node_service_test_status(
    node: str = "",
    test_run_id: str = "latest",
    lines: int = 30,
    instance_id: str = "",
    limit: int = DEFAULT_LIST_LIMIT,
    scope: str = "mine",
) -> str:
    """
    Check service function test status on one remote node.

    Args:
        node: node key/name/host from nodes.yaml.
        test_run_id: test run id, latest, or all for currently running tests.
        lines: number of recent log lines to include.
        instance_id: when test_run_id=all, filter tests by service instance id.
        limit: when test_run_id=all, maximum running tests to show, default 20, max 100.
        scope: mine shows current user's tasks by default; all shows all users' tasks read-only.
    """

    return node_tool_text(
        node,
        "service_test_status",
        {
            "test_run_id": test_run_id,
            "lines": lines,
            "instance_id": instance_id,
            "limit": limit,
            "scope": scope,
        },
    )


@tool
def node_service_test_stop(
    node: str = "",
    test_run_id: str = "latest",
    scope: str = "mine",
) -> str:
    """
    Stop a running service function test on one remote node.

    Args:
        node: node key/name/host from nodes.yaml.
        test_run_id: test run id, or latest for the latest submitted test.
        scope: mine resolves latest within current user's tasks; all allows selecting
          latest across all users.
    """

    return node_tool_text(
        node,
        "service_test_stop",
        {"test_run_id": test_run_id, "scope": scope},
    )


@tool
def node_benchmark_list(node: str = "", benchmark_type: str = "all") -> str:
    """
    List available benchmark evaluation datasets on one remote node.

    Use this for model evaluation datasets, not service function tests. Call it
    before node_benchmark_run unless the dataset name was copied exactly from a
    recent node_benchmark_list or node_benchmark_inspect result.
    For medical_choice datasets, use the exact file name shown in the list,
    e.g. step1.json, not medical_choice/step1.json.

    Args:
        node: node key/name/host from nodes.yaml.
        benchmark_type: all, general, medical_choice, or medbench.
    """

    return node_tool_text(node, "benchmark_list", {"benchmark_type": benchmark_type})


@tool
def node_benchmark_inspect(
    node: str = "",
    dataset: str = "",
    benchmark_type: str = "auto",
    split: str = "default",
) -> str:
    """
    Inspect one benchmark dataset on one remote node before running.

    Use this when dataset type, split, or format is unclear. For MedBench
    structure, use dataset="medical/medbench" or dataset="medbench"; do not
    invent a MedBench file name before calling node_benchmark_list. For
    medical_choice, use exact file names such as step1.json.
    For TruthfulQA, dataset="truthfulqa" means the default generation task; do
    not replace it with truthfulqa-mc1 or truthfulqa-mc2 unless the user
    explicitly asks for that mode.
    """

    return node_tool_text(
        node,
        "benchmark_inspect",
        {"dataset": dataset, "benchmark_type": benchmark_type, "split": split},
    )


@tool
def node_benchmark_run(
    node: str = "",
    dataset: str = "",
    benchmark_type: str = "auto",
    split: str = "default",
    max_workers: int = 5,
    limit: int = 0,
    save_every: int = 2,
    instance_id: str = "latest",
) -> str:
    """
    Run one benchmark evaluation job asynchronously on one remote node.

    Requirements before calling:
    - Do not invent dataset names.
    - Call node_benchmark_list first unless the dataset name was copied exactly
      from a recent node_benchmark_list or node_benchmark_inspect result.
    - If benchmark_type or split is unclear, call node_benchmark_inspect first.
    - This is for benchmark evaluation, not service function tests.
    - For medical_choice, dataset must be the exact file name such as
      step1.json; do not add medical_choice/ prefix.
    - If node_service_start was just submitted and the service is still starting,
      do not call this tool yet; ask the user to retry after startup is ready.
    - Uses the selected node's current user's latest running service instance by
      default. Pass instance_id only when the user selected a specific instance.
    - For TruthfulQA, if the user says only "truthfulqa" without specifying a
      mode, pass dataset="truthfulqa" unchanged. Do not infer mc1 or mc2 from
      conversation context. Use truthfulqa-mc1 only when the user explicitly
      asks for MC1, single-choice, multiple-choice accuracy, or choice
      accuracy. Use truthfulqa-mc2 only when the user explicitly asks for MC2,
      multi-select, or F1/partial-credit evaluation.

    Use node_benchmark_report with the returned job_id to check progress,
    partial result, final metrics, log path, and output path.
    """

    return node_tool_text(
        node,
        "benchmark_run",
        {
            "dataset": dataset,
            "benchmark_type": benchmark_type,
            "split": split,
            "max_workers": max_workers,
            "limit": limit,
            "save_every": save_every,
            "instance_id": instance_id,
        },
    )


@tool
def node_benchmark_report(node: str = "", job_id: str = "", scope: str = "mine") -> str:
    """
    Retrieve benchmark report by job_id on one remote node.

    Use this for benchmark progress, result, score, completion state, or "how
    is this job going". The job_id belongs to the selected remote node.
    scope: mine shows current user's report by default; all allows read-only
    viewing of all users' benchmark reports.
    """

    return node_tool_structured(
        node, "benchmark_report", {"job_id": job_id, "scope": scope}
    )


@tool
def node_benchmark_jobs(
    node: str = "",
    instance_id: str = "",
    limit: int = DEFAULT_LIST_LIMIT,
    scope: str = "mine",
) -> str:
    """
    List benchmark jobs on one remote node.

    Use this to find job_id values for node_benchmark_report or
    node_benchmark_stop when the user did not provide a job_id.

    Args:
        node: node key/name/host from nodes.yaml.
        instance_id: optional service instance id. When provided, only jobs
          associated with that instance are listed.
        limit: maximum jobs to show, default 20, max 100.
        scope: mine shows current user's jobs by default; all shows all users'
          jobs read-only.
    """

    return node_tool_text(
        node,
        "benchmark_jobs",
        {"instance_id": instance_id, "limit": limit, "scope": scope},
    )


@tool
def node_benchmark_stop(node: str = "", job_id: str = "") -> str:
    """
    Stop one running benchmark job on one remote node.

    This terminates the remote benchmark process. Partial results may be
    incomplete. Use node_benchmark_jobs first if the job_id is unknown.
    Only call this when the user explicitly confirms stopping the benchmark.
    Do not call it automatically just because node_service_stop was blocked.
    Cross-user stop is not allowed by ordinary tools.
    """

    return node_tool_text(node, "benchmark_stop", {"job_id": job_id})
