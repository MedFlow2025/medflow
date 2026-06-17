#!/bin/bash

IP=$1
PORT=$2
LOG_PATH=${TEST_LOG_DIR:-../logs/tests/manual}
LOG_FILE=${TEST_LOG_FILE:-${LOG_PATH}/quality.log}

if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
fi
: > "$LOG_FILE"

requests=(
  "quality_inspect|quality_inspect_post_input.json"
  "quality_inspect|quality_inspect_post_input_with_config_name.json"
  "quality_modify|quality_modify_post_input.json"
  "quality_modify|quality_modify_post_input_second.json"
  "quality_modify|quality_modify_multi_post_input.json"
)


for r in "${requests[@]}"; do
  IFS='|' read -r scheme json_file <<< "$r"

  URL="http://$IP:$PORT/$scheme"

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
