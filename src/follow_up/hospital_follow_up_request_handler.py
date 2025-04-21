from typing import List
from openai import OpenAI, AsyncOpenAI
import asyncio
import re
import json
from fastapi import  HTTPException
from jinja2 import Template
from .hospital_follow_up_data_models import *


class HospitalFollowUpRequestHandler():
    def __init__(self,
                 receive:FollowUpAPIRequest,
                 args,
                 prompt_conf = None
                 ):
        self.receive = receive
        self.args = args
        self.openai_api_key = args.api_key
        # args.model_url 这个参数实际是openai_base_url
        self.openai_base_url = args.model_url
        self.model = args.model    
        self.async_client = AsyncOpenAI(api_key = self.openai_api_key, base_url = self.openai_base_url)
        self.prompt_conf = prompt_conf


    async def async_predict_streaming(self, messages, temp=0, top_p=1):
        stream = await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=temp,
            top_p=top_p,
            max_tokens=4096,
            timeout=60
        )
        try:
            async for completion in stream:
                delta_content = completion.choices[0].delta.content or ""
                yield delta_content
        except Exception as e:
            print(f"发生异常: {e}")


    async def async_predict_non_streaming(self, messages, temp=0, top_p=1):
        stream = await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=temp,
            top_p=top_p,
            max_tokens=4096,
            timeout=60
        )
        answer = ""
        try:
            async for completion in stream:
                answer += (completion.choices[0].delta.content or "")
            return answer
        except Exception as e:
            print(f"发生异常: {e}")
            return None


    def convert_request_to_problems(self):
        output_text = ""
        for question in self.receive.input.questionsList:
            question_text = f"{question.questionId}） {question.questionContent}（{question.questionType}）\n"
            output_text += question_text
            if question.questionType == QuestionType.MULTIPLE_CHOICE.value or question.questionType == QuestionType.SINGLE_CHOICE.value:
                for option in question.questionOptions:
                        option_text = f"  {option.questionOptionId}  {option.questionOptionContent}   "
                        output_text += option_text
            elif  question.questionType == QuestionType.FILL_IN_THE_BLANK.value:
                pass
            output_text += "\n\n"
        return output_text


    def get_new_questionnaire_prompt(self, follow_up_questionnaire:str):
        template_str = self.prompt_conf["follow_up_prompts"]["generate_questions"]["versions"]["v1"]
        variables = {
            "follow_up_questionnaire": follow_up_questionnaire,
            "NEW_QUESTIONNAIRE_PROMPT": NEW_QUESTIONNAIRE_PROMPT
        }
        template = Template(template_str)
        system_str = template.render(**variables)
        return system_str


    async def process_to_generate_new_questionnaire(self) -> FollowUpAPIResponse:
        request_to_problems = self.convert_request_to_problems()
        question_message = self.get_new_questionnaire_prompt(request_to_problems)
        messages=[{"role": ChatRoleType.SYSTEM_ROLE.value, "content": question_message}]
        answer =  await self.async_predict_non_streaming(messages)

        # 使用 re.sub 函数进行替换，将开头的特定内容替换为空字符串
        answer = re.sub(rf"^{NEW_QUESTIONNAIRE_PROMPT}", "", answer)
        response = FollowUpAPIResponse(output=self.receive.input)
        response.output.questionsListTransformByLLM = answer
        return response


    def get_question_chat_prompt(self, new_questionnaire:str):
        template_str = self.prompt_conf["follow_up_prompts"]["generate_chat"]["versions"]["v1"]
        variables = {
            "new_questionnaire": new_questionnaire
        }
        template = Template(template_str)
        system_str = template.render(**variables)
        return system_str


    async def process_to_generate_chat(self) -> FollowUpAPIResponse:
        messages_list = []
        for chat_message in self.receive.input.chat:
            messages_list.append({"role": chat_message.role, "content": chat_message.content})
            if QUESTIONNAIRE_FINISH_PROMPT in chat_message.content:
                raise HTTPException(status_code=400, detail=f"{QUESTIONNAIRE_FINISH_PROMPT}, 不用重复调用。")
        question_message = self.get_question_chat_prompt(self.receive.input.questionsListTransformByLLM)
        messages_list.append({"role": ChatRoleType.SYSTEM_ROLE.value, "content": question_message})   
        answer =  await self.async_predict_non_streaming(messages_list)
        response = FollowUpAPIResponse(output=self.receive.input)
        chat_message_dic = {"role": ChatRoleType.SYSTEM_ROLE.value, "content": answer}
        response.output.chat.append(ChatMessage(**chat_message_dic))
        return response


    def get_questionnaire_answer_prompt(self, follow_up_questionnaire:str):
        template_str = self.prompt_conf["follow_up_prompts"]["generate_report"]["versions"]["v1"]
        variables = {
            "follow_up_questionnaire": follow_up_questionnaire
        }
        template = Template(template_str)
        system_str = template.render(**variables)
        return system_str


    def merge_answer_to_obj(self, response_obj:FollowUpAPIResponse, answer:str):
        try:
            answer_data_list = json.loads(answer)
            for answer_data in answer_data_list:
                qid = answer_data["qid"]
                options = answer_data["a"]

                # 查找对应的问题对象
                for question in response_obj.output.questionsList:
                    if question.questionId == qid:
                    # 构建问题答案对象列表
                        question_answers = []
                        for option in options:
                            option_id = option["id"]
                            answer_id = option_id  

                            if "val" in option:
                                # 填空题
                                answer_content = option["val"]
                            else:
                                # 选择题
                                for question_option in question.questionOptions:
                                    if question_option.questionOptionId == option_id:
                                        answer_content = question_option.questionOptionContent
                            question_answer = QuestionAnswer(
                                questionAnswerId=answer_id,
                                questionAnswerContent=answer_content
                            )
                            question_answers.append(question_answer)

                        # 将答案信息添加到问题对象中
                        question.questionAnswer = question_answers
                        break
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"follow up report answer {answer} error {e}。")


    async def process_to_generate_report(self) -> FollowUpAPIResponse:
        request_to_problems = self.convert_request_to_problems()
        messages_list = []
        for chat_message in self.receive.input.chat:
            messages_list.append({"role": chat_message.role, "content": chat_message.content})
        question_message = self.get_questionnaire_answer_prompt(request_to_problems)
        messages_list.append({"role": ChatRoleType.USER_ROLE.value, "content": question_message})   
        answer =  await self.async_predict_non_streaming(messages_list)
        response = FollowUpAPIResponse(output=self.receive.input)
        self.merge_answer_to_obj(response, answer=answer)
        return response