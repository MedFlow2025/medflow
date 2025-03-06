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

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from fastapi import FastAPI, Body
from typing_extensions import Annotated

class PhyscialExamination(BaseModel):
    temperature: str
    pulse: str
    blood_pressure: str
    respiration: str

class BasicMedicalRecord(BaseModel):
    chief_complaint: str
    history_of_present_illness: str
    past_medical_history: str
    personal_history: str
    allergy_history: str
    physical_examination: PhyscialExamination 
    auxiliary_examination: str

class ControlQuality(BaseModel):
    content: str
    field: str
    item: str=""
    standard: str=""
    check_quality: Union[str, dict] = ""  
    auto_modify_type: bool = False
    auto_modify_info: str=""
    positive_example: str=None
    negative_example: str=None
    

class HistoricalConversation(BaseModel):
    role: str
    content: str

class DebugPrompt(BaseModel):
    system_str: str
    user_str: str | None = None
    sentence: str | None = None

class HistoricalConversations(BaseModel):
    historical_conversations: List[HistoricalConversation] = []

class QualityAPIRequest(BaseModel):
    """_summary_
    Quality API Request data struct

    Args:
        BaseModel (_type_): _description_
    """
    basic_medical_record: BasicMedicalRecord
    control_quality: List[ControlQuality] | None = None
    # remark: Annotated[str, Body()]  | None = None
    # debug_prompt: DebugPrompt | None = None
    confirm_auto_modify: bool | None = None
    control_quality_config_name : str | None = None

'''
here datastruct is change struct by TianRui User
then went input / output / chat: to Clearly distinct, so add  here
'''
class QualityAPIRequestInput(BaseModel):
    input: QualityAPIRequest | None = None
    chat: HistoricalConversations | None = None
    
class QualityAPIResponse(BaseModel):
    """_summary_
    Quality API Response data struct

    Args:
        BaseModel (_type_): _description_
    """
    basic_medical_record: BasicMedicalRecord
    control_quality: Optional[List[ControlQuality]] = Field(None, exclude_none=True)
    historical_conversations: Optional[List[HistoricalConversation]] = Field(None, exclude_if=lambda v: v is None)
    # remark: Optional[str] = Field(None, exclude_none=True)
    # debug_prompt: Optional[DebugPrompt] = Field(None, exclude_none=True)
    
    @classmethod
    def from_request(cls, request: QualityAPIRequest) -> 'QualityAPIResponse':
        # 
        return cls(
            basic_medical_record=request.basic_medical_record,
            control_quality=request.control_quality,
            # historical_conversations=request.historical_conversations,
            # remark=request.remark,
            # debug_prompt=request.debug_prompt,
        )

class QualityAPIResponseOutput(BaseModel):
    output: QualityAPIResponse | None = None
    chat: HistoricalConversations | None = None

def qc_map_chinese_to_english_physcial_examination(chinese_data: Dict[str, Any]) -> Dict[str, Any]:
    # 映射体格检查中的中文字段到英文字段
    mapping = {
        '体温': 'temperature',
        '脉搏': 'pulse',
        '血压': 'blood_pressure',
        '呼吸': 'respiration'
    }
    mapped_data = {}
    for chinese_key, english_key in mapping.items():
        if chinese_key in chinese_data:
            mapped_data[english_key] = chinese_data[chinese_key]
    return mapped_data
 
def qc_map_chinese_to_english(chinese_data: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {
        '主诉': 'chief_complaint',
        '现病史': 'history_of_present_illness',
        '既往史': 'past_medical_history',
        '个人史': 'personal_history',
        '过敏史': 'allergy_history',
        '体格检查': 'physical_examination',
        '辅助检查': 'auxiliary_examination'
    }
    
    mapped_data = {}
    for chinese_key, english_key in mapping.items():
        if chinese_key in chinese_data:
            value = chinese_data[chinese_key]
            if english_key == 'physical_examination' and isinstance(value, dict):
                # 使用嵌套的映射函数处理体格检查数据
                mapped_data[english_key] = PhyscialExamination(**qc_map_chinese_to_english_physcial_examination(value))
            else:
                mapped_data[english_key] = value
    
    # 确保所有必要的字段都已映射（可选，但推荐用于验证）
    '''
    for english_key in BasicMedicalRecord.model_fields.keys():
        if english_key not in mapped_data:
            raise ValueError(f"Missing required field: {english_key}")
    '''
    
    return mapped_data

def map_cn_key_to_en_key(input_key: str) -> str:
    mapping = {
        '主诉': 'chief_complaint',
        '现病史': 'history_of_present_illness',
        '既往史': 'past_medical_history',
        '个人史': 'personal_history',
        '过敏史': 'allergy_history',
        '体格检查': 'physical_examination',
        '辅助检查': 'auxiliary_examination',
        '体温': 'temperature',
        '脉搏': 'pulse',
        '血压': 'blood_pressure',
        '呼吸': 'respiration'
    }
    if input_key in mapping:
        return mapping[input_key]
    else:
        return None

def modify_control_quality_data(data: QualityAPIResponse, key_input: str, value_input: str) -> QualityAPIResponse:
    if isinstance(data, BaseModel):
        for field in data.model_fields:
            field_value = getattr(data, field)
            if field == key_input:
                setattr(data, field, value_input)
                break
            modify_control_quality_data(field_value, key_input, value_input)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            modified_item = modify_control_quality_data(item, key_input, value_input)
            data[i] = modified_item
    return data
    