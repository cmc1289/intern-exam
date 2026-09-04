import random
import sqlite3

from app.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _gen_code(existing: set[str], length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混淆 I/O/0/1
    while True:
        code = "".join(random.choice(alphabet) for _ in range(length))
        if code not in existing:
            return code


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exam_records (
            id TEXT PRIMARY KEY,
            candidate_name TEXT NOT NULL DEFAULT '',
            specialty TEXT NOT NULL DEFAULT '',
            question_ids_json TEXT NOT NULL,
            answers_json TEXT,
            result_json TEXT,
            final_score REAL,
            passed INTEGER,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            exam_id TEXT,
            mode TEXT NOT NULL DEFAULT 'public',
            visitor_id TEXT,
            candidate_session_id TEXT,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_exam_records_started_at
        ON exam_records(started_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_exam_records_exam_id
        ON exam_records(exam_id)
        """
    )

    # 幂等迁移：exam_records 旧表补列
    cols = _columns(conn, "exam_records")
    for col, ddl in {
        "mode": "TEXT NOT NULL DEFAULT 'public'",
        "visitor_id": "TEXT",
        "candidate_session_id": "TEXT",
        "deleted": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE exam_records ADD COLUMN {col} {ddl}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exams (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            specialties_json TEXT NOT NULL,
            duration INTEGER NOT NULL DEFAULT 30,
            enable_subjective INTEGER NOT NULL DEFAULT 1,
            enable_ai INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            invite_code TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_session (
            id TEXT PRIMARY KEY,
            exam_id TEXT NOT NULL,
            candidate_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_session_unique
        ON candidate_session(exam_id, candidate_name)
        """
    )

    # 幂等迁移：exams 补 invite_code
    ecols = _columns(conn, "exams")
    if "invite_code" not in ecols:
        conn.execute("ALTER TABLE exams ADD COLUMN invite_code TEXT")

    # 存量数据对齐：
    # 1) 已有 exam_id 的记录 -> 考试模式；其余保持 public（游客归 null）
    conn.execute(
        "UPDATE exam_records SET mode='exam' WHERE exam_id IS NOT NULL AND mode='public'"
    )
    # 2) 为已有考试补齐邀请码
    existing = {
        r["invite_code"]
        for r in conn.execute("SELECT invite_code FROM exams WHERE invite_code IS NOT NULL")
    }
    for row in conn.execute("SELECT id FROM exams WHERE invite_code IS NULL").fetchall():
        conn.execute(
            "UPDATE exams SET invite_code = ? WHERE id = ?",
            (_gen_code(existing), row["id"]),
        )
    conn.commit()
