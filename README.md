# aitrade

A local, single-user trading platform: React + FastAPI unifying four
previously separate feature areas — corporate-announcement-driven trading,
indicator-based equity trading, a historical data extractor, and a corporate
announcements feed — built on top of existing Python trading scripts.

Full spec: [`docs/requirements.md`](docs/requirements.md) — the source of
truth for scope, architecture decisions, module boundaries, and the phased
delivery plan. Read it before working on anything in this repo.

## Status

Pre-build. No backend/frontend code yet — see the requirements doc's §7
phased plan for what's next (Phase 0: scaffold).

## Relationship to the legacy codebase

This repo does not contain the existing trading scripts it wraps. Those stay
in place at `D:\Trading System\Trading_bot` (a sibling directory, not a
subfolder of this repo) and are referenced by absolute path via a
`LEGACY_ROOT` config value once the backend exists — see `docs/requirements.md`
§4.
