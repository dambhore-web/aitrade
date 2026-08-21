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

**Status: built but unmounted — dropped by user decision.** TrueData was
judged not needed: Module B's own direct BSE/NSE scan already covers
corporate announcements end to end, so running a second, separate
announcement source was redundant and confusing (it produced two
disconnected-looking "announcement" surfaces in the UI). `main.py` no
longer starts the listener thread or mounts its router; the code under
`backend/app/modules/announcements/` and the DB it wrote to
(`Trading_bot/announcements_seen.db`) are untouched, not deleted, in case
this is wanted again later.

**Wraps (for reference, not currently running):**
`announcement_listener_v2.py`, `financial_result_checker.py`
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

**Status: built, including the automatic loop — full "as it is" parity was
explicitly requested (real money, no manual-confirmation redesign).** Two
windows, matching how the legacy app itself is laid out:

- **Window 1 — Session & Settings** (`TradingSettingsPanel`): the GTT
  Parameters / Zerodha Configuration / NSE App Configuration inputs from
  `Kite_API_31.py`'s PySimpleGUI app (`main()`, "Trading Bot - Professional
  Edition") — Amount, Order Variety, Order Type, Market/Product Type, GTT
  Stop Loss %, GTT Target %, Past Hours, NSE App ID/IT, Send-to-Telegram —
  as a real persisted form (`announcement_trading.db`, replacing
  `inputs/global.pickle`), plus a **Generate Token** action that logs into
  every account in `Zerodha_Orders.xlsx` (real Selenium logins) and produces
  the shared session both this module and Module C's future execution
  wiring will use.
- **Window 2 — Live Trading** (`AutomatedTradingPage`): START/STOP for the
  continuous scan→classify→trade loop, BSE/NSE connection-status dots, and
  a live SSE-fed activity table — every announcement the loop looks at,
  with its category/sentiment and either its skip reason or the order it
  triggered. Off by default; only runs after an explicit START, mirroring
  the legacy app's own STOP CODE/START CODE requirement (§0 rule 7) — not a
  restriction added on top of "as it is", it's what "as it is" already does.

**How it was built — ported, not imported.** `Kite_API_31.py` was tested
directly (see §9): importing it takes 70s and launches a real Firefox
session via Selenium as a *side effect of import alone*, which itself
failed in isolation. That ruled out running the real file as a subprocess.
Every function on the live decision path was instead traced end-to-end and
faithfully ported into `announcement_trading/`:

| File | Ported from | Notes |
|---|---|---|
| `market_data.py` | `bse_data`, `nse_data` (`Kite_API_31.py` defines two; the second, effective one ignores its `cookies` arg entirely), `merge_bse_nse_ticker`, `get_token`, `get_stock_info`, `get_current_price`, `historical_pricev1` | BSE is a plain public API call; NSE's cookie/Selenium machinery is dead code on the real path, confirmed by reading the effective definition. The optional TickerPlant merge (`D:\ticker\tp.csv`) is not ported — best-effort in the original too. |
| `classification.py` | `cleanText`/`analyseText` (SVM+TF-IDF sentiment) | Category reuses `onnx_bert.py`'s `predict_with_onnx` via clean import — already self-contained, no side effects, and it's what the live pipeline actually calls (a second pickle+tfidf category model also loaded at `Kite_API_31.py` module level has no caller on the live path and isn't ported). |
| `gates.py` | `check_symbol_and_pred_bert_existence`, `check_category_and_text_for_keywords`, `check_category_exists`, freshness check | Pure CSV/list lookups. |
| `execution.py` | `place_orders`/`place_orders_parallel` | Unchanged from the prior pass. |
| `pipeline.py` | `job()`'s inner per-announcement control flow, `get_stop_loss`, `margin_data_calculator.margin_calculator` (imported directly — clean, side-effect-free module) | Assembles the above into the same gate sequence, in the same order, ending in the same GTT-bracket order. |
| `session_login.py` | `fetch_request_token`, `get_token_for_multiple_users` (`load_multi_users.py`), `initialize_kite_instances` | Runs as a background job (each login is a real 10-30s+ Selenium flow); saves the resulting session to both `kite_instances.pkl` paths the original writes. |
| `auto_loop.py` | `the_thread`/`job()`'s scheduling (`schedule.every(1.5s)`) | Own background-thread loop calling the pieces above; in-memory dedup only, matching the original's `master_df`/`symbol_store` (not persisted across restarts). |

**Scoped out, on purpose, and logged per-item rather than silently:** the
short/ambiguous-text rescue path that re-extracts and re-classifies from the
announcement's PDF (plus its LLM-sentiment fallback). In the original this
only fires for short text or category="other"+sentiment="positive", as a
rescue. Skipping it means some announcements that path *would* have rescued
into a real category now just fall through the ordinary
sentiment=="neutral"/category=="other" skip — a real, bounded behavior
difference, tagged `pdf_fallback_not_ported` in the pipeline so it's visible
in the activity feed, not hidden.

**Why a new `trade_entries`/`activity_log`, not just an intent log:** the
original never actually linked a placed order to the announcement that
triggered it — `place_orders_parallel(...)` takes no message argument, and
the only place the two were ever associated (`data_symbol`, a `{SYMBOL,
MESSAGE}` DataFrame) was in-memory only, its one `to_csv` save commented
out. Every automatic-loop item is now logged (`activity_log`) and every
placed order becomes a `trade_entries` row referencing it — fixed going
forward, for both the manual per-announcement flow (still available on the
Announcements page) and the automatic loop.

**API**
- `GET/PUT /announcement-trading/settings`
- `GET /announcement-trading/session-status` — redacted (see Security)
- `POST /announcement-trading/session/generate`, `GET .../session/generate/status`
- `GET /announcement-trading/entries?announcement_id=` / `POST /entries` / `POST /entries/{id}/place-order` (manual flow)
- `POST /announcement-trading/auto/start` / `/auto/stop` / `GET /auto/status`
- `GET /announcement-trading/activity`, `SSE /announcement-trading/activity/stream`

**Security:** `kite_instances.pkl`'s per-account dict, and
`Zerodha_Orders.xlsx`, contain plaintext `password`/`API SECRET`/`TOTP_KEY`
(confirmed by inspecting structure/keys only, never values, during
development). `session-status` and the login-job status return an explicit
safe-field allowlist (Zerodha ID, multiplier, margin, per-account
pending/running/success/failed) — raw credentials and `KiteConnect`
instances never leave the backend process, and neither file is read into
this repo or committed anywhere.

**Verified, end-to-end, against live production data** (not synthetic):
`fetch_new_announcements()` pulled a real BSE filing (JINDALPOLY, "Company
Update"); `process_item()` ran it through real sentiment (SVM) and category
(ONNX BERT) models and correctly skipped it as routine news
(`neutral_or_other`) — a correct decision, not a bug. The live NSE endpoint
timed out in this same test run without a warmed browser session, exactly
the dead-cookie-path behavior identified above, not a regression. **Not**
verified: an actual order placement (deliberately never triggered outside
the user's own explicit action — this fires real trades).

**Acceptance criteria**
- Automatic loop starts/stops only on explicit action; off after every
  restart.
- Every processed announcement — traded or not — is visible in the
  activity feed with its category/sentiment and outcome.
- Placing an order (manual or automatic) fails clearly, not silently, when
  no Kite session exists.

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

**Decisions made while building Phase 1 (Module A + Module D):**

- **`financial_result_checker.py` does not produce sentiment.** Its docstring
  claims "positive"/"negative" sentiment, but `find_news_result()` actually
  returns `"result"` or `"general"` — it classifies whether text *is* a
  financial-result announcement, not its polarity. Module A's enrichment
  therefore populates `financial_result_flag` (1/0), not `sentiment_label`/
  `sentiment_score` — those two columns exist in the schema per the original
  data contract but stay unpopulated until a real sentiment model is wired in.
- **`bonus_buyback_extract.py` and the scraping portions of
  `nse_bse_extraction_tool.py` were not wrapped in this first pass** of
  Module A — both are large (39KB/69KB) and not required to get the core
  listener→feed→React pipeline working end to end. `category` and
  `is_bonus_buyback` stay unpopulated for now; wiring those in is follow-up
  work on Module A, not a new module.
- **Module D's job registry is in-memory only** (a plain dict in the backend
  process) — jobs don't survive a backend restart. Acceptable for a
  single-user local tool where a job is a one-off download; revisit with a
  persisted store only if that becomes a real annoyance.
- **`KITE_API_KEY`/`KITE_API_SECRET` were copied into `aitrade/backend/.env`
  directly**, rather than the backend reaching into
  `Trading_bot/_archive/other_bot_projects/new_trade_tool/.env` where they
  also live — that path has already moved once (per that project's own
  `config.py` comment) and Module D shouldn't depend on it staying put.
  `TRUEDATA_AUTH_TOKEN`/`OPENAI_API_KEY` were *not* copied and stay
  single-sourced in `Trading_bot/.env`, loaded at runtime via
  `app.core.legacy_path.load_legacy_env()` — refreshing the TrueData token
  (it expires every few hours) only ever has to happen in one file.
- **Downloaded historical CSVs land in `aitrade/data/historical/`**, not
  `Trading_bot/dev/zerodha_history/` — keeps aitrade's own output
  self-contained rather than writing into the legacy tree.
- **The announcement listener runs as a background thread, not an asyncio
  task**, reusing `announcement_listener_v2.py`'s own lock-file guard
  (`Trading_bot/listener.lock`) so it refuses to run two instances at once.
  The inherited quirk this caused in practice — `uvicorn --reload` tearing
  down the old worker before its thread's `finally: release_lock()` ran,
  leaving a stale lock every reload — is now fixed on our side:
  `listener.py._clear_stale_lock()` checks the lock file's recorded PID with
  `psutil.pid_exists()` and clears it only when confirmed dead, before
  calling the legacy `acquire_lock()`. The legacy file itself is untouched.

**Decisions made while building Phase 2 (Module C) and the announcement-trading panel:**

- **`marketdata.db` connections use SQLite's `mode=ro` URI flag**, not just
  the "don't write to it" convention — verified it raises `OperationalError`
  on any write attempt. `collector.py` stays the sole writer;
  `scanner.py`'s own live strategy/execution loop (confirmed actively
  running — real signals appear in the DB in real time) is never touched.
- **`watchlist.csv` is deduped on read** (order-preserving) rather than
  edited — it has a genuine duplicate row (`WCIL`) that surfaced as a React
  duplicate-key warning; `zerodha_scrape_core.py`'s `dedupe_upper` already
  treats this exact class of CSV issue as something to defend against, not
  assume away.
- **Two separate Kite auth mechanisms coexist in `Trading_bot`, deliberately
  not unified**: the official Kite Connect SDK (api_key + access_token via
  `generate_session()`, used by `auth.py`/`collector.py`/Module D) and the
  legacy enctoken web-session style (`KITE_ENCTOKEN` etc. in `.env`, used by
  some scraping code). `Kite_API_31.py`'s "Get Token" button produces an
  enctoken, but the actual order-placement path
  (`place_orders`/`place_orders_parallel`) runs on `KiteConnect` SDK
  instances from `kite_instances.pkl`, produced separately by its "Load User
  Data" button — that pkl, not the enctoken, is the real shared session
  Module B and Module C's future execution wiring should both consume.
- **`kite_instances.pkl` and `Zerodha_Orders.xlsx` are read but never
  regenerated by this backend.** The pickle's per-account dict was confirmed
  (by inspecting its keys only, never its values) to contain plaintext
  `password`/`API SECRET`/`TOTP_KEY` — the login that produces it is a real
  Selenium-driven action a human runs deliberately, not something to trigger
  from an API call.
- **No token, no trade — enforced in both layers, not just the backend.**
  `place-order` hard-fails (409) with no `kite_instances.pkl`; the Trade
  panel now also checks session status itself and disables "Place order
  (LIVE)" with an explanatory banner before the click, rather than only
  surfacing the failure after attempting one.
- **Follow-up, not yet done:** `announcement_trading/session.py` (reads
  `kite_instances.pkl`) currently lives inside Module B's package, but nothing
  about it is announcement-specific — Module C's future order-placement work
  needs the exact same session. Move it to `app/shared/kite_session.py` next
  time either module's execution path is touched, so both import from one
  place instead of Module C reaching into Module B's internals.

**Decisions made building the automatic loop (Module B, full parity pass):**

- **`transformers` pinned to `<5.0`.** `onnx_bert.py` (reused via clean
  import for category classification) calls `tokenizer.encode_plus()`,
  removed in transformers 5.x. Pinning, not patching the legacy file.
- **`scikit-learn` unpickle version warning, accepted not fixed.** The
  sentiment SVM/vectorizer were pickled under sklearn 1.0.2; this venv runs
  1.9.x. Loads and predicts fine (verified against real text), but
  `InconsistentVersionWarning` is a known sharp edge — if sentiment output
  ever looks wrong, this pin mismatch is the first thing to check, ideally
  by re-pickling the model under a matching sklearn version rather than
  chasing it in code.
- **`OPENAI_API_KEY` in `Trading_bot/.env` is empty**, not just present —
  found while testing dependency changes, unrelated to this pass. Means
  `financial_result_checker.py` (Module A's `financial_result_flag`
  enrichment) has likely been silently non-functional since Phase 1 — its
  import raises, `enrichment.py`'s lazy loader catches it and disables
  enrichment, so Module A itself doesn't break, but the flag never
  populates. Needs a real key from the user; not something to fix blind.
- **The PDF re-extraction/re-classification rescue path is not ported** —
  see Module B's write-up above. Logged per-item, not silent.
- **TickerPlant merge (`D:\ticker\tp.csv`) is not ported** — optional/
  best-effort in the original too (wrapped in its own try/except there).
- **The automatic loop's dedup state is in-memory only**, matching the
  original's `master_df`/`symbol_store` globals — resets on every restart,
  not persisted. Same tradeoff already accepted for Module D's job registry.
- **Bug found on first real Generate Token click:** `Zerodha_Orders.xlsx`
  actually lives at `Trading_bot/inputs/Zerodha_Orders.xlsx`, not
  `Trading_bot/Zerodha_Orders.xlsx` (root) as assumed while porting
  `load_multi_users.py` (which reads it via a bare relative filename,
  resolved by whatever directory it's launched from — not something to
  infer from the source alone). Fixed in `session_login.py`. Confirmed via
  the corrected path: 1 account (NGQ901), file last modified same day as
  the current `kite_instances.pkl` — genuinely the active file, not a stale
  copy (two backup copies and one old `~$` Excel lock file also sit in that
  folder; not the ones in use).
- **Real incident: a stuck Generate Token attempt froze the entire backend
  process.** After the path fix, a login attempt left `geckodriver.exe`
  dead while Firefox stayed running (confirmed via `tasklist`) — Selenium's
  `RemoteConnection` had no timeout configured, so every subsequent
  WebDriver command (including inside `driver.quit()` in the `finally`
  block) blocked forever waiting on a controller that no longer existed.
  This froze the *whole* process, not just that request — even `GET
  /health`, which touches nothing, stopped responding, which is what
  surfaced the Save-button and Generate-Token "stuck, no feedback" reports.
  Fixed with two independent layers, since the first alone wasn't trusted
  as sufficient: `driver.command_executor.set_timeout(30)` +
  `driver.set_page_load_timeout(30)` inside `_fetch_request_token` itself,
  and a `ThreadPoolExecutor(...).result(timeout=150)` wrapper around each
  account's login in `_run_job` as a second, independent backstop. Also
  added a request-level timeout (`AbortController`, 20s) to every frontend
  API call (`shared/api.ts`) — previously a hung backend meant a button
  stuck on "Saving..." forever with no way to distinguish "still working"
  from "broken"; now it surfaces a clear error instead. A frozen backend
  process itself still requires a manual restart to recover — these fixes
  prevent the freeze, they don't un-freeze an already-stuck process.
- **TrueData dropped entirely (Module A unmounted), by user decision.**
  Judged redundant: Module B's own BSE/NSE scan already covers corporate
  announcements end to end, and running both produced two disconnected
  "announcement" surfaces in the UI. `main.py` no longer starts the
  listener or mounts its router. Code and DB untouched, just unmounted —
  see the updated Module A section above. Frontend consolidated to one page
  (`AnnouncementTradingPage.tsx`, the renamed former `AutomatedTradingPage`)
  under the `/announcements` route; the separate `/auto-trading` route, the
  old TrueData-backed `AnnouncementsPage.tsx`, and `TradePanel.tsx` (its
  manual per-announcement trade UI, which only made sense against that
  TrueData list) were deleted.
- **Added persistent file logging** (`backend/logs/app.log`, rotating,
  10MB × 3 backups) alongside the console — previously logs only existed in
  whatever terminal happened to be running uvicorn at the time, with no
  fixed place to look.
- **NSE cookie auto-refresh, ported — corrected after an incomplete first
  read.** An earlier pass here concluded the cookie-refresh path was dead
  code, because `nse_data()`'s effective definition ignores its own
  `cookies` argument. That was wrong — caught by re-tracing
  `fetch_data_parallel_bse_nse()` all the way through on request, reading
  `nse_data_new()` to its actual end rather than stopping partway through:
  its `except` block closes the shared `session`, opens a fresh
  `requests.Session()`, and does `session.headers.update(set_header())` +
  `session.cookies.update(cookies)` — which `session.get()` then carries on
  every later call automatically, no per-call `cookies=` needed. The
  mechanism is real: NSE fetches run bare until the first failure, which
  triggers `get_app_id()` (`NSE_website_opener.py` — confirmed as the one
  actually imported and called by `nse_data_new()`, not the
  differently-scoped local `get_app_id()` inside
  `NSE_BSE_DATA_PULL.py`'s unrelated historical-pull function, which was
  briefly and mistakenly considered first) to open a headless Firefox,
  visit NSE's real announcements page, and read back the `nsit`/`nseappid`
  cookies its anti-bot check sets.
  Ported faithfully as `_refresh_nse_cookies_via_browser()` +
  `_maybe_refresh_nse_session()` (Selenium 4 API — the original used
  `executable_path=`, removed in Selenium 4), with the same two-layer
  timeout discipline as the Generate Token fix
  (`command_executor.set_timeout` + outer `ThreadPoolExecutor` watchdog) so
  a geckodriver crash can't cause another full-process freeze.
  **One deliberate change from "as it is":** the original retries on every
  single failed cycle with no cooldown at all — kept that (no artificial
  delay was added), but gated the browser launch on "one already in
  flight" rather than time, since firing a new Firefox launch every 1.5s
  cycle while an earlier one is still running is exactly the pattern that
  left 26 orphaned `firefox.exe` processes after the freeze incident.
  **First live attempts all failed** (`"NSE cookie refresh failed --
  browser could not establish a session"`, repeatedly, in the real log) --
  root cause confirmed empirically, not guessed: NSE sets `nsit`/
  `nseappid` via JS *after* the page reports loaded, so reading
  `driver.get_cookies()` immediately after `driver.get()` returns
  routinely misses them. `NSE_website_opener.py`'s `get_app_id()` (the
  function actually on this call path) doesn't wait for that; the
  unrelated `get_app_id()` inside `NSE_BSE_DATA_PULL.py` does, with a
  `time.sleep(3)` and explicit cookie-presence validation, for exactly
  this reason. Added the same wait + validation to the faithful port
  here — the one addition beyond a straight port, and it's a reliability
  fix for a race the original also had, not a logic change.
  **`sleep(3)` fix deployed, but live logs then showed a new, deeper
  symptom:** real cookies were coming back every attempt, just the wrong
  ones — Akamai bot-management cookies (`AKA_A2`, `bm_sz`, `ak_bmsc`,
  `_abck`, `RT`), never `nsit`/`nseappid`. User pushed back hard,
  correctly: *"My existing code Kite_API_31.py works perfectly fine...
  Don't think you are using the same logic."* Re-traced
  `NSE_website_opener.py` character-by-character on that challenge rather
  than re-guessing: `get_app_id()` really is a straight, faithful match —
  same URL, same headless Firefox, same cookie names, no extra headers or
  anti-detection args (the one stealth flag in that file,
  `disable-blink-features=AutomationControlled`, is applied to an unused
  `chrome_options` object — dead code, never reaches the Firefox session
  that actually runs). The real evidence of what's going on was sitting in
  `Kite_API_31.py` itself: `set_header()` has a commented-out `'Cookie'`
  line — a one-time real capture pasted in from a passed browser session —
  carrying the Akamai cookies *and* `nsit`/`nseappid` together, proving
  even the original author had, at some point, to work around this same
  Akamai challenge by hand rather than have `get_app_id()` reliably clear
  it unattended. Akamai's JS collects a sensor payload and POSTs it
  asynchronously after first load; `nsit`/`nseappid` are only issued on a
  *follow-up* request once that validates — a single `get()` plus any
  fixed wait was never going to produce them. Fixed by polling for the
  Akamai cookies (up to 30s), waiting for the async POST, re-navigating
  once to trigger the follow-up request, then continuing to poll for
  `nsit`/`nseappid` before giving up; outer watchdog timeout raised
  60s → 90s to give this room. Ported logic is unchanged — this is a
  second reliability fix for a timing/sequencing issue `get_app_id()`
  itself never had to handle, not a departure from it.
  **Confirmed by 20+ minutes of live testing that this is a hard block, not
  a race:** the auto-loop hammered the refresh every cycle from 18:09 to
  18:32 — dozens of attempts, one every ~10-15s. Real result: Akamai-only
  cookies every single time, except twice (18:22:53, 18:23:14) where `nsit`
  alone showed up — `nseappid` never did, not once. Two cookies set by two
  separate mechanisms, and the harder one never clears. No amount of
  polling or reloading was going to close that gap; retrying every cycle
  was just repeatedly hitting Akamai's protected endpoint at machine
  cadence, which is itself a bot signal likely making the block worse, not
  better.
  **Fix, in two parts:**
  (1) `NSE_REFRESH_COOLDOWN_SECONDS = 900` gates `_maybe_refresh_nse_session()`
  — a real departure from "as it is" (no cooldown at all), justified this
  time by hard evidence rather than a guess: the original's assumption
  (retrying costs nothing, might get lucky) doesn't hold against an active
  bot-detection wall that punishes repeated hits.
  (2) `seed_nse_cookies_from_settings()` — wired the `nse_app_id`/`nse_it`
  fields that were already sitting in the schema, DB, and Settings UI (visible,
  saveable) but never once read by anything on the live NSE path — into the
  session, on backend startup and again after every settings save. Same
  manual-refresh pattern already used for `KITE_ENCTOKEN` elsewhere: grab a
  real `nsit`/`nseappid` pair from your own logged-in browser's devtools,
  paste into Settings, Save — done, no fight with Akamai. The automatic
  Selenium attempt is kept as a best-effort background try (now on a long
  cooldown) in case it ever clears on its own; it is not the primary path
  anymore.
  User pushed back again, correctly: *"GUI input is not used"* — ruling out
  the Settings-paste theory as *the* mechanism (it's still wired up and
  correct, just not what was actually relied on). Went back to
  `Kite_API_31.py` a third time and found a function two earlier passes had
  missed entirely: `getCookiesFromDomain()`/`get_nse_token()`
  (~line 2049–2103) — not wired to `nse_data_new()`'s except block, so it
  never showed up in that trace. It doesn't automate a browser at all: it
  calls `browser_cookie3.firefox()` and reads `nsit`/`nseappid` straight out
  of the **local Firefox install's own cookie store on disk**, filtered to
  the nseindia domain. Real cookies from ordinary human browsing, sitting on
  the machine already — nothing for Akamai's bot check to ever see, because
  there's no automated visit for it to detect. `import browser_cookie3` is
  right there at the top of `Kite_API_31.py`, pinned in
  `Trading_bot/requirements.txt` as `browser-cookie3==0.19.1` — installed
  that exact version into the backend venv and added it to
  `backend/requirements.txt`.
  Ported as `_get_nse_cookies_from_local_browser()`, tried first in
  `_maybe_refresh_nse_session()` (no cooldown needed — it's a local disk
  read, not a network hit) before falling back to the Selenium path, which
  keeps its 900s cooldown. Matches the original having both mechanisms
  available; this one just doesn't fight Akamai in the first place. Needs a
  real Firefox profile on this machine with a recent-enough nseindia.com
  visit for the cookies to still be live — confirmed importable and running
  cleanly (returns the `("xx","xx")` no-cookies-found sentinel correctly
  when none exist), not yet confirmed producing a real nsit/nseappid pair
  end-to-end — that depends on this machine's actual Firefox cookie state,
  not on the code.
  **Resolution, finally found by running the user's own unmodified code
  directly:** ran `NSE_website_opener.py`'s `get_app_id()` as-is, in the
  real anaconda3/Selenium 4.8.2 environment — it failed identically
  (`'nsit'` KeyError). Checked the persisted `global.pickle` `nse_app_id`/
  `nse_it` the original loads at startup — both empty strings, not stale.
  User then pasted a real log from their own running `Kite_API_31.py`:
  `nse_data(cookies)` returned **200 with real live data** while
  `cookies == {'nsit': 'xx', 'nseappid': 'xx'}` — placeholder garbage.
  Proof cookies were never the actual gate on this endpoint: the effective
  `nse_data()` never sends `cookies` as a request parameter at all, it's
  `session.get(nse_url, ...)` on the shared module-level `requests.Session`,
  which auto-persists whatever `Set-Cookie` headers the server sends back
  across the process's lifetime — real Akamai trust cookies accumulate
  from ordinary successful traffic, independent of `nsit`/`nseappid`.
  Reproduced the exact original `nse_data()`/`nse_data_new()` logic
  standalone, looped every 10s: **39/40 cycles succeeded** — only the
  first (cold session, no headers yet) failed. Ported into `market_data.py`
  the actual fix: `_maybe_refresh_nse_session()` now resets the session and
  reapplies `NSE_HEADERS` **unconditionally** on every refresh attempt,
  even with `nsit`/`nseappid` still `"xx"` — matching `nse_data_new()`'s
  except block, which does `session.headers.update(set_header())`
  regardless of whether `get_app_id()` returned real values or its `"xx"`
  failure sentinel (it never raises). The previous port only reapplied
  headers on a successful cookie fetch, which never happened against
  Akamai — so headers, the actual fix, never got attached. Confirmed live
  in the port too (12/15 cycles) and in the running app (`state_nse: 1`).

