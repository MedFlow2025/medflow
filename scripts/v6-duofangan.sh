# v6-生成多方案

#url
#    挑选方案：http://ip:port/inference?request_type=v6&scheme=pick_therapy
#    默认方案-处方: http://ip:port/inference?request_type=v6&scheme=default_therapy&sub_scheme=prescription
#    默认方案-输液: http://ip:port/inference?request_type=v6&scheme=default_therapy&sub_scheme=transfusion
#    默认方案-处置: http://ip:port/inference?request_type=v6&scheme=default_therapy&sub_scheme=disposition
#    其他方案-手术治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=surgical_therapy
#    其他方案-化学治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=chemo_therapy
#    其他方案-放射治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=radiation_therapy
#    其他方案-心理治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=psycho_therapy
#    其他方案-康复治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=rehabilitation_therapy
#    其他方案-物理治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=physical_therapy
#    其他方案-替代疗法: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=alternative_therapy
#    其他方案-观察治疗: http://ip:port/inference?request_type=v6&scheme=other_therapy&sub_scheme=observation_therapy
#输入(input)：
#    client_info（患者基础信息，会用到患者的姓名、性别和年龄，其他的用不到）
#    basic_medical_record（预问诊阶段生成的病历）
#    diagnosis（诊断阶段生成的诊断，疑似和诊断均可以）
#输出(output)：
#   挑选方案：
#       pick_therapy: 挑选出适合该病历的治疗方案，并对所选方案进行解读。包括默认方案(default_therapy)与其他方案(挑选2-4种)
#   默认方案：
#       default_therapy: 默认方案，包括处方、输液和处置
#   其他方案：
#       surgical_therapy: 手术治疗
#       chemo_therapy: 化学治疗
#       radiation_therapy: 放射治疗
#       psycho_therapy: 心理治疗
#       rehabilitation_therapy: 康复治疗
#       physical_therapy: 物理治疗
#       alternative_therapy: 替代疗法
#       observation_therapy: 观察治疗
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示）
#步骤：
#    1.挑选方案: 
#        查询参数 &scheme=pick_therapy 时(&sub_scheme不用写)，发送请求后，更新output.pick_therapy，见测试结果(1)
#    2.默认方案: (每次请求只生成一个处方，如果需要多个处方，可同时发送多次请求，输液和处置也是。)
#        查询参数 &scheme=default_therapy&sub_scheme=prescription，发送请求后，更新output.default_therapy.prescription，见测试结果(2.1)
#        查询参数 &scheme=default_therapy&sub_scheme=transfusion，发送请求后，更新output.default_therapy.transfusion，见测试结果(2.2)
#        查询参数 &scheme=default_therapy&sub_scheme=disposition，发送请求后，更新output.default_therapy.disposition，见测试结果(2.3)
#    3.其他方案:(每次请求只生成一个手术治疗，如果需要多个手术治疗，可同时发送多次请求，化学治疗、放射治疗等其他治疗也是。)
#        查询参数 &scheme=other_therapy&sub_scheme=步骤1中挑选的方案之一，更新output.步骤1中挑选的方案之一.method
#        假设步骤1中挑选的方案有surgical_therapy、rehabilitation_therapy、default_therapy，此处可使用:
#            查询参数 &scheme=other_therapy&sub_scheme=surgical_therapy，更新output.surgical_therapy.method，见测试结果(3.1)
#            查询参数 &scheme=other_therapy&sub_scheme=rehabilitation_therapy，更新output.rehabilitation_therapy.method，见测试结果(3.2)
#测试脚本：
#    bash v6-duofangan.sh
curl -X 'POST' \
  'http://ip:port/inference?request_type=v6&scheme=pick_therapy' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '
{
    "input": {
        "client_info": [{
            "patient": {
                "patient_name": "张三",
                "patient_gender": "女",
                "patient_age": "76",
                "if_child": "否",
                "certificate_type": "",
                "certificate_number": "",
                "mobile_number": "",
                "current_address": {
                    "province": "",
                    "city": "",
                    "district": "",
                    "street": ""
                },
                "detailed_address": ""
            },
            "guardian": {
                "guardian_name": "",
                "certificate_type": "",
                "certificate_number": ""
            }
        }],
        "basic_medical_record": {
            "chief_complaint": "解黑便11小时",
            "history_of_present_illness": "昨晚20时开始无明显诱因出现解黑便2次，呈黑色成形大便，每次量约100g，伴阵发性腹部隐痛，偶有头晕、出冷汗，有气促，无晕厥，无胸痛、胸闷，无呕吐，无发热",
            "past_medical_history": "胃窦部溃疡伴出血、肺部感染、糜烂性胃炎、十二指肠炎、贫血、高血压病和腰椎退行性病变，骨质疏松，电解质紊乱，老年性心脏瓣膜病，高血压病史多年，长期服药治疗，否认糖尿病",
            "personal_history": "否认吸烟、酗酒、或过度劳累等习惯",
            "allergy_history": "否认药物和食物过敏史",
            "physical_examination": "体温： 36.5℃ ， 脉搏： 86次/分， 血压： 150/61mmHg,呼吸:18次",
            "auxiliary_examination": ""
        },
        "diagnosis": [
            {
                "diagnosis_name": "上消化道出血",
                "diagnosis_name_retrieve": "上消化道出血",
                "diagnosis_code": "K92.208",
                "diagnosis_identifier": "确诊"
            },
            {
                "diagnosis_name": "贫血",
                "diagnosis_name_retrieve": "贫血",
                "diagnosis_code": "D64.900",
                "diagnosis_identifier": "确诊"
            }
        ]
    },
    "output": {
        "pick_therapy": [],
        "default_therapy": {
            "prescription": [],
            "transfusion": [],
            "disposition": []
        },
        "surgical_therapy": {
            "method": []
        },
        "chemo_therapy": {
            "method": []
        },
        "radiation_therapy": {
            "method": []
        },
        "psycho_therapy": {
            "method": []
        },
        "rehabilitation_therapy": {
            "method": []
        },
        "physical_therapy": {
            "method": []
        },
        "alternative_therapy": {
            "method": []
        },
        "observation_therapy": {
            "method": []
        }
    },
    "chat": {
        "historical_conversations_bak": [],
        "historical_conversations": [],
        "prompt_version": "v1",
        "model_name": "model_medical_20250122"
    }
}
'






