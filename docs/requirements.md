# Trading Platform — Requirements & Technical Specification

Status: **Draft v1** — 2026-08-14
Owner: single-user, personal use, local deployment
Scope: unify 4 existing Python script collections into one React + FastAPI platform

**Project root:** `D:\Trading System\aitrade` — a fresh directory, **sibling**
to `D:\Trading System\Trading_bot`, not nested inside it. All legacy code
being wrapped (see module specs in §6) stays exactly where it already lives,
under `Trading_bot`; this repo references it by absolute path via one
configured root — see §4.

---

## 0. How to use this document (AI-native development)

This document is the source of truth for building the platform with an AI coding
agent (Claude Code), not a human dev team. It's written so each module can be
handed to an agent as one self-contained unit of work.

Working agreement for any agent session implementing a piece of this:

1. **Read this whole document first**, then read *in full* the specific legacy
   source files listed under the module you're implementing, before writing any
   code. The legacy files are the source of truth for business logic — this doc
   describes how to wrap/expose them, not how to reimplement the algorithms.
2. **One module (or phase) per session/branch.** Don't reach across module
   boundaries into another module's legacy files.
3. **Never modify a legacy file's write-ownership.** If a file today is the sole
   writer of a DB (e.g. `collector.py` → `marketdata.db`), new code reads that
   DB, it does not also write to it from a second process.
4. **Wrap, don't rewrite**, unless a module spec below explicitly says to
   decompose a file (this applies to `Kite_API_31.py` specifically — see Module
   B and the Execution Engine).
5. Every new backend endpoint ships with its frontend TanStack Query hook in the
   same pass — don't leave API/UI out of sync across sessions.
6. If an assumption has to be made, add it to §9 (Open questions) instead of
   silently deciding — this doc gets updated as decisions firm up, and future
   agent sessions read it as context.
7. Default state for anything that places real orders is **disabled**. Nothing
   trades live until a human explicitly arms it.

---

## 1. Product overview

Replace a set of ad hoc Streamlit apps and standalone polling scripts (in
`Trading_bot/` and `Trading_bot/_archive/other_bot_projects/new_trade_tool/`
— see §6 for the exact files each module wraps) with one coherent local
platform:

- A single React UI covering all 4 feature areas.
- A single FastAPI backend behind it.
- One shared broker-execution surface, since two independent strategies trade
  through the same Kite account and capital.

**Non-goals for v1:** multi-user/tenant support, cloud hosting, mobile app,
replacing Kite Connect or TrueData as data sources, rewriting NLP models.

---

## 2. Users & environment

- Single user, runs entirely on the local Windows machine that already runs the
  existing scripts.
- Backend: FastAPI + Uvicorn on `localhost:8000`.
- Frontend: React (Vite) on `localhost:5173` (dev) or a local static build.
- No internet-facing deployment. No need for HTTPS, multi-tenant auth, or a
  secrets vault beyond the existing `.env` pattern.
- Kite login stays Selenium/TOTP-automated as it is today — acceptable because
  it runs on the owner's own machine under the owner's own account.

---

## 3. Locked architecture decisions

| Concern | Decision | Why |
|---|---|---|
| Backend framework | FastAPI + Uvicorn | Async-native (fits WebSocket ticks + polling workers already in use), Pydantic validation, auto OpenAPI schema for frontend type generation |
| Backend language | Python 3.11+ | Matches existing scripts |
| Validation | Pydantic v2 | Ships with FastAPI |
| Database | SQLite (existing files), WAL mode | Single user, no concurrent-writer problem; keep the DB-per-domain split already in place (`marketdata.db`, `announcements_seen.db`) rather than merging |
| DB access | stdlib `sqlite3` for modules reading existing DBs (match `db.py` style); SQLAlchemy Core only for genuinely new tables | Consistency with what's already there |
| Background workers | `asyncio` tasks inside the FastAPI process for lightweight pollers (announcements listener); keep `collector.py` as its own separate OS process, unchanged | Preserves the existing "collector never crashes because of strategy code" design principle |
| Real-time push | WebSocket for trading (candles/ticks/signals), SSE for announcements (one-directional feed) | Replaces today's 3-second `st.cache_data(ttl=3)` polling hack |
| Frontend | React 18 + TypeScript + Vite | Fast local dev loop, typed |
| Data fetching | TanStack Query | Caching/retry/polling fallback for anything not on WS/SSE |
| Global state | Zustand (light) | Only for cross-cutting UI state (kill-switch status, selected account) |
| Charts | `lightweight-charts` (TradingView OSS) | Candle/OHLCV-shaped data already matches the `candles` table schema |
| Config | `python-dotenv`, existing `.env` files | Already the pattern in use |

---

## 4. Repository layout (new)

`aitrade/` is its own standalone root — a separate drive location from
`Trading_bot/`, not a subfolder of it. Legacy code is **not moved or
copied** — it's read from where it already sits, via one configured absolute
path (`LEGACY_ROOT`), so imports don't hardcode a machine-specific path in
more than one place.

