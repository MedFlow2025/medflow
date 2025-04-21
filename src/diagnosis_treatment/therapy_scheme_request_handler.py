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
from pydantic import ValidationError
from fastapi import HTTPException

class TherapySchemeProcessChecker:
    def __init__(self) -> None:
        pass

    def check(self):
        return 6

class TherapySchemeRequestHandler(BaseDiagnosisRequestHandler):
    def __init__(self,
                 receive,
                 args,
                 scheme : None, 
                 sub_scheme : None,
                 request_type: None,
                 ):
        super().__init__(receive, args, scheme, sub_scheme,request_type)
        try:
            self.receive = RequestV6(**receive)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
        self.db_engine = create_engine(f"sqlite:///{self.args.database}/medical_assistant.db")
        match scheme:
            case "default_therapy" | "other_therapy":
                self.temprature = 1
                self.top_p = 1

    def checker_flag(self):
        self.checker = TherapySchemeProcessChecker()
        self.flag = self.checker.check()

    def generate_prompt(self):
        self.prompt = get_prompt('PromptScheme', self.receive, self.scheme, self.sub_scheme)
        self.prompt.set_prompt()

    def postprocess(self, answer):
        results = self.postprocess_sm(self.receive, answer, self.scheme, self.sub_scheme)
        results_dict = results.model_dump()
        results_json = json.dumps(results_dict, ensure_ascii=False)
        results=str(results_json)
        results = results.encode('utf-8')
        results = io.BytesIO(results)
        for re in results:
            yield re
        return           
        
    def postprocess_sm(self, receive, answer, scheme, sub_scheme):
        params = receive
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

        if scheme == "pick_therapy":
            pick_therapy_item = []
            for item in json_data:
                pick_therapy_item.append(PickTherapy(
                    picked_therapy=therapy_scheme_fields[item['方案名称']],
                    interpret_therapy=item['方案解读']
                ))
            params.output.pick_therapy = pick_therapy_item

        elif scheme == "default_therapy":
            match sub_scheme:
                case "prescription":
                    if '处方' in json_data and json_data['处方']:
                        prescription_item = []
                        for item in json_data['处方']:
                            query_item = item['药品名称']
                            query_result = query_fastbm25(self.args.fastbm25_path, query_item, "prescription")
                            if self.args.fastbm25 and query_result:
                                query_item = query_result[0][0]
                                sql_str = f"SELECT id, drug_code, drug_name, drug_specification, pharmacy_unit, \
                                    drug_formulation, COALESCE(alias, drug_name) AS name FROM prescription_info \
                                    WHERE name=\"{query_item}\""
                                search_result = search_database(self.db_engine, sql_str)
                                prescription_item.append(PrescriptionContent(
                                    drug_id=search_result[0][1],
                                    drug_name=item['药品名称'],
                                    drug_name_retrieve=search_result[0][2],
                                    drug_specification=search_result[0][3],
                                    manufacturer_name=item['厂家名称'],
                                    order_quantity=str(item['开单数量']),
                                    order_unit=search_result[0][4],
                                    route_of_administration=search_result[0][5],
                                    dosage=str(item['单次剂量']) if '单次剂量' in item.keys() else str(item['单次用量']),
                                    duration=item['持续天数'],
                                    frequency=item['用药频次'],
                                    corresponding_diseases=item['针对疾病'],
                                    drug_efficacy=item['药品作用']
                                ))
                            else:
                                prescription_item.append(PrescriptionContent(
                                    drug_id=item['药品编号'],
                                    drug_name=item['药品名称'],
                                    drug_name_retrieve="",
                                    drug_specification=item['药品规格'],
                                    manufacturer_name=item['厂家名称'],
                                    order_quantity=str(item['开单数量']),
                                    order_unit=item['开单单位'],
                                    route_of_administration=item['用药途径'],
                                    dosage=str(item['单次剂量']) if '单次剂量' in item.keys() else str(item['单次用量']),
                                    duration=item['持续天数'],
                                    frequency=item['用药频次'],
                                    corresponding_diseases=item['针对疾病'],
                                    drug_efficacy=item['药品作用']
                                ))
                        params.output.default_therapy.prescription.append(Prescription(prescription_content=prescription_item))

                case "transfusion":
                    if '输液' in json_data and json_data['输液']:
                        transfusion_item = []
                        for item in json_data['输液']:
                            query_item = item['药品名称']
                            query_result = query_fastbm25(self.args.fastbm25_path, query_item, "prescription")
                            if self.args.fastbm25 and query_result:
                                query_item = query_result[0][0]
                                sql_str = f"SELECT id, drug_code, drug_name, drug_specification, pharmacy_unit, \
                                    drug_formulation, COALESCE(alias, drug_name) AS name FROM prescription_info \
                                    WHERE name=\"{query_item}\""
                                search_result = search_database(self.db_engine, sql_str)
                                transfusion_item.append(TransfusionContent(
                                    drug_id=search_result[0][1],
                                    drug_name=item['药品名称'],
                                    drug_name_retrieve=search_result[0][2],
                                    drug_specification=search_result[0][3],
                                    manufacturer_name=item['厂家名称'],
                                    order_quantity=str(item['开单数量']),
                                    order_unit=search_result[0][4],
                                    route_of_administration=search_result[0][5],
                                    dosage=str(item['单次剂量']) if '单次剂量' in item.keys() else str(item['单次用量']),
                                    duration=item['持续天数'],
                                    frequency=item['用药频次'],
                                    corresponding_diseases=item['针对疾病'],
                                    drug_efficacy=item['药品作用'],
                                    infusion_group=item['输液分组'],
                                    infusion_rate=item['输液速度']
                                ))
                            else:
                                transfusion_item.append(TransfusionContent(
                                    drug_id=item['药品编号'],
                                    drug_name=item['药品名称'],
                                    drug_name_retrieve="",
                                    drug_specification=item['药品规格'],
                                    manufacturer_name=item['厂家名称'],
                                    order_quantity=str(item['开单数量']),
                                    order_unit=item['开单单位'],
                                    route_of_administration=item['用药途径'],
                                    dosage=str(item['单次剂量']) if '单次剂量' in item.keys() else str(item['单次用量']),
                                    duration=item['持续天数'],
                                    frequency=item['用药频次'],
                                    corresponding_diseases=item['针对疾病'],
                                    drug_efficacy=item['药品作用'],
                                    infusion_group=item['输液分组'],
                                    infusion_rate=item['输液速度']
                                ))
                        params.output.default_therapy.transfusion.append(Transfusion(transfusion_content=transfusion_item))

                case "disposition":
                    if '处置' in json_data and json_data['处置']:
                        disposition_item = []
                        for item in json_data['处置']:
                            disposition_item.append(DispositionContent(
                                disposition_id=item['项目编号'],
                                disposition_name=item['项目名称'],
                                disposition_name_retrieve="",
                                frequency=item['频次'],
                                dosage=str(item['单次用量']) if '单次用量' in item.keys() else str(item['单次剂量']),
                                duration=item['持续时间']
                            ))
                        params.output.default_therapy.disposition.append(Disposition(disposition_content=disposition_item))

        elif scheme == "other_therapy":
            if '治疗方案' in json_data and json_data['治疗方案']:
                method_item = []
                for item in json_data['治疗方案']:
                    method_item.append(MethodTherapyContent(
                        method_code=item['治疗编号'],
                        method_type=item['治疗类型'],
                        method_name=item['治疗名称'],
                        method_name_retrieve="",
                        corresponding_diseases=item['针对疾病'],
                        method_plan=item['治疗计划'],
                        method_risk=item['潜在风险']
                    ))
                getattr(params.output, sub_scheme).method.append(MethodTherapy(methodtherapy_content=method_item))

        return params
