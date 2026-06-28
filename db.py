"""
Base de datos SQLite local para historial de impresiones del agente.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "history.db"
_lock   = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _lock:
        conn = _conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS print_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                job_code     TEXT    NOT NULL,
                ticket_type  TEXT    NOT NULL,
                status       TEXT    NOT NULL,
                ticket_num   TEXT,
                doc_type     TEXT,
                company      TEXT,
                total        TEXT,
                error_msg    TEXT,
                payload_json TEXT,
                printed_at   TEXT    NOT NULL
            )
        """)
        # Migraciones para tablas ya existentes
        for col_sql in [
            "ALTER TABLE print_history ADD COLUMN payload_json TEXT",
            "ALTER TABLE print_history ADD COLUMN print_count INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE print_history ADD COLUMN customer TEXT",
        ]:
            try:
                conn.execute(col_sql)
            except Exception:
                pass
        conn.commit()
        conn.close()


def log_job(*, job_code: str, ticket_type: str, status: str,
            payload: dict | None = None, error: str | None = None) -> None:
    p          = payload or {}
    ticket_num = p.get("ticket_number") or p.get("sale_code", "")
    doc_type   = p.get("document_type", "")
    company    = (p.get("company") or {}).get("name", "")
    customer   = p.get("customer", "")
    total      = str(p.get("total", ""))
    printed_at = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(p, ensure_ascii=False) if p is not None else None

    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO print_history
               (job_code, ticket_type, status, ticket_num, doc_type, company,
                customer, total, error_msg, payload_json, printed_at, print_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (job_code, ticket_type, status, ticket_num, doc_type, company,
             customer, total, error, payload_json, printed_at),
        )
        conn.commit()
        conn.close()


def increment_print_count(row_id: int) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE print_history SET print_count = print_count + 1 WHERE id = ?", (row_id,)
        )
        conn.commit()
        conn.close()


def get_by_id(row_id: int) -> dict | None:
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM print_history WHERE id = ?", (row_id,)
        ).fetchone()
        conn.close()
    return dict(row) if row else None


def get_history(limit: int = 300, ticket_type: str = "",
                date_from: str = "", date_to: str = "",
                company: str = "") -> list[dict]:
    conditions, params = [], []
    if ticket_type:
        conditions.append("ticket_type = ?")
        params.append(ticket_type)
    if date_from:
        conditions.append("printed_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("printed_at <= ?")
        params.append(date_to + "T23:59:59")
    if company:
        conditions.append("customer LIKE ?")
        params.append(f"%{company}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Agrupa por ticket_num; filas sin ticket_num son grupos individuales.
    # Toma datos del job más reciente; suma print_count de todos los jobs del ticket.
    sql = f"""
        SELECT h.id, h.job_code, h.ticket_num, h.ticket_type, h.printed_at,
               g.total_prints AS print_count,
               h.customer, h.doc_type, h.company, h.total,
               h.status, h.payload_json, h.error_msg
        FROM (
            SELECT
                CASE WHEN ticket_num IS NOT NULL AND ticket_num != ''
                     THEN ticket_num ELSE CAST(id AS TEXT) END AS grp_key,
                MAX(id)          AS max_id,
                SUM(print_count) AS total_prints
            FROM print_history
            {where}
            GROUP BY grp_key
            ORDER BY max_id DESC
            LIMIT ?
        ) g
        JOIN print_history h ON h.id = g.max_id
        ORDER BY h.id DESC
    """
    params.append(limit)

    with _lock:
        conn = _conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    _grp = """
        CASE WHEN ticket_num IS NOT NULL AND ticket_num != ''
             THEN ticket_num ELSE CAST(id AS TEXT) END
    """
    with _lock:
        conn = _conn()
        total     = conn.execute(f"SELECT COUNT(DISTINCT {_grp}) FROM print_history").fetchone()[0]
        completed = conn.execute(
            f"SELECT COUNT(DISTINCT {_grp}) FROM print_history WHERE status='COMPLETED'"
        ).fetchone()[0]
        failed    = conn.execute(
            f"SELECT COUNT(DISTINCT {_grp}) FROM print_history WHERE status='FAILED'"
        ).fetchone()[0]
        conn.close()
    return {"total": total, "completed": completed, "failed": failed}
