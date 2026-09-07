"""评估报告导出（PDF）——管理员专属，纯展示层。

- 复用已归档的 exam_records.result_json，不重算分数、不修改评分逻辑、不调用 AI。
- 鉴权复用 X-Admin-Token（候选人当前无 PDF 下载权限）。
"""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.records import verify_admin
from app.services import exam_service, record_service
from app.services.pdf_service import build_report_pdf, make_pdf_filename
from app.services.question_service import get_specialties


router = APIRouter()


def _make_report_id() -> str:
    """ASSESS-YYYYMMDD-序号（序号取当日已提交记录数+1）。"""
    day = datetime.now().strftime("%Y%m%d")
    seq = record_service.next_report_no()
    return f"ASSESS-{day}-{seq:03d}"


def _resolve_record(record_or_session: str) -> dict | None:
    """兼容两种标识：优先按 exam_records.id，其次按 candidate_session.id。"""
    record = record_service.get_record(record_or_session)
    if record is not None:
        return record
    return record_service.get_record_by_session(record_or_session)


@router.get("/report/{record_or_session}/pdf")
async def export_report_pdf(
    record_or_session: str,
    _: bool = Depends(verify_admin),
):
    """导出候选人评估报告 PDF（管理员）。"""
    record = _resolve_record(record_or_session)
    if record is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if record["status"] != "submitted" or not record.get("result"):
        raise HTTPException(status_code=400, detail="该记录尚未完成提交，无法导出 PDF")

    exam = None
    if record.get("exam_id"):
        exam = exam_service.get_exam(record["exam_id"])
    specialties_map = get_specialties()
    report_id = _make_report_id()

    try:
        pdf_bytes = build_report_pdf(record, exam, specialties_map, report_id=report_id)
    except Exception as exc:  # pragma: no cover - 防御：库/字体异常给可读错误
        raise HTTPException(status_code=500, detail=f"PDF 生成失败：{exc}")

    filename = make_pdf_filename(record, exam, specialties_map)
    # RFC 5987：中文文件名用 filename* 传输，同时保留 ASCII 兜底
    disposition = f"attachment; filename=\"report.pdf\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