# 测试结果(1)-挑选方案(&scheme=pick_therapy)
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "76",
#                "if_child": "否",
#                "certificate_type": "",
#                "certificate_number": "",
#                "mobile_number": "",
#                "current_address": {
#                    "province": "",
#                    "city": "",
#                    "district": "",
#                    "street": ""
#                },
#                "detailed_address": ""
#            },
#            "guardian": {
#                "guardian_name": "",
#                "certificate_type": "",
#                "certificate_number": ""
#            }
#        }],
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
#        "pick_therapy": [
#            {
#                "picked_therapy": "default_therapy",
#                "interpret_therapy": "针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。"
#            },
#            {
#                "picked_therapy": "surgical_therapy",
#                "interpret_therapy": "如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。"
#            },
#            {
#                "picked_therapy": "rehabilitation_therapy",
#                "interpret_therapy": "康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。"
#            }
#        ],
#        "default_therapy": {
#            "prescription": [],
#            "transfusion": [],
#            "disposition": []
#        },
#        "surgical_therapy": {
#            "method": []
#        },
#        "chemo_therapy": {
#            "method": []
#        },
#        "radiation_therapy": {
#            "method": []
#        },
#        "psycho_therapy": {
#            "method": []
#        },
#        "rehabilitation_therapy": {
#            "method": []
#        },
#        "physical_therapy": {
#            "method": []
#        },
#        "alternative_therapy": {
#            "method": []
#        },
#        "observation_therapy": {
#            "method": []
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}





