"""
Session/token generation ("Window 1") -- faithful port of
load_multi_users.py's fetch_request_token()/get_token_for_multiple_users()
and Kite_API_31.py's initialize_kite_instances(), run as a background job
since each account login is a real Selenium-driven browser flow (10-30s+).

SECURITY: reads Zerodha_Orders.xlsx directly -- plaintext password/API
secret/TOTP seed per account (confirmed by inspecting kite_instances.pkl's
structure, never by printing the Excel's actual values). Only ever used
in-process to drive the login; never returned via any API response. The job
status exposed to the frontend carries per-account progress by Zerodha ID
only.

This is a real login to the user's actual brokerage account(s) -- only ever
runs on an explicit POST /announcement-trading/session/generate, never
automatically.
"""
import logging
import pickle
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import pyotp
from kiteconnect import KiteConnect
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import get_settings

logger = logging.getLogger("announcement_trading.session_login")

_lock = threading.Lock()
_job_state: dict = {
    "running": False,
    "accounts": {},  # zerodha_id -> {"status": "pending"|"running"|"success"|"failed", "message": str}
    "error": None,
}


def get_job_status() -> dict:
    with _lock:
        return {
            "running": _job_state["running"],
            "accounts": dict(_job_state["accounts"]),
            "error": _job_state["error"],
        }


def _excel_path() -> Path:
    return get_settings().legacy_root / "inputs" / "Zerodha_Orders.xlsx"


def _geckodriver_path() -> Path:
    return get_settings().legacy_root / "browsers" / "geckodriver.exe"


def _fetch_request_token(username: str, password: str, totp_key: str, api_key: str) -> str:
    """Port of load_multi_users.py's fetch_request_token (api_secret param
    dropped -- unused in the original body too)."""
    import requests

    session = requests.Session()
    resp = session.post(
        "https://kite.zerodha.com/api/login", data={"user_id": username, "password": password}
    )
    request_id = resp.json()["data"]["request_id"]
    twofa_pin = pyotp.TOTP(totp_key).now()
    session.post(
        "https://kite.zerodha.com/api/twofa",
        data={"user_id": username, "request_id": request_id, "twofa_value": twofa_pin, "twofa_type": "totp"},
    )

    kite = KiteConnect(api_key=api_key)
    kite_url = kite.login_url()

    options = Options()
    options.add_argument("--headless")
    service = Service(str(_geckodriver_path()))
    driver = webdriver.Firefox(service=service, options=options)
    try:
        driver.get(kite_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(username)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "password"))).send_keys(password)
        time.sleep(1)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[@type='submit']"))
        ).click()
        time.sleep(1)
        twofa_pin = pyotp.TOTP(totp_key).now()
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(twofa_pin)
        WebDriverWait(driver, 20).until(lambda d: "request_token" in d.current_url)
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(driver.current_url)
        return parse_qs(parsed.query).get("request_token", [None])[0]
    finally:
        driver.quit()


def _run_job() -> None:
    excel_path = _excel_path()
    try:
        df = pd.read_excel(excel_path, sheet_name="Client Data")
    except Exception as e:
        with _lock:
            _job_state["running"] = False
            _job_state["error"] = f"Could not read {excel_path.name}: {e}"
        return

    with _lock:
        _job_state["accounts"] = {
            str(row["Zerodha ID"]): {"status": "pending", "message": ""} for _, row in df.iterrows()
        }

    # Step 1: request tokens (Selenium login per account)
    for index, row in df.iterrows():
        zerodha_id = str(row["Zerodha ID"])
        with _lock:
            _job_state["accounts"][zerodha_id] = {"status": "running", "message": "Logging in..."}
        try:
            request_token = _fetch_request_token(
                row["Zerodha ID"], row["password"], row["TOTP_KEY"], row["API KEY"]
            )
            if not request_token:
                raise RuntimeError("No request_token in redirect URL")
            df.at[index, "REQUEST TOKEN"] = request_token
            with _lock:
                _job_state["accounts"][zerodha_id] = {"status": "running", "message": "Got request token"}
        except Exception as e:
            logger.exception("Login failed for %s", zerodha_id)
            with _lock:
                _job_state["accounts"][zerodha_id] = {"status": "failed", "message": str(e)}

    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
            df.to_excel(writer, sheet_name="Client Data", index=False)
    except Exception:
        logger.exception("Could not save request tokens back to %s", excel_path.name)

    # Step 2: generate_session per account -> build KiteConnect instances
    instances = []
    for _, row in df.iterrows():
        zerodha_id = str(row["Zerodha ID"])
        with _lock:
            if _job_state["accounts"].get(zerodha_id, {}).get("status") == "failed":
                continue
        try:
            kite = KiteConnect(api_key=row["API KEY"])
            data = kite.generate_session(row["REQUEST TOKEN"], api_secret=row["API SECRET"])
            kite.set_access_token(data["access_token"])
            instances.append((kite, row.to_dict()))
            with _lock:
                _job_state["accounts"][zerodha_id] = {"status": "success", "message": "Session established"}
        except Exception as e:
            logger.exception("generate_session failed for %s", zerodha_id)
            with _lock:
                _job_state["accounts"][zerodha_id] = {"status": "failed", "message": str(e)}

    settings = get_settings()
    for path in (settings.legacy_root / "kite_instances.pkl", settings.legacy_root / "inputs" / "kite_instances.pkl"):
        try:
            with open(path, "wb") as f:
                pickle.dump(instances, f)
        except Exception:
            logger.exception("Could not save session to %s", path)

    with _lock:
        _job_state["running"] = False
        _job_state["error"] = None if instances else "No accounts authenticated successfully"


def start_login_job() -> None:
    with _lock:
        if _job_state["running"]:
            return
        _job_state["running"] = True
        _job_state["error"] = None
    thread = threading.Thread(target=_run_job, name="announcement-trading-login", daemon=True)
    thread.start()
