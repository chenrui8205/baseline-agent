# Baseline — Tennis Betting Intelligence

A **tennis-only** betting-intelligence app. You follow a list of matchups; for each, Baseline
produces a deep, *explained* analysis and surfaces what changed. It is a decision-support tool,
not an alpha engine — the edge is being **deeper on tennis than any generalist tool** (e.g.
ChatGPT) will bother to be, with structured facts a chatbot structurally can't reach.

> Why it beats a generalist agent: live odds it has no feed for, deterministic fatigue math it
> can't compute, an intel feed past its knowledge cutoff, and a memory of what changed.

## V0 scope (what's built vs. deferred)

**In V0:** Fatigue/Scheduling Engine · Cross-venue pricing (books + Polymarket) · Player-form
updates · Line-movement + "what changed" alerts · Factual intel feed (news/official only) ·
one LLM verdict.

**Deferred (clean migration paths kept):** social-media intel, motivation/retirement engines,
multilingual press at scale, CLV track record, LangGraph/Celery/Redis/pgvector/WebSockets.

### Build status

| # | Milestone | Status |
|---|-----------|--------|
| M0 | Scaffold + data model + seed (grass-season demo card) | ✅ |
| M1 | **Fatigue/Scheduling Engine** end-to-end + load gauges + tests | ✅ |
| M2 | Player form & surface splits | ▢ next |
| M3 | Cross-venue pricing: no-vig fair odds, edge %, edge meter | ▢ (raw prices already shown) |
| M4 | Line-movement poller + live "what changed" ticker (SSE) | ▢ (ticker is static for now) |
| M5 | Factual intel feed: live news/official extraction (Haiku) | ▢ (seeded press already shown) |
| M6 | `synthesize_verdict` (Opus) → BET/LEAN/PASS/WATCH + cited thesis | ▢ (placeholder block) |
| M7 | Polish: responsive, reduced-motion, age + responsible-gambling gate | ◑ gating done |

## Run

```bash
./run.sh                 # creates venv, seeds demo data, serves on :8099
```

Then open <http://127.0.0.1:8099>. Reseed / test any time:

```bash
PYTHONPATH=api .venv/bin/python -m app.seed
PYTHONPATH=api .venv/bin/python -m pytest api/tests -q
```

## Architecture

Single **FastAPI** service: clean JSON under `/api/*` (the contract a future Next.js front-end
would consume unchanged) **plus** server-rendered pages, so V0 ships a polished UI with no Node
toolchain. **SQLite** keeps it zero-infra; the ORM means Postgres later is a connection string.

```
api/app/
  engines/fatigue.py     deterministic load score (pure + unit-tested)  ← the signature
  sources/               polymarket / oddsapi (live, optional) + synthetic demo odds
  service.py             assembles the /analysis payload (brief §5 shape)
  routers/{api,views}.py JSON API + server-rendered pages
  templates/  static/    the analyst-terminal UI (Space Grotesk · Hanken · JetBrains Mono)
  seed.py                fictional grass-season card (no false claims about real players)
```

### Live data & cost

The demo runs fully on **seeded, fictional** players so nothing in the intel feed is a false
claim about a real athlete. The odds/intel **clients are written against real APIs** and light
up when keys are present — chosen to keep data costs ~zero:

- `ANTHROPIC_API_KEY` — verdict (Opus) + intel extraction (Haiku). Absent → graceful fallback.
- `THE_ODDS_API_KEY` — live book lines (free tier). Absent → realistic seeded lines.
- Polymarket (Gamma API) and news/official RSS + GDELT are **keyless/free**.

## Guardrails

CLV is the headline metric, never a win streak. No "lock"/"guaranteed" language. Every intel
claim is sourced + timestamped, low-confidence flagged *unconfirmed*, **no sentiment**.
Age/eligibility gate + responsible-gambling notice on every page.
