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

import copy
from .base_diagnosis_request_handler import BaseDiagnosisRequestHandler
from .prompt_template import *
from .util_data_models import *
from .util import *
import io
from pydantic import ValidationError
from fastapi import HTTPException

class DoctorMedicalRecordProcessChecker:
    def __init__(self) -> None:
        pass

    def check(self) -> int:
        return 9

class DoctorMedicalRecordRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None,
                 sub_scheme : None,
                 request_type: None
                 ):
        super().__init__(receive, args, scheme, sub_scheme, request_type)
        try:
            self.receive = RequestV9(**receive)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    def checker_flag(self):
        self.checker = DoctorMedicalRecordProcessChecker()
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptDoctorMedicalRecord', self.receive, self.scheme)
        self.prompt.set_prompt()

    def postprocess(self, answer):
        results = self.postprocess_dmr(self.receive, answer, self.scheme)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_dmr(self, receive, answer, scheme):
        params = copy.deepcopy(receive)
        hc = params.chat.historical_conversations
        hc_bak = params.chat.historical_conversations_bak
        if hc != [] and hc[-1].role == 'user':
            hc_bak.append(HistoricalConversations(role='user', content=hc[-1].content))
        hc.append(HistoricalConversations(role='assistant', content=answer))
        hc_bak.append(HistoricalConversations(role='assistant', content=answer))

        json_match, text_match = extract_json_and_text(answer)
        if not isinstance(json_match, re.Match):
            return params
        else:
            try:
                json_data = json_match.group(0)
                json_data = eval(json_data)
                # print(f"大模型匹配内容: \n{json_data=}\n")
            except:
                print("Error: There is no matching json data.")
                return params

        medical_format = ""
        if receive.input.medical_templet != None:
            templet_type = receive.input.templet_type
            if templet_type == "1":
                for key, value in json_data.items():
                    if not isinstance(value, dict):
                        medical_format += f"{key}:{value}\n"
                    else:
                        medical_format += f"{key}:\n"
                        for k, v in value.items(): medical_format += f"  {k}: {v}\n"
            elif templet_type == "2":
                for key, value in json_data.items():
                    if not isinstance(value, dict):
                        medical_format += f"<p>{key}:{value}</p>"
                    else:
                        sub_value = ""
                        for k, v in value.items(): sub_value += f"  {k}: {v}"
                        medical_format += f"<p>{key}:{sub_value}</p>"
                medical_format = "<div><h2>病历</h2>" + medical_format + "</div>"
            else:
                raise HTTPException(status_code=400, detail=f"Invalid Parameter: templet_type must be equal to 1 or 2.")
        else:
            for key, value in json_data.items():
                if not isinstance(value, dict):
                    if value == "": value = "无"
                    medical_format += f"{key}:{value}\n"
                else:
                    medical_format += f"{key}:\n"
                    for k, v in value.items(): medical_format += f"  {k}: {v}\n"

        medical = {medical_fields.get(key): (value if not isinstance(value, dict) 
            else {sub_medical_fields.get(k): v for k, v in value.items()}) for key, value in json_data.items()}
        basicMedicalRecord = DoctorMedicalRecord.parse_obj(medical)
        params.output.medical_format = medical_format
        params.output.basic_medical_record = basicMedicalRecord

        answer = self.format_basic_medical_record(json_data, text_match)
        hc.pop()
        hc.append(HistoricalConversations(role='assistant', content=answer))

        return params

    def format_basic_medical_record(self, json_data, text_match):
        #answer = f"""{text_match}
        answer = "依据您回复的情况，已经为您生成了病历，如无问题，请点击确认，如还需要补充请直接回复补充。"
        for key, value in json_data.items():
            if not isinstance(value, dict):
                answer += f"【{key}】：{value}\n"
            else:
                answer += f"【{key}】\n"
                for k, v in value.items(): answer += f"  {k}: {v}\n"
        return answer