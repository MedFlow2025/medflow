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
from .tabs import *
from ..util import inference_gradio_json_data
from ..config import prompt_versions, REGISTER_INTENTION_TYPE
from ..logic.handlers import *
from frontend.ui.quality_tab import create_quality_inspect_interface, create_quality_modify_interface

def create_interface_hospitalguide():
    with gr.Blocks(analytics_enabled=False) as interface_hospitalguide:
        build_chat_tab(
            module_name="hospitalguide",
            json_data=inference_gradio_json_data['hospitalguide_simple'],
            prompt_name=prompt_versions["hospitalguide"],
            default_chat=None,
            function=hospitalguide,
            note="simple为“简单对话”生成主诉与推荐科室。<br>detailed根据已有主诉，“详细对话”生成预问诊报告。",
            use_branch=True,
            branch_content={"label":"HospitalGuide Type", "choices": ["simple", "detailed"], "value": "simple"}
        )
    return interface_hospitalguide

def create_interface_returnvisit():
    with gr.Blocks(analytics_enabled=False) as interface_returnvisit:
        json_display, module = build_chat_tab(
            module_name="returnvisit",
            #json_data={},
            json_data=inference_gradio_json_data['returnvisit'],
            prompt_name=prompt_versions["returnvisit"],
            default_chat=None,
            function=returnvisit,
            note="请先点击“疾病诊断”页面“生成诊断”，再点击“发送到 患者复诊”。"
        )
    return interface_returnvisit, json_display, module

def create_interface_hospitalregister():
    with gr.Blocks(analytics_enabled=False) as interface_hospitalregister:
        build_chat_tab(
            module_name="hospitalregister",
            json_data=inference_gradio_json_data['hospitalregister'],
            prompt_name=prompt_versions["hospitalregister"],
            default_chat=[[None, inference_gradio_json_data['hospitalregister']['chat']['historical_conversations'][-2]['content']], [None, inference_gradio_json_data['hospitalregister']['chat']['historical_conversations'][-1]['content']]],
            function=hospitalregister,
            use_branch=True,
            branch_content={"label":"Register Intention Tpye", "choices": REGISTER_INTENTION_TYPE, "value": max(REGISTER_INTENTION_TYPE)}
        )
    return interface_hospitalregister

def create_interface_basicmedicalrecord(json_display_diagnosis, diagnosis):
    with gr.Blocks(analytics_enabled=False) as interface_basicmedicalrecord:
        json_display, module = build_chat_tab(
            module_name="basicmedicalrecord",
            json_data=inference_gradio_json_data['basicmedicalrecord'],
            prompt_name=prompt_versions["basicmedicalrecord"],
            default_chat=[[None, inference_gradio_json_data['basicmedicalrecord']['chat']['historical_conversations'][-1]['content']]],
            function=basicmedicalrecord
        )
        build_send_button(
            btn_config=[
                {"label": "发送到 疾病诊断", "display": json_display_diagnosis, "module": diagnosis, "visible": True},
            ],
            result_json=json_display
        )
    return interface_basicmedicalrecord

def create_interface_clientinfo():
    with gr.Blocks(analytics_enabled=False) as interface_clientinfo:
        build_chat_tab(
            module_name="clientinfo",
            json_data=inference_gradio_json_data['clientinfo'],
            prompt_name=prompt_versions["clientinfo"],
            default_chat=[[None, inference_gradio_json_data['clientinfo']['chat']['historical_conversations'][-1]['content']]],
            function=clientinfo
        )
    return interface_clientinfo

def create_interface_distribute():
    with gr.Blocks(analytics_enabled=False) as interface_distribute:
        build_chat_tab(
            module_name="distribute",
            json_data=inference_gradio_json_data['distribute'],
            prompt_name=prompt_versions["distribute"],
            default_chat=[[None, inference_gradio_json_data['distribute']['chat']['historical_conversations'][-1]['content']]],
            function=distribute
        )
    return interface_distribute

