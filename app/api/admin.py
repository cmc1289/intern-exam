from fastapi import APIRouter, Depends, HTTPException

from app.config import ADMIN_PASSWORD, ADMIN_TOKEN, ADMIN_USERNAME
from app.models import BankExpandRequest, CreateExamRequest, LoginRequest
from app.services import exam_service, question_service
from app.services.bank_expansion_service import get_job, start_expand_job

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


# ---------------- 题库健康 / 智能扩充 ----------------
@router.get("/bank/health")
async def bank_health(_: bool = Depends(verify_admin)):
    return question_service.bank_health()


@router.get("/bank/catalog")
async def bank_catalog(_: bool = Depends(verify_admin)):
    return {"modules": question_service.bank_catalog()}


@router.post("/bank/expand")
async def bank_expand(req: BankExpandRequest, _: bool = Depends(verify_admin)):
    """AI 智能扩充（异步）：候选收集 → 筛选 → 知识点聚合 → 重新设计 → 自动入库。

    dry_run=true 仅预览（不写库）。自动入库前会自动 .bak 备份题库。
    返回 job_id，用 GET /api/admin/bank/expand/{job_id} 轮询进度。
    """
    if not req.module.strip():
        raise HTTPException(status_code=400, detail="请选择专业方向")
    mode = req.mode if req.mode in ("brainstorm", "url") else "brainstorm"
    topics = [t.strip() for t in req.topics if t.strip()]
    urls = [u.strip() for u in req.urls if u.strip()]
    if mode == "brainstorm" and not topics:
        raise HTTPException(status_code=400, detail="脑暴模式需要至少填写一个话题")
    if mode == "url" and not urls:
        raise HTTPException(status_code=400, detail="URL 模式需要至少填写一个参考 URL")
    return await start_expand_job(
        req.module.strip(),
        topics,
        urls,
        dry_run=req.dry_run,
        instruction=(req.instruction or "").strip(),
        mode=mode,
    )


@router.get("/bank/expand/{job_id}")
async def bank_expand_status(job_id: str, _: bool = Depends(verify_admin)):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job
