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

import copy
import datetime
import re
import random

from fastapi.encoders import jsonable_encoder
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, insert, select, text)
from sqlalchemy.engine.base import Engine
from .base_diagnosis_request_handler import BaseDiagnosisRequestHandler
from .prompt_template import *
from .util_data_models import *
from .util_sqlite_function import *
from .util import *
import io
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import ValidationError
from fastapi import HTTPException
import time

ADD_REGISTRATION_INFO_TO_PROMPT = False

class RegisterDiagnosisProcessChecker:
    def __init__(self, receive) -> None:
        self.hr_o = receive.output.hospital_register
        self.cd_o = receive.output.chosen_department

    def __check_department(self):
        return any(item.department_id in ["", None] or item.department_name in ["", None] for item in self.cd_o)

    def __check_register(self):
        return any(item.doctor_list[0].doctor_id in ["", None] or item.doctor_list[0].doctor_name in ["", None] for item in self.hr_o)

    def check(self):
        if self.__check_department(): return 31
        elif self.__check_register(): return 32
        else: return 33


class DatabaseSchema:
    def __init__(self, receive):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        self.metadata = MetaData()
        self.hr_i = receive.input.hospital_register
 
    def __create_table(self):
        self.register = Table(
            'register',
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('department_code', String, nullable=False),
            Column('department_name', String, nullable=False),
            Column('doctor_code', String, nullable=False),
            Column('doctor_name', String, nullable=False),
            Column('doctor_title', String, nullable=False),
            Column('date', String, nullable=False),
            Column('start_time', String, nullable=False),
            Column('end_time', String, nullable=False),
            Column('source_num', Integer, nullable=False)
        )

        self.metadata.create_all(self.engine)


    def __define_database(self):
        now = datetime.datetime.now().strftime('%Y%m%d%H%M')
        json_hr_i = jsonable_encoder(self.hr_i)
        i = 0
        list_hr_i = []
        for department_l in json_hr_i:
            department_id = department_l.get("department_id", "default_department_id")
            department_name = department_l.get("department_name", "default_department_name")
            for doctor_l in department_l.get("doctor_list", []):
                doctor_id = doctor_l.get("doctor_id", "default_doctor_id")
                doctor_name = doctor_l.get("doctor_name", "default_doctor_name")
                doctor_title = doctor_l.get("doctor_title", "default_doctor_title")
                date_list = doctor_l.get("date_list")
                if date_list is None:
                    date_list = []
                for date_l in date_list:
                    date = date_l.get("date", "default_date")
                    for time_l in date_l.get("time_list", []):
                        start_time = time_l.get("start_time", "default_start_time")
                        end_time = time_l.get("end_time", "default_end_time")
                        source_num = time_l.get("source_num", 0)
                        if int(date.replace("-", "") + start_time.replace(":", "")) >= int(now):
                            i += 1
                            list_hr_i.append([
                                i,
                                department_id,
                                department_name,
                                doctor_id,
                                doctor_name,
                                doctor_title,
                                date,
                                start_time,
                                end_time,
                                source_num
                            ])

        # insert data to database table
        col_name = [c.key for c in self.register.c]
        try:
            zip_hr_i = []
            for v in list_hr_i:
                zip_hr_i.append(dict(zip(col_name, v)))

            for v in zip_hr_i:
                stmt = insert(self.register).values(**v)
                with self.engine.begin() as connection:
                    cursor = connection.execute(stmt)
            print(f"Table created successfully: {self.register.name}")
        except Exception as e:
            print(f"Error inserting row into table: {self.register.name}.")
            

    def __test_database(self):
        #Tests whether the amount of inserted data is correct
        sql_str = f"SELECT COUNT(*) FROM register"
        with self.engine.connect() as con:
            rows = con.execute(text(sql_str))
        for row in rows:
            print(f"\nTEST Table {self.register.name}. Total Data: {row}\n")

    def run(self):
        self.__create_table()
        self.__define_database()
        self.__test_database()
        return self.engine


class RegisterDiagnosisRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None,
                 ):
        super().__init__(receive, args, scheme, sub_scheme,request_type)
        try:
            self.receive = RequestV3(**receive)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

        self.register_model = REGISTER_MODEL_TYPE_BASE
        if self.receive.input.register_intention_enable is not None and self.receive.input.register_intention_enable == True:
            self.register_model = REGISTER_MODEL_TYPE_INTENTION

        self.db_engine = create_engine(f"sqlite:///{self.args.database}/medical_assistant.db")
        self.hr_i = self.receive.input.hospital_register
    
    def checker_flag(self):
        self.checker = RegisterDiagnosisProcessChecker(self.receive)
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.tmp_engine = None
        if REGISTER_MODEL_TYPE_BASE == self.register_model: 
            db = DatabaseSchema(self.receive)
            self.tmp_engine = db.run()
        self.prompt = get_prompt('PromptHospitalRegister', self.receive, self.db_engine, self.flag, self.tmp_engine, self.args.department_path)
        self.prompt.set_prompt()
        
    def postprocess_model_base(self, messages):
        self.generate_prompt()
        messages = self.preprocess(self.receive, self.prompt, self.flag)
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re in answers:
            answer+=re
            yield re        
        match self.flag:
            case 31|32:
                self.results = self.postprocess_hr(self.receive, answer, self.flag)
                # self.tmp_engine.dispose()
            case 33: 
                
                if format_new_regiter_info in answer:                 
                    self.results, json_data, intent_flag, passed = self.postprocess_hr(self.receive, answer, self.flag, self.tmp_engine)
                    if json_data != None:
                        sql_str = self.results.chat.historical_conversations_bak[-1].content
                        db = DatabaseSchema(self.receive)
                        self.tmp_engine = db.run()
                        sql_answer = search_database(self.tmp_engine, sql_str)

                        if len(sql_answer) == 0:
                            sql_department_name = self.get_department_name(sql_str)
                            sql_answer = self.search_register_random_top_10(sql_department_name)
                            
                        prompt = get_prompt('PromptHospitalRegister', self.results, self.db_engine, 34, self.tmp_engine, self.args.department_path, sql_answer, json_data, intent_flag, passed)

                        answer = prompt.get_generate_register()
                        self.results = self.postprocess_hr(self.results, answer, 34)
                    else:
                        print("Error: Unable to identify the patient's intention to register.")
                else:
                    self.results = self.postprocess_hr(self.receive, answer, 35)
                # self.tmp_engine.dispose()
        
        results=self.results
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    # 这里只用了user相关的对话信息，加上系统信息后，对模型产出结果又负面影响
    def preprocess_model_intention(self, receive, prompt, flag):
        params = copy.deepcopy(receive)
        hc = params.chat.historical_conversations
        hc_bak = params.chat.historical_conversations_bak

        if hc != [] and hc[-1].role == 'user':
            hc_bak.append(HistoricalConversations(role='user', content=hc[-1].content))
        infer_hc = self.handle_history_chat(hc_bak)

        prompt_content = prompt.get_prompt(flag)
        messages=[{"role": "system", "content": prompt_content[0]}]
        for item in infer_hc:
            if item.role == "user":
                messages.append({'role': item.role, 'content': item.content})
            # messages.append({'role': item.role, 'content': item.content})
        return messages

    def postprocess_model_intention(self, messages):
        params = copy.deepcopy(self.receive)      
        self.generate_prompt()
        messages.extend(self.preprocess_model_intention(self.receive, self.prompt, self.flag)) 
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re_answer in answers:
            answer+=re_answer
            yield re_answer

        hc = params.chat.historical_conversations
        hc_bak = params.chat.historical_conversations_bak
        if hc != [] and hc[-1].role == 'user':
            hc_bak.append(HistoricalConversations(role='user', content=hc[-1].content))
        hc.append(HistoricalConversations(role='assistant', content=answer))
        hc_bak.append(HistoricalConversations(role='assistant', content=answer))

        params.output.register_intention_enable = params.input.register_intention_enable

        json_pattern = re.compile(r'\[.*\]', re.DOTALL)  # 匹配 JSON 数组
        json_match = json_pattern.search(answer)
        if isinstance(json_match, re.Match):
            try:
                json_data = json_match.group(0)
                json_array = json.loads(json_data)

                params.output.register_intention_info = []

                for json_obj in json_array:
                    # json 转 RegisterIntention
                    mapped_data = {
                        register_intention_field_mapping.get(key, key): value
                        for key, value in json_obj.items()
                        if value is not None and value != "" and value != "不限"
                    }
                    # if 'department_name' not in mapped_data and params.output.hospital_register[0] is not None:
                    #     mapped_data['department_name'] = params.output.hospital_register[0].department_name
                    # elif 'department_name' not in mapped_data and params.output.hospital_register[0] is None:
                    #     mapped_data['department_name'] = "未指定"
                    register_intention = RegisterIntention(**mapped_data)
                    params.output.register_intention_info.append(register_intention)

            except Exception as e:
                print(f"Error: There is no matching json data {e}  answer {answer}, json_data {json_data}.")
        else:
            print(f"No JSON array found in the answer  {answer}.   ")

        results_dict = params.model_dump(exclude_none = True)
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re_answer in results:
            yield re_answer
        return

    def postprocess(self, messages):
        self.strategy_mapping = {
            REGISTER_MODEL_TYPE_BASE: self.postprocess_model_base,
            REGISTER_MODEL_TYPE_INTENTION: self.postprocess_model_intention
        }
        processor = self.strategy_mapping.get(self.register_model)
        if processor:
            return processor(messages)
        return messages

    def get_doctor_info(self, input_data: InputV3, doctor_name: str, department_name: str):
        """
        根据医生姓名、日期和开始时间获取医生信息。
        :param input_data: 包含挂号信息的 InputV3 对象
        :param doctor_name: 医生姓名
        :param date: 日期
        :param start_time: 开始时间
        :return: 医生 ID、医生职称、结束时间、号源数量，如果未找到则返回 None
        """
        for hospital_register in input_data.hospital_register:
            if department_name == hospital_register.department_name:
                for doctor in hospital_register.doctor_list:
                    if doctor.doctor_name == doctor_name:
                        return doctor.doctor_id, doctor.doctor_title
        return "", "" 

    def complete_json_data_information(self, json_data, text_match, tmp_engine:Engine=None):
        """
            此处添加修改是因为之前模型输出新的挂号信息时，输出了全部的信息，比如科室编号、科室名称、医生编号等等。
            但72B模型下推理速度慢，在prompt中压缩了其输出字符长度。只包含医生姓名、起始时间、科室名称等
            这里将确实的json对象数据补全
        """
        output_json_data = []
        
        for item in json_data:
            output_json_data_dict = {}
            department_name=item['科室名称']
            department_id = ""
            for v in self.receive.input.all_department:
                if v.department_name == department_name:
                    department_id = v.department_id
                    
            doctor_name = item['医生姓名']
            date = item['挂号日期']  
            start_time = item['起始时间']
            end_time = item['终止时间']
            source_num = item['号源数量']
            doctor_id, doctor_title = self.get_doctor_info(self.receive.input, doctor_name, department_name)
            output_json_data_dict['医生编号'] = doctor_id
            output_json_data_dict['医生职称'] = doctor_title

            output_json_data_dict = {
                '科室编号': department_id,
                '科室名称': department_name,
                '医生编号': doctor_id,
                '医生姓名': doctor_name,
                '医生职称': doctor_title,
                '挂号日期': date,
                '起始时间': start_time,
                '终止时间': end_time,
                '号源数量': source_num
            }
            output_json_data.append(output_json_data_dict)
        return output_json_data
        

    def postprocess_hr(self, receive, answer, flag, tmp_engine:Engine=None):
        
        params = copy.deepcopy(receive)
        hc = params.chat.historical_conversations
        hc_bak = params.chat.historical_conversations_bak
        if hc != [] and hc[-1].role == 'user' and flag != 34:
            hc_bak.append(HistoricalConversations(role='user', content=hc[-1].content))
        hc.append(HistoricalConversations(role='assistant', content=answer))
        hc_bak.append(HistoricalConversations(role='assistant', content=answer))
        if flag == 34:
            hc_bak.pop(-2)
        
        json_match, text_match = extract_json_and_text(answer)
        if not isinstance(json_match, re.Match):
            if flag == 33:
                return params, None, None, None
            else:
                return params
        else:
            try:
                json_data = json_match.group(0)
                json_data = eval(json_data)

                if format_new_regiter_info in text_match or format_register_first_info in text_match:
                    temp = self.complete_json_data_information(json_data, text_match , tmp_engine)
                    json_data = temp
                # print(f"大模型匹配内容: \n{json_data=}\n")
            except:
                print("Error: There is no matching json data.")
                return params

        match flag:
            case 31:
