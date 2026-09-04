"""考试（Exam）管理服务：创建考试、列表、Dashboard、候选人查询、Session。"""
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db import get_connection
from app.models import CreateExamRequest


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gen_code(existing: set[str], length: int = 6) -> str:
    while True:
        code = "".join(random.choice(_CODE_ALPHABET) for _ in range(length))
        if code not in existing:
            return code


def create_exam(req: CreateExamRequest) -> dict[str, Any]:
    exam_id = uuid.uuid4().hex
    with get_connection() as conn:
        used = {
            r["invite_code"]
            for r in conn.execute("SELECT invite_code FROM exams WHERE invite_code IS NOT NULL")
        }
        code = _gen_code(used)
        conn.execute(
            """
            INSERT INTO exams (
                id, title, specialties_json, duration,
                enable_subjective, enable_ai, status, created_at, invite_code
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                exam_id,
                req.title,
                json.dumps(req.specialties, ensure_ascii=False),
                req.duration,
                1 if req.enable_subjective else 0,
                1 if req.enable_ai else 0,
                utc_now_iso(),
                code,
            ),
        )
        conn.commit()
    return {
        "id": exam_id,
        "title": req.title,
        "specialties": req.specialties,
        "duration": req.duration,
        "enable_subjective": req.enable_subjective,
        "enable_ai": req.enable_ai,
        "status": "active",
        "created_at": utc_now_iso(),
        "invite_code": code,
    }


def _row_to_exam(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "specialties": json.loads(row["specialties_json"]),
        "duration": row["duration"],
        "enable_subjective": bool(row["enable_subjective"]),
        "enable_ai": bool(row["enable_ai"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "invite_code": row["invite_code"],
    }


def get_exam(exam_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM exams WHERE id = ?", (exam_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_exam(row)


def get_exam_by_code(code: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM exams WHERE invite_code = ? COLLATE NOCASE",
            (code.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _row_to_exam(row)


def _find_or_create_session(conn, exam_id: str, name: str) -> str:
    """按 (考试, 姓名) 查找或创建 CandidateSession，返回 session id。"""
    row = conn.execute(
        "SELECT id FROM candidate_session WHERE exam_id = ? AND candidate_name = ?",
        (exam_id, name),
    ).fetchone()
    if row:
        return row["id"]
    sid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO candidate_session (id, exam_id, candidate_name, created_at) "
        "VALUES (?, ?, ?, ?)",
        (sid, exam_id, name, utc_now_iso()),
    )
    conn.commit()
    return sid


def join_exam(code: str, candidate_name: str) -> dict[str, Any]:
    """候选人凭邀请码 + 姓名加入考试。

    单次作答：同 (考试, 姓名) 仅一次。
    返回考试公开信息、session 及既有记录状态：
      - submitted：已交卷，只能查看本次报告
      - started：答题中途，可继续
      - 否则 ready：可开始作答
    """
    exam = get_exam_by_code(code)
    if exam is None:
        raise ValueError("邀请码无效")
    if exam["status"] != "active":
        raise ValueError("该考试已关闭")

    with get_connection() as conn:
        sid = _find_or_create_session(conn, exam["id"], candidate_name)
        row = conn.execute(
            """
            SELECT id, status FROM exam_records
            WHERE candidate_session_id = ?
            ORDER BY started_at DESC LIMIT 1
            """,
            (sid,),
        ).fetchone()

    record_id, record_status = (row["id"], row["status"]) if row else (None, None)
    if record_status == "submitted":
        status = "submitted"
    elif record_status == "started":
        status = "started"
    else:
        status = "ready"

    return {
        "exam": exam,
        "candidate_session_id": sid,
        "status": status,
        "record_id": record_id,
    }


def list_exams() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.*, (
                SELECT COUNT(*) FROM exam_records r
                WHERE r.exam_id = e.id AND r.status IN ('submitted', 'started', 'timeout')
                  AND r.deleted = 0
            ) AS candidate_count,
            (
                SELECT COUNT(*) FROM exam_records r
                WHERE r.exam_id = e.id AND r.status = 'submitted' AND r.deleted = 0
            ) AS submitted_count
            FROM exams e
            ORDER BY e.created_at DESC
            """
        ).fetchall()
    out = []
    for row in rows:
        exam = _row_to_exam(row)
        exam["candidate_count"] = row["candidate_count"]
        exam["submitted_count"] = row["submitted_count"]
        out.append(exam)
    return out


def exam_candidates(exam_id: str) -> list[dict[str, Any]]:
    from app.services.record_service import record_summary_from_row

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, candidate_name, specialty, final_score, passed,
                   status, started_at, submitted_at
            FROM exam_records
            WHERE exam_id = ? AND deleted = 0
            ORDER BY started_at DESC
            """,
            (exam_id,),
        ).fetchall()
    return [record_summary_from_row(r) for r in rows]


def dashboard() -> dict[str, Any]:
    with get_connection() as conn:
        exam_total = conn.execute("SELECT COUNT(*) AS c FROM exams").fetchone()["c"]
        cand_total = conn.execute(
            "SELECT COUNT(*) AS c FROM exam_records"
        ).fetchone()["c"]
        submitted = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(AVG(final_score), 0) AS avg "
            "FROM exam_records WHERE status = 'submitted'"
        ).fetchone()
        recent_rows = conn.execute(
            "SELECT id, title, created_at FROM exams ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        recent = [dict(r) for r in recent_rows]
    return {
        "total_exams": exam_total,
        "total_candidates": cand_total,
        "submitted_candidates": submitted["c"],
        "avg_score": round(submitted["avg"], 1),
        "recent_exams": recent,
    }


def delete_exam(exam_id: str) -> bool:
    """删除考试及其全部候选人记录。"""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
        conn.execute("DELETE FROM exam_records WHERE exam_id = ?", (exam_id,))
        conn.commit()
        return cursor.rowcount > 0


def public_exam(exam_id: str) -> dict[str, Any] | None:
    """考试入口页所需的公开信息（不含候选人数据）。"""
    exam = get_exam(exam_id)
    if exam is None:
        return None
    return {
        "id": exam["id"],
        "title": exam["title"],
        "specialties": exam["specialties"],
        "duration": exam["duration"],
        "enable_subjective": exam["enable_subjective"],
        "enable_ai": exam["enable_ai"],
        "status": exam["status"],
    }
