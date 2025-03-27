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
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, insert, select, text)
from .base_diagnosis_request_handler import BaseDiagnosisRequestHandler
from .prompt_template import *
from .util_data_models import *
from .util_sqlite_function import *
from .util import *
import io
from fastapi.responses import StreamingResponse, JSONResponse

class ExamineAssayProcessChecker:
    def __init__(self) -> None:
        pass

    def check(self):
        return 5

class ExamineAssayRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None,
                 ):
        super().__init__(receive, args, scheme, sub_scheme,request_type)
        self.receive = RequestV5(**receive)
        self.db_engine = create_engine(f"sqlite:///{self.args.database}/medical_assistant.db")

    def checker_flag(self):
        self.checker = ExamineAssayProcessChecker()
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptExamAss', self.receive)
        self.prompt.set_prompt()

    def postprocess(self, answer):
        results = self.postprocess_ea(self.receive, answer, self.flag)
        #return results
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return

    def postprocess_ea(self, receive, answer, flag):
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
            case 5:
                if '检查' in json_data and json_data['检查']:
                    examine_item = []
                    for item in json_data['检查']:
                        diagnose_item = []
                        for dia in item['针对疾病']:
                            query_item2 = dia['诊断名称']
                            query_result2 = query_fastbm25(self.args.fastbm25_path, query_item2, "diagnosis")
                            if self.args.fastbm25 and query_result2:
                                query_item2 = query_result2[0][0]
                                sql_str2 = f"SELECT id, diagnosis_code, diagnosis_name, COALESCE(alias, diagnosis_name) \
                                    AS name FROM diagnosis_info WHERE name=\"{query_item2}\""
                                search_result2 = search_database(self.db_engine, sql_str2)
                                diagnose_item.append(Diagnosis(
                                    diagnosis_name=dia['诊断名称'],
                                    diagnosis_name_retrieve=search_result2[0][2],
                                    diagnosis_code=search_result2[0][1],
                                    diagnosis_identifier="疑似"
                                ))
                            else:
                                diagnose_item.append(Diagnosis(
                                    diagnosis_name=dia['诊断名称'],
                                    diagnosis_name_retrieve="",
                                    diagnosis_code="",
                                    diagnosis_identifier="疑似"
                                ))

                        query_item = item['检查名称']
                        query_result = query_fastbm25(self.args.fastbm25_path, query_item, "examination")
                        if self.args.fastbm25 and query_result:
                            query_item = query_result[0][0]
                            sql_str = f"SELECT id, examination_code, examination_name, examination_category, \
                                COALESCE(alias, examination_name) AS name FROM examination_info WHERE name=\"{query_item}\""
                            search_result = search_database(self.db_engine, sql_str)
                            examine_item.append(ExamineContent(
                                examine_code=search_result[0][1],
                                examine_category=search_result[0][3],
                                examine_name=item['检查名称'],
                                examine_name_retrieve=search_result[0][2],
                                order_quantity=str(item['开单数量']),
                                examine_result="",
                                corresponding_diagnosis=diagnose_item
                            ))
                        else:
                            examine_item.append(ExamineContent(
                                examine_code=item['检查编号'],
                                examine_category=item['检查类型'],
                                examine_name=item['检查名称'],
                                examine_name_retrieve="",
                                order_quantity=str(item['开单数量']),
                                examine_result="",
                                corresponding_diagnosis=diagnose_item
                            ))
                    params.output.examine_content = examine_item

                if '化验' in json_data and json_data['化验']:
                    assay_item = []
                    for item in json_data['化验']:
                        diagnose_item = []
                        for dia in item['针对疾病']:
                            query_item2 = dia['诊断名称']
                            query_result2 = query_fastbm25(self.args.fastbm25_path, query_item2, "diagnosis")
                            if self.args.fastbm25 and query_result2:
                                query_item2 = query_result2[0][0]
                                sql_str2 = f"SELECT id, diagnosis_code, diagnosis_name, COALESCE(alias, diagnosis_name) \
                                    AS name FROM diagnosis_info WHERE name=\"{query_item2}\""
                                search_result2 = search_database(self.db_engine, sql_str2)
                                diagnose_item.append(Diagnosis(
                                    diagnosis_name=dia['诊断名称'],
                                    diagnosis_name_retrieve=search_result2[0][2],
                                    diagnosis_code=search_result2[0][1],
                                    diagnosis_identifier="疑似"
                                ))
                            else:
                                diagnose_item.append(Diagnosis(
                                    diagnosis_name=dia['诊断名称'],
                                    diagnosis_name_retrieve="",
                                    diagnosis_code="",
                                    diagnosis_identifier="疑似"
                                ))

                        query_item = item['项目名称']
                        query_result = query_fastbm25(self.args.fastbm25_path, query_item, "laboratorytest")
                        if self.args.fastbm25 and query_result:
                            query_item = query_result[0][0]
                            sql_str = f"SELECT id, laboratorytest_code, laboratorytest_name, laboratorytest_catagory, \
                                COALESCE(alias, laboratorytest_name) AS name FROM laboratorytest_info \
                                WHERE name=\"{query_item}\""
                            search_result = search_database(self.db_engine, sql_str)
                            assay_item.append(AssayContent(
                                assay_code=search_result[0][1],
                                assay_category=search_result[0][3],
                                assay_name=item['项目名称'],
                                assay_name_retrieve=search_result[0][2],
                                order_quantity=str(item['开单数量']),
                                assay_result=[],
                                corresponding_diagnosis=diagnose_item
                            ))
                        else:
                            assay_item.append(AssayContent(
                                assay_code=item['项目编号'],
                                assay_category=item['项目类型'],
                                assay_name=item['项目名称'],
                                assay_name_retrieve="",
                                order_quantity=str(item['开单数量']),
                                assay_result=[],
                                corresponding_diagnosis=diagnose_item
                            ))
                    params.output.assay_content = assay_item
                    answer = self.format_exam_assay(json_data, text_match)
                    hc.pop()
                    hc.append(HistoricalConversations(role='assistant', content=answer))
        return params

    def format_exam_assay(self, json_data, text_match):
        answer = f"""{text_match}
检查项："""
        if '检查' in json_data and json_data['检查']:
            for item in json_data['检查']:
                cor_diagnosis=[v['诊断名称'] for v in item['针对疾病']]
                answer+=f"""
【检查编号：{item['检查编号']}  检查类型：{item['检查类型']}  检查名称：{item['检查名称']}  开单数量：{str(item['开单数量'])}  针对疾病：{"、".join(cor_diagnosis)}】"""
        answer+=f"""
化验项："""

        if '化验' in json_data and json_data['化验']:
            for item in json_data['化验']:
                cor_diagnosis=[v['诊断名称'] for v in item['针对疾病']]
                answer+=f"""
【化验编号：{item['项目编号']}  化验类型：{item['项目类型']}  化验名称：{item['项目名称']}  开单数量：{str(item['开单数量'])}  针对疾病：{"、".join(cor_diagnosis)}】"""
        return answer
