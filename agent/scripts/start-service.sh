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
    #"case2chat": ${DATA_ANNOTATION_PORT},
    #"voice": ${VOICE_PORT}

# Start server
if [ "$ACTION" == "start" ]; then
    # Clean
    . ../scripts/clean.sh $VLLM_OPENAI_PORT $INFERENCE_PORT $UI_PORT $DATA_ANNOTATION_PORT
    cd ../../src
    
    RUN_ID=${SERVICE_RUN_ID:-$(date +"%Y%m%d_%H%M%S")_$$}
    SERVICE_LOG_DIR=${LOG_DIR}/services
    RUN_LOG_DIR=${SERVICE_LOG_DIR}/runs/${RUN_ID}
    mkdir -p $RUN_LOG_DIR
    ln -sfnT runs/${RUN_ID} ${SERVICE_LOG_DIR}/latest
    LOG_FILE=${RUN_LOG_DIR}/start-service.log
    STATUS_FILE=${RUN_LOG_DIR}/status.json
    STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
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
    wait_for_port $UI_PORT "Web Server"

    echo "====== End ======" >> $LOG_FILE
    write_start_status "finished" "\"$(date +"%Y-%m-%d %H:%M:%S")\"" "null"
    
    cd -
    elif [ "$ACTION" == "stop" ]; then
    # Clean
    . ../scripts/clean.sh $VLLM_OPENAI_PORT $INFERENCE_PORT $UI_PORT $DATA_ANNOTATION_PORT
else
    echo "Unknown action: $ACTION, only support start or stop."
fi