- **Activity table enhancements (2026-08-15):** added `source` (NSE/BSE),
  `an_dt` (announcement time, normalized via `pd.to_datetime` in
  `merge_bse_nse()` — also fixed a latent bug where the dedup sort was
  comparing NSE's `"DD-Mon-YYYY"` strings lexicographically), and
  `attachment_url` (`attchmntFile`, clickable) columns to the activity
  table, plus a sentiment filter dropdown. `ts_utc` (processed time) and
  `an_dt` (announced time) now render through one shared 24-hour-clock
  formatter on the frontend instead of two different formats.

- **Symbol-wise P&L panel (2026-08-15):** ported `Kite_API_31.py`'s
  `get_open_position_count()` — the function behind the GUI's "Total
  Profit" column — as a new read-only `GET /announcement-trading/positions`
  endpoint + `PositionsPanel.tsx` on the Announcement Trading page.
  `kite.positions()` per account in the shared session, same P&L formula
  as the original: `(last_price - average_price) * quantity` for open
  positions (refreshing `last_price` via a live quote first), Kite's own
  `pnl` field kept as-is for already-squared-off (quantity == 0) legs.
  **Deliberately does not reproduce a real bug found while tracing the
  original:** `get_open_position_count()` returns a single DataFrame on
  its success path, but every caller unpacks it as two values
  (`all_positions, open_positions_df = get_open_position_count(kite)`),
  which raises `ValueError: too many values to unpack` on any real
  position data and gets silently caught by the caller's own `except` —
  meaning the original's "Total Profit" column likely never actually
  worked. The P&L formula and `kite.positions()` call are faithfully
  ported; only the return shape was made internally consistent.

- **Equity auto-trading integration (2026-08-15):** wrapped
  `new_trade_tool/scanner.py`'s real scan+execute loop (short-only AFL
  strategy, `LiveExitManager` trailing-stop/time-exit, `execution.py`
  marketable-LIMIT orders) as a new `equity_auto_trading` module —
  start/stop-able background thread, runs independently of the
  Announcement auto-loop (separate thread, separate start/stop). The one
  deliberate change, per explicit instruction: reuses the Announcement
  Trading page's shared Kite session (`session.get_kite_instances()`)
  instead of `scanner.py`'s own separate `auth.py`/`access_token_cache.json`
  login. `new_trade_tool/collector.py` must still run independently to
  keep `marketdata.db`'s candles flowing — this loop only reads that DB
  and places orders, never subscribes to ticks itself, same as the
  original. `PAPER_TRADING` is read from `new_trade_tool/config.py`
  unmodified (currently `False` — LIVE); the UI shows `mode` plainly.
  User started it live during testing; 0 orders placed, 0 open positions
  at last check.

