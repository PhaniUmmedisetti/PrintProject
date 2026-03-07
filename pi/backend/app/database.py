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
                failure_code      TEXT,
                retryable         INTEGER,
                terminal_event_type TEXT,
                terminal_event_payload TEXT,
                terminal_event_synced INTEGER NOT NULL DEFAULT 1,
                terminal_event_last_error TEXT,
                created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await _ensure_column(db, "print_jobs", "file_token", "TEXT")
        await _ensure_column(db, "print_jobs", "printer_name", "TEXT")
        await _ensure_column(db, "print_jobs", "job_summary", "TEXT")
        await _ensure_column(db, "print_jobs", "cups_job_id", "TEXT")
        await _ensure_column(db, "print_jobs", "failure_code", "TEXT")
        await _ensure_column(db, "print_jobs", "retryable", "INTEGER")
        await _ensure_column(db, "print_jobs", "terminal_event_type", "TEXT")
        await _ensure_column(db, "print_jobs", "terminal_event_payload", "TEXT")
        await _ensure_column(db, "print_jobs", "terminal_event_synced", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "print_jobs", "terminal_event_last_error", "TEXT")
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
    failure_code: str | None = None,
    retryable: bool | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE print_jobs
            SET status     = ?,
                error_msg  = COALESCE(?, error_msg),
                file_path  = COALESCE(?, file_path),
                cups_job_id = COALESCE(?, cups_job_id),
                failure_code = COALESCE(?, failure_code),
                retryable = COALESCE(?, retryable),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, error_msg, file_path, cups_job_id, failure_code, _bool_to_int(retryable), job_id),
        )
        await db.commit()


async def set_terminal_event(
    job_id: str,
    event_type: str,
    payload: dict,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE print_jobs
            SET terminal_event_type = ?,
                terminal_event_payload = ?,
                terminal_event_synced = 0,
                terminal_event_last_error = NULL,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (event_type, json.dumps(payload), job_id),
        )
        await db.commit()


async def mark_terminal_event_synced(job_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE print_jobs
            SET terminal_event_synced = 1,
                terminal_event_last_error = NULL,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (job_id,),
        )
        await db.commit()


async def set_terminal_event_error(job_id: str, error: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE print_jobs
            SET terminal_event_last_error = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (error, job_id),
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
        if result.get("terminal_event_payload"):
            try:
                result["terminal_event_payload"] = json.loads(result["terminal_event_payload"])
            except json.JSONDecodeError:
                result["terminal_event_payload"] = None
        if result.get("retryable") is not None:
            result["retryable"] = bool(result["retryable"])
        if result.get("terminal_event_synced") is not None:
            result["terminal_event_synced"] = bool(result["terminal_event_synced"])

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


async def get_unsynced_terminal_events() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM print_jobs
            WHERE terminal_event_type IS NOT NULL
              AND terminal_event_synced = 0
            ORDER BY updated_at ASC
            """
        )
        rows = await cursor.fetchall()
        jobs: list[dict] = []
        for row in rows:
            result = dict(row)
            if result.get("terminal_event_payload"):
                try:
                    result["terminal_event_payload"] = json.loads(result["terminal_event_payload"])
                except json.JSONDecodeError:
                    result["terminal_event_payload"] = None
            if result.get("retryable") is not None:
                result["retryable"] = bool(result["retryable"])
            if result.get("terminal_event_synced") is not None:
                result["terminal_event_synced"] = bool(result["terminal_event_synced"])
            jobs.append(result)
        return jobs


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0