```
D:\Trading System\
  aitrade/                          <- new, this project's root
    docs/
      requirements.md               <- this file
    backend/
      app/
        main.py
        core/
          config.py                 # defines LEGACY_ROOT, reads from .env
          db.py                     # session helpers
          security.py
        modules/
          announcements/            # Module A
          announcement_trading/     # Module B
          equity_trading/           # Module C
          execution/                # Shared Execution Engine
          historical/               # Module D
        shared/
      requirements.txt
      .env                          # LEGACY_ROOT=D:\Trading System\Trading_bot
    frontend/
      src/
        modules/                    # mirrors backend module split
        shared/
      package.json

  Trading_bot/                      <- existing, untouched
    new_trade_tool/                 <- unchanged, Module C wraps this
    Kite_API_31.py                  <- unchanged, wrapped by Module B / Execution
    announcement_listener_v2.py     <- unchanged, wrapped by Module A
    zerodha_api_core.py             <- unchanged, wrapped by Module D
    ...
```

**Cross-repo import convention:** `backend/app/core/config.py` defines
`LEGACY_ROOT` (from `.env`, default `D:\Trading System\Trading_bot`). Any
module needing a legacy file adds `LEGACY_ROOT` to `sys.path` at startup
rather than each module hardcoding its own relative walk-up — one seam to fix
if the legacy tree ever moves again (as its own history shows it has before).

---

## 5. Cross-cutting non-functional requirements

- **Logging:** structured, per-module log files, following the existing
  `listener.log` / `geckodriver.log` pattern; rotate.
- **Resilience:** every background worker (listener, scanner) must survive and
  log its own failures without taking down the FastAPI process — this is the
  same principle `collector.py`'s docstring already states; preserve it, don't
  relax it when wrapping.
- **Secrets:** never in code or in this doc; `.env` stays the pattern. Kite
  access tokens move from plaintext (`access_token_cache.json`, hardcoded
  globals in `global_var.py`) to a local encrypted file (e.g.
  `cryptography.Fernet` + a local key file) — worthwhile hardening even for
  single-user, not blocking for v1.
- **Auditability:** any "trade intent → order placed" path writes an audit row
  **before** the order call, not after — so a crash mid-call still leaves a
  record of what was attempted.
- **DB write ownership:** one writer per table, documented per module. New
  FastAPI code reads `marketdata.db`; it never writes to it.

---

## 6. Module specs

### Module A — Corporate Announcements Feed

**Wraps:** `announcement_listener_v2.py`, `financial_result_checker.py`
(ONNX FinBERT sentiment), `bonus_buyback_extract.py`, the scraping portions of
`nse_bse_extraction_tool.py` relevant to announcement capture.

**Responsibilities**
- Background poller (asyncio task) replacing the standalone script's own loop,
  writing to `announcements_seen.db` (existing `signals` table schema).
- NLP enrichment attached per row (sentiment label/score, category, bonus/
  buyback flag, financial-result flag).
- Dedup (existing logic already does this — preserve it).

**API**
- `GET /announcements` — paginated, filterable by exchange / date / keyword.
- `GET /announcements/{id}`
- `SSE /announcements/stream` — push new rows as captured.

**Data contract**
Reuse the existing `signals` table columns as-is (`id, captured_utc,
announcement_time_ist, stock_name, bse_code, nse_symbol, exchange, title,
message, link, pdf_url, pdf_path`); add nullable enrichment columns
(`sentiment_label, sentiment_score, category, is_bonus_buyback,
financial_result_flag`).

**Acceptance criteria**
- Listener runs a full trading day without manual restart.
- New announcement visible in the React feed within a few seconds of capture.
- TRUEDATA_AUTH_TOKEN expiry (HTTP 401) surfaces as a visible UI banner, not
  just a silent log line — this is a real upgrade over today's failure mode.

**Constraint**
- Decide explicitly whether `signals_dashboard.py`/`view_signals.py` are
  retired once the React view has parity, or kept running in parallel during
  transition (default: retire per-module once parity is verified — see §7).

---

### Module B — Announcement-Driven Trading

**Wraps:** the rule layer inside `Kite_API_31.py`
(`check_category_exists`, blacklist-keyword filters, `get_stop_loss(category)`,
`check_bse_title`) — decomposed out of the monolith, not copied wholesale.

**Responsibilities**
- Subscribe to Module A's feed.
- Evaluate each enriched announcement against configurable rules.
- Emit trade intents to the Shared Execution Engine.

**API**
- `GET/PUT /announcement-trading/rules` — rule config, stored as data (DB/JSON),
  editable from the UI, not hardcoded.
- `GET /announcement-trading/intents` — log of generated intents + outcome.
- `POST /announcement-trading/enabled` — kill switch, **default OFF**.

**Acceptance criteria**
- Every intent is logged even while disabled (dry-run visibility before arming
  live trading).
- Rule changes take effect without a restart.

---

### Module C — Indicator-Based Equity Trading

**Wraps:** `new_trade_tool/collector.py` (unchanged, stays sole writer of
`marketdata.db`), `candle_engine.py`, the `diagnostics` table
(EMA20/EMA50/VWAP/trend/vol_confirm — schema already exists in `db.py`),
`backtest.py`.

