# v9-病历

#1.普通病历的生成/修改
##不用模板-医生不填任何信息
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=general' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-general.json

  echo -e "\n==================================\n"

##不用模板-医生手动填了既往史、体温、血压
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=general' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-general-doctor.json

  echo -e "\n==================================\n"

##使用模板-不带标签-医生不填
##模板中只包含了5个字段，无体格检查，但医生描述了体温，此时无法写入到体格检查的体温中
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=general' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-general-template.json

  echo -e "\n==================================\n"

##使用模板-不带标签-医生填
##医生只能在模板中字段的范围内填写内容，比如模板中没有血压这项，医生写了血压也不会使用
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=general' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-general-template-doctor.json

  echo -e "\n==================================\n"

##使用模板-带标签-医生不填
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=general' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-general-template-label.json

  echo -e "\n==================================\n"

##使用模板-带标签-医生填
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=general' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-general-template-label-doctor.json

  echo -e "\n==================================\n"



#2.专科病历的“生成”填空
##用法同普通病历一致，此处只测试“使用模板-不带标签-医生填写内容”
##使用模板-不带标签-医生手动填写了专科检查，其他的按医生说的话进行修改
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special-template-doctor.json

  echo -e "\n==================================\n"



#3.专科病历的“修改”填空
##用法同普通病历一致，此处只测试“使用模板-不带标签-医生填写内容”
##使用模板-不带标签-医生手动将主诉的41改成了先天性，其他的按医生说的话进行修改
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special_modify-template-doctor.json

  echo -e "\n==================================\n"



#4.专科病历的“选择”填空
##用法同普通病历一致，此处只测试“使用模板-不带标签-医生填写内容”
##使用模板-不带标签-医生手动填写了专科检查，其他的按医生说的话进行修改
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special_select' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special_select-template-doctor.json

  echo -e "\n==================================\n"



#补充：I期、II期、取模、戴牙四个阶段的模板
#I期
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special-I.json

  echo -e "\n==================================\n"
#II期
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special-II.json

  echo -e "\n==================================\n"
#取模
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special-III.json

  echo -e "\n==================================\n"
#戴牙
curl -X 'POST' \
  'http://ip:port/inference?request_type=v9&scheme=special' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/doctormedicalrecord-special-IV.json

  echo -e "\n==================================\n"