def create_interface_doctormedicalrecord():
    with gr.Blocks(analytics_enabled=False) as interface_doctormedicalrecord:
        build_nochat_tab(
            module_name="doctormedicalrecord",
            json_data=inference_gradio_json_data['doctormedicalrecord_general'],
            prompt_name=prompt_versions["doctormedicalrecord"],
            module_label="病历",
            btn_name="生成病历",
            function=fetch_response_nochat,
            use_branch=True,
            branch_content={"label":"MedicalRecord Type", "choices": ["general", "special", "special_modify", "special_select"], "value": "general"}
        )
    return interface_doctormedicalrecord

def create_interface_examass():
    with gr.Blocks(analytics_enabled=False) as interface_examass:
        json_display, module, *args = build_nochat_tab(
            module_name="examass",
            json_data=inference_gradio_json_data['examass'],
            prompt_name=prompt_versions["examass"],
            module_label="检查与化验",
            btn_name="生成检查与化验",
            function=fetch_response_nochat,
            note="括号中内容为匹配数据表后的检查名称与化验名称。<br>请先点击“疾病诊断”页面“生成诊断”，再点击“发送到 检查化验开具”。",
        )
    return interface_examass, json_display, module

def create_interface_diagnosis(json_display_examass, examass, json_display_scheme, scheme, json_display_returnvisit, returnvisit):
    with gr.Blocks(analytics_enabled=False) as interface_diagnosis:
        json_display, module, result_json, send_btn, json_file, json_md, result_text, branch = build_nochat_tab(
            module_name="diagnosis",
            json_data=inference_gradio_json_data['diagnosis'],
            prompt_name=prompt_versions["diagnosis"],
            module_label="诊断",
            btn_name="生成诊断",
            function=fetch_response_nochat,
            note="括号中内容为匹配数据表后的诊断名称。"
        )
        extra_btns = build_send_button(
            btn_config=[
                {"label": "发送到 检查化验", "display": json_display_examass, "module": examass, "visible": False},
                {"label": "发送到 治疗方案", "display": json_display_scheme, "module": scheme, "visible": False},
                {"label": "发送到 患者复诊", "display": json_display_returnvisit, "module": returnvisit, "visible": False}
            ],
            result_json=result_json
        )
        #send_btn.click(fetch_response_nochat,
        #    inputs=[json_display, json_file, module],
        #    outputs=[json_file, json_md, result_text, result_json, *extra_btns]
        #)
        send_btn.click(fetch_response_nochat,
            inputs=[json_display, json_file, module, json_md, result_text, result_json, branch],
            outputs=[json_display, json_file, module, json_md, result_text, result_json, branch, *extra_btns]
        )
    return interface_diagnosis, json_display, module

