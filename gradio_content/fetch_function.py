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
import gradio as gr
import datetime
import copy
import httpx
import numpy as np
import pandas as pd
from inference_gradio import args
import requests
import re
import random

path = os.getcwd()

v3_last_test_date = datetime.datetime.now().date()
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
def update_v3_current_date(json_display_by_code_str : str):
    global v3_last_test_date
    test_days = random.randint(1, 10)
    today = datetime.datetime.now() + datetime.timedelta(days=test_days)
    # today = datetime.datetime.now()
    weeks = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    current_date_str  = f"""默认今天为：{today.year}年；{today.month}月；{today.day}日；{weeks[today.weekday()]}；"""
    current_date = today.date()
    if v3_last_test_date is None or current_date != v3_last_test_date:
        # 如果历史日期为空或者当前日期和历史日期不同，则更新 JSON 数据, 这里需要将日期字符串更改为指定字符
        json_display_by_code = json.loads(json_display_by_code_str)
        updated_data = replace_dates(json_display_by_code)
        json_display_by_code_str = json.dumps(updated_data, ensure_ascii=False, indent=4)
        json_data['v3'] = updated_data
        v3_last_test_date = current_date
        # print(f"***lmx*** update_v3_current_date {current_date_str}      current_date {current_date}    v3_last_test_date {v3_last_test_date} ")
        return json_data['v3'], json_display_by_code_str, current_date_str
    else:
        return None, None, None

def read_json():
    json_files = [f for f in os.listdir(f"{path}/gradio_content") if f.endswith('.json')]
    json_data = {}
    for i, v in enumerate(json_files):
        v_name = v.replace(".json", "")
        with open(os.path.join(f"{path}/gradio_content", v), 'r', encoding='utf-8') as f:
            json_data[v_name] = json.load(f)
            if v_name == "v3":
                json_data[v_name] = replace_dates(json_data[v_name])

    return json_data

json_data = read_json()

def chat_process(messages, history, json_diaplay_v, json_file, json_v:str):
    if json_file == "":
        params = copy.deepcopy(json_data[json_v])
        unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        file_name = f"{json_v}-{unique_id}.json"
    else:
        file_name = json_file
        params = json_diaplay_v
    hc = params['chat']['historical_conversations']
    hc_bak = params['chat']['historical_conversations_bak']
    hc.append({'role':'user', 'content':str(messages)})

    return params, file_name 

def write_to_file(json_file, json_display):
    stop_sign = [
        '现在为您返回',
        '已经为您生成了预问诊报告，如无问题，请点击确认',
        '为您生成病历',
        '如下预约就诊，您看是否可以？',
        '抱歉，目前没有查询到',
        '生成治疗方法'
    ]
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

def send2somewhere(from_data, to_data, vn):
    # if not os.path.exists(json_file):
    #     json_md = f"Failed to open {json_file}"
    match vn:#to
        case "v4":
            to_data['input']['client_info'] = from_data['input']['client_info']
            to_data['input']['basic_medical_record'] = from_data['output']['basic_medical_record']
            patient_name = from_data['input']['client_info'][0]['patient']['patient_name']
            patient_gender = from_data['input']['client_info'][0]['patient']['patient_gender']
            patient_age = from_data['input']['client_info'][0]['patient']['patient_age']
            zhusu = from_data['output']['basic_medical_record']['chief_complaint']
            xianbingshi = from_data['output']['basic_medical_record']['history_of_present_illness']
            jiwangshi = from_data['output']['basic_medical_record']['past_medical_history']
            gerenshi = from_data['output']['basic_medical_record']['personal_history']
            guominshi = from_data['output']['basic_medical_record']['allergy_history']
            tigejiancha = from_data['output']['basic_medical_record']['physical_examination']
            fuzhujiancha = from_data['output']['basic_medical_record']['auxiliary_examination']
            return from_data, to_data, patient_name, patient_gender, patient_age, zhusu, xianbingshi, jiwangshi, gerenshi, guominshi, tigejiancha, fuzhujiancha
        case "v5"|"v6":
            to_data['input']['client_info'] = from_data['input']['client_info']
            to_data['input']['basic_medical_record'] = from_data['input']['basic_medical_record']
            to_data['input']['diagnosis'] = from_data['output']['diagnosis']
            return from_data, to_data
        case "v7":
            to_data = json_data['v7']
            to_data['input']['client_info'] = from_data['input']['client_info']
            to_data['input']['basic_medical_record'] = from_data['input']['basic_medical_record']
            to_data['input']['diagnosis'] = from_data['output']['diagnosis']
            to_data['output']['return_visit']['summary'] = ""
            to_data['output']['return_visit']['if_visit'] = ""
            to_data['chat']['historical_conversations_bak'] = []
            to_data['chat']['historical_conversations'] = []
            return from_data, to_data

