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
import requests
from ..util import inference_gradio_json_data, write_to_file
from ..config import args, inference_gradio_http_common_headers
from diagnosis_treatment.prompt_template import (
    reversed_medical_fields,
    reversed_sub_medical_fields,
    reversed_therapy_scheme_fields,
    request_type_map,
    therapy_scheme_map
)

path = os.getcwd()

async def distribute(msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name):
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return *(await fetch_response(msg, json_display, json_file, module)), prompt_version, model_name

async def clientinfo(msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name):
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return *(await fetch_response(msg, json_display, json_file, module)), prompt_version, model_name

async def basicmedicalrecord(msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name):
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return *(await fetch_response(msg, json_display, json_file, module)), prompt_version, model_name

async def hospitalregister(msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name):
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return *(await fetch_response(msg, json_display, json_file, module)), prompt_version, model_name

async def returnvisit(msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name):
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return *(await fetch_response(msg, json_display, json_file, module)), prompt_version, model_name

async def hospitalguide(msg, chatbot, json_display, json_file, module, json_md, branch, prompt_version, model_name):
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return *(await fetch_response(msg, json_display, json_file, module, branch)), prompt_version, model_name

def chat_process(messages, json_diaplay_v, json_file, json_v:str, branch=None):
    if json_file == "":
        if branch != None:
            json_v = json_v + "_" + branch
        params = copy.deepcopy(inference_gradio_json_data[json_v])
        unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        file_name = f"{json_v}-{unique_id}.json"
    else:
        file_name = json_file
        params = json_diaplay_v
    hc = params['chat']['historical_conversations']
    #hc_bak = params['chat']['historical_conversations_bak']
    hc.append({'role':'user', 'content':str(messages)})

    return params, file_name

def send_to_tab(from_data, to_data, module):
    from_data = json.loads(from_data)
    to_data = json.loads(to_data)
    match module:#to
        case "diagnosis":
            to_data['input']['client_info'] = from_data['input']['client_info']
            to_data['input']['basic_medical_record'] = from_data['output']['basic_medical_record']
        case "examass" | "scheme":
            to_data['input'].update({'client_info': from_data['input']['client_info'],
                'basic_medical_record': from_data['input']['basic_medical_record'],
                'diagnosis': from_data['output']['diagnosis']})
        case "returnvisit":
            to_data = inference_gradio_json_data['returnvisit']
            to_data['input'].update({'client_info': from_data['input']['client_info'],
                'basic_medical_record': from_data['input']['basic_medical_record'],
                'diagnosis': from_data['output']['diagnosis']})
            to_data['output']['return_visit'].update({'summary': "", 'if_visit': ""})
            to_data['chat'].update({'historical_conversations_bak': [], 'historical_conversations': []})
    from_data = json.dumps(from_data, ensure_ascii=False, indent=4)
    to_data = json.dumps(to_data, ensure_ascii=False, indent=4)
    return from_data, to_data

async def fetch_response(msg, json_display, json_file, module, branch=None):
    json_display = json.loads(json_display)
    if module == "hospitalguide":
        params, json_file = chat_process(msg, json_display, json_file, module, branch)
        url = f"http://{args.host}:{args.port}/inference?request_type={request_type_map[module]}&scheme={branch}"
    else:
        params, json_file = chat_process(msg, json_display, json_file, module)
        url = f"http://{args.host}:{args.port}/inference?request_type={request_type_map[module]}"

    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, headers=inference_gradio_http_common_headers, json=params, timeout=600) as response:
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
                json_display = response_json

                write_flag = write_to_file(json_file, json_display)
                json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
                if write_flag == True:
                    json_md=f"""Successfully! write data to {json_file}.
    \nSuccessfully! write data to {str(json_file).replace('json', 'xlsx')}."""
                else:
                    #json_md="no write."
                    json_md=""

                return None, new_history, json_display, json_file, module, json_md, branch


            else:
                return "Error: Unable to fetch response from inference API."

