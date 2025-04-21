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

import re
import json
from bs4 import BeautifulSoup
from ..prompt_template import *
from ..util_data_models import DoctorMedicalRecord
from fastapi import HTTPException

@register_prompt
class PromptDoctorMedicalRecord_v2(PromptTemplate):
    def __init__(self, receive, scheme) -> None:
        super().__init__()
        self.yaml_name = "doctormedicalrecord_v2.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)
        self.medical_templet = receive.input.medical_templet
        self.templet_type = receive.input.templet_type
        self.doctor_supplement = receive.input.doctor_supplement
        self.scheme = scheme
        self.medical_fields = medical_fields
        self.sub_medical_fields = sub_medical_fields
        self.bmr = receive.input.basic_medical_record
        if self.medical_templet != None:
            self.bmr = receive.input.basic_medical_record = self.__extract_medical_from_tmplet(receive.input.basic_medical_record)
        self.reversed_medical_fields = reversed_medical_fields
        self.reversed_sub_medical_fields = reversed_sub_medical_fields

    def __match_fields(self, text, fields):
        pattern = '|'.join([f"{field}[:：]" for field in fields.keys()])
        regex = re.compile(f"({pattern})")
        matches = list(regex.finditer(text))
        return matches

    def __extract_medical_from_tmplet(self, basic_medical_record):
        result = {field: ("" if field is not "physical_examination" else {f: "" for f in self.sub_medical_fields.values()}) for field in self.medical_fields.values()}
        if self.templet_type == "1":
            text = self.medical_templet
        elif self.templet_type == "2":
            soup = BeautifulSoup(self.medical_templet, 'html.parser')
            soup_list = soup.find_all('p')
            soup_list = [tag.text for tag in soup_list]
            text = "".join(soup_list)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid Parameter: templet_type must be equal to 1 or 2.")

        matches = self.__match_fields(text, self.medical_fields)
        for index, value in enumerate(matches):
            current_field = re.sub(r"[:：]$", "", matches[index].group())
            start = matches[index].end()
            end = matches[index+1].start() if index+1 < len(matches) else len(text)
            if current_field != "体格检查":
                input_content = getattr(basic_medical_record, self.medical_fields.get(current_field))
                content = input_content if input_content else text[start:end].strip(",\"\n")
                result[self.medical_fields.get(current_field)] = content if content != "" else "无"
            else:
                content = text[start:end].strip(",\"\n")
                sub_matches = self.__match_fields(content, self.sub_medical_fields)
                for i, v in enumerate(sub_matches):
                    sub_current_field = re.sub(r"[:：]$", "", sub_matches[i].group())
                    sub_start = sub_matches[i].end()
                    sub_end = sub_matches[i+1].start() if i+1 < len(sub_matches) else len(content)
                    sub_input_content = getattr(basic_medical_record.physical_examination, self.sub_medical_fields.get(sub_current_field))
                    sub_content = sub_input_content if sub_input_content else content[sub_start:sub_end].strip(",\"\n")
                    result[self.medical_fields.get(current_field)][self.sub_medical_fields.get(sub_current_field)] = sub_content if sub_content != "" else "无"
        return DoctorMedicalRecord.parse_obj(result)

    def set_prompt(self):
        self.prompt = {
            "9": self.__set_doctor_medical_record()
        }
        return self.prompt

    def __set_doctor_medical_record(self):
        text = json.loads(self.bmr.json())
        medical = ""
        medical_json = {}
        if self.medical_templet is not None:
            for key, value in text.items():
                if not isinstance(value, dict):
                    medical += f"{self.reversed_medical_fields.get(key)}：{value}\n" if value != "" else ""
                    medical_json.update({self.reversed_medical_fields.get(key): ""}) if value != "" else None
                else:
                    if not all(v == "" for v in value.values()):
                        medical += f"{self.reversed_medical_fields.get(key)}：\n"
                        medical_json.update({self.reversed_medical_fields.get(key): {}})
                        for k, v in value.items():
                            medical += f"  {self.reversed_sub_medical_fields.get(k)}：{v}\n" if v != "" else ""
                            medical_json[self.reversed_medical_fields.get(key)].update({self.reversed_sub_medical_fields.get(k): ""}) if v != "" else None
        else:
            for key, value in text.items():
                if not isinstance(value, dict):
                    medical += f"{self.reversed_medical_fields.get(key)}：{value}\n"
                    medical_json.update({self.reversed_medical_fields.get(key): ""})
                else:
                    medical += f"{self.reversed_medical_fields.get(key)}：\n"
                    for k, v in value.items(): medical += f"  {self.reversed_sub_medical_fields.get(k)}：{v}\n"
                    medical_json.update({self.reversed_medical_fields.get(key): {self.reversed_sub_medical_fields.get(k): "" for k in value.keys()}})

        self.variables = {
            "doctor_supplement": self.doctor_supplement,
            "medical": medical,
            "medical_json": medical_json
        }
        match self.scheme:
            case "general":
                system_str = self.prompt_manager.get_prompt("general", 0, self.variables)
            case "special":
                system_str = self.prompt_manager.get_prompt("special", 0, self.variables)
            case "special_modify":
                system_str = self.prompt_manager.get_prompt("special", 0, self.variables)
            case "special_select":
                system_str = self.prompt_manager.get_prompt("special_select", 0, self.variables)
            case _:
                raise HTTPException(status_code=400, detail=f"Invalid Parameter: scheme must be equal to general, special, special_modify or special_select.")
        return system_str, None