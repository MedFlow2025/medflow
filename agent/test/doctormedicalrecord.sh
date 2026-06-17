#!/bin/bash

IP=$1
PORT=$2
LOG_PATH=${TEST_LOG_DIR:-../logs/tests/manual}
LOG_FILE=${TEST_LOG_FILE:-${LOG_PATH}/doctormedicalrecord.log}

if [ -z "$IP" ] || [ -z "$PORT" ]; then
    echo "ERROR: $0 <SERVICE_HOST> <INFERENCE_PORT>"
    exit 1
fi

if [ ! -d "$(dirname "$LOG_FILE")" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
fi
: > "$LOG_FILE"

requests=(
  "general|doctormedicalrecord-general.json"
  "general|doctormedicalrecord-general-doctor.json"
  "general|doctormedicalrecord-general-template.json"
  "general|doctormedicalrecord-general-template-doctor.json"
  "general|doctormedicalrecord-general-template-label.json"
  "general|doctormedicalrecord-general-template-label-doctor.json"
  "special|doctormedicalrecord-special-template-doctor.json"
  "special|doctormedicalrecord-special_modify-template-doctor.json"
  "special_select|doctormedicalrecord-special_select-template-doctor.json"
  "special|doctormedicalrecord-special-I.json"
  "special|doctormedicalrecord-special-II.json"
  "special|doctormedicalrecord-special-III.json"
  "special|doctormedicalrecord-special-IV.json"
)

for r in "${requests[@]}"; do
  IFS='|' read -r scheme json_file <<< "$r"

  URL="http://$IP:$PORT/inference?request_type=v9&scheme=$scheme"

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
