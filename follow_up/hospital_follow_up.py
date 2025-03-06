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

from typing import List
from openai import OpenAI

class FollowUp:
    def __init__(self,
                 openai_base_url : str,
                 openai_api_key : str,
                 model_name : str,
                 follow_up_questionnaire : str
                 ):
        self.openai_base_url = openai_base_url
        self.openai_api_key = openai_api_key
        self.model_name = model_name
        self.follow_up_questionnaire = follow_up_questionnaire   

    # 推理调用
    def predict(self, messages, temp:float=0, top_p:float=1):
        client = OpenAI(api_key=self.openai_api_key, base_url=self.openai_base_url)
        chat_response = client.chat.completions.create(
            model= self.model_name,
            messages=messages,
            temperature=temp,
            top_p=top_p,
            max_tokens=2048,#8192
            stream=False,#True
            stop="<|eot_id|>",
        )
        return chat_response.choices[0].message.content

    
    # 第一步将原问卷转换为更通俗的问卷问题，方便模型理解问题及交互
    def get_new_questionnaire_prompt(self):
        system_str = f"""##角色:
你是一位医院的随访人员，擅长以专业、简洁且通俗易懂的方式询问患者与健康相关的问题，要将问卷中的问题转化为日常交流风格的对话，同时确保问题之间的逻辑关联完整无缺。\n
## 改写示例：
-原始问卷问题：出院后睡眠质量如何？\n①睡眠质量良好  ②失眠    ③易醒   ④犯困
-改写后问卷问题：最近感觉睡眠怎么样？是睡得挺香的，还是有时候会睡不着，或者容易醒，或者总是觉得困呢？
## 改写要求：
-使用日常、口语化的适合医患交流的词汇和表述，风格简洁明了，直奔主题。
-对于每个问题的选项，也要融入自然的表述中，避免生硬罗列。
-当用户回答一个问题后，后续的追问要基于用户的回答合理引出，做到逻辑连贯，像正规的医院随访对话一样。
-仔细分析原问题的问题个数，不要生成无效追问问题。
## 待改写的原始问卷问题：
{self.follow_up_questionnaire}
## Workflow：1、根据<改写示例>、<改写要求>对<待改写问题>进行改写。
"""
        return system_str

    def generate_new_questionnaire_by_input(self):
        question_message = self.get_new_questionnaire_prompt()
        messages=[{"role": "system", "content": question_message}]
        answer =  self.predict(messages)
        # print(f"***lmx*** generate_new_questionnaire_by_input question_message {messages} \n answer {answer}")
        self.new_questionnaire = answer
        return answer


    # 第二步 根据输入问题逐步提问，完成交互
    def get_question_chat_prompt(self):
        system_str = f"""-你是一位专业且严谨的医院随访助手，你的核心职责是运用给定的问卷与患者（即用户）展开精准交互，\
这份问卷全方位覆盖了患者身体状况、生活习惯以及服药依从性等关键信息收集范畴。你必须严格遵循标准化流程执行任务，\
以保障信息收集的高效性与准确性，具体流程如下：
-深度剖析问卷：仔细研读问卷中的每一个问题，依据换行标识清晰划分出独立问题及其附属的关联子问题。
-例如，对于 “最近感觉身体怎么样？有没有觉得哪里不舒服，比如胸痛、胸闷、肌肉酸痛、心悸或者呼吸困难？ - 如果有这些症状，是在休息时就有，还是日常活动时才感觉明显呢？”，\
明确主问题为 “最近感觉身体怎么样？有没有觉得哪里不舒服，\
比如胸痛、胸闷、肌肉酸痛、心悸或者呼吸困难？”，关联子问题是 “如果有这些症状，是在休息时就有，还是日常活动时才感觉明显呢？”。\
在整个交互进程中，你只能围绕问卷既定问题展开询问，严禁引入问卷之外的额外问题或拓展性话题，确保信息收集的聚焦性。
-开启交互对话：从问卷的首个问题开始，用温和、专业的语气向用户提问，随后耐心等待用户给予回应。
-智能分析回应：一旦接收到用户的回答，迅速且精准地进行分析处理。\
若用户反馈未出现问卷所提及的相关症状，例如回答 “我身体没啥毛病，一切都好”，此时应果断跳过与之对应的关联子问题，无缝衔接到下一个主问题，\
即 “最近有没有出血的情况？比如皮肤、口腔粘膜出血，或者有黑便、血便，血尿，咳血等？”；倘若用户指明某一特定症状，\
如 “我偶尔会胸痛”，那么严格按照问卷设定，立即追问关联子问题 “如果有这些症状，是在休息时就有，还是日常活动时才感觉明显呢？”，\
追问时不要重复用户的回答，不要再问题中说明是关联子问题，后续依此类推。\
持续依照问卷顺序依次推进提问流程，直至问卷中的全部问题均已完成询问，或者因用户的回答使得某些后续问题不再具备追问必要性为止。\
最后一个问题用户回答后，不要过度追问，直接回答'问卷已经完成'。
-问卷：{self.new_questionnaire}
请严格依循上述指令，根据对话内容，开始与用户对话或结束对话：
"""
        return system_str
    
    # 完成问卷会返回对应 “问卷已经完成”类似的话语
    def generate_new_question_by_chat(self, history_chat_st = []):
        messages = []
        messages.extend(history_chat_st)
        question_message = self.get_question_chat_prompt()
        messages.append({"role": "system", "content": question_message})
        answer =  self.predict(messages)
        # print(f"***lmx*** generate_new_question_by_chat question_message {messages} \n answer {answer}")
        return answer
    
    
    # 第三步：根据对话内容，产出报告内容
    def get_questionnaire_answer_prompt(self):
        system_str = f"""-你是一个专业的医疗报告生成助手，需要依据给定的原始问卷内容以及医患之间的历史对话记录，\
精准生成一份完整、条理清晰的随访报告。原始问卷涵盖了患者身体症状、生活习惯、服药依从性等多方面信息收集要点，\
历史对话记录则反映了患者对各个问题的实际回答情况。
-具体步骤如下：
仔细研读原始问卷，明确每个问题的意图和选项含义。
-问卷问题包括：
{self.follow_up_questionnaire}
-深入分析历史对话记录，按照对话顺序，将患者的回答逐一对应到原始问卷的相应问题上：
对话开始助手问：“您好，我是医院随访助手。首先，我想问您第一个问题：最近感觉身体怎么样？有没有觉得哪里不舒服，比如胸痛、胸闷、肌肉酸痛、心悸或者呼吸困难？”，患者回答：“我有时候会胸痛”，
接着助手问：“了解了，关于胸痛，您能告诉我是在休息时就有，还是日常活动时才感觉明显呢？”，患者回答：“活动时才感觉明显”，这对应原始问卷中问题 1 及 1a 的选项②和③。
以此类推，完整梳理整个对话过程中患者对每个问题的回应，并准确匹配到原始问卷选项。
生成随访报告时，注意输出完整的问卷问题。
最后，根据上述分析，按照原始问卷的问题顺序，依次清晰地列出每个问题及其对应的患者答案，生成完整的随访报告。
-报告格式需严格参照以下示例：
1、近期您身体有以下不适症状吗？①无明显症状   ②胸痛 / 胸闷    ③肌肉酸痛   ④心悸  ⑤呼吸困难
1a. 以上的症状是在那种情况下出现？①休息时都有  ②日常活动感觉不明显  ③日常活动感觉明显
答：②， ③
2、近期您的身体有出血的情况吗？
①没有  ②有
如果有，请告知出现部位是哪里？
①皮肤、口腔粘膜出血  ②黑便或者血便  ③血尿  ④咳血
答：①
3、您最近有测量体重吗？请说出体重数字______\n
答：140 斤
（后续问题及答案依次罗列，直至全部完成）
-请严格按照上述要求生成随访报告。
"""
        return system_str

    def generate_questionnaire_answer_by_chat(self, history_chat_st = []):
        messages = []
        messages.extend(history_chat_st)
        question_message = self.get_questionnaire_answer_prompt()
        messages.append({"role": "system", "content": question_message})
        answer =  self.predict(messages)
        # print(f"***lmx*** generate_questionnaire_answer_by_chat question_message {messages} \n answer {answer} \n  {question_message}  history_chat_st {history_chat_st}")
        return answer