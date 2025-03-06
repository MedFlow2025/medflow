# v3-对话挂号

#url: http://ip:port/inference?request_type=v3
#输入(input)：
#    basic_medical_record（预问诊阶段生成的病历）
#    all_department（用于输入所有科室信息，包含科室层级编码与科室名称）
#    hospital_register（用于输入output.chosen_department中返回科室的对应医生出诊信息）
#输出(output)：
#    chosen_department（用于输出推荐的科室）
#    hospital_register（用于输出推荐的挂号）
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示，使用时增加一组role为user的回答即可）
#测试脚本：
#    bash v3-guahao.sh
#流程：
#    1.推荐科室：
#      1.1 输入input.basic_medical_record(填写病历)
#          输入input.all_department(输入所有科室信息)
#          输入input.hospital_register(初始为null)
#      1.2 发送请求后，会推荐科室
#          输出output.chosen_department.department_id和department_name（推荐的科室）
#          输出chat.historical_conversations中会显示“xxx推荐科室如下：【xxx】【xxx】”
#    2.首次推荐挂号：
#      2.1 输入input.basic_medical_record(同步骤1.1，无需修改)
#          输入input.all_department(同步骤1.1，无需修改)
#          输入input.hospital_register(需要将步骤1.2中所生成的科室output.chosen_department.department_name，对应的所有挂号信息填写到intput.hospital_register中。
#              例如，步骤1.2中生成的科室有“耳鼻喉科”和“呼吸内科门诊”，此处需要填写“耳鼻喉科”和“呼吸内科门诊”所有的医生日期时间等挂号信息。
#              注意，input.hospital_register中的所有内容不能有空的，日期采用YYYYMMDD格式显示，时间采用HH24:MI格式显示，08:30不能写成8:30。)
#          输入output.chosen_department(写入步骤1.2输出的结果，即生成的推荐科室)
#      2.2 发送请求后，推荐挂号，默认返回第一个号源不为0的挂号信息，所推荐的挂号默认是在已推荐科室的范围内;
#          输出output.hospital_register（推荐的挂号）
#          输出chat.historical_conversations中会显示“据您的病情，我们推荐您在【xxx xxx-xxx】，前往【xxx xxx xxx】处进行就诊，您看是否可以？”
#    3.患者要求更换挂号信息：
#      3.1 输入input.basic_medical_record(同步骤1.1，无需修改)
#          输入input.all_department(同步骤1.1，无需修改)
#          输入input.hospital_register(同步骤2.1)
#          输入output.chosen_department(写入步骤1.2输出的结果，即生成的推荐科室)
#          输入output.hospital_register(写入步骤2.2输出的结果，即生成的推荐挂号)
#          输入chat.historical_conversations中增加一组role为user的回答(即患者说的话)
#      3.2 发送请求后，会按照患者要求检索挂号信息，
#          如果检索到符合患者要求的挂号，会更新output.hospital_register，同时chat.historical_conversations会显示“我们推荐您在【xxx xxx-xxx】，前往【xxx xxx xxx】处进行就诊，您看是否可以？”
#          如果没有检索到符合患者要求的挂号，不更新output.hospital_register，同时chat.historical_conversations会显示“抱歉，目前没有查询到【xxx xxx ...】的出诊信息，您可以尝试换个问题，我会尽力帮助您。”
#          直至患者表示认可当前的挂号信息，会更新output.hospital_register，同时chat.historical_conversations会显示“您已经成功预约了【xxx xxx-xxx】【xxx xxx xxx】，请您按时就诊。另外，在您正式就诊前，医生会查阅你的预问诊报告，可能会向您提出新的问题，请注意接收消息并按指引给予回复。”
#其他：
#    1.当患者表示修改挂号日期、挂号时间段时，默认是按照上次对话所推荐的医生进行更换的。
#      例如，上次推荐的是【李四 20241125 08:00-08:30】，患者说“我想挂下午的号”，会按“李四医生”检索“下午”的。
#    2.如果需要同时更换挂号日期、挂号时间段，与医生姓名/医生职称等，可以加上具体的医生。
#      例如，上次推荐的是【李四 20241125 08:00-08:30】，患者说“我想挂张三的下午的号”，会按“张三医生”检索“下午”的。
#    3.患者的不同语言描述会影响检索的准确性。
#    4.支持换科室、换医生、换医生职称、换日期、换时间五种意图，可一次输入单个意图，也可一次输入多个意图。
#问题:
#    1.首次推荐挂号后，不能更换科室;（已解决）

curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-guahao.json

echo -e "\n==================================\n"

curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-gauhao-first.json

echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-gauhao-first-department.json

echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-guahao-first-case1.json

  echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-guahao-first-case2.json

  echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-guahao-first-case3.json


  echo -e "\n==================================\n"

  curl -X 'POST' \
  'http://ip:port/inference?request_type=v3' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data-v3-guahao-first-case4.json


#测试结果-流程-1.推荐科室
#{
#    "input": {
#        "basic_medical_record": {
#            "chief_complaint": "咳嗽一周伴头痛、嗓子疼。",
#            "history_of_present_illness": "患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。",
#            "past_medical_history": "否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。",
#            "personal_history": "吸烟史：否认；饮酒史：一周一次，一次半斤；",
#            "allergy_history": "药物过敏：否认；食物过敏：牛奶",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        },
#        "all_department": [
#            {
#                "department_id": "6858ab4e085646ab3207.191121.",
#                "department_name": "精神科心理科门诊"
#            },
#            {
#                "department_id": "f9f07f90284b46ab09dc.1d4b95f96e0746ae4ef4.",
#                "department_name": "中医治未病门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101711.",
#                "department_name": "神经内科门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.",
#                "department_name": "肿瘤医学中心一区门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9fee5610c946ac42b9.",
#                "department_name": "肿瘤医学中心二区门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101611.",
#                "department_name": "内分泌科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112211.",
#                "department_name": "乳腺外科门诊"
#            },
#            {
#                "department_id": "5aeaa849017646aa2073.dfa991d0215f46ab4553.",
#                "department_name": "中医科门诊"
#            },
#            {
#                "department_id": "685740a5084c46ab3207.141221.",
#                "department_name": "耳鼻喉科门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101311.",
#                "department_name": "消化内科门诊"
#            },
#            {
#                "department_id": "702ef2dd44b746ad047d.141312.",
#                "department_name": "口腔科门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.121211.",
#                "department_name": "产科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.111411.",
#                "department_name": "男性科门诊"
#            },
#            {
#                "department_id": "685675a3084946ab3207.141132.",
#                "department_name": "眼科门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.121111.",
#                "department_name": "妇科门诊"
#            },
#            {
#                "department_id": "6856e777084a46ab3207.140111.",
#                "department_name": "皮肤科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112011.",
#                "department_name": "甲状腺外科门诊"
#            },
#            {
#                "department_id": "507cfcf0761b46ae7f31.120111.",
#                "department_name": "营养科门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101411.",
#                "department_name": "血液科门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.11121.",
#                "department_name": "心胸外科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.111811.",
#                "department_name": "肝胆胰脾、疝外科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112311.",
#                "department_name": "神经外科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.111311.",
#                "department_name": "泌尿外科门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101512.",
#                "department_name": "肾内科门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101511.",
#                "department_name": "风湿内科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.111511.",
#                "department_name": "骨科门诊（关节）"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.111611.",
#                "department_name": "骨科门诊（脊柱）"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.fc97773c7e53663a5f37.",
#                "department_name": "肿瘤医学中心三区门诊"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101812.",
#                "department_name": "感染科门诊（含肝病）"
#            },
#            {
#                "department_id": "685990a4085c46ab3207.171121.",
#                "department_name": "康复医学科门诊"
#            },
#            {
#                "department_id": "cc49cf9b7b4146ad7635.451123.",
#                "department_name": "伤口、造口护理门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.b1dd166a7b8080814ec9.",
#                "department_name": "骨质疏松康复门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.f7bbba5c50bd46aa0d09.",
#                "department_name": "骨伤科门诊"
#            },
#            {
#                "department_id": "ea9b1e6a5ab346ac5e15.eaa26c615ac746ac5e15.",
#                "department_name": "肝胆脾胰肿瘤外科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.ad9875bb4b7246ad33d6.",
#                "department_name": "肛肠科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.ad9d5ce30f6e46ab7b22.",
#                "department_name": "胃肠外科门诊"
#            },
#            {
#                "department_id": "5ae9aac3017346aa2073.131112.",
#                "department_name": "儿科门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.35b278ed093f46af4fc3.",
#                "department_name": "产科门诊（初次建档）"
#            },
#            {
#                "department_id": "cc49cf9b7b4146ad7635.40119.",
#                "department_name": "消化内科护理门诊"
#            },
#            {
#                "department_id": "efc87fb82db680814ec9.efb10381364446ae591f.",
#                "department_name": "全科医学科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.4f8c1dd1106f46ac42b9.",
#                "department_name": "甲状腺乳腺外科门诊"
#            },
#            {
#                "department_id": "ea9b1e6a5ab346ac5e15.5f36c2ed44f946ae482e.",
#                "department_name": "胃肠肿瘤外科门诊"
#            },
#            {
#                "department_id": "5ae9aac3017346aa2073.131221.",
#                "department_name": "新生儿科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.ed173b9c455c46af5350.",
#                "department_name": "血管综合介入门诊"
#            },
#            {
#                "department_id": "5aeba734017846aa2073.55786ac6009446ac2d33.",
#                "department_name": "血透中心门诊"
#            },
#            {
#                "department_id": "6db8448b127c46ae3bc3.209131.",
#                "department_name": "核医学门诊"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101811.",
#                "department_name": "成人发热门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.55477e37009146ac2d33.",
#                "department_name": "助产士门诊"
#            },
#            {
#                "department_id": "5ae9aac3017346aa2073.cae024a7233f46ae0f93.",
#                "department_name": "小儿外科门诊 "
#            },
#            {
#                "department_id": "cc49cf9b7b4146ad7635.451128.",
#                "department_name": "关节骨科护理门诊"
#            },
#            {
#                "department_id": "5ae9aac3017346aa2073.6514fc120ef846aa56a6.",
#                "department_name": "儿童保健及生长发育专科门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.ea99c665752a46ac7b83.",
#                "department_name": "生殖健康与不孕门诊"
#            },
#            {
#                "department_id": "dbe504415d1c46ae50b9.cccf5ce265be46ab323b.",
#                "department_name": "肺部结节门诊"
#            },
#            {
#                "department_id": "cc49cf9b7b4146ad7635.401122.",
#                "department_name": "糖尿病专科护理门诊"
#            },
#            {
#                "department_id": "5aeba734017846aa2073.201114.",
#                "department_name": "用药咨询门诊(疼痛用药)"
#            },
#            {
#                "department_id": "ea9b1e6a5ab346ac5e15.eaa1298b5abb46ac5e15.",
#                "department_name": "泌尿系肿瘤外科门诊"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.09ded36d4ab746ab2abb.",
#                "department_name": "肠道门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.181311.",
#                "department_name": "综合内科门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.4c638e663a6a46cec61e.",
#                "department_name": "温馨产科门诊"
#            },
#            {
#                "department_id": "5aeba734017846aa2073.201113.",
#                "department_name": "用药咨询门诊（抗凝用药）"
#            },
#            {
#                "department_id": "cc49cf9b7b4146ad7635.451121.",
#                "department_name": "老年护理门诊"
#            },
#            {
#                "department_id": "fa7be7cb597346ae72ec.d8736a33586946aa1667.",
#                "department_name": "疼痛（麻醉）门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112112.",
#                "department_name": "创面修复外科、烧伤整形科门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.zly1.",
#                "department_name": "肿瘤医学中心一区综合门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.zly2.",
#                "department_name": "头颈部肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9fee5610c946ac42b9.zle1.",
#                "department_name": "肿瘤医学中心二区综合门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.zly3.",
#                "department_name": "妇科/乳腺肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.zly4.",
#                "department_name": "鼻咽肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.zly5.",
#                "department_name": "恶性黑色素瘤/骨肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9d5a7b109946ac42b9.zly6.",
#                "department_name": "泌尿生殖腺肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.4f9fee5610c946ac42b9.zle2.",
#                "department_name": "肺部肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.fc97773c7e53663a5f37.zls1.",
#                "department_name": "肿瘤医学中心三区综合门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.fc97773c7e53663a5f37.zls2.",
#                "department_name": "肝胆道肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.fc97773c7e53663a5f37.zls3.",
#                "department_name": "胰腺肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.fc97773c7e53663a5f37.zls4.",
#                "department_name": "食管肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.fc97773c7e53663a5f37.zls5.",
#                "department_name": "胃肠肿瘤"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112311.sjy1.",
#                "department_name": "脑与脊髓肿瘤专科"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112311.sjy2.",
#                "department_name": "三叉神经痛与面肌抽搐专科"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112311.sjy3.",
#                "department_name": "脑血管病专科"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112311.sjy4.",
#                "department_name": "昏迷评估促醒专科"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101711.sjn1.",
#                "department_name": "帕金森专科"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101711.sjn2.",
#                "department_name": "认识障碍专科"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101711.sjn3.",
#                "department_name": "癫痫专科"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.5c1f3dc21c1446ab6a9d.nxg2.",
#                "department_name": "脑血管病介入综合门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.5c1f3dc21c1446ab6a9d.nxg1.",
#                "department_name": "脊髓血管疾病专科"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.4b94574a256046aa62fa.",
#                "department_name": "爱心门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.112311.sjy5.",
#                "department_name": "神经外科综合门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101711.sjn4.",
#                "department_name": "神经内科综合门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101711.sjn5.",
#                "department_name": "脑血管病专科"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.5c1f3dc21c1446ab6a9d.nxg3.",
#                "department_name": "脑出血专科"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.5c1f3dc21c1446ab6a9d.nxg4.",
#                "department_name": "脑梗塞专科"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101812.grk1.",
#                "department_name": "感染综合"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101812.grk2.",
#                "department_name": "肝病门诊"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101812.grk3.",
#                "department_name": "脂肪肝"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101812.grk4.",
#                "department_name": "乙肝临床治愈"
#            },
#            {
#                "department_id": "fa7be7cb597346ae72ec.d8736a33586946aa1667.ttk1.",
#                "department_name": "疼痛门诊"
#            },
#            {
#                "department_id": "fa7be7cb597346ae72ec.d8736a33586946aa1667.ttk2.",
#                "department_name": "麻醉门诊"
#            },
#            {
#                "department_id": "5aeaa849017646aa2073.1547d3fc083d46aa420f.",
#                "department_name": "中医护理门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.79359e624d7246ab7a94.",
#                "department_name": "儿童青少年脊柱弯曲异常门诊"
#            },
#            {
#                "department_id": "702ef2dd44b746ad047d.113ebd49790446ae7e39.",
#                "department_name": "口腔正畸科"
#            },
#            {
#                "department_id": "3698c225179e46ce1c4d.3544468630da46ad7fab.",
#                "department_name": "综合内科夜诊（成人）"
#            },
#            {
#                "department_id": "507cfcf0761b46ae7f31.120111.yyk1",
#                "department_name": "儿童营养门诊"
#            },
#            {
#                "department_id": "507cfcf0761b46ae7f31.120111.yyk2",
#                "department_name": "肥胖门诊"
#            },
#            {
#                "department_id": "507cfcf0761b46ae7f31.120111.yyk3",
#                "department_name": "围孕期营养门诊"
#            },
#            {
#                "department_id": "507cfcf0761b46ae7f31.120111.yyk4",
#                "department_name": "综合营养门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.75067b1b010c46ae3f2d.",
#                "department_name": "腹膜透析门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.d3818ad612d746ad3e84.",
#                "department_name": "早产专病门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.f5d6ca9b299d46ae47a5.",
#                "department_name": "戒烟门诊"
#            },
#            {
#                "department_id": "685990a4085c46ab3207.7ea0f9223b9846aa2bd1.",
#                "department_name": "颈肩腰腿痛康复专科"
#            },
#            {
#                "department_id": "f9f07f90284b46ab09dc.944fed4906d146ce091d.",
#                "department_name": "中医治未病护理门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.b7430ef9101a46ad7655.",
#                "department_name": "遗传咨询门诊"
#            },
#            {
#                "department_id": "5ae9662c017246aa2073.201112.",
#                "department_name": "用药咨询门诊（孕产妇用药）"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.",
#                "department_name": "肿瘤医学中心四区门诊"
#            },
#            {
#                "department_id": "ea9b1e6a5ab346ac5e15.5f38106f461a46ae482e.",
#                "department_name": "脑肿瘤与微创神经外科门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq1",
#                "department_name": "肿瘤医学中心四区综合门诊"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq2",
#                "department_name": "呼吸系统恶性肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq3",
#                "department_name": "消化系统恶性肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq4",
#                "department_name": "泌尿生殖系统恶性肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq5",
#                "department_name": "骨与软组织恶性肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq6",
#                "department_name": "皮肤恶性肿瘤"
#            },
#            {
#                "department_id": "702fea9545af46ad047d.04cfcd617b3d46ad06ca.zlsq7",
#                "department_name": "创新性肿瘤临床研究"
#            },
#            {
#                "department_id": "685675a3084946ab3207.2ef420a0231546aa639e.",
#                "department_name": "早产儿眼底筛查专科门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.609e5875332746ae0e95.",
#                "department_name": "心脏医学中心外科"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.601264b112de46ab3a6d.",
#                "department_name": "心脏医学中心内科"
#            },
#            {
#                "department_id": "efc87fb82db680814ec9.a15cf29857e346ae7505.",
#                "department_name": "全科医学科教学门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.5c1f3dc21c1446ab6a9d.",
#                "department_name": "脑血管病介入科门诊"
#            },
#            {
#                "department_id": "702ef2dd44b746ad047d.cc75cc8372bd46ae0e95.",
#                "department_name": "口腔颌面外科门诊"
#            },
#            {
#                "department_id": "5ae9aac3017346aa2073.7a515b7e769046ac0df7.",
#                "department_name": "儿科教学门诊"
#            },
#            {
#                "department_id": "5ae697ab002b46ae19dd.3b9f1d4460b946ac1b1c.",
#                "department_name": "运动损伤医学"
#            },
#            {
#                "department_id": "685675a3084946ab3207.141131.",
#                "department_name": "视光/屈光手术门诊"
#            }
#        ],
#        "hospital_register": []
#    },
#    "output": {
#        "chosen_department": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            },
#            {
#                "department_id": "685740a5084c46ab3207.141221.",
#                "department_name": "耳鼻喉科门诊"
#            }
#        ],
#        "hospital_register": [
#            {
#                "department_id": "",
#                "department_name": "",
#                "doctor_list": [
#                    {
#                        "doctor_id": "",
#                        "doctor_name": "",
#                        "doctor_title": "",
#                        "date_list": [
#                            {
#                                "date": "",
#                                "time_list": [
#                                    {
#                                        "start_time": "",
#                                        "end_time": "",
#                                        "source_num": ""
#                                    }
#                                ]
#                            }
#                        ]
#                    }
#                ]
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n[\n    {\n        \"科室编号\": \"001\",\n        \"科室名称\": \"呼吸内科门诊\"\n    },\n    {\n        \"科室编号\": \"002\",\n        \"科室名称\": \"耳鼻喉科门诊\"\n    }\n]"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n【呼吸内科门诊】\n【耳鼻喉科门诊】"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-流程-2.首次推荐挂号
#{
#    "input": {
#        "basic_medical_record": {
#            "chief_complaint": "咳嗽一周伴头痛、嗓子疼。",
#            "history_of_present_illness": "患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。",
#            "past_medical_history": "否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。",
#            "personal_history": "吸烟史：否认；饮酒史：一周一次，一次半斤；",
#            "allergy_history": "药物过敏：否认；食物过敏：牛奶",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        },
#        "all_department": "内容同上，已省略...",
#        "hospital_register": "内容同上，已省略..."
#    },
#    "output": {
#        "chosen_department": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            },
#            {
#                "department_id": "685740a5084c46ab3207.141221.",
#                "department_name": "耳鼻喉科门诊"
#            }
#        ],
#        "hospital_register": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊",
#                "doctor_list": [
#                    {
#                        "doctor_id": "U0321366704108081152",
#                        "doctor_name": "殷楚芬",
#                        "doctor_title": "副主任医师",
#                        "date_list": [
#                            {
#                                "date": "2025-01-14",
#                                "time_list": [
#                                    {
#                                        "start_time": "15:00",
#                                        "end_time": "15:30",
#                                        "source_num": "14"
#                                    }
#                                ]
#                            }
#                        ]
#                    }
#                ]
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n[\n    {\n        \"科室编号\": \"001\",\n        \"科室名称\": \"呼吸内科门诊\"\n    },\n    {\n        \"科室编号\": \"002\",\n        \"科室名称\": \"耳鼻喉科门诊\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您的病情，我们为您推荐如下预约就诊，您看是否可以？\n[{\n    \"科室编号\": \"5ae37e47016d46aa2073.101211.\",\n    \"科室名称\": \"呼吸内科门诊\",\n    \"医生编号\": \"U0321366704108081152\",\n    \"医生姓名\": \"殷楚芬\",\n    \"医生职称\": \"副主任医师\",\n    \"挂号日期\": \"2025-01-14\",\n    \"起始时间\": \"15:00\",\n    \"终止时间\": \"15:30\",\n    \"号源数量\": \"14\"\n}]"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n【呼吸内科门诊】\n【耳鼻喉科门诊】"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您的病情，我们推荐您在【2025-01-14 15:00-15:30】，前往【呼吸内科门诊 殷楚芬 副主任医师】处进行就诊，您看是否可以？（如果所推荐挂号不符合您的预期，可以直接告诉我您的挂号要求，我将为您重新推荐。例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-流程-3.1患者不修改挂号，直接确认AI推荐的挂号信息
#{
#    "input": {
#        "basic_medical_record": {
#            "chief_complaint": "咳嗽一周伴头痛、嗓子疼。",
#            "history_of_present_illness": "患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。",
#            "past_medical_history": "否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。",
#            "personal_history": "吸烟史：否认；饮酒史：一周一次，一次半斤；",
#            "allergy_history": "药物过敏：否认；食物过敏：牛奶",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        },
#        "all_department": "内容同上，已省略...",
#        "hospital_register": "内容同上，已省略..."
#    },
#    "output": {
#        "chosen_department": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            },
#            {
#                "department_id": "685740a5084c46ab3207.141221.",
#                "department_name": "耳鼻喉科门诊"
#            }
#        ],
#        "hospital_register": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊",
#                "doctor_list": [
#                    {
#                        "doctor_id": "U0321366704108081152",
#                        "doctor_name": "殷楚芬",
#                        "doctor_title": "副主任医师",
#                        "date_list": [
#                            {
#                                "date": "2025-01-14",
#                                "time_list": [
#                                    {
#                                        "start_time": "11:30",
#                                        "end_time": "12:00",
#                                        "source_num": "14"
#                                    }
#                                ]
#                            }
#                        ]
#                    }
#                ]
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n[\n    {\n        \"科室编号\": \"001\",\n        \"科室名称\": \"呼吸内科门诊\"\n    },\n    {\n        \"科室编号\": \"002\",\n        \"科室名称\": \"耳鼻喉科门诊\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您的病情，我们为您推荐如下预约就诊，您看是否可以？\n[{\n    \"科室编号\": \"5ae37e47016d46aa2073.101211.\",\n    \"科室名称\": \"呼吸内科门诊\",\n    \"医生编号\": \"U0321366704108081152\",\n    \"医生姓名\": \"殷楚芬\",\n    \"医生职称\": \"副主任医师\",\n    \"挂号日期\": \"2025-01-14\",\n    \"起始时间\": \"11:30\",\n    \"终止时间\": \"12:00\",\n    \"号源数量\": \"14\"\n}]"
#            },
#            {
#                "role": "user",
#                "content": "好的"
#            },
#            {
#                "role": "assistant",
#                "content": "您已经成功预约了【2025-01-14 11:30-12:00】【呼吸内科门诊 殷楚芬 副主任医师】，请您按时就诊。另外，在您正式就诊前，医生会查阅你的预问诊报告，可能会向您提出新的问题，请注意接收消息并按指引给予回复。"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n【呼吸内科门诊】\n【耳鼻喉科门诊】"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您的病情，我们推荐您在【2025-01-14 11:30-12:00】，前往【呼吸内科门诊 殷楚芬 副主任医师】处进行就诊，您看是否可以？（如果所推荐挂号不符合您的预期，可以直接告诉我您的挂号要求，我将为您重新推荐。例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "好的"
#            },
#            {
#                "role": "assistant",
#                "content": "您已经成功预约了【2025-01-14 11:30-12:00】【呼吸内科门诊 殷楚芬 副主任医师】，请您按时就诊。另外，在您正式就诊前，医生会查阅你的预问诊报告，可能会向您提出新的问题，请注意接收消息并按指引给予回复。"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-流程-3.2患者对话修改挂号信息，直至患者确认AI推荐的挂号信息
#{
#    "input": {
#        "basic_medical_record": {
#            "chief_complaint": "咳嗽一周伴头痛、嗓子疼。",
#            "history_of_present_illness": "患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。",
#            "past_medical_history": "否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。",
#            "personal_history": "吸烟史：否认；饮酒史：一周一次，一次半斤；",
#            "allergy_history": "药物过敏：否认；食物过敏：牛奶",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        },
#        "all_department": "内容同上，已省略...",
#        "hospital_register": "内容同上，已省略..."
#    },
#    "output": {
#        "chosen_department": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            },
#            {
#                "department_id": "685740a5084c46ab3207.141221.",
#                "department_name": "耳鼻喉科门诊"
#            }
#        ],
#        "hospital_register": [
#            {
#                "department_id": "685740a5084c46ab3207.141221.",
#                "department_name": "耳鼻喉科门诊",
#                "doctor_list": [
#                    {
#                        "doctor_id": "U0321366704108081152",
#                        "doctor_name": "宋楚芬",
#                        "doctor_title": "副主任医师",
#                        "date_list": [
#                            {
#                                "date": "2025-01-16",
#                                "time_list": [
#                                    {
#                                        "start_time": "17:30",
#                                        "end_time": "18:00",
#                                        "source_num": "7"
#                                    }
#                                ]
#                            }
#                        ]
#                    }
#                ]
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n[\n    {\n        \"科室编号\": \"001\",\n        \"科室名称\": \"呼吸内科门诊\"\n    },\n    {\n        \"科室编号\": \"002\",\n        \"科室名称\": \"耳鼻喉科门诊\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您的病情，我们为您推荐如下预约就诊，您看是否可以？\n[{\n    \"科室编号\": \"5ae37e47016d46aa2073.101211.\",\n    \"科室名称\": \"呼吸内科门诊\",\n    \"医生编号\": \"U0321366704108081152\",\n    \"医生姓名\": \"殷楚芬\",\n    \"医生职称\": \"副主任医师\",\n    \"挂号日期\": \"2025-01-14\",\n    \"起始时间\": \"11:30\",\n    \"终止时间\": \"12:00\",\n    \"号源数量\": \"14\"\n}]"
#            },
#            {
#                "role": "user",
#                "content": "有其他科室的号吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"U0321366704108081152\", \"医生姓名\": \"宋楚芬\", \"医生职称\": \"副主任医师\", \"挂号日期\": \"2025-01-14\", \"起始时间\": \"15:00\", \"终止时间\": \"15:30\", \"号源数量\": \"14\"}]"
#            },
#            {
#                "role": "user",
#                "content": "有宋慧医生的号吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"396\", \"医生姓名\": \"宋慧\", \"医生职称\": \"主任医师\", \"挂号日期\": \"2025-01-14\", \"起始时间\": \"15:00\", \"终止时间\": \"15:30\", \"号源数量\": \"14\"}]"
#            },
#            {
#                "role": "user",
#                "content": "我想挂副主任的号"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"U0321366704108081152\", \"医生姓名\": \"宋楚芬\", \"医生职称\": \"副主任医师\", \"挂号日期\": \"2025-01-14\", \"起始时间\": \"15:00\", \"终止时间\": \"15:30\", \"号源数量\": \"14\"}]"
#            },
#            {
#                "role": "user",
#                "content": "我今天和明天都没有空"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"U0321366704108081152\", \"医生姓名\": \"宋楚芬\", \"医生职称\": \"副主任医师\", \"挂号日期\": \"2025-01-16\", \"起始时间\": \"15:00\", \"终止时间\": \"15:30\", \"号源数量\": \"7\"}]"
#            },
#            {
#                "role": "user",
#                "content": "还是这天，有上午的吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"U0321366704108081152\", \"医生姓名\": \"宋楚芬\", \"医生职称\": \"副主任医师\", \"挂号日期\": \"2025-01-16\", \"起始时间\": \"09:00\", \"终止时间\": \"09:30\", \"号源数量\": \"7\"}]"
#            },
#            {
#                "role": "user",
#                "content": "上午11点半的有吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"U0321366704108081152\", \"医生姓名\": \"宋楚芬\", \"医生职称\": \"副主任医师\", \"挂号日期\": \"2025-01-16\", \"起始时间\": \"11:30\", \"终止时间\": \"12:00\", \"号源数量\": \"7\"}]"
#            },
#            {
#                "role": "user",
#                "content": "下晌5点半的呢"
#            },
#            {
#                "role": "assistant",
#                "content": "我们为您推荐如下预约就诊，您看是否可以？ [{\"科室编号\": \"685740a5084c46ab3207.141221.\", \"科室名称\": \"耳鼻喉科门诊\", \"医生编号\": \"U0321366704108081152\", \"医生姓名\": \"宋楚芬\", \"医生职称\": \"副主任医师\", \"挂号日期\": \"2025-01-16\", \"起始时间\": \"17:30\", \"终止时间\": \"18:00\", \"号源数量\": \"7\"}]"
#            },
#            {
#                "role": "user",
#                "content": "可以"
#            },
#            {
#                "role": "assistant",
#                "content": "您已经成功预约了【2025-01-16 17:30-18:00】【耳鼻喉科门诊 宋楚芬 副主任医师】，请您按时就诊。另外，在您正式就诊前，医生会查阅你的预问诊报告，可能会向您提出新的问题，请注意接收消息并按指引给予回复。"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的推荐科室如下：\n【呼吸内科门诊】\n【耳鼻喉科门诊】"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您的病情，我们推荐您在【2025-01-14 11:30-12:00】，前往【呼吸内科门诊 殷楚芬 副主任医师】处进行就诊，您看是否可以？（如果所推荐挂号不符合您的预期，可以直接告诉我您的挂号要求，我将为您重新推荐。例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "有其他科室的号吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-14 15:00-15:30】，前往【耳鼻喉科门诊 宋楚芬 副主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "有宋慧医生的号吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-14 15:00-15:30】，前往【耳鼻喉科门诊 宋慧 主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "我想挂副主任的号"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-14 15:00-15:30】，前往【耳鼻喉科门诊 宋楚芬 副主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "我今天和明天都没有空"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-16 15:00-15:30】，前往【耳鼻喉科门诊 宋楚芬 副主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "还是这天，有上午的吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-16 09:00-09:30】，前往【耳鼻喉科门诊 宋楚芬 副主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "上午11点半的有吗"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-16 11:30-12:00】，前往【耳鼻喉科门诊 宋楚芬 副主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "下晌5点半的呢"
#            },
#            {
#                "role": "assistant",
#                "content": "我们推荐您在【2025-01-16 17:30-18:00】，前往【耳鼻喉科门诊 宋楚芬 副主任医师】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"
#            },
#            {
#                "role": "user",
#                "content": "可以"
#            },
#            {
#                "role": "assistant",
#                "content": "您已经成功预约了【2025-01-16 17:30-18:00】【耳鼻喉科门诊 宋楚芬 副主任医师】，请您按时就诊。另外，在您正式就诊前，医生会查阅你的预问诊报告，可能会向您提出新的问题，请注意接收消息并按指引给予回复。"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}