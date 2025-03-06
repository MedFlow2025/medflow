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

import argparse
import gradio as gr
import datetime
from gradio_content.fetch_function import *
import threading
import time
import asyncio
import pandas as pd

def args_parser():
    parser = argparse.ArgumentParser(description='Chatbot Web Interface with Customizable Parameters')
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default="8015")
    parser.add_argument("--gradio-port", type=int, default="7015")
    parser.add_argument("--share", action="store_true", help="Whether to generate a public, shareable link")
    parser.add_argument("--concurrency-count", type=int, default=50, help="The concurrency count of the gradio queue")
    parser.add_argument('--model', type=str, required=True, help='Model name for the chatbot')
    args = parser.parse_args()
    return args

args = args_parser()

#prompt_versions = ["v1", "v2"]
#default_prompt_version = "v1"
prompt_versions = {
    "agent": ["v1"],
    "jiandang": ["v1", "v2"],
    "yuwenzhen": ["v1", "v2", "v3"],
    "guahao": ["v1"],
    "fuzhen": ["v1"]
}

async def v0(msg, chatbot, json_display_v, json_file, json_md, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan=None)), prompt_version, model_name

async def v1(msg, chatbot, json_display_v, json_file, json_md, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan=None)), prompt_version, model_name

async def v2(msg, chatbot, json_display_v, json_file, json_md, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan=None)), prompt_version, model_name

async def v3(msg, chatbot, json_display_v, json_file, json_md, vn, prompt_version, model_name, json_display_by_code, today): 
    # return await fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan=None)
    # json_display_by_code 这个是可编辑的，这里没有对比是否有变化，所以每次都根据json_display_by_code更新原来json数据
    '''
    # update_v3_current_date() 这个主要是更新对应的日期，gradio启动后若第二天测试，这里触发自动改对应时间
    # json_display_by_code这部分根据当前day信息更新还没有实现，暂时先放在这里
    update_json_display, update_json_code, update_current = update_v3_current_date(json_display_by_code)
    if update_current is not None and update_json_display is not None and update_json_code is not None:
        json_display_by_code = update_json_code
        json_display_v = update_json_display
        today = update_current
    '''
    updated_data = json.loads(json_display_by_code)
    json_data['v3'] = updated_data
    json_display_v = updated_data
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    result = await fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan=None)
    updated_json_data = result[2]
    updated_json_str = json.dumps(updated_json_data, indent=4, ensure_ascii=False)
    return (*result, prompt_version, model_name, updated_json_str, today)

async def v7(msg, chatbot, json_display_v, json_file, json_md, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan=None)), prompt_version, model_name

