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

import os
import re
import json
import copy
import warnings
import datetime
from typing import Union, List
from typing_extensions import Annotated

import uvicorn
import argparse
from fastapi import FastAPI, Body
from fastapi.encoders import jsonable_encoder
from openai import OpenAI, AsyncOpenAI

import asyncio

from .quality_common_ds import PhyscialExamination, BasicMedicalRecord, ControlQuality, HistoricalConversations, QualityAPIRequest, QualityAPIResponse, DebugPrompt, QualityAPIRequestInput, QualityAPIResponseOutput

from .quality_inspect import QualityInspect
from .quality_modify import QualityModify
from fastapi.responses import JSONResponse


def args_parser():
    # Argument parser setup
    parser = argparse.ArgumentParser(description='Chatbot Interface with Customizable Parameters')
    parser.add_argument(
        '--model-url',
        type=str,
        default='http://localhost:8000/v1',
        help='Model URL'
    )
    parser.add_argument(
        '--model',
        type=str,
        required=True,
        help='Model name for the chatbot'
    )
    parser.add_argument(
        '--quality',
        type=str,
        default="/usr/local/insinfersystem/quality.json",
        help='Database name'
    )
    parser.add_argument(
        '--log',
        action='store_true',
        help='If True, save log to /usr/local/insinfersystem/medical_xxx.log.'
    )
    parser.add_argument(
        "--host",
        type=str,
        required=True
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001
    )

    # Parse the arguments
    args = parser.parse_args()

    return args

args = args_parser()
client = OpenAI(api_key="EMPTY", base_url=args.model_url)
app = FastAPI()

OPENAI_API_KEY = "EMPTY"
OPENAI_API_BASE = args.model_url
async_client = AsyncOpenAI(api_key="EMPTY", base_url=args.model_url)


def handle_quality(quality_path):
    with open(quality_path, 'r') as f:
        input = f.read()
    qs = json.loads(input)
    quality_settings = qs['check_quality']
    return quality_settings 


@app.post("/quality_inspect")
async def qulity_inspect(
   input_request_input: QualityAPIRequestInput
):
    input_request = input_request_input.input
    quality_inspect = QualityInspect(input_request, quality_settings, OPENAI_API_KEY, OPENAI_API_BASE, args.model)
    results = await quality_inspect.async_process_queries()
    json_compatible_data = jsonable_encoder(results, exclude_none = True)
    return JSONResponse(content=json_compatible_data)    

@app.post("/quality_modify")
async def qulity_modify(
   input_request_input: QualityAPIRequestInput
):
    input_request = input_request_input.input
    input_chat = input_request_input.chat
    historical_conversations = None
    if input_chat:
        historical_conversations = input_chat.historical_conversations
    quality_modify = QualityModify(input_request, historical_conversations, OPENAI_API_KEY, OPENAI_API_BASE, args.model)
    results = await quality_modify.async_process_queries()
    json_compatible_data = jsonable_encoder(results, exclude_none = True)
    return JSONResponse(content=json_compatible_data)


@app.post("/qulity")
async def qulity_item(
   input_request_input: QualityAPIRequestInput
):
    input_request = input_request_input.input
    match input_request.item_type:
        case "quality_inspect":
            quality_inspect = QualityInspect(input_request, quality_settings, OPENAI_API_KEY, OPENAI_API_BASE, args.model)
            results = await quality_inspect.async_process_queries()
            json_compatible_data = jsonable_encoder(results, exclude_none = True)
            return JSONResponse(content=json_compatible_data)
        
        case "quality_modify":
            quality_modify = QualityModify(input_request, OPENAI_API_KEY, OPENAI_API_BASE, args.model)
            results = await quality_modify.async_process_queries()
            json_compatible_data = jsonable_encoder(results, exclude_none = True)
            return JSONResponse(content=json_compatible_data)
            
        case _:
            return "Error: item_type is incorrect, please change it."

@app.get("/items/{item_id}")
async def update_item(
   input_request: QualityAPIRequest
):
    match input_request.item_type:
        
        case "quality_inspect":
            quality_inspect = QualityInspect(input_request, quality_settings, OPENAI_API_KEY, OPENAI_API_BASE, args.model)
            results = await quality_inspect.async_process_queries()
            json_compatible_data = jsonable_encoder(results, exclude_none = True)
            return JSONResponse(content=json_compatible_data)
        
        case "quality_modify":
            quality_modify = QualityModify(input_request, OPENAI_API_KEY, OPENAI_API_BASE, args.model)
            results = await quality_modify.async_process_queries()
            json_compatible_data = jsonable_encoder(results, exclude_none = True)
            return JSONResponse(content=json_compatible_data)
            
        case _:
            return "Error: item_type is incorrect, please change it."

if __name__ == '__main__':
    quality_settings = handle_quality(args.quality) 

    log_name = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    uvicorn.run(app, host=args.host, port=args.port)
