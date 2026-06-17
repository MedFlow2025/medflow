#!/bin/bash

IP=$1
PORT=$2
LOG_PATH=${TEST_LOG_DIR:-../logs/tests/manual}
LOG_FILE=${TEST_LOG_FILE:-${LOG_PATH}/clientinfo.log}
URL="http://${IP}:${PORT}/inference?request_type=v1"

if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
fi
: > "$LOG_FILE"

echo "Running healthcheck on ${URL} ..."

response=$(curl -s -w "\n%{http_code}" -X POST $URL \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d @../test/data/clientinfo.json
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

echo "Test Passed!"
exit 0