async def fetch_response(msg, chatbot, json_display_v, json_file, json_md, vn, send_zhenduan):
    params, json_file = chat_process(msg, chatbot, json_display_v, json_file, vn)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    url = f"http://{args.host}:{args.port}/inference?request_type={vn}"
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, headers=headers, json=params, timeout=600) as response:
            response_json = None
            if response.status_code == 200:
                response_str = ""
                async for chunk in response.aiter_bytes(chunk_size=65536 * 2):
                    chunk=chunk.decode('utf-8')
                    response_str += chunk
                    print(chunk)
                if '{"input":' and "output" in chunk:
                    json_str = '{"input":' + chunk.split('{"input":')[1]
                    response_json = json.loads(json_str)
                else:
                    print(f"error response {response_str}")
            if response_json:
                print(f"\n请求结果:{response_json}")
                new_history = [v['content'] for v in response_json['chat']['historical_conversations']]
                if len(new_history) % 2:
                    new_history.insert(0, None)
                new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
                new_history = new_history.tolist()
                json_display_v = response_json

                write_flag = write_to_file(json_file, json_display_v)
                if write_flag == True:
                    json_md=f"""Successfully! write data to {json_file}.
    \nSuccessfully! write data to {str(json_file).replace('json', 'xlsx')}."""
                    if vn == "v2": 
                        return None, new_history, json_display_v, json_file, json_md, vn #, gr.update(visible=True) # to do check file exist
                else:
                    #json_md="no write."
                    json_md=""

                return None, new_history, json_display_v, json_file, json_md, vn

            else:
                return "Error: Unable to fetch response from inference API."

def fetch_response_v123(msg, chatbot, json_display_v, json_file, json_md, vn,):
    params, json_file = chat_process(msg, chatbot, json_display_v, json_file, vn)
    url = 'http://' + str(args.host) + ':' + str(args.port) + '/inference?request_type=' + vn
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    response = requests.post(url, headers=headers,stream=True,json=params)  
    json_display_dict=params
    list_new={'role': 'assistant', 'content': ''}
    json_display_dict['chat']['historical_conversations'].append(list_new)

    if response.status_code == 200:
        answer=""
        for chunk in response.iter_content(chunk_size=65536*2):
            chunk=chunk.decode('utf-8')
            if "input" and "output" in chunk:
                out_json=chunk
                print(f"\n请求结果:{out_json}")
                out_dict = json.loads(out_json)
                new_history = [v['content'] for v in out_dict['chat']['historical_conversations']]
                if len(new_history) % 2:
                    new_history.insert(0, None)
                new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
                new_history = new_history.tolist()
                json_display_v = out_dict
                write_flag = write_to_file(json_file, json_display_v)
                if write_flag == True:
                    json_md=f"""Successfully! write data to {json_file}.
    \nSuccessfully! write data to {str(json_file).replace('json', 'xlsx')}."""
                    if vn == "v2": 
                        yield None, new_history, json_display_v, json_file, json_md, vn
                        return
                else:
                    #json_md="no write."
                    json_md=""
                
            else:
                answer+=chunk
                json_display_dict['chat']['historical_conversations'][-1]['content']=answer
                new_history = [v['content'] for v in json_display_dict['chat']['historical_conversations']]
                if len(new_history) % 2:
                    new_history.insert(0, None)
                new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
                new_history = new_history.tolist()
                json_display_v = json_display_dict
                yield None, new_history, json_display_v, json_file, json_md, vn
        
        out_dict = json.loads(out_json)
        new_history = [v['content'] for v in out_dict['chat']['historical_conversations']]
        if len(new_history) % 2:
            new_history.insert(0, None)
        new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
        new_history = new_history.tolist()
        json_display_v = out_dict

        yield None, new_history, json_display_v, json_file, json_md, vn
        return
    else:
        yield None ,"Error: Unable to fetch response from inference API." , None, None, None, None
        return


