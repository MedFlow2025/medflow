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
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import ValidationError
from fastapi import HTTPException

class BasicMedicalRecordProcessChecker:
    def __init__(self, receive) -> None:
        self.bmr = receive.output.basic_medical_record 

    def __check_chief_complaint(self):
        return any(getattr(self.bmr, attr) in ["", None] for attr in
            ['chief_complaint', 'history_of_present_illness', 'past_medical_history', 'personal_history', 'allergy_history'])

    def check(self):
        if self.__check_chief_complaint(): return 21
        else: return 2 

class BasicMedicalRecordRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None,
                 ):
        super().__init__(receive, args, scheme, sub_scheme,request_type)
        try:
            self.receive = RequestV2(**receive)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    def checker_flag(self):
        self.checker = BasicMedicalRecordProcessChecker(self.receive)
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptBasicMedicalRecord', self.receive)
        self.prompt.set_prompt()

    def postprocess(self, messages):
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re in answers:
            answer+=re
            yield re
        results = self.postprocess_bmr(self.receive, answer, self.flag)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_bmr(self, receive, answer, flag):
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

        basicMedicalRecord = params.output.basic_medical_record

        match flag:
            case 21|2:
                basicMedicalRecord.chief_complaint=json_data['主诉']
                basicMedicalRecord.history_of_present_illness=json_data['现病史']
                basicMedicalRecord.past_medical_history=json_data['既往史']
                basicMedicalRecord.personal_history=json_data['个人史']
                basicMedicalRecord.allergy_history=json_data['过敏史']

                answer = self.format_basic_medical_record(json_data, text_match)
                hc.pop()
                hc.append(HistoricalConversations(role='assistant', content=answer))
        return params

    def format_basic_medical_record(self, json_data, text_match):
        #answer = f"""{text_match}
        answer = f"""依据您回复的情况，已经为您生成了预问诊报告，如无问题，请点击确认，如还需要补充请直接回复补充。
主诉: {json_data['主诉']}
现病史: {json_data['现病史']}
既往史: {json_data['既往史']}
个人史: {json_data['个人史']}
过敏史: {json_data['过敏史']}
"""
        return answer
