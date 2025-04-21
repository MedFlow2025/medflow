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

import json
from ..prompt_template import *

@register_prompt
class PromptExamAss_v1(PromptTemplate):
    def __init__(self, receive) -> None:
        super().__init__()
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.input.basic_medical_record
        self.diag = receive.input.diagnosis
        self.diagnose_suspect = [(item.diagnosis_name_retrieve or item.diagnosis_name)
            for item in self.diag if item.diagnosis_identifier == "疑似"]
        physical_examination = json.loads(self.bmr.physical_examination.json())
        self.physical_examination = {reversed_sub_medical_fields.get(k): v for k, v in physical_examination.items()}

    def set_prompt(self):
        self.prompt = {
            "5": self.__set_exam_assay(),
        }
        return self.prompt

    def __set_exam_assay(self):
        #5-生成检查和化验
        system_str=f"""你是一个优秀的医生。主要工作是根据给出的病历与诊断，生成检查项或化验项。
检查或化验的格式是json格式，例如：{self.format_examine_assay}。
如果各个诊断的诊断标识全部都为“确诊”，直接回复“您的病历已经确诊，无需生成检查项或化验项”。
如果某个诊断的诊断标识有“疑似”，需要根据该项诊断项生成对应的检查或化验项，
生成时先说“根据诊断中为疑似的项，现在为您生成检查项或化验项：”。当患者确认准确时，你回复“好的，谢谢！祝您早日康复！”"""
        if len(self.diagnose_suspect) == 0:
            user_str=f"诊断中所有的诊断标识都为“确诊”，请直接回复“您的病历已经确诊，无需生成检查项或化验项”。"
        else:
            user_str=f"""当前患者的姓名是{self.ci_p.patient_name}，性别是{self.ci_p.patient_gender}，年龄是{self.ci_p.patient_age}，\
主诉是“{self.bmr.chief_complaint}”，现病史是“{self.bmr.history_of_present_illness}”，\
个人史是“{self.bmr.personal_history}”，过敏史是“{self.bmr.allergy_history}”，\
体格检查是“{self.physical_examination}”，辅助检查是“{self.bmr.auxiliary_examination}”，\
请根据诊断中为“疑似”的{self.diagnose_suspect}项，生成“检查”或“化验”。"""
        return system_str, user_str