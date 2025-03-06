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
from typing import Any, Dict, List, Union
from .quality_common_ds import PhyscialExamination, BasicMedicalRecord, ControlQuality, HistoricalConversations, QualityAPIRequest, DebugPrompt, QualityAPIResponse, QualityAPIRequestInput, QualityAPIResponseOutput
import json
from openai import OpenAI, AsyncOpenAI
import asyncio

from string import Template


# QUALITY_INSPECT_PROMPT_TEMPLATE v1.0  group 
# The main reason for splitting the prompt into multiple segments is that different
# combinations can affect the inference results. Therefore, the prompt was combined based on the input content
QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT = Template("""请检查：$inspect_content_title。
""")
QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_STANDARD = Template("""检查标准为："$inspect_standard。"\n""")
QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_POSITIVE_EXAMPLE = Template("""正例："$positive_example。"\n""")
QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_NEGATIVE_EXAMPLE = Template("""反例："$negative_example。"\n""")
QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT_OUTPUT = Template("""如果符合标准，质检结果为:"通过"。
如果不符合标准，质检结果为:"不通过"，不通过情况下给出详细说明。
不要输出python代码。
只检查待检查内容，不要检查因待检查内容而推理生成的内容。
检查结果以json格式输出，例如：{"质检结果": "","原因": "","建议修改为":""}。
""")

QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT_INPUT = Template("""待检查内容为:"$inspect_content。"
""")
# QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT_MODIFY  = Template("""请在检查结果后，给出正确修改后的结果，修改后结果的格式为json格式，例如：{"建议修改为": ""}""")


