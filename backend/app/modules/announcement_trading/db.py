"""
Module B's own database -- aitrade/data/announcement_trading.db. Deliberately
NOT reusing any of Kite_API_31.py's pickle files (global.pickle,
inputs/global.pickle) for settings storage: a real SQLite table is
inspectable/backupable in a way a PySimpleGUI pickle blob isn't, and this
keeps Module B fully self-contained under aitrade/.

Settings are stored as a single row (id=1) rather than a key/value table --
there is exactly one active configuration, matching the legacy GUI's own
single global settings model.
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parents[4] / "data" / "announcement_trading.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  variety TEXT NOT NULL DEFAULT 'regular',
  order_type TEXT NOT NULL DEFAULT 'MARKET',
  product_type TEXT NOT NULL DEFAULT 'MTF',
  hours_back REAL NOT NULL DEFAULT 0,
  amount INTEGER NOT NULL DEFAULT 0,
  gtt_stop_pct REAL NOT NULL DEFAULT -0.60,
  gtt_target_pct REAL NOT NULL DEFAULT 20,
  market_protection_pct REAL NOT NULL DEFAULT 3.0,
  nse_app_id TEXT NOT NULL DEFAULT '',
  nse_it TEXT NOT NULL DEFAULT '',
  telegram_enabled INTEGER NOT NULL DEFAULT 0,
  updated_utc TEXT
);
"""

CREATE_ACTIVITY_LOG = """
CREATE TABLE IF NOT EXISTS activity_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  symbol TEXT,
  category TEXT,
  sentiment TEXT,
  text_snippet TEXT,
  skipped INTEGER NOT NULL,
  skip_reason TEXT,
  order_placed INTEGER NOT NULL DEFAULT 0,
  quantity INTEGER,
  current_price REAL,
  trade_entry_id INTEGER,
  source TEXT,
  an_dt TEXT,
  attachment_url TEXT
);
"""

# Columns added after the table's initial release -- ALTER TABLE ADD COLUMN
# for anyone with an existing activity_log.db predating them. CREATE TABLE
# IF NOT EXISTS above only helps on a fresh DB; existing rows/tables need
# this to pick up the new columns without losing history.
_ACTIVITY_LOG_MIGRATIONS = [
    "ALTER TABLE activity_log ADD COLUMN source TEXT",
    "ALTER TABLE activity_log ADD COLUMN an_dt TEXT",
    "ALTER TABLE activity_log ADD COLUMN attachment_url TEXT",
]

# stop_loss_price/target_price are the ABSOLUTE prices the entry's GTT bracket was
# actually placed at -- distinct from the existing stop_loss_pct/target_pct columns,
# which are percentages used only by the manual draft-entry flow (router.py's
# POST /entries). Added 2026-08-17 for exit_management.py, which needs the real
# bracket prices back to re-place a GTT that triggered one leg while still holding
# the position.
_TRADE_ENTRIES_MIGRATIONS = [
    "ALTER TABLE trade_entries ADD COLUMN stop_loss_price REAL",
    "ALTER TABLE trade_entries ADD COLUMN target_price REAL",
]

# -1 (Zerodha/exchange's own automatic protection band) was the original's
# hardcoded value -- confirmed correct per kiteconnect's own place_order()
# docstring, but real live behavior traced 2026-08-19 (ITI: order submitted
# in <1s, sat unfilled for 9 minutes waiting for price to re-enter the
# exchange's band after a post-news spike). User explicitly chose a wider,
# user-configurable percentage (3% default) over the exchange default, to
# trade a little more price risk for materially faster fills.
_SETTINGS_MIGRATIONS = [
    "ALTER TABLE settings ADD COLUMN market_protection_pct REAL NOT NULL DEFAULT 3.0",
]

