import sys
import os
from typing import List, Union
from pydantic import BaseModel, Field

import sys
import os
import copy
from datetime import datetime, timedelta
import json
import asyncio
import aiohttp
import pandas as pd
import re
import argparse


current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
src_dir = os.path.join(parent_dir, 'src')
sys.path.append(src_dir)
from diagnosis_treatment.util_data_models import *

TEMPLETE_JSON_FILE = "./data/register_test_templete.json"
TEMPLETE_CHAT_INFO_FILE = "./data/register_chat_info.json"
OUTPUT_FILE_NAME = "register_test_output.xlsx"
DEFAULT_PROMPT_VERSION = "v4"

def args_parser():
    parser = argparse.ArgumentParser(description='register test with Customizable Parameters')
    parser.add_argument("--host", type=str, default="127.0.0.1", help="The inference server ip")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument('--input-file', type=str, default=TEMPLETE_CHAT_INFO_FILE, help='output register check file name')
    parser.add_argument('--output-file', type=str, default=OUTPUT_FILE_NAME, help='output register check file name')
    parser.add_argument('--prompt-version', type=str, default=DEFAULT_PROMPT_VERSION, help='prompt version')
    args = parser.parse_args()
    return args

args = args_parser()

# 假设的 API 地址和请求头
url = f"http://{args.host}:{args.port}/inference?request_type=v3"
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# 用于存储结果的列表
results = []
def replace_register_request_info(request_obj, doctor_name :str, date_input :str,  begin_time :str, end_time :str, prompt_version :str):
    # 替换 [医生姓名]
    if 'output' in request_obj and 'hospital_register' in request_obj['output']:
        for hospital in request_obj['output']['hospital_register']:
            for doctor in hospital['doctor_list']:
                doctor['doctor_name'] = doctor_name

    # 替换 [日期]
    if 'output' in request_obj and 'hospital_register' in request_obj['output']:
        for hospital in request_obj['output']['hospital_register']:
            for doctor in hospital['doctor_list']:
                for date_info in doctor['date_list']:
                    date_info['date'] = date_input

    # 替换 [开始时间] 和 [结束时间]
    if 'output' in request_obj and 'hospital_register' in request_obj['output']:
        for hospital in request_obj['output']['hospital_register']:
            for doctor in hospital['doctor_list']:
                for date_info in doctor['date_list']:
                    for time_info in date_info['time_list']:
                        time_info['start_time'] = begin_time
                        time_info['end_time'] = end_time

    # 替换 chat 部分的占位符
    if 'chat' in request_obj:
        for conversation in request_obj['chat']['historical_conversations_bak'] + request_obj['chat']['historical_conversations']:
            conversation['content'] = conversation['content'].replace('[医生姓名]', doctor_name)
            conversation['content'] = conversation['content'].replace('[日期]', date_input)
            conversation['content'] = conversation['content'].replace('[开始时间]', begin_time)
            conversation['content'] = conversation['content'].replace('[结束时间]', end_time)
        if 'prompt_version' in request_obj['chat']:
            request_obj['chat']['prompt_version'] = prompt_version
    

def read_json_file(file_path: str):
    try:
        with open(file_path, 'r', encoding='utf-8') as json_file:
            read_json_data = json.load(json_file)
            return read_json_data
    except FileNotFoundError:
        print("未找到指定的 JSON 文件，请检查文件路径。")
    except json.JSONDecodeError:
        print("JSON 文件格式错误，请检查文件内容。")
    except Exception as e:
        print(f"发生未知错误: {e}")


def add_30_minutes(time_str):
    time_obj = datetime.strptime(time_str, '%H:%M')
    new_time_obj = time_obj + timedelta(minutes=30)
    new_time_str = new_time_obj.strftime('%H:%M')
    return new_time_str


def extract_front_content(input_str):
    # 查找第一个 '{"input":' 出现的位置
    match = re.search(r'\{"input":', input_str)
    if match:
        start_index = match.start()
        return input_str[:start_index], input_str[start_index:]
    return input_str, ""