- **Historical Extractor (Module D) shared session + CSV upload
  (2026-08-15):** turned out Module D already had almost everything asked
  for -- NSE/BSE choice, minute-level interval, and `merge_and_save()`
  (from `zerodha_scrape_core.py`, imported into `zerodha_api_core.py`)
  already unconditionally dedupes on `[symbol, Date, Time]` on every save
  regardless of the incremental flag, so "always append, no duplicates"
  was already true structurally. Two real gaps: (1) it used its own
  separate `KITE_API_KEY`/`SECRET` OAuth login
  (`zerodha_api_core.load_cached_session()`), not the shared session --
  `service.get_kite()` now returns
  `announcement_trading.session.get_kite_instances()[0][0]` instead, same
  pattern as `equity_auto_trading`; `login_url()`/`complete_login()` left
  in place but unused, not deleted. (2) symbols were paste-only, no CSV
  file input -- added client-side CSV parsing (`parseSymbolsCsv()`,
  matching `load_symbols_from_file()`'s own column-detection rule:
  `tradingsymbol`/`symbol` column if present, else first column) feeding
  the same existing symbol-list submission path; no backend upload
  endpoint needed. Verified both `auth_status()` and `get_kite()` directly
  against the live shared session before deploying.
  Confirmed the other tool referenced ("announcement data extractor")
  is the Announcement Trading module itself, which already uses the
  shared session throughout (`market_data.py`'s `_first_kite()`,
  `execution.py` receiving `kite_instances` injected from
  `session.get_kite_instances()`) -- no change needed there.

- **Historical Extractor: added an optional download-path input**
  (2026-08-16) -- `JobCreateRequest.output_dir`, created if missing, job
  fails cleanly with a clear error if the path can't be created, defaults
  to `aitrade/data/historical` when left blank. Shown on the job progress
  view. Verified with a real (read-only) test job.

- **Real timezone bug found and fixed in `zerodha_api_core.py`
  (2026-08-16):** user reported downloaded minute candles timestamped
  03:45-09:59 instead of the actual 09:15-15:30 IST market hours -- a
  suspiciously exact -5:30 shift. Root cause, in
  `fetch_symbol_history_for_ranges()`:
  `pd.to_datetime(part["date"], utc=True).dt.tz_localize(None)`.
  `kite.historical_data()` already returns each candle's timestamp with
  IST's `+05:30` offset baked in; `utc=True` was converting those to UTC
  (shifting every candle back 5:30) *before* `tz_localize(None)` stripped
  the timezone marker, silently mislabeling the UTC-shifted time as if it
  were still IST -- a 09:15 IST candle came out stamped 03:45. Fixed by
  dropping `utc=True` (parses preserving the original +05:30 offset;
  `tz_localize(None)` then only drops the marker, keeping the correct
  wall-clock value). Verified directly: reproduced the exact 03:45 with
  the old code, confirmed 09:15 with the fix, using a synthetic
  Kite-shaped tz-aware datetime for market open. This is a genuine bug in
  the legacy file itself (edited in place, not a porting deviation) --
  `zerodha_scrape_core.py`'s equivalent path never had it (`utc=True` was
  never passed there). **Any minute/intraday CSVs downloaded through
  Module D before this fix have the wrong (shifted) times baked in and
  should be re-downloaded** -- day-interval data is unaffected (only the
  date matters there, and the shift doesn't cross a day boundary for
  market-hours timestamps).

