# v6-生成多方案

curl -X 'POST' \
  'http://ip:port/inference?request_type=v6&scheme=pick_therapy' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/therapyscheme.json

  echo -e "\n==================================\n"

curl -X 'POST' \
  'http://ip:port/inference?request_type=v6&scheme=default_therapy&sub_scheme=prescription' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/therapyscheme-prescription.json

  echo -e "\n==================================\n"

curl -X 'POST' \
  'http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=surgical_therapy' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/therapyscheme-surgicaltherapy.json

  echo -e "\n==================================\n"
