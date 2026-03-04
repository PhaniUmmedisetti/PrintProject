import aiosqlite
import json
from pathlib import Path

DB_PATH = str(Path(__file__).parent.parent / "jobs.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS print_jobs (
                id                TEXT PRIMARY KEY,
                code              TEXT NOT NULL DEFAULT '',
                status            TEXT NOT NULL,
                file_path         TEXT,
                file_token        TEXT,
                printer_name      TEXT,
                job_summary       TEXT,
                cups_job_id       TEXT,
                error_msg         TEXT,
                created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await _ensure_column(db, "print_jobs", "file_token", "TEXT")
        await _ensure_column(db, "print_jobs", "printer_name", "TEXT")
        await _ensure_column(db, "print_jobs", "job_summary", "TEXT")
        await _ensure_column(db, "print_jobs", "cups_job_id", "TEXT")
        await db.commit()


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, column_type: str) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    existing_columns = {row[1] for row in rows}
    if column not in existing_columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


async def create_job(
    job_id: str,
    file_token: str,
    printer_name: str,
    job_summary: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO print_jobs (id, code, status, file_token, printer_name, job_summary)
            VALUES (?, '', 'DOWNLOADING', ?, ?, ?)
            """,
            (job_id, file_token, printer_name, job_summary),
        )
        await db.commit()


async def update_job(
    job_id: str,
    status: str,
    *,
    error_msg: str | None = None,
    file_path: str | None = None,
    cups_job_id: str | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE print_jobs
            SET status     = ?,
                error_msg  = COALESCE(?, error_msg),
                file_path  = COALESCE(?, file_path),
                cups_job_id = COALESCE(?, cups_job_id),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, error_msg, file_path, cups_job_id, job_id),
        )
        await db.commit()


async def get_job(job_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            return None

        result = dict(row)
        if result.get("job_summary"):
            try:
                result["job_summary"] = json.loads(result["job_summary"])
            except json.JSONDecodeError:
                result["job_summary"] = None

        return result


async def get_in_flight_jobs() -> list[dict]:
    """Return jobs that were mid-process when the Pi last restarted."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM print_jobs
            WHERE status IN ('DOWNLOADING', 'CONVERTING', 'READY', 'PRINTING')
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
