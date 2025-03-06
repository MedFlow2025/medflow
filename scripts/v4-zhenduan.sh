# v4-生成诊断

#url: http://ip:port/inference?request_type=v4
#输入(input)：
#    client_info（患者基础信息，会用到患者的姓名、性别和年龄，其他的用不到）
#    basic_medical_record（预问诊阶段生成的病历）
#输出(output)：
#    diagnosis（根据病历生成的诊断）
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示）
#测试脚本：
#    bash v4-zhenduan.sh
curl -X 'POST' \
  'http://ip:port/inference?request_type=v4' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '
{
    "input": {
        "client_info": [{
            "patient": {
                "patient_name": "张三",
                "patient_gender": "女",
                "patient_age": "16",
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
            "chief_complaint": "咳嗽、喉咙痛3天，严重，影响睡眠和饮食。",
            "history_of_present_illness": "咳嗽3天，后出现喉咙痛，严重，影响睡眠和饮食。",
            "past_medical_history": "否认高血压，否认糖尿病，否认心脏病，否认肝病，否认肾病，否认骨折，否认手术，否认外伤。",
            "personal_history": "否认吸烟;饮酒，一周2次，每次半斤。",
            "allergy_history": "牛奶",
            "physical_examination": "",
            "auxiliary_examination": ""
        }
    },
    "output": {
        "diagnosis": [
            {
                "diagnosis_name": "",
                "diagnosis_name_retrieve": "",
                "diagnosis_code": "",
                "diagnosis_identifier": ""
            }
        ]
    },
    "chat": {
        "historical_conversations_bak": [],
        "historical_conversations": [],
        "prompt_version": "v1",
        "model_name": "model_medical_20250122"
    }
}
'




# 测试结果
#{
#    "input": {
#        "client_info": [{
#            "patient": {
#                "patient_name": "张三",
#                "patient_gender": "女",
#                "patient_age": "16",
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
#            "chief_complaint": "咳嗽、喉咙痛3天，严重，影响睡眠和饮食。",
#            "history_of_present_illness": "咳嗽3天，后出现喉咙痛，严重，影响睡眠和饮食。",
#            "past_medical_history": "否认高血压，否认糖尿病，否认心脏病，否认肝病，否认肾病，否认骨折，否认手术，否认外伤。",
#            "personal_history": "否认吸烟;饮酒，一周2次，每次半斤。",
#            "allergy_history": "牛奶",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        }
#    },
#    "output": {
#        "diagnosis": [
#            {
#                "diagnosis_name": "急性上呼吸道感染",
#                "diagnosis_name_retrieve": "急性上呼吸道感染",
#                "diagnosis_code": "J06.900",
#                "diagnosis_identifier": "疑似"
#            },
#            {
#                "diagnosis_name": "咽喉炎",
#                "diagnosis_name_retrieve": "急性咽喉炎",
#                "diagnosis_code": "J06.000",
#                "diagnosis_identifier": "疑似"
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "根据您的预问诊报告，我为您进行初步诊断如下。请合理安排就医，祝您早日康复。\n\n{\n\"诊断\": [{\n       \"诊断名称\": \"急性上呼吸道感染\",\n       \"诊断编码\": \"J06.900\",\n       \"诊断标识\": \"疑似\"\n    },\n    {\n       \"诊断名称\": \"咽喉炎\",\n       \"诊断编码\": \"J09.900\",\n       \"诊断标识\": \"疑似\"\n    }]\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "根据您的预问诊报告，我为您进行初步诊断如下。请合理安排就医，祝您早日康复。\n【急性上呼吸道感染  疑似】\n【咽喉炎  疑似】"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}