async def fetch_response_nochat(json_display_v, json_file, json_md, vn, results, results_json):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"{vn}-{unique_id}.json"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/inference?request_type={vn}",
            json=json_display_v,
            timeout=30,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json = response.json()
            results = ""
            if vn == "v4":
                for v in response.json()['output']['diagnosis']:
                    results += f"【{v['diagnosis_name']}（{v['diagnosis_name_retrieve']}）    {v['diagnosis_code']}    {v['diagnosis_identifier']}】\n"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""
                return json_file, json_md, results, results_json, gr.update(visible=True), gr.update(visible=True), gr.update(visible=True)
            if vn == "v5":
                for v in response.json()['output']['examine_content']:
                    exam_cd = "、".join([j['diagnosis_name'] for j in v['corresponding_diagnosis']])
                    results += f"【检查名称: {v['examine_name']}（{v['examine_name_retrieve']}）】\n检查编号: {v['examine_code']}\n检查类别: {v['examine_category']}\n开单数量: {v['order_quantity']}\n针对疾病: {exam_cd}\n\n\n"
                for v in response.json()['output']['assay_content']:
                    assay_cd = "、".join([j['diagnosis_name'] for j in v['corresponding_diagnosis']])
                    results += f"【化验名称: {v['assay_name']}（{v['assay_name_retrieve']}）】\n化验编号: {v['assay_code']}\n化验类别: {v['assay_category']}\n开单数量: {v['order_quantity']}\n针对疾病: {assay_cd}\n\n\n"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""
                return json_file, json_md, results, results_json 
        else:
            return "Error: Unable to fetch response from inference API."

async def fetch_response_edit(patient_name, patient_gender, patient_age, zhusu, xianbingshi, jiwangshi, gerenshi, guominshi, tigejiancha, fuzhujiancha, 
    json_file, json_md, vn, results, results_json):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"{vn}-{unique_id}.json"
    json_display_v = json_data[vn]
    json_display_v['input']['client_info'][0]['patient']['patient_name'] = patient_name
    json_display_v['input']['client_info'][0]['patient']['patient_gender'] = patient_gender
    json_display_v['input']['client_info'][0]['patient']['patient_age'] = patient_age
    json_display_v['input']['basic_medical_record']['chief_complaint'] = zhusu
    json_display_v['input']['basic_medical_record']['history_of_present_illness'] = xianbingshi
    json_display_v['input']['basic_medical_record']['past_medical_history'] = jiwangshi
    json_display_v['input']['basic_medical_record']['personal_history'] = gerenshi
    json_display_v['input']['basic_medical_record']['allergy_history'] = guominshi
    json_display_v['input']['basic_medical_record']['physical_examination'] = tigejiancha
    json_display_v['input']['basic_medical_record']['auxiliary_examination'] = fuzhujiancha
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/inference?request_type={vn}",
            json=json_display_v,
            timeout=30,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json = response.json()
            results = ""
            if vn == "v4":
                for v in response.json()['output']['diagnosis']:
                    results += f"【{v['diagnosis_name']}（{v['diagnosis_name_retrieve']}）    {v['diagnosis_code']}    {v['diagnosis_identifier']}】\n"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""

                return json_file, json_md, results, results_json, gr.update(visible=True), gr.update(visible=True), gr.update(visible=True)
        else:
            return "Error: Unable to fetch response from inference API."

async def fetch_responsev6(json_display_v6, json_file_v61, json_md_v61, duofangan, duofangan_json, vn, json_display_v621, json_display_v622, json_display_v623,
    json_display_v631, json_display_v632, json_display_v633, json_display_v634, json_display_v635, json_display_v636, json_display_v637, json_display_v638):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file_v61 = f"{vn}-{unique_id}.json"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/inference?request_type={vn}&scheme=pick_therapy",
            json=json_display_v6,
            timeout=60,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            duofangan_json = response.json()
            json_display_v621 = response.json()
            json_display_v622 = response.json()
            json_display_v623 = response.json()
            json_display_v631 = response.json()
            json_display_v632 = response.json()
            json_display_v633 = response.json()
            json_display_v634 = response.json()
            json_display_v635 = response.json()
            json_display_v636 = response.json()
            json_display_v637 = response.json()
            json_display_v638 = response.json()
            duofangan = ""
            therapy_map = {
                "default_therapy": "保守治疗",
                "surgical_therapy": "手术治疗",
                "chemo_therapy": "化疗",
                "radiation_therapy": "放疗",
                "psycho_therapy": "心理治疗",
                "rehabilitation_therapy": "康复治疗",
                "physical_therapy": "物理治疗",
                "alternative_therapy": "替代疗法",
                "observation_therapy": "观察治疗"
            }
            for i, v in enumerate(response.json()['output']['pick_therapy']):
                duofangan += f"【{therapy_map[v['picked_therapy']]}】\n{v['interpret_therapy']}\n\n\n"
            with open(json_file_v61, 'w', encoding='utf-8') as f:
                json.dump((duofangan_json), f, ensure_ascii=False, indent=4)
            f.close()
            json_md_v61=f"""Successfully! write data to {json_file_v61}."""

            return json_file_v61, json_md_v61, duofangan, duofangan_json, json_display_v621, json_display_v622, json_display_v623, \
