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

class DistributeProcessChecker:
    def __init__(self, receive) -> None:
        pass

    def check(self) -> int:
        return 0


class DistributeRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None,
                 sub_scheme : None,
                 request_type: None
                 ):
        super().__init__(receive, args, scheme, sub_scheme, request_type)
        try:
            self.receive = RequestV0(**receive)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    def checker_flag(self):
        self.checker = DistributeProcessChecker(self.receive)
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptDistribute', self.receive)
        self.prompt.set_prompt()
    
    def postprocess(self, messages):
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re in answers:
            answer+=re
            yield re
        results = self.postprocess_d(self.receive, answer, self.flag)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_d(self, receive, answer, flag):
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
            case 0:
                distritube_item = []
                for item in json_data:
                    distritube_item.append(PatientNeed(
                        need=item['患者意图']
                    ))
                params.output.patient_need = distritube_item
                answer = self.format_distribute(json_data, text_match)
                hc.pop()
                hc.append(HistoricalConversations(role='assistant', content=answer))

        return params

    def format_distribute(self, json_data, text_match):
        #answer = text_match
        answer = "好的，了解了。我将为您转接到如下智能助手："
        for item in json_data:
            answer+=f"""
【{item['患者意图']}】"""
        return answer