def user_response_stream(json_display, prompt_version, model_name):
    # chatbot = chatbot + [[msg, None]]
    json_display = json.loads(json_display)
    json_display['chat']['prompt_version'] = prompt_version
    json_display['chat']['model_name'] = model_name
    json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
    return json_display

def fetch_response_stream(msg, json_display, json_file, module, branch=None):
    json_display = json.loads(json_display)
    if module == "hospitalguide":
        params, json_file = chat_process(msg, json_display, json_file, module, branch)
        url = 'http://' + str(args.host) + ':' + str(args.port) + '/inference?request_type=' + request_type_map[module] + "&scheme=" + str(branch)
    else:
        params, json_file = chat_process(msg, json_display, json_file, module)
        url = 'http://' + str(args.host) + ':' + str(args.port) + '/inference?request_type=' + request_type_map[module]
    response = requests.post(url, headers=inference_gradio_http_common_headers,stream=True,json=params)
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
                json_display = out_dict
                write_flag = write_to_file(json_file, json_display)
                json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
                if write_flag == True:
                    json_md=f"""Successfully! write data to {json_file}.
    \nSuccessfully! write data to {str(json_file).replace('json', 'xlsx')}."""
                    if module == "basicmedicalrecord": 
                        yield None, new_history, json_display, json_file, json_md
                        return
                else:
                    #json_md="no write."
                    json_md=""
                
            else:
                json_md=""
                answer+=chunk
                json_display_dict['chat']['historical_conversations'][-1]['content']=answer
                new_history = [v['content'] for v in json_display_dict['chat']['historical_conversations']]
                if len(new_history) % 2:
                    new_history.insert(0, None)
                new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
                new_history = new_history.tolist()
                json_display = json_display_dict
                json_display = json.dumps(json_display, ensure_ascii=False, indent=4)
                yield None, new_history, json_display, json_file, json_md
        
        out_dict = json.loads(out_json)
        new_history = [v['content'] for v in out_dict['chat']['historical_conversations']]
        if len(new_history) % 2:
            new_history.insert(0, None)
        new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
        new_history = new_history.tolist()
        json_display = out_dict
        json_display = json.dumps(json_display, ensure_ascii=False, indent=4)

        yield None, new_history, json_display, json_file, json_md
        return
    else:
        yield None ,"Error: Unable to fetch response from inference API." , None, None, None, None
        return

async def fetch_response_nochat(json_display, json_file, module, json_md, result_text, result_json, branch=None):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"{module}-{unique_id}.json"
    json_display_dict = json.loads(json_display)
    if module == "doctormedicalrecord":
        url = f"http://{args.host}:{args.port}/inference?request_type={request_type_map[module]}&scheme={branch}"
    else:
        url = f"http://{args.host}:{args.port}/inference?request_type={request_type_map[module]}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=json_display_dict,
            timeout=240,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json = response.json()
            results = ""
            if module == "diagnosis":
                for v in response.json()['output']['diagnosis']:
                    results += f"【{v['diagnosis_name']}（{v['diagnosis_name_retrieve']}）    {v['diagnosis_code']}    {v['diagnosis_identifier']}】\n"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""
                results_json = json.dumps(results_json, ensure_ascii=False, indent=4)
                return json_display, json_file, module, json_md, results, results_json, branch, gr.update(visible=True), gr.update(visible=True), gr.update(visible=True)

            if module == "examass":
                for v in response.json()['output']['examine_content']:
                    exam_cd = "、".join([j['diagnosis_name'] for j in v['corresponding_diagnosis']])
                    results += f"""【检查名称: {v['examine_name']}（{v['examine_name_retrieve']}）】
检查编号: {v['examine_code']}
检查类别: {v['examine_category']}
开单数量: {v['order_quantity']}
针对疾病: {exam_cd}\n\n\n"""
                for v in response.json()['output']['assay_content']:
                    assay_cd = "、".join([j['diagnosis_name'] for j in v['corresponding_diagnosis']])
                    results += f"""【化验名称: {v['assay_name']}（{v['assay_name_retrieve']}）】
化验编号: {v['assay_code']}
化验类别: {v['assay_category']}
开单数量: {v['order_quantity']}
针对疾病: {assay_cd}\n\n\n"""
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""
                results_json = json.dumps(results_json, ensure_ascii=False, indent=4)
                return json_display, json_file, module, json_md, results, results_json, branch

            if module == "doctormedicalrecord":
                basic_medical_record = response.json()['output']['basic_medical_record']
                for key, value in basic_medical_record.items():
                    if not isinstance(value, dict):
                        results += f"【{reversed_medical_fields[key]}】：{value}\n" if value != "" else ""
                    else:
                        if not all(v == "" for v in value.values()):
                            results += f"【{reversed_medical_fields[key]}】\n"
                            for k, v in value.items(): results += f"  {reversed_sub_medical_fields[k]}: {v}\n" if v != "" else ""
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""
                results_json = json.dumps(results_json, ensure_ascii=False, indent=4)
                return json_display, json_file, module, json_md, results, results_json, branch
        else:
            return "Error: Unable to fetch response from inference API."