- **"Ends at 3:14 PM instead of 3:30 PM" -- root-caused, NOT a bug in our
  code (2026-08-16):** user pushed back hard on an earlier "Kite API
  limitation" claim, pointing at manual Zerodha-UI observation (correct
  15:29 last candle) and at a personal Jupyter notebook
  (`Historical_data_download.ipynb`) that had apparently downloaded full
  days before. Investigated the notebook first: neither of its two
  captured cell runs (official `kite.historical_data()` w/ `oi=True` +
  datetime objects, and the unofficial scrape endpoint) actually
  succeeded in their saved output -- one was interrupted at the login
  prompt before any fetch, the other 403'd on every symbol (different,
  unrelated `user_id=XE4670`). But real CSVs already sitting on disk from
  past successful runs (`.../PythonExperient/intrday_day_data/*.csv`)
  proved a full day *had* been downloaded before: `360ONE.csv` has a
  clean 09:15:00-15:29:00 run for 2026-02-20.
  Ran a live A/B/C/D test against the same shared Kite session, isolating
  every difference between the notebook's successful call and our
  code's (datetime objects vs pre-formatted strings, `oi=True` vs
  unset) -- all four variants returned an identical 360 candles cut off
  at 15:14 for 2026-08-14. Neither factor was the cause.
  Then tested the same symbol across a range of calendar days instead:
  clean split at the July/August boundary -- every trading day from
  2026-08-03 through 2026-08-14 (today's live query) returns exactly 360
  candles (09:15-15:14), while every day on or before 2026-07-31 returns
  the full 375 (09:15-15:29), including 2026-07-17, which is the exact
  date the user originally pasted truncated data for and which *now*
  comes back complete.
  **Conclusion: Kite's official historical-data warehouse has a backfill
  lag of roughly 2-3 weeks for intraday minute candles.** The most recent
  trading days are provisionally missing their last ~15 minutes of
  candles when queried too soon after the fact; Kite fills them in later.
  This explains every observation: our downloads of recent days were
  genuinely (if temporarily) incomplete; the live Zerodha UI is
  unaffected because it isn't reading from this same historical
  warehouse; and the user's own notebook run from February looked
  complete because months had passed since. Not a porting bug, not
  something fixable client-side -- Kite's own data isn't final yet at
  fetch time for very recent days. Practical mitigation for Module D:
  re-running an incremental download after a few weeks will pick up the
  now-backfilled candles for any previously "short" recent day, since
  `existing_coverage()` + `compute_missing_ranges()` only skip days
  that are *already* present, and a short day still gets its Date logged
  as covered -- so a true incremental re-fetch won't currently detect a
  short day as incomplete and re-pull it. Flagged to the user as a real
  gap worth a following change (detect and re-pull partial-day coverage,
  not just missing days) if this matters for their use case, rather than
  silently changed.

- **Short-day re-fetch + a second real bug found while testing it
  (2026-08-16):** implemented the mitigation from the entry above --
  `zerodha_scrape_core.find_short_recent_days()` checks the last 25
  days of an already-downloaded symbol's CSV and flags any day whose
  last saved candle falls short of the interval's expected
  session-close candle (with a small tolerance so genuine half-day
  sessions aren't misflagged); wired into both `download_symbol()`
  implementations (`zerodha_scrape_core.py`'s own, and
  `zerodha_api_core.py`'s, which is the one the live platform actually
  calls) so an incremental re-run folds any short recent day back into
  the fetch range alongside genuinely missing dates. Bounded to 25 days
  so a real short session (e.g. Muhurat trading) only gets harmlessly
  re-checked for a few weeks, then ages out and is left alone.
  While building an end-to-end test for this (seed a CSV with an
  artificially short day, run `download_symbol()`, confirm it comes
  back complete), found a second, independent, pre-existing bug in
  `merge_and_save()`: a freshly-fetched batch has real `datetime.time`
  objects in its `Time` column, but a batch just read back from an
  already-saved CSV has plain strings (CSV has no time dtype). Left
  unnormalized, concatenating the two produces a mixed-type column
  where e.g. `"09:15:00"` and `datetime.time(9, 15)` never compare
  equal, so `drop_duplicates()` silently missed every genuine duplicate
  on a date that already existed in the file -- directly breaking the
  user's original "no duplicates in the file" requirement for any
  incremental run that overlapped an already-saved date (which is
  exactly what the short-day fix above does on purpose). Reproduced in
  isolation (dtype mismatch confirmed, `duplicated()` returning
  `False` where it should return `True`), fixed by normalizing `Time`
  the same way `Date` already was
  (`pd.to_datetime(combined["Time"].astype(str), format="%H:%M:%S").dt.time`)
  before the dedup call. Verified both fixes together end-to-end
  against the live shared session: seeded a real symbol's CSV with an
  artificially short day, ran the real `download_symbol()`, confirmed
  it detected the short day, re-fetched it, and the file ended up with
  exactly 375 candles (09:15-15:29) and zero duplicate rows.

- **News Extractor (new module) -- historical NSE/BSE announcement
  download + sentiment/BERT classification (2026-08-16):** modeled on
  `nse_bse_extraction_tool.py`, a 1,528-line PySide6 desktop app
  ("Trading Data Analyzer") found in `Trading_bot/`. Per explicit
  instruction this is a **separate, from-scratch file**
  (`Trading_bot/nse_bse_tool_extraction.py`), not an edit to or import of
  the existing one -- that file can't be safely imported as a library: it
  unconditionally runs a live Zerodha login (Selenium + TOTP, writing
  fresh request tokens back to `Zerodha_Orders.xlsx`) at module scope just
  from being imported, and importing it at all requires `swifter` and
  PySide6 installed, neither needed here. It is untouched.
  Two things were found and disclosed before building: (1) the
  module-level auto-login described above; (2) the tool's `pred_bertv0.4`
  column, despite its name, was never real BERT -- `main()` calls its
  sklearn/TF-IDF `predict_category()` twice (once for `preds`/"category",
  again in a thread pool for `pred_bertv0.4`), while the file's own real
  `bert_predictor()`/`Bert_classification()` (a genuine
  `BertForSequenceClassification` load) is defined but never called.
  Asked how to handle this; told to match `Kite_API_31.py`'s BERT logic
  instead. Read that file: its live category classification
  (`calculate_row_values_in_parallel()`, `check_category_again_from_pdf()`)
  calls `predict_with_onnx()` from `onnx_bert.py` (an ONNX-accelerated
  real BERT model, `dev/Model_BERT/v0.4/onnx/bert_model.onnx`, verified
  present on disk, 438MB) -- not the pytorch `Bert_classification` either
  (also imported but unused there). Sentiment (`analyseText`/`cleanText`/
  `redact_with_spacy`, same `model/sentiment/svm.pickle` +
  `vectorizer.pickle`) is identical between both source files and ported
  as-is, including a quirky retry-order detail kept deliberately unfixed
  (see `analyse_sentiment()`'s docstring: on a non-positive first pass it
  cleans the raw text *then* redacts ORGs from the already-cleaned text,
  backwards from what would help spaCy's NER -- exactly what both source
  files do).
  The new file's `run_extraction()` therefore computes a single, real,
  BERT-backed `category` column (not two columns that were supposed to be
  different models but, in the original, silently computed the same one
  twice) -- disclosed to the user as an intentional UI deviation from strict
  1:1 column-for-column fidelity, everything else (BSE pagination, NSE
  date-range query, the BSE<->Zerodha symbol merge, the two market/sentiment
  filters, the 10-minutes-after-announcement price-reaction formulas)
  ported faithfully. BSE symbol mapping uses
  `reference_data.symbol_list()` (the platform's one already-maintained
  SCRIP_CD->SYMBOL map) instead of the original's separate, static
  `instruments(14).csv`, to avoid a second copy of the same data going
  stale independently. `append_bonus_buyback()` (writes to
  `inputs/bonus_buy_back.csv`, the schema `Kite_API_31.py`'s live trading
  GUI reads via `check_symbol_and_pred_bert_existence()` -- distinct from
  the newer `inputs/bonus_buyback.csv` the announcement-trading auto-loop
  uses) is kept as an explicit, separately-called opt-in step, never
  invoked automatically, since it writes to a file another live tool
  depends on.
  Backend: `app/modules/news_extractor/` -- same shared Kite session
  (`announcement_trading.session.get_kite_instances()`) and the same
  already-proven NSE cookie handling (`announcement_trading.market_data`)
  as every other module; async job pattern copied from Module D's
  `jobs.py` (`POST /jobs` returns immediately, `GET /jobs/{id}` polled by
  the frontend) since a full run -- BSE pagination across the date range,
  one NSE call, a Kite historical-data call per surviving row, then BERT
  inference per row -- comfortably exceeds the frontend's 20s request
  timeout.
  Frontend: `modules/news_extractor/` -- deliberately kept the original
  desktop app's own light-gray/blue palette (`#ecf0f1`/`#3498db`, 8px
  rounded corners) scoped to this page only, rather than the rest of
  aitrade's dark/yellow theme, since "exact UI" was the explicit ask.
  Dropped the "Script Folder Path" field (meaningless server-side -- the
  backend already knows where `Trading_bot/` is) and the "Close" button
  (a desktop-window concept); kept Start/End Date, all three checkboxes
  (Remove Negative Sentiment / Remove After Market / Run Zerodha Analysis,
  same defaults, all checked), Run Analysis / Refresh Table, the progress
  bar, the timestamped log panel, the status line, and the results table.
  Verified end-to-end against live BSE/NSE/Kite data through the actual
  FastAPI router layer (not just the pipeline functions directly): a real
  day's run returned 5,049 merged BSE+NSE rows, 102 after the sentiment
  filter, 17 after the market-hours filter, 7 after the symbol-exists
  filter, each with real Kite price-reaction numbers and real BERT
  categories (`approval`, `LOA`, `new order`, `partnership`, `mou`) --
  genuinely different classifications per announcement, not the
  ever-present-in-`nse_bse_extraction_tool.py` "same value twice" bug.

- **Bonus/Buyback Download (new module) + a real cache-staleness bug found
  while verifying the exclusion gate (2026-08-16):** user asked for
  Kite_API_31.py's "Get Bonus/Buy Back Data" feature as its own page, and
  to verify the exclusion logic it feeds (so already-seen bonus/buyback
  news doesn't trigger a repeat order) actually works.
  Traced the real call chain first: Kite_API_31.py's button calls
  `run_main_with_bonus_append()` from **`bonus_buyback_extract.py`** --
  confirmed via `from bonus_buyback_extract import run_main_with_bonus_append`
  -- not the near-identical copy of that function embedded in
  `nse_bse_extraction_tool.py` (used as the model for News Extractor's own
  `append_bonus_buyback()`, added 2026-08-16 earlier the same day). This
  mattered: `bonus_buyback_extract.py` writes to
  **`inputs/bonus_buyback.csv`** (no underscore), while
  `nse_bse_extraction_tool.py`'s copy writes to the separate, unrelated
  `inputs/bonus_buy_back.csv` (underscore) -- and `bonus_buyback.csv` (no
  underscore) is the exact file `Kite_API_31.py`'s
  `check_symbol_and_pred_bert_existence()` reads, and the exact file the
  already-ported `announcement_trading.gates.already_processed()` /
  `reference_data.bonus_buyback_list()` already read too. News Extractor's
  `append_bonus_buyback()` (in `Trading_bot/nse_bse_tool_extraction.py`,
  shared by both new pages) was pointed at the wrong file -- fixed to
  target `bonus_buyback.csv`, matching the authoritative source.
  Confirmed `bonus_buyback_extract.py`'s `main()` already calls
  `predict_with_onnx` (real BERT) for category, not the sklearn stand-in
  (that call is commented out there) -- same conclusion independently
  reached for News Extractor, now doubly confirmed against the actual
  live source.
  New page: `app/modules/bonus_buyback/` -- same `run_extraction()` +
  `append_bonus_buyback()` from `nse_bse_tool_extraction.py`
  (`compute_price_reaction=False`, not needed for a corporate-action
  catalog), run as its main action (fetch -> classify -> append is one
  button, matching the original's own behavior -- not opt-in the way
  News Extractor's bonus-append button is, since here that append *is*
  the tool's whole purpose). Also shows the current
  `bonus_buyback.csv` contents directly so the exclusion list itself is
  visible, not just inferred.
  While verifying the gate end-to-end (not just each half in isolation):
  ran a real 7-day extraction, got a genuine new `bo_stock_split` row
  (BANSALWIRE) appended to `bonus_buyback.csv`, then called
  `gates.already_processed()` directly -- **it returned False**, i.e. the
  row that had just been written was invisible to the live gate.
  Root cause: `reference_data.bonus_buyback_list()` loads the CSV once and
  caches it in memory for the life of the process, same pattern as this
  module's other reference tables (which is fine for those -- they're
  genuinely static). But this file is no longer read-only: the new Bonus/
  Buyback Download page writes to it from the *same* long-lived backend
  process the auto-loop's gate runs in, so the cache goes stale the
  instant a new row is appended and stays stale until a process restart
  -- silently letting through orders for symbols that should now be
  excluded. Fixed by re-reading the file whenever its mtime changes
  (`bonus_buyback_list()` now stats the file on every call -- cheap --
  instead of caching forever); the other reference tables are left as
  plain load-once caches since nothing writes to them at runtime.
  Verified the fix directly: appended a row to the CSV from outside the
  cached function, confirmed the very next call picked it up without a
  restart; then re-ran `gates.already_processed('BANSALWIRE',
  'bo_stock_split')` against the real row appended earlier and got
  `True`, with an unrelated symbol correctly still returning `False`.
  This is the kind of gap "check if the logic is working" was specifically
  asking about -- both halves worked correctly in isolation; only the
  interaction between two features running in the same process, verified
  together rather than separately, exposed it.
- **`new_trade_tool` collector/WS resilience fixes (2026-08-17):** two
  gaps found while diagnosing "equity trading generated only one alert
  since market open" traced back to real, recurring gaps in
  `marketdata.db` (confirmed via MMTC/PRESTIGE: clusters of 4-5
  consecutive near-zero-volume candles, ~73% of symbols unaffected in the
  same windows -- ruled out a full WS outage). Root cause: `ws_runner.py`
  sent `subscribe()`/`set_mode()` as one 534-token batch, silently
  dropping a subset; and a mid-session gap, once it happened, was never
  self-healed (`backfill()` only ran once at startup). Fixed both:
  `ws_runner.py` now chunks subscribe/set_mode (`SUBSCRIBE_CHUNK_SIZE=150`,
  0.25s between chunks) and `run_forever()`'s `on_noreconnect` now
  actually rebuilds the connection instead of returning and idling
  forever; `collector.py` gained `periodic_backfill_loop()` re-running
  `backfill()` every 20 min during market hours. Verified live: "WS
  subscribed 512 tokens in 4 chunks of <=150", 170-190 ticks/sec
  sustained, zero lock errors.
- **`db.py` missing `busy_timeout` (2026-08-17):** found while restarting
  `collector.py` -- the startup backfill (single-threaded, single
  connection, no internal race) still failed "database is locked" on
  nearly every symbol. Root cause turned out to be a second process:
  `equity_trading/service.py` and `equity_auto_trading/scanner_loop.py`
  both read/write this *exact* `new_trade_tool/marketdata.db` file (not a
  separate copy), and aitrade's Equity Auto Trading loop cycles every
  1-2s, winning most write races against `collector.py`'s slower,
  sequential catch-up. `db_connect()` had no `PRAGMA busy_timeout`, so any
  collision failed instantly instead of waiting briefly. Added
  `busy_timeout=5000`. Doesn't eliminate contention when both sides write
  at similar frequency, but turns instant failures into short waits;
  non-fatal either way since `collector.py`'s startup backfill already
  tolerates per-symbol failures and self-heals via the periodic-backfill
  fix above.
- **Shared Kite session for `new_trade_tool`'s standalone scripts
  (2026-08-17):** user wanted to run `new_trade_tool/main.py` (the
  monolithic collector+strategy+execution script, live order placement
  on) standalone in parallel with aitrade's own Equity Auto Trading, to
  compare signal generation -- explicitly approved running both live,
  same account ("I don't have money in account"). Running `main.py`'s own
  `auto_login()` (independent Selenium+TOTP login) risked invalidating
  aitrade's already-active session, since Kite generally allows one active
  access token per API key. Added `auth.load_shared_platform_session()`
  -- reads `Trading_bot/kite_instances.pkl` directly (same file
  `announcement_trading.session.get_kite_instances()` reads), returns
  `(kite, access_token)` matching `auto_login()`'s signature. Wired into
  both `main.py` and `collector.py`'s entry points. Running
  `collector.py` and `main.py` together is redundant (`main.py` already
  does its own WS collection + backfill on top of strategy/execution), so
  `collector.py` was stopped once `main.py` was confirmed running instead.
- **Announcement Trading orders silently failing all day (2026-08-17):**
  user reported "No order placed why?" for an announcement whose
  `activity_log` row showed `skipped=0` (passed every gate) but
  `order_placed=0` -- not a gating bug. Backend log showed the real cause:
  `execution.py`'s `place_orders()` (faithful port of `Kite_API_31.py`)
  calls `kite.place_order(..., market_protection=-1.0)`, but the
  installed `kiteconnect==5.0.1` had dropped `market_protection` from
  `place_order()`'s signature entirely -- every single order attempt that
  day failed with `TypeError: unexpected keyword argument
  'market_protection'`, caught and logged, so the pipeline believed it
  had "tried." Confirmed `market_protection` is required, not optional --
  Zerodha rejects plain MARKET orders via the API without it (already
  documented in `new_trade_tool/execution.py`'s own comment, which is why
  Equity Trading's orders use a marketable LIMIT-order workaround
  instead). Root cause fixed at the actual source instead of working
  around it in this file: `kiteconnect` upgraded 5.0.1 -> 5.2.1 (confirmed
  via the downloaded wheel's source that 5.2.1's `place_order()` restores
  `market_protection`, same `-1`-means-automatic-protection semantics) --
  `execution.py` needed no behavior change, matching the original port
  exactly. Verified end-to-end with a real 1-share live order (user-run,
  not run by the assistant -- placing trades directly is out of scope
  regardless of authorization) via a small standalone script,
  `new_trade_tool/test_order_placement.py`; order placed successfully.
- **`LiveExitManager` position tracking is in-memory-only (2026-08-17):**
  found while restarting the aitrade backend for the fix above --
  discovered `equity_auto_trading/scanner_loop.py`'s `exit_mgr.pos` (the
  trailing-stop state for open shorts) is a plain in-process dict, never
  persisted, and unlike Announcement Trading's entries, equity positions
  get no broker-side GTT bracket either. A backend restart with a real
  open position (PDSL, short 1, MIS) left it open at Zerodha but with zero
  active stop-loss management until MIS auto-square-off near close --
  user accepted this once ("Restart now as-is", stakes were ~Rs 370) but
  asked for the underlying gap fixed. Added
  `LiveExitManager.reconcile_open_positions(exchange, symbols)`: seeds
  `self.pos` from `kite.positions()` on startup, restricted to
  short/negative-quantity positions matching this manager's own
  product/exchange and the equity watchlist -- a position opened by
  another tool/strategy on the same shared account (e.g. `main.py`,
  running in parallel per the entry above) is deliberately left
  untouched, not swept in. Wired into both `scanner_loop.py` and
  `main.py` (both create their own `LiveExitManager`), gated on `not
  PAPER_TRADING`. Verified via a mocked-`kite.positions()` unit test
  (PDSL itself was already flat again by restart time, so nothing live to
  reconcile against) -- confirmed it seeds the matching short correctly
  and skips wrong-watchlist, wrong-product, and long positions.
- **`strategies.py` `Ref(Short_condition,-1)` shift applied then reverted
  (2026-08-17):** in response to "Equity trading seems to be not firing
  orders sine morning only one order" (one signal all day, PDSL at
  11:15), applied a fix diagnosed earlier the same session but never
  confirmed: AmiBroker's AFL computes `Short_raw = Ref(Short_condition,-1)
  AND ...` (previous-bar lag), but the ported code evaluated
  `Short_condition` unshifted -- confirmed via an 18-symbol entry-timing
  comparison against real AmiBroker output. Applied the shift
  (`d.groupby("date")["Short_condition"].shift(1)`) at all three
  `Short_raw` call sites, including the one `scanner.py`'s live path
  uses, restarted both `main.py` and the aitrade backend (no open
  equity-side positions on either restart, so nothing at risk). **User
  reverted this immediately: "i didn't want the signal shift fix. it was
  working fine."** Reverted all three sites back to the unshifted
  version exactly as they were (the shifted version is AFL-literal and
  well-evidenced by the AmiBroker comparison, but the user's live
  experience overrides that -- do not reapply without asking again). The
  `vwap_start` default fix (91500 -> 93000, applied in the same pass) was
  *not* called out as unwanted and was left in place.
- **Announcement Trading exit rules were never ported at all (2026-08-17):**
  user reported "exit rules are not getting forced." Traced to a whole
  missing subsystem, not a bug in an existing one: `auto_loop.py`
  (replacing `Kite_API_31.py`'s `the_thread()/job()`) only ever calls
  `pipeline.process_item()` -- the entry side (gates -> place order -> one
  static GTT OCO bracket). The original's `remove_orders()` and
  `remove_orders_before_mkt_close()` (submitted via `ThreadPoolExecutor`
  every job() tick whenever `num_open_positions > 0`) manage the position
  from there on: a trailing stop-loss that only ever tightens
  (`modify_gtt`, allowance narrowing from +0.4% in the first 2 min to
  `stop_pct - 0.2%` past 4 min via `calculate_factor()`), three forced-exit
  triggers (red P&L held >2min, hard 10-min time-stop regardless of P&L,
  P&L% < -1%), a 15:28-15:30 EOD forced-exit window, a re-place-if-
  triggered-but-still-open safety net, and a separate unconditional EOD
  square-off. None of this existed in the port -- a position got its
  static bracket at entry and was never revisited.
  Ported faithfully as `exit_management.py` (`run_cycle()`, called from
  `auto_loop.py`'s existing poll loop, gated per-account on
  `kite.positions()` actually returning something open). Needed the
  original's `stoploss_df_temp` (in-memory high-price-since-entry tracker,
  keyed here by `(zerodha_id, symbol)`, same restart-loses-the-ratchet
  characteristic as the original -- the broker-side GTT itself is
  unaffected, only how much tighter to trail it from here is reset) and a
  way to recover each position's original stop_loss_pct/absolute
  stop-target prices and per-account `gtt_trigger_id` -- added two new
  `trade_entries` columns (`stop_loss_price`, `target_price`; the
  pre-existing `stop_loss_pct`/`target_pct` were declared but never
  actually populated by the auto-loop's entry-creation call, only by the
  separate manual-draft flow in `router.py` -- fixed to populate all four,
  back-derived from `result.trigger_price`/`target_price` at creation
  time) and read the existing `order_result` JSON (already has
  `gtt_trigger_id` per account from `execution.place_orders_parallel()`)
  instead of adding new tracking for that.
  Verified with a dry run first: `_manage_position()` called directly
  against ASALCBR's real open position (from an earlier live order this
  same session) with a mocked `kite` that only records calls -- correctly
  decided a forced exit (already past the 10-min time-stop) and produced
  the exact `place_order` payload expected, no exceptions. User confirmed
  going live knowing this would immediately fire for real. It did,
  correctly, on the first cycle after restart: forced-exit LIMIT SELL
  placed for ASALCBR (held 38.8 min), then the GTT trailed on the next
  cycle since the SELL was still `OPEN` (not yet filled) -- confirmed this
  matches the original's own behavior (it doesn't gate the trailing step
  on a pending exit order either, so this isn't a new bug introduced by
  the port).
- **Navigation/UI redesign, Phase 1 (2026-08-17):** user asked for a PM-style
  UX audit + redesign proposal, not immediate code changes -- built and
  published a proposal artifact (nav IA diagram, working sidebar/dashboard
  mockup, visual token system, 3-phase rollout) before touching any code,
  per "first suggest the changes." User approved: sidebar nav, start
  Phase 1. Phase 1 scope (low risk -- purely additive, no existing page's
  internals touched): `shared/theme.css` (design tokens: ink/accent/live/
  paper/stopped/danger, light+dark), `shared/StatusBadge.tsx`,
  `shared/useTradingStatus.ts` (thin hooks over the existing
  `/announcement-trading/auto/status`, `/announcement-trading/positions`,
  `/equity-auto-trading/status`, `/equity-auto-trading/signals`
  endpoints -- no new backend work), `shared/Sidebar.tsx` (replaces the
  flat topbar with Trading/Tools grouping + live status dots per item),
  and `modules/dashboard/DashboardPage.tsx` (replaces the old home page's
  bare link list with a risk strip -- loops running, open positions,
  today's P&L, errors -- plus per-module status cards). `App.tsx`/`App.css`
  updated for the new sidebar-grid shell; every existing `<Route>` and
  module page left untouched. Verified: `tsc -b --noEmit` and
  `npm run build` both clean, then visually confirmed in-browser (Dashboard,
  Equity Trading, Announcement Trading all render correctly with real
  live data -- the "Window 1/Window 2" legacy naming on Announcement
  Trading is still there as expected, since renaming/restructuring
  individual pages is Phase 2, not started).
- **Navigation/UI redesign, Phase 2 (2026-08-17):** restructured the two
  live-trading pages per the approved proposal.
  Announcement Trading (`AnnouncementTradingPage.tsx`): reordered to
  Status & Control -> Positions & P&L -> Session & Settings (unchanged
  `TradingSettingsPanel`, already collapsed by default), dropped the
  legacy "Window 1"/"Window 2" labels from the PySimpleGUI desktop app.
  Equity Trading (`EquityTradingPage.tsx`): split into two tabs -- Live
  Auto-Trading (control + signals + a **new** Positions & P&L panel) and
  Symbol Explorer (the existing chart/signal-marker/symbol-picker view,
  unchanged). Both tab contents stay mounted and are toggled via CSS
  `display`, not conditional rendering, so the chart's one-time
  lightweight-charts setup effect never has to re-run on tab switch.
  The new equity positions panel needed a backend addition -- Equity Auto
  Trading's `/status` only ever exposed a bare `open_positions` count, no
  per-symbol detail (unlike Announcement Trading's own
  `/announcement-trading/positions`). Added
  `GET /equity-auto-trading/positions` (`equity_auto_trading/router.py` +
  `schemas.py`): reads `kite.positions()` directly across the shared
  session's accounts, filtered the same way
  `LiveExitManager.reconcile_open_positions()` already decides what it's
  willing to manage (this strategy's own product from `new_trade_tool/
  config.py`, short/quantity<0 only) -- deliberately *not* filtered to the
  current watchlist like the reconciler is, so a position that fell off
  the watchlist between restarts still shows up here instead of being
  silently hidden.
  Found and fixed a real, pre-existing, unrelated bug while verifying this
  in-browser: `GET /equity/status` 500'd with `UnicodeEncodeError`.
  `new_trade_tool/common.py`'s `log()` does a plain `print()` including
  emoji ("✅ Loaded ... symbols"); when the aitrade backend's stdout is
  redirected to a file (true for every backgrounded run this session) and
  not reconfigured, Windows Python defaults to cp1252 instead of UTF-8 and
  raises on the first such call. `new_trade_tool/main.py` already carries
  this exact fix at its own entry point; added the same
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (+ stderr)
  to `aitrade/backend/app/main.py`'s top, since it's a separate process/
  entry point that never had it.
  Verified: `tsc -b`/`npm run build` clean; live in-browser via
  `get_page_text` (screenshot capture was unreliable against the
  canvas-based candlestick chart specifically -- a CDP/tooling quirk, not
  an app bug, confirmed by the page rendering correctly both ways) --
  Announcement Trading's new section order and Equity Trading's tab split
  (including the new, correctly-empty positions panel) both confirmed
  working with real backend data.
- **Navigation/UI redesign, Phase 3 (2026-08-17):** consolidated the
  duplicated CSS the earlier phases left behind and finished the shared
  component migration.
  New `shared/components.css` (imported once in `App.tsx`, alongside
  `theme.css`): spinner, `.status-line`, `.table-scroll`, `.banner*`,
  `.positions-panel`/`.pnl-*`, `.control-panel`, `.start-button`/
  `.stop-button`, `.session-pill`, and the base `.activity-table`/
  `.entries-table`/`.signals-table` styling -- all previously copy-pasted
  near-verbatim between `trading.css` and `equity.css` (and partly
  reinvented in `historical.css`), now defined once on the token set.
  Each module's own CSS file kept only what's genuinely page-specific.
  `.loop-pill`/`.mode-pill` (trading.css/equity.css) retired entirely in
  favor of the shared `StatusBadge` component from Phase 1 -- these were
  literally reimplementing the same live/paper/stopped concept with their
  own hardcoded colors; `AutoLoopControl.tsx` and
  `EquityAutoLoopControl.tsx` now render `<StatusBadge>` instead. Also
  fixed `AutoLoopControl.tsx`'s `ConnectionDot` (BSE/NSE indicator) to use
  `var(--live)`/`var(--danger)`/`var(--stopped)` instead of its own
  separate hardcoded hex triplet.
  Full token migration (hardcoded hex -> `var(--token)`) on
  `trading.css`, `equity.css`, `historical.css`, `bonus_buyback.css` --
  all four already shared the same literal palette (`#12121c` ink,
  `#ffe600` legacy yellow brand -> now `var(--accent)`, `#1a7f37`/
  `#b3261e`/`#8a6d00` success/danger/warning, etc.), so this was a
  mechanical, low-risk substitution. `news_extractor.css` got a lighter
  touch -- only its two semantic status colors (success/danger) moved to
  tokens; its own distinct "flat UI" palette (blue/navy/grey, unrelated to
  the rest of the app) was left alone rather than forcing an unrelated
  page's visual identity into this pass without a closer audit.
  Verified: `tsc -b`/`npm run build` clean; visually confirmed in-browser
  (Dashboard, Announcement Trading, Equity Trading, Historical Data) --
  StatusBadge renders identically in the sidebar and inside each page's
  own control panel now (same component, same tokens), START/STOP buttons
  read as a more restrained green/red than the original bright
  `#22c55e`/`#ef4444`, consistent with the rest of the redesign's palette.
  This closes out all three phases of the nav/UI redesign proposed and
  approved earlier the same session.
