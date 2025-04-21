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

from typing import List, Union
from pydantic import BaseModel, Field

class HistoricalConversations(BaseModel):
    role: str = ""
    content: str = ""

class Chat(BaseModel):
    historical_conversations_bak: List[HistoricalConversations] = Field(default_factory=list)
    historical_conversations: List[HistoricalConversations] = Field(default_factory=list)
    prompt_version: str = ""
    model_name: str = ""

class PhyscialExamination(BaseModel):
    temperature: str = ""
    pulse: str = ""
    blood_pressure: str = ""
    respiration: str = ""

class BasicMedicalRecord(BaseModel):
    chief_complaint: str
    history_of_present_illness: str
    past_medical_history: str
    personal_history: str
    allergy_history: str
    physical_examination: PhyscialExamination
    auxiliary_examination: str

class DoctorMedicalRecord(BaseModel):
    chief_complaint: str = ""
    history_of_present_illness: str = ""
    past_medical_history: str = ""
    personal_history: str = ""
    allergy_history: str = ""
    physical_examination: PhyscialExamination = Field(default_factory=PhyscialExamination)
    auxiliary_examination: str = ""
    specialty_examination: str = ""
    cure: str = ""
    doctor_advice: str = ""

# v0  zh: fen fa, distribute
class PatientNeed(BaseModel):
    need: str

class OutputV0(BaseModel):
    patient_need: List[PatientNeed]

class RequestV0(BaseModel):
    input: None
    output: OutputV0
    chat: Chat


# v1  zh: jian dang, clinet info
class CurrentAddress(BaseModel):
    province: str
    city: str
    district: str
    street: str

class PatientBasic(BaseModel):
    patient_name: str
    patient_gender: str
    patient_age: str

class Patient(PatientBasic):
    if_child: str
    certificate_type: str
    certificate_number: str
    mobile_number: str
    current_address: CurrentAddress
    detailed_address: str

class Guardian(BaseModel):
    guardian_name: str
    certificate_type: str
    certificate_number: str

class ClientInfo(BaseModel):
    patient: Patient
    guardian: Guardian

class InputV1(BaseModel):
    client_info: Union[List[ClientInfo], List[None]]

class OutputV1(BaseModel):
    client_info: List[ClientInfo]
    create_file: str

class RequestV1(BaseModel):
    input: InputV1
    output: OutputV1
    chat: Chat


# v2  zh: yu wen zhen, basic medical record
class InputV2(BaseModel):
    client_info: Union[List[ClientInfo], List[None]]

class OutputV2(BaseModel):
    basic_medical_record: BasicMedicalRecord

class RequestV2(BaseModel):
    input: InputV2
    output: OutputV2
    chat: Chat


# v3  zh: gua hao, register diagnosis
class RegisterIntention(BaseModel):
    intention_tpye: str | None = None
    department_name: str| None = None
    doctor_name: str | None = None
    doctor_title: str | None = None
    register_date: str | None = None
    register_time: str | None = None
    register_source: str | None = None
    query_subject: str | None = None
    priority: str | None = None

class TimeList(BaseModel):
    start_time: str
    end_time: str
    source_num: str

class DateList(BaseModel):
    date: str
    time_list: List[TimeList]

class DoctorList(BaseModel):
    doctor_id: str
    doctor_name: str
    doctor_title: str
    date_list: List[DateList] | None = None

class Department(BaseModel):
    department_id: str
    department_name: str

class HospitalRegister(Department):
    doctor_list: List[DoctorList]    
    
class InputV3(BaseModel):
    client_info: List[ClientInfo] | None = None
    basic_medical_record: BasicMedicalRecord
    all_department: List[Department] | None = None
    hospital_register: Union[List[HospitalRegister], List[None]] | None = None
    register_intention_enable: bool | None = None

class OutputV3(BaseModel):
    chosen_department: List[Department]
    hospital_register: List[HospitalRegister]
    register_intention_enable: bool | None = None
    register_intention_info: List[RegisterIntention]  | None = None

class RequestV3(BaseModel):
    input: InputV3
    output: OutputV3
    chat: Chat


# v4  zh: zhen duan, diagnosis
class Diagnosis(BaseModel):
    diagnosis_name: str = ""
    diagnosis_name_retrieve: str = ""
    diagnosis_code: str = ""
    diagnosis_identifier: str = ""

class InputV4(BaseModel):
    client_info: Union[List[ClientInfo], List[None]]
    basic_medical_record: BasicMedicalRecord

class OutputV4(BaseModel):
    diagnosis: List[Diagnosis] = Field(default_factory=lambda: [Diagnosis()])

class RequestV4(BaseModel):
    input: InputV4
    output: OutputV4 = Field(default_factory=OutputV4)
    chat: Chat = Field(default_factory=Chat)


# v5  zh: jian cha hua yan, examine assay
class InputV5(BaseModel):
    client_info: Union[List[ClientInfo], List[None]]
    basic_medical_record: BasicMedicalRecord
    diagnosis: List[Diagnosis]

