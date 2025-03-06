curl -X 'POST' \
  'http://ip:port/quality_inspect' \
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality_config_name": "quality_1"
    }
}
'

#测试结果
# quality_1.json 不存在时
# {"detail":"config_name quality_1 not found"}
# quality_1.json 存在时
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
#                 "pulse": "",
#                 "blood_pressure": "99/73",
#                 "respiration": "200次/分"
#             },
#             "auxiliary_examination": ""
#         },
#         "control_quality": [
#             {
#                 "content": "体温单位",
#                 "field": "体格检查;",
#                 "item": "体温",
#                 "standard": "数值后必须带℃",
#                 "check_quality": "不通过    数值后缺少单位℃",
#                 "auto_modify_type": true,
#                 "auto_modify_info": "36.7℃。",
#                 "positive_example": "36.8℃",
#                 "negative_example": "36.1"
#             },
#             {
#                 "content": "脉搏单位",
#                 "field": "体格检查;",
#                 "item": "脉搏",
#                 "standard": "数值后必须带次/分",
#                 "check_quality": "不通过    缺少数值和单位",
#                 "auto_modify_type": true,
#                 "auto_modify_info": "0次/分",
#                 "positive_example": "20 次/分",
#                 "negative_example": "20, 20次, 20分"
#             },
#             {
#                 "content": "血压单位",
#                 "field": "体格检查;",
#                 "item": "血压",
#                 "standard": "数值后必须带mmHg",
#                 "check_quality": "不通过    数值后缺少单位mmHg",
#                 "auto_modify_type": true,
#                 "auto_modify_info": "99/73mmHg",
#                 "positive_example": "120/80mmHg",
#                 "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
#             },
#             {
#                 "content": "体格检查内容是否为空",
#                 "field": "体格检查;",
#                 "item": "",
#                 "standard": "只要有内容且不为空就可以",
#                 "check_quality": "不通过    脉搏的检查结果为空",
#                 "auto_modify_type": false,
#                 "auto_modify_info": "",
#                 "positive_example": "",
#                 "negative_example": ""
#             },
#             {
#                 "content": "辅助检查内容是否为空",
#                 "field": "辅助检查;",
#                 "item": "",
#                 "standard": "只要有内容且不为空就可以",
#                 "check_quality": "不通过    辅助检查内容为空",
#                 "auto_modify_type": false,
#                 "auto_modify_info": "",
#                 "positive_example": "",
#                 "negative_example": ""
#             },
#             {
#                 "content": "脉搏的数值是否符合标准",
#                 "field": "体格检查;",
#                 "item": "脉搏",
#                 "standard": "60~160 次/分，包含边界值",
#                 "check_quality": "不通过    未提供脉搏数值",
#                 "auto_modify_type": false,
#                 "auto_modify_info": "",
#                 "positive_example": "60,160",
#                 "negative_example": "59,161"
#             },
#             {
#                 "content": "呼吸的数值是否符合标准",
#                 "field": "体格检查;",
#                 "item": "呼吸",
#                 "standard": "12~45 次/分，包含边界值",
#                 "check_quality": "不通过    数值不在12~45次/分的范围内",
#                 "auto_modify_type": false,
#                 "auto_modify_info": "",
#                 "positive_example": "12,45",
#                 "negative_example": "11,46"
#             }
#         ]
#     }
# }