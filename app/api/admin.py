from fastapi import APIRouter, Depends, HTTPException

from app.config import ADMIN_PASSWORD, ADMIN_TOKEN, ADMIN_USERNAME
from app.models import CreateExamRequest, LoginRequest
from app.services import exam_service

from app.api.records import verify_admin


router = APIRouter()


@router.post("/login")
async def login(req: LoginRequest):
    if req.username == ADMIN_USERNAME and req.password == ADMIN_PASSWORD:
        return {"token": ADMIN_TOKEN, "username": req.username}
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.get("/dashboard")
async def dashboard(_: bool = Depends(verify_admin)):
    return exam_service.dashboard()


@router.post("/exams")
async def create_exam(req: CreateExamRequest, _: bool = Depends(verify_admin)):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="考试名称不能为空")
    if not req.specialties:
        raise HTTPException(status_code=400, detail="至少选择一个专业方向")
    exam = exam_service.create_exam(req)
    return exam


@router.get("/exams")
async def list_exams(_: bool = Depends(verify_admin)):
    return {"exams": exam_service.list_exams()}


@router.get("/exams/{exam_id}")
async def exam_detail(exam_id: str, _: bool = Depends(verify_admin)):
    exam = exam_service.get_exam(exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="考试不存在")
    candidates = exam_service.exam_candidates(exam_id)
    return {"exam": exam, "candidates": candidates}


@router.delete("/exams/{exam_id}")
async def delete_exam(exam_id: str, _: bool = Depends(verify_admin)):
    """删除考试及其全部候选人记录。"""
    if not exam_service.delete_exam(exam_id):
        raise HTTPException(status_code=404, detail="考试不存在")
    return {"ok": True}
