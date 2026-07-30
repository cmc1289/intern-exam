from fastapi import APIRouter, HTTPException, Query

from app.services import record_service


router = APIRouter()


@router.get("/records")
async def list_records(limit: int = Query(50, ge=1, le=200)):
    return {"records": record_service.list_records(limit)}


@router.get("/records/{record_id}")
async def get_record(record_id: str):
    record = record_service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record
