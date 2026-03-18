#!/bin/bash

IP=$1
PORT=$2

LOG_PATH=../test/logs/
LOG_FILE=$LOG_PATH/followup.log
if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "../test/logs" ]; then
    mkdir -p ../test/logs
fi
echo "" > $LOG_FILE

requests=(
    "followup-generate-questions.json"
    "followup-chat-first.json"
    "followup-chat-middle.json"
    "followup-chat-finish.json"
    "followup-report.json"
)

for json_file in "${requests[@]}"; do
    
    URL="http://$IP:$PORT/follow_up/questionnaire"
    
    echo "=== Request: $URL ==="
    
    response=$(curl -s -w "\n%{http_code}" -X POST $URL \
        -H 'accept: application/json' \
        -H 'Content-Type: application/json' \
        -d @"../test/data/$json_file"
    )
    
    body=$(echo "$response" | head -n -1)
    status=$(echo "$response" | tail -n 1)
    if [ "$status" != "200" ]; then
        echo "HTTP Status: $status"
        exit 1
    fi
    echo "HTTP Status: 200 OK"
    
    echo "$body" >> $LOG_FILE
    echo "" >> $LOG_FILE
done

echo "Test Passed!"
exit 0