class ExamineContent(BaseModel):
    examine_code: str = ""
    examine_category: str = ""
    examine_name: str = ""
    examine_name_retrieve: str = ""
    order_quantity: str = ""
    examine_result: str = ""
    corresponding_diagnosis: List[Diagnosis] = Field(default_factory=lambda: [Diagnosis()])

class AssayResult(BaseModel):
    result_id: str = ""
    result_item: str = ""
    result_value: float = 0.0
    result_identifier: str = ""
    reference_value: str = ""
    unit: str = ""
    
class AssayContent(BaseModel):
    assay_code: str = ""
    assay_category: str = ""
    assay_name: str = ""
    assay_name_retrieve: str = ""
    order_quantity: str = ""
    assay_result: List[AssayResult] = Field(default_factory=lambda: [AssayResult()])
    corresponding_diagnosis: List[Diagnosis] = Field(default_factory=lambda: [Diagnosis()])

class OutputV5(BaseModel):
    examine_content: List[ExamineContent] = Field(default_factory=lambda: [ExamineContent()])
    assay_content: List[AssayContent] = Field(default_factory=lambda: [AssayContent()])

class RequestV5(BaseModel):
    input: InputV5
    output: OutputV5 = Field(default_factory=OutputV5)
    chat: Chat = Field(default_factory=Chat)


# v6  zh: zhi liao fang an, therapy scheme
class InputV6(BaseModel):
    client_info: Union[List[ClientInfo], List[None]]
    basic_medical_record: BasicMedicalRecord
    diagnosis: List[Diagnosis]

class PickTherapy(BaseModel):
    picked_therapy: str
    interpret_therapy: str

class MethodTherapyContent(BaseModel):
    method_code: str
    method_type: str
    method_name: str
    method_name_retrieve: str
    corresponding_diseases: str
    method_plan: str
    method_risk: str

class MethodTherapy(BaseModel):
    methodtherapy_content: List[MethodTherapyContent]

class BasicTherapy(BaseModel):
    method: List[MethodTherapy] = Field(default_factory=list)

class PrescriptionContent(BaseModel):
    drug_id: str
    drug_name: str
    drug_name_retrieve: str
    drug_specification: str
    manufacturer_name: str
    order_quantity: str
    order_unit: str
    route_of_administration: str
    dosage: str
    duration: str
    frequency: str
    corresponding_diseases: str
    drug_efficacy: str

class Prescription(BaseModel):
    prescription_content: List[PrescriptionContent]

  
class TransfusionContent(PrescriptionContent):
    infusion_group: str
    infusion_rate: str
        
class Transfusion(BaseModel):
    transfusion_content: List[TransfusionContent]


class DispositionContent(BaseModel):
    disposition_id: str
    disposition_name: str
    disposition_name_retrieve: str
    frequency: str
    dosage: str
    duration: str
    
class Disposition(BaseModel):
    disposition_content: List[DispositionContent]

class DefaultTherapy(BaseModel):
    prescription: List[Prescription] = Field(default_factory=list)
    transfusion: List[Transfusion] = Field(default_factory=list)
    disposition: List[Disposition] = Field(default_factory=list)

class OutputV6(BaseModel):
    pick_therapy: List[PickTherapy] = Field(default_factory=list)
    default_therapy: DefaultTherapy = Field(default_factory=DefaultTherapy)
    surgical_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    chemo_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    radiation_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    psycho_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    rehabilitation_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    physical_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    alternative_therapy: BasicTherapy = Field(default_factory=BasicTherapy)
    observation_therapy: BasicTherapy = Field(default_factory=BasicTherapy)

class RequestV6(BaseModel):
    input: InputV6
    output: OutputV6 = Field(default_factory=OutputV6)
    chat: Chat = Field(default_factory=Chat)


# v7  zh: fu zhen, return visit
class ReturnVisit(BaseModel):
    summary: str
    if_visit: str

class InputV7(BaseModel):
    client_info: List[ClientInfo]
    basic_medical_record: BasicMedicalRecord
    diagnosis: List[Diagnosis]

class OutputV7(BaseModel):
    return_visit: ReturnVisit

class RequestV7(BaseModel):
    input: InputV7
    output: OutputV7
    chat: Chat


# v8  zh: dao zhen, hospital guide
class InputV8(BaseModel):
    client_info: List[ClientInfo]
    all_department: List[Department] | None = None

class OutputV8(BaseModel):
    basic_medical_record: BasicMedicalRecord
    chosen_department: List[Department]

class RequestV8(BaseModel):
    input: InputV8
    output: OutputV8
    chat: Chat


# v9  zh: bing li, doctor medical record
class InputV9(BaseModel):
    medical_templet: str | None = None
    templet_type: str | None = None
    basic_medical_record: DoctorMedicalRecord = Field(default_factory=DoctorMedicalRecord)
    doctor_supplement: str

class OutputV9(BaseModel):
    medical_format: str | None = None
    basic_medical_record: DoctorMedicalRecord | None = None

class RequestV9(BaseModel):
    input: InputV9
    output: OutputV9 = Field(default_factory=OutputV9)
    chat: Chat  = Field(default_factory=Chat)