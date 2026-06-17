#!/bin/bash

IP=$1
PORT=$2

LOG_PATH=${TEST_LOG_DIR:-../logs/tests/manual}
LOG_FILE=${TEST_LOG_FILE:-${LOG_PATH}/register.log}
if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
fi
: > "$LOG_FILE"

requests=(
    "register.json"
    "register-first.json"
    "register-first-department.json"
    "register-first-case1.json"
    "register-first-case2.json"
    "register-first-case3.json"
    "register-first-case4.json"
)

for json_file in "${requests[@]}"; do
    
    URL="http://$IP:$PORT/inference?request_type=v3"
    
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
    
    echo "$body" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
done

echo "Test Passed!"
exit 0
