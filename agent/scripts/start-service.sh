#!/bin/bash

ACTION=$1
CONFIG_PROFILE=${2:-service}

if [ -z "$ACTION" ]; then
    echo "Usage: bash start-service.sh start|stop [service|default|CONFIG_FILE]"
    exit 1
fi

case "$CONFIG_PROFILE" in
    service|current|"")
        CONFIG_FILE=../config/service.yaml
        ;;
    default)
        CONFIG_FILE=../config/service.default.yaml
        ;;
    *)
        CONFIG_FILE=$CONFIG_PROFILE
        ;;
esac

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found: $CONFIG_FILE"
    exit 1
fi


# Config
VLLM_OPENAI_PORT=$(yq -r '.PORTS.VLLM_OPENAI_PORT' $CONFIG_FILE)
INFERENCE_PORT=$(yq -r '.PORTS.INFERENCE_PORT' $CONFIG_FILE)
UI_PORT=$(yq -r '.PORTS.UI_PORT' $CONFIG_FILE)
DATA_ANNOTATION_PORT=$(yq -r '.PORTS.DATA_ANNOTATION_PORT' $CONFIG_FILE)
VOICE_PORT=$(yq -r '.PORTS.VOICE_PORT // 9007' $CONFIG_FILE)

HOST_IP=$(yq -r '.ENV.HOST_IP' $CONFIG_FILE)
LOG_DIR=$(yq -r '.ENV.LOG_DIR' $CONFIG_FILE)
MODEL_NAME=$(yq -r '.ENV.MODEL_NAME' $CONFIG_FILE)
MODEL_PATH=$(yq -r '.ENV.MODEL_PATH' $CONFIG_FILE)${MODEL_NAME}
export CUDA_VISIBLE_DEVICES=$(yq -r '.ENV.CUDA_VISIBLE_DEVICES' $CONFIG_FILE)
MASTER_PORT=$(yq -r '.ENV.MASTER_PORT // 50121' $CONFIG_FILE)

TENSOR_PARALLEL_SIZE=$(yq -r '.RUNTIME.TENSOR_PARALLEL_SIZE' $CONFIG_FILE)
GPU_MEMORY_UTILIZATION=$(yq -r '.RUNTIME.GPU_MEMORY_UTILIZATION' $CONFIG_FILE)
MAX_TOKENS=$(yq -r '.RUNTIME.MAX_TOKENS' $CONFIG_FILE)

MODEL_URL="http://"${HOST_IP}":"${VLLM_OPENAI_PORT}"/v1"
VOICE_URL="http://"${HOST_IP}":"${VOICE_PORT}"/v1"

MAX_ROUND=50

resolve_run_log_dir() {
    if [ -n "${SERVICE_RUN_LOG_DIR}" ]; then
        echo "${SERVICE_RUN_LOG_DIR}"
        return
    fi

    local config_name
    local config_dir
    config_name=$(basename "${CONFIG_FILE}")
    config_dir=$(cd "$(dirname "${CONFIG_FILE}")" 2>/dev/null && pwd)
    if [ "${config_name}" = "service.runtime.yaml" ] && [ -n "${config_dir}" ]; then
        echo "${config_dir}"
        return
    fi

    echo ""
}

kill_pid_tree() {
    local pid=$1
    if [ -z "${pid}" ] || ! kill -0 "${pid}" >/dev/null 2>&1; then
        return
    fi

    local child
    for child in $(pgrep -P "${pid}" 2>/dev/null); do
        kill_pid_tree "${child}"
    done

    kill -TERM "${pid}" >/dev/null 2>&1 || true
}

force_kill_pid_tree() {
    local pid=$1
    if [ -z "${pid}" ] || ! kill -0 "${pid}" >/dev/null 2>&1; then
        return
    fi

    local child
    for child in $(pgrep -P "${pid}" 2>/dev/null); do
        force_kill_pid_tree "${child}"
    done

    kill -KILL "${pid}" >/dev/null 2>&1 || true
}