class QualityInspect:
    def __init__(self, input_request: QualityAPIRequest, 
        quality_template_info : List[Dict],
        openai_api_key: str,
        openai_api_base: str,
        model_name : str,
        async_client : AsyncOpenAI | None,
    ):
        self.input_request = input_request
        self.quality_template_info = quality_template_info
        self.openai_api_key = openai_api_key
        self.openai_api_base = openai_api_base
        self.model_name = model_name
        
        if async_client is None:
            self.async_client = AsyncOpenAI(api_key = openai_api_key, base_url = openai_api_base)
        else:
            self.async_client = async_client
        self.quality_list = [ControlQuality(**data) for data in self.quality_template_info] 
        self.kong_str = "空"
        self.format_inspect = """{
    "质检结果": ""
}
"""
        self.format_inspect_modify = """{
            "建议修改为": ""
        }
"""
        self.CHECK_QUALITY_KEY = "质检结果"
        self.QUALITY_NO_ABNORM = "无异常"
        self.AUTO_MODIFY_KEY = "建议修改为"
        self.QUALITY_NO_PASS = "不通过"
        self.QUALITY_PASS = "通过"
        
        self.RESON_OF_NO_PASS = "原因"

    def __con_medical_record(self, field : str, item : str) -> str:
        """generate new new_fields for AI inference 

        Args:
            field (str): one  ControlQuality.field info IN self.input_request control_quality 
            item (str): one  ControlQuality.item info IN self.input_request control_quality 
            
            more info look quality.json

        Returns:
            str: _description_, change dict->str and change to define format,  such as 
                remove ""{}, "}" ,change "," to "\n" 
        
        """
        pe = self.input_request.basic_medical_record.physical_examination
        
        self.physical_examination = (
            f"体温:{pe.temperature or self.kong_str}; 脉搏:{pe.pulse or self.kong_str};"
            f"血压:{pe.blood_pressure or self.kong_str}; 呼吸:{pe.respiration or self.kong_str};"
        )
        self.temperature = pe.temperature or self.kong_str
        self.pulse = pe.pulse or self.kong_str
        self.blood_pressure = pe.blood_pressure or self.kong_str
        self.respiration = pe.respiration or self.kong_str
        
        bmr_map={
            "主诉":self.input_request.basic_medical_record.chief_complaint,
            "现病史":self.input_request.basic_medical_record.history_of_present_illness  or self.kong_str,
            "既往史":self.input_request.basic_medical_record.past_medical_history or self.kong_str,
            "个人史":self.input_request.basic_medical_record.personal_history or self.kong_str,
            "过敏史":self.input_request.basic_medical_record.allergy_history or self.kong_str,
            "体格检查":self.physical_examination,
            "体温":self.temperature,
            "脉搏":self.pulse,
            "血压":self.blood_pressure,
            "呼吸":self.respiration,
            "辅助检查":self.input_request.basic_medical_record.auxiliary_examination  or self.kong_str
        }
        
        fields = field.split(";")
        if fields[-1] == "":
            fields = fields[:-1]
        new_fields = dict()
        new_info = None
        for f in fields:
            if f == '体格检查' and bool(item):
                new_fields[item] = bmr_map.get(item)
                new_info = bmr_map.get(item)
                new_info = str(new_info).replace("{", "").replace("}", "").replace("\',", "\n").replace("\'", "").replace(" ", "")
            else:
                new_fields[f] = bmr_map.get(f)
                
        new_fields = str(new_fields).replace("{", "").replace("}", "").replace("\',", "\n").replace("\'", "").replace(" ", "")
        if new_info is not None:
            return new_info
        else:
            return new_fields


    def extract_json_data(self, partial_message:str) ->  Union[str, dict]: 
        """_summary_
        input case:
            我已经按照您的要求检查了病历，现在为您生成异常项：
            {
                "质检结果": "体温数值后缺少单位“℃”"
            }
        
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
        
        
        json_pattern = re.compile(r'\{[^}]*\}')
        json_matches = json_pattern.findall(partial_message_2)

        json_data_list = []
        for match in json_matches:
            try:
                json_data_list.append(json.loads(match))
            except json.JSONDecodeError:
                print(f"无法解码的JSON数据: {match}")

        result_dict = {}
        for item in json_data_list:
            result_dict.update(item)
        return result_dict
            
        
        try:  
            # json.loads Parse string  
            # case_data = json.loads(case_search.group(0))  
            if isinstance(case_search, re.Match):
                case_data = case_search.group(0)
                case_data = eval(case_data)

            return case_data['质检结果']
                       
        except json.JSONDecodeError:  
            return None  
        except Exception as e:
            return ""    

        
    def __get_quality_inspect_message(self, inspect_content:str, 
                                      new_fields:str, 
                                      enable_modify_check = False, 
                                      standard_info = None,
                                      positive_example = None,
                                      negative_example = None) -> str:
        system_str = ""
        # QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT()
        system_str = QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT.substitute(inspect_content_title = inspect_content)
        
        if standard_info is not None and isinstance(standard_info, str) and len(standard_info) > 0:
            system_str = system_str + QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_STANDARD.substitute(inspect_standard = standard_info)
        if positive_example is not None and isinstance(positive_example, str) and len(positive_example) > 0:
            system_str = system_str + QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_POSITIVE_EXAMPLE.substitute(positive_example = positive_example)
        if negative_example is not None and isinstance(negative_example, str) and len(negative_example) > 0:
            system_str = system_str + QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_NEGATIVE_EXAMPLE.substitute(negative_example = negative_example)    
        system_str = system_str + QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT_OUTPUT.substitute()
        system_str = system_str + QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT_INPUT.substitute(inspect_content = new_fields)
        # if enable_modify_check:
        #       system_str = system_str + QUALITY_INSPECT_PROMPT_TEMPLATE_V1_0_CONTENT_MODIFY.substitute()
        
        messages=[{"role": "user", "content": system_str}]
        return messages
        '''
        system_str=f"""\
你是医院里一个优秀的病历质检员，主要工作是对病历的撰写质量进行检查，按照'检查要求'对待检查内容进行检查，并将检查结果输出。`检查要求`为“{inspect_content}”。
质检是对病历的质量进行打分，不是对病人健康进行打分，因此请注意数值类的异常必须对两种情况进行严格区分：
1）注意病人生病会造成某些指标的异常，如果在生病的范围内，判断不是撰写有误的问题，认定为通过
2）如果异常过大，明显超过人体/生物体数值范围，则为撰写错误，认定为不通过。
3）如果待检查不通过，在检查结果里进行详细说明。
4）如果检查要求为“xxx是否为空”，只检查`待检查内容`是否为空，不检查其它错误， 只要不为空就将检查结果记录为“通过”。

