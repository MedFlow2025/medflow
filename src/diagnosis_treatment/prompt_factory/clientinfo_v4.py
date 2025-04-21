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
class PromptClientInfo_v4(PromptTemplate):
    def __init__(self, receive, flag, verify_results:str="") -> None:
        super().__init__()
        self.yaml_name = "clientinfo_v4.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)
        self.ci_i= receive.input.client_info
        self.ci_p = receive.output.client_info[0].patient
        self.ci_g = receive.output.client_info[0].guardian
        self.hc = receive.chat.historical_conversations
        self.flag = flag
        self.verify_results = verify_results

    def set_prompt(self):
        self.variables = {
            "format_client_select": self.format_client_select,
            "format_client_info": self.format_client_info,
            "verify_results": self.verify_results,
            "format_translate": self.format_translate,
            "patient_name": self.ci_p.patient_name,
            "if_child": self.ci_p.if_child,
            "patient_gender": self.ci_p.patient_gender,
            "patient_age": self.ci_p.patient_age,
            "certificate_type": self.ci_p.certificate_type,
            "certificate_number": self.ci_p.certificate_number,
            "mobile_number": self.ci_p.mobile_number,
            "province": self.ci_p.current_address.province,
            "city": self.ci_p.current_address.city,
            "district": self.ci_p.current_address.district,
            "street": self.ci_p.current_address.street,
            "detailed_address": self.ci_p.detailed_address,
            "guardian_name": self.ci_g.guardian_name,
            "guardian_certificate_type": self.ci_g.certificate_type,
            "guardian_certificate_number": self.ci_g.certificate_number
        }
        self.prompt = {
            "11": self.__set_select_client(),
            "12": self.__set_patient(),
            "14": self.__set_gender_age(),
            "15": self.__set_guardian(),
            "1": self.__set_modify_client()
        }
        if self.flag == 13:
            self.prompt = {
            "13": self.__set_patient_optimize(),
            }
        return self.prompt

    def __client_num(self):
        client = []
        for k, v in enumerate(self.ci_i):
            if not any(getattr(v.patient, attr) in ["", None] for attr in ['patient_name', 'certificate_type', 'certificate_number']):
                client.append(v.patient.patient_name)
        return client

    def __set_select_client(self):
        client = self.__client_num()
        if len(client) == 1:
            self.variables["client_name"] = "".join(client)
            system_str = self.prompt_manager.get_prompt("select_client", 0, self.variables)
        else:
            self.variables["client_name"] = "、".join(client)
            self.variables["client_name_space"] = "  ".join(client)
            system_str = self.prompt_manager.get_prompt("select_client", 1, self.variables)
        return system_str, None

    def __set_patient(self):
        if self.flag == 11:
            system_str = self.prompt_manager.get_prompt("patient", 0, self.variables)
        else:
            system_str = self.prompt_manager.get_prompt("patient", 1, self.variables)
        return system_str, None

    def __set_patient_optimize(self):
        system_str = self.prompt_manager.get_prompt("patient_optimize", 0, self.variables)
        return system_str, None

    def __set_gender_age(self):
        system_str = self.prompt_manager.get_prompt("gender_age", 0, self.variables)
        return system_str, None

    def __set_guardian(self):
        system_str = self.prompt_manager.get_prompt("guardian", 0, self.variables)
        return system_str, None

    def __set_modify_client(self):
        system_str = self.prompt_manager.get_prompt("modify_client", 0, self.variables)
        return system_str, None