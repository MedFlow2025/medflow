# v1-对话生成建档

#url: http://ip:port/inference?request_type=v1
#输入(input)：
#    null
#输出(output)：
#    client_info(患者信息和监护人信息)
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示，使用时增加一组role为user的回答即可）
#步骤:
#   1.问患者的姓名（无校验）
#     更新output.client_info.patient.patient_name。
#   2.问患者的身份证号码（2.1中列举的三类证件类型的证件号码可以进行校验(按身份证规则)，其他类型的没有校验）
#     2.1如果输入的是大陆居民身份证(一代/二代)、港澳居民居住证、台湾居民居住证三者，可以解析出性别、年龄和是否儿童，更新output.client_info.patient.patient_gender、patient_age、if_child、certificate_type、certificate_number
#        如果不是儿童，会同步更新output.client_info.guardian中的内容全为“无”。
#     2.2如果输入的不是上边三类证件类型，例如，香港身份证等，先更新output.client_info.patient.certificate_type、certificate_number。
#        然后向患者询问性别和出生日期（限制于1-120岁），解析出性别、年龄和是否儿童，依次更新output.client_info.patient.patient_gender、patient_age、if_child。
#   3.问患者的手机号（有校验：位数+固定开头）
#     更新output.client_info.patient.mobile_number。
#   4.问患者的所居区域（有校验：需填写到 省/市/区/街道 四级。每级可能存在列举不全的情况，例如，一级的省、市、自治区、直辖市等，可能还有其他的叫法也属于一级。）
#     更新output.client_info.patient.current_address。
#   5.问患者的详细地址（有校验：只能填写包含到“号”的地址）
#     更新output.client_info.patient.detailed_address。
#   6.（如果非儿童，会跳过这一步）问监护人的姓名（无校验）
#     更新output.client_info.guardian.guardian_name。
#   7.（如果非儿童，会跳过这一步）问监护人的身份证号码（有校验，同上，且身份证年龄不能小于20岁）
#     更新output.client_info.patient.certificate_type、certificate_number。
#   8.将如上所收集的信息返回给患者：“我已经收集了<患者姓名>的相关信息如下：xxxxxx”。
#其他:
#    1.output.client_info.patient.if_child、patient_age的类型都改成str("");
#    2.测试用身份证号：
#      儿童身份证：620623202010117375
#      成人身份证：11010119900307803X
#      香港身份证：V136750(A)
#      一代身份证：610104620927690
#测试脚本：
#    bash v1-jiandang.sh
curl -X 'POST' \
  'http://ip:port/inference?request_type=v1' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '
{
    "input": {
        "client_info": []
    },
    "output": {
        "client_info": [
            {
                "patient": {
                    "patient_name": "",
                    "patient_gender": "",
                    "patient_age": "",
                    "if_child": "",
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
            }
        ],
        "create_file": ""
    },
    "chat": {
        "historical_conversations_bak": [
            {
                "role": "assistant",
                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
            }
        ],
        "historical_conversations": [
            {
                "role": "assistant",
                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
            },
            {
                "role": "user",
                "content": "张三"
            }
        ],
        "prompt_version": "v1",
        "model_name": "model_medical_20250122"
    }
}
'


#测试结果-选择就诊人(已有建档数量=1)-选择本人就诊
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "孙七",
#                    "patient_gender": "男",
#                    "patient_age": "34",
#                    "if_child": "否",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X",
#                    "mobile_number": "13878541269",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            }
#        ]
#    },
#    "output": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "孙七",
#                    "patient_gender": "男",
#                    "patient_age": "34",
#                    "if_child": "否",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X",
#                    "mobile_number": "13878541269",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            }
#        ],
#        "create_file": "否"
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，孙七！请问您是本人就诊吗?如果是的话，请回复我“是的”，如果不是的话，请回复我本次就诊的患者姓名。"
#            },
#            {
#                "role": "user",
#                "content": "是的"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的信息如下：{\n    \"就诊人姓名\": \"孙七\"\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了孙七的相关信息如下：\n{\n    \"档案\": {\n        \"患者信息\": {\n            \"姓名\": \"孙七\",\n            \"是否儿童\": \"否\",\n            \"性别\": \"男\",\n            \"年龄\": \"34\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"11010119900307803X\",\n            \"手机号\": \"13878541269\",\n            \"所在区域\": {\n                \"省\": \"广东省\",\n                \"市\": \"广州市\",\n                \"区\": \"增城区\",\n                \"街道\": \"朱村街道\"\n            },\n            \"详细地址\": \"\"\n        },\n        \"监护人信息\": {\n            \"姓名\": \"无\",\n            \"证件类型\": \"无\",\n            \"证件号码\": \"无\"\n        }\n    }\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，孙七！请问您是本人就诊吗?如果是的话，请回复我“是的”，如果不是的话，请回复我本次就诊的患者姓名。"
#            },
#            {
#                "role": "user",
#                "content": "是的"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了孙七的相关信息如下：\n\n患者信息: \n   姓名: 孙七\n   是否儿童: 否\n   性别: 男\n   年龄: 34\n   证件类型: 大陆居民身份证(二代)\n   证件号码: 11010119900307803X\n   手机号: 13878541269\n   所在区域: \n       省: 广东省\n       市: 广州市\n       区: 增城区\n       街道: 朱村街道\n   详细地址: \n\n监护人信息:\n    姓名: 无\n    证件类型: 无\n    证件号码: 无\n"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-选择就诊人(已有建档数量=1)-不选择已有，选择新建档案
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "孙七",
#                    "patient_gender": "男",
#                    "patient_age": "34",
#                    "if_child": "否",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X",
#                    "mobile_number": "13878541269",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            }
#        ]
#    },
#    "output": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "",
#                    "patient_age": "",
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
#        "create_file": "是"
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，孙七！请问您是本人就诊吗?如果是的话，请回复我“是的”，如果不是的话，请回复我本次就诊的患者姓名。"
#            },
#            {
#                "role": "user",
#                "content": "不是，是我妈妈，张三"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的信息如下：{\n    \"就诊人姓名\": \"张三\"\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，孙七！请问您是本人就诊吗?如果是的话，请回复我“是的”，如果不是的话，请回复我本次就诊的患者姓名。"
#            },
#            {
#                "role": "user",
#                "content": "不是，是我妈妈，张三"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-选择就诊人(已有建档数量>1)-选择其中一人就诊
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "孙七",
#                    "patient_gender": "男",
#                    "patient_age": "34",
#                    "if_child": "否",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X",
#                    "mobile_number": "13878541269",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            },
#            {
#                "patient": {
#                    "patient_name": "赵六",
#                    "patient_gender": "男",
#                    "patient_age": "4",
#                    "if_child": "是",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "620623202010117375",
#                    "mobile_number": "15323654256",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": "东山街道231号"
#                },
#                "guardian": {
#                    "guardian_name": "孙七",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X"
#                }
#            }
#        ]
#    },
#    "output": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "赵六",
#                    "patient_gender": "男",
#                    "patient_age": "4",
#                    "if_child": "是",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "620623202010117375",
#                    "mobile_number": "15323654256",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": "东山街道231号"
#                },
#                "guardian": {
#                    "guardian_name": "孙七",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X"
#                }
#            }
#        ],
#        "create_file": "否"
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好！当前您绑定的患者有孙七、赵六，请选择本次就诊的患者姓名是？如果需要就诊的患者不在已绑定列表中，请直接回复本次就诊的患者姓名。\n已绑定患者信息：【孙七  赵六】。"
#            },
#            {
#                "role": "user",
#                "content": "赵六"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的信息如下：{\"就诊人姓名\": \"赵六\"}"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了赵六的相关信息如下：\n{\n    \"档案\": {\n        \"患者信息\": {\n            \"姓名\": \"赵六\",\n            \"是否儿童\": \"是\",\n            \"性别\": \"男\",\n            \"年龄\": \"4\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"620623202010117375\",\n            \"手机号\": \"15323654256\",\n            \"所在区域\": {\n                \"省\": \"广东省\",\n                \"市\": \"广州市\",\n                \"区\": \"增城区\",\n                \"街道\": \"朱村街道\"\n            },\n            \"详细地址\": \"东山街道231号\"\n        },\n        \"监护人信息\": {\n            \"姓名\": \"孙七\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"11010119900307803X\"\n        }\n    }\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好！当前您绑定的患者有孙七、赵六，请选择本次就诊的患者姓名是？如果需要就诊的患者不在已绑定列表中，请直接回复本次就诊的患者姓名。\n已绑定患者信息：【孙七  赵六】。"
#            },
#            {
#                "role": "user",
#                "content": "赵六"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了赵六的相关信息如下：\n\n患者信息: \n   姓名: 赵六\n   是否儿童: 是\n   性别: 男\n   年龄: 4\n   证件类型: 大陆居民身份证(二代)\n   证件号码: 620623202010117375\n   手机号: 15323654256\n   所在区域: \n       省: 广东省\n       市: 广州市\n       区: 增城区\n       街道: 朱村街道\n   详细地址: 东山街道231号\n\n监护人信息:\n    姓名: 孙七\n    证件类型: 大陆居民身份证(二代)\n    证件号码: 11010119900307803X\n"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-选择就诊人(已有建档数量>1)-不选择已有，选择新建档案
#{
#    "input": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "孙七",
#                    "patient_gender": "男",
#                    "patient_age": "34",
#                    "if_child": "否",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X",
#                    "mobile_number": "13878541269",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": ""
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            },
#            {
#                "patient": {
#                    "patient_name": "赵六",
#                    "patient_gender": "男",
#                    "patient_age": "4",
#                    "if_child": "是",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "620623202010117375",
#                    "mobile_number": "15323654256",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": "东山街道231号"
#                },
#                "guardian": {
#                    "guardian_name": "孙七",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X"
#                }
#            }
#        ]
#    },
#    "output": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "王五",
#                    "patient_gender": "",
#                    "patient_age": "",
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
#        "create_file": "是"
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好！当前您绑定的患者有孙七、赵六，请选择本次就诊的患者姓名是？如果需要就诊的患者不在已绑定列表中，请直接回复本次就诊的患者姓名。\n已绑定患者信息：【孙七  赵六】。"
#            },
#            {
#                "role": "user",
#                "content": "王五"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的信息如下：{\n    \"就诊人姓名\": \"王五\"\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好！当前您绑定的患者有孙七、赵六，请选择本次就诊的患者姓名是？如果需要就诊的患者不在已绑定列表中，请直接回复本次就诊的患者姓名。\n已绑定患者信息：【孙七  赵六】。"
#            },
#            {
#                "role": "user",
#                "content": "王五"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-一问一答-儿童
#{
#    "input": {
#        "client_info": []
#    },
#    "output": {
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "男",
#                    "patient_age": "4",
#                    "if_child": "是",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "620623202010117375",
#                    "mobile_number": "15323654256",
#                    "current_address": {
#                        "province": "内蒙古自治区",
#                        "city": "巴盟",
#                        "district": "杭锦后旗",
#                        "street": "二道桥镇"
#                    },
#                    "detailed_address": "中山路102号"
#                },
#                "guardian": {
#                    "guardian_name": "王五",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X"
#                }
#            }
#        ],
#        "create_file": "是"
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "张三"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的姓名如下：{'姓名': '张三'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117376"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的证件号码不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的证件信息如下：\n{'证件类型': '大陆居民身份证', '证件号码': '620623202010117375'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的手机号码是什么？"
#            },
#            {
#                "role": "user",
#                "content": "15423654256"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的手机号码不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "15323654256"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的手机号码如下：{'手机号码': '15323654256'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？例如，广东省广州市增城区朱村街道等，请详细到省、市、区、街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东省广州市增城区"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的现居地址需要包含正确的“省/市/区/街道”四个级别，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "内蒙古自治区巴盟杭锦后旗二道桥镇"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的所居区域如下：\n{'所居区域': {'省': '内蒙古自治区', '市': '巴盟', '区': '杭锦后旗', '街道': '二道桥镇'}}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "中山路"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的详细地址没有具体到门牌号，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "中山路102号"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的详细地址如下：\n{'详细地址': '中山路102号'}"
#            },
#            {
#                "role": "assistant",
#                "content": "当前患者是儿童，请问监护人的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "王五"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的监护人姓名如下：{'监护人姓名': '王五'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问监护人的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的证件号码所对应的监护人年龄过小，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "11010119900307803X"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的监护人证件信息如下：\n{'证件类型': '大陆居民身份证', '证件号码': '11010119900307803X'}"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了张三的相关信息如下：\n{\n    \"档案\": {\n        \"患者信息\": {\n            \"姓名\": \"张三\",\n            \"是否儿童\": \"是\",\n            \"性别\": \"男\",\n            \"年龄\": \"4\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"620623202010117375\",\n            \"手机号\": \"15323654256\",\n            \"所在区域\": {\n                \"省\": \"内蒙古自治区\",\n                \"市\": \"巴盟\",\n                \"区\": \"杭锦后旗\",\n                \"街道\": \"二道桥镇\"\n            },\n            \"详细地址\": \"中山路102号\"\n        },\n        \"监护人信息\": {\n            \"姓名\": \"王五\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"11010119900307803X\"\n        }\n    }\n}"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，谢谢！祝您早日康复！"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "张三"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117376"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的证件号码不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的手机号码是什么？"
#            },
#            {
#                "role": "user",
#                "content": "15423654256"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的手机号码不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "15323654256"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？例如，广东省广州市增城区朱村街道等，请详细到省、市、区、街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东省广州市增城区"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的现居地址需要包含正确的“省/市/区/街道”四个级别，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "内蒙古自治区巴盟杭锦后旗二道桥镇"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "中山路"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的详细地址没有具体到门牌号，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "中山路102号"
#            },
#            {
#                "role": "assistant",
#                "content": "当前患者是儿童，请问监护人的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "王五"
#            },
#            {
#                "role": "assistant",
#                "content": "请问监护人的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的证件号码所对应的监护人年龄过小，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "11010119900307803X"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了张三的相关信息如下：\n\n患者信息: \n   姓名: 张三\n   是否儿童: 是\n   性别: 男\n   年龄: 4\n   证件类型: 大陆居民身份证(二代)\n   证件号码: 620623202010117375\n   手机号: 15323654256\n   所在区域: \n       省: 内蒙古自治区\n       市: 巴盟\n       区: 杭锦后旗\n       街道: 二道桥镇\n   详细地址: 中山路102号\n\n监护人信息:\n    姓名: 王五\n    证件类型: 大陆居民身份证(二代)\n    证件号码: 11010119900307803X\n"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，谢谢！祝您早日康复！"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试结果-一问一答-非儿童
#{
#    "input": {
#        "client_info": []
#    },
#    "output": {
#        "create_file": "是",
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "张三",
#                    "patient_gender": "男",
#                    "patient_age": "44",
#                    "if_child": "否",
#                    "certificate_type": "香港居民身份证",
#                    "certificate_number": "V136750(A)",
#                    "mobile_number": "13874569825",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": "幸福小区2号楼二单元202"
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "张三"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的姓名如下：{'姓名': '张三'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "香港身份证，V136750(A)"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的证件信息如下：\n{'证件类型': '香港居民身份证', '证件号码': 'V136750(A)'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的性别是什么？（男/女）"
#            },
#            {
#                "role": "user",
#                "content": "不知道"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的患者性别不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "男"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的性别如下：{'性别': '男'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的出生年月日是什么?（例如，20120916、2012年9月16日、2012-9-16等。）"
#            },
#            {
#                "role": "user",
#                "content": "2035年8月14号"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的患者出生日期需要包含正确的“年/月/日”，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "1900-1-1"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的患者出生日期需要包含正确的“年/月/日”，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "19801011"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的出生日期如下：\n{'出生日期': {'年': '1980', '月': '10', '日': '11'}}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的手机号码是什么？"
#            },
#            {
#                "role": "user",
#                "content": "4567989"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的手机号码不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "13874569825"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的手机号码如下：{'手机号码': '13874569825'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？例如，广东省广州市增城区朱村街道等，请详细到省、市、区、街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东省广州市增城区朱村"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的所居区域如下：\n{'所居区域': {'省': '广东省', '市': '广州市', '区': '增城区', '街道': '朱村街道'}}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "无"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的详细地址没有具体到门牌号，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "幸福小区"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的详细地址没有具体到门牌号，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "幸福小区2号楼二单元202"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的详细地址如下：\n{'详细地址': '幸福小区2号楼二单元202'}"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了张三的相关信息如下：\n{\n    \"档案\": {\n        \"患者信息\": {\n            \"姓名\": \"张三\",\n            \"是否儿童\": \"否\",\n            \"性别\": \"男\",\n            \"年龄\": \"44\",\n            \"证件类型\": \"香港居民身份证\",\n            \"证件号码\": \"V136750(A)\",\n            \"手机号\": \"13874569825\",\n            \"所在区域\": {\n                \"省\": \"广东省\",\n                \"市\": \"广州市\",\n                \"区\": \"增城区\",\n                \"街道\": \"朱村街道\"\n            },\n            \"详细地址\": \"幸福小区2号楼二单元202\"\n        },\n        \"监护人信息\": {\n            \"姓名\": \"无\",\n            \"证件类型\": \"无\",\n            \"证件号码\": \"无\"\n        }\n    }\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "张三"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "香港身份证，V136750(A)"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的性别是什么？（男/女）"
#            },
#            {
#                "role": "user",
#                "content": "不知道"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的患者性别不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "男"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的出生年月日是什么?（例如，20120916、2012年9月16日、2012-9-16等。）"
#            },
#            {
#                "role": "user",
#                "content": "2035年8月14号"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的患者出生日期需要包含正确的“年/月/日”，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "1900-1-1"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的患者出生日期需要包含正确的“年/月/日”，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "19801011"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者的手机号码是什么？"
#            },
#            {
#                "role": "user",
#                "content": "4567989"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的手机号码不符合规范，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "13874569825"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？例如，广东省广州市增城区朱村街道等，请详细到省、市、区、街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东省广州市增城区朱村"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "无"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的详细地址没有具体到门牌号，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "幸福小区"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉，您输入的详细地址没有具体到门牌号，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "幸福小区2号楼二单元202"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了张三的相关信息如下：\n\n患者信息: \n   姓名: 张三\n   是否儿童: 否\n   性别: 男\n   年龄: 44\n   证件类型: 香港居民身份证\n   证件号码: V136750(A)\n   手机号: 13874569825\n   所在区域: \n       省: 广东省\n       市: 广州市\n       区: 增城区\n       街道: 朱村街道\n   详细地址: 幸福小区2号楼二单元202\n\n监护人信息:\n    姓名: 无\n    证件类型: 无\n    证件号码: 无\n"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试-一问多答-儿童
#{
#    "input": {
#        "client_info": []
#    },
#    "output": {
#        "create_file": "是",
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "赵六",
#                    "patient_gender": "男",
#                    "patient_age": "4",
#                    "if_child": "是",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "620623202010117375",
#                    "mobile_number": "13878523690",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": "东山街道202号"
#                },
#                "guardian": {
#                    "guardian_name": "孙七",
#                    "certificate_type": "大陆居民身份证(二代)",
#                    "certificate_number": "11010119900307803X"
#                }
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "赵六，62062320201011737，手机号是15425362023"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的证件号码、手机号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117377，手机号13878523690"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的证件号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的证件信息如下：{\"姓名\": \"赵六\", \"性别\": \"\", \"出生日期\": {\"年\": \"\", \"月\": \"\", \"日\": \"\"}, \"证件类型\": \"大陆居民身份证\", \"证件号码\": \"620623202010117375\", \"手机号码\": \"13878523690\"}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？请具体到XX省XX市XX区XX街道，例如，广东省广州市黄埔区萝岗街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东广州增城区"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，我已经收集到了您所居住的广东省广州市增城区，请补充街道信息。"
#            },
#            {
#                "role": "user",
#                "content": "朱村街道"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的所居区域如下：\n{'所居区域': {'省': '广东省', '市': '广州市', '区': '增城区', '街道': '朱村街道'}}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "东山路202号"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的详细地址如下：{'详细地址': '东山路202号'}"
#            },
#            {
#                "role": "assistant",
#                "content": "当前患者是儿童，请问监护人的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "孙七"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的监护人姓名如下：{'监护人姓名': '孙七'}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问监护人的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的证件号码所对应的监护人年龄过小，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "11010119900307803X"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的监护人证件信息如下：\n{'证件类型': '大陆居民身份证', '证件号码': '11010119900307803X'}"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了赵六的相关信息如下：\n{\n    \"档案\": {\n        \"患者信息\": {\n            \"姓名\": \"赵六\",\n            \"是否儿童\": \"是\",\n            \"性别\": \"男\",\n            \"年龄\": \"4\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"620623202010117375\",\n            \"手机号\": \"13878523690\",\n            \"所在区域\": {\n                \"省\": \"广东省\",\n                \"市\": \"广州市\",\n                \"区\": \"增城区\",\n                \"街道\": \"朱村街道\"\n            },\n            \"详细地址\": \"东山街道202号\"\n        },\n        \"监护人信息\": {\n            \"姓名\": \"孙七\",\n            \"证件类型\": \"大陆居民身份证(二代)\",\n            \"证件号码\": \"11010119900307803X\"\n        }\n    }\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "赵六，62062320201011737，手机号是15425362023"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的证件号码、手机号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117377，手机号13878523690"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的证件号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？请具体到XX省XX市XX区XX街道，例如，广东省广州市黄埔区萝岗街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东广州增城区"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，我已经收集到了您所居住的广东省广州市增城区，请补充街道信息。"
#            },
#            {
#                "role": "user",
#                "content": "朱村街道"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "东山路202号"
#            },
#            {
#                "role": "assistant",
#                "content": "当前患者是儿童，请问监护人的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "孙七"
#            },
#            {
#                "role": "assistant",
#                "content": "请问监护人的身份证号码是什么？（支持的证件类型有：大陆居民身份证、港澳居民居住证、台湾居民居住证。如果您使用其他证件，请跟我说明证件类型与证件号码。）"
#            },
#            {
#                "role": "user",
#                "content": "620623202010117375"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的证件号码所对应的监护人年龄过小，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "11010119900307803X"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了赵六的相关信息如下：\n\n患者信息: \n   姓名: 赵六\n   是否儿童: 是\n   性别: 男\n   年龄: 4\n   证件类型: 大陆居民身份证(二代)\n   证件号码: 620623202010117375\n   手机号: 13878523690\n   所在区域: \n       省: 广东省\n       市: 广州市\n       区: 增城区\n       街道: 朱村街道\n   详细地址: 东山街道202号\n\n监护人信息:\n    姓名: 孙七\n    证件类型: 大陆居民身份证(二代)\n    证件号码: 11010119900307803X\n"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}






#测试-一问多答-非儿童
#{
#    "input": {
#        "client_info": []
#    },
#    "output": {
#        "create_file": "是",
#        "client_info": [
#            {
#                "patient": {
#                    "patient_name": "赵六",
#                    "patient_gender": "男",
#                    "patient_age": "44",
#                    "if_child": "否",
#                    "certificate_type": "香港身份证",
#                    "certificate_number": "V136750(A)",
#                    "mobile_number": "15225362022",
#                    "current_address": {
#                        "province": "广东省",
#                        "city": "广州市",
#                        "district": "增城区",
#                        "street": "朱村街道"
#                    },
#                    "detailed_address": "东山街道203号"
#                },
#                "guardian": {
#                    "guardian_name": "无",
#                    "certificate_type": "无",
#                    "certificate_number": "无"
#                }
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "赵六，男，1800年7月8号出生，手机号是1542536202，香港身份证V136750(A)"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的出生日期、手机号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "15425362022，1980年7月8号"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的手机号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "15225362022"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的手机号码如下：{\"姓名\": \"赵六\", \"性别\": \"男\", \"出生日期\": {\"年\": \"1980\", \"月\": \"7\", \"日\": \"8\"}, \"证件类型\": \"香港身份证\", \"证件号码\": \"V136750(A)\", \"手机号码\": \"15225362022\"}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？请具体到XX省XX市XX区XX街道，例如，广东省广州市黄埔区萝岗街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东省广州市增城区朱村街道"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的所居区域如下：\n{'所居区域': {'省': '广东省', '市': '广州市', '区': '增城区', '街道': '朱村街道'}}"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "东山路203号"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的详细地址如下：{'详细地址': '东山路203号'}"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了赵六的相关信息如下：\n{\n    \"档案\": {\n        \"患者信息\": {\n            \"姓名\": \"赵六\",\n            \"是否儿童\": \"否\",\n            \"性别\": \"男\",\n            \"年龄\": \"44\",\n            \"证件类型\": \"香港身份证\",\n            \"证件号码\": \"V136750(A)\",\n            \"手机号\": \"15225362022\",\n            \"所在区域\": {\n                \"省\": \"广东省\",\n                \"市\": \"广州市\",\n                \"区\": \"增城区\",\n                \"街道\": \"朱村街道\"\n            },\n            \"详细地址\": \"东山街道203号\"\n        },\n        \"监护人信息\": {\n            \"姓名\": \"无\",\n            \"证件类型\": \"无\",\n            \"证件号码\": \"无\"\n        }\n    }\n}"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，我是AI导诊助手，将协助您完成预问诊和预约挂号的全过程。请问患者的姓名是什么?"
#            },
#            {
#                "role": "user",
#                "content": "赵六，男，1800年7月8号出生，手机号是1542536202，香港身份证V136750(A)"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的出生日期、手机号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "15425362022，1980年7月8号"
#            },
#            {
#                "role": "assistant",
#                "content": "抱歉😊，您输入的手机号码不符合规范呢，请核对后重新输入。"
#            },
#            {
#                "role": "user",
#                "content": "15225362022"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的区域在哪里？请具体到XX省XX市XX区XX街道，例如，广东省广州市黄埔区萝岗街道。"
#            },
#            {
#                "role": "user",
#                "content": "广东省广州市增城区朱村街道"
#            },
#            {
#                "role": "assistant",
#                "content": "请问患者所居住的详细地址是什么？例如，中山路101号等，请详细填写到门牌号。"
#            },
#            {
#                "role": "user",
#                "content": "东山路203号"
#            },
#            {
#                "role": "assistant",
#                "content": "我已经收集了赵六的相关信息如下：\n\n患者信息: \n   姓名: 赵六\n   是否儿童: 否\n   性别: 男\n   年龄: 44\n   证件类型: 香港身份证\n   证件号码: V136750(A)\n   手机号: 15225362022\n   所在区域: \n       省: 广东省\n       市: 广州市\n       区: 增城区\n       街道: 朱村街道\n   详细地址: 东山街道203号\n\n监护人信息:\n    姓名: 无\n    证件类型: 无\n    证件号码: 无\n"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}
