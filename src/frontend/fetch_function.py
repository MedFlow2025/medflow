
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
from .util import inference_gradio_json_data, inference_gradio_http_common_headers, args
from .util import write_to_file
from diagnosis_treatment.prompt_template import medical_fields

path = os.getcwd()
prompt_versions = {
    "agent": ["v1"],
    "jiandang": ["v1", "v2", "v3"],
    "yuwenzhen": ["v1", "v2", "v3"],
    "guahao": ["v1"],
    "fuzhen": ["v1"],
    "daozhen": ["v1"],
    "bingli": ["v1"]
}

async def v0(msg, json_display_v, json_file, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, json_display_v, json_file, vn)), prompt_version, model_name

async def v1(msg, json_display_v, json_file, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, json_display_v, json_file, vn)), prompt_version, model_name

async def v2(msg, json_display_v, json_file, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, json_display_v, json_file, vn)), prompt_version, model_name

async def v3(msg, json_display_v, json_file, vn, prompt_version, model_name, json_display_by_code, today): 
    # return await fetch_response(msg, chatbot, json_display_v, json_file)
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
    inference_gradio_json_data['v3'] = updated_data
    json_display_v = updated_data
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    result = await fetch_response(msg, json_display_v, json_file, vn)
    updated_json_data = result[2]
    updated_json_str = json.dumps(updated_json_data, indent=4, ensure_ascii=False)
    return (*result, prompt_version, model_name, updated_json_str, today)

async def v7(msg, json_display_v, json_file, vn, prompt_version, model_name):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, json_display_v, json_file, vn)), prompt_version, model_name

async def v8(msg, json_display_v, json_file, vn, prompt_version, model_name, test_branch):
    json_display_v['chat']['prompt_version'] = prompt_version
    json_display_v['chat']['model_name'] = model_name
    return *(await fetch_response(msg, json_display_v, json_file, vn, test_branch)), prompt_version, model_name


def chat_process(messages, json_diaplay_v, json_file, json_v:str, test_branch=None):
    if json_file == "":
        if test_branch != None:
            json_v = json_v + "_" + test_branch
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

def send2somewhere(from_data, to_data, vn):
    # if not os.path.exists(json_file):
    #     json_md = f"Failed to open {json_file}"
    match vn:#to
        case "v4":
            to_data['input']['client_info'] = from_data['input']['client_info']
            to_data['input']['basic_medical_record'] = from_data['output']['basic_medical_record']
            patient = from_data['input']['client_info'][0]['patient']
            record = from_data['output']['basic_medical_record']
            return (from_data, to_data, patient['patient_name'], patient['patient_gender'], patient['patient_age'],
                    record['chief_complaint'], record['history_of_present_illness'], record['past_medical_history'],
                    record['personal_history'], record['allergy_history'], record['physical_examination'], record['auxiliary_examination'])
        case "v5"|"v6":
            to_data['input'].update({'client_info': from_data['input']['client_info'],
                'basic_medical_record': from_data['input']['basic_medical_record'],
                'diagnosis': from_data['output']['diagnosis']})
            return from_data, to_data
        case "v7":
            to_data = inference_gradio_json_data['v7']
            to_data['input'].update({'client_info': from_data['input']['client_info'],
                'basic_medical_record': from_data['input']['basic_medical_record'],
                'diagnosis': from_data['output']['diagnosis']})
            to_data['output']['return_visit'].update({'summary': "", 'if_visit': ""})
            to_data['chat'].update({'historical_conversations_bak': [], 'historical_conversations': []})
            return from_data, to_data

async def fetch_response(msg, json_display_v, json_file, vn, test_branch=None):
    if vn == "v8":
        params, json_file = chat_process(msg, json_display_v, json_file, vn, test_branch)
        url = f"http://{args.host}:{args.port}/inference?request_type={vn}&scheme={test_branch}"
    else:
        params, json_file = chat_process(msg, json_display_v, json_file, vn)
        url = f"http://{args.host}:{args.port}/inference?request_type={vn}"

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
                json_display_v = response_json

                write_flag = write_to_file(json_file, json_display_v)
                if write_flag == True:
                    json_md=f"""Successfully! write data to {json_file}.
    \nSuccessfully! write data to {str(json_file).replace('json', 'xlsx')}."""
                    if vn == "v2": 
                        return None, new_history, json_display_v, json_file, json_md #, gr.update(visible=True) # to do check file exist
                else:
                    #json_md="no write."
                    json_md=""

                return None, new_history, json_display_v, json_file, json_md

            else:
                return "Error: Unable to fetch response from inference API."

def fetch_response_v123(msg, json_display_v, json_file, vn, test_branch=None):
    if vn == "v8":
        params, json_file = chat_process(msg, json_display_v, json_file, vn, test_branch)
        url = 'http://' + str(args.host) + ':' + str(args.port) + '/inference?request_type=' + vn + "&scheme=" + str(test_branch)
    else:
        params, json_file = chat_process(msg, json_display_v, json_file, vn)
        url = 'http://' + str(args.host) + ':' + str(args.port) + '/inference?request_type=' + vn
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
                json_display_v = out_dict
                write_flag = write_to_file(json_file, json_display_v)
                if write_flag == True:
                    json_md=f"""Successfully! write data to {json_file}.
    \nSuccessfully! write data to {str(json_file).replace('json', 'xlsx')}."""
                    if vn == "v2": 
                        yield None, new_history, json_display_v, json_file, json_md
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
                json_display_v = json_display_dict
                yield None, new_history, json_display_v, json_file, json_md
        
        out_dict = json.loads(out_json)
        new_history = [v['content'] for v in out_dict['chat']['historical_conversations']]
        if len(new_history) % 2:
            new_history.insert(0, None)
        new_history = np.array(new_history).reshape(int(len(new_history)/2),2)
        new_history = new_history.tolist()
        json_display_v = out_dict

        yield None, new_history, json_display_v, json_file, json_md
        return
    else:
        yield None ,"Error: Unable to fetch response from inference API." , None, None, None, None
        return


