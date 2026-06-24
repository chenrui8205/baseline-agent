"""Baseline API + server-rendered UI. Single FastAPI service: clean JSON under
/api (the contract a future Next.js front-end would consume) plus server-rendered
pages so V0 ships a polished UI with zero Node toolchain."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import api, views

BASE = Path(__file__).resolve().parent

app = FastAPI(title="Baseline — Tennis Betting Intelligence", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.include_router(api.router)
app.include_router(views.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