def build_app():
    def user_response_v123(msg, chatbot, json_display_v, json_file, json_md, vn, prompt_version, model_name): #, send_zhenduan:None):
            # chatbot = chatbot + [[msg, None]]
            json_display_v['chat']['prompt_version'] = prompt_version
            json_display_v['chat']['model_name'] = model_name
            return msg, chatbot, json_display_v, json_file, json_md, vn #, send_zhenduan

    with gr.Blocks(analytics_enabled=False) as v7_interface:
        v7_name = gr.Textbox(value="v7", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True):
                #json_display_v7 = gr.JSON(value=json_data['v7'], visible=True, label="JSON", show_label=False, open=True)
                json_display_v7 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file = gr.Textbox(value="", visible=False, show_label=False)
                json_md = gr.Markdown(value="")

            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["fuzhen"], value=max(prompt_versions["fuzhen"]), interactive=True, show_label=False, container=False)
                chatbot=gr.Chatbot(
                    label="Chat",
                    #value=[[json_data['v7']['chat']['historical_conversations'][-2]['content'], json_data['v7']['chat']['historical_conversations'][-1]['content']]],
                    show_label=True,
                    show_copy_button=True,
                    height=600
                )
                with gr.Row():
                    msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False)
                    send_btn = gr.Button(value="Send", variant="primary", scale=1)

        send_btn.click(v7,
            inputs=[msg, chatbot, json_display_v7, json_file, json_md, v7_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v7, json_file, json_md, v7_name, prompt_version, model_name]
        )

        msg.submit(
            user_response_v123,
            inputs=[msg, chatbot, json_display_v7, json_file, json_md, v7_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v7, json_file, json_md, v7_name]
            ).then(
            fetch_response_v123,
            inputs=[msg, chatbot, json_display_v7, json_file, json_md, v7_name],
            outputs=[msg, chatbot, json_display_v7, json_file, json_md, v7_name]
        )

    with gr.Blocks(analytics_enabled=False) as v631_interface:
        v631_name = gr.Textbox(value="v631", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v631 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v631 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v631 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                shoushu_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                shoushu = gr.Textbox(label="手术治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                shoushu_btn = gr.Button(value="生成手术治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v632_interface:
        v632_name = gr.Textbox(value="v632", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v632 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v632 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v632 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                hualiao_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                hualiao = gr.Textbox(label="化学治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                hualiao_btn = gr.Button(value="生成化学治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v633_interface:
        v633_name = gr.Textbox(value="v633", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v633 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v633 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v633 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                fangliao_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                fangliao = gr.Textbox(label="放射治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                fangliao_btn = gr.Button(value="生成放射治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v634_interface:
        v634_name = gr.Textbox(value="v634", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v634 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v634 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v634 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                xinli_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                xinli = gr.Textbox(label="心理治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                xinli_btn = gr.Button(value="生成心理治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v635_interface:
        v635_name = gr.Textbox(value="v635", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v635 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v635 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v635 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                kangfu_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                kangfu = gr.Textbox(label="康复治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                kangfu_btn = gr.Button(value="生成康复治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v636_interface:
        v636_name = gr.Textbox(value="v636", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v636 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v636 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v636 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                wuli_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                wuli = gr.Textbox(label="物理治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                wuli_btn = gr.Button(value="生成物理治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v637_interface:
        v637_name = gr.Textbox(value="v637", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v637 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v637 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v637 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                tidai_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                tidai = gr.Textbox(label="替代疗法", placeholder="", value="", show_label=True, interactive=False, lines=21)
                tidai_btn = gr.Button(value="生成替代疗法", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v638_interface:
        v638_name = gr.Textbox(value="v638", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True, visible=True):
                json_display_v638 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                json_file_v638 = gr.Textbox(value="", visible=False, show_label=False)
                json_md_v638 = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                guancha_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                guancha = gr.Textbox(label="观察治疗", placeholder="", value="", show_label=True, interactive=False, lines=21)
                guancha_btn = gr.Button(value="生成观察治疗", variant="primary")

    with gr.Blocks(analytics_enabled=False) as v6_interface:
        v6_name = gr.Textbox(value="v6", visible=False)
        with gr.TabItem("v6.1-挑选方案"):
            with gr.Row():
                with gr.Accordion(label="JSON", open=True, visible=True):
                    json_display_v6 = gr.JSON(value=json_data['v6'], visible=True, label="JSON", show_label=False, open=True)
                    json_file_v61 = gr.Textbox(value="", visible=False, show_label=False)
                    json_md_v61 = gr.Markdown(value="")
                with gr.Column():
                    gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                    duofangan_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                    duofangan = gr.Textbox(label="多方案", placeholder="", value="", show_label=True, interactive=False, lines=21)
                    duofangan_btn = gr.Button(value="生成多方案", variant="primary")
    
        with gr.TabItem("v6.2-保守方案"):
            with gr.Tab("v6.2.1-处方"):
                v621_name = gr.Textbox(value="v621", visible=False)
                with gr.Row():
                    with gr.Accordion(label="JSON", open=True, visible=True):
                        json_display_v621 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                        json_file_v621 = gr.Textbox(value="", visible=False, show_label=False)
                        json_md_v621 = gr.Markdown(value="")
                    with gr.Column():
                        gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                        chufang_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                        chufang = gr.Textbox(label="处方", placeholder="", value="", show_label=True, interactive=False, lines=21)
                        note_md = gr.Markdown(value="括号中内容为匹配数据表后的药品名称。")
                        chufang_btn = gr.Button(value="生成处方", variant="primary")

            with gr.Tab("v6.2.2-输液"):
                v622_name = gr.Textbox(value="v622", visible=False)
                with gr.Row():
                    with gr.Accordion(label="JSON", open=True, visible=True):
                        json_display_v622 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                        json_file_v622 = gr.Textbox(value="", visible=False, show_label=False)
                        json_md_v622 = gr.Markdown(value="")
                    with gr.Column():
                        gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                        shuye_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                        shuye = gr.Textbox(label="输液", placeholder="", value="", show_label=True, interactive=False, lines=21)
                        note_md = gr.Markdown(value="括号中内容为匹配数据表后的药品名称。")
                        shuye_btn = gr.Button(value="生成输液", variant="primary")

            with gr.Tab("v6.2.3-处置"):
                v623_name = gr.Textbox(value="v623", visible=False)
                with gr.Row():
                    with gr.Accordion(label="JSON", open=True, visible=True):
                        json_display_v623 = gr.JSON(value={}, visible=True, label="JSON", show_label=False, open=True)
                        json_file_v623 = gr.Textbox(value="", visible=False, show_label=False)
                        json_md_v623 = gr.Markdown(value="")
                    with gr.Column():
                        gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                        chuzhi_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                        chuzhi = gr.Textbox(label="处置", placeholder="", value="", show_label=True, interactive=False, lines=21)
                        chuzhi_btn = gr.Button(value="生成处置", variant="primary")

        with gr.TabItem("v6.3-其他方案"):
            v63_interfaces = [
                (v631_interface, "v6.3.1-手术治疗", "v631"),
                (v632_interface, "v6.3.2-化疗", "v632"),
                (v633_interface, "v6.3.3-放疗", "v633"),
                (v634_interface, "v6.3.4-心理治疗", "v634"),
                (v635_interface, "v6.3.5-康复治疗", "v635"),
                (v636_interface, "v6.3.6-物理治疗", "v636"),
                (v637_interface, "v6.3.7-替代疗法", "v637"),
                (v638_interface, "v6.3.8-观察治疗", "v638")
            ]
            show_table=['v631','v632','v633','v634','v635','v636','v637','v638']
            with gr.Blocks(analytics_enabled=False) as v63_app:
                for i, l, id in v63_interfaces:
                    if id not in show_table:
                        continue
                    with gr.TabItem(l, id=id, visible=True):
                        i.render()

        duofangan_btn.click(fetch_responsev6,
            inputs=[json_display_v6, json_file_v61, json_md_v61, duofangan, duofangan_json, v6_name, json_display_v621, json_display_v622, json_display_v623,
json_display_v631, json_display_v632, json_display_v633, json_display_v634, json_display_v635, json_display_v636, json_display_v637, json_display_v638],
            outputs=[json_file_v61, json_md_v61, duofangan, duofangan_json, json_display_v621, json_display_v622, json_display_v623,
json_display_v631, json_display_v632, json_display_v633, json_display_v634, json_display_v635, json_display_v636, json_display_v637, json_display_v638]
        )
        chufang_btn.click(fetch_responsev6_each,
            inputs=[json_display_v621, json_file_v621, json_md_v621, chufang, chufang_json, v621_name],
            outputs=[json_file_v621, json_md_v621, chufang, chufang_json]
        )
        shuye_btn.click(fetch_responsev6_each,
            inputs=[json_display_v622, json_file_v622, json_md_v622, shuye, shuye_json, v622_name],
            outputs=[json_file_v622, json_md_v622, shuye, shuye_json]
        )
        chuzhi_btn.click(fetch_responsev6_each,
            inputs=[json_display_v623, json_file_v623, json_md_v623, chuzhi, chuzhi_json, v623_name],
            outputs=[json_file_v623, json_md_v623, chuzhi, chuzhi_json]
        )
        shoushu_btn.click(fetch_responsev6_each,
            inputs=[json_display_v631, json_file_v631, json_md_v631, shoushu, shoushu_json, v631_name],
            outputs=[json_file_v631, json_md_v631, shoushu, shoushu_json]
        )
        hualiao_btn.click(fetch_responsev6_each,
            inputs=[json_display_v632, json_file_v632, json_md_v632, hualiao, hualiao_json, v632_name],
            outputs=[json_file_v632, json_md_v632, hualiao, hualiao_json]
        )
        fangliao_btn.click(fetch_responsev6_each,
            inputs=[json_display_v633, json_file_v633, json_md_v633, fangliao, fangliao_json, v633_name],
            outputs=[json_file_v633, json_md_v633, fangliao, fangliao_json]
        )
        xinli_btn.click(fetch_responsev6_each,
            inputs=[json_display_v634, json_file_v634, json_md_v634, xinli, xinli_json, v634_name],
            outputs=[json_file_v634, json_md_v634, xinli, xinli_json]
        )
        kangfu_btn.click(fetch_responsev6_each,
            inputs=[json_display_v635, json_file_v635, json_md_v635, kangfu, kangfu_json, v635_name],
            outputs=[json_file_v635, json_md_v635, kangfu, kangfu_json]
        )
        wuli_btn.click(fetch_responsev6_each,
            inputs=[json_display_v636, json_file_v636, json_md_v636, wuli, wuli_json, v636_name],
            outputs=[json_file_v636, json_md_v636, wuli, wuli_json]
        )
        tidai_btn.click(fetch_responsev6_each,
            inputs=[json_display_v637, json_file_v637, json_md_v637, tidai, tidai_json, v637_name],
            outputs=[json_file_v637, json_md_v637, tidai, tidai_json]
        )
        guancha_btn.click(fetch_responsev6_each,
            inputs=[json_display_v638, json_file_v638, json_md_v638, guancha, guancha_json, v638_name],
            outputs=[json_file_v638, json_md_v638, guancha, guancha_json]
        )

    with gr.Blocks(analytics_enabled=False) as v5_interface:
        v5_name = gr.Textbox(value="v5", visible=False)
        with gr.Row():
            with gr.Column():
                with gr.Accordion(label="JSON", open=True, visible=True):
                    json_display_v5 = gr.JSON(value=json_data['v5'], visible=True, label="JSON", show_label=False, open=True)
                json_file = gr.Textbox(value="", visible=False, show_label=False)
                json_md = gr.Markdown(value="")
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                jiancha_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                jiancha = gr.Textbox(label="检查与化验", placeholder="", value="", show_label=True, interactive=False, lines=24)
                note_md = gr.Markdown(value="括号中内容为匹配数据表后的检查名称与化验名称。")
                with gr.Row():
                    jiancha_btn = gr.Button(value="生成检查与化验(json)", variant="primary")

        jiancha_btn.click(fetch_response_nochat,
            inputs=[json_display_v5, json_file, json_md, v5_name, jiancha, jiancha_json],
            outputs=[json_file, json_md, jiancha, jiancha_json]
        )

    with gr.Blocks(analytics_enabled=False) as v4_interface:
        v4_name = gr.Textbox(value="v4", visible=False)
        with gr.Row():
            with gr.Column():
                with gr.Accordion(label="JSON", open=True, visible=True):
                    json_display_v4 = gr.JSON(value=json_data['v4'], visible=True, label="JSON", show_label=False, open=True)
                with gr.Accordion(label="编辑病历", open=False, visible=True):
                    v4_patient_name = gr.Textbox(label="姓名", placeholder="Patient Name", value=json_display_v4.value['input']['client_info'][0]['patient']['patient_name'], show_label=True, interactive=True)
                    v4_patient_gender = gr.Textbox(label="性别", placeholder="Patient Gender", value=json_display_v4.value['input']['client_info'][0]['patient']['patient_gender'], show_label=True, interactive=True)
                    v4_patient_age = gr.Textbox(label="年龄", placeholder="Patient Age", value=json_display_v4.value['input']['client_info'][0]['patient']['patient_age'], show_label=True)
                    v4_zhusu = gr.Textbox(label="主诉", placeholder="Chief complaint", value=json_display_v4.value['input']['basic_medical_record']['chief_complaint'], show_label=True, interactive=True)
                    v4_xianbingshi = gr.Textbox(label="现病史", placeholder="history of present illness", value=json_display_v4.value['input']['basic_medical_record']['history_of_present_illness'], show_label=True, interactive=True)
                    v4_jiwangshi = gr.Textbox(label="既往史", placeholder="past medical history", value=json_display_v4.value['input']['basic_medical_record']['past_medical_history'], show_label=True, interactive=True)
                    v4_gerenshi = gr.Textbox(label="个人史", placeholder="personal history", value=json_display_v4.value['input']['basic_medical_record']['personal_history'], show_label=True, interactive=True)
                    v4_guominshi = gr.Textbox(label="过敏史", placeholder="allergy history", value=json_display_v4.value['input']['basic_medical_record']['allergy_history'], show_label=True, interactive=True)
                    v4_tigejiancha = gr.Textbox(label="体格检查", placeholder="pyhsical exam", value=json_display_v4.value['input']['basic_medical_record']['physical_examination'], show_label=True, interactive=True)
                    v4_fuzhujiancha = gr.Textbox(label="辅助检查", placeholder="auxiliary exam", value=json_display_v4.value['input']['basic_medical_record']['auxiliary_examination'], show_label=True)
                json_file = gr.Textbox(value="", visible=False, show_label=False)
                json_md = gr.Markdown(value="")
                with gr.Row():
                    send_jiancha = gr.Button(value="发送到 检查化验", variant="primary", scale=1, visible=False)
                    send_duofangan = gr.Button(value="发送到 多方案", variant="primary", scale=1, visible=False)
                    send_fuzhen = gr.Button(value="发送到 复诊", variant="primary", scale=1, visible=False)
            with gr.Column():
                gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                zhenduan_json = gr.JSON(value={}, label="JSON", show_label=False, visible=False, open=True)
                zhenduan = gr.Textbox(label="诊断结果", placeholder="", value="", show_label=True, interactive=False, lines=24)
                note_md = gr.Markdown(value="括号中内容为匹配数据表后的诊断名称。")
                with gr.Row():
                    zhenduan_btn = gr.Button(value="生成诊断(json)", variant="primary")
                    zhenduan_edit_btn = gr.Button(value="生成诊断(编辑病历)", variant="primary")

        zhenduan_btn.click(fetch_response_nochat,
            inputs=[json_display_v4, json_file, json_md, v4_name, zhenduan, zhenduan_json],
            outputs=[json_file, json_md, zhenduan, zhenduan_json, send_jiancha, send_duofangan, send_fuzhen]
        )
        zhenduan_edit_btn.click(fetch_response_edit,
            inputs=[v4_patient_name, v4_patient_gender, v4_patient_age, v4_zhusu, v4_xianbingshi, v4_jiwangshi, v4_gerenshi, v4_guominshi, v4_tigejiancha, v4_fuzhujiancha, json_file, json_md, v4_name, zhenduan, zhenduan_json],
            outputs=[json_file, json_md, zhenduan, zhenduan_json, send_jiancha, send_duofangan, send_fuzhen]
        )
        send_jiancha.click(send2somewhere,
            inputs=[zhenduan_json, json_display_v5, v5_name],
            outputs=[zhenduan_json, json_display_v5]
        ) 
        send_duofangan.click(send2somewhere,
            inputs=[zhenduan_json, json_display_v6, v6_name],
            outputs=[zhenduan_json, json_display_v6]
        )
        send_fuzhen.click(send2somewhere,
            inputs=[zhenduan_json, json_display_v7, v7_name],
            outputs=[zhenduan_json, json_display_v7]
        )


    with gr.Blocks(analytics_enabled=False) as v3_interface:
        v3_name = gr.Textbox(value="v3", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True):
                json_display_v3 = gr.JSON(value=json_data['v3'], visible=False, label="JSON", show_label=False, open=True)
                
                # code
                json_display_by_code = gr.Code(value=json.dumps(json_data['v3'], indent=4, ensure_ascii=False), language="json", label="Edit JSON String", interactive=True, max_lines=100)

                today = datetime.datetime.now()
                weeks = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
                current_date = f"""默认今天为：{today.year}年；{today.month}月；{today.day}日；{weeks[today.weekday()]}；"""
                today = gr.Textbox(value=current_date, show_label=False, interactive=False)
                json_file = gr.Textbox(value="", visible=False, show_label=False)
                json_md = gr.Markdown(value="")
            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["guahao"], value=max(prompt_versions["guahao"]), interactive=True, show_label=False, container=False)
                chatbot=gr.Chatbot(
                    label="Chat",
                    value=[[None, json_data['v3']['chat']['historical_conversations'][-2]['content']], [None, json_data['v3']['chat']['historical_conversations'][-1]['content']]],
                    show_label=True,
                    show_copy_button=True,
                    height=600
                )
                with gr.Row():
                    msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False)
                    send_btn = gr.Button(value="Send", variant="primary", scale=1)

        send_btn.click(v3,
            inputs=[msg, chatbot, json_display_v3, json_file, json_md, v3_name, prompt_version, model_name, json_display_by_code, today],
            outputs=[msg, chatbot, json_display_v3, json_file, json_md, v3_name, prompt_version, model_name, json_display_by_code, today]
        )
        msg.submit(
            user_response_v123, 
            inputs=[msg, chatbot, json_display_v3, json_file, json_md, v3_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v3, json_file, json_md, v3_name]
            ).then(
            fetch_response_v123,
            inputs=[msg, chatbot, json_display_v3, json_file, json_md, v3_name],
            outputs=[msg, chatbot, json_display_v3, json_file, json_md, v3_name]
        )


    with gr.Blocks(analytics_enabled=False) as v2_interface:
        v2_name = gr.Textbox(value="v2", visible=False)
        with gr.Row():
            with gr.Column():
                with gr.Accordion(label="JSON", open=True):
                    json_display_v2 = gr.JSON(value=json_data['v2'], visible=True, label="JSON", show_label=False, open=True)
                    json_file = gr.Textbox(value="", visible=False, show_label=False)
                    json_md = gr.Markdown(value="")
                with gr.Row():
                    send_zhenduan = gr.Button(value="发送到 诊断", variant="primary", scale=1, visible=True)
            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["yuwenzhen"], value=max(prompt_versions["yuwenzhen"]), interactive=True, show_label=False, container=False)
                chatbot=gr.Chatbot(
                    label="Chat",
                    value=[[None, json_data['v2']['chat']['historical_conversations'][-1]['content']]],
                    show_label=True,
                    show_copy_button=True,
                    height=600
                )
                with gr.Row():
                    msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False)
                    send_btn = gr.Button(value="Send", variant="primary", scale=1)
        send_btn.click(v2,
            inputs=[msg, chatbot, json_display_v2, json_file, json_md, v2_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v2, json_file, json_md, v2_name, prompt_version, model_name]
        )
        msg.submit(
            user_response_v123, 
            inputs=[msg, chatbot, json_display_v2, json_file, json_md, v2_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v2, json_file, json_md, v2_name,],
            ).then(
            fetch_response_v123,
            inputs=[msg, chatbot, json_display_v2, json_file, json_md, v2_name,],
            outputs=[msg, chatbot, json_display_v2, json_file, json_md, v2_name,],
        )
        send_zhenduan.click(send2somewhere,
            inputs=[json_display_v2, json_display_v4, v4_name],
            outputs=[json_display_v2, json_display_v4, v4_patient_name, v4_patient_gender, v4_patient_age, v4_zhusu, v4_xianbingshi, v4_jiwangshi, v4_gerenshi, v4_guominshi, v4_tigejiancha, v4_fuzhujiancha]
        )

    with gr.Blocks(analytics_enabled=False) as v1_interface:
        v1_name = gr.Textbox(value="v1", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True):
                json_display_v1 = gr.JSON(value=json_data['v1'], visible=True, label="JSON", show_label=False, open=True)
                json_file = gr.Textbox(value="", visible=False, show_label=False)
                json_md = gr.Markdown(value="")

            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["jiandang"], value=max(prompt_versions["jiandang"]), interactive=True, show_label=False, container=False)
                chatbot=gr.Chatbot(
                    label="Chat",
                    value=[[None, json_data['v1']['chat']['historical_conversations'][-1]['content']]],
                    show_label=True,
                    show_copy_button=True,
                    height=600
                )
                with gr.Row():
                    msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False,interactive=True, visible=True)
                    send_btn = gr.Button(value="Send", variant="primary", scale=1)
        send_btn.click(v1,              
            inputs=[msg, chatbot, json_display_v1, json_file, json_md, v1_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v1, json_file, json_md, v1_name, prompt_version, model_name]
        )
        msg.submit(
            user_response_v123, 
            inputs=[msg, chatbot, json_display_v1, json_file, json_md, v1_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v1, json_file, json_md, v1_name]
            ).then(
            fetch_response_v123,
            inputs=[msg, chatbot, json_display_v1, json_file, json_md, v1_name],
            outputs=[msg, chatbot, json_display_v1, json_file, json_md, v1_name]
        )

    with gr.Blocks(analytics_enabled=False) as v0_interface:
        v0_name = gr.Textbox(value="v0", visible=False)
        with gr.Row():
            with gr.Accordion(label="JSON", open=True):
                json_display_v0 = gr.JSON(value=json_data['v0'], visible=True, label="JSON", show_label=False, open=True)
                json_file = gr.Textbox(value="", visible=False, show_label=False)
                json_md = gr.Markdown(value="")

            with gr.Column():
                model_name = gr.Dropdown(label="Model Name", choices=[args.model], value=args.model, interactive=True, show_label=False, container=False)
                prompt_version = gr.Dropdown(label="Prompt Version", choices=prompt_versions["agent"], value=max(prompt_versions["agent"]), interactive=True, show_label=False, container=False)
                chatbot=gr.Chatbot(
                    label="Chat",
                    value=[[None, json_data['v0']['chat']['historical_conversations'][-1]['content']]],
                    show_label=True,
                    show_copy_button=True,
                    height=600
                )
                with gr.Row():
                    msg = gr.Textbox(placeholder="Type a message", scale=7, show_label=False)
                    send_btn = gr.Button(value="Send", variant="primary", scale=1)
        send_btn.click(v0,
            inputs=[msg, chatbot, json_display_v0, json_file, json_md, v0_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v0, json_file, json_md, v0_name, prompt_version, model_name]
        )

        msg.submit(
            user_response_v123,
            inputs=[msg, chatbot, json_display_v0, json_file, json_md, v0_name, prompt_version, model_name],
            outputs=[msg, chatbot, json_display_v0, json_file, json_md, v0_name]
            ).then(
            fetch_response_v123,
            inputs=[msg, chatbot, json_display_v0, json_file, json_md, v0_name],
            outputs=[msg, chatbot, json_display_v0, json_file, json_md, v0_name]
        )

    interfaces = [
        (v0_interface, "v0-智能体", "v0_fenfa"),
        (v1_interface, "v1-建档", "v1_jiandang"),
        (v2_interface, "v2-预问诊", "v2_yuwenzhen"),
        (v3_interface, "v3-挂号", "v3_guahao"),
        (v4_interface, "v4-诊断", "v4_zhenduan"),
        (v5_interface, "v5-检查化验", "v5_jiancha"),
        (v6_interface, "v6-多方案", "v6_duofangan"),
        (v7_interface, "v7-复诊", "v0_fuzhen")
    ]

    with gr.Blocks(
        title="Seafarer Medical AI",
        theme="soft"
    ) as app:
        for i, l, id in interfaces:
            with gr.TabItem(l, id=id):
                i.render()
    return app

if __name__ == "__main__":
    app = build_app()
    app.queue(
        default_concurrency_limit=args.concurrency_count,
        api_open=True,
        status_update_rate=10,
    ).launch(
        server_name=args.host,
        server_port=args.gradio_port,
        share=args.share,
        max_threads=200,
        auth=None
    )
