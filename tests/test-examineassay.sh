# v5-生成检查和化验

#url: http://ip:port/inference?request_type=v5
#输入(input)：
#    client_info（患者基础信息，会用到患者的姓名、性别和年龄，其他的用不到）
#    basic_medical_record（预问诊阶段生成的病历）
#    diagnosis（诊断阶段生成的诊断）
#输出(output)：
#    examine_content（生成检查）
#    assay_content（生成化验）
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示）
#其他:
#    1.在生成的每个检查与化验下，增加corresponding_diagnosis（所针对的诊断）；
#测试脚本：
#    bash test-examineassay.sh

curl -X 'POST' \
  'http://ip:port/inference?request_type=v5' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/examineassay.json

  echo -e "\n==================================\n"

# 测试结果-疑似
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "女",
#                    "patient_age": "76",
#                    "if_child": "否",
#                    "certificate_type": "",
#                    "certificate_number": "",
#                    "mobile_number": "",
#                    "current_address": {
#                        "province": "",
#                        "city": "",
#                        "district": "",
#                        "street": ""
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "",
#                    "certificate_type": "",
#                    "certificate_number": ""
#                }
#            }
#        ],
#        "basic_medical_record": {
#            "chief_complaint": "解黑便11小时",
#            "history_of_present_illness": "昨晚20时开始无明显诱因出现解黑便2次，呈黑色成形大便，每次量约100g，伴阵发性腹部隐痛，偶有头晕、出冷汗，有气促，无晕厥，无胸痛、胸闷，无呕吐，无发热",
#            "past_medical_history": "胃窦部溃疡伴出血、肺部感染、糜烂性胃炎、十二指肠炎、贫血、高血压病和腰椎退行性病变，骨质疏松，电解质紊乱，老年性心脏瓣膜病，高血压病史多年，长期服药治疗，否认糖尿病",
#            "personal_history": "否认吸烟、酗酒、或过度劳累等习惯",
#            "allergy_history": "否认药物和食物过敏史",
#            "physical_examination": "体温： 36.5℃ ， 脉搏： 86次/分， 血压： 150/61mmHg,呼吸:18次",
#            "auxiliary_examination": ""
#        },
#        "diagnosis": [
#            {
#                "diagnosis_name": "上消化道出血",
#                "diagnosis_name_retrieve": "上消化道出血",
#                "diagnosis_code": "K92.208",
#                "diagnosis_identifier": "疑似"
#            },
#            {
#                "diagnosis_name": "贫血",
#                "diagnosis_name_retrieve": "贫血",
#                "diagnosis_code": "D64.900",
#                "diagnosis_identifier": "疑似"
#            }
#        ]
#    },
#    "output": {
#        "examine_content": [
#            {
#                "examine_code": "#701",
#                "examine_category": "胃肠镜",
#                "examine_name": "胃镜检查",
#                "examine_name_retrieve": "无痛胃镜检查",
#                "order_quantity": "1",
#                "examine_result": "",
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "上消化道出血",
#                        "diagnosis_name_retrieve": "上消化道出血",
#                        "diagnosis_code": "K92.208",
#                        "diagnosis_identifier": "疑似"
#                    },
#                    {
#                        "diagnosis_name": "贫血",
#                        "diagnosis_name_retrieve": "贫血",
#                        "diagnosis_code": "D64.900",
#                        "diagnosis_identifier": "疑似"
#                    }
#                ]
#            }
#        ],
#        "assay_content": [
#            {
#                "assay_code": "559258",
#                "assay_category": "临检类",
#                "assay_name": "血红蛋白",
#                "assay_name_retrieve": "血红蛋白电泳",
#                "order_quantity": "1",
#                "assay_result": [],
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "贫血",
#                        "diagnosis_name_retrieve": "贫血",
#                        "diagnosis_code": "D64.900",
#                        "diagnosis_identifier": "疑似"
#                    }
#                ]
#            },
#            {
#                "assay_code": "559053",
#                "assay_category": "临检类",
#                "assay_name": "红细胞计数",
#                "assay_name_retrieve": "有核红细胞计数",
#                "order_quantity": "1",
#                "assay_result": [],
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "贫血",
#                        "diagnosis_name_retrieve": "贫血",
#                        "diagnosis_code": "D64.900",
#                        "diagnosis_identifier": "疑似"
#                    }
#                ]
#            },
#            {
#                "assay_code": "560503",
#                "assay_category": "临检类",
#                "assay_name": "血清胆红素",
#                "assay_name_retrieve": "血清总胆红素测定(化学法或酶促法)",
#                "order_quantity": "1",
#                "assay_result": [],
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "上消化道出血",
#                        "diagnosis_name_retrieve": "上消化道出血",
#                        "diagnosis_code": "K92.208",
#                        "diagnosis_identifier": "疑似"
#                    }
#                ]
#            },
#            {
#                "assay_code": "559342",
#                "assay_category": "临检类",
#                "assay_name": "凝血酶原时间",
#                "assay_name_retrieve": "血浆凝血酶原时间测定(PT:仪器法)",
#                "order_quantity": "1",
#                "assay_result": [],
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "上消化道出血",
#                        "diagnosis_name_retrieve": "上消化道出血",
#                        "diagnosis_code": "K92.208",
#                        "diagnosis_identifier": "疑似"
#                    }
#                ]
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "根据诊断中为疑似的项，现在为您生成检查项或化验项：\n{\n\"检查\": [{\n       \"检查编号\": \"CK001\",\n       \"检查类型\": \"内镜检查\",\n       \"检查名称\": \"胃镜检查\",\n       \"针对疾病\": [\n           {\n               \"诊断名称\": \"上消化道出血\"\n           },\n           {\n               \"诊断名称\": \"贫血\"\n           }\n       ],\n       \"开单数量\": \"1\"\n    }],\n\"化验\": [{\n        \"项目编号\": \"JY001\",\n        \"项目类型\": \"血常规\",\n        \"项目名称\": \"血红蛋白\",\n        \"针对疾病\": [\n            {\n                \"诊断名称\": \"贫血\"\n            }\n        ],\n        \"开单数量\": \"1\"\n    },\n    {\n        \"项目编号\": \"JY002\",\n        \"项目类型\": \"血常规\",\n        \"项目名称\": \"红细胞计数\",\n        \"针对疾病\": [\n            {\n                \"诊断名称\": \"贫血\"\n            }\n        ],\n        \"开单数量\": \"1\"\n    },\n    {\n        \"项目编号\": \"JY003\",\n        \"项目类型\": \"肝功能\",\n        \"项目名称\": \"血清胆红素\",\n        \"针对疾病\": [\n            {\n                \"诊断名称\": \"上消化道出血\"\n            }\n        ],\n        \"开单数量\": \"1\"\n    },\n    {\n        \"项目编号\": \"JY004\",\n        \"项目类型\": \"凝血功能\",\n        \"项目名称\": \"凝血酶原时间\",\n        \"针对疾病\": [\n            {\n                \"诊断名称\": \"上消化道出血\"\n            }\n        ],\n        \"开单数量\": \"1\"\n    }]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "根据诊断中为疑似的项，现在为您生成检查项或化验项：\n检查项：\n【检查编号：CK001  检查类型：内镜检查  检查名称：胃镜检查  开单数量：1  针对疾病：上消化道出血、贫血】\n化验项：\n【化验编号：JY001  化验类型：血常规  化验名称：血红蛋白  开单数量：1  针对疾病：贫血】\n【化验编号：JY002  化验类型：血常规  化验名称：红细胞计数  开单数量：1  针对疾病：贫血】\n【化验编号：JY003  化验类型：肝功能  化验名称：血清胆红素  开单数量：1  针对疾病：上消化道出血】\n【化验编号：JY004  化验类型：凝血功能  化验名称：凝血酶原时间  开单数量：1  针对疾病：上消化道出血】"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






