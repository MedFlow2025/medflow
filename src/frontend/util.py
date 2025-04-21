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
import json
import datetime
import pandas as pd
import re
import random

path = os.getcwd()

hospitalregister_last_test_date = datetime.datetime.now().date()
# Define recursive functions to traverse JSON data and replace dates
def replace_dates(data):
    current_date = datetime.datetime.now().date()
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = replace_dates(value)
    elif isinstance(data, list):
        return [replace_dates(item) for item in data]
    elif isinstance(data, str):
        def replace_match(match):
            day_number = int(match.group(1))
            new_date = current_date + datetime.timedelta(days=day_number)
            return str(new_date)
        return re.sub(r'test_timeinfo_day_(\d+)', replace_match, data)
    return data

# 定义更新当前日期信息的函数
def update_hospitalregister_current_date(json_display_by_code_str : str):
    global hospitalregister_last_test_date
    test_days = random.randint(1, 10)
    today = datetime.datetime.now() + datetime.timedelta(days=test_days)
    # today = datetime.datetime.now()
    weeks = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    current_date_str  = f"""默认今天为：{today.year}年；{today.month}月；{today.day}日；{weeks[today.weekday()]}；"""
    current_date = today.date()
    if hospitalregister_last_test_date is None or current_date != hospitalregister_last_test_date:
        # 如果历史日期为空或者当前日期和历史日期不同，则更新 JSON 数据, 这里需要将日期字符串更改为指定字符
        json_display_by_code = json.loads(json_display_by_code_str)
        updated_data = replace_dates(json_display_by_code)
        json_display_by_code_str = json.dumps(updated_data, ensure_ascii=False, indent=4)
        json_data['hospitalregister'] = updated_data
        hospitalregister_last_test_date = current_date
        # print(f"***lmx*** update_hospitalregister_current_date {current_date_str}      current_date {current_date}    hospitalregister_last_test_date {hospitalregister_last_test_date} ")
        return json_data['hospitalregister'], json_display_by_code_str, current_date_str
    else:
        return None, None, None

def get_current_date():
    today = datetime.datetime.now()
    weeks = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    current_date = f"""默认今天为：{today.year}年；{today.month}月；{today.day}日；{weeks[today.weekday()]}；"""
    return current_date

def read_json():
    json_files = [f for f in os.listdir(f"{path}/frontend/data") if f.endswith('.json')]
    json_data = {}
    for i, v in enumerate(json_files):
        v_name = v.replace(".json", "")
        with open(os.path.join(f"{path}/frontend/data", v), 'r', encoding='utf-8') as f:
            json_data[v_name] = json.load(f)
            if v_name == "hospitalregister":
                json_data[v_name] = replace_dates(json_data[v_name])
    return json_data

def write_to_file(json_file, json_display):
    from diagnosis_treatment.prompt_template import stop_sign
    write_flag = False
    user_content = []
    assistant_content = []
    hc = json_display['chat']['historical_conversations']
    c1 = json_display['chat']['historical_conversations_bak'][-1]['content']
    c2 = json_display['chat']['historical_conversations_bak'][-2]['content']
    for i in stop_sign:
        if i in c1:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump((json_display), f, ensure_ascii=False, indent=4)
            f.close()

            for j in range(0, len(hc), 2):
                user_content.append(hc[j].get('content'))
                assistant_content.append(hc[j+1].get('content') if j+1 < len(hc) else '')
            df = pd.DataFrame({
                '轮次': range(len(user_content)),
                '患者 User': user_content,
                '模型 Assistant': assistant_content,
                '问题': ['' for n in user_content]
            })
            xlsx_file = str(json_file).replace('json', 'xlsx')
            df.to_excel(f"{path}/{xlsx_file}", index=False)
            write_flag = True
        if i in c2:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump((json_display), f, ensure_ascii=False, indent=4)
            f.close()

            for j in range(0, len(hc), 2):
                user_content.append(hc[j].get('content'))
                assistant_content.append(hc[j+1].get('content') if j+1 < len(hc) else '')
            df = pd.DataFrame({
                '轮次': range(len(user_content)),
                '患者 User': user_content,
                '模型 Assistant': assistant_content,
                '问题': ['' for n in user_content]
            })
            xlsx_file = str(json_file).replace('json', 'xlsx')
            df.to_excel(f"{path}/{xlsx_file}", index=False)
            write_flag = True
    return write_flag

inference_gradio_json_data = read_json()
