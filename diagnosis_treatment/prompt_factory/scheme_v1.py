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

from ..prompt_template import *

@register_prompt
class PromptScheme_v1(PromptTemplate):
    def __init__(self, receive, scheme, sub_scheme) -> None:
        super().__init__()
        self.scheme = scheme
        self.sub_scheme = sub_scheme
        self.ci_p = receive.input.client_info[0].patient
        self.bmr = receive.input.basic_medical_record
        self.diag = receive.input.diagnosis
        #self.diagnose_definite = [(item.diagnosis_name_retrieve or item.diagnosis_name)
        #    for item in self.diag if item.diagnosis_identifier == "确诊"]
        self.diagnose_definite = [(item.diagnosis_name_retrieve or item.diagnosis_name)
            for item in self.diag]
        self.pick_therapy = receive.output.pick_therapy

    def set_prompt(self):
        self.prompt = {
            "61": self.__set_default_therapy(),
        }
        return self.prompt

    def __interpret_therapy(self, picked_therapy):
        if self.pick_therapy != []:
            interpret_therapy = [i.interpret_therapy for i in self.pick_therapy if i.picked_therapy == picked_therapy]
        else:
            interpret_therapy = ['无']
        return interpret_therapy

    def __set_default_therapy(self):
        other_therapy_map = {
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
        if self.scheme == "pick_therapy":
            #挑选多方案
            system_str=f"""你是一个优秀的专业医生。主要工作是根据患者的病历，从如下9个方案名称中挑选合适的：\
“保守治疗、手术治疗、化疗、放疗、心理治疗、康复治疗、物理治疗、替代疗法、观察治疗”，并对选中的每个方案都生成100字以上的方案解读，\
最后以json格式返回，例如：{self.format_pick_therapy}。生成时先说“您已确诊，现在为您生成方案：”。\
注意：挑选的方案必须在上边所列的9个方案名称中，且需要挑选3~5个方案，其中必须要包含保守治疗。"""
            user_str=f"""当前患者的姓名是{self.ci_p.patient_name}，性别是{self.ci_p.patient_gender}，年龄是{self.ci_p.patient_age}，\
主诉是“{self.bmr.chief_complaint}”，现病史是“{self.bmr.history_of_present_illness}”，\
个人史是“{self.bmr.personal_history}”，过敏史是“{self.bmr.allergy_history}”，\
体格检查是“{self.bmr.physical_examination}”，辅助检查是“{self.bmr.auxiliary_examination}”，\
患者确诊的疾病有{self.diagnose_definite}，请生成“方案”。"""

        elif self.scheme == "default_therapy":
            match self.sub_scheme:
                case "prescription":
                    #生成处方
                    system_str=f"""你是一个优秀的专业医生。主要工作是根据患者的病历，合理开药并生成处方。\
注意，病历中包含的所有疾病都需要开出对应的药品。请注意，你必须给出尽可能全面的药品名称**及其详细的医学依据，\
包括药品的具体作用和开药的理由**。
处方的格式严格按照如下：{self.format_prescription}。
遵循以下步骤进行：
1.读取病历信息：读取病历信息的全部内容，确定患者共有几种疾病，及所患疾病的名称。
2.分析诊断信息：根据诊断信息确定患者共患几种疾病。
3.为每种疾病分别确定治疗方案：根据每种疾病，参考相关医学指南和常用治疗方案，选择合适的药物进行治疗。\
确定每种疾病对应的药物名称、规格、用法用量、频率、疗程和其他相关信息。
请注意，输出前请检查处方中要包含对每一种确诊疾病的药品。生成的药品名称要使用中文，严禁使用英文。\
给出的处方中不能包含注射类药物。
生成时先说“您已确诊，现在为您生成处方：”。"""
                    user_str=f"""当前采用的方案是“{other_therapy_map['default_therapy']}”，方案解读是{self.__interpret_therapy('default_therapy')}，\
患者确诊的疾病有{self.diagnose_definite}，请对每项疾病都生成对应的“处方”。"""
                case "transfusion":
                    #生成输液
                    system_str=f"""你是一个优秀的专业医生。主要工作是根据患者的病历，合理开药并生成输液方案。\
注意，病历中包含的所有疾病都需要开出对应的输液。请注意，你必须给出尽可能全面的药品名称**及其详细的医学依据，\
包括药品的具体作用和开药的理由**。
输液的格式严格按照如下：{self.format_transfusion}。
遵循以下步骤进行：
1.读取病历信息：读取病历信息的全部内容，确定患者共有几种疾病，及所患疾病的名称。
2.分析诊断信息：根据诊断信息确定患者共患几种疾病。
3.为每种疾病分别确定治疗方案：根据每种疾病，参考相关医学指南和常用治疗方案，选择合适的输液药品进行治疗。\
确定每种疾病对应的药物名称、规格、用法用量、频率、疗程和其他相关信息。
请注意，输出前请检查输液中要包含对每一种确诊疾病的药品。生成的药品名称要使用中文，严禁使用英文。\
给出的输液中只能包含注射类药物，不能包含片剂、胶囊剂、口服散剂、中药等药物。
生成时先说“您已确诊，现在为您生成输液：”。"""
                    user_str=f"""当前采用的方案是“{other_therapy_map['default_therapy']}”，方案解读是{self.__interpret_therapy('default_therapy')}，\
患者确诊的疾病有{self.diagnose_definite}，请对每项疾病都生成对应的“输液”。"""
                case "disposition":
                    #生成处置
                    system_str=f"""你是一个优秀的专业医生。主要工作是根据患者的病历，生成处置。处置的格式严格按照如下：\
{self.format_disposition}。生成时先说“您已确诊，现在为您生成处置：”。注意：处置要包含项目编号、项目名称、频次、\
单次用量、持续时间，不可以漏项。处置中可以生成1~2组处置项。"""
                    user_str=f"""当前患者的主诉是“{self.bmr.chief_complaint}”，现病史是“{self.bmr.history_of_present_illness}”，\
个人史是“{self.bmr.personal_history}”，过敏史是“{self.bmr.allergy_history}”，\
体格检查是“{self.bmr.physical_examination}”，辅助检查是“{self.bmr.auxiliary_examination}”，\
当前采用的方案是“{other_therapy_map['default_therapy']}”，方案解读是{self.__interpret_therapy('default_therapy')}，\
患者确诊的疾病有{self.diagnose_definite}，请生成“处置”。"""

        elif self.scheme == "other_therapy":
            #生成治疗方案
            cked_therapy = other_therapy_map[self.sub_scheme]
            system_str=f"""你是一个优秀的专业医生。主要工作是根据患者的病历，参考相关医学指南与医疗专业书籍，\
生成关于“{cked_therapy}”的治疗方案。治疗方案包含治疗编号、治疗类型、治疗名称、针对疾病、治疗计划、潜在风险。\
治疗方案的格式严格按照如下：{self.format_generate_therapy}。生成时先说“您已确诊，现在为您生成治疗方案：”。\
注意：治疗计划要进行充分且详尽的描述。"""
            user_str=f"""当前患者的姓名是{self.ci_p.patient_name}，性别是{self.ci_p.patient_gender}，年龄是{self.ci_p.patient_age}，\
主诉是“{self.bmr.chief_complaint}”，现病史是“{self.bmr.history_of_present_illness}”，\
个人史是“{self.bmr.personal_history}”，过敏史是“{self.bmr.allergy_history}”，\
体格检查是“{self.bmr.physical_examination}”，辅助检查是“{self.bmr.auxiliary_examination}”，\
当前采用的方案是“{other_therapy_map[self.sub_scheme]}”，方案解读是{self.__interpret_therapy(self.sub_scheme)}，\
患者确诊的疾病有{self.diagnose_definite}，请生成关于“{cked_therapy}”的治疗方案。"""
        return system_str, user_str
    