import ast
import json
import os
import signal
import socket
import subprocess
import threading
import time
import uuid
from typing import Dict

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
LOG_FILES = {
    "start": "start-service.log",
    "vllm": "vllm.log",
    "inference": "inference.log",
    "ui": "ui.log",
    "case2chat": "case2chat.log",
}
MAX_OUTPUT_CHARS = 6000
PROGRESS_UPDATE_INTERVAL = 5


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


def benchmark_list() -> str:
    """List all available benchmark datasets."""
    CONFIG = show_config()
    return run_command(f"ls {CONFIG['ENV']['BENCHMARK_DIR']}/dataset")


def is_process_running(pid: int) -> bool:
    """Check if the process is running and not a zombie."""
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def monitor_job(job_id: str, pid: int, meta_path: str):
    """Background thread checks if the job is finished."""
    while True:
        if not is_process_running(pid):
            meta = json.load(open(meta_path))
            if meta["status"] == "running":
                meta["status"] = "finished"
                meta["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)
                break
        time.sleep(10)


def benchmark_test(dataset: str, max_workers: int = 5, save_every: int = 2) -> str:
    """Start a benchmark evaluation job (runs asynchronously in the background)."""

    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"

    cfg = show_config()
    model = cfg["ENV"]["MODEL_NAME"]
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"

    job_dir = f"{benchmark_dir}/logs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)

    meta_file = os.path.join(job_dir, "meta.json")
    log_file = os.path.join(job_dir, "run.log")
    output_file = os.path.join(job_dir, "result.json")

    cmd = [
        "python",
        f"{benchmark_dir}/eval_runner.py",
        "--mode",
        "eval",
        "--base-url",
        base_url,
        "--model",
        model,
        "--dataset",
        f"{benchmark_dir}/dataset/{dataset}",
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

    threading.Thread(
        target=monitor_job, args=(job_id, int(pid), meta_file), daemon=True
    ).start()

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
                "end_time": "",
            },
            f,
            indent=2,
        )

    return f"任务已启动: \njob_id={job_id}\npid={pid}\nmodel={model}\ndataset={dataset}"


def benchmark_check(job_id: str) -> str:
    """Check the current status of a benchmark job."""

    cfg = show_config()
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    meta_path = f"{benchmark_dir}/logs/{job_id}/meta.json"

    if not os.path.exists(meta_path):
        return "job_id 不存在: status=not found"

    meta = json.load(open(meta_path))
    pid = meta["pid"]

    if meta["status"] == "running":
        return f"任务运行中: status={meta['status']}, job_id={job_id}, pid={pid}, 可查看中间结果: {meta['output']}"

    elif meta["status"] == "finished":
        return f"任务已结束: status={meta['status']}, job_id={job_id}, 可查看完整结果: {meta['output']}"

    elif meta["status"] == "stopped":
        return f"任务意外终止: status={meta['status']}, job_id={job_id}, 可查看部分结果: {meta['output']}, 结果可能不完整。"

    else:  # failed
        return "任务状态查询失败: status=failed"


def benchmark_result(job_id: str) -> str:
    """Retrieve the evaluation result of a benchmark job."""

    cfg = show_config()
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    meta_path = f"{benchmark_dir}/logs/{job_id}/meta.json"

    if not os.path.exists(meta_path):
        return "job_id 不存在"

    meta = json.load(open(meta_path))
    output_file = meta["output"]
    mode = meta["mode"]

    if mode == "medbench":
        return "ERROR: Accuracy cannot be calculated (no ground truth labels). \
The MedBench inference job only generates answers without evaluation."

    if not os.path.exists(output_file):
        return "结果尚未生成"
    elif os.path.isdir(output_file):
        return f"ERROR: {output_file} is a directory."

    data = json.load(open(output_file))
    summary = data["summary"]

    return (
        f"评测结果:\n"
        f"total={summary['total']}\n"
        f"processed={summary['processed']}\n"
        f"progress={summary['progress']}\n"
        f"correct={summary['correct']}\n"
        f"accuracy={summary['accuracy']:.4f}\n"
        f"avg_f1={summary['avg_f1']:.4f}\n"
        f"invalid={summary['invalid']}\n"
        f"invalid_rate={summary['invalid_rate']:.4f}"
    )


def benchmark_job_list() -> str:
    """List all benchmark jobs with their current status."""

    cfg = show_config()
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]

    base = f"{benchmark_dir}/logs/"

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