async def process_case(session, case_name, case_content, templete_data):
    print(f"开始处理 {case_name}")
    case_results = []
    i = 0
    templete_data_case = copy.deepcopy(templete_data)
    while i < len(case_content) - 1:
        system_info = case_content[i].get("系统")
        user_speech = case_content[i + 1].get("用户")
        if system_info and user_speech:
            if isinstance(system_info, dict):
                print(f"*** system_info register time {system_info['挂号时间']}")
                end_time = add_30_minutes(system_info["挂号时间"])
                replace_register_request_info(templete_data_case, system_info["医生姓名"], system_info["挂号日期"], system_info["挂号时间"], end_time, args.prompt_version)
                
            user_chat_data = {"role": "user",
                "content": user_speech}
            templete_data_case['chat']['historical_conversations_bak'].append(user_chat_data)
            templete_data_case['chat']['historical_conversations'].append(user_chat_data)
            
            try:
                test_answer = ""
                async with session.post(url, json=templete_data_case, headers=headers) as response:
                    # test_answer = await response.text()
                    # print(f"{case_name} - 请求结果: {test_answer}\n")
                    # 检查响应状态码
                    if response.status == 200:
                        # 以流式方式读取响应内容
                        async for chunk in response.content.iter_chunked(65536*2):
                            try:
                                chunk_text  = chunk.decode('utf-8')
                                test_answer = test_answer + chunk_text
                            except UnicodeDecodeError:
                                print("无法解码部分数据块")
                    else:
                        print(f"请求失败，状态码: {response.status}")

                test_answer_front, test_answer_back = extract_front_content(test_answer)

                register_intention_info = ""
                try:
                    test_answer_obj = json.loads(test_answer_back)
                    # request_v3_info = RequestV3(**test_answer_obj)
                    register_intention_info = test_answer_obj['output']['register_intention_info']
                    print(f" register_intention_info answer: {register_intention_info}")
                except json.JSONDecodeError as e:
                    print(f"test_answer_back JSON 解析错误: {e}")

                print(f"{case_name} - answer: {test_answer_front}")
                test_answer_data = {"role": "assistant",
                    "content": test_answer_front}
                
                case_results.append({
                    "case_name": case_name,
                    "system_info": system_info,
                    "user_speech": user_speech,
                    "openai_api_response": test_answer_front,
                    "register_intention_info": register_intention_info
                })
                templete_data_case['chat']['historical_conversations_bak'].append(test_answer_data)
                templete_data_case['chat']['historical_conversations'].append(test_answer_data)

            except Exception as e:
                print(f"{case_name} - 请求出错: {e}")
        i += 2
    print(f"{case_name} 处理完成 \n")
    return case_results

async def main():
    batch_size = 15
    tasks = []
    all_results = []
    chat_info_data = read_json_file(args.input_file)
    register_template_data = read_json_file(TEMPLETE_JSON_FILE)
    async with aiohttp.ClientSession() as session:
        for case_name, case_content in chat_info_data.items():
            task = asyncio.create_task(process_case(session, case_name, case_content, register_template_data))
            tasks.append(task)
            if len(tasks) >= batch_size:
                results = await asyncio.gather(*tasks)
                # 按 case 顺序整理结果
                for case_result in results:
                    all_results.extend(case_result)

                tasks = []
        if tasks:
            results = await asyncio.gather(*tasks)
            # 按 case 顺序整理结果
            for case_result in results:
                all_results.extend(case_result)

        # 将结果写入 Excel 文件
        df = pd.DataFrame(all_results)

        # 在不同的 case 之间添加空行
        new_df = pd.DataFrame()
        current_case = None
        for index, row in df.iterrows():
            if current_case is None:
                current_case = row["case_name"]
            elif row["case_name"] != current_case:
                empty_row = pd.DataFrame([[None] * len(df.columns)], columns=df.columns)
                new_df = pd.concat([new_df, empty_row], ignore_index=True)
                current_case = row["case_name"]
            new_df = pd.concat([new_df, pd.DataFrame([row])], ignore_index=True)

        new_df.to_excel(args.output_file, index=False)

if __name__ == "__main__":
    asyncio.run(main())