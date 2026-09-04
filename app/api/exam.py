from fastapi import APIRouter, HTTPException

from app.models import JoinExamRequest, SubmitRequest, AnswerItem
from app.services import exam_service, grading_service, question_service, record_service


router = APIRouter()


@router.get("/specialties")
async def get_specialties():
    return {"specialties": question_service.get_specialties()}


@router.post("/exams/join")
async def join_exam(req: JoinExamRequest):
    """候选人凭邀请码 + 姓名加入考试，建立 CandidateSession。"""
    name = req.candidate_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写姓名")
    try:
        return exam_service.join_exam(req.invite_code.strip(), name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/exam/start")
async def start_exam(
    specialty: str = "",
    candidate_name: str = "",
    exam_id: str = "",
    candidate_session_id: str = "",
    visitor_id: str = "",
):
    """开始考试。

    无 exam_id：公开自测（mode=public，可选 visitor_id 归档个人记录）。
    带 exam_id：正式考试（mode=exam），同一候选人同一场仅允许一次作答。
    """
    specialties_actual = specialty
    duration_override: int | None = None
    min_subjective, max_subjective = 2, 4
    mode = "public"
    session_id: str | None = candidate_session_id or None

    if exam_id:
        exam = exam_service.get_exam(exam_id)
        if exam is None:
            raise HTTPException(status_code=404, detail="考试不存在或链接无效")
        if exam["status"] != "active":
            raise HTTPException(status_code=403, detail="该考试已关闭")
        if exam["specialties"]:
            specialties_actual = ",".join(exam["specialties"])
        duration_override = exam["duration"]
        if not exam["enable_subjective"]:
            min_subjective = max_subjective = 0
        mode = "exam"

        # 单次作答：同一候选人同一场考试已有提交则拒绝；进行中引导继续
        existing = record_service.find_existing_exam_attempt(exam_id, candidate_name)
        if existing:
            if existing["status"] == "submitted":
                raise HTTPException(status_code=403, detail="该场考试已完成作答")
            raise HTTPException(
                status_code=409,
                detail="该场考试已有进行中的作答，请返回继续",
            )

    paper = question_service.generate_exam(
        specialties_actual,
        min_subjective=min_subjective,
        max_subjective=max_subjective,
    )
    question_ids = [q["id"] for q in paper["questions"]]
    paper["record_id"] = record_service.create_record(
        specialty=paper["specialty"],
        question_ids=question_ids,
        candidate_name=candidate_name,
        exam_id=exam_id or None,
        mode=mode,
        visitor_id=visitor_id or None,
        candidate_session_id=session_id,
    )
    if duration_override:
        paper["time_limit_minutes"] = duration_override
    return paper


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
    # 若属于某场管理员考试，按其 enable_ai 配置决定是否调用 AI
    allow_ai = True
    if request.record_id:
        record = record_service.get_record(request.record_id)
        if record and record.get("exam_id"):
            exam = exam_service.get_exam(record["exam_id"])
            if exam:
                allow_ai = exam["enable_ai"]
    return await grading_service.submit_exam(request, allow_ai=allow_ai)


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "total_questions": question_service.get_total_question_count(),
    }