- **Manual Trade Entry form was documented but never actually built
  (2026-08-17):** user asked why Announcement Trading's UI had no entry
  form (Order Variety, Order Type, Market type, GTT parameters, Amount).
  Not something removed during the nav redesign -- confirmed by grep that
  no `.tsx` component for it had ever existed, despite `docs/
  requirements.md` §6 Module B always documenting it ("the manual
  per-announcement flow, still available on the Announcements page"),
  the backend endpoints being fully built (`GET/POST
  /announcement-trading/entries`, `POST .../entries/{id}/place-order`),
  the `TradeEntryCreate`/`TradeEntry` types already in `types.ts`, and even
  `trading.css`'s `.trade-panel`/`.trade-form`/`.entries-table` classes
  already sitting there unused.
  Built `TradeEntryPanel.tsx`, reusing the exact same variety (regular/co/
  bo), order_type (MARKET/SL-M/LIMIT), and product_type (MTF/MIS/CNC)
  option sets `TradingSettingsPanel` already uses, for consistency. Two-
  step by design, matching the backend: `POST /entries` only ever saves a
  draft (Symbol, Exchange, Transaction, Amount-or-Quantity, optional
  per-trade GTT stop/target %, and optional variety/order_type/
  product_type overrides -- left blank, they fall back to Session &
  Settings' global values at place-order time, so the form defaults to
  "(Settings default)" rather than silently duplicating whatever the
  global settings currently are and drifting from them later). Placing an
  order is a separate, explicit button per draft row, gated behind
  `window.confirm(...)` naming the symbol/side and stating it's a real
  order -- same pattern as the existing "Generate Token" confirm.
  Wired into `AnnouncementTradingPage.tsx` between Positions & P&L and
  Session & Settings.
  Verified live: the panel correctly rendered *existing* real
  `trade_entries` rows (ASALCBR/THYROCARE placed by the auto-loop earlier
  the same session, an older manual test draft from 2026-08-14) with
  correct status-gated Place Order visibility (only on `status=draft`
  rows). Submitted one new draft (`TESTSYM`) through the new form and
  confirmed via the API it was created with exactly the submitted fields
  and all blank-left fields correctly `null` -- did not click Place Order
  on it or any other draft (that fires a real order; left for the user to
  test themselves). No DELETE endpoint exists for entries, so this test
  draft (id 4) stays in the table as a harmless, never-placed row.
- **Four trader's-eye-view fixes to Announcement Trading (2026-08-17):**
  asked to assess the page "as a trader who manages the algo platform" --
  four real problems identified and fixed the same session:
  1. *Activity feed defaulted to "All", burying signal in noise.* Most
     rows are routine `symbol_not_tradeable`/`neutral_or_other` filings
     that were never going to trade. Added a "Show" filter
     (`AutoLoopControl.tsx`) defaulting to "Orders placed" instead of
     "All" -- Skipped/All still one click away. Sentiment dropdown's
     per-option counts now reflect the current outcome filter, not the
     unfiltered set.
  2. *Manual Trade Entry (added earlier the same session) was permanently
     expanded, same visual weight as Positions.* It's an occasional
     override action, not checked every visit. `TradeEntryPanel.tsx` now
     uses the same `.collapse-toggle`/`.settings-body` pattern
     `TradingSettingsPanel` already had, collapsed by default, showing a
     "N draft pending" pill when relevant.
  3. *Positions & P&L mixed open and already-flat (qty=0) rows in one
     table* -- "what's open right now, at risk" had to be found by
     scanning a Qty column. Both `PositionsPanel.tsx` (announcement) and
     `EquityPositionsPanel.tsx` (equity) now split into "Open"/"Closed
     today" sub-tables, open first.
  4. *The Dashboard's risk strip (loops running/open positions/P&L/
     errors) didn't follow you off the Dashboard* -- scroll down on any
     other page and the top-level "is this live and what's it holding"
     view was gone. Extracted to `shared/RiskStrip.tsx`, moved its CSS to
     `shared/components.css`, and it now renders once from the app shell
     (`App.tsx`, above `<Routes>`) so it's visible on every page
     regardless of scroll position. Removed the now-duplicate inline copy
     from `DashboardPage.tsx`.
  Verified: `tsc -b`/`npm run build` clean; visually confirmed in-browser
  on both Announcement Trading and Equity Trading -- risk strip persists
  across pages, "Orders Placed (0)" default correctly shows the helpful
  empty-state message instead of 100+ noise rows, "New trade entry"
  toggle collapsed (▸) on load, Open/Closed sections rendering correctly
  with real data (0 open, 5 closed today on Announcement Trading at
  verification time).
