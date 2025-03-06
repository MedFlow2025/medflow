curl -X 'POST' \
  'http://ip:port/quality_modify' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '
{
    "input": {
        "basic_medical_record": {
            "chief_complaint": "神志模糊、呕吐1小时",
            "history_of_present_illness": "1小时前饮酒后出现神志模糊，伴呕吐非咖啡色胃内容数次，无肢体抽搐，无呼吸困难，无胸闷、胸痛",
            "past_medical_history": "既往高血压病史1个月，规律服药治疗",
            "personal_history": "否认吸烟、有饮酒史",
            "allergy_history": "否认药物和食物过敏史",
            "physical_examination": {
                "temperature": "36.7",
                "pulse": "84次/分",
                "blood_pressure": "197/73mmHg",
                "respiration": "20次"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温的数值后是否带有单位“℃”",
                "field": "体格检查;",
                "item": "体温",
                "standard": "℃",
                "check_quality": "体温数值后缺少单位“℃”",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃",             
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            }
        ]
    }
}
'
echo -e "\n\n"

curl -X 'POST' \
  'http://ip:port/quality_modify' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '
{
    "input": {
        "basic_medical_record": {
            "chief_complaint": "神志模糊、呕吐1小时",
            "history_of_present_illness": "1小时前饮酒后出现神志模糊，伴呕吐非咖啡色胃内容数次，无肢体抽搐，无呼吸困难，无胸闷、胸痛",
            "past_medical_history": "既往高血压病史1个月，规律服药治疗",
            "personal_history": "否认吸烟、有饮酒史",
            "allergy_history": "否认药物和食物过敏史",
            "physical_examination": {
                "temperature": "36.7",
                "pulse": "84次/分",
                "blood_pressure": "197/73mmHg",
                "respiration": "20次"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温的数值后是否带有单位“℃”",
                "field": "体格检查;",
                "item": "体温",
                "standard": "℃",
                "check_quality": "体温数值后缺少单位“℃”",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃",             
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            }
        ]    
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问是否需要补充体温的单位？"
            },
            {
                "role": "user",
                "content": "请补充体温单位"
            }
        ]
    }
}
'
echo -e "\n\n"

#测试结果
# {
#     "output": {
#         "basic_medical_record": {
#             "chief_complaint": "神志模糊、呕吐1小时",
#             "history_of_present_illness": "1小时前饮酒后出现神志模糊，伴呕吐非咖啡色胃内容数次，无肢体抽搐，无呼吸困难，无胸闷、胸痛",
#             "past_medical_history": "既往高血压病史1个月，规律服药治疗",
#             "personal_history": "否认吸烟、有饮酒史",
#             "allergy_history": "否认药物和食物过敏史",
#             "physical_examination": {
#                 "temperature": "36.7",
#                 "pulse": "84次/分",
#                 "blood_pressure": "197/73mmHg",
#                 "respiration": "20次"
#             },
#             "auxiliary_examination": ""
#         },
#         "control_quality": [
#             {
#                 "content": "体温的数值后是否带有单位“℃”",
#                 "field": "体格检查;",
#                 "item": "体温",
#                 "standard": "℃",
#                 "check_quality": "体温数值后缺少单位“℃”",
#                 "auto_modify_type": true,
#                 "auto_modify_info": "36.7℃",
#                 "positive_example": "36.8℃",
#                 "negative_example": "36.1"
#             }
#         ]
#     },
#     "chat": {
#         "historical_conversations": [
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：体格检查 体温 体温数值后缺少单位“℃”，请问医生是否需要补充体温的单位？"
#             }
#         ]
#     }
# }