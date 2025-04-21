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

prompt_versions = {
    "distribute": ["v1", "v2"],
    "clientinfo": ["v1", "v2", "v3", "v4"],
    "basicmedicalrecord": ["v1", "v2", "v3", "v4"],
    "hospitalregister": ["v1", "v2", "v3", "v4", "v5"],
    "diagnosis": ["v1", "v2"],
    "examass": ["v1", "v2"],
    "scheme": ["v1", "v2"],
    "returnvisit": ["v1", "v2"],
    "hospitalguide": ["v1", "v2"],
    "doctormedicalrecord": ["v1", "v2"],
    "quality_inspect": ["v1", "v2"],
    "quality_modify": ["v1", "v2"]
}

REGISTER_INTENTION_TYPE = ["base_tpye", "intention_tpye"]

inference_gradio_http_common_headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

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