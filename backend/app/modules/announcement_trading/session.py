"""
Reads the shared multi-account Kite session file (Trading_bot/kite_instances.pkl
-- produced by Kite_API_31.py's "Load User Data" button, which drives a real
Selenium login per account using credentials from Zerodha_Orders.xlsx) so
BOTH announcement-driven and equity trading can place orders through the
same authenticated sessions instead of each re-authenticating separately.

SECURITY: the pickled per-user dict contains plaintext password/API
SECRET/TOTP_KEY (confirmed by inspection -- see docs/requirements.md open
questions). get_session_status() below returns only an explicit safe-field
allowlist; get_kite_instances() (the raw list, for execution.py only) must
never be serialized back out over the API.
"""
import pickle
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

SAFE_USER_FIELDS = ["Zerodha ID", "MULTIPLIER", "ENABLED", "LOGIN STATUS", "EQUITY MARGIN", "PNL"]


def pkl_path() -> Path:
    return get_settings().legacy_root / "kite_instances.pkl"


def get_kite_instances() -> list[tuple]:
    """Returns [(KiteConnect, user_dict), ...] for execution.py's internal
    use only. Raises FileNotFoundError if no session has been established."""
    path = pkl_path()
    if not path.exists():
        raise FileNotFoundError(
            "No Kite session found (kite_instances.pkl missing). Run Kite_API_31.py's "
            "\"Load User Data\" to authenticate before placing orders."
        )
    with open(path, "rb") as f:
        return pickle.load(f)


def get_session_status() -> dict:
    path = pkl_path()
    if not path.exists():
        return {"connected": False, "account_count": 0, "accounts": [], "session_file_mtime": None}
    try:
        instances = get_kite_instances()
    except Exception:
        return {"connected": False, "account_count": 0, "accounts": [], "session_file_mtime": None}

    accounts = []
    for _kite, user in instances:
        accounts.append({k: user.get(k) for k in SAFE_USER_FIELDS if k in user})

    return {
        "connected": len(instances) > 0,
        "account_count": len(instances),
        "accounts": accounts,
        "session_file_mtime": path.stat().st_mtime,
    }
