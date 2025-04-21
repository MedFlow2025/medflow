from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

NEW_QUESTIONNAIRE_PROMPT = "以下是改写后的问题："
QUESTIONNAIRE_FINISH_PROMPT ="问卷已经完成"

class QuestionType(Enum):
    MULTIPLE_CHOICE = "多选题"
    SINGLE_CHOICE = "单选题"
    FILL_IN_THE_BLANK = "填空题"


class ChatRoleType(Enum):
    USER_ROLE = "user"
    ASSISTANT_ROLE = "assistant"
    SYSTEM_ROLE = "system"


class ChatKeyType(Enum):
    ROLE_KEY = "role"
    CONTENT_KEY = "content"


class QuestionOption(BaseModel):
    questionOptionId: str
    questionOptionContent: str


class QuestionAnswer(BaseModel):
    questionAnswerId: str
    questionAnswerContent: str


class Question(BaseModel):
    questionId: str
    questionContent: str
    questionType: str
    questionOptions: Optional[List[QuestionOption]] = None
    questionRelation: Optional[str] = None
    questionAnswer: Optional[List[QuestionAnswer]] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class Questionnaire(BaseModel):
    questionsList: List[Question]
    chat: List[ChatMessage] | None = None
    questionsListTransformByLLM: str | None = None
    questionName: str
    qId: str


class FollowUpAPIRequest(BaseModel):
    input: Questionnaire 


class FollowUpAPIResponse(BaseModel):
    output: Questionnaire 
