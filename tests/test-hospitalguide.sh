# v8-导诊

curl -X 'POST' \
  'http://ip:port/inference?request_type=v8&scheme=simple' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/hospitalguide-simple.json

  echo -e "\n==================================\n"

curl -X 'POST' \
  'http://ip:port/inference?request_type=v8&scheme=detailed' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/hospitalguide-detailed.json

  echo -e "\n==================================\n"
