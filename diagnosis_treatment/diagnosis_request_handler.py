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
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, insert, select, text)
from .base_diagnosis_request_handler import BaseDiagnosisRequestHandler
from .prompt_template import *
from .util_data_models import *
from .util_sqlite_function import *
from .util import *
import io
from fastapi.responses import StreamingResponse, JSONResponse

class ProcessCheckerDN:
    def __init__(self) -> None:
        pass

    def check(self):
        return 41

class DiagnosisRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None,
                 ):
        super().__init__(receive, args, scheme, sub_scheme,request_type)
        self.receive = RequestV4(**receive)
        self.db_engine = create_engine(f"sqlite:///{self.args.database}/medical_assistant.db")

    def checker_flag(self):
        self.checker = ProcessCheckerDN()
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptDiagnosis', self.receive)
        self.prompt.set_prompt()
        
    def postprocess(self, answer):
        results = self.postprocess_dn(self.receive, answer, self.flag)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_dn(self, receive, answer, flag):
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

        match flag:
            case 41:
                if '诊断' in json_data and json_data['诊断']:
                    diagnose_item = []
                    for item in json_data['诊断']:
                        query_item = item['诊断名称']
                        query_result = query_fastbm25(self.database, query_item, "diagnosis")
                        if self.args.fastbm25 and query_result:
                            query_item = query_result[0][0]
                            sql_str = f"SELECT id, diagnosis_code, diagnosis_name, COALESCE(alias, diagnosis_name) \
                                AS name FROM diagnosis_info WHERE name=\"{query_item}\""
                            search_result = search_database(self.db_engine, sql_str)
                            diagnose_item.append(Diagnosis(
                                diagnosis_name=item['诊断名称'],
                                diagnosis_name_retrieve=search_result[0][2],
                                diagnosis_code=search_result[0][1],
                                diagnosis_identifier=item['诊断标识']
                            ))
                        else:
                            diagnose_item.append(Diagnosis(
                                diagnosis_name=item['诊断名称'],
                                diagnosis_name_retrieve="",
                                diagnosis_code=item['诊断编码'],
                                diagnosis_identifier=item['诊断标识']
                            ))
                    params.output.diagnosis = diagnose_item
                    answer = self.format_diagnose(json_data, text_match)
                    hc.pop()
                    hc.append(HistoricalConversations(role='assistant', content=answer))
        return params    

    def format_diagnose(self, json_data, text_match):
        answer = f"""{text_match}"""
        if '诊断' in json_data and json_data['诊断']:
            for item in json_data['诊断']:
                answer+=f"""
【{item['诊断名称']}  {item['诊断标识']}】"""
        return answer
