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
