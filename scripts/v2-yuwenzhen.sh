# v2-对话生成预问诊

#url: http://ip:port/inference?request_type=v2
#输入(input)：
#    client_info（患者基础信息，会用到患者的姓名、性别和年龄，其他的用不到）
#输出(output)：
#    basic_medical_record（病历分四阶段生成，在返回提示“xxx，如果没有问题，请点击确认，如果有问题请直接告诉我哪里不正确。”时，表示四个阶段的问题都已经问完，可以获取该字段的全部内容。
#    后续可以继续回复要修改的内容，让模型修改病历信息，直至患者点击确认按钮。）
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示，使用时增加一组role为user的回答即可）
#测试脚本：
#    bash v2-yuwenzhen.sh
curl -X 'POST' \
  'http://ip:port/inference?request_type=v2' \
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
        }]
    },
    "output": {
        "basic_medical_record": {
            "chief_complaint": "",
            "history_of_present_illness": "",
            "past_medical_history": "",
            "personal_history": "",
            "allergy_history": "",
            "physical_examination": "",
            "auxiliary_examination": ""
        }
    },
    "chat": {
        "historical_conversations_bak": [
            {
                "role": "assistant",
                "content": "您好，张三！您的就诊档案已经建立成功，欢迎您来我院就诊，期望我们可以帮助到您。请问您有什么症状？"
            },
            {
                "role": "user",
                "content": "咳嗽"
            },
            {
                "role": "assistant",
                "content": "咳嗽持续了多久？"
            }
        ],
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "您好，张三！您的就诊档案已经建立成功，欢迎您来我院就诊，期望我们可以帮助到您。请问您有什么症状？"
            },
            {
                "role": "user",
                "content": "咳嗽"
            },
            {
                "role": "assistant",
                "content": "咳嗽持续了多久？"
            },
            {
                "role": "user",
                "content": "一个星期"
            }
        ],
        "prompt_version": "v2",
        "model_name": "model_medical_20250122"
    }
}
'

