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
class PromptDiagnosis_v1(PromptTemplate):
    def __init__(self, receive) -> None:
        super().__init__()
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.input.basic_medical_record

    def set_prompt(self):
        self.prompt = {
            "4": self.__set_diagnosis(),
        }
        return self.prompt

    def __set_diagnosis(self):
        #4-生成诊断
        system_str=f"""你是一个优秀的医生。主要工作是根据给出的病历，生成疾病诊断，根据物理检查的各项指标结果，增强确诊疾病细节。
诊断是json格式，例如：{self.format_diagnose}。
生成时先说“根据您的预问诊报告，我为您进行初步诊断如下。请合理安排就医，祝您早日康复。”。
输出结果前，请检查，诊断标识只有‘确诊’和‘疑似’两种情况。
注意！诊断名称只能是疾病名称。"""
        user_str=f"""当前患者的姓名是{self.ci_p.patient_name}，性别是{self.ci_p.patient_gender}，年龄是{self.ci_p.patient_age}，\
主诉是“{self.bmr.chief_complaint}”，现病史是“{self.bmr.history_of_present_illness}”，\
个人史是“{self.bmr.personal_history}”，过敏史是“{self.bmr.allergy_history}”，\
体格检查是“{self.bmr.physical_examination}”，辅助检查是“{self.bmr.auxiliary_examination}”，请生成“诊断”。"""
        return system_str, user_str
