#!/usr/bin/env bash
# Baseline — one-command dev runner.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "Creating venv + installing deps..."
  python3 -m venv .venv
  $PY -m pip install -q --upgrade pip
  $PY -m pip install -q -r api/requirements.txt
fi

# Seed the demo DB if it doesn't exist yet, then ingest one REAL live match
# (real Polymarket odds + GDELT news). Live ingest is best-effort (needs network).
if [ ! -f api/data/baseline.db ]; then
  echo "Seeding demo data..."
  PYTHONPATH=api $PY -m app.seed
  echo "Ingesting one live match (real Polymarket + news)..."
  PYTHONPATH=api $PY -m app.live || echo "  (live ingest skipped — offline or no market available)"
fi

echo "Baseline on http://127.0.0.1:8099  (Ctrl-C to stop)"
exec $PY -m uvicorn app.main:app --app-dir api --port 8099 --reload
