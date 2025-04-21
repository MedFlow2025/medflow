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
from fastapi import HTTPException

@register_prompt
class PromptScheme_v2(PromptTemplate):
    def __init__(self, receive, scheme, sub_scheme) -> None:
        super().__init__()
        self.yaml_name = "scheme_v2.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)
        self.scheme = scheme
        self.sub_scheme = sub_scheme
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.input.basic_medical_record
        self.diag = receive.input.diagnosis
        #self.diagnose_definite = [(item.diagnosis_name_retrieve or item.diagnosis_name)
        #    for item in self.diag if item.diagnosis_identifier == "确诊"]
        self.diagnose_definite = [(item.diagnosis_name_retrieve or item.diagnosis_name)
            for item in self.diag]
        self.pick_therapy = receive.output.pick_therapy
        physical_examination = json.loads(self.bmr.physical_examination.json())
        self.physical_examination = {reversed_sub_medical_fields.get(k): v for k, v in physical_examination.items()}

    def set_prompt(self):
        self.variables = {
            "format_pick_therapy": self.format_pick_therapy,
            "patient_name": self.ci_p.patient_name,
            "patient_gender": self.ci_p.patient_gender,
            "patient_age": self.ci_p.patient_age,
            "chief_complaint": self.bmr.chief_complaint,
            "history_of_present_illness": self.bmr.history_of_present_illness,
            "personal_history": self.bmr.personal_history,
            "allergy_history": self.bmr.allergy_history,
            "physical_examination": self.physical_examination,
            "auxiliary_examination": self.bmr.auxiliary_examination,
            "diagnose_definite": self.diagnose_definite,
            "format_prescription": self.format_prescription,
            "default_therapy": reversed_therapy_scheme_fields['default_therapy'],
            "interpret_therapy": self.__interpret_therapy('default_therapy'),
            "format_transfusion": self.format_transfusion,
            "format_disposition": self.format_disposition,
            "chief_complaint": self.bmr.chief_complaint,
            "history_of_present_illness": self.bmr.history_of_present_illness,
            "personal_history": self.bmr.personal_history,
            "allergy_history": self.bmr.allergy_history,
            "physical_examination": self.physical_examination,
            "auxiliary_examination": self.bmr.auxiliary_examination,
            "format_generate_therapy": self.format_generate_therapy
        }
        self.prompt = {
            "6": self.__set_default_therapy(),
        }
        return self.prompt

    def __interpret_therapy(self, picked_therapy):
        if self.pick_therapy != []:
            interpret_therapy = [i.interpret_therapy for i in self.pick_therapy if i.picked_therapy == picked_therapy]
        else:
            interpret_therapy = ['无']
        return interpret_therapy

    def __set_default_therapy(self):
        match self.scheme:
            case "pick_therapy":
                system_str = self.prompt_manager.get_prompt(self.scheme, 0, self.variables)
                user_str = self.prompt_manager.get_prompt(self.scheme, 1, self.variables)
            case "default_therapy":
                if self.sub_scheme in ["prescription", "transfusion", "disposition"]:
                    system_str = self.prompt_manager.get_prompt(self.sub_scheme, 0, self.variables)
                    user_str = self.prompt_manager.get_prompt(self.sub_scheme, 1, self.variables)
                else:
                    raise HTTPException(status_code=400, detail=f"Invalid Parameter: sub_scheme must be equal to prescription, transfusion or disposition.")
            case "other_therapy":
                self.variables["other_therapy"] = reversed_therapy_scheme_fields[self.sub_scheme]
                self.variables["sub_interpret_therapy"] = self.__interpret_therapy(self.sub_scheme)
                system_str = self.prompt_manager.get_prompt(self.scheme, 0, self.variables)
                user_str = self.prompt_manager.get_prompt(self.scheme, 1, self.variables)
            case _:
                raise HTTPException(status_code=400, detail=f"Invalid Parameter: scheme must be equal to pick_therapy, other_therapy or default_therapy.")
        return system_str, user_str