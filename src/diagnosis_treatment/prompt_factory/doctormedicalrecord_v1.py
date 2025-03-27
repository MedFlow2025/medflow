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

@register_prompt
class PromptDoctorMedicalRecord_v1(PromptTemplate):
    def __init__(self, receive, scheme) -> None:
        super().__init__()
        self.medical_templet = receive.input.medical_templet
        self.templet_type = receive.input.templet_type
        self.doctor_supplement = receive.input.doctor_supplement
        self.scheme = scheme
        self.fields = medical_fields
        self.bmr = receive.input.basic_medical_record = self.__extract_medical_from_tmplet()
        self.reversed_fields = {value: key for key, value in self.fields.items()}

    def __extract_medical_from_tmplet(self):
        result = {field: "" for field in self.fields.values()}
        if self.templet_type == "1":
            text = self.medical_templet
        elif self.templet_type == "2":
            soup = BeautifulSoup(self.medical_templet, 'html.parser')
            soup_list = soup.find_all('p')
            soup_list = [tag.text for tag in soup_list]
            text = "".join(soup_list)
        else:
            raise ValueError(f"Invalid templet_type: {self.templet_type}")

        pattern = '|'.join([f"{field}[:：]" for field in self.fields.keys()])
        regex = re.compile(f"({pattern})")
        matches = list(regex.finditer(text))
        for index, value in enumerate(matches):
            current_field = re.sub(r"[:：]$", "", matches[index].group())
            start = matches[index].end()
            end = matches[index+1].start() if index+1 < len(matches) else len(text)
            content = text[start:end].strip(",\"\n")
            result[self.fields.get(current_field)] = content
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
        for key, value in text.items():
            if value != "":
                medical += f"{self.reversed_fields.get(key)}：{value}\n"
                medical_json.update({self.reversed_fields.get(key): ""})

        match self.scheme:
            case "text":
                system_str=f"""#Role:
专业医生
## Profile
-description: 你是一个优秀的专业医生，主要工作是按任务要求对病历进行补充或修改，并以json格式返回重新生成的病历。
## Skills
1.具备扎实的医疗知识，掌握病历书写的标准规则。
2.主诉只需要填写最主要的症状和持续时间即可，不要超过10个字。
3.现病史需要填写患者本次患病后全过程，包括发生、发展和诊治经过。如果患者表示没有某种症状时，记录为“否认xxx”，注意不要遗漏任何细节。
## MedicalRecord 
{medical}
## Tasks
-任务要求：“{self.doctor_supplement}”
## Initialization:
作为<Role>，任务为<Profile>，拥有<Skills>技能，待修改的病历为<MedicalRecord>，按<Tasks>中的任务要求对病历进行修改，\
并严格按照json格式返回，例如：
{medical_json}。
重新生成病历时先说“现在为您返回修改后的病历：”。
注意，<Tasks>中的描述通常会是口语化描述，你需要将口语化的描述转换成简洁、正式、专业的医学术语。"""
            case "template":
                system_str=f"""#Role:
专业医生

## Profile
你是一个优秀的专业医生，主要工作是按任务要求中的描述填写病历记录，病历记录采取下面的病历模板，只能修改括号里的内容，括号需要保留。\
请完全理解任务要求中描述内容后填写并输出，不要遗漏任何细节。注意纠正可能的语音识别错误。数值都采用阿拉伯数字表示。

## Template
{medical}

## Tasks
-任务要求：“{self.doctor_supplement}”

## Initialization:
作为<Role>，任务为<Profile>，病历模板为<Template>，按<Tasks>中的任务要求对病历模板进行补充，并严格按照json格式返回，例如：
{medical_json}。
返回补充完的病历时先说“现在为您返回补充后的病历：”。
注意，返回的病历中要保留括号。"""
            case "select":
                system_str=f"""#Role:
专业医生

## Profile
你是一个优秀的专业医生，主要工作是按任务要求中的描述填写病历记录，病历记录采取下面的病历模板，只能修改括号里的内容，括号需要保留。\
如果括号中已经填写了内容，代表是选择题，你需要按照任务要求中的描述，挑选出一个进行填空，注意，括号中只能保留一个。\
请完全理解任务要求中描述内容后填写并输出，不要遗漏任何细节。注意纠正可能的语音识别错误。数值都采用阿拉伯数字表示。

## Template
{medical}

## Tasks
-任务要求：“{self.doctor_supplement}”

## Initialization:
作为<Role>，任务为<Profile>，病历模板为<Template>，按<Tasks>中的任务要求对病历模板进行补充，并严格按照json格式返回，例如：
{medical_json}。
返回补充完的病历时先说“现在为您返回补充后的病历：”。
注意，返回的病历中要保留括号。"""
            case _:
                system_str=""
        return system_str, None