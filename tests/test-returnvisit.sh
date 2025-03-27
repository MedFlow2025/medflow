# v7-复诊

#url: http://ip:port/inference?request_type=v7
#输入(input)：
#    client_info（患者基础信息，会用到患者的姓名、性别和年龄，其他的用不到）
#    basic_medical_record（预问诊阶段生成的病历）
#    diagnosis（诊断阶段生成的诊断）
#输出(output)：
#    return_visit(复诊，包括当前病情的问诊总结，以及判断是否需要复诊)
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示，使用时增加一组role为user的回答即可）
#步骤:
#    1.在historical_conversations中增加一组role为user的患者回复；
#    2.发送请求后，会基于患者上次就诊的病历，询问当前的病情恢复情况。多轮对话后，生成病情总结与是否复诊，更新output.return_visit.summary和if_visit；
#测试脚本：
#    bash test-returnvisit.sh

curl -X 'POST' \
  'http://ip:port/inference?request_type=v7' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/returnvisit.json

  echo -e "\n==================================\n"

#测试结果
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
#        "return_visit": {
#            "summary": "患者目前主要症状为胃部不适和乏力，无恶心、呕吐、发热、心悸、气促、水肿等症状。患者一直按照医生开的药在服用，但未测量过血压和心率。",
#            "if_visit": "是"
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！我是您的智能医生助理，想跟您聊一下最近的身体状况，看看是否需要为您安排一次复诊。我看到您上次就诊是因为上消化道出血、贫血，请问在经过治疗后，您现在感觉怎么样？"
#            },
#            {
#                "role": "user",
#                "content": "胃还是有些不舒服"
#            },
#            {
#                "role": "assistant",
#                "content": "了解到您现在胃部还是有些不舒服。请问您最近有没有出现其他症状，比如腹痛、恶心、呕吐、发热等？同时，您现在的饮食和排便情况如何？这些信息对于我们判断是否需要复诊很重要。"
#            },
#            {
#                "role": "user",
#                "content": "有些恶心，吃的很清淡，排便正常"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，您目前有恶心感，但饮食清淡且排便正常。请问您最近有没有出现头晕、乏力、心悸等症状？另外，您最近有没有服用任何药物，或者有其他不适的感觉？这些信息将帮助我更好地了解您的病情。"
#            },
#            {
#                "role": "user",
#                "content": "有些乏力，没劲，一直吃着医生开的药"
#            },
#            {
#                "role": "assistant",
#                "content": "了解到您最近有些乏力，但一直按照医生开的药在服用。请问您最近有没有出现心悸、气促、水肿等症状？同时，您现在的血压和心率是否正常？这些信息对于我们判断是否需要复诊非常重要。"
#            },
#            {
#                "role": "user",
#                "content": "没有这些症状，没有测量血压和心率"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，您目前没有心悸、气促、水肿等症状，也没有测量过血压和心率。根据您提供的信息，您目前的主要症状是胃部不适和乏力。考虑到您之前有上消化道出血和贫血的病史，这些症状可能与您的病情有关。\n\n现在为您生成病情总结如下：\n{\n    \"病情总结\": \"患者目前主要症状为胃部不适和乏力，无恶心、呕吐、发热、心悸、气促、水肿等症状。患者一直按照医生开的药在服用，但未测量过血压和心率。\",\n    \"是否复诊\": \"是\"\n}"
#            },
#            {
#                "role": "user",
#                "content": "为啥要复诊啊"
#            },
#            {
#                "role": "assistant",
#                "content": "复诊的原因是因为您目前有胃部不适和乏力等症状，这些症状可能与您之前的上消化道出血和贫血有关。虽然您目前没有其他严重症状，但为了确保您的健康，我们需要进一步评估您的病情。复诊可以帮助医生了解您目前的身体状况，确认是否需要调整治疗方案，或者进行进一步的检查，以确保您的病情得到妥善管理。您的安全和健康是我们最关心的。"
#            },
#            {
#                "role": "user",
#                "content": "好的，谢谢"
#            },
#            {
#                "role": "assistant",
#                "content": "不客气，张三。如果您有任何其他问题或需要帮助，随时可以联系我。祝您早日康复！"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！我是您的智能医生助理，想跟您聊一下最近的身体状况，看看是否需要为您安排一次复诊。我看到您上次就诊是因为上消化道出血、贫血，请问在经过治疗后，您现在感觉怎么样？"
#            },
#            {
#                "role": "user",
#                "content": "胃还是有些不舒服"
#            },
#            {
#                "role": "assistant",
#                "content": "了解到您现在胃部还是有些不舒服。请问您最近有没有出现其他症状，比如腹痛、恶心、呕吐、发热等？同时，您现在的饮食和排便情况如何？这些信息对于我们判断是否需要复诊很重要。"
#            },
#            {
#                "role": "user",
#                "content": "有些恶心，吃的很清淡，排便正常"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，您目前有恶心感，但饮食清淡且排便正常。请问您最近有没有出现头晕、乏力、心悸等症状？另外，您最近有没有服用任何药物，或者有其他不适的感觉？这些信息将帮助我更好地了解您的病情。"
#            },
#            {
#                "role": "user",
#                "content": "有些乏力，没劲，一直吃着医生开的药"
#            },
#            {
#                "role": "assistant",
#                "content": "了解到您最近有些乏力，但一直按照医生开的药在服用。请问您最近有没有出现心悸、气促、水肿等症状？同时，您现在的血压和心率是否正常？这些信息对于我们判断是否需要复诊非常重要。"
#            },
#            {
#                "role": "user",
#                "content": "没有这些症状，没有测量血压和心率"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，您目前没有心悸、气促、水肿等症状，也没有测量过血压和心率。根据您提供的信息，您目前的主要症状是胃部不适和乏力。考虑到您之前有上消化道出血和贫血的病史，这些症状可能与您的病情有关。现在为您生成病情总结如下：\n病情总结: 患者目前主要症状为胃部不适和乏力，无恶心、呕吐、发热、心悸、气促、水肿等症状。患者一直按照医生开的药在服用，但未测量过血压和心率。\n是否复诊：是"
#            },
#            {
#                "role": "user",
#                "content": "为啥要复诊啊"
#            },
#            {
#                "role": "assistant",
#                "content": "复诊的原因是因为您目前有胃部不适和乏力等症状，这些症状可能与您之前的上消化道出血和贫血有关。虽然您目前没有其他严重症状，但为了确保您的健康，我们需要进一步评估您的病情。复诊可以帮助医生了解您目前的身体状况，确认是否需要调整治疗方案，或者进行进一步的检查，以确保您的病情得到妥善管理。您的安全和健康是我们最关心的。"
#            },
#            {
#                "role": "user",
#                "content": "好的，谢谢"
#            },
#            {
#                "role": "assistant",
#                "content": "不客气，张三。如果您有任何其他问题或需要帮助，随时可以联系我。祝您早日康复！"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}
