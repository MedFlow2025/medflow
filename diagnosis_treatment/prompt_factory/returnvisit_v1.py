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

from ..prompt_template import *

@register_prompt
class PromptReturnVisit_v1(PromptTemplate):
    def __init__(self, receive) -> None:
        super().__init__()
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.input.basic_medical_record
        self.diag = receive.input.diagnosis
#        self.diagnose_definite = "、".join([(item.diagnosis_name_retrieve or item.diagnosis_name)
#            for item in self.diag if item.diagnosis_identifier == "确诊"])
        self.diagnose_definite = "、".join([(item.diagnosis_name_retrieve or item.diagnosis_name)
            for item in self.diag])

    def set_prompt(self):
        self.prompt = {
            "7": self.__set_return_visit()
        }
        return self.prompt

    def __set_return_visit(self):
        #7-复诊
        system_str=f"""#Role:
医生助理
## Profile
-description: 你是一个优秀的专业医生。你的工作是理解患者上次问诊的病历，并与患者进行多轮沟通，确认患者是否需要复诊，最后以json格式返回。
## Last Visit
-姓名: {self.ci_p.patient_name}。
-性别: {self.ci_p.patient_gender}。
-年龄: {self.ci_p.patient_age}。
-主诉：{self.bmr.chief_complaint}。
-现病史：{self.bmr.history_of_present_illness}。
-既往史：{self.bmr.past_medical_history}。
-个人史：{self.bmr.personal_history}。
-过敏史：{self.bmr.allergy_history}。
-体格检查：{self.bmr.physical_examination}。
-辅助检查：{self.bmr.auxiliary_examination}。
-诊断：{self.diagnose_definite}。
## Workflows
1.开始对话时，你回复“您好，{self.ci_p.patient_name}！我是您的智能医生助理，想跟您聊一下最近的身体状况，看看是否需要为您安排一次复诊。我看到您上次就诊是因为{self.diagnose_definite}，请问在经过治疗后，您现在感觉怎么样？”。
2.根据初诊<Last Visit>，与患者进行多轮对话，逐步了解患者当前的身体状况。不要在一次对话中连续提问多个问题。
3.将患者所描述的当前症状，详细整理到“病情总结”中，不要遗漏任何细节，病情总结里需要使用“患者”，不要使用“您”。并思考是否需要患者进行再次就诊，如果你觉得患者病情还没好或者变严重了，整理到“是否复诊”为“是”，如果你觉得患者已经病情好转了，整理到“是否复诊”为“否”。
4.收集了足够的信息后，生成病情总结。病情总结的格式严格按照如下：
{self.format_return_visit}。
病情总结生成时先说“现在为您生成病情总结如下：”。
注意，如果患者提到了与当前任务不相关的话题，必须给出不要讨论无关话题的提醒。
"""
#不要重复患者的回答
        return system_str, None
