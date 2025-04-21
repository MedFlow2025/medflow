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

import json
import gradio as gr
from ..logic.handlers import *
from ..util import get_current_date 
from ..config import args

def build_chat_tab(module_name, json_data, prompt_name, default_chat, function, note:str="", use_branch:bool=False, branch_content:dict={}):
    module = gr.Textbox(value=module_name, visible=False)
    with gr.Row():
        with gr.Accordion(label="JSON", open=True):
            json_display = gr.Code(value=json.dumps(json_data, indent=4, ensure_ascii=False), language="json", label="", interactive=True, max_lines=36)
            if module_name == "hospitalregister":
                current_date = get_current_date()
                today = gr.Textbox(value=current_date, show_label=False, interactive=False)
            json_file = gr.Textbox(value="", visible=False, show_label=False)
            json_md = gr.Markdown(value="")

        with gr.Column():
            model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
            prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_name, value=max(prompt_name), interactive=True, show_label=False, container=False)
            if use_branch:
                branch = gr.Dropdown(label=branch_content["label"], choices=branch_content["choices"], value=branch_content["value"], interactive=True, show_label=False, container=False)
            else:
                branch = gr.Dropdown(visible=False)
            chatbot=gr.Chatbot(
                label="🤖",
                value=default_chat,
                show_label=True,
                show_copy_button=True,
                height=600
            )
            with gr.Row():
                msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False)
                send_btn = gr.Button(value="🚀 Send", variant="primary", scale=1)
            note_md = gr.Markdown(value="使用键盘“Enter”发送消息时，以流式显示。点击“Send”发送消息时，以非流式显示。<br>"+note)

    #send_btn.click(function,
    #    inputs=[msg, json_display, json_file, module, prompt_version, model_name, branch],
    #    outputs=[msg, chatbot, json_display, json_file, json_md, prompt_version, model_name]
    #)
    send_btn.click(function,
        inputs=[msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name],
        outputs=[msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name]
    )

    msg.submit(
        user_response_stream,
        inputs=[json_display, prompt_version, model_name],
        outputs=[json_display]
        ).then(
        fetch_response_stream,
        inputs=[msg, json_display, json_file, module, branch],
        outputs=[msg, chatbot, json_display, json_file, json_md]
    )

    if use_branch:
        if module_name == "hospitalguide":
            branch.change(
                lambda x : gr.update(value=json.dumps(inference_gradio_json_data[module_name + "_" + x], indent=4, ensure_ascii = False)),
                inputs=[branch],
                outputs=[json_display]
            )
        if module_name == "hospitalregister":
            def change_register_info(selected_register_type, json_display):
                json_ret = json_display
                json_ret_data = json.loads(json_ret)
                if selected_register_type == "base_tpye":
                    json_ret_data["input"]["register_intention_enable"] = False
                else:
                    json_ret_data["input"]["register_intention_enable"] = True
                json_ret = json.dumps(json_ret_data, indent=4, ensure_ascii = False)
                return json_ret

            branch.change(
                fn = change_register_info,
                inputs=[branch, json_display],
                outputs=[json_display]
            )  
    return json_display, module

def build_nochat_tab(module_name, json_data, prompt_name, module_label, btn_name, function, note:str="", use_branch:bool=False, branch_content:dict={}):
    module = gr.Textbox(value=module_name, visible=False)
    with gr.Row():
        with gr.Column():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display = gr.Code(value=json.dumps(json_data, indent=4, ensure_ascii=False), language="json", label="", interactive=True, max_lines=33)
            json_file = gr.Textbox(value="", visible=False, show_label=False)
            json_md = gr.Markdown(value="")

        with gr.Column():
            model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
            prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_name, value=max(prompt_name), interactive=True, show_label=False, container=False)
            if use_branch:
                branch = gr.Dropdown(label=branch_content["label"], choices=branch_content["choices"], value=branch_content["value"], interactive=True, show_label=False, container=False)
            else:
                branch = gr.Dropdown(visible=False)
            result_json = gr.Code(value=json.dumps({}, indent=4, ensure_ascii=False), language="json", label="", interactive=True, max_lines=33, visible=False)
            result_text = gr.Textbox(label="️📑 "+module_label, placeholder="", value="", show_label=True, interactive=False, lines=24)
            note_md = gr.Markdown(value=note)
            with gr.Row():
                send_btn = gr.Button(value="🚀 "+btn_name, variant="primary")

    if module_name not in ["diagnosis", "scheme"]:
        #send_btn.click(function,
        #    inputs=[json_display, json_file, module, branch],
        #    outputs=[json_file, json_md, result_text, result_json]
        #)
        send_btn.click(function,
            inputs=[json_display, json_file, module, json_md, result_text, result_json, branch],
            outputs=[json_display, json_file, module, json_md, result_text, result_json, branch]
        )

    if use_branch:
        if module_name == "doctormedicalrecord":
            branch.change(
                lambda x : gr.update(value=json.dumps(inference_gradio_json_data[module_name + "_" + x], indent=4, ensure_ascii = False)),
                inputs=[branch],
                outputs=[json_display]
            )

    return json_display, module, result_json, send_btn, json_file, json_md, result_text, branch

def build_send_button(btn_config, result_json):
    extra_btns = []
    with gr.Row() as row:
        with gr.Column(scale=1):
            with gr.Row():
                for cfg in btn_config:
                    extra_btn = gr.Button(value=cfg["label"], variant="primary", scale=1, visible=cfg["visible"])
                    extra_btn.click(
                        send_to_tab,
                        inputs=[result_json, cfg["display"], cfg["module"]],
                        outputs=[result_json, cfg["display"]]
                    )
                    extra_btns.append(extra_btn)
        with gr.Column(scale=1):
            pass
    return extra_btns

def build_multi_tabs(tab_config):
    with gr.Blocks(analytics_enabled=False):
        for i, l, id, v in tab_config:
            if v == False:
                continue
            with gr.TabItem(l, id=id, visible=True):
                i.render()