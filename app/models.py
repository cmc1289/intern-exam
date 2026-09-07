from pydantic import BaseModel


class AnswerItem(BaseModel):
    question_id: int
    user_answer: str | list[str]


class SubmitRequest(BaseModel):
    record_id: str | None = None
    answers: list[AnswerItem]


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateExamRequest(BaseModel):
    title: str
    specialties: list[str]
    duration: int = 30
    enable_subjective: bool = True
    enable_ai: bool = True


class JoinExamRequest(BaseModel):
    invite_code: str
    candidate_name: str


class BankExpandRequest(BaseModel):
    module: str
    topics: list[str] = []
    urls: list[str] = []
    instruction: str = ""
    mode: str = "brainstorm"  # brainstorm=快速脑暴 / url=URL 定向清洗出题
    dry_run: bool = False
