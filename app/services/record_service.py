import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import get_connection

TIMEOUT_MINUTES = 30


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_timed_out_records(conn) -> None:
    """将超过时间限制仍为 'started' 的记录标记为 'timeout'"""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=TIMEOUT_MINUTES)).isoformat()
    conn.execute(
        """
        UPDATE exam_records
        SET status = 'timeout'
        WHERE status = 'started'
          AND started_at <= ?
        """,
        (cutoff,),
    )
    conn.commit()


def create_record(
    specialty: str,
    question_ids: list[int],
    candidate_name: str = "",
    exam_id: str | None = None,
    mode: str = "public",
    visitor_id: str | None = None,
    candidate_session_id: str | None = None,
) -> str:
    record_id = uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO exam_records (
                id,
                candidate_name,
                specialty,
                question_ids_json,
                status,
                started_at,
                exam_id,
                mode,
                visitor_id,
                candidate_session_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                candidate_name,
                specialty,
                json.dumps(question_ids, ensure_ascii=False),
                "started",
                utc_now_iso(),
                exam_id,
                mode,
                visitor_id,
                candidate_session_id,
            ),
        )
        conn.commit()
    return record_id


def finish_record(
    record_id: str,
    answers: list[dict[str, Any]],
    result: dict[str, Any],
) -> bool:
    submitted_at = utc_now_iso()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE exam_records
            SET answers_json = ?,
                result_json = ?,
                final_score = ?,
                passed = ?,
                status = ?,
                submitted_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(answers, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                result.get("final_score"),
                1 if result.get("passed") else 0,
                "submitted",
                submitted_at,
                record_id,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_records(
    visitor_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """仅返回游客自己的、未删除的『自测(public)』记录。

    正式考试(exam)记录不出现在公共历史，只归属后台考试。
    visitor_id 为空时返回空列表（不再向所有访客公开他人记录）。
    """
    limit = max(1, min(limit, 200))
    if not visitor_id:
        return []
    with get_connection() as conn:
        _mark_timed_out_records(conn)
        rows = conn.execute(
            """
            SELECT id,
                   candidate_name,
                   specialty,
                   final_score,
                   passed,
                   status,
                   started_at,
                   submitted_at,
                   exam_id,
                   mode,
                   visitor_id
            FROM exam_records
            WHERE deleted = 0
              AND mode = 'public'
              AND visitor_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (visitor_id, limit),
        ).fetchall()

    return [record_summary_from_row(row) for row in rows]


def get_own_record(
    record_id: str,
    visitor_id: str | None,
) -> dict[str, Any] | None:
    """按访客归属取记录（自测模式隔离校验用）。"""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM exam_records
            WHERE id = ? AND deleted = 0
              AND mode = 'public'
              AND (? IS NULL OR visitor_id = ?)
            """,
            (record_id, visitor_id, visitor_id),
        ).fetchone()
    if row is None:
        return None
    return record_detail_from_row(row)


def find_existing_exam_attempt(
    exam_id: str,
    candidate_name: str,
) -> dict[str, Any] | None:
    """同一候选人同一场考试已存在的记录（单次作答守卫）。"""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, status FROM exam_records
            WHERE exam_id = ? AND candidate_name = ? AND deleted = 0
            ORDER BY started_at DESC LIMIT 1
            """,
            (exam_id, candidate_name),
        ).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "status": row["status"]}


def get_record(record_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        _mark_timed_out_records(conn)
        row = conn.execute(
            """
            SELECT *
            FROM exam_records
            WHERE id = ? AND deleted = 0
            """,
            (record_id,),
        ).fetchone()

    if row is None:
        return None
    return record_detail_from_row(row)


def record_summary_from_row(row) -> dict[str, Any]:
    summary = {
        "id": row["id"],
        "candidate_name": row["candidate_name"],
        "specialty": row["specialty"],
        "final_score": row["final_score"],
        "passed": bool(row["passed"]) if row["passed"] is not None else None,
        "status": row["status"],
        "started_at": row["started_at"],
        "submitted_at": row["submitted_at"],
    }
    try:
        summary["exam_id"] = row["exam_id"]
    except (KeyError, IndexError):
        pass
    return summary


def record_detail_from_row(row) -> dict[str, Any]:
    detail = record_summary_from_row(row)
    detail.update({
        "question_ids": loads_json(row["question_ids_json"], []),
        "answers": loads_json(row["answers_json"], []),
        "result": loads_json(row["result_json"], None),
    })
    return detail


def soft_delete_record(
    record_id: str,
    visitor_id: str | None = None,
    admin: bool = False,
) -> tuple[bool, str]:
    """软删除记录。

    - 普通游客：仅能删除自己名下的 public 自测记录
    - 管理员（admin=True）：可清理任意记录（含考试记录异常数据）
    考试记录对游客永远不可删。
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT mode, visitor_id, exam_id FROM exam_records WHERE id = ? AND deleted = 0
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            return False, "记录不存在"
        if not admin and (row["exam_id"] or row["mode"] == "exam"):
            return False, "该记录属于后台考试，请勿删除"
        # 非管理员必须携带自己的 visitor_id 且完全匹配
        if not admin:
            if not visitor_id or row["visitor_id"] != visitor_id:
                return False, "只能删除自己的记录"
        conn.execute(
            "UPDATE exam_records SET deleted = 1 WHERE id = ?", (record_id,)
        )
        conn.commit()
        return True, "ok"


def save_progress(record_id: str, answers: list[dict[str, Any]]) -> bool:
    """保存答题进度（不提交，不改变状态）"""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE exam_records SET answers_json = ? WHERE id = ? AND status = 'started'",
            (json.dumps(answers, ensure_ascii=False), record_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def loads_json(value: str | None, default):
    if not value:
        return default
    return json.loads(value)
