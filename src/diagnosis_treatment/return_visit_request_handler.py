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

class ReturnVisitProcessChecker:
    def __init__(self, receive) -> None:
        pass

    def check(self) -> int:
        return 7


class ReturnVisitRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None,
                 sub_scheme : None,
                 request_type: None
                 ):
        super().__init__(receive, args, scheme, sub_scheme, request_type)
        self.receive = RequestV7(**receive)

    def checker_flag(self):
        self.checker = ReturnVisitProcessChecker(self.receive)
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptReturnVisit', self.receive)
        self.prompt.set_prompt()
    
    def postprocess(self, messages):
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re in answers:
            answer+=re
            yield re
        #answer = self.predict(messages, self.temprature, self.top_p)
        results = self.postprocess_rv(self.receive, answer, self.flag)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_rv(self, receive, answer, flag):
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
            case 7:
                return_visit = params.output.return_visit
                return_visit.summary = json_data['病情总结']
                return_visit.if_visit = json_data['是否复诊']
                answer = self.format_return_visit(json_data, text_match)
                hc.pop()
                hc.append(HistoricalConversations(role='assistant', content=answer))

        return params

    def format_return_visit(self, json_data, text_match):
        answer = f"""{text_match}
病情总结: {json_data['病情总结']}
是否复诊：{json_data['是否复诊']}"""
        return answer