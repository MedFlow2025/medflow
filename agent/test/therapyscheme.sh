#!/bin/bash

IP=$1
PORT=$2
LOG_PATH=${TEST_LOG_DIR:-../logs/tests/manual}
LOG_FILE=${TEST_LOG_FILE:-${LOG_PATH}/therapy.log}
if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
fi
: > "$LOG_FILE"

requests=(
    "pick_therapy||0|therapyscheme-picktherapy.json"
    "generate_therapy|1|0|therapyscheme-generatetherapy.json"
    "generate_therapy|1|1|therapyscheme-generatetherapy.json"
    "generate_therapy|2|1|therapyscheme-generatetherapy.json"
    "generate_therapy|3|1|therapyscheme-generatetherapy.json"
    "generate_therapy|4|1|therapyscheme-generatetherapy.json"
    "generate_therapy|5|1|therapyscheme-generatetherapy.json"
)

for r in "${requests[@]}"; do
    IFS='|' read -r scheme sub enable_think json_file <<< "$r"

    URL="http://$IP:$PORT/inference?request_type=v6&scheme=$scheme"
    [ -n "$sub" ] && URL+="&sub_scheme=$sub"
    [ "$enable_think" = "1" ] && URL+="&enable_think=1"

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
