"""Server-rendered pages. Both read the same service layer as the JSON API."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, not_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Match, Subscription
from ..service import _header, analysis_payload, dashboard_data

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
USER = "demo"


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    now = get_settings().now
    data = dashboard_data(db, USER)
    subbed = select(Subscription.match_id).where(Subscription.user_id == USER)
    browse = db.execute(
        select(Match).where(and_(Match.status == "scheduled", not_(Match.id.in_(subbed))))
        .order_by(Match.scheduled_at)
    ).scalars().all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "data": data,
        "browse": [_header(m, now) for m in browse],
    })


@router.get("/matchup/{match_id}", response_class=HTMLResponse)
def matchup(match_id: int, request: Request, db: Session = Depends(get_db)):
    payload = analysis_payload(db, match_id)
    if payload is None:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse("matchup.html", {"request": request, "p": payload})
