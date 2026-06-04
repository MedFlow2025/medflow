#!/bin/bash

VLLM_OPENAI_PORT=$1
INFERENCE_PORT=$2
UI_PORT=$3
DATA_ANNOTATION_PORT=$4

rm -rf  ../../src/*.json ../../src/*.xlsx

pid=$(ps -aux | grep vllm | grep ${VLLM_OPENAI_PORT} | grep -v 'grep ' | awk '{print $2}')
if [ -n "$pid" ]; then
    pkill -P $pid || true
    kill -9 $pid || true
fi

kill -9 $(lsof -i :${INFERENCE_PORT} -t) || true

#kill -9 $(ps -aux | grep inference_ui | grep ${UI_PORT} | grep -v 'grep ' | awk '{print $2}') || true
kill -9 $(lsof -i :${UI_PORT} -t) || true

kill -9 $(lsof -i :${DATA_ANNOTATION_PORT} -t) || true