# 测试结果-确诊
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "女",
#                    "patient_age": "76",
#                    "if_child": "否",
#                    "certificate_type": "",
#                    "certificate_number": "",
#                    "mobile_number": "",
#                    "current_address": {
#                        "province": "",
#                        "city": "",
#                        "district": "",
#                        "street": ""
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "",
#                    "certificate_type": "",
#                    "certificate_number": ""
#                }
#            }
#        ],
#        "basic_medical_record": {
#            "chief_complaint": "解黑便11小时",
#            "history_of_present_illness": "昨晚20时开始无明显诱因出现解黑便2次，呈黑色成形大便，每次量约100g，伴阵发性腹部隐痛，偶有头晕、出冷汗，有气促，无晕厥，无胸痛、胸闷，无呕吐，无发热",
#            "past_medical_history": "胃窦部溃疡伴出血、肺部感染、糜烂性胃炎、十二指肠炎、贫血、高血压病和腰椎退行性病变，骨质疏松，电解质紊乱，老年性心脏瓣膜病，高血压病史多年，长期服药治疗，否认糖尿病",
#            "personal_history": "否认吸烟、酗酒、或过度劳累等习惯",
#            "allergy_history": "否认药物和食物过敏史",
#            "physical_examination": "体温： 36.5℃ ， 脉搏： 86次/分， 血压： 150/61mmHg,呼吸:18次",
#            "auxiliary_examination": ""
#        },
#        "diagnosis": [
#            {
#                "diagnosis_name": "上消化道出血",
#                "diagnosis_name_retrieve": "上消化道出血",
#                "diagnosis_code": "K92.208",
#                "diagnosis_identifier": "确诊"
#            },
#            {
#                "diagnosis_name": "贫血",
#                "diagnosis_name_retrieve": "贫血",
#                "diagnosis_code": "D64.900",
#                "diagnosis_identifier": "确诊"
#            }
#        ]
#    },
#    "output": {
#        "examine_content": [
#            {
#                "examine_code": "",
#                "examine_category": "",
#                "examine_name": "",
#                "examine_name_retrieve": "",
#                "order_quantity": "",
#                "examine_result": "",
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "",
#                        "diagnosis_name_retrieve": "",
#                        "diagnosis_code": "",
#                        "diagnosis_identifier": ""
#                    }
#                ]
#            }
#        ],
#        "assay_content": [
#            {
#                "assay_code": "",
#                "assay_category": "",
#                "assay_name": "",
#                "assay_name_retrieve": "",
#                "order_quantity": "",
#                "assay_result": [
#                    {
#                        "result_id": "",
#                        "result_item": "",
#                        "result_value": 0.0,
#                        "result_identifier": "",
#                        "reference_value": "",
#                        "unit": ""
#                    }
#                ],
#                "corresponding_diagnosis": [
#                    {
#                        "diagnosis_name": "",
#                        "diagnosis_name_retrieve": "",
#                        "diagnosis_code": "",
#                        "diagnosis_identifier": ""
#                    }
#                ]
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您的病历已经确诊，无需生成检查项或化验项。"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您的病历已经确诊，无需生成检查项或化验项。"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}