json_display_v631, json_display_v632, json_display_v633, json_display_v634, json_display_v635, json_display_v636, json_display_v637, json_display_v638
        else:
            return "Error: Unable to fetch response from inference API."

async def fetch_responsev6_each(json_display_v, json_file_v, json_md_v, results, results_json, vn):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file_v = f"{vn}-{unique_id}.json"
    match vn:
        case "v621":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=default_therapy&sub_scheme=prescription"
        case "v622":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=default_therapy&sub_scheme=transfusion"
        case "v623":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=default_therapy&sub_scheme=disposition"
        case "v631":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=surgical_therapy"
        case "v632":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=chemo_therapy"
        case "v633":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=radiation_therapy"
        case "v634":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=psycho_therapy"
        case "v635":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=rehabilitation_therapy"
        case "v636":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=physical_therapy"
        case "v637":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=alternative_therapy"
        case "v638":
            url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme=other_therapy&sub_scheme=observation_therapy"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=json_display_v,
            timeout=90,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json = response.json()
            results = ""
            match vn:
                case "v621":
                    for i, v in enumerate(response.json()['output']['default_therapy']['prescription'][0]['prescription_content']):
                        results += f"""【药品名称: {v['drug_name']}  （{v['drug_name_retrieve']}）】
适应疾病: {v['corresponding_diseases']}
药品作用: {v['drug_efficacy']}
药品信息: 
    药品编号: {[v['drug_id']]}
    药品规格: {v['drug_specification']}
    用药途径: {v['route_of_administration']}
开药信息:
    开单数量: {v['order_quantity']}
    开单单位: {v['order_unit']}
    单次剂量: {v['dosage']}
    用药频次: {v['frequency']}
    持续时间: {v['duration']}\n\n\n"""
                case "v622":
                    for i, v in enumerate(response.json()['output']['default_therapy']['transfusion'][0]['transfusion_content']):
                        results += f"""【药品名称: {v['drug_name']}  （{v['drug_name_retrieve']}）】
适应疾病: {v['corresponding_diseases']}
药品作用: {v['drug_efficacy']}
药品信息: 
    药品编号: {[v['drug_id']]}
    药品规格: {v['drug_specification']}
    用药途径: {v['route_of_administration']}
开药信息:
    开单数量: {v['order_quantity']}
    开单单位: {v['order_unit']}
    单次剂量: {v['dosage']}
    用药频次: {v['frequency']}
    持续时间: {v['duration']}
    输液分组: {v['infusion_group']}
    输液速度: {v['infusion_rate']}\n\n\n"""
                case "v623":
                    for i, v in enumerate(response.json()['output']['default_therapy']['disposition'][0]['disposition_content']):
                        results += f"""【处置名称: {v['disposition_name']}】\n处置编号: {v['disposition_id']}\n单次用量: {v['dosage']}\n处置频次: {v['frequency']}\n持续时间: {v['duration']}\n\n\n"""
                case "v631":
                    for i, v in enumerate(response.json()['output']['surgical_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v632":
                    for i, v in enumerate(response.json()['output']['chemo_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v633":
                    for i, v in enumerate(response.json()['output']['radiation_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v634":
                    for i, v in enumerate(response.json()['output']['psycho_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v635":
                    for i, v in enumerate(response.json()['output']['rehabilitation_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v636":
                    for i, v in enumerate(response.json()['output']['physical_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v637":
                    for i, v in enumerate(response.json()['output']['alternative_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""
                case "v638":
                    for i, v in enumerate(response.json()['output']['observation_therapy']['method'][0]['methodtherapy_content']):
                        results += f"""【治疗名称: {v['method_name']}】\n治疗编号: {v['method_code']}\n治疗类型: {v['method_type']}\n\
适用疾病: {v['corresponding_diseases']}\n治疗计划: {v['method_plan']}\n潜在风险: {v['method_risk']}\n\n\n"""

            with open(json_file_v, 'w', encoding='utf-8') as f:
                json.dump((results_json), f, ensure_ascii=False, indent=4)
            f.close()
            json_md_v=f"""Successfully! write data to {json_file_v}."""
            return json_file_v, json_md_v, results, results_json
        else:
            return "Error: Unable to fetch response from inference API."