async def fetch_response_nochat(json_display_v, json_file, vn, test_branch=None):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"{vn}-{unique_id}.json"
    if vn == "v9":
        if test_branch == "template_modify":
            test_branch = "template"
        url = f"http://{args.host}:{args.port}/inference?request_type={vn}&scheme={test_branch}"
    else:
        url = f"http://{args.host}:{args.port}/inference?request_type={vn}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=json_display_v,
            timeout=240,
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
                return json_file, json_md, results, results_json 
            if vn == "v9":
                reversed_fields = {value: key for key, value in medical_fields.items()}
                for k, v in response.json()['output']['basic_medical_record'].items():
                    if v != "":
                        results += f"【{reversed_fields[k]}】：{v}\n"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump((results_json), f, ensure_ascii=False, indent=4)
                f.close()
                json_md=f"""Successfully! write data to {json_file}."""
                return json_file, json_md, results, results_json
        else:
            return "Error: Unable to fetch response from inference API."


async def fetch_response_edit(patient_name, patient_gender, patient_age, zhusu, xianbingshi, jiwangshi, gerenshi, guominshi, tigejiancha, fuzhujiancha, 
    json_file, vn):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file = f"{vn}-{unique_id}.json"
    json_display_v = inference_gradio_json_data[vn]
    patient = json_display_v['input']['client_info'][0]['patient']
    patient.update({'patient_name': patient_name, 'patient_gender': patient_gender, 'patient_age': patient_age})
    basic_medical_record_map={
        "chief_complaint": zhusu,
        "history_of_present_illness": xianbingshi,
        "past_medical_history": jiwangshi,
        "personal_history": gerenshi,
        "allergy_history": guominshi,
        "physical_examination": tigejiancha,
        "auxiliary_examination": fuzhujiancha
    }
    for attr in json_display_v['input']['basic_medical_record']:
        json_display_v['input']['basic_medical_record'][attr]= basic_medical_record_map.get(attr)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/inference?request_type={vn}",
            json=json_display_v,
            timeout=240,
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


async def fetch_responsev6(json_display_v6, json_file_v61, vn):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file_v61 = f"{vn}-{unique_id}.json"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{args.host}:{args.port}/inference?request_type={vn}&scheme=pick_therapy",
            json=json_display_v6,
            timeout=240,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            duofangan_json=json_display_v621=json_display_v622=json_display_v623=json_display_v631=json_display_v632=json_display_v633= \
            json_display_v634=json_display_v635=json_display_v636=json_display_v637=json_display_v638 = response.json()
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


async def fetch_responsev6_each(json_display_v, json_file_v, vn):
    unique_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    json_file_v = f"{vn}-{unique_id}.json"
    params_map={
        "v621": ["default_therapy", "prescription"],
        "v622": ["default_therapy", "transfusion"],
        "v623": ["default_therapy", "disposition"],
        "v631": ["other_therapy", "surgical_therapy"],
        "v632": ["other_therapy", "chemo_therapy"],
        "v633": ["other_therapy", "radiation_therapy"],
        "v634": ["other_therapy", "psycho_therapy"],
        "v635": ["other_therapy", "rehabilitation_therapy"],
        "v636": ["other_therapy", "physical_therapy"],
        "v637": ["other_therapy", "alternative_therapy"],
        "v638": ["other_therapy", "observation_therapy"]
    }
    url = f"http://{args.host}:{args.port}/inference?request_type=v6&scheme={params_map[vn][0]}&sub_scheme={params_map[vn][1]}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=json_display_v,
            timeout=240,
        )
        if response.status_code == 200:
            print(f"\n请求结果:{response.json()}")
            results_json = response.json()
            results = ""
            scheme = params_map[vn][0]
            sub_scheme = params_map[vn][1]
            if scheme == "default_therapy":
                for i, v in enumerate(response.json()['output'][scheme][sub_scheme][0][sub_scheme+'_content']):
                    if vn == "v621":
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
                    if vn == "v622":
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
                    if vn == "v623":
                        results += f"""【处置名称: {v['disposition_name']}】
处置编号: {v['disposition_id']}
单次用量: {v['dosage']}
处置频次: {v['frequency']}
持续时间: {v['duration']}\n\n\n"""
            if scheme == "other_therapy":
                for i, v in enumerate(response.json()['output'][params_map[vn][1]]['method'][0]['methodtherapy_content']):
                    results += f"""【治疗名称: {v['method_name']}】
治疗编号: {v['method_code']}
治疗类型: {v['method_type']}
适用疾病: {v['corresponding_diseases']}
治疗计划: {v['method_plan']}
潜在风险: {v['method_risk']}\n\n\n"""

            with open(json_file_v, 'w', encoding='utf-8') as f:
                json.dump((results_json), f, ensure_ascii=False, indent=4)
            f.close()
            json_md_v=f"""Successfully! write data to {json_file_v}."""
            return json_file_v, json_md_v, results, results_json
        else:
            return "Error: Unable to fetch response from inference API."


def user_response_v123(json_display_v, prompt_version, model_name):
        # chatbot = chatbot + [[msg, None]]
        json_display_v['chat']['prompt_version'] = prompt_version
        json_display_v['chat']['model_name'] = model_name
        return json_display_v