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

from hospital_follow_up import FollowUp
import json
import copy

OPENAI_API_KEY = "EMPTY"
OPENAI_API_BASE = "http://10.130.7.2:8000/v1/"
MODEL_NAME = "model_medical_20250122"
QUESTION_FILE = "question.json"

question_list = []
output_text = ""
g_question_json_data = None


follow_up_chat = [
    [],
    [{"role": "assistant", "content":"您好，我是您的随访助手，希望您最近身体状况良好。我有几个问题需要向您了解，可以吗？首先，最近身体有没有什么不舒服的地方？比如胸痛、胸闷、肌肉酸痛、心悸或者呼吸困难？"},
     {"role": "user", "content":"我有时候会胸痛"}],
    [{"role": "assistant", "content":"了解了，这种胸痛是在什么情况下出现的？是休息的时候也有，还是日常活动的时候感觉不明显，或者日常活动的时候感觉明显？"},
     {"role": "user", "content":"活动时明显。"}],
    [{"role": "assistant", "content":"明白了，您最近身体有没有出血的情况？比如皮肤、口腔粘膜出血，黑便或者血便，血尿，咳血？"},
     {"role": "user", "content":"没有。"}],
    [{"role": "assistant", "content":"好的，您最近有测量过体重吗？现在的体重是多少？"},
     {"role": "user", "content":"最近没称过，大概140斤左右。"}],
    [{"role": "assistant", "content":"了解了，您最近的运动情况怎么样？是规律运动，还是不规律运动？"},
     {"role": "user", "content":"偶尔运动。"}],
    [{"role": "assistant", "content":"明白了，您出院后的睡眠质量怎么样？是睡得挺香的，还是有时候会睡不着，或者容易醒，或者总是觉得困？"},
     {"role": "user", "content":"睡眠还可以。"}],
    [{"role": "assistant", "content":"好的，您出院后的情绪状态怎么样？是心情愉快，还是有时候会感到焦虑、抑郁，或者容易暴躁？"},
     {"role": "user", "content":"跟以前一样。"}],
    [{"role": "assistant", "content":"了解了，自从得了这个病以来，现在的工作承受能力怎么样？是正常，还是轻度受限制，严重受限，还是卧床为主？"},
     {"role": "user", "content":"还工作跟之前一样，座久了稍累。"}],
    [{"role": "assistant", "content":"明白了，您现在的饮食习惯怎么样？是清淡，偏咸，辛辣，肥腻，还是喜甜？"},
     {"role": "user", "content":"一般比较清淡。"}],
    [{"role": "assistant", "content":"好的，您现在有没有吸烟的情况？是不吸烟，仍在吸烟，还是正在戒烟？"},
     {"role": "user", "content":"我不吸烟。"}],
    [{"role": "assistant", "content":"了解了，您现在的饮酒情况怎么样？是从不饮酒，还是有饮酒？"},
     {"role": "user", "content":"偶尔喝点。"}],
    [{"role": "assistant", "content":"明白了，您常喝的是哪种酒？是白酒，红酒，还是啤酒？"},
     {"role": "user", "content":"一天一瓶啤酒。"}],
    [{"role": "assistant", "content":"了解了，您能坚持按照医嘱规律服用心脏相关药物吗？是能，还是不能？"},
     {"role": "user", "content":"不能。"}],
    [{"role": "assistant", "content":"明白了，您不能坚持服药的原因是什么呢？"},
     {"role": "user", "content":"有时候忙忘了。"}]
]


def convert_json_to_problems():
     global output_text, g_question_json_data
     with open(QUESTION_FILE, 'r') as json_file:
          g_question_json_data = json.load(json_file)
          for question in g_question_json_data["questionsList"]:
               question_text = f"{question['questionId']}） {question['questionContent']}（{question['questionType']}）\n"
               output_text += question_text
               if question["questionType"] == "多选题" or question["questionType"] == "单选题":

                    for option in question["questionOptions"]:
                         option_text = f"  {option['questionOptionId']}  {option['questionOptionContent']}   "
                         output_text += option_text
               elif  question["questionType"] == "填空题":
                    pass
               output_text += "\n\n"     

     print(f"***lmx*** output_text output_text {output_text}")

def generate_new_questions_structure(original_questions, original_answers):
    answer_dict = {item["qid"]: item["a"] for item in original_answers}
    new_structure = []
    for question in original_questions:
        new_question = question.copy()
        qid = question["questionId"]
        if qid in answer_dict:
            new_question["questionAnswer"] = []
            for answer in answer_dict[qid]:
                if "val" in answer:
                    answer_content = answer["val"]
                else:
                    option_id = answer["id"]
                    for option in question["questionOptions"]:
                        if option["questionOptionId"] == option_id:
                            answer_content = option["questionOptionContent"]
                            break
                new_question["questionAnswer"].append({
                    "questionAnswerId": answer["id"],
                    "questionAnswerContent": answer_content
                })
        new_structure.append(new_question)
    # return [{"questionsList": new_structure}]
    return new_structure

def generate_followup_report(original_json_data, chat_history, original_answers):
     followup_report = copy.deepcopy(original_json_data)
     followup_report["chat"] = chat_history
     question_list_with_answer = generate_new_questions_structure(followup_report["questionsList"], original_answers)
     followup_report["questionsList"] = question_list_with_answer
     return followup_report

if __name__ == '__main__':
     convert_json_to_problems()
     follow_up_obj = FollowUp(OPENAI_API_BASE, OPENAI_API_KEY, MODEL_NAME, output_text)

     new_questionnaire = follow_up_obj.generate_new_questionnaire_by_input()
     print(f"new_questionnaire {new_questionnaire}")

     temp_chat_info = []
     for chat_info in follow_up_chat:
          temp_chat_info.extend(chat_info)
          new_question = follow_up_obj.generate_new_question_by_chat(temp_chat_info)
          print(f"new_question {new_question}")

     # 根据对话内容，生成问卷报告
     questionnaire_answer = follow_up_obj.generate_questionnaire_answer_by_chat(temp_chat_info) 
     print(f"questionnaire_answer {questionnaire_answer}")

     questionnaire_answer_json_data = json.loads(questionnaire_answer)
     print(questionnaire_answer_json_data)

     # 根据对话内容 + 模型理解答案 + 原始问卷回答格式，产出问卷报告
     followup_report_ret = generate_followup_report(g_question_json_data, temp_chat_info, questionnaire_answer_json_data)
     js_followup_report_ret = json.dumps(followup_report_ret, ensure_ascii=False)
     print(f"js_followup_report_ret {js_followup_report_ret}")
