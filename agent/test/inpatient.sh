#!/bin/bash

IP=$1
PORT=$2
LOG_PATH=${TEST_LOG_DIR:-../logs/tests/manual}
LOG_FILE=${TEST_LOG_FILE:-${LOG_PATH}/inpatient.log}

if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
fi
: > "$LOG_FILE"

requests=(
    "inpatient-admission_record.json"
    "inpatient-admission_record-modify.json"
    "inpatient-admission_record-fields.json"
    "inpatient-admission_record-prefill.json"
)

for json_file in "${requests[@]}"; do
    URL="http://$IP:$PORT/inference?request_type=inpatient&scheme=admission_record"
    
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
