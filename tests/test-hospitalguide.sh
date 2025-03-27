# v8-导诊

#url: 
#    导诊简单版：http://ip:port/inference?request_type=v8&scheme=simple
#    导诊详细版：http://ip:port/inference?request_type=v8&scheme=detailed
#输入(input)：
#    client_info（患者基础信息，会用到患者的姓名、性别和年龄，其他的用不到）
#    all_department（用于输入所有科室信息，包含科室层级编码与科室名称）
#输出(output)：
#    basic_medical_record（用于输出病历）
#    chosen_department（用于输出推荐科室）
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示，使用时增加一组role为user的回答即可）
#步骤:
#    1.在historical_conversations中增加一组role为user的患者回复；
#    2.发送请求(scheme=simple)，在与患者进行多轮对话后，生成“主诉”和“推荐科室”，更新output.basic_medical_record.chief_complaint和output.chosen_department；
#    2.发送请求(scheme=detailed)，在与患者进行多轮对话后，生成“预问诊报告”，更新output.basic_medical_record；
#测试脚本：
#    bash test-hospitalguide.sh

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

#测试结果1-导诊简单版
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "男",
#                    "patient_age": "44",
#                    "if_child": "",
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
#        "all_department": [...]
#    },
#    "output": {
#        "basic_medical_record": {
#            "chief_complaint": "发烧、咳嗽一天",
#            "history_of_present_illness": "",
#            "past_medical_history": "",
#            "personal_history": "",
#            "allergy_history": "",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        },
#        "chosen_department": [
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            },
#            {
#                "department_id": "1f0f55bc398046ae05d0.101811.",
#                "department_name": "成人发热门诊"
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！欢迎您来我院就诊，期望我们可以帮助到您。我将为您推荐最合适的科室，请问您有什么症状？"
#            },
#            {
#                "role": "user",
#                "content": "发烧了"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您的发烧持续了多久？"
#            },
#            {
#                "role": "user",
#                "content": "一天了"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您还有其他症状吗？例如咳嗽、喉咙痛、流鼻涕等？"
#            },
#            {
#                "role": "user",
#                "content": "有些咳嗽"
#            },
#            {
#                "role": "assistant",
#                "content": "为您推荐以下科室：{\n\"病历\": {\n    \"主诉\": \"发烧、咳嗽一天\"\n    },\n\"推荐科室\": [\n    {\n        \"科室编号\": \"001\",\n        \"科室名称\": \"呼吸内科门诊\"\n    },\n    {\n        \"科室编号\": \"002\",\n        \"科室名称\": \"成人发热门诊\"\n    }]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！欢迎您来我院就诊，期望我们可以帮助到您。我将为您推荐最合适的科室，请问您有什么症状？"
#            },
#            {
#                "role": "user",
#                "content": "发烧了"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您的发烧持续了多久？"
#            },
#            {
#                "role": "user",
#                "content": "一天了"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您还有其他症状吗？例如咳嗽、喉咙痛、流鼻涕等？"
#            },
#            {
#                "role": "user",
#                "content": "有些咳嗽"
#            },
#            {
#                "role": "assistant",
#                "content": "患者病情：\n【主诉】: 发烧、咳嗽一天\n\n推荐科室：\n【呼吸内科门诊】\n【成人发热门诊】"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": ""
#    }
#}


