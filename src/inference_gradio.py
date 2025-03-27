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
from frontend.diagnosis_treatment_tab import *
from frontend.quality_tab import create_quality_inspect_interface, create_quality_modify_interface
from frontend.util import args


def build_app():
    v5_interface, json_display_v5, v5_name = create_v5_interface()
    v6_interface, json_display_v6, v6_name = create_v6_interface()
    v7_interface, json_display_v7, v7_name = create_v7_interface()
    v4_interface, json_display_v4, v4_name, v4_patient_name, v4_patient_gender, v4_patient_age, \
        v4_zhusu, v4_xianbingshi, v4_jiwangshi, v4_gerenshi, v4_guominshi, v4_tigejiancha, v4_fuzhujiancha = (
        create_v4_interface(json_display_v5, v5_name, json_display_v6, v6_name, json_display_v7, v7_name))
    v2_interface = create_v2_interface(json_display_v4, v4_name, v4_patient_name, v4_patient_gender, v4_patient_age,
        v4_zhusu, v4_xianbingshi, v4_jiwangshi, v4_gerenshi, v4_guominshi, v4_tigejiancha, v4_fuzhujiancha)
    v8_interface = create_v8_interface()
    v9_interface = create_v9_interface()

    quality_modify_interface, json_display_quality_modify = create_quality_modify_interface()
    quality_inspect_interface = create_quality_inspect_interface(json_display_quality_modify)

    interfaces = [
        (create_v0_interface(), "v0-智能体", "v0_fenfa"),
        (create_v1_interface(), "v1-建档", "v1_jiandang"),
        (v2_interface, "v2-预问诊", "v2_yuwenzhen"),
        (create_v3_interface(), "v3-挂号", "v3_guahao"),
        (v4_interface, "v4-诊断", "v4_zhenduan"),
        (v5_interface, "v5-检查化验", "v5_jiancha"),
        (v6_interface, "v6-多方案", "v6_duofangan"),
        (v7_interface, "v7-复诊", "v7_fuzhen"),
        (v8_interface, "v8-导诊", "v8_daozhen"),
        (v9_interface, "v9-病历", "v9_bingli"),
        (quality_inspect_interface, "质检-检验", "quality_inspect"),
        (quality_modify_interface, "质检-对话修改", "quality_modify")
    ]

    with gr.Blocks(title="Seafarer Medical AI", theme="soft") as app:
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