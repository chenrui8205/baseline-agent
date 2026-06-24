"""JSON API (brief 5). This is the stable contract; the HTML views read the same
service layer, so a Next.js front-end could later consume these endpoints unchanged."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, not_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Match, Subscription
from ..service import SURFACE_LABEL, _header, analysis_payload, dashboard_data

router = APIRouter(prefix="/api")
USER = "demo"  # single-user V0


class SubscribeBody(BaseModel):
    match_id: int


@router.get("/subscriptions")
def get_subscriptions(db: Session = Depends(get_db)) -> dict:
    return dashboard_data(db, USER)


@router.post("/subscriptions")
def subscribe(body: SubscribeBody, db: Session = Depends(get_db)) -> dict:
    if db.get(Match, body.match_id) is None:
        raise HTTPException(404, "match not found")
    exists = db.execute(select(Subscription).where(and_(
        Subscription.user_id == USER, Subscription.match_id == body.match_id))).scalar_one_or_none()
    if not exists:
        db.add(Subscription(user_id=USER, match_id=body.match_id, created_at=get_settings().now))
        db.commit()
    return {"ok": True, "match_id": body.match_id}


@router.delete("/subscriptions/{sub_id}")
def unsubscribe(sub_id: int, db: Session = Depends(get_db)) -> dict:
    sub = db.get(Subscription, sub_id)
    if sub and sub.user_id == USER:
        db.delete(sub)
        db.commit()
    return {"ok": True}


@router.get("/matchups")
def browse_matchups(db: Session = Depends(get_db)) -> dict:
    """Scheduled matches the user could add (the 'Add matchup' affordance)."""
    now = get_settings().now
    subbed = select(Subscription.match_id).where(Subscription.user_id == USER)
    rows = db.execute(
        select(Match).where(and_(Match.status == "scheduled", not_(Match.id.in_(subbed))))
        .order_by(Match.scheduled_at)
    ).scalars().all()
    return {"matchups": [_header(m, now) for m in rows]}


@router.get("/matchups/{match_id}/analysis")
def matchup_analysis(match_id: int, db: Session = Depends(get_db)) -> dict:
    payload = analysis_payload(db, match_id)
    if payload is None:
        raise HTTPException(404, "match not found")
    return payload


@router.get("/matchups/{match_id}/feed")
def matchup_feed(match_id: int, db: Session = Depends(get_db)) -> dict:
    payload = analysis_payload(db, match_id)
    if payload is None:
        raise HTTPException(404, "match not found")
    return {"feed": payload["feed"]}
