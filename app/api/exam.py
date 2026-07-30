from fastapi import APIRouter, HTTPException

from app.models import SubmitRequest, AnswerItem
from app.services import grading_service, question_service, record_service


router = APIRouter()


@router.get("/specialties")
async def get_specialties():
    return {"specialties": question_service.get_specialties()}


@router.get("/exam/start")
async def start_exam(specialty: str = "", candidate_name: str = ""):
    exam = question_service.generate_exam(specialty)
    question_ids = [q["id"] for q in exam["questions"]]
    exam["record_id"] = record_service.create_record(
        specialty=exam["specialty"],
        question_ids=question_ids,
        candidate_name=candidate_name,
    )
    return exam


@router.get("/exam/resume/{record_id}")
async def resume_exam(record_id: str):
    record = record_service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if record["status"] != "started":
        raise HTTPException(status_code=403, detail="该考试已结束或已超时，无法继续答题")

    question_ids = record["question_ids"]
    questions = question_service.get_questions_by_ids(question_ids)
    exam_config = question_service.get_exam_config()

    return {
        "record_id": record_id,
        "questions": questions,
        "answers": record["answers"],
        "total": len(questions),
        "full_score": exam_config["full_score"],
        "pass_score": exam_config["pass_score"],
        "time_limit_minutes": exam_config["time_limit_minutes"],
        "specialty": record["specialty"],
        "started_at": record["started_at"],
    }


@router.post("/exam/save/{record_id}")
async def save_progress(record_id: str, answers: list[AnswerItem]):
    ok = record_service.save_progress(
        record_id,
        [{"question_id": a.question_id, "user_answer": a.user_answer} for a in answers],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在或已结束")
    return {"status": "ok"}


@router.post("/exam/submit")
async def submit_exam(request: SubmitRequest):
    return await grading_service.submit_exam(request)


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "total_questions": question_service.get_total_question_count(),
    }