#测试结果2-导诊详细版
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "男",
#                    "patient_age": "44",
#                    "if_child": "",
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
#        "all_department": null
#    },
#    "output": {
#        "basic_medical_record": {
#            "chief_complaint": "发烧一天，嗓子疼",
#            "history_of_present_illness": "患者于1天前出现发热，最高体温39.8℃，伴有嗓子疼，咽唾沫和吃饭时疼痛明显，有咳嗽，无痰，有乏力，食欲不振，否认尿频、尿急、尿痛、尿血、尿量减少等症状。",
#            "past_medical_history": "否认高血压、糖尿病、心脏病等慢性病史；否认手术、外伤、输血等既往病史。",
#            "personal_history": "吸烟10年，每天2-3支；偶尔饮酒。",
#            "allergy_history": "对柳絮过敏，打喷嚏；否认其他药物或食物过敏。",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        },
#        "chosen_department": [
#            {
#                "department_id": "1f0f55bc398046ae05d0.101811.",
#                "department_name": "成人发热门诊"
#            },
#            {
#                "department_id": "5ae37e47016d46aa2073.101211.",
#                "department_name": "呼吸内科门诊"
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！我是您的智能医生助理，想跟您详细了解一下病情，为您生成预问诊报告。我看到您的主要症状有“发烧一天，嗓子疼”，您还有其他不适吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，了解了。您发烧的最高体温是多少？"
#            },
#            {
#                "role": "user",
#                "content": "39度8"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您嗓子疼的具体感觉是怎样的？"
#            },
#            {
#                "role": "user",
#                "content": "咽唾沫和吃饭的时候很痛"
#            },
#            {
#                "role": "assistant",
#                "content": "清楚了。您有咳嗽、咳痰、胸闷、胸痛、呼吸困难等症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "有咳嗽，没有痰"
#            },
#            {
#                "role": "assistant",
#                "content": "了解了。您有头痛、肌肉酸痛、关节痛、乏力、食欲不振等症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "有些乏力，不想吃饭"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。您有尿频、尿急、尿痛、尿血、尿量减少等症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您有高血压、糖尿病、心脏病等慢性病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有，我有宫颈炎"
#            },
#            {
#                "role": "assistant",
#                "content": "宫颈炎是女性的病症，您是男性，我们不讨论这个话题。您有其他慢性病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。您有手术、外伤、输血等既往病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "了解了。您有吸烟史吗？"
#            },
#            {
#                "role": "user",
#                "content": "有"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您每天吸烟多少支，吸烟多久了？"
#            },
#            {
#                "role": "user",
#                "content": "每天也就2，3支，10年了"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。您有饮酒史吗？"
#            },
#            {
#                "role": "user",
#                "content": "偶尔喝"
#            },
#            {
#                "role": "assistant",
#                "content": "了解了。您对什么药物、食物或环境因素过敏吗？"
#            },
#            {
#                "role": "user",
#                "content": "柳絮过敏，打喷嚏"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您对其他药物或食物过敏吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。{\n    \"主诉\": \"发烧一天，嗓子疼\",\n    \"现病史\": \"患者于1天前出现发热，最高体温39.8℃，伴有嗓子疼，咽唾沫和吃饭时疼痛明显，有咳嗽，无痰，有乏力，食欲不振，否认尿频、尿急、尿痛、尿血、尿量减少等症状。\",\n    \"既往史\": \"否认高血压、糖尿病、心脏病等慢性病史；否认手术、外伤、输血等既往病史。\",\n    \"个人史\": \"吸烟10年，每天2-3支；偶尔饮酒。\",\n    \"过敏史\": \"对柳絮过敏，打喷嚏；否认其他药物或食物过敏。\"\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！我是您的智能医生助理，想跟您详细了解一下病情，为您生成预问诊报告。我看到您的主要症状有“发烧一天，嗓子疼”，您还有其他不适吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，了解了。您发烧的最高体温是多少？"
#            },
#            {
#                "role": "user",
#                "content": "39度8"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您嗓子疼的具体感觉是怎样的？"
#            },
#            {
#                "role": "user",
#                "content": "咽唾沫和吃饭的时候很痛"
#            },
#            {
#                "role": "assistant",
#                "content": "清楚了。您有咳嗽、咳痰、胸闷、胸痛、呼吸困难等症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "有咳嗽，没有痰"
#            },
#            {
#                "role": "assistant",
#                "content": "了解了。您有头痛、肌肉酸痛、关节痛、乏力、食欲不振等症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "有些乏力，不想吃饭"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。您有尿频、尿急、尿痛、尿血、尿量减少等症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您有高血压、糖尿病、心脏病等慢性病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有，我有宫颈炎"
#            },
#            {
#                "role": "assistant",
#                "content": "宫颈炎是女性的病症，您是男性，我们不讨论这个话题。您有其他慢性病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。您有手术、外伤、输血等既往病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "了解了。您有吸烟史吗？"
#            },
#            {
#                "role": "user",
#                "content": "有"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您每天吸烟多少支，吸烟多久了？"
#            },
#            {
#                "role": "user",
#                "content": "每天也就2，3支，10年了"
#            },
#            {
#                "role": "assistant",
#                "content": "好的。您有饮酒史吗？"
#            },
#            {
#                "role": "user",
#                "content": "偶尔喝"
#            },
#            {
#                "role": "assistant",
#                "content": "了解了。您对什么药物、食物或环境因素过敏吗？"
#            },
#            {
#                "role": "user",
#                "content": "柳絮过敏，打喷嚏"
#            },
#            {
#                "role": "assistant",
#                "content": "明白了。您对其他药物或食物过敏吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n主诉: 发烧一天，嗓子疼\n现病史: 患者于1天前出现发热，最高体温39.8℃，伴有嗓子疼，咽唾沫和吃饭时疼痛明显，有咳嗽，无痰，有乏力，食欲不振，否认尿频、尿急、尿痛、尿血、尿量减少等症状。\n既往史: 否认高血压、糖尿病、心脏病等慢性病史；否认手术、外伤、输血等既往病史。\n个人史: 吸烟10年，每天2-3支；偶尔饮酒。\n过敏史: 对柳絮过敏，打喷嚏；否认其他药物或食物过敏。\n"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": ""
#    }
#}