def benchmark_stop(job_id: str) -> str:
    """Stop a running benchmark job."""

    cfg = show_config()
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    job_dir = f"{benchmark_dir}/logs/{job_id}"
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

    CONFIG = show_config()
    base_dir = CONFIG["ENV"]["BENCHMARK_DIR"]
    dataset_dir = os.path.join(base_dir, "MedBench_LLM")

    if not os.path.exists(dataset_dir):
        return f"[ERROR]: Dataset directory not found: {dataset_dir}."

    try:
        files = [f for f in os.listdir(dataset_dir) if f.endswith(".jsonl")]
    except Exception as e:
        return f"[ERROR]: Failed to list dataset: {str(e)}."

    files.sort()

    if not files:
        return "MedBench_LLM/ (empty)"

    lines = []
    lines.append(f"MedBench_LLM/ (共 {len(files)} 个文件):")

    for f in files:
        lines.append(f"  - {f}")

    return "\n".join(lines)


def medbench_run(dataset: str, max_workers: int = 5) -> str:
    """Start a medbench evaluation job (runs asynchronously in the background)."""

    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"

    cfg = show_config()
    model = cfg["ENV"]["MODEL_NAME"]
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]
    base_url = f"http://{cfg['ENV']['HOST_IP']}:{cfg['PORTS']['VLLM_OPENAI_PORT']}/v1"

    job_dir = f"{benchmark_dir}/logs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)

    meta_file = os.path.join(job_dir, "meta.json")
    log_file = os.path.join(job_dir, "run.log")
    output_dir = os.path.join(job_dir, "results")
    os.makedirs(output_dir, exist_ok=True)

    dataset_path = f"{benchmark_dir}/{dataset}"
    if not os.path.exists(dataset_path):
        return (
            f"Not Found: {dataset_path}. Please use `list_medbench` to check available MedBench jsonl files, \
            or run the entire dataset: MedBench_LLM."
        )
    if dataset.endswith(".jsonl"):
        # dataset_type = "file"
        files = [os.path.basename(dataset_path)]
    else:
        # dataset_type = "folder"
        files = [f for f in os.listdir(dataset_path) if f.endswith(".jsonl")]

    cmd = [
        "python",
        f"{benchmark_dir}/eval_runner.py",
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

    threading.Thread(
        target=monitor_medbench_job, args=(job_id, int(pid), meta_file), daemon=True
    ).start()

    with open(meta_file, "w") as f:
        json.dump(
            {
                "job_id": job_id,
                "pid": pid,
                "model": model,
                "mode": "medbench",
                "dataset": dataset,
                # "dataset_type": dataset_type,
                "files": files,
                "log": log_file,
                "output": output_dir,
                "start_time": start_time,
                "status": "running",
                "end_time": "",
            },
            f,
            indent=2,
        )

    return f"MedBench任务已启动: \njob_id={job_id}\npid={pid}\nmodel={model}\ndataset={dataset}"


def monitor_medbench_job(job_id: str, pid: int, meta_path: str):
    """Background thread: monitor job status + update progress."""

    last_progress_update = 0

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

        if not is_process_running(pid):
            if meta.get("status") == "running":
                meta["status"] = "finished"
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

    dataset = meta.get("dataset").split("/")[0]
    files = meta.get("files", [])
    output_dir = meta.get("output")

    if not dataset or not files or not output_dir:
        return False

    cfg = show_config()
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]

    progress = meta.setdefault("progress", {})
    file_stats = progress.setdefault("files", {})

    changed = False
    completed_files = 0

    for f in files:
        input_path = os.path.join(benchmark_dir, dataset, f)
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


def medbench_progress(job_id: str) -> str:
    """Get MedBench job progress summary."""

    cfg = show_config()
    benchmark_dir = cfg["ENV"]["BENCHMARK_DIR"]

    meta_file = os.path.join(benchmark_dir, "logs", job_id, "meta.json")

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
    lines.append(f"结果位置: {output}")
    lines.append(f"详细信息: {meta_file}")
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


@tool
def list_benchmark() -> str:
    """
    List all available benchmark datasets.

    Purpose:
    - Help the agent or user discover which datasets can be used for evaluation.
    - Typically used before calling `run_benchmark`.
    """

    return benchmark_list()