def create_interface_scheme():
    with gr.Blocks(analytics_enabled=False) as interface_scheme_surgical:
        json_display_surgical, *args = build_nochat_tab(
            module_name="surgical",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="手术治疗",
            btn_name="生成手术治疗",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_chemo:
        json_display_chemo, *args = build_nochat_tab(
            module_name="chemo",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="化学治疗",
            btn_name="生成化学治疗",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_radiation:
        json_display_radiation, *args = build_nochat_tab(
            module_name="radiation",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="放射治疗",
            btn_name="生成放射治疗",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_psycho:
        json_display_psycho, *args = build_nochat_tab(
            module_name="psycho",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="心理治疗",
            btn_name="生成心理治疗",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_rehabilitation:
        json_display_rehabilitation, *args = build_nochat_tab(
            module_name="rehabilitation",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="康复治疗",
            btn_name="生成康复治疗",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_physical:
        json_display_physical, *args = build_nochat_tab(
            module_name="physical",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="物理治疗",
            btn_name="生成物理治疗",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_alternative:
        json_display_alternative, *args = build_nochat_tab(
            module_name="alternative",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="替代疗法",
            btn_name="生成替代疗法",
            function=fetch_response_sub_scheme
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_observation:
        json_display_observation, *args = build_nochat_tab(
            module_name="observation",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="观察治疗",
            btn_name="生成观察治疗",
            function=fetch_response_sub_scheme
        )

    with gr.Blocks(analytics_enabled=False) as interface_scheme_prescription:
        json_display_prescription, *args = build_nochat_tab(
            module_name="prescription",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="处方",
            btn_name="生成处方",
            function=fetch_response_sub_scheme,
            note="括号中内容为匹配数据表后的药品名称。"
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_transfusion:
        json_display_transfusion, *args = build_nochat_tab(
            module_name="transfusion",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="输液",
            btn_name="生成输液",
            function=fetch_response_sub_scheme,
            note="括号中内容为匹配数据表后的药品名称。"
        )
    with gr.Blocks(analytics_enabled=False) as interface_scheme_disposition:
        json_display_disposition, *args = build_nochat_tab(
            module_name="disposition",
            json_data={},
            prompt_name=prompt_versions["scheme"],
            module_label="处置",
            btn_name="生成处置",
            function=fetch_response_sub_scheme
        )

    with gr.Blocks(analytics_enabled=False) as interface_scheme:
        with gr.TabItem("🗳️ 挑选方案"):
            json_display, module, result_json, send_btn, json_file, json_md, result_text, *args = build_nochat_tab(
                module_name="scheme",
                json_data=inference_gradio_json_data['scheme'],
                prompt_name=prompt_versions["scheme"],
                module_label="多方案",
                btn_name="生成多方案",
                function=fetch_response_scheme,
                note="请先点击“疾病诊断”页面“生成诊断”，再点击“发送到 治疗方案”。"
            )
        with gr.TabItem("💊 默认方案"):
            build_multi_tabs([
                (interface_scheme_prescription, "处方", "prescription", True),
                (interface_scheme_transfusion, "输液", "transfusion", True),
                (interface_scheme_disposition, "处置", "disposition", True)
            ])
        with gr.TabItem("📑 其他方案"):
            build_multi_tabs([
                (interface_scheme_surgical, "手术治疗", "surgical", True),
                (interface_scheme_chemo, "化疗", "chemo", True),
                (interface_scheme_radiation, "放疗", "radiation", True),
                (interface_scheme_psycho, "心理治疗", "psycho", True),
                (interface_scheme_rehabilitation, "康复治疗", "rehabilitation", True),
                (interface_scheme_physical, "物理治疗", "physical", True),
                (interface_scheme_alternative, "替代疗法", "alternative", True),
                (interface_scheme_observation, "观察治疗", "observation", True)
            ])

        send_btn.click(fetch_response_scheme,
            inputs=[json_display, json_file, module],
            outputs=[json_file, json_md, result_text, result_json,
                json_display_prescription, json_display_transfusion, json_display_disposition,
                json_display_surgical, json_display_chemo, json_display_radiation, json_display_psycho,
                json_display_rehabilitation, json_display_physical, json_display_alternative, json_display_observation
            ]
        )

    return interface_scheme, json_display, module

interface_examass, json_display_examass, examass = create_interface_examass()
interface_scheme, json_display_scheme, scheme = create_interface_scheme()
interface_returnvisit, json_display_returnvisit, return_visit = create_interface_returnvisit()
interface_diagnosis, json_display_diagnosis, diagnosis = create_interface_diagnosis(
    json_display_examass, examass, json_display_scheme, scheme, json_display_returnvisit, return_visit
)

interface_distribute = create_interface_distribute()
interface_clientinfo = create_interface_clientinfo()
interface_basicmedicalrecord = create_interface_basicmedicalrecord(json_display_diagnosis, diagnosis)
inteface_hospitalregister = create_interface_hospitalregister()

interface_hospitalguide = create_interface_hospitalguide()
interface_doctormedicalrecord = create_interface_doctormedicalrecord()

quality_modify_interface, json_display_quality_modify = create_quality_modify_interface()
quality_inspect_interface = create_quality_inspect_interface(json_display_quality_modify)