async def fetch_response_scheme(json_display, json_file, module):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file= f"{module}-{unique_id}.json"
    json_display_dict = json.loads(json_display)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/inference?request_type={request_type_map[module]}&scheme=pick_therapy",
            json=json_display_dict,
            timeout=240,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            result_json = response.json()
            result_text = ""
            for i, v in enumerate(response.json()['output']['pick_therapy']):
                result_text += f"【{reversed_therapy_scheme_fields[v['picked_therapy']]}】\n{v['interpret_therapy']}\n\n\n"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump((result_json), f, ensure_ascii=False, indent=4)
            f.close()
            json_md=f"""Successfully! write data to {json_file}."""
            result_json=json_display_prescription=json_display_transfusion=json_display_disposition=json_display_surgical=json_display_chemo=json_display_radiation= \
            json_display_psycho=json_display_rehabilitation=json_display_physical=json_display_alternative=json_display_observation = json.dumps(result_json, ensure_ascii=False, indent=4)
            return json_file, json_md, result_text, result_json, json_display_prescription, json_display_transfusion, json_display_disposition, \
json_display_surgical, json_display_chemo, json_display_radiation, json_display_psycho, json_display_rehabilitation, json_display_physical, json_display_alternative, json_display_observation
        else:
            return "Error: Unable to fetch response from inference API."

async def fetch_response_sub_scheme(json_display, json_file, module, json_md, result_text, result_json, branch=None):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"{module}-{unique_id}.json"
    json_display_dict = json.loads(json_display)
    scheme = therapy_scheme_map[module]
    sub_scheme = module + "_therapy" if module not in ["prescription", "transfusion", "disposition"] else module
    url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme={scheme}&sub_scheme={sub_scheme}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=json_display_dict,
            timeout=240,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json = response.json()
            results = ""
            if scheme == "default_therapy":
                for i, v in enumerate(response.json()['output'][scheme][sub_scheme][0][sub_scheme+'_content']):
                    if module == "prescription":
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
                    if module == "transfusion":
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
                    if module == "disposition":
                        results += f"""【处置名称: {v['disposition_name']}】
处置编号: {v['disposition_id']}
单次用量: {v['dosage']}
处置频次: {v['frequency']}
持续时间: {v['duration']}\n\n\n"""
            if scheme == "other_therapy":
                for i, v in enumerate(response.json()['output'][module+"_therapy"]['method'][0]['methodtherapy_content']):
                    results += f"""【治疗名称: {v['method_name']}】
治疗编号: {v['method_code']}
治疗类型: {v['method_type']}
适用疾病: {v['corresponding_diseases']}
治疗计划: {v['method_plan']}
潜在风险: {v['method_risk']}\n\n\n"""

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump((results_json), f, ensure_ascii=False, indent=4)
            f.close()
            json_md=f"""Successfully! write data to {json_file}."""
            results_json = json.dumps(results_json, ensure_ascii=False, indent=4)
            return json_display, json_file, module, json_md, results, results_json, branch
        else:
            return "Error: Unable to fetch response from inference API."