检查结果的格式为json格式，例如：{self.format_inspect}。输出检查结果时先说“我已经按照您的要求检查了病历，现在为您生成检查结果：”。"""

        if standard_info is not None and isinstance(standard_info, str) and len(standard_info) > 0:
            system_str = system_str + f"""检查要求对应的标准如下：{standard_info}"""
            
        if enable_modify_check:
            user_str=f"""待检查内容如下：“{new_fields}”，请对其进行检查。请在检查结果后，对不符合`检查要求`的内容给出修改后的结果，不要修改其它内容。修改后结果的格式为json格式，例如：{self.format_inspect_modify}"""
        else:
            user_str=f"""待检查内容如下：“{new_fields}”，请对其进行检查。"""
            
        system_str = system_str + user_str    
        
        messages=[{"role": "system", "content": system_str}]
        # messages=[{"role": "user", "content": system_str}]

        # messages.append({"role": "user", "content": user_str})
        
        # str_messages = json.dumps(messages, ensure_ascii=False)
        # print(f"***lmx***  __get_quality_inspect_message {str_messages}   ")
        return messages
        '''
    
    def remove_normal_control_quality(self, control_quality: List[ControlQuality] ):
        ret_control_quality = []
        for cq in control_quality:
            # if self.QUALITY_NO_ABNORM not in cq.check_quality:
            #    ret_control_quality.append(cq)
            if cq.check_quality != self.QUALITY_PASS:
                ret_control_quality.append(cq)
            
            # ret_control_quality.append(cq)
        return ret_control_quality
        
    
    async def async_predict(self, messages:str,  control_quality:ControlQuality, temp:float = 0, top_p:float = 1) -> ControlQuality:
        '''
        stream = await self.async_client.chat.completions.create(
            model = self.model_name,
            messages=messages,
            stream=True,
            temperature=temp,
            top_p=top_p,
            max_tokens=4096, 
            stop="<|eot_id|>",
            timeout = 30
        )
        '''
        
        stream = await self.async_client.chat.completions.create(
            model = self.model_name,
            messages=messages,
            stream=True,
            temperature=temp,
            top_p=top_p,
            max_tokens=4096, 
            timeout = 30
        )

        control_quality_ret = control_quality
        answer=""
        
        try:
            async for completion in stream:
                answer+= (completion.choices[0].delta.content or "" )
        except Exception as e:
            print(f"发生异常: {e}")
        
        result_dict = self.extract_json_data(answer)
        check_quality = result_dict.get(self.CHECK_QUALITY_KEY, self.QUALITY_PASS)
        auto_modify_info = result_dict.get(self.AUTO_MODIFY_KEY, "")
        reson_of_no_pass = result_dict.get(self.RESON_OF_NO_PASS)
        
        control_quality_ret.check_quality = check_quality 
        if control_quality_ret.auto_modify_type is True:
            control_quality_ret.auto_modify_info = auto_modify_info
        if reson_of_no_pass is not None and self.QUALITY_NO_PASS in check_quality:
            control_quality_ret.check_quality = control_quality_ret.check_quality + "    " + reson_of_no_pass
        return control_quality_ret
   
    
    async def async_process_queries(self):
        queries = []
        for index, control_quality in enumerate(self.quality_list):
            new_fields = self.__con_medical_record(control_quality.field, control_quality.item)
            messages = self.__get_quality_inspect_message(control_quality.content, 
                                                          new_fields, 
                                                          control_quality.auto_modify_type, 
                                                          control_quality.standard,
                                                          control_quality.positive_example,
                                                          control_quality.negative_example)
            queries.append(messages)
        
        results = await asyncio.gather(*(self.async_predict(query, control_quality) for query, control_quality in zip(queries, self.quality_list)))
        
        response = QualityAPIResponse.from_request(self.input_request) 
        clear_results = self.remove_normal_control_quality(results)  
        
        response.control_quality = clear_results
        response_output = QualityAPIResponseOutput()
        response_output.output = response
        return response_output
