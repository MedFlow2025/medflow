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
class PromptBasicMedicalRecord_v4(PromptTemplate):
    def __init__(self, receive) -> None:
        super().__init__()
        self.yaml_name = "basicmedicalrecord_v4.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.output.basic_medical_record

    def set_prompt(self):
        self.variables = {
            "patient_name": self.ci_p.patient_name,
            "patient_gender": self.ci_p.patient_gender,
            "patient_age": self.ci_p.patient_age,
            "reversed_patient_gender": gender_map.get(self.ci_p.patient_gender),
            "format_basic_medical_record": self.format_basic_medical_record,
            "chief_complaint": self.bmr.chief_complaint,
            "history_of_present_illness": self.bmr.history_of_present_illness,
            "past_medical_history": self.bmr.past_medical_history,
            "personal_history": self.bmr.personal_history,
            "allergy_history": self.bmr.allergy_history
        }
        self.prompt = {
            "21": self.__set_collect_record(),
            "2": self.__set_modify_record()
        }
        return self.prompt

    def __set_collect_record(self):
        system_str = self.prompt_manager.get_prompt("collect_record", 0, self.variables)
        if int(self.ci_p.patient_age) >= 18:
            system_str += self.prompt_manager.get_prompt("collect_record", 1, self.variables)
        else:
            system_str += self.prompt_manager.get_prompt("collect_record", 2, self.variables)
        system_str += self.prompt_manager.get_prompt("collect_record", 3, self.variables)
        return system_str, None

    def __set_modify_record(self):
        system_str = self.prompt_manager.get_prompt("modify_reocrd", 0, self.variables)
        return system_str, None