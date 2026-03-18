import ast
import os
import socket
import subprocess
import time
from typing import Dict

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
LOG_FILES = {
    "start": "start-service.log",
    "vllm": "vllm.log",
    "inference": "inference.log",
    "ui": "ui.log",
    "case2chat": "case2chat.log",
}
MAX_OUTPUT_CHARS = 6000


def safe_output(text):
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n... truncated ..."
    return text


def get_log_path(service: str):
    CONFIG = show_config()
    LOG_DIR = f"../{CONFIG['ENV']['LOG_DIR']}"

    if service == "all":
        return " ".join([LOG_DIR + f for f in LOG_FILES.values()])
    if service not in LOG_FILES:
        raise ValueError(
            f"Invalid service: {service}. Valid options: {list(LOG_FILES.keys())}"
        )

    return LOG_DIR + LOG_FILES[service]


def show_config() -> dict:
    """Show current service config"""
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


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


def status() -> str:
    """Check all service ports."""
    lines = ["\n======== 推理服务状态 ========"]
    CONFIG = show_config()

    for name, port in CONFIG["PORTS"].items():
        running = check_port(port)
        mark = "RUNNING" if running else "STOPPED"
        lines.append(f"{name:20s} ({port}) : {mark}")

    lines.append("============================\n")
    return "\n".join(lines)


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
            "analysis": f"""ENV.MODEL_NAME 不存在: {model_name}。\nUse list_model() to see all available models.""",
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
            + "\nUse recommend_gpu_allocation() to analyze current GPU status "
            + "and provide optimal GPU allocation strategy.",
        }

    # ----------------------------
    # All passed
    # ----------------------------
    return {"ok": True, "analysis": "\n".join(analysis_lines)}


