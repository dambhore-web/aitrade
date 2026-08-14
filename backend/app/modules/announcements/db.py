"""
Reads/writes Trading_bot/announcements_seen.db directly -- the same file
announcement_listener_v2.py already owns. The listener background thread
(listener.py) is the only writer to `signals` besides these enrichment
columns; API reads below open their own short-lived connection per call
(cheap, avoids sharing a connection across threads).
"""
import sqlite3
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

ANNOUNCEMENT_COLUMNS = [
    "id", "captured_utc", "announcement_time_ist", "stock_name", "bse_code",
    "nse_symbol", "exchange", "title", "message", "link", "pdf_url", "pdf_path",
    "sentiment_label", "sentiment_score", "category", "is_bonus_buyback",
    "financial_result_flag",
]


def db_path() -> Path:
    return get_settings().legacy_root / "announcements_seen.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, col_type: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table});").fetchall()]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
        return True
    return False


def ensure_enrichment_columns(conn: sqlite3.Connection) -> None:
    """Add the Module A enrichment columns (docs/requirements.md §6 data
    contract) to the existing `signals` table if missing. Idempotent --
    matches the self-migrating pattern already used in new_trade_tool/db.py.
    """
    for col, col_type in [
        ("sentiment_label", "TEXT"),
        ("sentiment_score", "REAL"),
        ("category", "TEXT"),
        ("is_bonus_buyback", "INTEGER"),
        ("financial_result_flag", "INTEGER"),
    ]:
        _add_column_if_missing(conn, "signals", col, col_type)
    conn.commit()


def fetch_announcements(
    limit: int = 50,
    offset: int = 0,
    exchange: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list[dict], int]:
    conn = get_conn()
    try:
        where, params = [], []
        if exchange and exchange != "All":
            where.append("exchange = ?")
            params.append(exchange)
        if search:
            where.append("(stock_name LIKE ? OR title LIKE ? OR message LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(f"SELECT COUNT(*) FROM signals {where_sql}", params).fetchone()[0]
        cols = ", ".join(ANNOUNCEMENT_COLUMNS)
        rows = conn.execute(
            f"SELECT {cols} FROM signals {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()


def fetch_announcement(ann_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        cols = ", ".join(ANNOUNCEMENT_COLUMNS)
        row = conn.execute(f"SELECT {cols} FROM signals WHERE id = ?", (ann_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_financial_result_flag(ann_id: int, flag: Optional[int]) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE signals SET financial_result_flag = ? WHERE id = ?", (flag, ann_id))
        conn.commit()
    finally:
        conn.close()
