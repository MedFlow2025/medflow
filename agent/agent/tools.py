import ast
import copy
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Dict, Optional

import psutil
import yaml
from langchain.tools import tool

CONFIG_FILE = "../config/service.yaml"
DEFAULT_CONFIG_FILE = "../config/service.default.yaml"
NODES_CONFIG_FILE = "../config/nodes.yaml"
WHITELIST = {
    "PORTS.VLLM_OPENAI_PORT",
    "PORTS.INFERENCE_PORT",
    "PORTS.UI_PORT",
    "PORTS.DATA_ANNOTATION_PORT",
    "ENV.HOST_IP",
    "ENV.CUDA_VISIBLE_DEVICES",
    "ENV.MODEL_NAME",
    "RUNTIME.TENSOR_PARALLEL_SIZE",
    "RUNTIME.MAX_TOKENS",
    "RUNTIME.GPU_MEMORY_UTILIZATION",
}
# "ENV.BENCHMARK_DIR",
# "ENV.GENERAL_BENCHMARK_DIR",
# "ENV.HUMANEVAL_EXECUTOR",
# "ENV.HUMANEVAL_DOCKER_IMAGE",
# "ENV.HUMANEVAL_TIMEOUT",
# "ENV.HUMANEVAL_MEMORY",
# "ENV.HUMANEVAL_CPUS",
# "ENV.HUMANEVAL_PIDS_LIMIT",
# "ENV.LCB_EXECUTOR",
# "ENV.LCB_DOCKER_IMAGE",
# "ENV.LCB_TIMEOUT",
# "ENV.LCB_NUM_PROCESS",
# "ENV.LCB_MEMORY",
# "ENV.LCB_CPUS",
# "ENV.LCB_PIDS_LIMIT",
LOG_FILES = {
    "start": "start-service.log",
    "vllm": "vllm.log",
    "inference": "inference.log",
    "ui": "web.log",
    "web": "web.log",
    "case2chat": "case2chat.log",
}
MAX_OUTPUT_CHARS = 6000
PROGRESS_UPDATE_INTERVAL = 5
NODE_AGENT_TIMEOUT = 120


def safe_output(text):
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n... truncated ..."
    return text


def get_service_log_root() -> str:
    CONFIG = show_config()
    log_dir = CONFIG["ENV"]["LOG_DIR"]
    if os.path.isabs(log_dir):
        return os.path.normpath(log_dir)
    return os.path.normpath(f"../{log_dir}")


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


def resolve_node_config(node: str, require_enabled: bool = True) -> tuple[str, dict]:
    key = str(node or "").strip()
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
            if str(item.get("NAME", "")).strip() == key
            or str(item.get("HOST", "")).strip() == key
        ]
        if len(matches) != 1:
            available = ", ".join(enabled_nodes().keys()) or "none"
            raise ValueError(
                f"Unknown node: {node}. Available enabled nodes: {available}"
            )
        node_key, node_cfg = matches[0]

    if require_enabled and not is_node_enabled(node_cfg):
        raise ValueError(f"Node disabled: {node_key}")
    if not node_cfg.get("TOOL_URL") and not node_cfg.get("URL"):
        raise ValueError(f"Node URL missing: {node_key}")
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
    if payload.get("config") is not None:
        node_data["config"] = payload["config"]
    if payload.get("services") is not None:
        node_data["services"] = payload["services"]

    response_data = {"nodes": {}}
    if node_data:
        response_data["nodes"][node_key] = node_data

    return {
        "_tool_text": format_node_tool_response(node, response),
        "_response_data": response_data,
    }


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


def parse_json_args(args_json: str) -> dict:
    if not str(args_json or "").strip():
        return {}
    data = json.loads(args_json)
    if not isinstance(data, dict):
        raise ValueError("args_json must be a JSON object")
    return data


def node_is_worker(node_cfg: dict) -> bool:
    role = str(node_cfg.get("ROLE", "worker")).strip().lower()
    return "worker" in role or role in {"", "both"}


def response_result_text(response: dict) -> str:
    result = response.get("result", "")
    if isinstance(result, dict):
        return str(result.get("analysis", result))
    return str(result)


def service_status_has_running(status_text: str) -> bool:
    return "RUNNING" in str(status_text)


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


def get_service_run_log_root() -> str:
    return os.path.join(get_service_log_root(), "services")


def get_service_log_dir(run_id: str = "latest") -> str:
    log_root = get_service_run_log_root()
    if run_id == "all":
        run_id = "latest"
    if not run_id or run_id == "latest":
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


def get_log_path(service: str, run_id: str = "latest"):
    return " ".join(shlex.quote(path) for path in get_log_paths(service, run_id))


def get_latest_service_log_run() -> str:
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


def list_service_log_runs_text(limit: int = 10) -> str:
    log_root = get_service_run_log_root()
    runs_dir = os.path.join(log_root, "runs")
    if not os.path.isdir(runs_dir):
        legacy_runs_dir = os.path.join(get_service_log_root(), "runs")
        if os.path.isdir(legacy_runs_dir):
            runs_dir = legacy_runs_dir
    latest_run = get_latest_service_log_run()

    if not os.path.isdir(runs_dir):
        return f"服务日志目录不存在或暂无启动记录: {runs_dir}"

    run_ids = [
        name
        for name in os.listdir(runs_dir)
        if os.path.isdir(os.path.join(runs_dir, name))
    ]
    if not run_ids:
        return f"暂无服务启动日志: {runs_dir}"

    run_ids.sort(
        key=lambda name: os.path.getmtime(os.path.join(runs_dir, name)),
        reverse=True,
    )
    limit = max(1, int(limit))

    lines = ["服务日志启动记录:"]
    if latest_run:
        lines.append(f"latest -> {latest_run}")
    else:
        lines.append("latest -> 未设置")

    for run_id in run_ids[:limit]:
        run_dir = os.path.join(runs_dir, run_id)
        mtime = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(run_dir))
        )
        log_names = sorted(
            name for name in os.listdir(run_dir) if name.endswith(".log")
        )
        marker = " *latest*" if run_id == latest_run else ""
        lines.append(
            f"- {run_id}{marker} | {mtime} | logs: "
            + (", ".join(log_names) if log_names else "none")
        )

    if len(run_ids) > limit:
        lines.append(f"... 还有 {len(run_ids) - limit} 条，可增大 limit 查看")

    return "\n".join(lines)


def get_service_start_latest_path() -> str:
    return os.path.join(get_service_run_log_root(), "latest.json")


def get_legacy_service_start_latest_path() -> str:
    return os.path.join(get_service_log_root(), "service_start_latest.json")


def service_start_status_text(run_id: str = "latest") -> str:
    log_root = get_service_run_log_root()
    if not run_id or run_id == "latest":
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
        if run_id and run_id != "latest":
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

    return "\n".join(lines)


def show_config() -> dict:
    """Show current service config"""
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


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


