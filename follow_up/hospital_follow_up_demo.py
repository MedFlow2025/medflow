# Copyright (c) 2025,  IEIT SYSTEMS Co.,Ltd.  All rights reserved

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from hospital_follow_up import FollowUp

OPENAI_API_KEY = "EMPTY"
OPENAI_API_BASE = "http://ip:port/v1/"
MODEL_NAME = "model_medical_20241011"

follow_up_question = f"""
1、近期您身体有以下不适症状吗？①无明显症状   ②胸痛/胸闷    ③肌肉酸痛   ④心悸  ⑤呼吸困难 \n 1a以上的症状是在那种情况下出现？\n ①休息时都有 ②日常活动感觉不明显  ③日常活动感觉明显
2、近期您的身体有出血的情况吗？\n ①没有 ②有\n 如果有，请告知出现部位是哪里？\n ①皮肤、口腔粘膜出血  ②黑便或者血便  ③血尿  ④咳血
3、您最近有测量体重吗？请说出体重数字______
4、您的运动情况怎样？\n①规律运动   ②不规律运动
5、出院后睡眠质量如何？\n①睡眠质量良好  ②失眠    ③易醒   ④犯困
6、出院后情绪状态如何？\n①心情愉快   ②焦虑    ③抑郁   ④暴躁
7、自获得此病以来，您目前的工作承受能力如何？\n①正常  ②轻度受限制 ③ 严重受限  ④卧床为主
8、您现在的饮食习惯如何？\n①清淡  ②偏咸  ③辛辣  ④肥腻 ⑤喜甜 
9、目前您有无吸烟的情况？\n①不吸烟  ②仍在吸烟   ③正在戒烟\n4a如果有吸烟，请告知每天吸烟数量是多少支？_______\n4b如果您已经戒烟，已戒烟了多长时间？\n①住院时开始戒烟   ②戒烟不到半年  ③戒烟已超过半年
10、目前您的饮酒情况怎样？\n①从不饮酒  ②有饮酒\n如果有饮酒，您常喝开的是哪种酒？①白酒   ②红酒   ③啤酒\n请告知每天饮酒的量是多少ml？_______
11、您是否能坚持按照医嘱规律服用心脏相关药物？\n①是   ②否\n如果没有，您能告诉我原因吗？__________
"""

# 随访chat测试demo数据
follow_up_chat = [
    [],
    [{"role": "assistant", "content":"您好，我是医院随访助手。首先，我想问您第一个问题：最近感觉身体怎么样？有没有觉得哪里不舒服，比如胸痛、胸闷、肌肉酸痛、心悸或者呼吸困难？"},
     {"role": "user", "content":"我有时候会胸痛"}],
    [{"role": "assistant", "content":"了解了，关于胸痛，您能告诉我是在休息时就有，还是日常活动时才感觉明显呢？"},
     {"role": "user", "content":"活动时才感觉明显"}],
    [{"role": "assistant", "content":"好的，谢谢您的回答。接下来，请您回答第二个问题：最近有没有出血的情况？比如皮肤、口腔粘膜出血，或者有黑便、血便，血尿，咳血等？"},
     {"role": "user", "content":"没有。"}],
    [{"role": "assistant", "content":"好的，没有出血的情况。那么，请您回答第三个问题：最近有量体重吗？能告诉我一下你的体重数字吗？"},
     {"role": "user", "content":"最近没称过，大概140斤。"}],
    [{"role": "assistant", "content":"好的，您的大概体重是140斤。接下来是第四个问题：最近运动得怎么样？是经常运动，还是偶尔运动？"},
     {"role": "user", "content":"偶尔运动一下。"}],
    [{"role": "assistant", "content":"了解了，偶尔运动。现在请您回答第五个问题：出院后，您感觉睡眠质量怎么样？是睡得挺香的，还是有时候会睡不着，或者容易醒，或者总是觉得困呢？"},
     {"role": "user", "content":"有时候会睡不着。"}],
    [{"role": "assistant", "content":"好的，您有时候会睡不着。接下来是第六个问题：出院后，您的情绪状态如何？是心情愉快，还是有点焦虑、抑郁，或者容易暴躁？"},
     {"role": "user", "content":"心情正常吧，没多愉快，但也没啥负面情绪。"}],
    [{"role": "assistant", "content":"了解了，您的心情是正常的，没有多愉快，也没有负面情绪。那么，第七个问题是：自从得病以来，您现在的工作情况怎么样？是还能正常工作，还是有点受限制，或者主要是卧床休息？"},
     {"role": "user", "content":"还能正常工作，没太大影响。"}],
    [{"role": "assistant", "content":"了好的，您还能正常工作，没有太大影响。接下来是第八个问题：现在的饮食习惯怎么样？是吃得很清淡，还是偏咸、辛辣、肥腻，或者喜欢甜食？"},
     {"role": "user", "content":"一般偏咸，也喜欢甜食。"}],
    [{"role": "assistant", "content":"好的，您的饮食习惯一般偏咸，也喜欢甜食。现在请您回答第九个问题：现在您有没有在吸烟？是不抽，还是还在抽，或者正在戒烟中？"},
     {"role": "user", "content":"目前在戒烟。"}],
    [{"role": "assistant", "content":"好的，您目前正在戒烟。那么，关于戒烟，您能告诉我戒烟了多久了吗？是住院的时候就开始戒了，还是不到半年，或者已经超过半年了？"},
     {"role": "user", "content":"差不多不到半年。"}],
    [{"role": "assistant", "content":"了解了，戒烟差不多不到半年。接下来是第十个问题：现在您喝酒吗？是不喝，还是有喝？如果有喝，您一般喝什么酒？是白酒、红酒还是啤酒？"},
     {"role": "user", "content":"不喝"}],
    [{"role": "assistant", "content":"好的，您不喝酒。最后一个问题：您现在还能坚持按照医生的建议规律地吃心脏相关的药吗？如果不能，能告诉我是什么原因吗？"},
     {"role": "user", "content":"没有坚持，有时候忘了。"}]
]