def start_service() -> str:
    """Start inference service stack."""
    CONFIG = show_config()
    subprocess.Popen(
        ["bash", CONFIG["ENV"]["START_SCRIPT"], "start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return wait_until_ready()


def stop_service() -> str:
    """Stop inference service stack."""
    CONFIG = show_config()
    run_command(f"bash {CONFIG['ENV']['START_SCRIPT']} stop")
    return "Service stopped!"


def tail_logs(service: str = "start", lines: int = 30) -> str:
    """Summarize important messages in log."""
    path = get_log_path(service)
    cmd = f"""
    echo "\n========= ERRORS =========";
    grep -inE "error|exception|fail|traceback|timeout|critical" {path} | tail -n 20;

    echo "\n========= WARNINGS =========";
    grep -in warn {path} | tail -n 20;

    echo "\n========= LAST LOG =========";
    grep -n "" {path} | tail -n {lines};
    """
    return safe_output(run_command(cmd))


def logs_search(keyword: str = "error", service: str = "all", limit: int = 20) -> str:
    """Search keyword in logs."""
    path = get_log_path(service)
    cmd = f"grep -in '{keyword}' {path} | tail -n {limit}"
    return safe_output(run_command(cmd))


def context_log(service: str, index: int, window: int = 20) -> str:
    """Show log context around a specific line."""
    path = get_log_path(service)
    start = max(index - window, 1)
    end = index + window
    return safe_output(run_command(f"sed -n '{start},{end}p' {path}"))


def list_tests() -> str:
    """List all available test scripts."""
    CONFIG = show_config()
    TEST_DIR = CONFIG["ENV"]["TEST_DIR"]
    return run_command(f"ls {TEST_DIR}/*.sh 2>/dev/null | xargs -n1 basename")


def run_test(test_name: str) -> str:
    """Run a specific test script."""
    CONFIG = show_config()
    LOG_DIR = f"../{CONFIG['ENV']['LOG_DIR']}"
    TEST_DIR = CONFIG["ENV"]["TEST_DIR"]
    host = CONFIG["ENV"]["HOST_IP"]
    port = (
        CONFIG["PORTS"]["INFERENCE_PORT"]
        if test_name != "case2chat.sh"
        else CONFIG["PORTS"]["DATA_ANNOTATION_PORT"]
    )
    log_file = os.path.join(LOG_DIR, "test.log")

    if "/" in test_name or ".." in test_name:
        return "Invalid test name"

    script = os.path.join(TEST_DIR, test_name)

    if not os.path.exists(script):
        return f"Test script not found: {test_name}"

    cmd = f"""
    echo "\n===== Test Run: $(date) =====" >> {log_file}
    echo "===== Running {test_name} =====" | tee -a {log_file}
    bash {script} {host} {port} 2>&1 | tee -a {log_file}
    echo "" | tee -a {log_file}
    """
    return run_command(cmd)


def run_all_tests() -> str:
    """Run all test scripts in test directory."""
    CONFIG = show_config()

    LOG_DIR = f"../{CONFIG['ENV']['LOG_DIR']}"
    TEST_DIR = CONFIG["ENV"]["TEST_DIR"]
    host = CONFIG["ENV"]["HOST_IP"]
    log_file = os.path.join(LOG_DIR, "test.log")

    cmd = f"""
    echo "\n===== Test Run: $(date) =====" >> {log_file}
    for f in {TEST_DIR}/*.sh; do
        if [ "$(basename $f)" = "case2chat.sh" ]; then
            port={CONFIG["PORTS"]["DATA_ANNOTATION_PORT"]}
        else
            port={CONFIG["PORTS"]["INFERENCE_PORT"]}
        fi

        echo "===== Running $(basename $f) =====" | tee -a {log_file}
        bash $f {host} $port 2>&1 | tee -a {log_file}
        echo "" | tee -a {log_file}
    done
    """
    # echo "\n===== Test completed at $(date) =====" | tee -a {log_file}
    # echo "Test results saved to {log_file}"
    return run_command(cmd)


def restart_service() -> str:
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


def wait_until_ready(timeout=300):
    start = time.time()
    CONFIG = show_config()

    while True:
        all_ok = True
        for port in CONFIG["PORTS"].values():
            if not check_port(port):
                all_ok = False
                break

        if all_ok:
            return "Startup finished, all ports ready!"

        if time.time() - start > timeout:
            return "Timeout: some services not ready."

        time.sleep(20)


def model_list() -> str:
    """List all available models."""
    CONFIG = show_config()
    return run_command(f"ls {CONFIG['ENV']['MODEL_PATH']}")


@tool
def get_ip() -> str:
    """Show current ip"""
    return get_local_ip()


@tool
def config_show() -> str:
    """Show current service config"""
    return show_config()


@tool
def service_status() -> str:
    """Check whether all inference services are running."""
    return status()


@tool
def port_status(port: int) -> str:
    """Check port status."""
    return check_port_status(port)


@tool
def gpu_status() -> str:
    """Show GPU usage status."""
    return check_gpu_status()


@tool
def recommend_gpu_allocation() -> dict:
    """Recommend gpu allocation."""
    return recommend_gpu()


@tool
def check_config() -> dict:
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
    2. Execute check_config()
    """

    return start_service()


@tool
def service_stop() -> str:
    """Stop all inference services."""
    return stop_service()


@tool
def service_restart() -> str:
    """Restart all inference services.

    Prerequisites:
    1. Execute service_status() - if any services are running, run service_stop() before proceeding
    2. Execute check_config()
    """

    return restart_service()


@tool
def service_logs(service: str = "start", lines: int = 30) -> str:
    """
    Summarize important messages in log.

    Shows three sections:
    - ERRORS: grep for error|exception|fail|traceback|timeout|critical (last 20 matches)
    - WARNINGS: grep for warn (last 20 matches)
    - LAST LOG: last N lines with line numbers

    Args:
        service: one of ["start","vllm","inference","ui","case2chat"]
        lines: number of recent log lines to show (default: 30)
    """

    return tail_logs(service, lines)


@tool
def search_logs(keyword: str = "error", service: str = "all", lines: int = 20) -> str:
    """
    Search keyword in logs.

    Args:
        keyword: search text (e.g., error, exception, fail, traceback, timeout, warn, critical, etc.)
        service: specific service or "all"
        line: number of results
    """

    return logs_search(keyword, service, lines)


@tool
def log_context(service: str, index: int, window: int = 20) -> str:
    """
    Show log context around a specific line.

    Args:
        service: log name
        index: line number
        window: lines before and after
    """

    return context_log(service, index, window)


@tool
def available_tests() -> str:
    """List all available test scripts."""
    return list_tests()


@tool
def service_test(test_name: str = "basicmedicalrecord.sh") -> str:
    """
    Run a specific test script.

    This function runs an individual test script and returns the execution results.
    By default, it runs the basic medical record test if no test name is specified.

    Args:
        test_name (str, optional): Name of the test script to execute.
                                   Defaults to "basicmedicalrecord.sh".
                                   Example: "diagnosis.sh", "inpatient.sh"

    """

    return run_test(test_name)


@tool
def service_test_all() -> str:
    """Run all test scripts in test directory."""
    return run_all_tests()


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
def list_model() -> str:
    """List all available models."""
    return model_list()
