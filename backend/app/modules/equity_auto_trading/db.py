"""
Equity Auto Trading's own database -- aitrade/data/equity_auto_trading.db.
Holds two settings: `amount`, the rupee amount-per-trade that
new_trade_tool/scanner.py's process_symbol_candle_close() converts into a
share quantity at order time (quantity = max(1, int(amount //
current_price))); and `strategy`, which of new_trade_tool's two strategy
modules the scanner runs -- "wisestock" (VWAP-crossover, strategies.py) or
"breakout" (Opening-Range-Breakout, strategy_breakout.py, added
2026-08-20). Both replace what used to be restart-only config.py
constants -- read fresh by scanner_loop.py on every signal, so editing
either here takes effect on the very next signal, no restart needed.

Self-contained under aitrade/, same single-row settings model as
announcement_trading/db.py (there's exactly one active configuration, no
need for a key/value table). A separate connection from scanner_loop.py's
own -- this file has exactly one writer at a time in practice (whichever
of router.py/scanner_loop.py touches it), and SQLite's WAL mode (set below)
already handles that safely, the same pattern used throughout this
codebase for connections to a shared file from different modules/threads.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[4] / "data" / "equity_auto_trading.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  amount INTEGER NOT NULL DEFAULT 10000,
  strategy TEXT NOT NULL DEFAULT 'wisestock',
  updated_utc TEXT
);
"""

# Columns added after the table's initial release -- ALTER TABLE ADD
# COLUMN for anyone with an existing equity_auto_trading.db predating
# them, same migration pattern as announcement_trading/db.py.
_SETTINGS_MIGRATIONS = [
    "ALTER TABLE settings ADD COLUMN strategy TEXT NOT NULL DEFAULT 'wisestock'",
]


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    conn.execute(CREATE_SETTINGS)
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(settings)").fetchall()}
    for stmt in _SETTINGS_MIGRATIONS:
        col_name = stmt.split("ADD COLUMN")[1].strip().split(" ")[0]
        if col_name not in existing_cols:
            conn.execute(stmt)
    conn.commit()


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