stop_pid_file() {
    local pid_file=$1
    local name=$2
    local expected=$3

    if [ ! -f "${pid_file}" ]; then
        return
    fi

    local pid
    pid=$(cat "${pid_file}" 2>/dev/null)
    if [ -z "${pid}" ]; then
        rm -f "${pid_file}"
        return
    fi

    if kill -0 "${pid}" >/dev/null 2>&1; then
        if [ -n "${expected}" ]; then
            local cmdline
            cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null)
            if [[ "${cmdline}" != *"${expected}"* ]]; then
                echo "Skip ${name} pid ${pid}: cmdline does not match ${expected}"
                rm -f "${pid_file}"
                return
            fi
        fi
        echo "Stopping ${name} by pid ${pid}"
        kill_pid_tree "${pid}"
        sleep 2
        if kill -0 "${pid}" >/dev/null 2>&1; then
            echo "Force stopping ${name} by pid ${pid}"
            force_kill_pid_tree "${pid}"
        fi
    fi

    rm -f "${pid_file}"
}

stop_recorded_pids() {
    local run_log_dir=$1
    if [ -z "${run_log_dir}" ]; then
        return
    fi

    local pid_dir="${run_log_dir}/pids"
    if [ ! -d "${pid_dir}" ]; then
        return
    fi

    stop_pid_file "${pid_dir}/start-service.pid" "start-service" "start-service.sh"
    stop_pid_file "${pid_dir}/ui.pid" "web-ui" "npm"
    stop_pid_file "${pid_dir}/web.pid" "web" "npm"
    stop_pid_file "${pid_dir}/case2chat.pid" "case2chat" "case2chat"
    stop_pid_file "${pid_dir}/inference.pid" "inference" "inference.py"
    stop_pid_file "${pid_dir}/vllm.pid" "vllm" "vllm"
}

if [ ! -f "../../src/key.pem" ] || [ ! -f "../../src/cert.pem" ]; then
    openssl req -x509 -newkey rsa:4096 -keyout ../../src/key.pem -out ../../src/cert.pem \
    -sha256 -days 365 -nodes -subj "/C=CN/ST=B/L=B/O=B/OU=B/CN="${HOST_IP}
fi

wait_for_port() {
    local port=$1
    local name=$2
    
    echo "Waiting for $name on port $port..."
    
    while ! lsof -i:$port >/dev/null 2>&1; do
        sleep 1
    done
    
    echo "$name is ready!"
}

write_start_status() {
    local status=$1
    local finished_at=$2
    local error=$3

    cat > ${STATUS_FILE} <<EOF
{
  "run_id": "${RUN_ID}",
  "status": "${status}",
  "script_pid": $$,
  "config_profile": "${CONFIG_PROFILE}",
  "config_file": "${CONFIG_FILE}",
  "log_dir": "${RUN_LOG_DIR}",
  "pid_dir": "${PID_DIR}",
  "started_at": "${STARTED_AT}",
  "finished_at": ${finished_at},
  "ports": {
    "vllm": ${VLLM_OPENAI_PORT},
    "inference": ${INFERENCE_PORT},
    "ui": ${UI_PORT},
    "case2chat": ${DATA_ANNOTATION_PORT}
  },
  "error": ${error}
}
EOF
}