#                department_item = []
#                for item in json_data:
#                    query_item = item['科室名称']
#                    sql_str = f"SELECT DISTINCT department_code, department_name FROM register WHERE department_name=\"{query_item}\""
#                    search_result = search_database(self.tmp_engine, sql_str)
#                    if search_result:
#                        department_item.append(Department(
#                            department_id=search_result[0][0],
#                            department_name=search_result[0][1]
#                        ))
#                    else:
#                        department_item.append(Department(
#                            department_id=item['科室编号'],
#                            department_name=item['科室名称']
#                        ))
                department_item = []
                all_department = [{"department_id":v.department_id, "department_name":v.department_name} for v in self.receive.input.all_department]
                for item in json_data:
                    query_item = item['科室名称']
                    search_result = list(filter(lambda item: query_item in item['department_name'], all_department))
                    if search_result:
                        department_item.append(Department(
                            department_id=search_result[0]['department_id'],
                            department_name=search_result[0]['department_name']
                        ))
                    else:
                        department_item.append(Department(
                            department_id=item['科室编号'],
                            department_name=item['科室名称']
                        ))
                params.output.chosen_department = department_item
                answer = self.format_department(json_data, text_match)
                hc.pop()
                hc.append(HistoricalConversations(role='assistant', content=answer))

            case 32|34:
                hospital_register = []
                for item in json_data:

                    hospital_register_single = HospitalRegister(
                        department_id = item['科室编号'],          
                        department_name = item['科室名称'],
                        doctor_list = [DoctorList(
                            doctor_id = item['医生编号'],
                            doctor_name = item['医生姓名'],
                            doctor_title = item['医生职称'],
                            date_list = [DateList(
                                date = item['挂号日期'],
                                time_list = [TimeList(
                                    start_time = item['起始时间'],
                                    end_time = item['终止时间'],
                                    source_num = item['号源数量'])])])])
                    hospital_register.append(hospital_register_single)
                params.output.hospital_register = hospital_register
                if flag == 32:
                    answer = self.format_register_first(json_data, text_match)
                if flag == 34:
                    answer = self.format_register_other(json_data, text_match)
                hc.pop()
                hc.append(HistoricalConversations(role='assistant', content=answer))

            case 33:
                answer, intent_flag, passed = self.patient_intent_sql(params.output, json_data)

                hc.pop()
                hc_bak.pop()
                hc_bak.append(HistoricalConversations(role='assistant', content=answer))

                return params, json_data, intent_flag, passed

            case 35:
                pass

        return params
    

    def patient_intent_sql(self, output, json_data):
        doctor_list = output.hospital_register[0].doctor_list[0]
        department_name = output.hospital_register[0].department_name
        chosen_department = output.chosen_department
        original_intent = {
            "department_name": department_name,
            "doctor_name": doctor_list.doctor_name,
            "doctor_title": doctor_list.doctor_title,
            "date": doctor_list.date_list[0].date,
            "start_time": doctor_list.date_list[0].time_list[0].start_time
        }
        new_intent = {
            "department_name": json_data[0]['科室名称'],
            "doctor_name": json_data[0]['医生姓名'],
            "doctor_title": json_data[0]['医生职称'],
            "date": json_data[0]['挂号日期'],
            "start_time": json_data[0]['起始时间']
        }