- **Session creation was hidden inside collapsed Settings (2026-08-17):**
  user asked "where is the session creation???" -- traced to a real design
  mistake from Phase 2: "Generate Token" and session status had been left
  inside `TradingSettingsPanel`'s collapsed panel, alongside GTT %/amount/
  order-type fields that really are configure-once. A session isn't --
  Kite tokens expire daily, and nothing else on the page (START, positions,
  manual trade entry) works without one -- so burying it behind a
  collapsed toggle at the bottom of the page was wrong.
  Split into a new `SessionPanel.tsx`: connection badge, account list,
  and Generate Token (with its login-progress polling), moved out of
  `TradingSettingsPanel.tsx` entirely and given its own always-visible,
  uncollapsed "Kite Session" section -- now the *first* thing on the page,
  above Status & Control. `TradingSettingsPanel.tsx` keeps only the
  genuinely configure-once fields, still collapsed by default, renamed
  from "Session & Settings" to plain "Settings" now that Session has its
  own heading.
  Verified: `tsc -b`/`npm run build` clean; visually confirmed in-browser
  -- "Kite Session" now leads the page, showing "1 Kite account connected"
  and the Generate Token button immediately, no longer hidden behind a
  collapsed toggle.
- **Sections looked "merged" -- card-based visual segregation
  (2026-08-17):** user pointed out sections on Announcement Trading were
  separated only by an `<h2>`, no real visual boundary, so the whole page
  read as one continuous block rather than distinct sections -- asked for
  proper UI/UX practice here. Standard fix: bordered/shadowed card per
  section with a distinct header band, using tokens that already existed
  (`--surface`/`--border`/`--radius`/`--shadow`, the exact same ones
  Dashboard's own module cards already used) but had never been applied to
  page-level sections.
  Added `shared/Section.tsx` -- a card wrapper (title + optional
  `headerRight` + body) -- used for Kite Session, Status & Control, and
  Positions & P&L on both Announcement Trading and Equity Trading, and for
  Symbol Explorer's chart/signals sections. `TradeEntryPanel`/
  `TradingSettingsPanel` keep managing their own collapse (they need a
  live badge in the header, which would mean prop-drilling a query result
  up through the page to go through Section) -- but their existing
  `.trading-settings`/`.collapse-toggle`/`.settings-body` CSS (moved from
  `trading.css` to `shared/components.css`) was rewritten to match the
  identical card language, so every section reads as the same kind of
  thing regardless of which mechanism renders it.
  Verified: `tsc -b`/`npm run build` clean; visually confirmed in-browser
  on both pages -- Kite Session/Status & Control/Positions & P&L now each
  render as clearly bordered, shadowed, distinct cards instead of a wall
  of content divided only by heading text.
- **Failed trade entries showed no reason (2026-08-17):** user tested
  Manual Trade Entry's "Place Order" themselves (NMDC, qty 1) -- it
  failed, and the table just said "failed" with no way to see why short
  of reading backend logs. The real reason was already captured
  (`order_result` JSON on the entry, `{"results": [{"zerodha_id":...,
  "error":...}]}`) but never rendered. Added `orderErrors()` in
  `TradeEntryPanel.tsx` -- parses `order_result`, extracts each account's
  error, renders it directly under the "failed" status in the table
  (`.entry-error`, small red text). Verified live: the NMDC row now shows
  "NGQ901: Your order could not be converted to a After Market Order
  (AMO)." right in the table.
  Root cause of that specific failure, for context: it was 8:22 PM, well
  after NSE market hours (09:15-15:30 IST) -- outside those hours Zerodha
  requires AMO-eligible order construction, and `execution.py`'s plain
  MARKET order isn't one. This isn't a bug in the automatic loop (its own
  gate in `pipeline.py`, `MARKET_TRADE_START`/`MARKET_TRADE_END` =
  09:15-15:28, correctly blocks it from ever attempting an order outside
  that window) -- Manual Trade Entry has no equivalent gate, since placing
  a manual order after hours is a legitimate thing a user might
  deliberately want to do (e.g. queuing an AMO). Not fixed here; flagged
  as an open question, not silently patched, since the right fix (build
  proper AMO order construction, or warn-and-block instead) is a product
  decision, not just a bug fix.
- **"Orders placed" filter showed nothing despite real orders existing
  (2026-08-17):** user reported two real announcement orders (ASALCBR,
  THYROCARE, both placed earlier the same day) were missing from the
  activity feed's new "Orders placed" filter. Root cause: `GET /activity`
  always applied `LIMIT` to the *whole* `activity_log` table before any
  filtering -- confirmed live, only 2 of 912 total rows that day had
  `order_placed=1`, so on a day with this much routine/skipped traffic
  the handful of real orders scroll out of "the most recent 100 rows of
  everything" long before 100 more rows have been scanned since the last
  one. The earlier "defaults to Orders placed" fix (same session) had
  made this bug visible by making it the default view instead of an edge
  case nobody hit.
  Fixed at the source: `db.list_activity()` now takes an optional
  `order_placed` filter and applies `WHERE order_placed = ?` *before*
  `LIMIT`, not after; `GET /activity` exposes it as
  `?order_placed=true|false`. `AutoLoopControl.tsx`'s activity query now
  requests `order_placed=true` directly from the backend when that's the
  active filter, instead of fetching the general recent-100 window and
  filtering client-side. Also fixed the "Orders placed (N)" count itself,
  which had the identical bug one level up (computed from whatever the
  currently-active query returned, so it under-reported whenever a
  different filter was selected) -- added a small always-on dedicated
  count query so the badge is accurate regardless of which filter is
  showing.
  Verified live: `GET /activity?order_placed=true` now correctly returns
  both real orders (ids 454, 492) despite them being ~450 rows older than
  the most recent activity_log entry; confirmed in-browser -- "Orders
  placed (2)" now lists THYROCARE and ASALCBR with their real
  "ORDER PLACED (qty N)" outcomes.