**Responsibilities**
- Read API over `candles` / `diagnostics` / `signals`.
- Scanner process (extracted from `new_trade_tool`'s intended
  `scanner.py` split, referenced in `collector.py`'s own docstring) evaluates
  diagnostics → trade intents → Shared Execution Engine.

**API**
- `GET /equity/watchlist`
- `GET /equity/candles?symbol=&interval=`
- `WS /equity/live` — tick/candle push
- `GET /equity/signals`
- `POST /equity/enabled` — kill switch, **default OFF**

**Acceptance criteria**
- React candle chart matches what `dashboard.py` currently shows for the same
  symbol/interval — verify parity before retiring the Streamlit dashboard.
- Read-only phase ships and is verified **before** any order-placement wiring
  (matches the agreed rollout order in §7).

---

### Shared Execution Engine

**Wraps:** `place_orders` / `place_orders_parallel` from `Kite_API_31.py`, the
multi-account session pattern in `load_multi_users.py`, `auth.py`'s Kite
session handling.

**Responsibilities**
- Sole owner of the broker session.
- Accepts trade intents from Module B and Module C.
- Idempotent order placement (dedup on intent id — a retried intent must not
  double-order).
- Positions/holdings view aggregated across both strategies.
- Audit log of every intent and every order call.
- **Global kill switch**, independent of and overriding both strategies'
  individual switches.

**API**
- `POST /execution/intents` — internal, called by Module B/C only.
- `GET /execution/positions`
- `GET /execution/orders`
- `POST /execution/kill-switch`

**Acceptance criteria**
- Flipping the kill switch stops new orders from both strategies within one
  poll cycle.
- Positions view is reconciled against actual Kite account state, not just the
  local intent log — catches local DB drift instead of trusting it blindly.
- No two intents for the same symbol from B and C execute as a silent double
  position without at least a visible warning (collision guard).

---

### Module D — Historical Data Extractor

**Wraps:** `zerodha_api_core.py` (canonical — Kite Connect API based).
`zerodha_history_downloader_scrape.py` (cookie-scrape variant) is **not**
wrapped; retire it once Module D has parity, to avoid maintaining two download
paths.

**API**
- `POST /historical/jobs` — start a download (symbols, date range, interval).
- `GET /historical/jobs/{id}` — progress/status.
- `GET /historical/jobs/{id}/result` — CSV/zip download.

**Acceptance criteria**
- Matches the existing Streamlit app's capability: symbol search, watchlist
  upload, pasted symbol list, date range, interval, threaded download with
  progress.
- Job-based, so React shows a progress bar without holding an HTTP request
  open for the duration of a long download.

---

## 7. Phased delivery plan

Each phase has an explicit Definition of Done — don't start the next phase
until the current one's DoD is met.

| Phase | Scope | Definition of Done |
|---|---|---|
| 0 | Scaffold `aitrade/backend` + `aitrade/frontend`, health-check endpoint | `GET /health` returns 200 from a running Uvicorn process; empty React shell renders and calls it |
| 1 | Module A + Module D (parallel — both are closest to done already) | Both usable from React for daily use, replacing their Streamlit equivalents |
| 2 | Module C, **read-only** | Candle chart parity with `dashboard.py` verified side by side |
| 3 | Shared Execution Engine | Kill switch, audit log, and position reconciliation verified against a real (small/test) order before any strategy is wired to it |
| 4 | Module B, then arm Module B and Module C one at a time behind their kill switches | Each strategy runs live-armed independently; the other's kill switch stays OFF while the first is being verified |

---

## 8. Cross-strategy note: why the Execution Engine is shared

Both "Trading" (announcement-driven) and "Equity trading" (indicator-driven)
place orders through the same Kite account and the same capital pool. If each
strategy keeps its own order-placement code — which is how it exists today,
tangled together inside `Kite_API_31.py` — there is no single place to see
combined exposure, no guard against both firing on the same symbol at once,
and two copies of session/auth logic to keep in sync. One Execution Engine,
two upstream signal producers (Module B, Module C), is both less code and the
only way to get a trustworthy "what do I currently hold, and why" view.

---

## 9. Open questions / assumptions log

- **Historical downloader variant:** assumed `zerodha_api_core.py` (official
  Kite Connect API) is canonical over the cookie-scrape variant. Revisit if
  the scrape variant covers something the API path doesn't.
- **Streamlit retirement timing:** assumed each Streamlit app is retired once
  its React replacement reaches parity, not kept running in parallel
  long-term. Revisit if parallel running turns out to be wanted during
  transition.
- **Scanner process for Module C:** `collector.py`'s docstring references a
  separate `scanner.py` reading `marketdata.db` — assumed this exists or gets
  built as part of Module C; confirm which is the case when Phase 2 starts.
- **Backtest engine integration:** `backtest.py`'s exact integration point
  (Module C only, or also exposed via Module D for research) not yet decided
  — revisit when Phase 2/1 implementation starts.