# 第一个问题，没有症状下，跳过有症状的位置提问。
follow_up_chat_1 = [{"role": "assistant", "content":"您好，我是医院随访助手。首先，我想问您第一个问题：最近身体感觉怎么样？有没有觉得哪里不舒服，比如胸口闷闷的、肌肉酸痛、心跳得快，或者呼吸有点困难？"},
    {"role": "user", "content":"没有"}]

# 吸烟问题，无吸烟情况下跳过当前追问。
follow_up_chat_2 = [{"role": "assistant", "content":"好的，您的饮食习惯一般偏咸，也喜欢甜食。现在请您回答第九个问题：现在您有没有在吸烟？是不抽，还是还在抽，或者正在戒烟中？"},
     {"role": "user", "content":"没有。"}]
follow_up_chat_3 = [{"role": "assistant", "content":"好的，您的饮食习惯一般偏咸，也喜欢甜食。现在请您回答第九个问题：现在您有没有在吸烟？是不抽，还是还在抽，或者正在戒烟中？"},
     {"role": "user", "content":"还抽烟。"}]
# 注意此处肯定需要前面的这个第几个问题，否则无法从历史对话中识别第几个问题；
follow_up_chat_4 = [{"role": "assistant", "content":"好的，您的饮食习惯一般偏咸，也喜欢甜食。现在请您回答第九个问题：现在您有没有在吸烟？是不抽，还是还在抽，或者正在戒烟中？"},
     {"role": "user", "content":"还抽烟。"},
     {"role": "assistant", "content":"好的，那请问您每天大概抽多少支烟呢"}, 
     {"role": "user", "content":"10多支吧。"}]

# 喝酒问题
follow_up_chat_5 = [{"role": "assistant", "content":"好的，您不吸烟。那么，第十个问题来了：现在您还喝酒吗？是不喝，还是偶尔喝一点？"},
     {"role": "user", "content":"偶尔喝点。"}]
follow_up_chat_6 = [{"role": "assistant", "content":"好的，您不吸烟。那么，第十个问题来了：现在您还喝酒吗？是不喝，还是偶尔喝一点？"},
     {"role": "user", "content":"偶尔喝点。"},
     {"role": "assistant", "content":"好的，那么请问您一般喝什么酒？是白酒、红酒还是啤酒？"},
     {"role": "user", "content":"一般喝啤酒多，偶尔和白酒。"}]
follow_up_chat_7 = [{"role": "assistant", "content":"好的，您不吸烟。那么，第十个问题来了：现在您还喝酒吗？是不喝，还是偶尔喝一点？"},
     {"role": "user", "content":"偶尔喝点。"},
     {"role": "assistant", "content":"好的，那么请问您一般喝什么酒？是白酒、红酒还是啤酒？"},
     {"role": "user", "content":"一般喝啤酒多，偶尔和白酒。"},
     {"role": "assistant", "content":"了解了，那么能告诉我您每天大概喝多少啤酒和白酒吗？"},
     {"role": "user", "content":"啤酒一天最多一瓶，白酒也就1两。"}]

# 心脏药物问题
follow_up_chat_8 =     [{"role": "assistant", "content":"好的，您不喝酒。最后一个问题：您现在还能坚持按照医生的建议规律地吃心脏相关的药吗？如果不能，能告诉我是什么原因吗？"},
     {"role": "user", "content":"我现在按时吃药。"}]


if __name__ == '__main__':
    follow_up_obj = FollowUp(OPENAI_API_BASE, OPENAI_API_KEY, MODEL_NAME, follow_up_question)
    
    # 生成新的问卷内容
    new_questionnaire = follow_up_obj.generate_new_questionnaire_by_input()
    print(f"new_questionnaire {new_questionnaire}")
    
    # '''
    # 根据新的问卷内容及历史chat情况，生成新的对话问题
    temp_chat_info = []
    for chat_info in follow_up_chat:
        temp_chat_info.extend(chat_info)
        new_question = follow_up_obj.generate_new_question_by_chat(temp_chat_info)
        print(f"new_question {new_question}")
    
    # 根据对话内容，生成问卷报告
    questionnaire_answer = follow_up_obj.generate_questionnaire_answer_by_chat(temp_chat_info) 
    print(f"questionnaire_answer {questionnaire_answer}")
    # '''
    
    # chat 分支问题生成
    for index in range(8):
        index = index + 1
        temp_chat = f"follow_up_chat_{index}"
        result = eval(temp_chat)
        new_question = follow_up_obj.generate_new_question_by_chat(result)
        print(f"new_question {new_question}")

    