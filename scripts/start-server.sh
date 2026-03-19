#!/bin/bash

log_file=../scripts/start-server.log

# Config
openai_api_server_port=8000
inference_server_port=8013
web_server_port=7860
case2chat_port=8016
max_round=50
gpu_memory_utilization=0.8
tensor_parallel_size=4
max_tokens=4096
voice_server_port=9007

export CUDA_VISIBLE_DEVICES=${IEI_VISIBLE_DEVICES}
MODEL_NAME=${IEI_VISIBLE_MODELS_NAME}
MODEL_PATH=${IEI_VISIBLE_MODELS_PATH}${MODEL_NAME}
MODEL_URL="http://"${IEI_VISIBLE_OS_IP}":"${openai_api_server_port}"/v1"
VOICE_URL="http://"${IEI_VISIBLE_OS_IP}":"${voice_server_port}"/v1"

if [ -z "$1" ]; then
    echo "Usage：bash start-server.sh start|stop"
    exit 1
fi

if [ ! -f "../src/key.pem" ] || [ ! -f "../src/cert.pem" ]; then
    openssl req -x509 -newkey rsa:4096 -keyout ../src/key.pem -out ../src/cert.pem -sha256 -days 365 -nodes -subj "/C=CN/ST=B/L=B/O=B/OU=B/CN="${IEI_VISIBLE_OS_IP}
fi

# Start server
if [ "$1" == "start" ]; then
    # Clean
    . clean.sh $log_file $openai_api_server_port $inference_server_port $web_server_port $case2chat_port
    cd ../src

    echo "" >> $log_file
    echo "====== Config ======" >> $log_file
    echo "openai_api_server_port="${openai_api_server_port} >> $log_file
    echo "inference_server_port="${inference_server_port} >> $log_file
    echo "web_server_port="${web_server_port} >> $log_file
    echo "case2chat_port="${case2chat_port} >> $log_file
    echo "max_round="${max_round} >> $log_file
    echo "gpu_memory_utilization="${gpu_memory_utilization} >> $log_file
    echo "tensor_parallel_size="${tensor_parallel_size} >> $log_file
    echo "max_tokens="${max_tokens} >> $log_file

    echo "" >> $log_file
    echo "CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES} >> $log_file
    echo "MODEL_NAME="${MODEL_NAME} >> $log_file
    echo "MODEL_PATH="${MODEL_PATH} >> $log_file
    echo "MODEL_URL="${MODEL_URL} >> $log_file
    echo "====== Config End ======" >> $log_file
    echo "" >> $log_file

    echo "====== Starting server ======" >> $log_file
    echo "vllm serve" ${MODEL_PATH} "--served-model-name" ${MODEL_NAME} "--host" ${IEI_VISIBLE_OS_IP} "--port" ${openai_api_server_port} "--tensor-parallel-size" ${tensor_parallel_size} "--gpu-memory-utilization" ${gpu_memory_utilization} >> $log_file
    nohup vllm serve ${MODEL_PATH} --served-model-name ${MODEL_NAME} --host ${IEI_VISIBLE_OS_IP} --port ${openai_api_server_port} --tensor-parallel-size ${tensor_parallel_size} --gpu-memory-utilization ${gpu_memory_utilization} >> ../scripts/nohup.out &
    sleep 240

    echo "" >> $log_file
    echo "python3 inference.py --model" ${MODEL_NAME} "--model-url" ${MODEL_URL} "--fastbm25 --log --host" ${IEI_VISIBLE_OS_IP} "--port" ${inference_server_port} "--max-round" ${max_round} "--max-tokens" ${max_tokens} >> $log_file
    nohup python3 inference.py --model ${MODEL_NAME} --model-url ${MODEL_URL} --fastbm25 --log --host ${IEI_VISIBLE_OS_IP} --port ${inference_server_port} --max-round ${max_round} --max-tokens ${max_tokens} >>  ../scripts/nohup.out &
    sleep 3

    echo "" >> $log_file
    echo "python3 inference_ui.py --host" ${IEI_VISIBLE_OS_IP} "--port" ${inference_server_port} "--gradio-port" ${web_server_port} "--model" ${MODEL_NAME} "--voice-url" ${VOICE_URL} >> $log_file
    nohup python3 inference_ui.py --host ${IEI_VISIBLE_OS_IP} --port ${inference_server_port} --gradio-port ${web_server_port} --model ${MODEL_NAME} --voice-url ${VOICE_URL} >>  ../scripts/nohup.out &
    sleep 3

    echo "" >> $log_file
    echo "python3 case2chat/case2chat_together.py --model" ${MODEL_NAME} "--model-url" ${MODEL_URL} "--host" ${IEI_VISIBLE_OS_IP} "--port" ${case2chat_port} >> $log_file
    nohup python3 case2chat/case2chat_together.py --model ${MODEL_NAME} --model-url ${MODEL_URL} --host ${IEI_VISIBLE_OS_IP} --port ${case2chat_port} >>  ../scripts/nohup.out &
    sleep 3
    echo "====== End ======" >> $log_file

    cd -
elif [ "$1" == "stop" ]; then
    # Clean
    . clean.sh $log_file $openai_api_server_port $inference_server_port $web_server_port $case2chat_port
else
    echo "Unknown parameters: $1, only support start or stop."
fi
