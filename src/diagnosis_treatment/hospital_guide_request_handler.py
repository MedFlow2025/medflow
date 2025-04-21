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
from sqlalchemy import create_engine
from .base_diagnosis_request_handler import BaseDiagnosisRequestHandler
from .prompt_template import *
from .util_data_models import *
from .util_sqlite_function import *
from .util import *
import io
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import ValidationError
from fastapi import HTTPException

class HospitalGuideProcessChecker:
    def __init__(self, receive) -> None:
        pass

    def check(self) -> int:
        return 8

class HospitalGuideRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None,
                 sub_scheme : None,
                 request_type: None
                 ):
        super().__init__(receive, args, scheme, sub_scheme, request_type)
        try:
            self.receive = RequestV8(**receive)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
        self.db_engine = create_engine(f"sqlite:///{self.args.database}/medical_assistant.db")

    def checker_flag(self):
        self.checker = HospitalGuideProcessChecker(self.receive)
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptHospitalGuide', self.receive, self.db_engine, self.scheme, self.args.department_path)
        self.prompt.set_prompt()

    def postprocess(self, messages):
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re in answers:
            answer+=re
            yield re
        #answer = self.predict(messages, self.temprature, self.top_p)
        results = self.postprocess_hg(self.receive, answer, self.scheme)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_hg(self, receive, answer, scheme):
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

        match scheme:
            case "simple":
                if '病历' in json_data and json_data['病历']:
                    params.output.basic_medical_record.chief_complaint = json_data['病历']['主诉']

                if '推荐科室' in json_data and json_data['推荐科室']:
                    department_item = []
                    all_department = [{"department_id":v.department_id, "department_name":v.department_name} for v in self.receive.input.all_department]
                    for item in json_data['推荐科室']:
                        query_item = item['科室名称']
                        search_result = list(filter(lambda item: query_item in item['department_name'], all_department))
                        if search_result:
                            department_item.append(Department(
                                department_id=search_result[0]['department_id'],
                                department_name=search_result[0]['department_name']
                            ))
                        else:
                            department_item.append(Department(
                                department_id=item['科室编号'],
                                department_name=item['科室名称']
                            ))
                    params.output.chosen_department = department_item
                    answer = self.format_department(json_data, text_match)
                    hc.pop()
                    hc.append(HistoricalConversations(role='assistant', content=answer))

            case "detailed":
                params.output.basic_medical_record.chief_complaint = json_data['主诉']
                params.output.basic_medical_record.history_of_present_illness = json_data['现病史']
                params.output.basic_medical_record.past_medical_history = json_data['既往史']
                params.output.basic_medical_record.personal_history = json_data['个人史']
                params.output.basic_medical_record.allergy_history = json_data['过敏史']

                answer = self.format_basic_medical_record(json_data, text_match)
                hc.pop()
                hc.append(HistoricalConversations(role='assistant', content=answer))
 
        return params

    def format_department(self, json_data, text_match):
        #answer = text_match
        answer = "患者病情："
        if '病历' in json_data and json_data['病历']:
            answer += f"""
【主诉】: {json_data['病历']['主诉']}
"""
        if '推荐科室' in json_data and json_data['推荐科室']:
            answer += "\n推荐科室："
            for item in json_data['推荐科室']:
                answer+=f"""
【{item['科室名称']}】"""
        return answer

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
