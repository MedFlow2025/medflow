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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    }
}
'

echo -e "\n\n"

# 根据问题不断交互
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "脉搏是70次/分"
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "脉搏是70次/分"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：血压数值后缺少单位“mmHg”，请问血压的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "血压是197/73mmHg"
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "脉搏是70次/分"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：血压数值后缺少单位“mmHg”，请问血压的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "血压是197/73mmHg"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏的检查结果为空，请问脉搏的检查结果是否正常？如果不正常，请提供具体的数值。"
            },
            {
                "role": "user",
                "content": "上面的回复中已经提供了。"
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "脉搏是70次/分"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：血压数值后缺少单位“mmHg”，请问血压的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "血压是197/73mmHg"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏的检查结果为空，请问脉搏的检查结果是否正常？如果不正常，请提供具体的数值。"
            },
            {
                "role": "user",
                "content": "上面的回复中已经提供了。"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：辅助检查内容为空，请问是否需要进行辅助检查？如果需要，请提供具体的检查项目。"
            },
            {
                "role": "user",
                "content": "血常规检查"
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "脉搏是70次/分"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：血压数值后缺少单位“mmHg”，请问血压的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "血压是197/73mmHg"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏的检查结果为空，请问脉搏的检查结果是否正常？如果不正常，请提供具体的数值。"
            },
            {
                "role": "user",
                "content": "上面的回复中已经提供了。"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：辅助检查内容为空，请问是否需要进行辅助检查？如果需要，请提供具体的检查项目。"
            },
            {
                "role": "user",
                "content": "血常规检查"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏未提供脉搏数值，请问脉搏的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "上面的回复中已经提供了。"
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
                "pulse": "",
                "blood_pressure": "99/73",
                "respiration": "200次/分"
            },
            "auxiliary_examination": ""
        },
        "control_quality": [
            {
                "content": "体温单位",
                "field": "体格检查;",
                "item": "体温",
                "standard": "数值后必须带℃",
                "check_quality": "不通过    数值后缺少单位℃",
                "auto_modify_type": true,
                "auto_modify_info": "36.7℃。",
                "positive_example": "36.8℃",
                "negative_example": "36.1"
            },
            {
                "content": "脉搏单位",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "数值后必须带次/分",
                "check_quality": "不通过    缺少数值和单位",
                "auto_modify_type": true,
                "auto_modify_info": "0次/分",
                "positive_example": "20 次/分",
                "negative_example": "20, 20次, 20分"
            },
            {
                "content": "血压单位",
                "field": "体格检查;",
                "item": "血压",
                "standard": "数值后必须带mmHg",
                "check_quality": "不通过    数值后缺少单位mmHg",
                "auto_modify_type": true,
                "auto_modify_info": "99/73mmHg",
                "positive_example": "120/80mmHg",
                "negative_example": "120/80, 120/80m, 120/80mm, 120/80mmH"
            },
            {
                "content": "体格检查内容是否为空",
                "field": "体格检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    脉搏的检查结果为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "辅助检查内容是否为空",
                "field": "辅助检查;",
                "item": "",
                "standard": "只要有内容且不为空就可以",
                "check_quality": "不通过    辅助检查内容为空",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "",
                "negative_example": ""
            },
            {
                "content": "脉搏的数值是否符合标准",
                "field": "体格检查;",
                "item": "脉搏",
                "standard": "60~160 次/分，包含边界值",
                "check_quality": "不通过    未提供脉搏数值",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "60,160",
                "negative_example": "59,161"
            },
            {
                "content": "呼吸的数值是否符合标准",
                "field": "体格检查;",
                "item": "呼吸",
                "standard": "12~45 次/分，包含边界值",
                "check_quality": "不通过    数值不在12~45次/分的范围内",
                "auto_modify_type": false,
                "auto_modify_info": "",
                "positive_example": "12,45",
                "negative_example": "11,46"
            }
        ]
    },
    "chat": {
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "36.7℃"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "脉搏是70次/分"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：血压数值后缺少单位“mmHg”，请问血压的具体数值和单位是多少？"
            },
            {
                "role": "user",
                "content": "血压是197/73mmHg"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏的检查结果为空，请问脉搏的检查结果是否正常？如果不正常，请提供具体的数值。"
            },
            {
                "role": "user",
                "content": "上面的回复中已经提供了。"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：辅助检查内容为空，请问是否需要进行辅助检查？如果需要，请提供具体的检查项目。"
            },
            {
                "role": "user",
                "content": "血常规检查"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：脉搏未提供脉搏数值，请问脉搏的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "上面的回复中已经提供了。"
            },
            {
                "role": "assistant",
                "content": "\n当前的问题是：呼吸数值不在12~45次/分的范围内，请问呼吸的具体数值是多少？"
            },
            {
                "role": "user",
                "content": "呼吸：18 次/分"
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
#             "chief_complaint": "神志模糊、呕吐1小时。",
#             "history_of_present_illness": "1小时前饮酒后出现神志模糊，伴呕吐非咖啡色胃内容数次，无肢体抽搐，无呼吸困难，无胸闷、胸痛。",
#             "past_medical_history": "既往高血压病史1个月，规律服药治疗。",
#             "personal_history": "否认吸烟、有饮酒史。",
#             "allergy_history": "否认药物和食物过敏史。",
#             "physical_examination": {
#                 "temperature": "36.7℃",
#                 "pulse": "70次/分",
#                 "blood_pressure": "197/73mmHg",
#                 "respiration": "18次/分"
#             },
#             "auxiliary_examination": "血常规检查"
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
#     },
#     "chat": {
#         "historical_conversations": [
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：体温数值后缺少单位“℃”，请问体温的具体数值是多少？"
#             },
#             {
#                 "role": "user",
#                 "content": "36.7℃"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：脉搏缺少数值和单位，请问脉搏的具体数值和单位是多少？"
#             },
#             {
#                 "role": "user",
#                 "content": "脉搏是70次/分"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：血压数值后缺少单位“mmHg”，请问血压的具体数值和单位是多少？"
#             },
#             {
#                 "role": "user",
#                 "content": "血压是197/73mmHg"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：脉搏的检查结果为空，请问脉搏的检查结果是否正常？如果不正常，请提供具体的数值。"
#             },
#             {
#                 "role": "user",
#                 "content": "上面的回复中已经提供了。"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：辅助检查内容为空，请问是否需要进行辅助检查？如果需要，请提供具体的检查项目。"
#             },
#             {
#                 "role": "user",
#                 "content": "血常规检查"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：脉搏未提供脉搏数值，请问脉搏的具体数值是多少？"
#             },
#             {
#                 "role": "user",
#                 "content": "上面的回复中已经提供了。"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n当前的问题是：呼吸数值不在12~45次/分的范围内，请问呼吸的具体数值是多少？"
#             },
#             {
#                 "role": "user",
#                 "content": "呼吸：18 次/分"
#             },
#             {
#                 "role": "assistant",
#                 "content": "\n我已按照您的要求修改了病历，现在为您重新生成病历：{\n\"病历\": {\n    \"主诉\": \"神志模糊、呕吐1小时。\",\n    \"现病史\": \"1小时前饮酒后出现神志模糊，伴呕吐非咖啡色胃内容数次，无肢体抽搐，无呼吸困难，无胸闷、胸痛。\",\n    \"既往史\": \"既往高血压病史1个月，规律服药治疗。\",\n    \"个人史\": \"否认吸烟、有饮酒史。\",\n    \"过敏史\": \"否认药物和食物过敏史。\",\n    \"体格检查\": {\n        \"体温\": \"36.7℃\",\n        \"脉搏\": \"70次/分\",\n        \"血压\": \"197/73mmHg\",\n        \"呼吸\": \"18次/分\"\n    },\n    \"辅助检查\": \"血常规检查\"\n}\n}\n请确认病历信息是否准确，如果正确请回复“正确”，如果不正确请回复需要修改的内容。"
#             }
#         ]
#     }
# }