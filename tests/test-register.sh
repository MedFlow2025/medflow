# v3-对话挂号

curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register.json

echo -e "\n==================================\n"

curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register-first.json

echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register-first-department.json

echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register-first-case1.json

  echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register-first-case2.json

  echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register-first-case3.json


  echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/register-first-case4.json
