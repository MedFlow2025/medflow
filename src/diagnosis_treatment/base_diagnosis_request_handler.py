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

from abc import ABC, abstractmethod
import copy
from openai import OpenAI
from .prompt_template import *
from .util_data_models import *
from fastapi.responses import StreamingResponse, JSONResponse

class BaseDiagnosisRequestHandler(ABC):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None
                 ):
        self.receive = receive
        self.args = args
        self.openai_api_key = args.api_key
        self.openai_base_url = args.model_url
        self.model = args.model
        self.database = args.database
        self.scheme = scheme
        self.sub_scheme = sub_scheme
        self.temprature = 0
        self.top_p = 1
        #self.args = args_parser()
        self.checker = None
        self.flag = None
        self.prompt = None
        self.messages = None
        self.answer = None
        self.results = None
        self.request_type = request_type

    @abstractmethod
    def checker_flag(self):
        pass

    @abstractmethod
    def generate_prompt(self):
        pass

    @abstractmethod
    def postprocess(self, answer):
        pass

    def handle_history_chat(self, hc_bak):
        if bool(hc_bak):
            stop_list = []
            for k, v in enumerate(hc_bak):
                for i in stop_sign:
                    stop_list.append(k) if i in v.content else None
            if bool(stop_list):
                hc_bak = hc_bak[stop_list[-1]+1:]
        #print(f"推理输入对话: {hc_bak=}")

        return hc_bak

    def preprocess(self, receive, prompt, flag):
        params = copy.deepcopy(receive)
        hc = params.chat.historical_conversations
        hc_bak = params.chat.historical_conversations_bak

        if hc != [] and hc[-1].role == 'user':
            hc_bak.append(HistoricalConversations(role='user', content=hc[-1].content))
        infer_hc = self.handle_history_chat(hc_bak)

        prompt_content = prompt.get_prompt(flag)
        messages=[{"role": "system", "content": prompt_content[0]}]

        current_round = len(infer_hc)
        #irrelevant = 0
        #for v in infer_hc:
        #    if irrelevant_content in v.content:
        #        irrelevant+=1
        #current_round-=(irrelevant*2)
        match flag:
            case 0|11:
                for item in infer_hc:
                    messages.append({'role': item.role, 'content': item.content})
            case 33:
                for item in infer_hc:
                    messages.append({'role': item.role, 'content': item.content})
                for item in messages:
                    if item['role'] == "user":
                        item['content'] += multi_agent_prompt
                        break
            case 12:
                for item in infer_hc:
                    messages.append({'role': item.role, 'content': item.content})
                for item in messages:
                    if item['role'] == "user":
                        item['content'] += multi_agent_prompt
                        break
                if len(infer_hc) != 0:
                    if infer_hc[0].role == "assistant":
                        for k, v in enumerate(infer_hc):
                            round = k + 1
                            if round >= 12 and round % 6 == 0:
                                messages[round]['content'] = messages[round]['content'].replace(single_add_prompt, '') + irrelevant_content
                    elif infer_hc[0].role == "user":
                        for k, v in enumerate(infer_hc):
                            round = k + 1
                            if (round >= 11) and ((round+1) % 6 == 0):
                                messages[round]['content'] = messages[round]['content'].replace(single_add_prompt, '') + irrelevant_content
            case 14|15|1|2:
                for item in infer_hc:
                    messages.append({'role': item.role, 'content': item.content})
                for item in messages:
                    if item['role'] == "user":
                        item['content'] += multi_agent_prompt
                        break
                if len(infer_hc) != 0:
                    if infer_hc[0].role == "assistant":
                        for k, v in enumerate(infer_hc):
                            round = k + 1
                            if round % 6 == 0:
                                messages[round]['content'] = messages[round]['content'].replace(single_add_prompt, '') + irrelevant_content
                    elif infer_hc[0].role == "user":
                        for k, v in enumerate(infer_hc):
                            round = k + 1
                            if ((round+1) % 6 == 0):
                                messages[round]['content'] = messages[round]['content'].replace(single_add_prompt, '') + irrelevant_content
            case 8:
                for item in infer_hc:
                    if item.role == "user":
                        messages.append({'role': item.role, 'content': item.content + single_add_prompt})
                    elif item.role == "assistant":
                        messages.append({'role': item.role, 'content': item.content})
            case 21|7:
                for item in infer_hc:
                    if item.role == "user":
                        messages.append({'role': item.role, 'content': item.content + single_add_prompt})
                    elif item.role == "assistant":
                        messages.append({'role': item.role, 'content': item.content})
                for item in messages:
                    if item['role'] == "user":
                        item['content'] += multi_agent_prompt
                        break
                if current_round >= self.args.max_round:
                    #print(f"\n当前轮次: {current_round}, 将自动生成病历:")
                    last_round = messages.pop(-1)
                    last_role = last_round['role']
                    last_content = last_round['content'].replace(single_add_prompt, '') + single_max_round
                    messages.append({'role': last_role, 'content': last_content})
                if len(infer_hc) != 0:
                    if infer_hc[0].role == "assistant":
                        for k, v in enumerate(infer_hc):
                            round = k + 1
                            if round >= 12 and round % 6 == 0:
                                messages[round]['content'] = messages[round]['content'].replace(single_add_prompt, '') + irrelevant_content
                    elif infer_hc[0].role == "user":
                        for k, v in enumerate(infer_hc):
                            round = k + 1
                            if (round >= 11) and ((round+1) % 6 == 0):
                                messages[round]['content'] = messages[round]['content'].replace(single_add_prompt, '') + irrelevant_content
            case 4|5|6:
                messages.append({"role": "user", "content": prompt_content[1]})
            case _:#31|32|9
                pass
        #print(f"初始prompt: {messages=}\n")

        return messages
    
    def predict(self, messages, temp:float=0, top_p:float=1):
        client = OpenAI(api_key=self.openai_api_key, base_url=self.openai_base_url)
        chat_response = client.chat.completions.create(
            model= self.model,
            messages=messages,
            temperature=temp,
            top_p=top_p,
            max_tokens=1024,#8192
            stream=False,#True
            stop="<|eot_id|>",
        )
        '''
        answer=""
        for chunk in chat_response:
            if chunk.choices[0].delta.content is not None:
                answer+=(chunk.choices[0].delta.content or "")
        '''
        answer=chat_response.choices[0].message.content
        #print(f"对话结果: {answer=}")
        return answer
    
    def predict_stream(self, messages, temp:float=0, top_p:float=1):
        client = OpenAI(api_key=self.openai_api_key, base_url=self.openai_base_url)
        chat_response = client.chat.completions.create(
            model= self.model,
            messages=messages,
            temperature=temp,
            top_p=top_p,
            max_tokens=1024,
            stream=True,
            stop="<|eot_id|>",
        )
        
        for chunk in chat_response:
            if chunk.choices[0].delta.content is not None:
                #print(f"{chunk.choices[0].delta.content=}")
                yield chunk.choices[0].delta.content
        return

    def handle_request(self):
        self.checker_flag()

        messages = []
        if self.request_type != "v3":
            self.generate_prompt()
            messages = self.preprocess(self.receive, self.prompt, self.flag)

        if self.request_type in ["v0", "v1", "v2", "v3", "v7", "v8"]:
            self.results = self.postprocess(messages)
        else:
            answer = self.predict(messages, self.temprature, self.top_p)
            self.results = self.postprocess(answer)
        return StreamingResponse(self.results, media_type="application/json")