CREATE_TRADE_ENTRIES = """
CREATE TABLE IF NOT EXISTS trade_entries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  announcement_id INTEGER,
  announcement_snapshot TEXT,
  symbol TEXT NOT NULL,
  exchange TEXT NOT NULL DEFAULT 'NSE',
  transaction_type TEXT NOT NULL DEFAULT 'BUY',
  amount INTEGER,
  quantity INTEGER,
  stop_loss_pct REAL,
  target_pct REAL,
  order_type TEXT,
  product_type TEXT,
  variety TEXT,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  order_result TEXT,
  created_utc TEXT NOT NULL,
  placed_utc TEXT
);
"""


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    conn.execute(CREATE_SETTINGS)
    conn.execute(CREATE_TRADE_ENTRIES)
    conn.execute(CREATE_ACTIVITY_LOG)
    conn.execute(
        "INSERT OR IGNORE INTO settings (id) VALUES (1)"
    )
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(activity_log)").fetchall()}
    for stmt in _ACTIVITY_LOG_MIGRATIONS:
        col_name = stmt.split("ADD COLUMN")[1].strip().split(" ")[0]
        if col_name not in existing_cols:
            conn.execute(stmt)

    existing_entry_cols = {row[1] for row in conn.execute("PRAGMA table_info(trade_entries)").fetchall()}
    for stmt in _TRADE_ENTRIES_MIGRATIONS:
        col_name = stmt.split("ADD COLUMN")[1].strip().split(" ")[0]
        if col_name not in existing_entry_cols:
            conn.execute(stmt)

    existing_settings_cols = {row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()}
    for stmt in _SETTINGS_MIGRATIONS:
        col_name = stmt.split("ADD COLUMN")[1].strip().split(" ")[0]
        if col_name not in existing_settings_cols:
            conn.execute(stmt)

    conn.commit()


def log_activity(conn: sqlite3.Connection, fields: dict) -> dict:
    import datetime as dt

    fields = {**fields, "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO activity_log ({cols}) VALUES ({placeholders})", list(fields.values()))
    conn.commit()
    row = conn.execute("SELECT * FROM activity_log WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_activity(conn: sqlite3.Connection, limit: int = 100, order_placed: Optional[bool] = None) -> list[dict]:
    """order_placed=True finds real placed orders regardless of how far
    back they are -- added 2026-08-17 after "Orders placed" in the UI
    showed nothing even though orders really had been placed that day.
    Root cause: this always applied LIMIT to the whole table before any
    filtering, so on a busy day (skipped/routine rows vastly outnumber
    real orders -- confirmed live: 2 placed among 912 total rows) the
    handful of real orders scroll out of "the most recent N rows"
    entirely, long before N rows have even been scanned since the last
    one. Filtering first, then limiting, fixes that."""
    if order_placed is None:
        rows = conn.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM activity_log WHERE order_placed = ? ORDER BY id DESC LIMIT ?",
            (int(order_placed), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_settings(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return dict(row)


def update_settings(conn: sqlite3.Connection, fields: dict) -> dict:
    import datetime as dt

    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE settings SET {cols}, updated_utc = ? WHERE id = 1",
        (*fields.values(), dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    conn.commit()
    return get_settings(conn)


def create_trade_entry(conn: sqlite3.Connection, fields: dict) -> dict:
    import datetime as dt

    fields = {**fields, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO trade_entries ({cols}) VALUES ({placeholders})", list(fields.values()))
    conn.commit()
    return get_trade_entry(conn, cur.lastrowid)


def get_trade_entry(conn: sqlite3.Connection, entry_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM trade_entries WHERE id = ?", (entry_id,)).fetchone()
    return dict(row) if row else None


def list_trade_entries(conn: sqlite3.Connection, announcement_id: Optional[int] = None) -> list[dict]:
    if announcement_id is not None:
        rows = conn.execute(
            "SELECT * FROM trade_entries WHERE announcement_id = ? ORDER BY id DESC", (announcement_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM trade_entries ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def mark_entry_placed(conn: sqlite3.Connection, entry_id: int, order_result: dict, status: str) -> dict:
    import datetime as dt

    conn.execute(
        "UPDATE trade_entries SET status = ?, order_result = ?, placed_utc = ? WHERE id = ?",
        (status, json.dumps(order_result, default=str), dt.datetime.now(dt.timezone.utc).isoformat(), entry_id),
    )
    conn.commit()
    return get_trade_entry(conn, entry_id)