#        select_clause = f"""SELECT department_code, department_name, doctor_code, doctor_name, doctor_title, \
#    date, start_time, end_time, source_num FROM register WHERE department_name LIKE '%{json_data[0]['科室名称']}%' """
#        where_clause = " AND source_num > '0'"
        select_clause = f"""SELECT department_code, department_name, doctor_code, doctor_name, doctor_title, \
date, start_time, end_time, source_num FROM register"""
        where_clause = " WHERE source_num > '0'"
        intent_flag = 0

        passed = False
        where_clause += f" AND department_name LIKE '%{new_intent['department_name']}%'"
        if new_intent['department_name'] != original_intent['department_name']:
            passed = True

        if new_intent['doctor_name'] != original_intent['doctor_name']:
            where_clause += f""" AND doctor_name LIKE '%{new_intent['doctor_name']}%'"""
            intent_flag = 11
            where_clause += f""" AND date = '{new_intent['date']}'"""
            intent_flag += 1
            where_clause += f""" AND start_time >= '{new_intent['start_time']}'"""
            intent_flag += 2
            '''
            if new_intent['date'] != original_intent['date']:
                where_clause += f""" AND date = '{new_intent['date']}'"""
                intent_flag += 1
            if new_intent['start_time'] != original_intent['start_time']:
                where_clause += f""" AND start_time >= '{new_intent['start_time']}'"""
                intent_flag += 2
            '''
        elif new_intent['doctor_title'] != original_intent['doctor_title']:
            where_clause += f""" AND doctor_title LIKE '{new_intent['doctor_title']}%'"""
            intent_flag = 21
            if new_intent['date'] != original_intent['date']:
                where_clause += f""" AND date = '{new_intent['date']}'"""
                intent_flag += 1
            if new_intent['start_time'] != original_intent['start_time']:
                where_clause += f""" AND start_time >= '{new_intent['start_time']}'"""
                intent_flag += 2
        elif new_intent['date'] != original_intent['date']:
            intent_flag = 31
            where_clause += f""" AND doctor_name LIKE '%{new_intent['doctor_name']}%' \
AND doctor_title LIKE '{new_intent['doctor_title']}%' \
AND date = '{new_intent['date']}'"""
            # if new_intent['start_time'] != original_intent['start_time']:
            # when date change， may has AM、PM info，so here must use start_time
            intent_flag += 1
            where_clause += f""" AND start_time >= '{new_intent['start_time']}'"""
        elif new_intent['start_time'] != original_intent['start_time']:
            where_clause += f""" AND doctor_name LIKE '%{new_intent['doctor_name']}%' \
AND doctor_title LIKE '{new_intent['doctor_title']}%' \
AND date = '{new_intent['date']}' \
AND start_time >= '{new_intent['start_time']}'"""
            intent_flag = 41
        else:
            if passed == False:
                where_clause += f""" AND doctor_name LIKE '%{original_intent['doctor_name']}%' \
AND doctor_title LIKE '{original_intent['doctor_title']}%' \
AND date = '{original_intent['date']}' \
AND start_time >= '{original_intent['start_time']}'"""
            intent_flag = 51

        answer = select_clause + where_clause
        #print(f"挂号意图：{intent_flag=}")
        #print(f"查询的sql语句：{answer=}")
        return answer, intent_flag, passed
    
    def format_register_first(self, json_data, text_match):
        #answer = f"""{text_match}"""
        answer = f"""依据您的病情，我们推荐您在"""
        for item in json_data:
            answer+=f"""【{item['挂号日期']} {item['起始时间']}-{item['终止时间']}】，前往\
【{item['科室名称']} {item['医生姓名']} {item['医生职称']}】处进行就诊，您看是否可以？（如果所推荐挂号不符合您的预期，可以直接告诉我您的挂号要求，我将为您重新推荐。例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"""
        return answer

    def format_register_other(self, json_data, text_match):
        #answer = f"""{text_match}"""
        answer = f"""我们推荐您在"""
        for item in json_data:
            answer+=f"""【{item['挂号日期']} {item['起始时间']}-{item['终止时间']}】，前往\
【{item['科室名称']} {item['医生姓名']} {item['医生职称']}】处进行就诊，您看是否可以？（或者您可以直接告诉我您的挂号要求，例如：“张三的号”、“主任的号”、“明天下午3点半的号”等。）"""
        return answer

    def format_department(self, json_data, text_match):
        answer = text_match
        for item in json_data:
            answer+=f"""
【{item['科室名称']}】"""
        return answer


    def get_department_name(self, sql_str):
        department_name = ""
        pattern = r"department_name LIKE '%(.*?)%'"
        match = re.search(pattern, sql_str)
        if match:
            department_name = match.group(1)
        return department_name


    def search_register_random_top_10(self, department_name:str):
        ret_answer = []
        sql_str = f"SELECT department_code, department_name, doctor_code, doctor_name, doctor_title, \
date, start_time, end_time, source_num FROM register WHERE department_name LIKE '%{department_name}%' \
AND source_num > '0' ORDER BY date ASC, start_time ASC  LIMIT 10" 
        sql_answer = search_database(self.tmp_engine, sql_str)
        real_len = len(sql_answer)
        if real_len > 1:
            random_int = random.randint(1, real_len - 1)
            ret_answer.append(sql_answer[random_int])
        elif real_len == 1:
            ret_answer.append(sql_answer[0])
        return ret_answer
