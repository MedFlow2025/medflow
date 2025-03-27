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

import re

def extract_json_and_text(answer):
    # Check conversation, extract medical records or medical checklists
    case_format_1 = r'{(.*?)}'
    case_format_2 = r'\[(.*?)\]'
    case_format_3 = r'{(.*?)}]}'
    # case_format_3 = r'\[{(.*?)}\]}\]'
    case_format_4 = r'{(.*?)]}'
    case_format_5 = r'{(.*?)}}}'
    case_format_6 = r'{(.*?)}}'
    #case_format_6 = r'{(.*?)}}}}'
    case_format_7 = r'{(.*?)}(.*?)}'
    answer_new = answer.replace("\n", "").replace("\t", "").replace(" ", "")
    json_match = re.search(case_format_3, answer_new, re.DOTALL)
    text_match = re.sub(case_format_3, '', answer_new, flags=re.DOTALL).strip()
    #if not json_match:
    #    json_match = re.search(case_format_6, answer_new , re.DOTALL)
    #    text_match = re.sub(case_format_6, '', answer_new, flags=re.DOTALL).strip()
    if not json_match:
        json_match = re.search(case_format_5, answer_new , re.DOTALL)
        text_match = re.sub(case_format_5, '', answer_new, flags=re.DOTALL).strip()
    if not json_match:
        json_match = re.search(case_format_6, answer_new , re.DOTALL)
        text_match = re.sub(case_format_6, '', answer_new, flags=re.DOTALL).strip()
    if not json_match:
        json_match = re.search(case_format_4, answer_new , re.DOTALL)
        text_match = re.sub(case_format_4, '', answer_new, flags=re.DOTALL).strip()
    if not json_match:
        json_match = re.search(case_format_2, answer_new , re.DOTALL)
        text_match = re.sub(case_format_2, '', answer_new, flags=re.DOTALL).strip()
    if not json_match:
        json_match = re.search(case_format_7, answer_new , re.DOTALL)
        text_match = re.sub(case_format_7, '', answer_new, flags=re.DOTALL).strip()
    if not json_match:
        json_match = re.search(case_format_1, answer_new , re.DOTALL)
        text_match = re.sub(case_format_1, '', answer_new, flags=re.DOTALL).strip()
    return json_match, text_match