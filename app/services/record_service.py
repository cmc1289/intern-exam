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
                started_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                candidate_name,
                specialty,
                json.dumps(question_ids, ensure_ascii=False),
                "started",
                utc_now_iso(),
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


def list_records(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
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
                   submitted_at
            FROM exam_records
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [record_summary_from_row(row) for row in rows]


def get_record(record_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        _mark_timed_out_records(conn)
        row = conn.execute(
            """
            SELECT *
            FROM exam_records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()

    if row is None:
        return None
    return record_detail_from_row(row)


def record_summary_from_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "candidate_name": row["candidate_name"],
        "specialty": row["specialty"],
        "final_score": row["final_score"],
        "passed": bool(row["passed"]) if row["passed"] is not None else None,
        "status": row["status"],
        "started_at": row["started_at"],
        "submitted_at": row["submitted_at"],
    }


def record_detail_from_row(row) -> dict[str, Any]:
    detail = record_summary_from_row(row)
    detail.update({
        "question_ids": loads_json(row["question_ids_json"], []),
        "answers": loads_json(row["answers_json"], []),
        "result": loads_json(row["result_json"], None),
    })
    return detail


def delete_record(record_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM exam_records WHERE id = ?", (record_id,))
        conn.commit()
        return cursor.rowcount > 0


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
