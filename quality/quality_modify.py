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
import re
from typing import Any, Dict, List, Union

from fastapi import HTTPException
from .quality_common_ds import PhyscialExamination, BasicMedicalRecord, ControlQuality, HistoricalConversations, QualityAPIRequest, DebugPrompt, QualityAPIResponse, QualityAPIRequestInput, QualityAPIResponseOutput, HistoricalConversation
from .quality_common_ds import qc_map_chinese_to_english_physcial_examination, qc_map_chinese_to_english, modify_control_quality_data, map_cn_key_to_en_key
# import quality_common_ds

import json
from openai import OpenAI, AsyncOpenAI
import asyncio
from pydantic import BaseModel, Field, ValidationError


class QualityModify:
    def __init__(self, input_request: QualityAPIRequest, 
        historical_conversations: HistoricalConversations,
        openai_api_key: str,
        openai_api_base: str,
        model_name : str,
        async_client : AsyncOpenAI | None,
    ):
        self.input_request = input_request
        self.openai_api_key = openai_api_key
        self.openai_api_base = openai_api_base
        self.model_name = model_name
        self.historical_conversations = historical_conversations
        
        if async_client is None:
            self.async_client = AsyncOpenAI(api_key = openai_api_key, base_url = openai_api_base)
        else:
            self.async_client = async_client
        self.control_quality = self.input_request.control_quality
        
        self.stop_sign = [
            '为您生成检查结果',
            '为您重新生成病历'
        ]
        self.kong_str = "空"
        self.format_inspect = """{
    "质检结果": ""
}
"""
        #病历
        self.format_case="""{
"病历": {
    "主诉": "",
    "现病史": "",
    "既往史": "",
    "个人史": "xxx;xxx",
    "过敏史": "",
    "体格检查": {
        "体温": "value ℃",
        "脉搏": "value 次/分",
        "血压": "value mmHg",
        "呼吸": "value 次/分"
    },
    "辅助检查": ""
}
}
"""

        self.QUALITY_NO_ABNORM = "无异常"
        self.QUALITY_NO_PASS = "不通过"
        pe = self.input_request.basic_medical_record.physical_examination
        self.physical_examination = (
            f"体温:{pe.temperature or self.kong_str}; 脉搏:{pe.pulse or self.kong_str};"
            f"血压:{pe.blood_pressure or self.kong_str}; 呼吸:{pe.respiration or self.kong_str};"
        )
        self.temperature = pe.temperature or self.kong_str
        self.pulse = pe.pulse or self.kong_str
        self.blood_pressure = pe.blood_pressure or self.kong_str
        self.respiration = pe.respiration or self.kong_str
        
        self.auxiliary_examination = self.input_request.basic_medical_record.auxiliary_examination or self.kong_str
        self.handle_control_quality = self.__handle_control_quality()

    def handle_history_chat(self, history_chat):
        if bool(history_chat):
            stop_list = []
            for k, v in enumerate(history_chat):
                for i in self.stop_sign:
                    stop_list.append(k) if i in v.content else None
            if bool(stop_list):
                history_chat = history_chat[stop_list[-1]+1:]
        return history_chat

    def __handle_control_quality(self):
        problem_list = list()
        
        if self.control_quality is None or len(self.control_quality) == 0:
            return self.QUALITY_NO_ABNORM
        
        problem_list = [(item.item + item.check_quality.replace(self.QUALITY_NO_PASS, "").lstrip()) for item in self.control_quality if item.check_quality != "" and "无异常" not in item.check_quality]
        problem_dict = dict()
        for i, v in enumerate(problem_list):
            problem_dict[f"问题{i+1}"] = v
        problem_dict = str(problem_dict).replace("{", "").replace("}", "。").replace("\'", "").replace(";", "").replace("问题", "\n问题")
        return problem_dict
    
    def __get_quality_modify_message(self):
        #92-质检对话修改病历
        system_str=f"""
#Role
病历质检员
## Profile
-description: 你的工作是按照待询问的问题与医生进行多轮沟通，沟通完成后重新生成病历。
## Skills
具备扎实的医疗知识，掌握病历书写的标准规则。
## Medical Record
主诉：{self.input_request.basic_medical_record.chief_complaint}。
现病史：{self.input_request.basic_medical_record.history_of_present_illness  or self.kong_str}。
既往史：{self.input_request.basic_medical_record.past_medical_history or self.kong_str}。
个人史：{self.input_request.basic_medical_record.personal_history or self.kong_str}。
过敏史：{self.input_request.basic_medical_record.allergy_history or self.kong_str}。
体格检查：{self.physical_examination}。
辅助检查：{self.auxiliary_examination}。
## Problems
{self.handle_control_quality}
## Workflow
1.按照<Problems>中的问题，依次向医生进行询问，每次只能提问一个问题，例如：“当前的问题是：xxx，请问xxx？”。
2.检查<Problems>中的问题是否全部都向医生进行了提问。如果没有就直接向医生提问下一个问题。
3.根据的病历修改意见，重新生成病历。重新生成病历时先说“我已按照您的要求修改了病历，现在为您重新生成病历：”。\
病历的格式为json格式，例如：{self.format_case}。病历生成结束后，说“请确认病历信息是否准确，如果正确请回复“正确”，\
如果不正确请回复需要修改的内容。”。注意：体温、脉搏、血压、呼吸都记录到体格检查。
4.如果医生表示有其他需要修改的内容，按照医生的要求重新生成病历，病历的格式为json格式，例如：{self.format_case}。
## Initialization :
作为 <Role>，拥有<Skills>技能，病历为<Medical Record>，待询问的问题有<Problems>，按<Workflow>的顺序和医生对话。"""
        user_str=f"""请开始进行进行提问。"""
        messages=[{"role": "system", "content":system_str}]


        hc = copy.deepcopy(self.historical_conversations)
        stop_list = []
        if hc is not None:
            for k, v in enumerate(hc):
                stop_list.append(k) if self.stop_sign[-1] in v.content else None
            infer_hc = self.handle_history_chat(hc)
        if not bool(stop_list):
            messages.append({"role": "user", "content": user_str})
        if hc is not None:    
            for i in infer_hc:
                messages.append({'role': i.role, 'content': i.content})
        return messages

    def extract_json_data(self, partial_message:str) ->  Union[str, dict]: 
        """_summary_
        input case:
            我已经按照您的要求检查了病历，现在为您生成异常项：
            {
                "'病历'": ""
            }
        或者，只有chat信息，没有病例信息
        
        Args:
            partial_message (_type_): input answer  str

        Returns:
            str: quality result  
        """
        '''
        # remove \n \t " "
        cleaned_message = partial_message.replace("\n", "").replace("\t", "").replace(" ", "")  
        
        # define JSON  format regular expression  
        case_format_6 = r'\{(.*?)\}'
        
        # find use case_format_6 
        case_search = re.search(case_format_6, cleaned_message, re.DOTALL)  
        '''
        
        case_format_6 = r'{(.*?)}}'
        case_format_1 = r'{(.*?)}'
        partial_message_2 = partial_message.replace("\n", "").replace("\t", "").replace(" ", "")
        case_search = re.search(case_format_6, partial_message_2, re.DOTALL)
        if not case_search:
            case_search = re.search(case_format_1, partial_message_2, re.DOTALL)
        
        try:  
            # json.loads Parse string  
            # case_data = json.loads(case_search.group(0))  
            if isinstance(case_search, re.Match):
                case_data = case_search.group(0)
                case_data = eval(case_data)
            
            return case_data['病历']
                       
        except json.JSONDecodeError:  
            return None  
        except Exception as e:
            return None  


    def confirm_auto_modify_request(self)-> QualityAPIResponse:
        if len(self.input_request.control_quality) == 0:
            raise HTTPException(status_code = 422, detail="no control_quality info, request must give control_quality") 
        response = QualityAPIResponse.from_request(self.input_request) 
        
        if ":" in self.input_request.control_quality[0].auto_modify_info:
            parts = self.input_request.control_quality[0].auto_modify_info.split(":")
            en_result_key = map_cn_key_to_en_key(parts[0])
            if en_result_key is None:
                return response
            modify_key = en_result_key
            modify_val = parts[1]
        else:
            en_result_key = self.input_request.control_quality[0].field
            input_item = self.input_request.control_quality[0].item
            if input_item is not None and isinstance(input_item, str) and len(input_item) > 0:
                en_result_key = input_item
            if en_result_key is None:
                return response
            modify_key = map_cn_key_to_en_key(en_result_key)
            modify_val = self.input_request.control_quality[0].auto_modify_info
        
        # print(f"***lmx*** confirm_auto_modify_request  modify_key {modify_key} modify_val {modify_val}  ")
        response.control_quality = None
        return modify_control_quality_data(response,  modify_key, modify_val)


    async def async_predict(self, messages:str, temp:float = 0, top_p:float = 1) -> str:
        stream = await self.async_client.chat.completions.create(
            model = self.model_name,
            messages=messages,
            stream=True,
            temperature=temp,
            top_p=top_p,
            max_tokens=1024, 
            stop="<|eot_id|>",
        )

        answer=""
        async for completion in stream:
            answer+= (completion.choices[0].delta.content or "" )

        return answer
    
    async def async_process_queries(self) -> QualityAPIResponse:
        if self.input_request.confirm_auto_modify:
            response = self.confirm_auto_modify_request()
            response_output = QualityAPIResponseOutput()
            response_output.output = response
            return response_output            
        
        query = self.__get_quality_modify_message()
        results = await self.async_predict(messages=query)

        response = QualityAPIResponse.from_request(self.input_request)      
        
        # response.historical_conversations.append(HistoricalConversations(role='assistant', content=results))
        historical_conversation_new = HistoricalConversation(role='assistant', content=results)
        
        medical_record = self.extract_json_data(results)
        
        if medical_record is not None:
            en_medical_record = qc_map_chinese_to_english(medical_record)
            # print(f"***lmx*** async_process_queries medical_record {medical_record}  \n en_medical_record{en_medical_record} \n results {results} \n request {self.input_request}")
            medical_record_info = BasicMedicalRecord(**en_medical_record)
            response.basic_medical_record = medical_record_info
            
        response_output = QualityAPIResponseOutput()
        response_output.output = response
        response_output.chat = HistoricalConversations()
        if self.historical_conversations is not None:
            response_output.chat.historical_conversations = self.historical_conversations

        response_output.chat.historical_conversations.append(historical_conversation_new)
        
        return response_output