#测试结果-预问诊
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
#        }]
#    },
#    "output": {
#        "basic_medical_record": {
#            "chief_complaint": "咳嗽一周伴头痛、嗓子疼。",
#            "history_of_present_illness": "患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。",
#            "past_medical_history": "否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。",
#            "personal_history": "吸烟史：否认；饮酒史：一周一次，一次半斤；",
#            "allergy_history": "药物过敏：否认；食物过敏：牛奶",
#            "physical_examination": "",
#            "auxiliary_examination": ""
#        }
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！您的就诊档案已经建立成功，欢迎您来我院就诊，期望我们可以帮助到您。请问您有什么症状？"
#            },
#            {
#                "role": "user",
#                "content": "咳嗽"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽持续了多久？"
#            },
#            {
#                "role": "user",
#                "content": "一个星期"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽是干咳还是有痰？"
#            },
#            {
#                "role": "user",
#                "content": "干咳"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽时有没有伴随其他症状，比如发热、头痛或喉咙痛？"
#            },
#            {
#                "role": "user",
#                "content": "有些头痛，嗓子也疼"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽时有没有出现胸痛或呼吸困难的情况？"
#            },
#            {
#                "role": "user",
#                "content": "没有出现"
#            },
#            {
#                "role": "assistant",
#                "content": "除了咳嗽、头痛和嗓子疼，还有其他不适的症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有了"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，根据您提供的信息，我已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n\n{\n    \"姓名\": \"张三\",\n    \"性别\": \"女\",\n    \"年龄\": \"16\",\n    \"主诉\": \"咳嗽一周伴头痛、嗓子疼\",\n    \"现病史\": \"患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\"\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您以前有高血压、糖尿病等病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您以前有冠心病、脑梗塞等病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您以前有骨折、手术史等病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "左腿有过骨折"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n\n{\n    \"主诉\": \"咳嗽一周伴头痛、嗓子疼\",\n    \"现病史\": \"患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\",\n    \"既往史\": \"否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折\"\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有吸烟吗？"
#            },
#            {
#                "role": "user",
#                "content": "不吸烟"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有饮酒史吗？"
#            },
#            {
#                "role": "user",
#                "content": "有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您饮酒的频率和量是多少？"
#            },
#            {
#                "role": "user",
#                "content": "一周喝一次，一次半斤"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n\n{\n    \"主诉\": \"咳嗽一周伴头痛、嗓子疼\",\n    \"现病史\": \"患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\",\n    \"既往史\": \"否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折\",\n    \"个人史\": \"吸烟史：否认；饮酒史：一周一次，一次半斤\"\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有药物过敏史吗？例如：青霉素，头孢等。"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有食物过敏史吗？例如：鸡蛋，花生等。"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n\n{\n    \"主诉\": \"咳嗽一周伴头痛、嗓子疼\",\n    \"现病史\": \"患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\",\n    \"既往史\": \"否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折\",\n    \"个人史\": \"吸烟史：否认；饮酒史：一周一次，一次半斤\",\n    \"过敏史\": \"否认药物过敏；否认食物过敏\"\n}"
#            },
#            {
#                "role": "user",
#                "content": "我对牛奶过敏"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n\n{\n    \"主诉\": \"咳嗽一周伴头痛、嗓子疼。\",\n    \"现病史\": \"患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\",\n    \"既往史\": \"否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。\",\n    \"个人史\": \"吸烟史：否认；饮酒史：一周一次，一次半斤；\",\n    \"过敏史\": \"药物过敏：否认；食物过敏：牛奶\"\n}"
#            },
#            {
#                "role": "user",
#                "content": "现在都对了"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，谢谢！祝您早日康复！"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，张三！您的就诊档案已经建立成功，欢迎您来我院就诊，期望我们可以帮助到您。请问您有什么症状？"
#            },
#            {
#                "role": "user",
#                "content": "咳嗽"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽持续了多久？"
#            },
#            {
#                "role": "user",
#                "content": "一个星期"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽是干咳还是有痰？"
#            },
#            {
#                "role": "user",
#                "content": "干咳"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽时有没有伴随其他症状，比如发热、头痛或喉咙痛？"
#            },
#            {
#                "role": "user",
#                "content": "有些头痛，嗓子也疼"
#            },
#            {
#                "role": "assistant",
#                "content": "咳嗽时有没有出现胸痛或呼吸困难的情况？"
#            },
#            {
#                "role": "user",
#                "content": "没有出现"
#            },
#            {
#                "role": "assistant",
#                "content": "除了咳嗽、头痛和嗓子疼，还有其他不适的症状吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有了"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您以前有高血压、糖尿病等病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您以前有冠心病、脑梗塞等病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您以前有骨折、手术史等病史吗？"
#            },
#            {
#                "role": "user",
#                "content": "左腿有过骨折"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有吸烟吗？"
#            },
#            {
#                "role": "user",
#                "content": "不吸烟"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有饮酒史吗？"
#            },
#            {
#                "role": "user",
#                "content": "有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您饮酒的频率和量是多少？"
#            },
#            {
#                "role": "user",
#                "content": "一周喝一次，一次半斤"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有药物过敏史吗？例如：青霉素，头孢等。"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "请问您有食物过敏史吗？例如：鸡蛋，花生等。"
#            },
#            {
#                "role": "user",
#                "content": "没有"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n主诉: 咳嗽一周伴头痛、嗓子疼\n现病史: 患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\n既往史: 否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折\n个人史: 吸烟史：否认；饮酒史：一周一次，一次半斤\n过敏史: 否认药物过敏；否认食物过敏\n"
#            },
#            {
#                "role": "user",
#                "content": "我对牛奶过敏"
#            },
#            {
#                "role": "assistant",
#                "content": "依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。\n主诉: 咳嗽一周伴头痛、嗓子疼。\n现病史: 患者出现干咳，持续一周，伴有头痛和嗓子疼，无胸痛和呼吸困难。\n既往史: 否认高血压，否认糖尿病，否认冠心病，否认脑梗塞，左腿骨折。\n个人史: 吸烟史：否认；饮酒史：一周一次，一次半斤；\n过敏史: 药物过敏：否认；食物过敏：牛奶\n"
#            },
#            {
#                "role": "user",
#                "content": "现在都对了"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，谢谢！祝您早日康复！"
#            }
#        ],
#        "prompt_version": "v2",
#        "model_name": "model_medical_20250122"
#    }
#}