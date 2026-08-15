"""
Live BSE/NSE announcement fetch + Kite market-data lookups, ported from
Kite_API_31.py.

BSE: a plain, unauthenticated GET to BSE's public announcements API --
verified this needs no cookies. NSE: also ported as a plain unauthenticated
GET (Kite_API_31.py defines nse_data() TWICE; Python keeps the second
definition, which -- confirmed by reading it -- ignores the `cookies`
argument entirely and just does a bare requests.Session().get(). The whole
NSE-session-cookie/Selenium-bootstrap machinery elsewhere in that file is
therefore dead code on the actual call path; not ported. NSE fetches may
fail with 401/403 without a warmed browser session -- that's the original's
real behavior too, not a regression; failures surface as a normal state=0,
same as the original's own error handling.

The TickerPlant merge step (an optional local file at D:\\ticker\\tp.csv in
the original, wrapped in its own try/except that silently continues on
failure) is not ported -- best-effort/optional there, and its absence here
fails exactly as silently as it would have there.
"""
import logging
import threading
from typing import Optional

import pandas as pd
import requests

from app.core.config import get_settings

from . import reference_data, session

logger = logging.getLogger("announcement_trading.market_data")

BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
NSE_URL = "https://www.nseindia.com/api/corporate-announcements"

BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}
PARAMS_NSE = {"index": "equities"}

_MERGED_COLS = ["desc", "an_dt", "attchmntText", "attchmntFile", "symbol"]

_session = requests.Session()
_news_type_lock = threading.Lock()
_news_type: Optional[list[str]] = None


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
    try:
        resp = _session.get(BSE_URL, params=params_bse, headers=BSE_HEADERS, timeout=10)
        if resp.status_code != 200:
            logger.warning("BSE API returned status %s", resp.status_code)
            return pd.DataFrame(columns=_MERGED_COLS), 0
        data_b = pd.json_normalize(resp.json().get("Table", []))
    except Exception:
        logger.exception("Error downloading BSE data")
        return pd.DataFrame(columns=_MERGED_COLS), 0

    if data_b.empty:
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
    except Exception:
        logger.exception("Error processing BSE data")
        return pd.DataFrame(columns=_MERGED_COLS), 0

    return data_b, 1


def nse_data_fetch() -> tuple[pd.DataFrame, int]:
    try:
        resp = _session.get(NSE_URL, params=PARAMS_NSE, timeout=10)
        if resp.status_code != 200:
            logger.warning("NSE API returned status %s", resp.status_code)
            return pd.DataFrame(columns=_MERGED_COLS), 0
        data_nse = pd.json_normalize(resp.json())
        if "an_dt" not in data_nse.columns or data_nse.empty:
            return pd.DataFrame(columns=_MERGED_COLS), 1
        return data_nse, 1
    except Exception:
        logger.exception("Error fetching NSE data")
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