@tool
def run_benchmark(dataset: str, max_workers: int = 5, save_every: int = 2) -> str:
    """
    Start a benchmark evaluation job (runs asynchronously in the background).

    Purpose:
    - Evaluate model performance on a specified medical exam dataset.
    - This is a long-running task (may take minutes to hours).

    Args:
    - dataset (str): Dataset filename (must be a JSON file). Supported values:
        - 2021.json: China Medical Licensing Exam (中国职业医师考试)
        - 2024.json: Clinical Medicine Graduate Exam (硕士西医临床考试)
        - step1.json: USMLE Step 1 (美国执业医师考试)
        - step2.json: USMLE Step 2 (美国执业医师考试)
        - step3.json: USMLE Step 3 (美国执业医师考试)
    - max_workers (int): Maximum number of concurrent workers.
    - save_every (int): Save evaluation results after every N records.

    Returns:
    - A `job_id` string (unique identifier for the task)

    Notes:
    - This function does NOT return evaluation results.
    - Use `check_benchmark` or `get_benchmark_result` to track progress or retrieve results.
    """

    return benchmark_test(dataset, max_workers, save_every)
    # Before running, call `list_benchmark` to check which benchmark datasets are available.


@tool
def check_benchmark(job_id: str) -> str:
    """
    Check the current status of a benchmark job.

    Purpose:
    - Determine whether a job is still running or has completed.
    - Retrieve basic runtime information.

    Args:
    - job_id (str): Unique identifier returned by `run_benchmark`.

    Returns:
    - Job status:
        - "running": job is still executing
        - "finished": job completed successfully
        - "stopped": job has been stopped
        - "failed": job terminated with error
        - "not found": invalid job_id
    """

    return benchmark_check(job_id)


@tool
def get_benchmark_result(job_id: str) -> str:
    """
    Retrieve the evaluation result of a benchmark job.

    Purpose:
    - Obtain model performance metrics after job completion

    Args:
    - job_id (str): Unique identifier of the job

    Returns:
    - A summary string containing evaluation metrics, e.g.:
       total, processed, progress, correct, accuracy, avg_f1, invalid, invalid_rate

    Notes:
    - This can be called whether the job is running or finished.
    - For MedBench-related jobs, accuracy cannot be calculated (no ground truth labels).
    """

    return benchmark_result(job_id)


@tool
def list_benchmark_jobs() -> str:
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

    return benchmark_job_list()


@tool
def stop_benchmark(job_id: str) -> str:
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
    - After stopping, `get_benchmark_result` may not return valid results
    """

    return benchmark_stop(job_id)


@tool
def list_medbench() -> str:
    """
    List available MedBench datasets and jsonl files.

    Purpose:
    - Discover available MedBench dataset folders and their jsonl files.
    - Used before calling `run_medbench` to select valid inputs.

    Returns:
    - A human-readable list containing:
        - Dataset folders (e.g. "MedBench_LLM")
        - Corresponding jsonl files under each folder

    Example output:
    - MedBench_LLM/
        - CMB-Clin-extended.jsonl
        - MedMC.jsonl
        - ...
    """

    return medbench_list()


@tool
def run_medbench(dataset: str = "MedBench_LLM", max_workers: int = 5) -> str:
    """
    Run MedBench inference job (no evaluation, only generate answers).

    Purpose:
    - Generate model outputs for MedBench-style datasets.
    - Suitable for online submission (no accuracy calculation).

    Args:
    - dataset (str): Dataset folder or a specific jsonl file.
        Examples:
        - "MedBench_LLM" → run the entire dataset folder
        - "MedBench_LLM/CMB-Clin-extended.jsonl" → run a single jsonl file
    - max_workers (int): concurrency (default=5)

    Returns:
    - A `job_id` string (unique identifier for the task)

    Notes:
    - If `dataset` is a folder (e.g. "MedBench_LLM"), the system creates ONE job
      and processes all jsonl files inside the folder.
    - If `dataset` is a specific jsonl file, the system creates ONE job
      for that file only.
    - The system does NOT create one job per file when a folder is provided.
    - When providing a file, use a relative path under the dataset directory
      (e.g., "MedBench_LLM/your_file.jsonl").
    - Use `list_medbench` to view all available medbench jsonl files.
    """

    return medbench_run(dataset, max_workers)


@tool
def get_medbench_progress(job_id: str) -> str:
    """
    Get MedBench job progress summary.

    Args:
    - job_id (str): Unique identifier for the task.

    Returns:
    - Human-readable progress report containing:
        - Job ID
        - Status (running/finished/stopped/failed)
        - Model name
        - Dataset name
        - Result directory path
        - Metadata file path
        - File progress (completed_files/total_files)
        - Sample progress (done_samples/total_samples with percentage)
        - Running files list (filename, done/total samples, percentage)
        - Finished files list (filename, done/total samples, percentage)
    """

    return medbench_progress(job_id)
