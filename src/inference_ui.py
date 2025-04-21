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
from frontend.config import args
from frontend.ui.ui import (
    interface_distribute,
    interface_clientinfo,
    interface_basicmedicalrecord,
    inteface_hospitalregister,
    interface_diagnosis,
    interface_examass,
    interface_scheme,
    interface_returnvisit,
    interface_hospitalguide,
    interface_doctormedicalrecord,
    quality_inspect_interface,
    quality_modify_interface
)
from frontend.ui.tabs import build_multi_tabs

def build_app():
    with gr.Blocks(title="MedFlow", theme="soft") as app:
        with gr.Row():
            gr.Markdown("## **🏥 MedFlow**")
        with gr.Row():
            with gr.Column(scale=1, min_width="100px"):
                pre_btn = gr.Button("🩺 诊前模块", size="md")
                in_btn = gr.Button("🥼 诊中模块", size="md")
                post_btn = gr.Button("📋️ 诊后模块", size="md")
            with gr.Column(scale=15):
                with gr.Column(visible=True) as pre_section:
                    build_multi_tabs([
                        (interface_distribute, "️🏷️ 任务分发", "distribute", False),
                        (interface_clientinfo, "👤 患者建档", "clientinfo", True),
                        (interface_basicmedicalrecord, "🗣️ 症状预问诊", "basicmedicalrecord", True),
                        (interface_hospitalguide, "🪧 导诊推荐科室", "hospitalguide", True),
                        (inteface_hospitalregister, "🏢 智能挂号", "hospitalregister", True),
                    ])
                with gr.Column(visible=False) as in_section:
                    build_multi_tabs([
                        (quality_inspect_interface, "🔍 病历质检-检验", "quality_inspect", True),
                        (quality_modify_interface, "✍️ 病历质检-对话修改", "quality_modify", True),
                        (interface_doctormedicalrecord , "📄 病历生成", "doctormedicalrecord", True),
                        (interface_diagnosis, "🧬 疾病诊断", "diagnosis", True),
                        (interface_examass, "🧪 检查化验开具", "examass", True),
                        (interface_scheme, "🌿 治疗方案", "scheme", True),
                    ])
                with gr.Column(visible=False) as post_section:
                    build_multi_tabs([
                        (interface_returnvisit, "🔁 患者复诊", "returnvisit", True),
                    ])

        pre_btn.click(
            lambda: [gr.update(visible=(i==0)) for i in range(3)],
            outputs=[pre_section, in_section, post_section]
        )
        in_btn.click(
            lambda: [gr.update(visible=(i==1)) for i in range(3)],
            outputs=[pre_section, in_section, post_section]
        )
        post_btn.click(
            lambda: [gr.update(visible=(i==2)) for i in range(3)],
            outputs=[pre_section, in_section, post_section]
        )

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
