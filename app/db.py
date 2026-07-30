import sqlite3

from app.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


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
            submitted_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_exam_records_started_at
        ON exam_records(started_at DESC)
        """
    )
    conn.commit()