write_stop_status() {
    local run_log_dir=$1
    if [ -z "${run_log_dir}" ]; then
        return
    fi

    local status_file="${run_log_dir}/status.json"
    if [ ! -f "${status_file}" ]; then
        return
    fi

    python3 - "${status_file}" <<'PY'
import json
import os
import sys
import time

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as e:
    print(f"Failed to read status file {path}: {e}")
    sys.exit(0)

data["status"] = "stopped"
data["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
data["error"] = None

tmp_path = path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
os.replace(tmp_path, path)
PY
}
    #"case2chat": ${DATA_ANNOTATION_PORT},
    #"voice": ${VOICE_PORT}

# Start server
if [ "$ACTION" == "start" ]; then
    # Clean
    . ../scripts/clean.sh $VLLM_OPENAI_PORT $INFERENCE_PORT $UI_PORT $DATA_ANNOTATION_PORT
    cd ../../src
    
    RUN_ID=${SERVICE_RUN_ID:-$(date +"%Y%m%d_%H%M%S")_$$}
    SERVICE_LOG_DIR=${LOG_DIR}/services
    RUN_LOG_DIR=${SERVICE_RUN_LOG_DIR:-${SERVICE_LOG_DIR}/runs/${RUN_ID}}
    PID_DIR=${SERVICE_PID_DIR:-${RUN_LOG_DIR}/pids}
    mkdir -p $SERVICE_LOG_DIR
    mkdir -p $RUN_LOG_DIR
    mkdir -p $PID_DIR
    ln -sfnT ${RUN_LOG_DIR} ${SERVICE_LOG_DIR}/latest
    LOG_FILE=${RUN_LOG_DIR}/start-service.log
    STATUS_FILE=${RUN_LOG_DIR}/status.json
    STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
    echo $$ > ${PID_DIR}/start-service.pid
    write_start_status "starting" "null" "null"
    cat > ${SERVICE_LOG_DIR}/latest.json <<EOF
{
  "run_id": "${RUN_ID}",
  "status_file": "${STATUS_FILE}"
}
EOF
    
    echo "" >> $LOG_FILE
    echo "====== Config ======" >> $LOG_FILE
    echo "CONFIG_PROFILE="${CONFIG_PROFILE} >> $LOG_FILE
    echo "CONFIG_FILE="${CONFIG_FILE} >> $LOG_FILE
    echo "VLLM_OPENAI_PORT="${VLLM_OPENAI_PORT} >> $LOG_FILE
    echo "INFERENCE_PORT="${INFERENCE_PORT} >> $LOG_FILE
    echo "UI_PORT="${UI_PORT} >> $LOG_FILE
    echo "DATA_ANNOTATION_PORT="${DATA_ANNOTATION_PORT} >> $LOG_FILE
    echo "VOICE_PORT="${VOICE_PORT} >> $LOG_FILE
    echo "RUN_ID="${RUN_ID} >> $LOG_FILE
    echo "RUN_LOG_DIR="${RUN_LOG_DIR} >> $LOG_FILE
    echo "PID_DIR="${PID_DIR} >> $LOG_FILE
    echo "MAX_ROUND="${MAX_ROUND} >> $LOG_FILE
    echo "GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION} >> $LOG_FILE
    echo "TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE} >> $LOG_FILE
    echo "MAX_TOKENS="${MAX_TOKENS} >> $LOG_FILE
    
    echo "" >> $LOG_FILE
    echo "CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES} >> $LOG_FILE
    echo "VLLM_PORT="${MASTER_PORT} >> $LOG_FILE
    echo "MASTER_PORT="${MASTER_PORT} >> $LOG_FILE
    echo "MODEL_NAME="${MODEL_NAME} >> $LOG_FILE
    echo "MODEL_PATH="${MODEL_PATH} >> $LOG_FILE
    echo "MODEL_URL="${MODEL_URL} >> $LOG_FILE
    echo "====== Config End ======" >> $LOG_FILE
    echo "" >> $LOG_FILE
    
    echo "====== Starting server ======" >> $LOG_FILE
    echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES} VLLM_PORT=${MASTER_PORT} MASTER_PORT=${MASTER_PORT} vllm serve" ${MODEL_PATH} \
    "--served-model-name" ${MODEL_NAME} \
    "--host" ${HOST_IP} \
    "--port" ${VLLM_OPENAI_PORT} \
    "--tensor-parallel-size" ${TENSOR_PARALLEL_SIZE} \
    "--gpu-memory-utilization" ${GPU_MEMORY_UTILIZATION} \
    "--enable-auto-tool-choice" \
    "--tool-call-parser hermes" \
    >> $LOG_FILE
    nohup env CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" VLLM_PORT="${MASTER_PORT}" MASTER_PORT="${MASTER_PORT}" vllm serve ${MODEL_PATH} \
    --served-model-name ${MODEL_NAME} \
    --host ${HOST_IP} \
    --port ${VLLM_OPENAI_PORT} \
    --tensor-parallel-size ${TENSOR_PARALLEL_SIZE} \
    --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} \
    --enable-auto-tool-choice  \
    --tool-call-parser hermes \
    > ${RUN_LOG_DIR}/vllm.log 2>&1 &
    echo $! > ${PID_DIR}/vllm.pid
    wait_for_port $VLLM_OPENAI_PORT "vLLM OpenAI API"
    
    echo "" >> $LOG_FILE
    echo "python3 inference.py" \
    "--model" ${MODEL_NAME} \
    "--model-url" ${MODEL_URL} \
    "--fastbm25" \
    "--log" \
    "--host" ${HOST_IP} \
    "--port" ${INFERENCE_PORT} \
    "--max-round" ${MAX_ROUND} \
    "--max-tokens" ${MAX_TOKENS} \
    >> $LOG_FILE
    nohup python3 inference.py \
    --model ${MODEL_NAME} \
    --model-url ${MODEL_URL} \
    --fastbm25 \
    --log \
    --host ${HOST_IP} \
    --port ${INFERENCE_PORT} \
    --max-round ${MAX_ROUND} \
    --max-tokens ${MAX_TOKENS} \
    > ${RUN_LOG_DIR}/inference.log 2>&1 &
    echo $! > ${PID_DIR}/inference.pid
    wait_for_port $INFERENCE_PORT "Inference Server"
    
    #echo "" >> $LOG_FILE
    #echo "python3 inference_ui.py" \
    #"--host" ${HOST_IP} \
    #"--port" ${INFERENCE_PORT} \
    #"--gradio-port" ${UI_PORT} \
    #"--model" ${MODEL_NAME} \
    #"--voice-url" ${VOICE_URL} \
    #>> $LOG_FILE
    #nohup python3 inference_ui.py \
    #--host ${HOST_IP} \
    #--port ${INFERENCE_PORT} \
    #--gradio-port ${UI_PORT} \
    #--model ${MODEL_NAME} \
    #--voice-url ${VOICE_URL} \
    #> ${RUN_LOG_DIR}/ui.log 2>&1 &
    #wait_for_port $UI_PORT "Web UI"
    
    echo "" >> $LOG_FILE
    echo "python3 case2chat/case2chat_together.py" \
    "--model" ${MODEL_NAME} \
    "--model-url" ${MODEL_URL} \
    "--host" ${HOST_IP} \
    "--port" ${DATA_ANNOTATION_PORT} \
    >> $LOG_FILE
    nohup python3 case2chat/case2chat_together.py \
    --model ${MODEL_NAME} \
    --model-url ${MODEL_URL} \
    --host ${HOST_IP} \
    --port ${DATA_ANNOTATION_PORT} \
    > ${RUN_LOG_DIR}/case2chat.log 2>&1 &
    echo $! > ${PID_DIR}/case2chat.pid
    wait_for_port $DATA_ANNOTATION_PORT "Case2Chat"
    
    cd -
    cd ../../web

    echo "" >> $LOG_FILE
    echo "npm install --production" >> $LOG_FILE
    nohup npm install --production > ${RUN_LOG_DIR}/web.log 2>&1

    echo "mkcert -key-file key.pem -cert-file cert.pem ${HOST_IP}" >> $LOG_FILE
    nohup mkcert -key-file key.pem -cert-file cert.pem ${HOST_IP} >> ${RUN_LOG_DIR}/web.log 2>&1

    echo "HOST_IP=${HOST_IP} UI_PORT=${UI_PORT} INFERENCE_PORT=${INFERENCE_PORT} VOICE_PORT=${VOICE_PORT} npm run start" >> $LOG_FILE
    nohup env HOST_IP=${HOST_IP} UI_PORT=${UI_PORT} INFERENCE_PORT=${INFERENCE_PORT} VOICE_PORT=${VOICE_PORT} npm run start >> ${RUN_LOG_DIR}/web.log 2>&1 &
    echo $! > ${PID_DIR}/ui.pid
    echo $! > ${PID_DIR}/web.pid
    wait_for_port $UI_PORT "Web Server"

    echo "====== End ======" >> $LOG_FILE
    write_start_status "finished" "\"$(date +"%Y-%m-%d %H:%M:%S")\"" "null"
    
    cd -
    elif [ "$ACTION" == "stop" ]; then
    # Clean
    RUN_LOG_DIR=$(resolve_run_log_dir)
    stop_recorded_pids "${RUN_LOG_DIR}"
    . ../scripts/clean.sh $VLLM_OPENAI_PORT $INFERENCE_PORT $UI_PORT $DATA_ANNOTATION_PORT
    write_stop_status "${RUN_LOG_DIR}"
else
    echo "Unknown action: $ACTION, only support start or stop."
fi