# 测试结果(2.1)-默认方案-处方(&scheme=default_therapy&sub_scheme=prescription)
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "76",
#                "if_child": "否",
#                "certificate_type": "",
#                "certificate_number": "",
#                "mobile_number": "",
#                "current_address": {
#                    "province": "",
#                    "city": "",
#                    "district": "",
#                    "street": ""
#                },
#                "detailed_address": ""
#            },
#            "guardian": {
#                "guardian_name": "",
#                "certificate_type": "",
#                "certificate_number": ""
#            }
#        }],
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
#        "pick_therapy": [
#            {
#                "picked_therapy": "default_therapy",
#                "interpret_therapy": "针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。"
#            },
#            {
#                "picked_therapy": "surgical_therapy",
#                "interpret_therapy": "如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。"
#            },
#            {
#                "picked_therapy": "rehabilitation_therapy",
#                "interpret_therapy": "康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。"
#            }
#        ],
#        "default_therapy": {
#            "prescription": [
#                {
#                    "prescription_content": [
#                        {
#                            "drug_id": "103012",
#                            "drug_name": "维生素C片",
#                            "drug_name_retrieve": "维生素C片（乙自选）",
#                            "drug_specification": "0.1g*100",
#                            "manufacturer_name": "XXXXXXXX制药厂",
#                            "order_quantity": "10",
#                            "order_unit": "片",
#                            "route_of_administration": "片剂",
#                            "dosage": "1粒",
#                            "duration": "7天",
#                            "frequency": "每日3次",
#                            "corresponding_diseases": "贫血",
#                            "drug_efficacy": "维生素C可参与铁的吸收，并且有助合成血红蛋白，对改善贫血症状有积极作用。"
#                        },
#                        {
#                            "drug_id": "30987",
#                            "drug_name": "云南白药胶囊",
#                            "drug_name_retrieve": "云南白药气雾剂(丙国基)",
#                            "drug_specification": "60g*50g",
#                            "manufacturer_name": "云南生物谷植物药业有限公司",
#                            "order_quantity": "10",
#                            "order_unit": "瓶",
#                            "route_of_administration": "吸入气雾剂",
#                            "dosage": "1粒",
#                            "duration": "7天",
#                            "frequency": "每日3次",
#                            "corresponding_diseases": "上消化道出血",
#                            "drug_efficacy": "云南白药具有止血、消肿、镇痛的作用，适用于上消化道出血的治疗。"
#                        },
#                        {
#                            "drug_id": "10445",
#                            "drug_name": "硫酸亚铁胶囊",
#                            "drug_name_retrieve": "硫酸亚铁片（甲国基）",
#                            "drug_specification": "0.3g*100",
#                            "manufacturer_name": "XXXXXXXX制药厂",
#                            "order_quantity": "10",
#                            "order_unit": "片",
#                            "route_of_administration": "片剂",
#                            "dosage": "1粒",
#                            "duration": "7天",
#                            "frequency": "每日3次",
#                            "corresponding_diseases": "贫血",
#                            "drug_efficacy": "硫酸亚铁是常用的补铁药物，可以补充体内缺乏的铁离子，促进血红蛋白的合成和红细胞的生成，从而缓解贫血症状。"
#                        }
#                    ]
#                }
#            ],
#            "transfusion": [],
#            "disposition": []
#        },
#        "surgical_therapy": {
#            "method": []
#        },
#        "chemo_therapy": {
#            "method": []
#        },
#        "radiation_therapy": {
#            "method": []
#        },
#        "psycho_therapy": {
#            "method": []
#        },
#        "rehabilitation_therapy": {
#            "method": []
#        },
#        "physical_therapy": {
#            "method": []
#        },
#        "alternative_therapy": {
#            "method": []
#        },
#        "observation_therapy": {
#            "method": []
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成处方：\n\n{\n\"处方\": [{\n    \"药品编号\": \"YP123456\",\n    \"药品名称\": \"维生素C片\",\n    \"药品规格\": \"0.1g*100\",\n    \"厂家名称\": \"XXXXXXXX制药厂\",\n    \"开单数量\": \"10\",\n    \"开单单位\": \"粒\",\n    \"用药途径\": \"口服\",\n    \"单次剂量\": \"1粒\",\n    \"持续天数\": \"7天\",\n    \"用药频次\": \"每日3次\",\n    \"针对疾病\": \"贫血\",\n    \"药品作用\": \"维生素C可参与铁的吸收，并且有助合成血红蛋白，对改善贫血症状有积极作用。\"\n},\n{\n    \"药品编号\": \"YP123457\",\n    \"药品名称\": \"云南白药胶囊\",\n    \"药品规格\": \"0.25g*100粒\",\n    \"厂家名称\": \"云南生物谷植物药业有限公司\",\n    \"开单数量\": \"10\",\n    \"开单单位\": \"粒\",\n    \"用药途径\": \"口服\",\n    \"单次剂量\": \"1粒\",\n    \"持续天数\": \"7天\",\n    \"用药频次\": \"每日3次\",\n    \"针对疾病\": \"上消化道出血\",\n    \"药品作用\": \"云南白药具有止血、消肿、镇痛的作用，适用于上消化道出血的治疗。\"\n},\n{\n    \"药品编号\": \"YP123458\",\n    \"药品名称\": \"硫酸亚铁胶囊\",\n    \"药品规格\": \"0.3g*100粒\",\n    \"厂家名称\": \"XXXXXXXX制药厂\",\n    \"开单数量\": \"10\",\n    \"开单单位\": \"粒\",\n    \"用药途径\": \"口服\",\n    \"单次剂量\": \"1粒\",\n    \"持续天数\": \"7天\",\n    \"用药频次\": \"每日3次\",\n    \"针对疾病\": \"贫血\",\n    \"药品作用\": \"硫酸亚铁是常用的补铁药物，可以补充体内缺乏的铁离子，促进血红蛋白的合成和红细胞的生成，从而缓解贫血症状。\"\n}\n]}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成处方：\n\n{\n\"处方\": [{\n    \"药品编号\": \"YP123456\",\n    \"药品名称\": \"维生素C片\",\n    \"药品规格\": \"0.1g*100\",\n    \"厂家名称\": \"XXXXXXXX制药厂\",\n    \"开单数量\": \"10\",\n    \"开单单位\": \"粒\",\n    \"用药途径\": \"口服\",\n    \"单次剂量\": \"1粒\",\n    \"持续天数\": \"7天\",\n    \"用药频次\": \"每日3次\",\n    \"针对疾病\": \"贫血\",\n    \"药品作用\": \"维生素C可参与铁的吸收，并且有助合成血红蛋白，对改善贫血症状有积极作用。\"\n},\n{\n    \"药品编号\": \"YP123457\",\n    \"药品名称\": \"云南白药胶囊\",\n    \"药品规格\": \"0.25g*100粒\",\n    \"厂家名称\": \"云南生物谷植物药业有限公司\",\n    \"开单数量\": \"10\",\n    \"开单单位\": \"粒\",\n    \"用药途径\": \"口服\",\n    \"单次剂量\": \"1粒\",\n    \"持续天数\": \"7天\",\n    \"用药频次\": \"每日3次\",\n    \"针对疾病\": \"上消化道出血\",\n    \"药品作用\": \"云南白药具有止血、消肿、镇痛的作用，适用于上消化道出血的治疗。\"\n},\n{\n    \"药品编号\": \"YP123458\",\n    \"药品名称\": \"硫酸亚铁胶囊\",\n    \"药品规格\": \"0.3g*100粒\",\n    \"厂家名称\": \"XXXXXXXX制药厂\",\n    \"开单数量\": \"10\",\n    \"开单单位\": \"粒\",\n    \"用药途径\": \"口服\",\n    \"单次剂量\": \"1粒\",\n    \"持续天数\": \"7天\",\n    \"用药频次\": \"每日3次\",\n    \"针对疾病\": \"贫血\",\n    \"药品作用\": \"硫酸亚铁是常用的补铁药物，可以补充体内缺乏的铁离子，促进血红蛋白的合成和红细胞的生成，从而缓解贫血症状。\"\n}\n]}"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}





