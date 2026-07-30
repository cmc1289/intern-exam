from fastapi import APIRouter

from app.models import SubmitRequest
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


@router.post("/exam/submit")
async def submit_exam(request: SubmitRequest):
    return await grading_service.submit_exam(request)


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "total_questions": question_service.get_total_question_count(),
    }
