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
class PromptExamAss_v2(PromptTemplate):
    def __init__(self, receive) -> None:
        super().__init__()
        self.yaml_name = "examass_v2.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.input.basic_medical_record
        self.diag = receive.input.diagnosis
        self.diagnose_suspect = [(item.diagnosis_name_retrieve or item.diagnosis_name)
            for item in self.diag if item.diagnosis_identifier == "疑似"]
        physical_examination = json.loads(self.bmr.physical_examination.json())
        self.physical_examination = {reversed_sub_medical_fields.get(k): v for k, v in physical_examination.items()}

    def set_prompt(self):
        self.variables = {
            "format_examine_assay": self.format_examine_assay,
            "patient_name": self.ci_p.patient_name,
            "patient_gender": self.ci_p.patient_gender,
            "patient_age": self.ci_p.patient_age,
            "chief_complaint": self.bmr.chief_complaint,
            "history_of_present_illness": self.bmr.history_of_present_illness,
            "personal_history": self.bmr.personal_history,
            "allergy_history": self.bmr.allergy_history,
            "physical_examination": self.physical_examination,
            "auxiliary_examination": self.bmr.auxiliary_examination,
            "diagnose_suspect": self.diagnose_suspect
        }
        self.prompt = {
            "5": self.__set_exam_assay(),
        }
        return self.prompt

    def __set_exam_assay(self):
        system_str = self.prompt_manager.get_prompt("exam_assay", 0, self.variables)
        if len(self.diagnose_suspect) == 0:
            user_str = self.prompt_manager.get_prompt("exam_assay", 1, self.variables)
        else:
            user_str = self.prompt_manager.get_prompt("exam_assay", 2, self.variables)
        return system_str, user_str