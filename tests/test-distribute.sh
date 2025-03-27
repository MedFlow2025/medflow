# v0-任务分发

#url: http://ip:port/inference?request_type=v0
#输入(input)：
#    null
#输出(output)：
#    patient_need(患者需求)
#对话(chat)：
#    historical_conversations_bak（用于存储推理结果，使用时无需改动）
#    historical_conversations（用于返回界面显示，使用时增加一组role为user的回答即可）
#步骤:
#    1.在historical_conversations中增加一组role为user的患者回复；
#    2.发送请求后，会识别患者的意图，并将结果更新到output.patient_need中（可以仅有一个意图，也可以有多个）；
#其他:
#    1.目前患者的意图只包含“建立档案”、“预问诊”，“预约挂号”三种；
#测试脚本：
#    bash test-distribute.sh

curl -X 'POST' \
  'http://ip:port/inference?request_type=v0' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @data/distribute.json

  echo -e "\n==================================\n"

#测试结果
#{
#    "input": null,
#    "output": {
#        "patient_need": [
#            {
#                "need": "预问诊"
#            },
#            {
#                "need": "预约挂号"
#            }
#        ]
#    },
#    "chat": {
#        "historical_conversations_bak": [
#            {
#                "role": "assistant",
#                "content": "您好，请问您今天需要哪些方面的医疗服务呢？目前我们可以协助您进行“建立档案”、“预问诊”，“预约挂号”。请简单告诉我您的需求，我将为您转接到最合适的智能医疗助手。"
#            },
#            {
#                "role": "user",
#                "content": "我没来过咱们医院"
#            },
#            {
#                "role": "assistant",
#                "content": "您好，了解到您是第一次来我们医院。为了更好地为您服务，我们可以帮助您建立个人信息档案。请问您是否需要现在进行“建立档案”呢？这样我们就可以为您记录下重要的健康信息，方便您未来的就医过程。"
#            },
#            {
#                "role": "user",
#                "content": "其他的呢"
#            },
#            {
#                "role": "assistant",
#                "content": "除了建立档案，我们还可以提供“预问诊”和“预约挂号”服务。预问诊是在正式就诊前，通过AI预先了解您的病情，帮助您更好地准备就诊。而预约挂号则是根据您的病情，帮助您进行挂号，以便您能够顺利就诊。请问您对哪一项服务感兴趣呢？我可以为您进一步说明。"
#            },
#            {
#                "role": "user",
#                "content": "我有些咳嗽"
#            },
#            {
#                "role": "assistant",
#                "content": "您提到咳嗽，这可能是由于多种原因引起的。为了更好地了解您的病情，我们可以进行“预问诊”。通过预问诊，我们可以初步了解您的症状，并提供一些建议。请问您是否愿意进行预问诊呢？这样我们可以为您提供更具体的指导。"
#            },
#            {
#                "role": "user",
#                "content": "可以的"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的意图如下：\n[\n    {\n        \"患者意图\": \"预问诊\"\n    }\n]"
#            },
#            {
#                "role": "user",
#                "content": "我想直接挂号"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的意图如下：\n[\n    {\n        \"患者意图\": \"预约挂号\"\n    }\n]"
#            },
#            {
#                "role": "user",
#                "content": "我先预问诊，再挂号吧"
#            },
#            {
#                "role": "assistant",
#                "content": "现在为您返回患者的意图如下：\n[\n    {\n        \"患者意图\": \"预问诊\"\n    },\n    {\n        \"患者意图\": \"预约挂号\"\n    }\n]"
#            }
#        ],
#        "historical_conversations": [
#            {
#                "role": "assistant",
#                "content": "您好，请问您今天需要哪些方面的医疗服务呢？目前我们可以协助您进行“建立档案”、“预问诊”，“预约挂号”。请简单告诉我您的需求，我将为您转接到最合适的智能医疗助手。"
#            },
#            {
#                "role": "user",
#                "content": "我没来过咱们医院"
#            },
#            {
#                "role": "assistant",
#                "content": "您好，了解到您是第一次来我们医院。为了更好地为您服务，我们可以帮助您建立个人信息档案。请问您是否需要现在进行“建立档案”呢？这样我们就可以为您记录下重要的健康信息，方便您未来的就医过程。"
#            },
#            {
#                "role": "user",
#                "content": "其他的呢"
#            },
#            {
#                "role": "assistant",
#                "content": "除了建立档案，我们还可以提供“预问诊”和“预约挂号”服务。预问诊是在正式就诊前，通过AI预先了解您的病情，帮助您更好地准备就诊。而预约挂号则是根据您的病情，帮助您进行挂号，以便您能够顺利就诊。请问您对哪一项服务感兴趣呢？我可以为您进一步说明。"
#            },
#            {
#                "role": "user",
#                "content": "我有些咳嗽"
#            },
#            {
#                "role": "assistant",
#                "content": "您提到咳嗽，这可能是由于多种原因引起的。为了更好地了解您的病情，我们可以进行“预问诊”。通过预问诊，我们可以初步了解您的症状，并提供一些建议。请问您是否愿意进行预问诊呢？这样我们可以为您提供更具体的指导。"
#            },
#            {
#                "role": "user",
#                "content": "可以的"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，了解了。我将为您转接到如下智能助手：\n【预问诊】"
#            },
#            {
#                "role": "user",
#                "content": "我想直接挂号"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，了解了。我将为您转接到如下智能助手：\n【预约挂号】"
#            },
#            {
#                "role": "user",
#                "content": "我先预问诊，再挂号吧"
#            },
#            {
#                "role": "assistant",
#                "content": "好的，了解了。我将为您转接到如下智能助手：\n【预问诊】\n【预约挂号】"
#            }
#        ],
#        "prompt_version": "v1",
#        "model_name": "model_medical_20250122"
#    }
#}