# 测试结果(2.2)-默认方案-输液(&scheme=default_therapy&sub_scheme=transfusion)
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "76",
#                "if_child": "否",
#                "certificate_type": "",
#                "certificate_number": "",
#                "mobile_number": "",
#                "current_address": {
#                    "province": "",
#                    "city": "",
#                    "district": "",
#                    "street": ""
#                },
#                "detailed_address": ""
#            },
#            "guardian": {
#                "guardian_name": "",
#                "certificate_type": "",
#                "certificate_number": ""
#            }
#        }],
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
#        "pick_therapy": [
#            {
#                "picked_therapy": "default_therapy",
#                "interpret_therapy": "针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。"
#            },
#            {
#                "picked_therapy": "surgical_therapy",
#                "interpret_therapy": "如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。"
#            },
#            {
#                "picked_therapy": "rehabilitation_therapy",
#                "interpret_therapy": "康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。"
#            }
#        ],
#        "default_therapy": {
#            "prescription": [],
#            "transfusion": [
#                {
#                    "transfusion_content": [
#                        {
#                            "drug_id": "103031",
#                            "drug_name": "维生素K1注射液",
#                            "drug_name_retrieve": "维生素B1片(乙自选）",
#                            "drug_specification": "10mg*100",
#                            "manufacturer_name": "XXXXXXXX制药股份有限公司",
#                            "order_quantity": "1",
#                            "order_unit": "片",
#                            "route_of_administration": "片剂",
#                            "dosage": "1支",
#                            "duration": "1天",
#                            "frequency": "每日1次",
#                            "corresponding_diseases": "上消化道出血",
#                            "drug_efficacy": "本药是一种维生素K1，用于治疗因维生素K缺乏引起的出血，可作为上消化道出血的治疗药物，有助于凝血功能恢复。",
#                            "infusion_group": "第一组",
#                            "infusion_rate": "30gtt/min"
#                        },
#                        {
#                            "drug_id": "ZS123457",
#                            "drug_name": "山梨醇铁注射液",
#                            "drug_name_retrieve": "",
#                            "drug_specification": "100mg*20ml",
#                            "manufacturer_name": "XXXXXXXX制药股份有限公司",
#                            "order_quantity": "1",
#                            "order_unit": "支",
#                            "route_of_administration": "静脉滴注",
#                            "dosage": "1支",
#                            "duration": "1天",
#                            "frequency": "每日1次",
#                            "corresponding_diseases": "贫血",
#                            "drug_efficacy": "本药的主要成分为山梨醇铁，是治疗缺铁性贫血的常用药，可以补充体内铁元素，促进血红蛋白的合成，缓解贫血症状。",
#                            "infusion_group": "第二组",
#                            "infusion_rate": "30gtt/min"
#                        }
#                    ]
#                }
#            ],
#            "disposition": []
#        },
#        "surgical_therapy": {
#            "method": []
#        },
#        "chemo_therapy": {
#            "method": []
#        },
#        "radiation_therapy": {
#            "method": []
#        },
#        "psycho_therapy": {
#            "method": []
#        },
#        "rehabilitation_therapy": {
#            "method": []
#        },
#        "physical_therapy": {
#            "method": []
#        },
#        "alternative_therapy": {
#            "method": []
#        },
#        "observation_therapy": {
#            "method": []
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成输液：\n\n{\n\"输液\": [\n  {\n    \"药品编号\": \"ZS123456\",\n    \"药品名称\": \"维生素K1注射液\",\n    \"药品规格\": \"10mg*2ml\",\n    \"厂家名称\": \"XXXXXXXX制药股份有限公司\",\n    \"开单数量\": \"1\",\n    \"开单单位\": \"支\",\n    \"用药途径\": \"静脉滴注\",\n    \"单次剂量\": \"1支\",\n    \"持续天数\": \"1天\",\n    \"用药频次\": \"每日1次\",\n    \"针对疾病\": \"上消化道出血\",\n    \"药品作用\": \"本药是一种维生素K1，用于治疗因维生素K缺乏引起的出血，可作为上消化道出血的治疗药物，有助于凝血功能恢复。\",\n    \"输液分组\": \"第一组\",\n    \"输液速度\": \"30gtt/min\"\n  },\n  {\n    \"药品编号\": \"ZS123457\",\n    \"药品名称\": \"山梨醇铁注射液\",\n    \"药品规格\": \"100mg*20ml\",\n    \"厂家名称\": \"XXXXXXXX制药股份有限公司\",\n    \"开单数量\": \"1\",\n    \"开单单位\": \"支\",\n    \"用药途径\": \"静脉滴注\",\n    \"单次剂量\": \"1支\",\n    \"持续天数\": \"1天\",\n    \"用药频次\": \"每日1次\",\n    \"针对疾病\": \"贫血\",\n    \"药品作用\": \"本药的主要成分为山梨醇铁，是治疗缺铁性贫血的常用药，可以补充体内铁元素，促进血红蛋白的合成，缓解贫血症状。\",\n    \"输液分组\": \"第二组\",\n    \"输液速度\": \"30gtt/min\"\n  }\n]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成输液：\n\n{\n\"输液\": [\n  {\n    \"药品编号\": \"ZS123456\",\n    \"药品名称\": \"维生素K1注射液\",\n    \"药品规格\": \"10mg*2ml\",\n    \"厂家名称\": \"XXXXXXXX制药股份有限公司\",\n    \"开单数量\": \"1\",\n    \"开单单位\": \"支\",\n    \"用药途径\": \"静脉滴注\",\n    \"单次剂量\": \"1支\",\n    \"持续天数\": \"1天\",\n    \"用药频次\": \"每日1次\",\n    \"针对疾病\": \"上消化道出血\",\n    \"药品作用\": \"本药是一种维生素K1，用于治疗因维生素K缺乏引起的出血，可作为上消化道出血的治疗药物，有助于凝血功能恢复。\",\n    \"输液分组\": \"第一组\",\n    \"输液速度\": \"30gtt/min\"\n  },\n  {\n    \"药品编号\": \"ZS123457\",\n    \"药品名称\": \"山梨醇铁注射液\",\n    \"药品规格\": \"100mg*20ml\",\n    \"厂家名称\": \"XXXXXXXX制药股份有限公司\",\n    \"开单数量\": \"1\",\n    \"开单单位\": \"支\",\n    \"用药途径\": \"静脉滴注\",\n    \"单次剂量\": \"1支\",\n    \"持续天数\": \"1天\",\n    \"用药频次\": \"每日1次\",\n    \"针对疾病\": \"贫血\",\n    \"药品作用\": \"本药的主要成分为山梨醇铁，是治疗缺铁性贫血的常用药，可以补充体内铁元素，促进血红蛋白的合成，缓解贫血症状。\",\n    \"输液分组\": \"第二组\",\n    \"输液速度\": \"30gtt/min\"\n  }\n]\n}"
#            }
#        ]
#    }
#}





# 测试结果(2.3)-默认方案-处置(&scheme=default_therapy&sub_scheme=disposition)
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "76",
#                "if_child": "否",
#                "certificate_type": "",
#                "certificate_number": "",
#                "mobile_number": "",
#                "current_address": {
#                    "province": "",
#                    "city": "",
#                    "district": "",
#                    "street": ""
#                },
#                "detailed_address": ""
#            },
#            "guardian": {
#                "guardian_name": "",
#                "certificate_type": "",
#                "certificate_number": ""
#            }
#        }],
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
#        "pick_therapy": [
#            {
#                "picked_therapy": "default_therapy",
#                "interpret_therapy": "针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。"
#            },
#            {
#                "picked_therapy": "surgical_therapy",
#                "interpret_therapy": "如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。"
#            },
#            {
#                "picked_therapy": "rehabilitation_therapy",
#                "interpret_therapy": "康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。"
#            }
#        ],
#        "default_therapy": {
#            "prescription": [],
#            "transfusion": [],
#            "disposition": [
#                {
#                    "disposition_content": [
#                        {
#                            "disposition_id": "CZ123457",
#                            "disposition_name": "输血治疗",
#                            "disposition_name_retrieve": "",
#                            "frequency": "根据患者情况调整",
#                            "dosage": "根据患者情况调整",
#                            "duration": "病情稳定至血红蛋白恢复正常"
#                        },
#                        {
#                            "disposition_id": "CZ123458",
#                            "disposition_name": "补铁药物治疗",
#                            "disposition_name_retrieve": "",
#                            "frequency": "根据医嘱",
#                            "dosage": "根据医嘱",
#                            "duration": "医师建议的时间"
#                        }
#                    ]
#                }
#            ]
#        },
#        "surgical_therapy": {
#            "method": []
#        },
#        "chemo_therapy": {
#            "method": []
#        },
#        "radiation_therapy": {
#            "method": []
#        },
#        "psycho_therapy": {
#            "method": []
#        },
#        "rehabilitation_therapy": {
#            "method": []
#        },
#        "physical_therapy": {
#            "method": []
#        },
#        "alternative_therapy": {
#            "method": []
#        },
#        "observation_therapy": {
#            "method": []
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊为上消化道出血和贫血，现在为您生成处置：\n\n{\n    \"处置\": [{\n        \"项目编号\": \"CZ123457\",\n        \"项目名称\": \"输血治疗\",\n        \"频次\": \"根据患者情况调整\",\n        \"单次用量\": \"根据患者情况调整\",\n        \"持续时间\": \"病情稳定至血红蛋白恢复正常\"\n    },\n    {\n        \"项目编号\": \"CZ123458\",\n        \"项目名称\": \"补铁药物治疗\",\n        \"频次\": \"根据医嘱\",\n        \"单次用量\": \"根据医嘱\",\n        \"持续时间\": \"医师建议的时间\"\n    }]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊为上消化道出血和贫血，现在为您生成处置：\n\n{\n    \"处置\": [{\n        \"项目编号\": \"CZ123457\",\n        \"项目名称\": \"输血治疗\",\n        \"频次\": \"根据患者情况调整\",\n        \"单次用量\": \"根据患者情况调整\",\n        \"持续时间\": \"病情稳定至血红蛋白恢复正常\"\n    },\n    {\n        \"项目编号\": \"CZ123458\",\n        \"项目名称\": \"补铁药物治疗\",\n        \"频次\": \"根据医嘱\",\n        \"单次用量\": \"根据医嘱\",\n        \"持续时间\": \"医师建议的时间\"\n    }]\n}"
#            }
#        ]
#    }
#}





# 测试结果(3.1)-其他方案-手术治疗(&scheme=other_therapy&sub_scheme=surgical_therapy)
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "76",
#                "if_child": "否",
#                "certificate_type": "",
#                "certificate_number": "",
#                "mobile_number": "",
#                "current_address": {
#                    "province": "",
#                    "city": "",
#                    "district": "",
#                    "street": ""
#                },
#                "detailed_address": ""
#            },
#            "guardian": {
#                "guardian_name": "",
#                "certificate_type": "",
#                "certificate_number": ""
#            }
#        }],
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
#        "pick_therapy": [
#            {
#                "picked_therapy": "default_therapy",
#                "interpret_therapy": "针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。"
#            },
#            {
#                "picked_therapy": "surgical_therapy",
#                "interpret_therapy": "如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。"
#            },
#            {
#                "picked_therapy": "rehabilitation_therapy",
#                "interpret_therapy": "康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。"
#            }
#        ],
#        "default_therapy": {
#            "prescription": [],
#            "transfusion": [],
#            "disposition": []
#        },
#        "surgical_therapy": {
#            "method": [
#                {
#                    "methodtherapy_content": [
#                        {
#                            "method_code": "001",
#                            "method_type": "手术治疗",
#                            "method_name": "消化道出血手术",
#                            "method_name_retrieve": "",
#                            "method_plan": "先进行术前准备，包括禁食、消化道术前准备等；然后在手术室进行麻醉和消毒，进行选择性胃肠镜检查以确认出血部位；接着进行创面止血操作，包括结扎、硬化剂注射、断层缝合等，必要时可能需要器械切除出血部位；术后需要在监护病房进行术后观察，包括呼吸、心率、血压的监测，以及术后说话、进食、排尿等功能的恢复情况；根据患者的具体情况，决定是否需要进一步的术后治疗和支持治疗，如术后感染的控制、营养支持、血容量补充等；治疗完成后进行好转观察和伤口愈合情况监测，包括伤口感染的观察、疼痛的评估、伤口缝合技术的评估等；整个治疗周期预计约为1-2周，具体时间由患者的恢复情况而定。",
#                            "method_risk": "手术风险可能包括术中出血、呼吸道并发症、术后感染、术后腹痛、切口愈合不良等，以及可能出现严重并发症，如休克、心衰等。"
#                        },
#                        {
#                            "method_code": "002",
#                            "method_type": "手术治疗",
#                            "method_name": "贫血治疗手术",
#                            "method_name_retrieve": "",
#                            "method_plan": "术中使用输血技术，对贫血进行纠正；进行必要的手术治疗，如通过外科手术切除贫血产生的病理因素，如肿瘤或囊肿等；术后需要进行血管брауз和血容量的监测，保持贫血状况的稳定；根据患者病情和手术情况，进行术后感染的处理和协助伤口愈合等；完成手术后，对患者进行术后的全面康复治疗，包括营养管理、伤口护理、健康指导和进一步的临床观察等。整个治疗周期预计约为2-4周，具体时间由患者的恢复情况而定。",
#                            "method_risk": "手术治疗贫血可能存在的风险包括手术感染、术后呼吸衰竭、术后血栓形成等。"
#                        }
#                    ]
#                }
#            ]
#        },
#        "chemo_therapy": {
#            "method": []
#        },
#        "radiation_therapy": {
#            "method": []
#        },
#        "psycho_therapy": {
#            "method": []
#        },
#        "rehabilitation_therapy": {
#            "method": []
#        },
#        "physical_therapy": {
#            "method": []
#        },
#        "alternative_therapy": {
#            "method": []
#        },
#        "observation_therapy": {
#            "method": []
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成治疗方案：\n\n{\n    \"治疗方案\": [{\n       \"治疗编号\": \"001\",\n       \"治疗类型\": \"手术治疗\",\n       \"治疗名称\": \"消化道出血手术\",\n       \"潜在风险\": \"手术风险可能包括术中出血、呼吸道并发症、术后感染、术后腹痛、切口愈合不良等，以及可能出现严重并发症，如休克、心衰等。\",\n       \"治疗计划\": \"先进行术前准备，包括禁食、消化道术前准备等；然后在手术室进行麻醉和消毒，进行选择性胃肠镜检查以确认出血部位；接着进行创面止血操作，包括结扎、硬化剂注射、断层缝合等，必要时可能需要器械切除出血部位；术后需要在监护病房进行术后观察，包括呼吸、心率、血压的监测，以及术后说话、进食、排尿等功能的恢复情况；根据患者的具体情况，决定是否需要进一步的术后治疗和支持治疗，如术后感染的控制、营养支持、血容量补充等；治疗完成后进行好转观察和伤口愈合情况监测，包括伤口感染的观察、疼痛的评估、伤口缝合技术的评估等；整个治疗周期预计约为1-2周，具体时间由患者的恢复情况而定。\"\n    },\n    {\n       \"治疗编号\": \"002\",\n       \"治疗类型\": \"手术治疗\",\n       \"治疗名称\": \"贫血治疗手术\",\n       \"潜在风险\": \"手术治疗贫血可能存在的风险包括手术感染、术后呼吸衰竭、术后血栓形成等。\",\n       \"治疗计划\": \"术中使用输血技术，对贫血进行纠正；进行必要的手术治疗，如通过外科手术切除贫血产生的病理因素，如肿瘤或囊肿等；术后需要进行血管 брауз和血容量的监测，保持贫血状况的稳定；根据患者病情和手术情况，进行术后感染的处理和协助伤口愈合等；完成手术后，对患者进行术后的全面康复治疗，包括营养管理、伤口护理、健康指导和进一步的临床观察等。整个治疗周期预计约为2-4周，具体时间由患者的恢复情况而定。\"\n    }]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成治疗方案：\n\n{\n    \"治疗方案\": [{\n       \"治疗编号\": \"001\",\n       \"治疗类型\": \"手术治疗\",\n       \"治疗名称\": \"消化道出血手术\",\n       \"潜在风险\": \"手术风险可能包括术中出血、呼吸道并发症、术后感染、术后腹痛、切口愈合不良等，以及可能出现严重并发症，如休克、心衰等。\",\n       \"治疗计划\": \"先进行术前准备，包括禁食、消化道术前准备等；然后在手术室进行麻醉和消毒，进行选择性胃肠镜检查以确认出血部位；接着进行创面止血操作，包括结扎、硬化剂注射、断层缝合等，必要时可能需要器械切除出血部位；术后需要在监护病房进行术后观察，包括呼吸、心率、血压的监测，以及术后说话、进食、排尿等功能的恢复情况；根据患者的具体情况，决定是否需要进一步的术后治疗和支持治疗，如术后感染的控制、营养支持、血容量补充等；治疗完成后进行好转观察和伤口愈合情况监测，包括伤口感染的观察、疼痛的评估、伤口缝合技术的评估等；整个治疗周期预计约为1-2周，具体时间由患者的恢复情况而定。\"\n    },\n    {\n       \"治疗编号\": \"002\",\n       \"治疗类型\": \"手术治疗\",\n       \"治疗名称\": \"贫血治疗手术\",\n       \"潜在风险\": \"手术治疗贫血可能存在的风险包括手术感染、术后呼吸衰竭、术后血栓形成等。\",\n       \"治疗计划\": \"术中使用输血技术，对贫血进行纠正；进行必要的手术治疗，如通过外科手术切除贫血产生的病理因素，如肿瘤或囊肿等；术后需要进行血管 брауз和血容量的监测，保持贫血状况的稳定；根据患者病情和手术情况，进行术后感染的处理和协助伤口愈合等；完成手术后，对患者进行术后的全面康复治疗，包括营养管理、伤口护理、健康指导和进一步的临床观察等。整个治疗周期预计约为2-4周，具体时间由患者的恢复情况而定。\"\n    }]\n}"
#            }
#        ]
#    }
#}





# 测试结果(3.2)-其他方案-康复治疗(&scheme=other_therapy&sub_scheme=rehabilitation_therapy)
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "76",
#                "if_child": "否",
#                "certificate_type": "",
#                "certificate_number": "",
#                "mobile_number": "",
#                "current_address": {
#                    "province": "",
#                    "city": "",
#                    "district": "",
#                    "street": ""
#                },
#                "detailed_address": ""
#            },
#            "guardian": {
#                "guardian_name": "",
#                "certificate_type": "",
#                "certificate_number": ""
#            }
#        }],
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
#        "pick_therapy": [
#            {
#                "picked_therapy": "default_therapy",
#                "interpret_therapy": "针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。"
#            },
#            {
#                "picked_therapy": "surgical_therapy",
#                "interpret_therapy": "如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。"
#            },
#            {
#                "picked_therapy": "rehabilitation_therapy",
#                "interpret_therapy": "康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。"
#            }
#        ],
#        "default_therapy": {
#            "prescription": [],
#            "transfusion": [],
#            "disposition": []
#        },
#        "surgical_therapy": {
#            "method": []
#        },
#        "chemo_therapy": {
#            "method": []
#        },
#        "radiation_therapy": {
#            "method": []
#        },
#        "psycho_therapy": {
#            "method": []
#        },
#        "rehabilitation_therapy": {
#            "method": [
#                {
#                    "methodtherapy_content": [
#                        {
#                            "method_code": "001",
#                            "method_type": "康复治疗",
#                            "method_name": "上消化道出血康复治疗",
#                            "method_name_retrieve": "",
#                            "method_plan": "1.早期以卧床休息为主，用于保持体力，减轻心脏负荷，并使身体逐渐适应因肠道失血而带来的低血压状态；2.晚期/中度症状患者进行腹部按摩缓解腹部不适；3.根据患者的年龄和体力情况，选择性地进行早期躯体康复运动，如轻度的拉筋、气功等以促进胃肠蠕动，改善血液循环；4.合理规划饮食，逐渐增加营养摄入。",
#                            "method_risk": "可能在康复治疗过程中可能出现肌肉疲劳、关节僵硬、心脏负荷增加等风险"
#                        },
#                        {
#                            "method_code": "002",
#                            "method_type": "康复治疗",
#                            "method_name": "贫血康复治疗",
#                            "method_name_retrieve": "",
#                            "method_plan": "1.饮食调理：合理增加富含铁质的食物摄入，保证血红蛋白的生成所需；2.运动康复：在病情稳定情况下，进行适量的有氧运动，如散步、太极等，有助于促进血液循环，提高氧气的吸收率；3.心理支持和健康教育：提供心理支持，帮助患者缓解对疾病的恐惧和焦虑，并教育患者如何预防和应对贫血相关症状。",
#                            "method_risk": "在康复治疗过程中，可能会引发感染、心血管负荷加重等风险"
#                        }
#                    ]
#                }
#            ]
#        },
#        "physical_therapy": {
#            "method": []
#        },
#        "alternative_therapy": {
#            "method": []
#        },
#        "observation_therapy": {
#            "method": []
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成治疗方案：\n\n{\n  \"治疗方案\": [\n    {\n      \"治疗编号\": \"001\",\n      \"治疗类型\": \"康复治疗\",\n      \"治疗名称\": \"上消化道出血康复治疗\",\n      \"潜在风险\": \"可能在康复治疗过程中可能出现肌肉疲劳、关节僵硬、心脏负荷增加等风险\",\n      \"治疗计划\": \"1. 早期以卧床休息为主，用于保持体力，减轻心脏负荷，并使身体逐渐适应因肠道失血而带来的低血压状态；2. 晚期/中度症状患者进行腹部按摩缓解腹部不适；3. 根据患者的年龄和体力情况，选择性地进行早期躯体康复运动，如轻度的拉筋、气功等以促进胃肠蠕动，改善血液循环；4. 合理规划饮食，逐渐增加营养摄入。\"\n    },\n    {\n      \"治疗编号\": \"002\",\n      \"治疗类型\": \"康复治疗\",\n      \"治疗名称\": \"贫血康复治疗\",\n      \"潜在风险\": \"在康复治疗过程中，可能会引发感染、心血管负荷加重等风险\",\n      \"治疗计划\": \"1. 饮食调理：合理增加富含铁质的食物摄入，保证血红蛋白的生成所需；2. 运动康复：在病情稳定情况下，进行适量的有氧运动，如散步、太极等，有助于促进血液循环，提高氧气的吸收率；3. 心理支持和健康教育：提供心理支持，帮助患者缓解对疾病的恐惧和焦虑，并教育患者如何预防和应对贫血相关症状。\"\n    }\n  ]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成方案：\n\n[\n    {\n        \"方案名称\": \"保守治疗\",\n        \"方案解读\": \"针对张三女士的病情，保守治疗是首选方案。这包括休息、饮食调整、药物治疗等。饮食上建议避免刺激性食物，增加富含铁质的食物摄入，以促进血红蛋白的合成。药物治疗方面，可能需要使用止血药物和补铁药物，以控制出血和改善贫血症状。保守治疗通常适用于病情较轻的患者，可以避免手术带来的风险。\"\n    },\n    {\n        \"方案名称\": \"手术治疗\",\n        \"方案解读\": \"如果保守治疗无效或病情严重，可能需要考虑手术治疗。手术可以切除出血的部位，以防止再次出血。手术风险和恢复时间需要与患者及其家属充分沟通，并权衡利弊后决定是否进行。\"\n    },\n    {\n        \"方案名称\": \"康复治疗\",\n        \"方案解读\": \"康复治疗是辅助保守治疗和手术治疗的方案，旨在帮助患者恢复身体功能和生活质量。这可能包括物理治疗、康复训练等，以促进患者的康复。康复治疗通常在病情稳定后进行，有助于患者更快地恢复健康。\"\n    }\n]"
#            },
#            {
#                "role": "assistant",
#                "content": "您已确诊，现在为您生成治疗方案：\n\n{\n  \"治疗方案\": [\n    {\n      \"治疗编号\": \"001\",\n      \"治疗类型\": \"康复治疗\",\n      \"治疗名称\": \"上消化道出血康复治疗\",\n      \"潜在风险\": \"可能在康复治疗过程中可能出现肌肉疲劳、关节僵硬、心脏负荷增加等风险\",\n      \"治疗计划\": \"1. 早期以卧床休息为主，用于保持体力，减轻心脏负荷，并使身体逐渐适应因肠道失血而带来的低血压状态；2. 晚期/中度症状患者进行腹部按摩缓解腹部不适；3. 根据患者的年龄和体力情况，选择性地进行早期躯体康复运动，如轻度的拉筋、气功等以促进胃肠蠕动，改善血液循环；4. 合理规划饮食，逐渐增加营养摄入。\"\n    },\n    {\n      \"治疗编号\": \"002\",\n      \"治疗类型\": \"康复治疗\",\n      \"治疗名称\": \"贫血康复治疗\",\n      \"潜在风险\": \"在康复治疗过程中，可能会引发感染、心血管负荷加重等风险\",\n      \"治疗计划\": \"1. 饮食调理：合理增加富含铁质的食物摄入，保证血红蛋白的生成所需；2. 运动康复：在病情稳定情况下，进行适量的有氧运动，如散步、太极等，有助于促进血液循环，提高氧气的吸收率；3. 心理支持和健康教育：提供心理支持，帮助患者缓解对疾病的恐惧和焦虑，并教育患者如何预防和应对贫血相关症状。\"\n    }\n  ]\n}"
#            }
#        ]
#    }
#}
