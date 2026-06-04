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
import uuid
from typing import Dict, Optional

import psutil
import yaml
from langchain.tools import tool

CONFIG_FILE = "../config/service.yaml"
DEFAULT_CONFIG_FILE = "../config/service.default.yaml"
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


def safe_output(text):
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n... truncated ..."
    return text


def get_service_log_root() -> str:
    CONFIG = show_config()
    return os.path.normpath(f"../{CONFIG['ENV']['LOG_DIR']}")


def get_agent_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def format_agent_relative_path(path: str, base_dir: Optional[str] = None) -> str:
    if not path:
        return path
    abs_path = path if os.path.isabs(path) else os.path.abspath(
        os.path.join(base_dir or os.getcwd(), path)
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
    # return "\n".join(lines)
    return {
        "services": services,
        "text": "\n".join(lines),
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

    lines = output.strip().split("\n")

    result = ["\n====== GPU Status ======"]

    for line in lines:
        idx, name, gpu_bus_id, used, total, util = [x.strip() for x in line.split(",")]

        bus_id_to_idx[gpu_bus_id] = idx
        result.append(
            f"GPU {idx} ({name}) | Bus-Id: {gpu_bus_id} | Memory-Usage: {used}/{total} MiB | GPU-Util: {util}%"
        )

    cmd_process = (
        "nvidia-smi --query-compute-apps=gpu_bus_id,pid,name,used_memory "
        "--format=csv,noheader,nounits"
    )
    process_output = run_command(cmd_process)

    process_lines = process_output.strip().split("\n")

    result.append("\n====== GPU Processes ======")
    for line in process_lines:
        gpu_bus_id, pid, name, used = [x.strip() for x in line.split(",")]
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

    visible = cfg["ENV"]["CUDA_VISIBLE_DEVICES"]
    tp_size = int(cfg["RUNTIME"]["TENSOR_PARALLEL_SIZE"])
    mem_util = float(cfg["RUNTIME"].get("GPU_MEMORY_UTILIZATION", 0.9))

    param_billion = float(cfg["ENV"].get("MODEL_PARAM_B", 72))
    precision = cfg["ENV"].get("PRECISION", "bf16").lower()

    # ---------------------------------------------
    # 1️. Estimate GPU Memory
    # ---------------------------------------------
    def estimate_per_gpu_memory_mib(
        param_billion: float,
        precision: str,
        tp_size: int,
        buffer_ratio: float = 0.25,
    ) -> int:
        bytes_map = {
            "fp16": 2,
            "bf16": 2,
            "int8": 1,
            "int4": 0.5,
        }

        bytes_per_param = bytes_map.get(precision, 2)

        total_weight_bytes = param_billion * 1e9 * bytes_per_param
        per_gpu_bytes = total_weight_bytes / tp_size

        # per_gpu_bytes *= (1 + buffer_ratio)

        return int(per_gpu_bytes / 1024 / 1024)

    # ---------------------------------------------
    # 2️. Get GPU Memory
    # ---------------------------------------------
    cmd = (
        "nvidia-smi --query-gpu=index,memory.used,memory.total "
        "--format=csv,noheader,nounits"
    )
    output = run_command(cmd)

    if "[ERROR]" in output:
        return {"ok": False, "analysis": "无法获取 GPU 信息，请确认 nvidia-smi 可用"}

    gpu_memory: Dict[str, tuple] = {}

    for line in output.strip().split("\n"):
        idx, used, total = [x.strip() for x in line.split(",")]
        gpu_memory[idx] = (int(used), int(total))

    # ---------------------------------------------
    # 3️. Generate Candidate List
    # ---------------------------------------------
    analysis_lines = []
    candidates = []

    analysis_lines.append(f"模型规模: {param_billion}B | 精度: {precision}")

    for idx, (used, total) in gpu_memory.items():
        safe_limit = int(total * mem_util)
        available = safe_limit - used
        # available = total - used

        analysis_lines.append(
            f"GPU {idx}: 总 {total} MiB | 已用 {used} MiB | 可分配 {available} MiB"
        )

        if available > 0:
            candidates.append((idx, available))

    candidates.sort(key=lambda x: x[1], reverse=True)

    if not candidates:
        return {"ok": False, "analysis": "\n".join(analysis_lines) + "\n没有可用 GPU。"}

    # ---------------------------------------------
    # 4️. Try different TP combinations
    # ---------------------------------------------
    # max_tp = len(candidates)
    # for tp in range(max_tp, 0, -2):

    # For model_medical_* models, TP=8/6 is not feasible, only try TP=4 and TP=2
    for tp in range(4, 0, -2):
        required = estimate_per_gpu_memory_mib(param_billion, precision, tp)

        top_tp = candidates[:tp]
        min_available = min([avail for _, avail in top_tp])

        if min_available >= required:
            recommended_ids = [idx for idx, _ in top_tp]

            analysis_lines.append(f"\n推荐 TP={tp}")
            analysis_lines.append(f"单卡需求 ≈ {required} MiB")
            analysis_lines.append(f"最小可用显存 ≈ {min_available} MiB")

            return {
                "ok": True,
                "recommended_gpus": ",".join(recommended_ids),
                "recommended_tp": tp,
                "analysis": "\n".join(analysis_lines),
            }

    analysis_lines.append("\n所有 GPU 组合均无法满足显存需求。")

    return {
        "ok": False,
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
    param_billion = float(cfg["ENV"].get("MODEL_PARAM_B", 72))
    precision = cfg["ENV"].get("PRECISION", "bf16").lower()

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

    if visible.startswith("["):
        visible = ",".join(map(str, ast.literal_eval(visible)))
        return {
            "ok": False,
            "reason": "gpu_value_error",
            "analysis": f"CUDA_VISIBLE_DEVICES 格式错误，应改为 '{visible}' ",
        }

    target_gpus = [x.strip() for x in visible.split(",") if x.strip()]

    # ------------------------------------------------
    # 4. Driver check
    # ------------------------------------------------
    cmd = (
        "nvidia-smi --query-gpu=index,memory.used,memory.total "
        "--format=csv,noheader,nounits"
    )
    output = run_command(cmd)
    if "[ERROR]" in output:
        return {
            "ok": False,
            "reason": "nvidia_smi_failed",
            "analysis": "NVIDIA driver 不可用或 nvidia-smi 执行失败",
        }

    # ------------------------------------------------
    # 5. GPU status
    # ------------------------------------------------
    gpu_memory: Dict[str, tuple] = {}

    for line in output.strip().split("\n"):
        idx, used, total = [x.strip() for x in line.split(",")]
        gpu_memory[idx] = (int(used), int(total))

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
    bytes_map = {
        "fp16": 2,
        "bf16": 2,
        "int8": 1,
        "int4": 0.5,
    }
    # dtype=torch.bfloat16,

    bytes_per_param = bytes_map.get(precision, 2)

    total_weight_bytes = param_billion * 1e9 * bytes_per_param
    per_gpu_bytes = total_weight_bytes / tp_size
    # per_gpu_bytes *= 1.25  # buffer 25%

    required_mib = int(per_gpu_bytes / 1024 / 1024)
    total_mib = int(total_weight_bytes / 1024 / 1024)

    analysis_lines = []
    analysis_lines.append(f"模型 {param_billion}B | 精度 {precision}")
    analysis_lines.append(
        f"采用 {tp_size} 张卡 | 总需求 ≈ {total_mib} MiB | 单卡需求 ≈ {required_mib} MiB"
    )

    out_of_memory = False
    for gid in target_gpus:
        used, total = gpu_memory[gid]
        safe_limit = int(total * mem_util)
        available = safe_limit - used
        # available = total - used

        analysis_lines.append(f"GPU {gid}: 可用 {available} MiB")

        if available < required_mib:
            out_of_memory = True

    if out_of_memory:
        return {
            "ok": False,
            "reason": "insufficient_memory",
            "analysis": "\n".join(analysis_lines)
            + "\nUse gpu_recommend_allocation() to analyze current GPU status "
            + "and provide optimal GPU allocation strategy.",
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
        f"- Case2Chat: {ports['DATA_ANNOTATION_PORT']}"
    )
    # f"- Voice: {ports.get('VOICE_PORT', 9007)}"
    # "可调用 service_start_status() 查看后台启动状态。"


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


def start_test_job(test_name: str = "basicmedicalrecord.sh", run_all: bool = False) -> str:
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
    stop_service()
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
        return (
            f"Benchmark dataset not found: {dataset}\n"
            + medical_choice_candidates(dataset)
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


def inspect_json_samples(path: str, sample_limit: int = 3) -> tuple[int, list[str], list]:
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
        return (
            f"医疗选择题数据集不存在: {dataset}\n"
            + medical_choice_candidates(dataset)
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
            f"Not Found: {dataset_path}. Please use `benchmark_list(benchmark_type=\"medbench\")` to check available MedBench jsonl files, \
            or run the entire dataset: medical/medbench.\n"
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
    lines.append(f"状态: {status}")
    lines.append(f"模型: {model}")
    lines.append(f"数据集: {dataset}")
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
    if lowered.endswith(".json") or lowered.startswith("medical/choice/"):
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
def config_show() -> str:
    """Show current service config"""
    return show_public_config()


@tool
def service_status() -> str:
    """Check current inference service ports.

    Use this for current running/stopped port status. If the user asks whether a
    background startup has completed, use service_start_status instead.
    """
    return service_status_data()["text"]


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
def config_update(key: str, value: str) -> str:
    """
    Update config value. Key must be one of config_keys().
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
    return update_config(key, value)


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
      MedDiag.jsonl. To inspect the overall MedBench structure, use
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
