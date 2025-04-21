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

import datetime
from ..prompt_template import *
from typing import List
from ..util_sqlite_function import department_introduction

@register_prompt
class PromptHospitalRegister_v5(PromptTemplate):
    def __init__(self, receive, db_engine, flag, tmp_engine, department_path,
            sql_answer: str = "",
            json_data: dict = {},
            intent_flag: int = 0,
            passed: bool = False
        ) -> None:
        super().__init__()
        self.yaml_name = "hospitalregister_v5.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)
        self.ci = receive.input.client_info
        self.bmr = receive.input.basic_medical_record
        self.ad_i = receive.input.all_department
        # self.hr_i : List[HospitalRegister] = receive.input.hospital_register
        self.hr_i : List = receive.input.hospital_register
        self.hr_o = receive.output.hospital_register
        self.cd_o = receive.output.chosen_department
        self.hc = receive.chat.historical_conversations
        self.db_engine = db_engine
        self.flag = flag
        self.sql_answer = sql_answer
        self.json_data = json_data
        self.intent_flag = intent_flag
        self.tmp_engine = tmp_engine
        self.passed = passed
        self.department_intro = department_introduction(department_path)

        self.register_model = REGISTER_MODEL_TYPE_BASE
        if receive.input.register_intention_enable is not None and receive.input.register_intention_enable == True:
            self.register_model = REGISTER_MODEL_TYPE_INTENTION

    def __search_department(self, table:str):
        sub_dept = [v.department_name for v in self.ad_i]
        return sub_dept

    def __search_register(self, table:str):
        from sqlalchemy import text
        dept = []
        sub_dept = []
        if table == "register":
            for item in self.cd_o:
                sql_str = f"SELECT department_code, department_name, doctor_code, doctor_name, doctor_title, \
date, start_time, end_time, source_num FROM register WHERE department_name LIKE '%{item.department_name}%' \
AND source_num > '0' ORDER BY date ASC, start_time ASC" 
                with self.tmp_engine.connect() as con:
                    rows = con.execute(text(sql_str))
                    rows = [r for r in rows]
                    
                    if rows != []:
                        sub_dept.append(rows)
            if sub_dept != []:
                sub_dept = [a[0] for a in sub_dept]
                for v in sub_dept:
                    sub_dept=f"""科室编号: {v[0]}；科室名称: {v[1]}；医生编号: {v[2]}；医生姓名: {v[3]}；\
医生职称: {v[4]}；挂号日期: {v[5]}；起始时间: {v[6]}；终止时间: {v[7]}；号源数量: {v[8]}；"""
                    dept.append(sub_dept)
                dept = dept[0]
                
        else:
            print(f"Error: no table named {table}.")
        return dept

    def __generate_registration_info(self):
        """_summary_
            return registration info json string by receive.input.hospital_register
        """
        if len(self.hr_i) == 0:
            return ""
        doctor_list = self.hr_i[0].doctor_list
        return json.dumps([i.model_dump() for i in doctor_list], ensure_ascii=False)

    def __current_register(self):
        current_register = f"""\{{
"科室编号": "{self.hr_o[0].department_id}",
"科室名称": "{self.hr_o[0].department_name}",
"医生编号": "{self.hr_o[0].doctor_list[0].doctor_id}",
"医生姓名": "{self.hr_o[0].doctor_list[0].doctor_name}",
"医生职称": "{self.hr_o[0].doctor_list[0].doctor_title}",
"挂号日期": "{self.hr_o[0].doctor_list[0].date_list[0].date}",
"起始时间": "{self.hr_o[0].doctor_list[0].date_list[0].time_list[0].start_time}",
"终止时间": "{self.hr_o[0].doctor_list[0].date_list[0].time_list[0].end_time}",
"号源数量": "{self.hr_o[0].doctor_list[0].date_list[0].time_list[0].source_num}"}}"""
        return current_register

    def __current_department(self):
        current_department = [v.department_name for v in self.cd_o]
        return current_department

    def __current_doctor(self):
        from sqlalchemy import text
        sql_str = f"SELECT DISTINCT doctor_name,department_name,doctor_title FROM register"
        for i, v in enumerate(self.cd_o):
            sql_str += f" WHERE department_name LIKE '%{v.department_name}%'" if i == 0 else f" OR department_name LIKE '%{v.department_name}%'"
        with self.tmp_engine.connect() as con:
            rows = con.execute(text(sql_str))
            current_doctor = [f"{row[0]}({row[1]},{row[2]})" for row in rows]
        return current_doctor

    def __current_doctor_title(self):
        from sqlalchemy import text
        sql_str = f"SELECT DISTINCT doctor_title FROM register"
        for i, v in enumerate(self.cd_o):
            sql_str += f" WHERE department_name LIKE '%{v.department_name}%'" if i == 0 else f" OR department_name LIKE '%{v.department_name}%'"
        with self.tmp_engine.connect() as con:
            rows = con.execute(text(sql_str))
            current_doctor_title = [row[0] for row in rows]
        return current_doctor_title

    def __current_date(self):
        today = datetime.datetime.now()
        # just for test, do not delete
        # date_str = '2026-04-25'
        # today = datetime.datetime.strptime(date_str, '%Y-%m-%d')

        weeks = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
        current_date = f"""{today.year}年；{today.month}月；{today.day}日；{weeks[today.weekday()]}；"""
        #current_date = f"""2024年；11月；25日；星期一；"""
        return current_date

    def __get_date_by_offset(self, offset):
        today = datetime.datetime.now()
        target_date = today + datetime.timedelta(days=offset)
        weeks = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
        return f"{target_date.year}年；{target_date.month}月；{target_date.day}日；{weeks[target_date.weekday()]}；"

    def __patient_intent(self):
        answer = self.hc[-1].content if self.hc != [] and self.hc[-1].role == 'user' else ""
        return answer

    def __last_system_patient_intent(self):
        answer = self.hc[-2].content if self.hc != [] and len(self.hc) > 4 and self.hc[-2].role != 'user' else ""
        return answer

    def __confirmed(self):
        first_data = f"""\
【{self.hr_o[0].doctor_list[0].date_list[0].date} \
{self.hr_o[0].doctor_list[0].date_list[0].time_list[0].start_time}-\
{self.hr_o[0].doctor_list[0].date_list[0].time_list[0].end_time}】\
【{self.hr_o[0].department_name} \
{self.hr_o[0].doctor_list[0].doctor_name} \
{self.hr_o[0].doctor_list[0].doctor_title}】"""
        return first_data

    def __yes_register(self):
        sa = self.sql_answer[0]
        yes_register = ["我们为您推荐如下预约就诊，您看是否可以？<json格式的挂号信息>"]
        yes_register.append(f"""科室编号: {sa[0]}；科室名称: {sa[1]}；医生编号: {sa[2]}；医生姓名: {sa[3]}；\
医生职称: {sa[4]}；挂号日期: {sa[5]}；起始时间: {sa[6]}；终止时间: {sa[7]}；号源数量: {sa[8]}；""")
        return yes_register

    def __no_register(self):
        jd = self.json_data
        match self.intent_flag:
            case 11:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']}】"""
            case 12:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['挂号日期']}】"""
            case 13:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['起始时间']}】"""
            case 14:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['挂号日期']} {jd[0]['起始时间']}】"""
            case 21:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生职称']}】"""
            case 22:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生职称']} {jd[0]['挂号日期']}】"""
            case 23:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生职称']} {jd[0]['起始时间']}】"""
            case 24:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生职称']} {jd[0]['挂号日期']} {jd[0]['起始时间']}】"""
            case 31:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['医生职称']} {jd[0]['挂号日期']}】"""
            case 32:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['医生职称']} {jd[0]['挂号日期']} {jd[0]['起始时间']}】"""
            case 41:
                no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['医生职称']} {jd[0]['挂号日期']} {jd[0]['起始时间']}】"""
            case 51:
                if self.passed:
                    no_register = f"""【{jd[0]['科室名称']}】"""
                else:
                    no_register = f"""【{jd[0]['科室名称']} {jd[0]['医生姓名']} {jd[0]['医生职称']} {jd[0]['挂号日期']} {jd[0]['起始时间']}】"""
            case _:
                no_register = ""
        return no_register

    def __set_department(self):
        #31-生成科室
        self.department_all = self.__search_department("department")
        self.variables = {
            "chief_complaint": self.bmr.chief_complaint,
            "history_of_present_illness": self.bmr.history_of_present_illness,
            "past_medical_history": self.bmr.past_medical_history,
            "personal_history": self.bmr.personal_history,
            "allergy_history": self.bmr.allergy_history,
            "format_department_single": self.format_department_single,
            "format_department_multi": self.format_department_multi,
            "department_all": self.department_all,
            "department_intro": self.department_intro
        }
        system_str = self.prompt_manager.get_prompt("department", 0, self.variables)
        if self.ci == None:
            system_str += self.prompt_manager.get_prompt("department", 1, self.variables)
        else:
            self.variables["patient_name"] = self.ci[0].patient.patient_name
            self.variables["patient_gender"] = self.ci[0].patient.patient_gender
            self.variables["patient_age"] = self.ci[0].patient.patient_age
            system_str += self.prompt_manager.get_prompt("department", 2, self.variables)
        return system_str, None

    def __set_first_register(self):
        #32-推荐挂号
        self.search_register = self.__search_register('register')
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        self.variables = {
            "search_register": self.search_register,
            "format_hospital_register_modify": self.format_hospital_register_modify,
            "now": now
        }
        if self.search_register != []:
            system_str = self.prompt_manager.get_prompt("first_register", 0, self.variables)
        else:
            system_str = self.prompt_manager.get_prompt("first_register", 1, self.variables)
        return system_str, None

    def __set_recognize_intent(self):
        #33/35-修改挂号-识别患者意图
        self.current_register = self.__current_register()
        self.current_department = self.__current_department()
        self.current_doctor = self.__current_doctor()
        self.current_doctor_title = self.__current_doctor_title()
        self.current_date = self.__current_date()
        self.patient_intent = self.__patient_intent()
        self.confirmed = self.__confirmed()
        self.tomorrow_date = self.__get_date_by_offset(1)
        self.day_after_tomorrow_date = self.__get_date_by_offset(2)
        self.three_days_from_now_date = self.__get_date_by_offset(3)

        self.variables = {
            "current_department": self.current_department,
            "current_doctor": self.current_doctor,
            "current_doctor_title": self.current_doctor_title,
            "current_date": self.current_date,
            "tomorrow_date": self.tomorrow_date,
            "day_after_tomorrow_date": self.day_after_tomorrow_date,
            "three_days_from_now_date": self.three_days_from_now_date,
            "current_register": self.current_register,
            "patient_intent": self.patient_intent,
            "format_hospital_register_modify": self.format_hospital_register_modify,
            "format_new_regiter_info": self.format_new_regiter_info,
            "confirmed": self.confirmed
        }
        system_str = self.prompt_manager.get_prompt("recognize_intent", 0, self.variables)
        return system_str, None

    def __set_recognize_intent_by_intention_model(self):
        # 33/35-修改挂号-识别患者意图
        # 这里的患者意图，不再是只限于一个挂号信息，而是一个带优先级的挂号意图，具体差异通过prompt内容查看
        self.current_register = self.__current_register()
        # self.current_department = self.__current_department()
        # self.current_doctor = self.__current_doctor()
        # self.current_doctor_title = self.__current_doctor_title()
        self.current_date = self.__current_date()
        self.patient_intent = self.__patient_intent()
        self.confirmed = self.__confirmed()
        self.tomorrow_date = self.__get_date_by_offset(1)
        self.day_after_tomorrow_date = self.__get_date_by_offset(2)
        self.three_days_from_now_date = self.__get_date_by_offset(3)
        self.last_system_intent = self.__last_system_patient_intent()

        # new v0_user_last_intent base from hospital register v2 file
        self.variables = {
            "current_date": self.current_date,
            "current_register": self.current_register,
            "patient_intent": self.patient_intent,
            "last_system_intent": self.last_system_intent
        }
        system_str = self.prompt_manager.get_prompt("recognize_intent_by_intention_model", 0, self.variables)
        return system_str, None

    def __set_recognize_intent_with_registration_info(self):
        #33/35-修改挂号-识别患者意图
        self.current_register = self.__current_register()
        self.current_doctor = self.__current_doctor()
        self.current_date = self.__current_date()
        self.patient_intent = self.__patient_intent()
        self.confirmed = self.__confirmed()
        self.tomorrow_date = self.__get_date_by_offset(1)
        self.day_after_tomorrow_date = self.__get_date_by_offset(2)
        self.three_days_from_now_date = self.__get_date_by_offset(3)
        self.registration_info_json_str = self.__generate_registration_info()

        self.variables = {
            "registration_info_json_str": self.registration_info_json_str,
            "current_register": self.current_register,
            "current_date": self.current_date,
            "tomorrow_date": self.tomorrow_date,
            "day_after_tomorrow_date": self.day_after_tomorrow_date,
            "three_days_from_now_date": self.three_days_from_now_date,
            "patient_intent": self.patient_intent,
            "format_hospital_register": self.format_hospital_register,
            "format_new_regiter_info": self.format_new_regiter_info,
            "confirmed": self.confirmed
        }
        system_str = self.prompt_manager.get_prompt("recognize_intent_with_registration_info", 0, self.variables)
        return system_str, None

    def set_prompt(self):
        if self.flag == 31:
            self.prompt = {"31": self.__set_department()}
        if self.flag == 32:
            self.prompt = {"32": self.__set_first_register()}
        if self.flag == 33:
            # if False: #ADD_REGISTRATION_INFO_TO_PROMPT == True:
            if REGISTER_MODEL_TYPE_INTENTION == self.register_model:
                self.prompt = {"33": self.__set_recognize_intent_by_intention_model()}
            else:
                self.prompt = {"33": self.__set_recognize_intent()}
        # if self.flag == 34:
        #     self.prompt = {"34": self.__set_generate_register()}
        return self.prompt

    def get_generate_register(self):
        #34-生成挂号
        if self.sql_answer != []:
            sa = self.sql_answer[0]
            register_info = {
                "科室编号": sa[0],
                "科室名称": sa[1],
                "医生编号": sa[2],
                "医生姓名": sa[3],
                "医生职称": sa[4],
                "挂号日期": sa[5],
                "起始时间": sa[6],
                "终止时间": sa[7],
                "号源数量": str(sa[8])
            }
            register_info_list = []
            register_info_list.append(register_info)
            json_format_info = json.dumps(register_info_list, ensure_ascii=False)
            return f"我们为您推荐如下预约就诊，您看是否可以？ {json_format_info}"            
        else:
            no_register = self.__no_register()   
            return f"抱歉，目前没有查询到{no_register}的出诊信息，您可以尝试换个问题，我会尽力帮助您。"
