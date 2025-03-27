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
import gradio as gr
import os
import json
import datetime
import copy
import httpx
import numpy as np
import pandas as pd
import requests
import re
import random
# from .fetch_function import *
from .util import inference_gradio_json_data, inference_gradio_http_common_headers, args

prompt_versions = {
    "quality_inspect": ["v1"],
    "quality_modify": ["v1"],
}

async def fetch_response_quality_inspect(json_display_quality_inspect, json_file, json_md, interface_name, prompt_version, model_name, results_json):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"quality-inspect-{unique_id}.json"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/quality_inspect",
            json=json_display_quality_inspect,
            headers=inference_gradio_http_common_headers,
            timeout=60,
        )
        
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json_src = response.json()
            json_display_quality_inspect = copy.deepcopy(results_json_src) 
            results_json = results_json_src['output']['control_quality']

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump((results_json_src), f, ensure_ascii=False, indent=4)
                json_md=f"""Successfully! write data to {json_file}."""

            # 检查是否存在 output 键
            if "output" in json_display_quality_inspect:
                # 将 output 键的值赋给 input 键
                json_display_quality_inspect["input"] = json_display_quality_inspect.pop("output")

            return json_display_quality_inspect, json_file, json_md, interface_name, prompt_version, model_name, results_json_src 
        else:
            return "Error: Unable to fetch response from inference API."


async def fetch_response_quality_modify(msg, chatbot, json_display_quality_modify, json_file, json_md, interface_modify_name, prompt_version, model_name):
    if "chat" in json_display_quality_modify:
        user_msg={'role': 'user', 'content': msg}
        json_display_quality_modify["chat"]["historical_conversations"].append(user_msg)
        chatbot.append((msg, None))

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/quality_modify",
            json=json_display_quality_modify,
            headers=inference_gradio_http_common_headers,
            timeout=60,
        )
        
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json_src = response.json()
            chatbot.append((None, results_json_src["chat"]["historical_conversations"][-1]["content"]))
            json_display_quality_modify = results_json_src

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump((results_json_src), f, ensure_ascii=False, indent=4)
                json_md=f"""Successfully! write data to {json_file}."""

            # 检查是否存在 output 键 
            if "output" in json_display_quality_modify:
                # 将 output 键的值赋给 input 键
                json_display_quality_modify["input"] = json_display_quality_modify.pop("output")

            return None, chatbot, json_display_quality_modify, json_file, json_md, interface_modify_name, prompt_version, model_name 
        else:
            return "Error: Unable to fetch response from inference API."

def send_inpect_info_to_qulity_modify(json_display_quality_inspect, json_display_quality_modify):
    json_display_quality_modify = copy.deepcopy(json_display_quality_inspect)
    return json_display_quality_inspect, json_display_quality_modify


def create_quality_inspect_interface(json_display_quality_modify):
    with gr.Blocks(analytics_enabled=False) as quality_inspect_interface:
        interface_name = gr.Textbox(value="质检-检验", visible=False)
        with gr.Row():
            with gr.Column():
                with gr.Accordion(label="JSON", open=True):
                    json_display_quality_inspect = gr.JSON(value=inference_gradio_json_data['quality_inspect'], visible=True, label="JSON", show_label=False, open=True)
                    json_file = gr.Textbox(value="", visible=False, show_label=False)
                    json_md = gr.Markdown(value="")
                with gr.Row():
                    send_quality_modify = gr.Button(value="发送到 质检修改", variant="primary", scale=1, visible=True)
            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["quality_inspect"], value=max(prompt_versions["quality_inspect"]), interactive=True, show_label=False, container=False)
                quality_inspect_result = gr.JSON(label="质检结果", value=None, visible=True, show_label=True, open=True)
                with gr.Row():
                    check_btn = gr.Button(value="检查", variant="primary", scale=1)
        check_btn.click(fetch_response_quality_inspect,
            inputs=[json_display_quality_inspect, json_file, json_md, interface_name, prompt_version, model_name, quality_inspect_result],
            outputs=[json_display_quality_inspect, json_file, json_md, interface_name, prompt_version, model_name, quality_inspect_result]
        )
        send_quality_modify.click(send_inpect_info_to_qulity_modify,
            inputs=[json_display_quality_inspect, json_display_quality_modify],
            outputs=[json_display_quality_inspect, json_display_quality_modify]
        )
        return quality_inspect_interface

def create_quality_modify_interface():
    with gr.Blocks(analytics_enabled=False) as quality_modify_interface:
        interface_modify_name = gr.Textbox(value="质检-对话修改", visible=False)
        with gr.Row():
            with gr.Column():
                with gr.Accordion(label="JSON", open=True):
                    json_display_quality_modify = gr.JSON(value=inference_gradio_json_data['quality_modify'], visible=True, label="JSON", show_label=False, open=True)
                    
                    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    json_file_str = f"quality-modify-{unique_id}.json"
                    json_file = gr.Textbox(value=json_file_str, visible=False, show_label=False)
                    json_md = gr.Markdown(value="")
            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["quality_modify"], value=max(prompt_versions["quality_inspect"]), interactive=True, show_label=False, container=False)
                chatbot=gr.Chatbot(
                    label="Chat",
                    value=[[None, None]],
                    show_label=True,
                    show_copy_button=True,
                    height=600
                )
                with gr.Row():
                    msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False)
                    send_btn = gr.Button(value="发送/获取问题", variant="primary", scale=1)

        send_btn.click(fetch_response_quality_modify,
            inputs=[msg, chatbot, json_display_quality_modify, json_file, json_md, interface_modify_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_quality_modify, json_file, json_md, interface_modify_name, prompt_version, model_name]
        )
        msg.submit(
            fetch_response_quality_modify,
            inputs=[msg, chatbot, json_display_quality_modify, json_file, json_md, interface_modify_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_quality_modify, json_file, json_md, interface_modify_name, prompt_version, model_name]            
        )
        return quality_modify_interface, json_display_quality_modify