def check_port(port: int) -> bool:
    """Return True if port is listening."""
    cmd = f"lsof -i :{port}"
    code = subprocess.call(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return code == 0


def service_status_data() -> dict:
    """Check all service ports."""
    # lines = ["\n======== 推理服务状态 ========"]
    # CONFIG = show_config()

    # for name, port in CONFIG["PORTS"].items():
    #    running = check_port(port)
    #    mark = "RUNNING" if running else "STOPPED"
    #    lines.append(f"{name:20s} ({port}) : {mark}")

    # lines.append("============================\n")
    # return "\n".join(lines)

    lines = ["\n======== 推理服务状态 ========"]
    CONFIG = show_config()
    services = []

    for name, port in CONFIG["PORTS"].items():
        running = check_port(port)
        mark = "RUNNING" if running else "STOPPED"
        lines.append(f"{name:20s} ({port}) : {mark}")
        services.append(
            {
                "name": name,
                "port": int(port),
                "status": "running" if running else "stopped",
                "rawStatus": mark,
            }
        )

    lines.append("============================\n")
    # lines.append(f"Web UI: https://{CONFIG['ENV']['HOST_IP']}:{CONFIG['PORTS']['UI_PORT']}")
    # return "\n".join(lines)
    return {
        "services": services,
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
        param_billion = 72.0
        param_source = "default fallback"

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
    if item.get("recommended_ok"):
        return "满足保守预算"
    if item.get("ok"):
        return "满足最低需求"
    return "低于最低需求"


def format_gpu_budget_table(gpu_memory: Dict[str, tuple], mem_util: float) -> list[str]:
    lines = ["GPU预算:"]
    for idx, (used, total) in gpu_memory.items():
        planned_limit = gpu_vllm_planned_limit_mib(total, mem_util)
        budget = gpu_vllm_budget_mib(gpu_memory, idx, mem_util)
        lines.append(
            f"- GPU {idx}: total={total} MiB, used={used} MiB, "
            f"vllm_limit={planned_limit} MiB, budget={budget} MiB"
        )
    return lines


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
    ok = True
    for gid in gpu_ids:
        used, total = gpu_memory[gid]
        planned_limit = gpu_vllm_planned_limit_mib(total, mem_util)
        budget = gpu_vllm_budget_mib(gpu_memory, gid, mem_util)
        if budget < required_mib:
            ok = False
        details.append(
            {
                "gpu": gid,
                "used_mib": used,
                "total_mib": total,
                "vllm_planned_limit_mib": planned_limit,
                "vllm_budget_mib": budget,
                "recommended_mib": required_mib + margin_mib,
                "ok": budget >= required_mib,
                "recommended_ok": budget >= required_mib + margin_mib,
            }
        )

    return {
        "ok": ok,
        "reason": "" if ok else "insufficient_memory",
        "required_mib": required_mib,
        "recommended_mib": required_mib + margin_mib,
        "margin_mib": margin_mib,
        "total_mib": total_mib,
        "details": details,
    }


def recommend_gpu() -> dict:
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

    cfg = show_config()

    mem_util = float(cfg["RUNTIME"].get("GPU_MEMORY_UTILIZATION", 0.9))
    configured_visible = cfg["ENV"].get("CUDA_VISIBLE_DEVICES", "")
    configured_gpus = parse_visible_gpus(configured_visible)
    configured_tp = int(cfg["RUNTIME"].get("TENSOR_PARALLEL_SIZE", len(configured_gpus) or 1))
    profile = get_model_memory_profile(cfg)

    gpu_memory, error = get_gpu_memory_map()
    if error:
        return {"ok": False, "analysis": error}

    analysis_lines = describe_model_profile(profile)
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
            configured_gpus, configured_tp, gpu_memory, profile, mem_util
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
    analysis_lines.extend(format_gpu_budget_table(gpu_memory, mem_util))

    candidates = []
    for idx, (used, total) in gpu_memory.items():
        planned_limit = gpu_vllm_planned_limit_mib(total, mem_util)
        budget = gpu_vllm_budget_mib(gpu_memory, idx, mem_util)
        if budget > 0:
            candidates.append((idx, budget, planned_limit, total))

    candidates.sort(key=lambda x: x[1], reverse=True)
    if not candidates:
        return {
            "ok": False,
            "current_ok": current_ok,
            "analysis": "\n".join(analysis_lines) + "\n没有可用 GPU。",
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
            if min_budget >= current_eval["recommended_mib"]
            else "满足最低启动需求，但低于保守推荐预算"
        )
        analysis_lines.append("")
        analysis_lines.append("推荐:")
        analysis_lines.append(f"- GPU={','.join(configured_gpus)}, TP={configured_tp}")
        analysis_lines.append("- 理由: 当前 service.yaml 配置已满足最低启动需求，优先保持当前配置，避免无必要扩卡。")
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


def check_config_validity() -> dict:
    """
    Pre-startup configuration validity check.

    If the current configuration meets the running conditions, ok=True.
    If not, ok=False and return the reason for failure.
    """

    cfg = show_config()

    target_ip = cfg["ENV"]["HOST_IP"]
    visible = cfg["ENV"]["CUDA_VISIBLE_DEVICES"]
    model_path = cfg["ENV"]["MODEL_PATH"]
    model_name = cfg["ENV"]["MODEL_NAME"]
    start_script = cfg["ENV"]["START_SCRIPT"]
    tp_size = int(cfg["RUNTIME"]["TENSOR_PARALLEL_SIZE"])
    mem_util = float(cfg["RUNTIME"].get("GPU_MEMORY_UTILIZATION", 0.9))
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

    # ------------------------------------------------
    # 2. IP check
    # ------------------------------------------------
    host_ip = get_local_ip()

    if target_ip != host_ip:
        return {
            "ok": False,
            "reason": "ip_error",
            "analysis": f"ENV.HOST_IP 错误: {target_ip} 应改为 {host_ip}",
        }

    # ------------------------------------------------
    # 3. GPU List
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
        target_gpus, tp_size, gpu_memory, profile, mem_util
    )
    required_mib = current_eval["required_mib"]
    total_mib = current_eval["total_mib"]

    analysis_lines = []
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
            f"| {'满足保守预算' if item.get('recommended_ok') else ('满足最低需求' if item['ok'] else '低于最低需求')}"
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


def start_service() -> str:
    """Start inference service stack."""
    CONFIG = show_config()
    ports = CONFIG["PORTS"]
    env = CONFIG["ENV"]
    run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    log_root = get_service_run_log_root()
    run_log_dir = os.path.join(log_root, "runs", run_id)
    status_file = os.path.join(run_log_dir, "status.json")
    os.makedirs(run_log_dir, exist_ok=True)
    latest_link = os.path.join(log_root, "latest")
    try:
        if os.path.lexists(latest_link):
            os.unlink(latest_link)
        os.symlink(os.path.join("runs", run_id), latest_link)
    except OSError:
        pass
    proc_env = os.environ.copy()
    proc_env["SERVICE_RUN_ID"] = run_id
    proc = subprocess.Popen(
        ["bash", env["START_SCRIPT"], "start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=proc_env,
    )
    atomic_write_json(
        status_file,
        {
            "run_id": run_id,
            "status": "starting",
            "script_pid": proc.pid,
            "config_profile": "service",
            "config_file": "../config/service.yaml",
            "log_dir": run_log_dir,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
            "ports": {
                "vllm": ports["VLLM_OPENAI_PORT"],
                "inference": ports["INFERENCE_PORT"],
                "ui": ports["UI_PORT"],
                "case2chat": ports["DATA_ANNOTATION_PORT"],
            },
            "error": None,
        },
    )
    atomic_write_json(
        get_service_start_latest_path(),
        {
            "run_id": run_id,
            "status_file": status_file,
        },
    )

    return (
        "启动任务已提交，正在后台启动。\n"
        f"run_id: {run_id}\n"
        f"模型: {env['MODEL_NAME']}\n"
        f"模型路径: {env['MODEL_PATH']}{env['MODEL_NAME']}\n"
        f"HOST_IP: {env['HOST_IP']}\n"
        "端口:\n"
        f"- vLLM OpenAI API: {ports['VLLM_OPENAI_PORT']}\n"
        f"- Inference Server: {ports['INFERENCE_PORT']}\n"
        f"- Web UI: {ports['UI_PORT']}\n"
        f"- Case2Chat: {ports['DATA_ANNOTATION_PORT']}\n"
        "启动任务已提交不代表服务已启动完成。\n"
        "除非用户明确要求继续执行其他操作，否则请直接返回以上信息，不要继续调用 service_status、service_start_status 或日志工具。"
    )
    # f"- Voice: {ports.get('VOICE_PORT', 9007)}"
    # "您可以稍后调用 service_start_status() 查看推理启动状态。"


def stop_service() -> str:
    """Stop inference service stack."""
    CONFIG = show_config()
    run_command(f"bash {CONFIG['ENV']['START_SCRIPT']} stop")
    return "Service stopped!"


def tail_logs(service: str = "start", lines: int = 30, run_id: str = "latest") -> str:
    """Summarize important messages in log."""
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
    return run_command(f"ls {TEST_DIR}/*.sh 2>/dev/null | xargs -n1 basename")


def get_test_log_root() -> str:
    return os.path.join(get_service_log_root(), "tests")


def get_test_latest_path() -> str:
    return os.path.join(get_test_log_root(), "test_latest.json")


def get_test_status_path(test_run_id: str) -> str:
    if "/" in test_run_id or ".." in test_run_id:
        raise ValueError("Invalid test_run_id")
    return os.path.join(get_test_log_root(), "runs", test_run_id, "status.json")


def resolve_test_run_id(test_run_id: str = "latest") -> str:
    if test_run_id and test_run_id != "latest":
        return test_run_id
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


def running_tests_text() -> str:
    runs_dir = os.path.join(get_test_log_root(), "runs")
    if not os.path.isdir(runs_dir):
        return f"暂无功能测试运行记录: {runs_dir}"

    running_items = []
    for test_run_id in sorted(os.listdir(runs_dir), reverse=True):
        status_file = os.path.join(runs_dir, test_run_id, "status.json")
        if not os.path.isfile(status_file):
            continue
        try:
            with open(status_file, "r") as f:
                meta = json.load(f)
        except json.JSONDecodeError:
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
                    }
                )

    if not running_items:
        return (
            "当前没有正在运行的功能测试脚本。\n"
            f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    lines = [
        "正在运行的功能测试脚本:",
        f"current_time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"running={len(running_items)}",
    ]
    for item in running_items:
        lines.append(
            "- "
            f"test_run_id={item['test_run_id']}, "
            f"test_name={item.get('test_name')}, "
            f"script={item.get('script')}, "
            f"pid={item.get('pid')}, "
            f"port={item.get('port')}, "
            f"started_at={item.get('started_at')}, "
            f"log_file={item.get('log_file')}"
        )
    return "\n".join(lines)


def monitor_test_job(test_run_id: str, proc: subprocess.Popen, status_file: str):
    exit_code = proc.wait()
    with open(status_file, "r") as f:
        meta = json.load(f)
    if meta.get("status") != "running":
        return
    meta["status"] = "finished" if exit_code == 0 else "failed"
    meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["exit_code"] = exit_code
    atomic_write_json(status_file, meta)


def update_all_test_status(status_file: str, update_fn):
    with open(status_file, "r") as f:
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
        with open(status_file, "r") as f:
            meta = json.load(f)
        if meta.get("status") != "running":
            mark_remaining_tests(meta.get("tests", {}), "stopped")
            meta["finished_at"] = meta.get("finished_at") or time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            atomic_write_json(status_file, meta)
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
                preexec_fn=os.setsid,
            )

        def mark_running(meta):
            item = meta["tests"][script_name]
            item["status"] = "running"
            item["pid"] = proc.pid
            item["port"] = port
            item["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        update_all_test_status(status_file, mark_running)
        exit_code = proc.wait()

        with open(status_file, "r") as f:
            meta = json.load(f)
        if meta.get("status") != "running":
            if is_process_running(proc.pid):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            item = meta["tests"][script_name]
            item["status"] = "stopped"
            item["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            item["exit_code"] = None
            mark_remaining_tests(meta.get("tests", {}), "stopped")
            meta["finished_at"] = meta.get("finished_at") or time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            atomic_write_json(status_file, meta)
            return

        item = meta["tests"][script_name]
        item["status"] = "finished" if exit_code == 0 else "failed"
        item["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        item["exit_code"] = exit_code
        item["pid"] = proc.pid
        failed = failed or exit_code != 0
        atomic_write_json(status_file, meta)

    with open(status_file, "r") as f:
        meta = json.load(f)
    if meta.get("status") != "running":
        return
    meta["status"] = "failed" if failed else "finished"
    meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["exit_code"] = 1 if failed else 0
    atomic_write_json(status_file, meta)


def start_test_job(
    test_name: str = "basicmedicalrecord.sh", run_all: bool = False
) -> str:
    CONFIG = show_config()
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
                preexec_fn=os.setsid,
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
        f"test_name: {selected_test}\n"
        f"script_pid: {None if run_all else proc.pid}\n"
        f"log_file: {format_agent_relative_path(log_file)}\n"
        "可调用 service_test_status(test_run_id) 查看测试状态。"
    )


def test_status_text(test_run_id: str = "latest", lines: int = 30) -> str:
    if test_run_id == "all":
        return running_tests_text()

    try:
        test_run_id = resolve_test_run_id(test_run_id)
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


def test_stop_text(test_run_id: str = "latest") -> str:
    try:
        test_run_id = resolve_test_run_id(test_run_id)
        status_file = get_test_status_path(test_run_id)
    except FileNotFoundError as e:
        return str(e)
    except ValueError:
        return "Invalid test_run_id"

    if not os.path.exists(status_file):
        return f"测试状态文件不存在: {status_file}"

    with open(status_file, "r") as f:
        meta = json.load(f)

    status = meta.get("status")
    script_pid = int(meta.get("script_pid") or 0)
    if status != "running":
        return (
            f"测试任务无需停止: status={status}, test_run_id={test_run_id}, "
            f"log_file={format_test_path(meta.get('log_file'))}"
        )

    tests = meta.get("tests") or {}
    if tests:
        stopped_pid = None
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

        meta["status"] = "stopped"
        meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["exit_code"] = None
        mark_remaining_tests(tests, "stopped")
        atomic_write_json(status_file, meta)
        return (
            f"测试任务已停止: test_run_id={test_run_id}, pid={stopped_pid}\n"
            f"log_file={format_test_path(meta.get('log_file'))}"
        )

    if not script_pid or not is_process_running(script_pid):
        meta["status"] = "stopped"
        meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["exit_code"] = None
        atomic_write_json(status_file, meta)
        return f"测试进程已不存在，状态已标记为 stopped: test_run_id={test_run_id}"

    try:
        os.killpg(os.getpgid(script_pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        return f"停止测试失败: test_run_id={test_run_id}, pid={script_pid}, error={e}"

    meta["status"] = "stopped"
    meta["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["exit_code"] = None
    atomic_write_json(status_file, meta)
    return (
        f"测试任务已停止: test_run_id={test_run_id}, pid={script_pid}\n"
        f"log_file={format_test_path(meta.get('log_file'))}"
    )


def start_single_test(test_name: str) -> str:
    """Run a specific test script."""
    return start_test_job(test_name=test_name, run_all=False)


def start_all_tests() -> str:
    """Run all test scripts in test directory."""
    return start_test_job(run_all=True)


def restart_service_stack() -> str:
    """Restart inference service stack."""
    stop_result = stop_service()
    time.sleep(10)
    config_msg = check_config_validity()
    if not config_msg["ok"]:
        return (
            "旧服务已停止，并已等待 15 秒释放 GPU 资源，但重启前检查不通过，新服务未启动。\n"
            f"停止结果: {stop_result}\n"
            f"原因: {config_msg['reason']}\n"
            f"分析: {config_msg['analysis']}"
        )
    return start_service()


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
    """Update service config value."""
    if isinstance(value, str):
        run_command(f"yq -y -i '.{key} = \"{value}\"' {CONFIG_FILE}")
    else:
        run_command(f"yq -y -i '.{key} = {value}' {CONFIG_FILE}")
    return f"更新配置文件 {CONFIG_FILE}: .{key} = {value}"


def restore_default_config() -> str:
    """Restore config file from default backup."""
    run_command(f"cp {DEFAULT_CONFIG_FILE} {CONFIG_FILE}")
    return "Configuration restored to defaults."


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


def resolve_medical_choice_dataset_path(dataset: str) -> str:
    benchmark_dir = get_medical_benchmark_dir()
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


def medical_choice_candidates(dataset: str) -> str:
    choice_dir = get_medical_choice_dir()
    if not os.path.isdir(choice_dir):
        return f"医疗选择题目录不存在: {choice_dir}"
    files = sorted(f for f in os.listdir(choice_dir) if f.endswith(".json"))
    return format_dataset_candidates(files, dataset)


def medbench_candidates(dataset: str) -> str:
    medbench_dir = get_medbench_dir()
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


def run_medical_choice_benchmark(
    dataset: str, max_workers: int = 5, save_every: int = 2
) -> str:
    """Start a benchmark evaluation job (runs asynchronously in the background)."""

    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"

    cfg = show_config()
    model = cfg["ENV"]["MODEL_NAME"]
    benchmark_dir = get_medical_benchmark_dir()
    log_dir = get_benchmark_log_dir()
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"
    dataset_path = resolve_medical_choice_dataset_path(dataset)

    if not os.path.exists(dataset_path):
        return f"Benchmark dataset not found: {dataset}\n" + medical_choice_candidates(
            dataset
        )
    if not os.path.isfile(dataset_path):
        return f"Benchmark dataset is not a file: {dataset}"

    job_dir = os.path.join(log_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    meta_file = os.path.join(job_dir, "meta.json")
    log_file = os.path.join(job_dir, "run.log")
    output_file = os.path.join(job_dir, "result.json")

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
    log_f = open(log_file, "w")

    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    pid = proc.pid

    with open(meta_file, "w") as f:
        json.dump(
            {
                "job_id": job_id,
                "pid": pid,
                "model": model,
                "dataset": dataset,
                "mode": "eval",
                "log": log_file,
                "output": output_file,
                "start_time": start_time,
                "status": "running",
                "return_code": None,
                "end_time": "",
            },
            f,
            indent=2,
        )

    threading.Thread(
        target=monitor_job, args=(job_id, proc, meta_file), daemon=True
    ).start()

    return (
        "Benchmark任务已启动:\n"
        f"job_id={job_id}\n"
        f"pid={pid}\n"
        f"model={model}\n"
        f"dataset={dataset}\n"
        "benchmark_type=medical_choice\n"
        f"log_file={format_agent_relative_path(log_file)}\n"
        f"output={format_agent_relative_path(output_file)}\n"
        "可调用 benchmark_report(job_id) 查看进度和结果。"
    )


def list_benchmark_jobs_text() -> str:
    """List all benchmark jobs with their current status."""

    cfg = show_config()
    base = get_benchmark_log_dir()

    if not os.path.exists(base):
        return "暂无任务"

    jobs = []

    for job_id in os.listdir(base):
        meta_path = os.path.join(base, job_id, "meta.json")
        if not os.path.exists(meta_path):
            continue

        meta = json.load(open(meta_path))

        jobs.append(
            f"{meta['job_id']} | {meta['model']} | {meta['dataset']} | {meta['status']}"
        )

    return "\n".join(jobs) if jobs else "暂无任务"


def stop_benchmark_job(job_id: str) -> str:
    """Stop a running benchmark job."""

    cfg = show_config()
    job_dir = os.path.join(get_benchmark_log_dir(), job_id)
    meta_file = os.path.join(job_dir, "meta.json")

    if not os.path.exists(meta_file):
        return f"not found: {meta_file}"

    meta = json.load(open(meta_file))
    pid = int(meta["pid"])

    if meta["status"] == "running":
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)

            meta["status"] = "stopped"
            meta["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # add, for medbench stop
            if "progress" in meta and "files" in meta["progress"]:
                for file_stat in meta["progress"]["files"].values():
                    if file_stat.get("status") == "running":
                        file_stat["status"] = "stopped"

            with open(meta_file, "w") as f:
                json.dump(meta, f, indent=2)

            return f"stopped successfully: job_id={job_id} pid={pid}"

        except Exception as e:
            return f"error: {str(e)}"

    elif meta["status"] == "finished":
        return "already finished: no action taken"

    elif meta["status"] == "stopped":
        return "already stopped: no action taken"

    else:
        return f"unvalid status: {meta['status']}"


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


def run_medbench_benchmark(dataset: str, max_workers: int = 5) -> str:
    """Start a medbench evaluation job (runs asynchronously in the background)."""

    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"

    cfg = show_config()
    model = cfg["ENV"]["MODEL_NAME"]
    benchmark_dir = get_medical_benchmark_dir()
    log_dir = get_benchmark_log_dir()
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"

    try:
        dataset_path = resolve_medbench_dataset_path(benchmark_dir, dataset)
    except ValueError:
        return f"Invalid dataset path: {dataset}"

    if not os.path.exists(dataset_path):
        return (
            f'Not Found: {dataset_path}. Please use `benchmark_list(benchmark_type="medbench")` to check available MedBench jsonl files, \
            or run the entire dataset: medical/medbench.\n'
            + medbench_candidates(dataset)
        )
    if dataset.endswith(".jsonl"):
        # dataset_type = "file"
        files = [os.path.basename(dataset_path)]
    else:
        # dataset_type = "folder"
        files = [f for f in os.listdir(dataset_path) if f.endswith(".jsonl")]

    job_dir = os.path.join(log_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    meta_file = os.path.join(job_dir, "meta.json")
    log_file = os.path.join(job_dir, "run.log")
    output_dir = os.path.join(job_dir, "results")
    os.makedirs(output_dir, exist_ok=True)

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
    log_f = open(log_file, "w")

    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    pid = proc.pid

    with open(meta_file, "w") as f:
        json.dump(
            {
                "job_id": job_id,
                "pid": pid,
                "model": model,
                "mode": "medbench",
                "dataset": dataset,
                "input_dir": dataset_path
                if os.path.isdir(dataset_path)
                else os.path.dirname(dataset_path),
                # "dataset_type": dataset_type,
                "files": files,
                "log": log_file,
                "output": output_dir,
                "start_time": start_time,
                "status": "running",
                "return_code": None,
                "end_time": "",
            },
            f,
            indent=2,
        )

    threading.Thread(
        target=monitor_medbench_job, args=(job_id, proc, meta_file), daemon=True
    ).start()

    return (
        "MedBench任务已启动:\n"
        f"job_id={job_id}\n"
        f"pid={pid}\n"
        f"model={model}\n"
        f"dataset={dataset}\n"
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
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def medbench_progress_text(job_id: str) -> str:
    """Get MedBench job progress summary."""

    cfg = show_config()
    meta_file = os.path.join(get_benchmark_log_dir(), job_id, "meta.json")

    if not os.path.exists(meta_file):
        return f"未找到任务: {job_id}"

    with open(meta_file, "r") as f:
        meta = json.load(f)

    status = meta.get("status", "unknown")
    dataset = meta.get("dataset", "")
    model = meta.get("model", "")
    # dataset_type = meta.get("dataset_type", "")
    start_time = meta.get("start_time", "")
    end_time = meta.get("end_time", "")
    progress = meta.get("progress", {})
    files = progress.get("files", [])
    output = meta.get("output", "")

    if not files:
        return f"""任务 {job_id}
状态: {status}
数据集: {dataset}
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
    lines.append(f"开始时间: {start_time}")
    lines.append(f"结束时间: {end_time}")
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


def general_benchmark_inspect(dataset: str, split: str = "default") -> str:
    """Inspect a supported public benchmark dataset."""
    output = run_general_runner(
        [
            "--action",
            "inspect",
            "--dataset-root",
            get_general_benchmark_dir(),
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
) -> str:
    """Start a public benchmark job (runs asynchronously in the background)."""
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"

    cfg = show_config()
    model = cfg["ENV"]["MODEL_NAME"]
    log_dir = get_benchmark_log_dir()
    general_dir = get_general_benchmark_dir()
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"

    if not os.path.exists(general_dir):
        return f"GENERAL_BENCHMARK_DIR not found: {general_dir}"

    inspect_output = general_benchmark_inspect(dataset, split)
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
    job_dir = os.path.join(log_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    meta_file = os.path.join(job_dir, "meta.json")
    log_file = os.path.join(job_dir, "run.log")
    output_file = os.path.join(job_dir, "result.json")

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

    log_f = open(log_file, "w")
    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    pid = proc.pid

    dataset_key = dataset.strip().lower().replace("_", "-")
    meta = {
        "job_id": job_id,
        "pid": pid,
        "model": model,
        "dataset": dataset,
        "split": split,
        "mode": "general",
        "log": log_file,
        "output": output_file,
        "start_time": start_time,
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

    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

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
        "benchmark_type=general\n"
        f"log_file={format_agent_relative_path(log_file)}\n"
        f"output={format_agent_relative_path(output_file)}\n"
        "可调用 benchmark_report(job_id) 查看进度和结果。"
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


def infer_benchmark_type(dataset: str, split: str = "default") -> str:
    name = dataset.strip()
    lowered = name.lower()

    if lowered.endswith(".jsonl") or "medbench" in lowered:
        return "medbench"
    if lowered.endswith(".json") or lowered.startswith(("medical/choice/", "medical_choice/", "choice/")):
        return "medical_choice"

    choice_path = resolve_medical_choice_dataset_path(name)
    if os.path.isfile(choice_path):
        return "medical_choice"

    inspect_output = general_benchmark_inspect(name, split)
    if not inspect_output.startswith("[ERROR]"):
        return "general"

    try:
        medbench_path = resolve_medbench_dataset_path(get_medical_benchmark_dir(), name)
        if os.path.exists(medbench_path):
            return "medbench"
    except ValueError:
        pass

    return "unknown"


def correct_benchmark_type(dataset: str, benchmark_type: str, split: str = "default"):
    inferred = infer_benchmark_type(dataset, split)
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
) -> str:
    """Run a benchmark job by unified type."""
    benchmark_type = normalize_benchmark_type(benchmark_type)
    benchmark_type, correction_note = correct_benchmark_type(
        dataset, benchmark_type, split
    )

    if benchmark_type == "general":
        return correction_note + run_general_benchmark_job(
            dataset,
            split,
            max_workers,
            limit if limit > 0 else None,
            save_every,
        )

    if benchmark_type == "medical_choice":
        return correction_note + run_medical_choice_benchmark(
            dataset, max_workers, save_every
        )

    if benchmark_type == "medbench":
        return correction_note + run_medbench_benchmark(dataset, max_workers)

    return (
        f"无法识别数据集类型: dataset={dataset}, benchmark_type={benchmark_type}。\n"
        "请先调用 benchmark_list 或显式指定 benchmark_type=general/medical_choice/medbench。"
    )


def benchmark_report_text(job_id: str) -> str:
    """Return benchmark status, progress and available result metrics."""
    meta_path = os.path.join(get_benchmark_log_dir(), job_id, "meta.json")
    if not os.path.exists(meta_path):
        return f"job_id 不存在: {job_id}"

    meta = json.load(open(meta_path))
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
        lines.append("note=任务仍在运行，以上为当前已保存的中间结果。")
    else:
        lines.append("note=任务已结束，以上为最终结果。")

    return "\n".join(lines)


@tool
def get_ip() -> str:
    """Show current ip"""
    return get_local_ip()


@tool
def config_show() -> dict:
    """Show current service config"""
    config = show_public_config()
    return build_local_tool_response(config, {"config": config})


@tool
def service_status() -> dict:
    """Check current inference service ports.

    Use this for current running/stopped port status. If the user asks whether a
    background startup has completed, use service_start_status instead.
    """
    status = service_status_data()
    return build_local_tool_response(status["text"], {"services": status["services"]})


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
    """Recommend gpu allocation."""
    return recommend_gpu()


@tool
def config_check() -> dict:
    """Check configuration before starting service."""
    config_msg = check_config_validity()
    if config_msg["ok"]:
        return {"ok": True, "msg": f"检查通过。\n分析：{config_msg['analysis']}"}
    else:
        return {
            "ok": False,
            "msg": f"检查不通过。\n原因：{config_msg['reason']}\n分析：{config_msg['analysis']}",
        }


@tool
def service_start() -> str:
    """Start the full inference service stack.

    Prerequisites:
    1. Execute service_status() - if any services are running, run service_stop() before proceeding
    2. Execute config_check()

    Startup runs asynchronously. Do not immediately call service_status after
    this tool. Use service_start_status after a short wait or when the user asks
    for startup progress.
    """

    return start_service()


@tool
def service_start_status(run_id: str = "latest") -> str:
    """Check background service startup status.

    Use this when users ask whether startup has finished, whether the service has
    started successfully, or what the startup progress is.

    Args:
    - run_id: startup run id, or "latest" for the latest startup.
    """

    return service_start_status_text(run_id)


@tool
def service_stop() -> str:
    """Stop all inference services."""
    return stop_service()


@tool
def service_restart() -> str:
    """Restart all inference services.

    Prerequisites:
    1. Execute service_status() - if any services are running, run service_stop() before proceeding
    2. Execute config_check()
    """

    return restart_service_stack()


@tool
def service_log_runs(limit: int = 10) -> str:
    """
    List recent service log runs.

    Purpose:
    - Discover available service startup run IDs.
    - Check which run ID "latest" points to before calling service_log_tail,
      service_log_search, or service_log_context with a specific run_id.
    - Use this before service_log_tail/service_log_search/service_log_context
      when the user asks for historical logs or run_id is unknown.

    Args:
        limit: maximum number of recent runs to list.
    """

    return list_service_log_runs_text(limit)


@tool
def service_log_tail(
    service: str = "start", lines: int = 30, run_id: str = "latest"
) -> str:
    """
    Summarize important messages in log.

    Shows three sections:
    - ERRORS: grep for error|exception|fail|traceback|timeout|critical (last 20 matches)
    - WARNINGS: grep for warn (last 20 matches)
    - LAST LOG: last N lines with line numbers

    If the user asks for historical logs or provides no clear run_id, call
    service_log_runs first to discover valid run IDs. Use run_id="latest" only
    when the user asks for the latest/current service logs.

    Args:
        service: one of ["start","vllm","inference","ui","web","case2chat"]
        lines: number of recent log lines to show (default: 30)
        run_id: service startup run id, or "latest" for the newest run.
                Do not use "all" here; use service="all" to search all service logs.
    """

    return tail_logs(service, lines, run_id)


@tool
def service_log_search(
    keyword: str = "error",
    service: str = "all",
    lines: int = 20,
    run_id: str = "latest",
) -> str:
    """
    Search keyword or extended regex in logs with case-insensitive matching.

    If the user asks for historical logs or provides no clear run_id, call
    service_log_runs first to discover valid run IDs. Use run_id="latest" only
    when the user asks for the latest/current service logs.

    Args:
        keyword: search text or extended regex, case-insensitive
                 (e.g., error, exception, "runtime|memory|permission denied", etc.)
        service: specific service or "all"
        line: number of results
        run_id: service startup run id, or "latest" for the newest run.
                Do not use "all" here; use service="all" to search all service logs.
    """

    return logs_search(keyword, service, lines, run_id)


@tool
def service_log_context(
    service: str, index: int, window: int = 20, run_id: str = "latest"
) -> str:
    """
    Show log context around a specific line.

    If the user asks for historical logs or provides no clear run_id, call
    service_log_runs first to discover valid run IDs. Use run_id="latest" only
    when the user asks for the latest/current service logs.

    Args:
        service: log name
        index: line number
        window: lines before and after
        run_id: service startup run id, or "latest" for the newest run.
                Do not use "all" here.
    """

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
def service_test_run(test_name: str = "basicmedicalrecord.sh") -> str:
    """
    Run a specific test script.

    This function runs an individual test script and returns the execution results.
    By default, it runs the basic medical record test if no test name is specified.

    Args:
        test_name (str, optional): Name of the test script to execute.
                                   Defaults to "basicmedicalrecord.sh".
                                   Example: "diagnosis.sh", "inpatient.sh"

    """

    return start_single_test(test_name)


@tool
def service_test_run_all() -> str:
    """Run all test scripts in test directory."""
    return start_all_tests()


@tool
def service_test_status(test_run_id: str = "latest", lines: int = 30) -> str:
    """
    Check background service test status.

    Args:
        test_run_id: test run id, or "latest" for the latest submitted test.
                     Use "all" to list all currently running test scripts.
        lines: number of recent log lines to include.
    """

    return test_status_text(test_run_id, lines)


@tool
def service_test_stop(test_run_id: str = "latest") -> str:
    """
    Stop a running background service test.

    Args:
        test_run_id: test run id, or "latest" for the latest submitted test.
    """

    return test_stop_text(test_run_id)


@tool
def config_keys() -> str:
    """
    Return all valid config keys that can be updated.
    LLM must choose one of these keys before calling config_update.
    """

    cfg = show_config()
    keys = flatten_config_keys(cfg)
    return "\n".join(keys)


@tool
def config_update(key: str, value: str) -> dict | str:
    """
    Update config value. Key must be one of config_keys().
    CUDA_VISIBLE_DEVICES GPU count must equal RUNTIME.TENSOR_PARALLEL_SIZE.
    """

    valid = flatten_config_keys(show_config())

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
    text = update_config(key, value)
    return build_local_tool_response(text, {"config": show_public_config()})


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

    Args:
    - dataset: Dataset key or file name.
    - benchmark_type: auto, general, medical_choice, or medbench.
    - split: General benchmark split.
    - max_workers: Concurrent model requests.
    - limit: Optional sample limit for general benchmarks. Use 0 for full dataset.
    - save_every: Save partial result every N completed samples.
    """

    return benchmark_run_unified(
        dataset, benchmark_type, split, max_workers, limit, save_every
    )


@tool
def benchmark_report(job_id: str) -> str:
    """
    Retrieve benchmark report by job_id.

    The report includes status, progress, partial results, final metrics, log path
    and output path. Use this for user requests about benchmark progress, result,
    score, completion state, or "how is this job going".
    """

    return benchmark_report_text(job_id)


@tool
def benchmark_jobs() -> str:
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
    """

    return list_benchmark_jobs_text()


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

    lines = ["多节点推理 Agent 配置:"]
    for key, node in nodes.items():
        enabled = is_node_enabled(node)
        if not enabled and not show_disabled:
            continue
        lines.append(
            " | ".join(
                [
                    f"node={key}",
                    f"name={node.get('NAME', key)}",
                    f"enabled={enabled}",
                    f"role={node.get('ROLE', '')}",
                    f"host={node.get('HOST', '')}",
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
def node_service_status(node: str) -> str:
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

    response = call_node_tool(node, "service_status")
    return build_node_tool_response(node, response)


@tool
def node_gpu_status(node: str) -> str:
    """
    Check one remote node's local GPU status.

    Use this controller-side tool when the user explicitly specifies a node
    such as node1/main or asks for multi-node GPU status. This only reports GPU
    usage on the selected remote node; it does not modify config or start
    service.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    response = call_node_tool(node, "gpu_status")
    return format_node_tool_response(node, response)


@tool
def node_config_show(node: str) -> str:
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

    response = call_node_tool(node, "config_show")
    return build_node_tool_response(node, response)


@tool
def node_config_keys(node: str) -> str:
    """
    Return config keys that can be updated on one remote node.

    Call this before node_config_update when the user gives an imprecise key
    name such as "GPU", "TP", "model", or "port". The update key must be one of
    the returned keys or a unique suffix accepted by the remote worker.
    """

    response = call_node_tool(node, "config_keys")
    return format_node_tool_response(node, response)


@tool
def node_config_update(node: str, key: str, value: str) -> str:
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

    response = call_node_tool(node, "config_update", {"key": key, "value": value})
    return build_node_tool_response(node, response)


@tool
def node_port_status(node: str, port: int) -> str:
    """
    Check one port status on one remote node.

    Use this for a specific remote port such as VLLM, inference API, UI, or data
    annotation port. Use node_service_status when the user wants the full remote
    service status.
    """

    response = call_node_tool(node, "port_status", {"port": port})
    return format_node_tool_response(node, response)


@tool
def node_model_list(node: str) -> str:
    """
    List available models on one remote node.

    Use this before node_config_update when the user wants to switch model but
    has not provided the exact model name/path available on that node.
    """

    response = call_node_tool(node, "model_list")
    return format_node_tool_response(node, response)


@tool
def node_config_check(node: str) -> str:
    """
    Check whether one remote node's service config is valid before startup.

    This validates the selected node's current service.yaml, model path, GPU
    allocation, tensor parallel size, and ports. It does not start, stop, or
    modify anything.
    """

    response = call_node_tool(node, "config_check")
    return format_node_tool_response(node, response)


@tool
def node_gpu_recommend_allocation(node: str) -> str:
    """
    Recommend GPU allocation for one remote node.

    Use this when deciding which GPUs and tensor parallel size to use on that
    node. This is analysis only: it does not update CUDA_VISIBLE_DEVICES, does
    not update TENSOR_PARALLEL_SIZE, and does not start service. After choosing
    a recommendation, call node_config_update for the required config keys, then
    node_service_start.
    """

    response = call_node_tool(node, "gpu_recommend_allocation")
    return format_node_tool_response(node, response)


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

    preferred_key = ""
    if str(target_node or "auto").strip().lower() not in {"", "auto"}:
        try:
            preferred_key, _ = resolve_node_config(target_node)
        except Exception as e:
            return f"目标节点无效: {target_node}\nerror={e}"

    candidates = []
    skipped = []

    for node_key, node_cfg in nodes.items():
        if not is_node_enabled(node_cfg):
            skipped.append(f"{node_key}: disabled")
            continue
        if not node_is_worker(node_cfg):
            skipped.append(f"{node_key}: not worker")
            continue

        try:
            status_response = call_node_tool(node_key, "service_status")
            status_text = response_result_text(status_response)
            if service_status_has_running(status_text):
                skipped.append(f"{node_key}: service already running")
                continue

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
        f"- 推荐配置: ENV.CUDA_VISIBLE_DEVICES={best['recommended_gpus']}, "
        f"RUNTIME.TENSOR_PARALLEL_SIZE={best['recommended_tp']}"
    )
    if best.get("current_ok"):
        lines.append("- 说明: 推荐节点当前 service.yaml 已满足最低启动需求，可直接调用 node_service_start。")
    else:
        lines.append("- 说明: 推荐节点需要先按推荐配置更新 service.yaml，再启动。")

    lines.append("")
    lines.append("后续操作建议:")
    if not best.get("current_ok"):
        lines.append(
            f"1. node_config_update(node='{best['node']}', key='ENV.CUDA_VISIBLE_DEVICES', "
            f"value='{best['recommended_gpus']}')"
        )
        lines.append(
            f"2. node_config_update(node='{best['node']}', key='RUNTIME.TENSOR_PARALLEL_SIZE', "
            f"value='{best['recommended_tp']}')"
        )
        lines.append(f"3. node_service_start(node='{best['node']}')")
    else:
        lines.append(f"1. node_service_start(node='{best['node']}')")
        lines.append(f"2. node_service_start_status(node='{best['node']}', run_id='latest')")

    lines.append("")
    lines.append("候选节点摘要:")
    for item in usable:
        status = "current_ok" if item.get("current_ok") else "needs_config_update"
        lines.append(
            f"- {item['node']}: {status}, gpu={item.get('recommended_gpus')}, "
            f"tp={item.get('recommended_tp')}"
        )
    if skipped:
        lines.append("跳过节点:")
        lines.extend(f"- {item}" for item in skipped)

    return "\n".join(lines)


@tool
def node_service_start(node: str) -> str:
    """
    Start one remote node's local inference service.

    Use this controller-side tool only when the user explicitly specifies a node
    such as node1/main. The remote node will run its own service_start policy
    checks before starting.

    This tool only starts the service with the node's current service.yaml.
    It does not modify CUDA_VISIBLE_DEVICES, TENSOR_PARALLEL_SIZE, model name,
    ports, or any other config.

    If the user requested any config change before startup, such as "use GPU 0",
    "set TP=1", "switch model", or "change port", call node_config_update for
    every requested config change first. Only call node_service_start after all
    required node_config_update calls have succeeded.

    If this tool returns blocked/insufficient_memory, call
    node_recommend_start_target with the same node to find another available
    node.

    Startup runs asynchronously. Do not immediately call node_service_status
    after this tool. Use node_service_start_status after a short wait or when
    the user asks for startup progress.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    response = call_node_tool(node, "service_start")
    return append_start_target_hint(format_node_tool_response(node, response), node)


@tool
def node_service_start_status(node: str, run_id: str = "latest") -> str:
    """
    Check one remote node's latest service start task status.

    Use this after node_service_start or node_service_restart when the user asks
    whether startup has finished, whether startup succeeded, or what the startup
    progress is.

    Args:
        node: node key/name/host from nodes.yaml.
        run_id: service start run_id on that node, or latest.
    """

    response = call_node_tool(node, "service_start_status", {"run_id": run_id})
    return format_node_tool_response(node, response)


@tool
def node_service_stop(node: str) -> str:
    """
    Stop one remote node's local inference service.

    Use this controller-side tool when the user explicitly specifies a node such
    as node1/main or asks to stop service on a remote node. This stops the
    remote node's local service stack only; it does not disable the node in
    nodes.yaml. Use node_disable separately if the user wants to disable routing
    after service is stopped.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    response = call_node_tool(node, "service_stop")
    return format_node_tool_response(node, response)


@tool
def node_service_restart(node: str) -> str:
    """
    Restart one remote node's local inference service.

    Use this controller-side tool when the user explicitly specifies a node such
    as node1/main. The remote node restarts with its current service.yaml.

    This tool does not modify GPU, TP, model, or port config. If the user asks
    to change config and restart, call node_config_update for every requested
    change first, then call node_service_restart. Use node_service_start_status
    afterwards to check startup progress.

    Args:
        node: node key/name/host from nodes.yaml.
    """

    response = call_node_tool(node, "service_restart")
    return format_node_tool_response(node, response)


@tool
def node_service_log_runs(node: str, limit: int = 10) -> str:
    """
    List recent service log runs on one remote node.

    Use this to discover valid run_id values before calling
    node_service_log_tail, node_service_log_search, or node_service_log_context
    for historical logs. Use run_id="latest" only for the newest/current logs.
    """

    response = call_node_tool(node, "service_log_runs", {"limit": limit})
    return format_node_tool_response(node, response)


@tool
def node_service_log_tail(
    node: str,
    service: str = "all",
    lines: int = 80,
    run_id: str = "latest",
) -> str:
    """
    Summarize important service log messages on one remote node.

    Use this to inspect errors, warnings, and recent log lines for one remote
    startup run. If the user asks for historical logs and no run_id is clear,
    call node_service_log_runs first.

    Args:
        node: node key/name/host from nodes.yaml.
        service: one of start, vllm, inference, ui, web, case2chat, or all.
        lines: number of recent lines to include.
        run_id: service startup run id, or latest.
    """

    response = call_node_tool(
        node,
        "service_log_tail",
        {"service": service, "lines": lines, "run_id": run_id},
    )
    return format_node_tool_response(node, response)


@tool
def node_service_log_search(
    node: str,
    keyword: str = "error",
    service: str = "all",
    lines: int = 20,
    run_id: str = "latest",
) -> str:
    """
    Search service logs on one remote node.

    The keyword can be plain text or an extended regex and is matched
    case-insensitively. Use service="all" to search all service logs on that
    node. If the user asks for historical logs and no run_id is clear, call
    node_service_log_runs first.
    """

    response = call_node_tool(
        node,
        "service_log_search",
        {"keyword": keyword, "service": service, "lines": lines, "run_id": run_id},
    )
    return format_node_tool_response(node, response)


@tool
def node_service_log_context(
    node: str,
    service: str,
    index: int,
    window: int = 20,
    run_id: str = "latest",
) -> str:
    """
    Show service log context around a line number on one remote node.

    Use this after node_service_log_tail or node_service_log_search returns a
    specific line number and the user wants surrounding lines.
    """

    response = call_node_tool(
        node,
        "service_log_context",
        {"service": service, "index": index, "window": window, "run_id": run_id},
    )
    return format_node_tool_response(node, response)


@tool
def node_service_test_list(node: str) -> str:
    """
    List service function test scripts on one remote node.

    These are service tests such as basicmedicalrecord.sh, not benchmark
    evaluation datasets. Use node_benchmark_list for benchmark datasets.
    """

    response = call_node_tool(node, "service_test_list")
    return format_node_tool_response(node, response)


@tool
def node_service_test_run(
    node: str, test_name: str = "basicmedicalrecord.sh"
) -> str:
    """
    Run one service function test script on one remote node.

    This starts a background test job for scripts such as
    basicmedicalrecord.sh. It is not a benchmark evaluation. Use
    node_service_test_status to check progress/result and node_service_test_stop
    to stop it.
    """

    response = call_node_tool(
        node,
        "service_test_run",
        {"test_name": test_name},
    )
    return format_node_tool_response(node, response)


@tool
def node_service_test_run_all(node: str) -> str:
    """
    Run all service function test scripts on one remote node.

    This submits a background test-all job. Use node_service_test_status to
    check per-script progress/result and node_service_test_stop to stop it.
    Do not use this for benchmark datasets.
    """

    response = call_node_tool(node, "service_test_run_all")
    return format_node_tool_response(node, response)


@tool
def node_service_test_status(
    node: str, test_run_id: str = "latest", lines: int = 30
) -> str:
    """
    Check service function test status on one remote node.

    Args:
        node: node key/name/host from nodes.yaml.
        test_run_id: test run id, latest, or all for currently running tests.
        lines: number of recent log lines to include.
    """

    response = call_node_tool(
        node,
        "service_test_status",
        {"test_run_id": test_run_id, "lines": lines},
    )
    return format_node_tool_response(node, response)


@tool
def node_service_test_stop(node: str, test_run_id: str = "latest") -> str:
    """
    Stop a running service function test on one remote node.

    Args:
        node: node key/name/host from nodes.yaml.
        test_run_id: test run id, or latest for the latest submitted test.
    """

    response = call_node_tool(
        node,
        "service_test_stop",
        {"test_run_id": test_run_id},
    )
    return format_node_tool_response(node, response)


@tool
def node_benchmark_list(node: str, benchmark_type: str = "all") -> str:
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

    response = call_node_tool(
        node,
        "benchmark_list",
        {"benchmark_type": benchmark_type},
    )
    return format_node_tool_response(node, response)


@tool
def node_benchmark_inspect(
    node: str,
    dataset: str,
    benchmark_type: str = "auto",
    split: str = "default",
) -> str:
    """
    Inspect one benchmark dataset on one remote node before running.

    Use this when dataset type, split, or format is unclear. For MedBench
    structure, use dataset="medical/medbench" or dataset="medbench"; do not
    invent a MedBench file name before calling node_benchmark_list. For
    medical_choice, use exact file names such as step1.json.
    """

    response = call_node_tool(
        node,
        "benchmark_inspect",
        {"dataset": dataset, "benchmark_type": benchmark_type, "split": split},
    )
    return format_node_tool_response(node, response)


@tool
def node_benchmark_run(
    node: str,
    dataset: str,
    benchmark_type: str = "auto",
    split: str = "default",
    max_workers: int = 5,
    limit: int = 0,
    save_every: int = 2,
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

    Use node_benchmark_report with the returned job_id to check progress,
    partial result, final metrics, log path, and output path.
    """

    response = call_node_tool(
        node,
        "benchmark_run",
        {
            "dataset": dataset,
            "benchmark_type": benchmark_type,
            "split": split,
            "max_workers": max_workers,
            "limit": limit,
            "save_every": save_every,
        },
    )
    return format_node_tool_response(node, response)


@tool
def node_benchmark_report(node: str, job_id: str) -> str:
    """
    Retrieve benchmark report by job_id on one remote node.

    Use this for benchmark progress, result, score, completion state, or "how
    is this job going". The job_id belongs to the selected remote node.
    """

    response = call_node_tool(node, "benchmark_report", {"job_id": job_id})
    return format_node_tool_response(node, response)


@tool
def node_benchmark_jobs(node: str) -> str:
    """
    List benchmark jobs on one remote node.

    Use this to find job_id values for node_benchmark_report or
    node_benchmark_stop when the user did not provide a job_id.
    """

    response = call_node_tool(node, "benchmark_jobs")
    return format_node_tool_response(node, response)


@tool
def node_benchmark_stop(node: str, job_id: str) -> str:
    """
    Stop one running benchmark job on one remote node.

    This terminates the remote benchmark process. Partial results may be
    incomplete. Use node_benchmark_jobs first if the job_id is unknown.
    """

    response = call_node_tool(node, "benchmark_stop", {"job_id": job_id})
    return format_node_tool_response(node, response)


@tool
def node_tool_call(node: str, tool_name: str, args_json: str = "{}") -> str:
    """
    Call one tool directly on a specific remote inference agent node.

    This is a fallback/debug controller-side tool. Do not use it when a specific
    node_* wrapper exists, such as node_service_status, node_config_update,
    node_service_log_tail, node_service_test_run, or node_benchmark_run.

    Use this only when all conditions are true:
    - The user explicitly names a node.
    - No specific node_* wrapper exists for the requested operation.
    - The exact remote worker tool name and arguments are known.
    - Direct tool execution is intended; this does not call the remote LLM.

    Args:
        node: node key/name/host from nodes.yaml.
        tool_name: local worker tool name to execute on that node.
        args_json: JSON object string for tool arguments, e.g. {"service":"all"}.
    """

    response = call_node_tool(node, tool_name, parse_json_args(args_json))
    return format_node_tool_response(node, response)
