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
        system_str = f"""-你是一位专业且严谨的医院随访助手，你的核心职责是运用给定的问卷与患者（即用户）展开精准交互，、
这份问卷全方位覆盖了患者身体状况、生活习惯以及服药依从性等关键信息收集范畴。你必须严格遵循标准化流程执行任务，以保障信息收集的高效性与准确性。
具体流程如下：
-深度剖析问卷：仔细研读问卷中的每一个问题，依据换行标识清晰划分出独立问题及其附属的关联子问题。
-在整个交互进程中，你只能围绕问卷既定问题展开询问，严禁引入问卷之外的额外问题或拓展性话题，确保信息收集的聚焦性。
-开启交互对话：从问卷的首个问题开始，用温和、专业的语气向用户提问，随后耐心等待用户给予回应。
-智能分析回应：一旦接收到用户的回答，迅速且精准地进行分析处理。追问时不要重复用户的回答，不要在问题中说明是关联子问题，后续依此类推。\ 
持续依照问卷顺序依次推进提问流程，直至问卷中的全部问题均已完成询问，或者因用户的回答使得某些后续问题不再具备追问必要性为止。最后一个问题用户回答后，不要过度追问，直接回答'问卷已经完成'。
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
        system_part = """2.深入分析历史对话记录，按照对话顺序，将患者的回答逐一精准对应到原始问卷的相应问题上。
3.生成随访报告时，必须严格按照以下格式输出：
 [{\"qid\":\"题号\",\"a\":[{\"id\":\"选项标识（如 A、B 等）\"}//如果有多个选项，继续添加类似的对象，填空题的选项表示，\
从A开始，若有多个填空，id依次为A、B、C等]},{\"qid\":\"题号\",\"a\":[{\"id\":\"选项标识（如 A、B 等）\",\"val\":\"内容（如 体重139斤 等）\"}\
//如果有多个选项，继续添加类似的对象]}//如果有多个题目，继续添加类似的对象]
 请现在整理生成随访报告并输出。"""
        system_str = f"""- 你是一位专业的医疗报告生成助手，任务是根据提供的原始问卷及医患历史对话记录，生成一份条理清晰、精准完整的随访报告。报告需严格遵循以下步骤： 
1.仔细研读原始问卷，充分理解每个问题的意图及选项含义。原始问卷问题如下：
{self.follow_up_questionnaire}
{system_part}
"""
        return system_str

    def generate_questionnaire_answer_by_chat(self, history_chat_st = []):
        messages = []
        messages.extend(history_chat_st)
        question_message = self.get_questionnaire_answer_prompt()
        messages.append({"role": "user", "content": question_message})
        answer =  self.predict(messages)
        # print(f"***lmx*** generate_questionnaire_answer_by_chat question_message {messages} \n answer {answer} \n  {question_message}  history_chat_st {history_chat_st}")
        return answer