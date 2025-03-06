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
import signal
import time
import warnings
import datetime
import uvicorn
import argparse
import threading
from typing import List, Optional, Union, TypeVar, Generic

import asyncio
from pydantic import BaseModel
from fastapi import FastAPI, Query, Body, HTTPException
from fastapi.encoders import jsonable_encoder
from openai import OpenAI, AsyncOpenAI
from sqlalchemy import create_engine, text
from fastbm25 import fastbm25
from concurrent.futures import ThreadPoolExecutor
from id_validator import validator

from multiprocessing import  freeze_support

from quality.quality_common_ds import QualityAPIRequestInput
from quality.quality_inspect import QualityInspect
from quality.quality_modify import QualityModify
from quality.util import handle_quality
from fastapi.responses import JSONResponse


from diagnosis_treatment.client_info_request_handler import ClientInfoRequestHandler
from diagnosis_treatment.basic_medical_record_request_handler import BasicMedicalRecordRequestHandler
from diagnosis_treatment.register_diagnosis_request_handler import RegisterDiagnosisRequestHandler
from diagnosis_treatment.diagnosis_request_handler import DiagnosisRequestHandler
from diagnosis_treatment.examine_assay_request_handler import ExamineAssayRequestHandler
from diagnosis_treatment.therapy_scheme_request_handler import TherapySchemeRequestHandler
from diagnosis_treatment.distribute_request_handler import DistributeRequestHandler
from diagnosis_treatment.return_visit_request_handler import ReturnVisitRequestHandler
from diagnosis_treatment.prompt_factory import *
from quality.quality_configs import QualityConfigs

def args_parser():
    parser = argparse.ArgumentParser(description='Chatbot Interface with Customizable Parameters')
    parser.add_argument('--model-url', type=str, default='http://localhost:8000/v1', help='Model URL')
    parser.add_argument('--model', type=str, required=True, help='Model name for the chatbot')
    parser.add_argument('--database', type=str, default="/usr/local/insinfersystem/database", help='Database name')
    parser.add_argument('--fastbm25', action='store_true', help='If True, enable fastbm25 query.')
    parser.add_argument('--log', action='store_true', help='If True, save log to ./medical_xxx.log.')
    parser.add_argument('--max-round', type=int, default=30, help='The maximum number of conversations.')
    parser.add_argument("--host", type=str, required=True)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument('--quality', type=str, default="../../database/quality/quality.json", help='Database name')
    parser.add_argument('--api-key', type=str, default='EMPTY', help='api key')
    args = parser.parse_args()
    return args


app = FastAPI()


def thread_pool_executor(requestv, *receive, **kreceive):
    loop = asyncio.get_running_loop()
    def signal_handler():
            print("Received SIGINT, cancelling tasks...")
            executor.shutdown(wait=False)
            loop.stop()
    # 注册信号处理函数
    loop.add_signal_handler(signal.SIGINT, signal_handler)    
    return loop.run_in_executor(executor, requestv, *receive, **kreceive)


@app.post("/quality_inspect")
async def qulity_inspect(
   input_request_input: QualityAPIRequestInput
):
    args = args_parser()
    OPENAI_API_KEY = "EMPTY"
    input_request = input_request_input.input
    g_quality_configs = QualityConfigs(args.quality)
    QUALITY_SETTINGS = handle_quality(args.quality)
    g_async_client = AsyncOpenAI(api_key = OPENAI_API_KEY, base_url = args.model_url)

    
    if input_request.control_quality_config_name is not None:
        quality_config_real = g_quality_configs.get_quality_config_by_name(input_request.control_quality_config_name)
        if quality_config_real is None:
            raise HTTPException(status_code=400, detail=f"config_name {input_request.control_quality_config_name} not found")
    else:
        quality_config_real = g_quality_configs.get_default_quality_config()
    quality_inspect = QualityInspect(input_request, quality_config_real, OPENAI_API_KEY, args.model_url, args.model, async_client=g_async_client)
    results = await quality_inspect.async_process_queries()
    json_compatible_data = jsonable_encoder(results, exclude_none = True)
    return JSONResponse(content=json_compatible_data)    


@app.post("/quality_modify")
async def qulity_modify(
   input_request_input: QualityAPIRequestInput
):
    args = args_parser()
    OPENAI_API_KEY = "EMPTY"
    input_request = input_request_input.input
    input_chat = input_request_input.chat
    historical_conversations = None
    QUALITY_SETTINGS = handle_quality(args.quality)
    g_async_client = AsyncOpenAI(api_key = OPENAI_API_KEY, base_url = args.model_url)

    if input_chat:
        historical_conversations = input_chat.historical_conversations
    quality_modify = QualityModify(input_request, historical_conversations, OPENAI_API_KEY, args.model_url, args.model, async_client=g_async_client)
    results = await quality_modify.async_process_queries()
    json_compatible_data = jsonable_encoder(results, exclude_none = True)
    return JSONResponse(content=json_compatible_data)


@app.post("/inference")
async def request_inference(
    request_type: str = Query(...),
    data: dict = Body(...),
    scheme: str = Query(None),
    sub_scheme: str = Query(None)
):
    args = args_parser()
    handler_classes = {
        "v0": DistributeRequestHandler,
        "v1": ClientInfoRequestHandler,
        "v2": BasicMedicalRecordRequestHandler,
        "v3": RegisterDiagnosisRequestHandler,
        "v4": DiagnosisRequestHandler,
        "v5": ExamineAssayRequestHandler,
        "v6": TherapySchemeRequestHandler,
        "v7": ReturnVisitRequestHandler
    }
    if request_type in handler_classes:
        handler_class = handler_classes.get(request_type)
        if handler_class:
            handler = handler_class(data, args, scheme, sub_scheme,request_type, )
            results = await thread_pool_executor(handler.handle_request)
    else:
        results = HTTPException(status_code=400, detail="Invalid request_type")
    return results

#curl_num = 0
#tmp_engine = None
executor = ThreadPoolExecutor(200) # max_workers = 1024
log_name = datetime.datetime.now().strftime('%Y%m%d%H%M%S')


if __name__ == '__main__':
    freeze_support()
    args = args_parser()
    uvicorn.run(app="inference:app", host=args.host, port=args.port, timeout_keep_alive=30, workers=32,reload=False)
