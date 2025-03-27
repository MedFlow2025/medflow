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
import json
import datetime

from id_validator import validator
from .base_diagnosis_request_handler import BaseDiagnosisRequestHandler
from .prompt_template import *
from .util_data_models import *
from .util import *
import io
from fastapi.responses import StreamingResponse, JSONResponse

class ClientInfoProcessChecker:
    def __init__(self, receive) -> None:
        self.ci_i = receive.input.client_info
        self.ci_o = receive.output.client_info[0]
        self.cf_o = receive.output.create_file

    def __check_client_num(self):
        client_num = 0
        if self.ci_i == []:
            pass
        else:
            for k, v in enumerate(self.ci_i):
                client_num += 1 if not any(getattr(v.patient, attr) in ["", None] for attr in 
                    ['patient_name', 'certificate_type', 'certificate_number']) else 0
        return True if client_num != 0 and self.cf_o == "" else False

    def __check_basic_patient(self):
        return (any(getattr(self.ci_o.patient, attr) in ["", None] for attr in
            ['patient_name', 'certificate_type', 'certificate_number', 'mobile_number', 'detailed_address'])) or \
            (any(getattr(self.ci_o.patient.current_address, attr) in ["", None] for attr in
            ['province', 'city', 'district', 'street']))

    def __check_patient(self):
        return any(getattr(self.ci_o.patient, attr) in ["", None] for attr in
            ['patient_age', 'patient_gender']) and self.cf_o == "是"

    def __check_guardian(self):
        return any(getattr(self.ci_o.guardian, attr) in ["", None] for attr in
            ['guardian_name', 'certificate_type', 'certificate_number']) and self.cf_o == "是"

    def check(self):
        if self.__check_client_num():
            return 11
        else:
            if self.__check_basic_patient(): return 12
            elif self.__check_patient(): return 14
            elif self.__check_guardian(): return 15
            else: return 1

class ClientInfoRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None,
                 ):
        super().__init__(receive, args, scheme, sub_scheme,request_type)
        self.receive = RequestV1(**receive)

    def checker_flag(self):
        self.checker = ClientInfoProcessChecker(self.receive)
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptClientInfo', self.receive,  self.flag)
        self.prompt.set_prompt()

    def postprocess(self, messages):
        answer=""
        answers = self.predict_stream(messages, self.temprature, self.top_p)
        for re in answers:
            answer+=re
            yield re
        results = self.postprocess_ci(self.receive, answer, self.flag)

        if self.flag == 11:
            if "现在为您返回" in results.chat.historical_conversations[-1].content:
                prompt = get_prompt('PromptClientInfo', results, self.flag)
                prompt.set_prompt()
                checker = ClientInfoProcessChecker(results)
                self.flag = checker.check()
                messages = self.preprocess(results, prompt, self.flag)
                answer = self.predict(messages)
                results = self.postprocess_ci(results, answer, self.flag)
                results.chat.historical_conversations.pop(-2)

        if self.flag in [12, 14, 15, 1]:
            if "校验结果" in results.chat.historical_conversations[-1].content:
                prompt = get_prompt('PromptClientInfo', results, 13, results.chat.historical_conversations[-1].content)
                prompt.set_prompt()
                messages = self.preprocess(results, prompt, 13)
                answer = self.predict(messages, 1, 1)
                results = self.postprocess_ci(results, answer, 13)
            if "现在为您返回" in results.chat.historical_conversations[-1].content:
                prompt = get_prompt('PromptClientInfo', results, self.flag)
                prompt.set_prompt()
                checker = ClientInfoProcessChecker(results)
                self.flag = checker.check()
                if self.flag in [14, 15]:#1
                    messages = self.preprocess(results, prompt, self.flag)
                    answer = self.predict(messages)
                    results = self.postprocess_ci(results, answer, self.flag)
                    results.chat.historical_conversations.pop(-2)

        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return
 
    def postprocess_ci(self, receive, answer, flag):
        params = copy.deepcopy(receive)
        hc = params.chat.historical_conversations
        hc_bak = params.chat.historical_conversations_bak
        if hc != [] and hc[-1].role == 'user':
            hc_bak.append(HistoricalConversations(role='user', content=hc[-1].content))
        hc.append(HistoricalConversations(role='assistant', content=answer))
        hc_bak.append(HistoricalConversations(role='assistant', content=answer))

        json_match, text_match = extract_json_and_text(answer)
        if not isinstance(json_match, re.Match):
           return params
        else:
           try:
               json_data = json_match.group(0)
               json_data = eval(json_data)
               # print(f"大模型匹配内容: \n{json_data=}\n")
           except:
               print("Error: There is no matching json data.")
               return params

        match flag:
            case 11:
                client = next((v for v in params.input.client_info if v.patient.patient_name == json_data['就诊人姓名']), None)
                if client == None:
                    params.output.client_info[0].patient.patient_name = json_data['就诊人姓名']
                    params.output.create_file = "是"
                else:
                    params.output.client_info[0] = client
                    params.output.create_file = "否"

            case 12|14|15|1:
                count_answer = []
                json_data_p = json_data['档案']['患者信息']
                json_data_g = json_data['档案']['监护人信息']
                if json_data_p['姓名'] != "":
                    params.output.client_info[0].patient.patient_name = json_data_p['姓名']
                    if flag != 1: params.output.create_file = "是"

                if json_data_p['证件号码'] != "":
                    if json_data_p['证件类型'] in ['身份证', '居住证', '大陆居民身份证', '大陆居民身份证(二代)', '大陆居民身份证(一代)', '港澳居民居住证', '台湾居民居住证']:
                        if_valid = validator.is_valid(json_data_p['证件号码'])
                        if if_valid == 0:
                            count_answer.append("患者的证件号码不存在。")
                        else:
                            detail_info = validator.get_info(json_data_p['证件号码'])
                            match detail_info['address_code']:
                                case '810000':
                                    params.output.client_info[0].patient.certificate_type = "港澳居民居住证"
                                case '820000':
                                    params.output.client_info[0].patient.certificate_type = "港澳居民居住证"
                                case '830000':
                                    params.output.client_info[0].patient.certificate_type = "台湾居民居住证"
                                case _:
                                    if detail_info['length'] == 18:
                                        params.output.client_info[0].patient.certificate_type = "大陆居民身份证(二代)"
                                    elif detail_info['length'] == 15:
                                        params.output.client_info[0].patient.certificate_type = "大陆居民身份证(一代)"
                            params.output.client_info[0].patient.certificate_number = json_data_p['证件号码']
                            params.output.client_info[0].patient.if_child = "是" if detail_info['age'] < 15 else "否"
                            params.output.client_info[0].patient.patient_gender = "女" if detail_info['sex'] == 0 else "男"
                            params.output.client_info[0].patient.patient_age = str(detail_info['age'])
                            if params.output.client_info[0].patient.if_child == "否":
                                params.output.client_info[0].guardian.guardian_name = "无"
                                params.output.client_info[0].guardian.certificate_type = "无"
                                params.output.client_info[0].guardian.certificate_number = "无"
                            if params.output.client_info[0].patient.if_child == "是":
                                params.output.client_info[0].guardian.guardian_name = ""
                                params.output.client_info[0].guardian.certificate_type = ""
                                params.output.client_info[0].guardian.certificate_number = ""
                    else:
                        params.output.client_info[0].patient.certificate_type = json_data_p['证件类型']
                        params.output.client_info[0].patient.certificate_number = json_data_p['证件号码']

                        if flag != 12:
                            if json_data_p['性别'] != "":
                                if json_data_p['性别'] in ['男', '女']:
                                    params.output.client_info[0].patient.patient_gender = json_data_p['性别']
                                else:
                                    count_answer.append("患者性别错误，应为“男/女”。")

                            if json_data_p['出生日期']['年'] != "" and json_data_p['出生日期']['月'] != "" and json_data_p['出生日期']['日'] != "":
                                age = self.calculate_age(json_data_p)
                                if age > 0 and age < 120:
                                    params.output.client_info[0].patient.if_child = "是" if age < 15 else "否"
                                    params.output.client_info[0].patient.patient_age = str(age)
                                else:
                                    count_answer.append("出生日期错误，年龄应介于1岁到120岁之间。")

                                if params.output.client_info[0].patient.if_child == "否":
                                    params.output.client_info[0].guardian.guardian_name = "无"
                                    params.output.client_info[0].guardian.certificate_type = "无"
                                    params.output.client_info[0].guardian.certificate_number = "无"

                if json_data_p['手机号码'] != "":
                    pattern = r"^\d{11}$"
                    pattern2 = r"^(13[0-9]|14[01456879]|15[0-35-9]|16[2567]|17[0-8]|18[0-9]|19[0-35-9])\d{8}$"
                    if not re.match(pattern, json_data_p['手机号码']):
                        count_answer.append("手机号码位数错误。")
                    elif not re.match(pattern2, json_data_p['手机号码']):
                        count_answer.append("手机号码固定开头错误。")
                    else:
                        params.output.client_info[0].patient.mobile_number = json_data_p['手机号码']

                wait_check = json_data_p['所居区域']['省'] + json_data_p['所居区域']['市'] + json_data_p['所居区域']['区'] + json_data_p['所居区域']['街道']
                if wait_check != "":
                    import jionlp as jio
                    res = jio.parse_location(wait_check)
                    params.output.client_info[0].patient.current_address.province = res['province'] if res['province'] else ""
                    params.output.client_info[0].patient.current_address.city = res['city'] if res['city'] else ""
                    params.output.client_info[0].patient.current_address.district = res['county'] if res['county'] else ""
                    params.output.client_info[0].patient.current_address.street = res['detail'] if res['detail'] else ""
                    if params.output.client_info[0].patient.current_address.province == "":
                        count_answer.append("“省”填写错误或漏填。")
                    if params.output.client_info[0].patient.current_address.city == "":
                        count_answer.append("“市”填写错误或漏填。")
                    if params.output.client_info[0].patient.current_address.district == "":
                        count_answer.append("“区”填写错误或漏填。")
                    if params.output.client_info[0].patient.current_address.street == "":
                        count_answer.append("“街道”填写错误或漏填。")

                if json_data_p['详细地址'] != "":
                    params.output.client_info[0].patient.detailed_address = json_data_p['详细地址']

                if json_data_g['姓名'] != "":
                    params.output.client_info[0].guardian.guardian_name = json_data_g['姓名']

                if json_data_g['证件号码'] != "":
                    if json_data_g['证件类型'] in ['身份证', '居住证', '大陆居民身份证', '大陆居民身份证(二代)', '大陆居民身份证(一代)', '港澳居民居住证', '台湾居民居住证']:
                        if_valid = validator.is_valid(json_data_g['证件号码'])
                        if if_valid == 0:
                            count_answer.append("监护人的证件号码错误。")
                        else:
                            detail_info = validator.get_info(json_data_g['证件号码'])
                            if detail_info['age'] < 20:
                                count_answer.append("监护人的证件号码所对应的年龄不能小于20岁，请修改监护人的证件号码。")
                            else:
                                match detail_info['address_code']:
                                    case '810000':
                                        params.output.client_info[0].guardian.certificate_type = "港澳居民居住证"
                                    case '820000':
                                        params.output.client_info[0].guardian.certificate_type = "港澳居民居住证"
                                    case '830000':
                                        params.output.client_info[0].guardian.certificate_type = "台湾居民居住证"
                                    case _:
                                        if detail_info['length'] == 18:
                                            params.output.client_info[0].guardian.certificate_type = "大陆居民身份证(二代)"
                                        elif detail_info['length'] == 15:
                                            params.output.client_info[0].guardian.certificate_type = "大陆居民身份证(一代)"
                                params.output.client_info[0].guardian.certificate_number = json_data_g['证件号码']
                    else:
                        params.output.client_info[0].guardian.certificate_type = json_data_g['证件类型']
                        params.output.client_info[0].guardian.certificate_number = json_data_g['证件号码']

                if count_answer != []:
                    answer = "校验结果:"+"".join(count_answer)
                    hc[-1] = HistoricalConversations(role='assistant', content=answer)
                    hc_bak[-1] = HistoricalConversations(role='assistant', content=answer)
                else:
                    answer = self.format_client_info_2(params)
                    hc.pop()
                    hc.append(HistoricalConversations(role='assistant', content=answer))
                return params

            case 13:
               hc.pop()
               hc_bak.pop()
               hc.pop()
               hc_bak.pop()
               hc.append(HistoricalConversations(role='assistant', content=json_data['翻译结果']))
               hc_bak.append(HistoricalConversations(role='assistant', content=json_data['翻译结果']))

        return params

    def calculate_age(self, birth_date):
        today = datetime.datetime.today()
        if birth_date['出生日期']['年'] and birth_date['出生日期']['月'] and birth_date['出生日期']['日']:
            year = int(birth_date['出生日期']['年'])
            month = int(birth_date['出生日期']['月'])
            day = int(birth_date['出生日期']['日'])
            age = today.year - year
            if age == 0:
                return age+1
            if (today.month < month) | ((today.month == month) & (today.day < day)):
                age+=-1
            return age
        else:
            return 0

    def format_client_info_2(self, results):
        item_p = results.output.client_info[0].patient
        item_g = results.output.client_info[0].guardian
        answer = f"""现在为您返回患者的信息如下：

患者信息: 
   姓名: {item_p.patient_name}
   是否儿童: {item_p.if_child}
   性别: {item_p.patient_gender}
   年龄: {item_p.patient_age}
   证件类型: {item_p.certificate_type}
   证件号码: {item_p.certificate_number}
   手机号码: {item_p.mobile_number}
   所居区域:
       省: {item_p.current_address.province}
       市: {item_p.current_address.city}
       区: {item_p.current_address.district}
       街道: {item_p.current_address.street}
   详细地址: {item_p.detailed_address}

监护人信息:
    姓名: {item_g.guardian_name}
    证件类型: {item_g.certificate_type}
    证件号码: {item_g.certificate_number}
"""
        return answer