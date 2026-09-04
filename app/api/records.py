from fastapi import APIRouter, Depends, HTTPException, Query, Header

from app.config import ADMIN_TOKEN
from app.services import record_service


router = APIRouter()


async def verify_admin(x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return True


@router.get("/records")
async def list_records(
    visitor_id: str = Query(default="", max_length=128),
    limit: int = Query(50, ge=1, le=200),
):
    """历史记录仅返回游客自己的自测记录（visitor_id 隔离）。"""
    records = record_service.list_records(visitor_id or None, limit)
    return {"records": records}


@router.get("/records/{record_id}")
async def get_record(record_id: str):
    record = record_service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: str,
    x_admin_token: str = Header(default=""),
    visitor_id: str = Query(default="", max_length=128),
):
    """删除（软删除）记录。

    - 携带管理员令牌：可清理任意记录（考试异常数据处理）
    - 普通游客：只能删除自己名下（visitor_id）的公开自测记录
    - 考试记录对游客永远不可删
    """
    is_admin = bool(ADMIN_TOKEN) and x_admin_token == ADMIN_TOKEN
    ok, reason = record_service.soft_delete_record(
        record_id,
        visitor_id=visitor_id or None,
        admin=is_admin,
    )
    if not ok:
        detail = reason
        status = 403 if "删除" in reason or "只能" in reason else 404
        raise HTTPException(status_code=status, detail=detail)
    return {"ok": True}
