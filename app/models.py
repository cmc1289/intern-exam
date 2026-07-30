from pydantic import BaseModel


class AnswerItem(BaseModel):
    question_id: int
    user_answer: str | list[str]


class SubmitRequest(BaseModel):
    record_id: str | None = None
    answers: list[AnswerItem]
