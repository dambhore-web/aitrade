"""
Live BSE/NSE announcement fetch + Kite market-data lookups, ported from
Kite_API_31.py.

BSE: a plain, unauthenticated GET to BSE's public announcements API --
verified this needs no cookies.

NSE: Kite_API_31.py defines nse_data() TWICE; Python keeps the second
definition, which -- confirmed by reading it -- ignores its own `cookies`
argument and just does session.get(nse_url, params=params_nse, timeout=10),
no explicit cookies=/headers=. That's not dead code, though: `session` is a
shared module-level object, and nse_data_new()'s except block (verified by
reading it in full, not stopping partway through as an earlier pass here
did) closes it, opens a fresh requests.Session(), and does
session.headers.update(set_header()) + session.cookies.update(cookies) --
which `session.get()` then carries automatically on every later call
through the same session object, with no per-call cookies= needed. So the
mechanism is real: NSE fetches run bare until the first failure, which
triggers get_app_id() (NSE_website_opener.py -- the one actually imported
and called by nse_data_new(); NSE_BSE_DATA_PULL.py has a differently-scoped
get_app_id() local to its own historical-pull function, unrelated to this
live path) to open a headless Firefox, visit NSE's real announcements page,
and read back the nsit/nseappid cookies its anti-bot check sets -- then
every subsequent call reuses them until the next failure repeats the cycle.
Ported faithfully as _refresh_nse_cookies_via_browser() +
_maybe_refresh_nse_session(), on the modern Selenium 4 API (the original
used the executable_path= kwarg, removed in Selenium 4) with two added
timeout layers (command-executor + outer ThreadPoolExecutor watchdog) a
geckodriver crash can't turn into another full-process freeze (see
docs/requirements.md incident notes).

One deliberate change from "as it is": the original retries on every single
failed cycle, no cooldown. Kept that (no artificial delay), but gated the
browser launch on "one already in flight" rather than time -- the loop
polls every 1.5s, and firing a new Firefox launch every cycle while earlier
ones are still running is exactly the pattern that left 26 orphaned
firefox.exe processes after the freeze incident.

The TickerPlant merge step (an optional local file at D:\\ticker\\tp.csv in
the original, wrapped in its own try/except that silently continues on
failure) is not ported -- best-effort/optional there, and its absence here
fails exactly as silently as it would have there.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Optional

import pandas as pd
import requests

from app.core.config import get_settings

from . import reference_data, session

logger = logging.getLogger("announcement_trading.market_data")

BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
NSE_URL = "https://www.nseindia.com/api/corporate-announcements"
NSE_ANNOUNCEMENTS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}
# Applied to `_session` only after a successful cookie refresh -- the
# original built an equivalent header dict (set_header()) but, like the
# cookies, never actually attached it to the live request either.
#: Matches set_header()'s field set exactly (Kite_API_31.py:3336, the
#: effective definition) -- its User-Agent came from a random_agent() call
#: (the fake_useragent package, which does its own live HTTP fetch of a UA
#: list); a fixed modern Chrome UA here avoids that extra dependency and
#: failure point without changing what the header accomplishes. Its
#: commented-out 'Cookie' entry (a long-stale captured value) is correctly
#: not ported -- it was never live in the original either.
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Referer": NSE_ANNOUNCEMENTS_PAGE,
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}
PARAMS_NSE = {"index": "equities"}

_MERGED_COLS = ["desc", "an_dt", "attchmntText", "attchmntFile", "symbol"]

_session = requests.Session()
_news_type_lock = threading.Lock()
_news_type: Optional[list[str]] = None

_nse_refresh_in_progress = threading.Event()
_nse_cookies_refreshed: bool = False


def _refresh_nse_cookies_via_browser() -> tuple[str, str]:
    """Faithful port of NSE_website_opener.py's get_app_id() (the function
    actually called from nse_data_new()'s except block -- verified by
    tracing the full call chain, not the differently-scoped local
    get_app_id() inside NSE_BSE_DATA_PULL.py's historical-pull function,
    which is unrelated). Visits NSE's real announcements page in a headless
    Firefox so its anti-bot check sets real nsit/nseappid cookies, read back
    off the browser and reused directly in plain `requests` calls from then
    on. Returns ("xx", "xx") on total failure, matching the original's own
    placeholder-on-failure sentinel."""
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service

    settings = get_settings()
    options = Options()
    options.add_argument("--headless")
    service = Service(str(settings.legacy_root / "browsers" / "geckodriver.exe"))
    driver = webdriver.Firefox(service=service, options=options)
    # Two independent timeout layers -- see module docstring. A geckodriver
    # that dies mid-session must never be able to hang this indefinitely
    # again.
    driver.command_executor.set_timeout(30)
    driver.set_page_load_timeout(30)
    try:
        driver.get(NSE_ANNOUNCEMENTS_PAGE)
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        return cookies.get("nseappid", "xx"), cookies.get("nsit", "xx")
    except Exception:
        logger.exception("NSE cookie refresh browser session failed")
        return "xx", "xx"
    finally:
        driver.quit()


def _maybe_refresh_nse_session() -> None:
    """Port of nse_data_new()'s except block: on every failure (verified --
    the original has no cooldown at all, it retries every single failed
    cycle) closes the shared session and opens a fresh one with the
    refreshed cookies + headers attached, exactly matching
    session.close(); session = requests.Session(); session.headers.update
    (...); session.cookies.update(...).

    The one deliberate change from the original: gated on "is a refresh
    already running", not time. The original's unconditional per-failure
    retry is fine at its own pace, but this loop polls every 1.5s -- without
    this gate, a sustained NSE outage would fire a new Firefox launch every
    cycle while earlier ones are still mid-flight, which is the exact
    pattern that left 26 orphaned firefox.exe processes running after an
    earlier incident. This preserves "retries every failure, no artificial
    delay" while still guaranteeing at most one browser session at a time.
    """
    if _nse_refresh_in_progress.is_set():
        return
    _nse_refresh_in_progress.set()

    def _watchdog():
        global _session, _nse_cookies_refreshed
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_refresh_nse_cookies_via_browser)
                try:
                    app_id, nsit = future.result(timeout=60)
                except FuturesTimeoutError:
                    logger.error("NSE cookie refresh timed out after 60s")
                    return
            if app_id == "xx":
                logger.warning("NSE cookie refresh failed -- browser could not establish a session")
                return
            _session.close()
            _session = requests.Session()
            _session.headers.update(NSE_HEADERS)
            _session.cookies.update({"nseappid": app_id, "nsit": nsit})
            _nse_cookies_refreshed = True
            logger.info("NSE session cookies refreshed successfully")
        finally:
            _nse_refresh_in_progress.clear()

    threading.Thread(target=_watchdog, name="nse-cookie-refresh", daemon=True).start()

# Last fetch error per source, surfaced via /announcement-trading/auto/status
# so "why is the dot red" is answerable from the UI, not just a scrolling
# terminal log -- these were previously caught and swallowed with only a
# logger.exception() call, invisible unless you were watching that terminal
# at the right moment.
_last_bse_error: Optional[str] = None
_last_nse_error: Optional[str] = None


def get_last_fetch_errors() -> tuple[Optional[str], Optional[str]]:
    return _last_bse_error, _last_nse_error


def _news_type_allowlist() -> list[str]:
    """desc/category values allowed through -- from inputs/nse_descriptions.csv."""
    global _news_type
    with _news_type_lock:
        if _news_type is None:
            path = get_settings().legacy_root / "inputs" / "nse_descriptions.csv"
            df = pd.read_csv(path)
            _news_type = df["news_type"].dropna().str.lower().tolist()
        return _news_type


def check_desc(desc: Optional[str]) -> bool:
    if desc is None:
        return False
    return desc.lower() in _news_type_allowlist()


def bse_data(hours_back: float = 0) -> tuple[pd.DataFrame, int]:
    """Returns (data, state) -- state 1 on success, 0 on failure, matching
    the original's connection-status semantics."""
    import datetime as dt

    tt = (dt.datetime.today() - dt.timedelta(hours=hours_back, seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    params_bse = {
        "pageno": "1",
        "strCat": "-1",
        "strPrevDate": dt.datetime.today().strftime("%Y%m%d"),
        "strScrip": "",
        "strSearch": "P",
        "strToDate": dt.datetime.today().strftime("%Y%m%d"),
        "strType": "C",
    }
    global _last_bse_error
    try:
        resp = _session.get(BSE_URL, params=params_bse, headers=BSE_HEADERS, timeout=10)
        if resp.status_code != 200:
            _last_bse_error = f"HTTP {resp.status_code} from BSE"
            logger.warning(_last_bse_error)
            return pd.DataFrame(columns=_MERGED_COLS), 0
        data_b = pd.json_normalize(resp.json().get("Table", []))
    except Exception as e:
        _last_bse_error = f"{type(e).__name__}: {e}"
        logger.exception("Error downloading BSE data")
        return pd.DataFrame(columns=_MERGED_COLS), 0

    if data_b.empty:
        _last_bse_error = None
        return data_b, 1

    try:
        data_b["attchmntFile"] = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/" + data_b.get(
            "ATTACHMENTNAME", ""
        )
        data_b.rename(
            columns={"DissemDT": "an_dt", "HEADLINE": "attchmntText", "CATEGORYNAME": "desc"}, inplace=True
        )
        data_b["DT_TM"] = pd.to_datetime(data_b["DT_TM"], errors="coerce")
        data_b = data_b[data_b["DT_TM"] > tt].sort_values(by="DT_TM")
    except Exception as e:
        _last_bse_error = f"{type(e).__name__}: {e}"
        logger.exception("Error processing BSE data")
        return pd.DataFrame(columns=_MERGED_COLS), 0

    _last_bse_error = None
    return data_b, 1


def nse_data_fetch() -> tuple[pd.DataFrame, int]:
    global _last_nse_error
    try:
        resp = _session.get(NSE_URL, params=PARAMS_NSE, timeout=10)
        if resp.status_code != 200:
            _last_nse_error = f"HTTP {resp.status_code} from NSE"
            logger.warning(_last_nse_error)
            _maybe_refresh_nse_session()
            return pd.DataFrame(columns=_MERGED_COLS), 0
        data_nse = pd.json_normalize(resp.json())
        _last_nse_error = None
        if "an_dt" not in data_nse.columns or data_nse.empty:
            return pd.DataFrame(columns=_MERGED_COLS), 1
        return data_nse, 1
    except Exception as e:
        in_progress_note = " (a session refresh is already in progress)" if _nse_refresh_in_progress.is_set() else ""
        _last_nse_error = (
            f"{type(e).__name__}: {e} -- NSE needs a warmed browser session (anti-bot cookies) before "
            f"its API responds; refreshing one now in the background{in_progress_note}."
        )
        logger.exception("Error fetching NSE data")
        _maybe_refresh_nse_session()
        return pd.DataFrame(columns=_MERGED_COLS), 0


def merge_bse_nse(data_nse: pd.DataFrame, data_b: pd.DataFrame) -> pd.DataFrame:
    """Faithful port of merge_bse_nse_ticker(), minus the optional
    TickerPlant append (see module docstring)."""
    try:
        if not data_b.empty:
            data_b["SCRIP_CD"] = pd.to_numeric(data_b["SCRIP_CD"], downcast="signed")
            sl = reference_data.symbol_list().copy()
            sl["SCRIP_CD"] = pd.to_numeric(sl["SCRIP_CD"], downcast="signed")
            data_bse = pd.merge(data_b, sl, how="inner", on=["SCRIP_CD"])
            data_bse.rename(columns={"SYMBOL": "symbol", "Sector": "smIndustry"}, inplace=True)
            data_bse = data_bse[_MERGED_COLS]
        else:
            data_bse = pd.DataFrame(columns=_MERGED_COLS)

        if not data_nse.empty:
            data_nse = data_nse[[c for c in _MERGED_COLS if c in data_nse.columns]]
            for c in _MERGED_COLS:
                if c not in data_nse.columns:
                    data_nse[c] = None
            data_nse = data_nse[_MERGED_COLS]
        else:
            data_nse = pd.DataFrame(columns=_MERGED_COLS)

        if len(data_nse) > 0 and len(data_bse) > 0:
            data = pd.concat([data_bse, data_nse], ignore_index=True)
        elif len(data_nse) > 0:
            data = data_nse
        elif len(data_bse) > 0:
            data = data_bse
        else:
            return pd.DataFrame(columns=_MERGED_COLS)

        data = data.sort_values("an_dt", ascending=False)
        data = data.drop_duplicates(subset="symbol", keep="first")
        data = data[data["desc"].apply(check_desc)]
        return data
    except Exception:
        logger.exception("Error in merge_bse_nse")
        return pd.DataFrame(columns=_MERGED_COLS)


def fetch_new_announcements(hours_back: float = 0) -> tuple[pd.DataFrame, int, int]:
    """Returns (merged_data, state_nse, state_bse)."""
    data_b, state_bse = bse_data(hours_back)
    data_nse, state_nse = nse_data_fetch()
    merged = merge_bse_nse(data_nse, data_b)
    return merged, state_nse, state_bse


# ---------------------------------------------------------------------
# Kite-backed lookups (clean KiteConnect SDK calls -- no scraping needed)
# ---------------------------------------------------------------------
def _first_kite():
    instances = session.get_kite_instances()
    return instances[0][0]


def get_token(security: str):
    """Returns (token, exchange, name) or None if not found."""
    df = reference_data.zerodha_list_equity()
    matches = df.loc[df["tradingsymbol"] == security]
    if matches.empty:
        return None
    if len(matches) == 1:
        row = matches.iloc[0]
        return row["instrument_token"], row["exchange"], row["name"]
    for _, row in matches.iterrows():
        if row["exchange"] == "NSE":
            return row["instrument_token"], "NSE", row["name"]
    row = matches.iloc[0]
    return row["instrument_token"], row["exchange"], row["name"]


def get_token_and_margin(security: str):
    """Returns (token, exchange, margin). Raises ValueError if not found,
    matching the original."""
    df = reference_data.zerodha_list_equity()
    filtered = df[df["tradingsymbol"] == security]
    if len(filtered) == 1:
        row = filtered.iloc[0]
        return row["instrument_token"], row["exchange"], row["margin"]
    if len(filtered) > 1:
        nse_row = filtered[filtered["exchange"] == "NSE"]
        row = nse_row.iloc[0] if not nse_row.empty else filtered[filtered["exchange"] == "BSE"].iloc[0]
        return row["instrument_token"], row["exchange"], row["margin"]
    raise ValueError(f"No observations found for symbol: {security}")


def symbol_check(security: str) -> int:
    df = reference_data.zerodha_list_equity()
    return 1 if not df.loc[df["tradingsymbol"] == security].empty else 0


def get_stock_info(exchange: str, stock_name: str) -> tuple[float, float]:
    """Returns (volume, spread_percentage). (100, 0) on failure, matching
    the original's fallback."""
    try:
        query = f"{exchange}:{stock_name}"
        kite = _first_kite()
        quote = kite.quote(query)
        volume = quote[query]["volume"]
        sell = quote[query]["depth"]["sell"][0]["price"]
        buy = quote[query]["depth"]["buy"][0]["price"]
        spread_pct = ((sell - buy) / sell) * 100
        return volume, spread_pct
    except Exception:
        logger.debug("get_stock_info failed for %s:%s", exchange, stock_name, exc_info=True)
        return 100, 0


def get_current_price(security: str) -> float:
    """Returns 1 on failure, matching the original's fallback."""
    try:
        _token, exchange, _margin = get_token_and_margin(security)
        query = f"{exchange}:{security}"
        kite = _first_kite()
        quote = kite.ltp(query)
        price = quote[query]["last_price"]
        return float(price)
    except Exception:
        logger.debug("get_current_price failed for %s", security, exc_info=True)
        return 1.0


def historical_pricev1(security: str) -> tuple[float, float, float]:
    """Returns (change_pct, highest_value, last_open). (10, 15, 100) on
    failure, matching the original's fallback."""
    import datetime as dt

    try:
        kite = _first_kite()
        token, _exchange, _margin = get_token_and_margin(security)
        data = kite.historical_data(
            instrument_token=int(token),
            from_date=dt.datetime.now() - dt.timedelta(minutes=15),
            to_date=dt.datetime.now(),
            interval="minute",
            oi=True,
        )
        df = pd.DataFrame(data)
        if df.empty:
            return 10, 15, 100
        last_15 = df.tail(15).copy()
        highest = pd.to_numeric(last_15["high"], errors="coerce").max()
        lowest = pd.to_numeric(last_15["low"], errors="coerce").min()
        change = (highest - lowest) * 100 / lowest
        last_open = df.iloc[-1]["open"]
        return change, highest, last_open
    except Exception:
        logger.debug("historical_pricev1 failed for %s", security, exc_info=True)
        return 10, 15, 100
