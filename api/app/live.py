"""Ingest ONE real match end-to-end (the user's "fully real on one match").

Real Polymarket odds + real GDELT news intel, written into the same schema the seeded
demo uses so the existing UI renders it. We are scrupulously honest about gaps: ITF-level
players have ~no press and there is no free live match-data feed, so the intel feed may be
empty and fatigue is marked unavailable rather than faked.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from .config import get_settings
from .models import Match, PressItem, Player, Subscription, Tournament, VenuePrice
from .sources import intel as intel_mod
from .sources.polymarket import LiveMarket, fetch_h2h, pick_featured

PM_RULE = "Resolves to the match result; a walkover/retirement resolves to the advancing player."


def _short(name: str) -> str:
    parts = name.split()
    return f"{parts[0][0]}. {parts[-1]}" if len(parts) >= 2 else name


def _get_or_make_player(db, name: str) -> Player:
    p = db.execute(select(Player).where(Player.full_name == name)).scalar_one_or_none()
    if p:
        return p
    p = Player(full_name=name, short_name=_short(name), country="", tour="ITF", hand="?",
               dob=datetime(2000, 1, 1).date(), rank=0, press_lang="en",
               note="Live ingest — limited public data")
    db.add(p)
    db.flush()
    return p


def _real_tournament(db, market: LiveMarket) -> Tournament:
    name = market.tournament
    t = db.execute(select(Tournament).where(Tournament.name == name)).scalar_one_or_none()
    if t:
        return t
    t = Tournament(name=name, tier="ITF", surface="unknown", indoor=False, city="", country="",
                   lat=0.0, lng=0.0, tz_offset_min=0, continent="EU", altitude_m=0)
    db.add(t)
    db.flush()
    return t


def ingest_featured(db, *, fetch_intel: bool = True) -> int | None:
    """Pick a live H2H, write real players/match/prices(+intel), subscribe demo user."""
    now = get_settings().now
    markets = fetch_h2h()
    market = pick_featured(markets)
    if market is None:
        return None

    # replace any prior live match so re-ingest is idempotent
    old = db.execute(select(Match).where(Match.is_real == True)).scalars().all()  # noqa: E712
    for m in old:
        db.execute(delete(VenuePrice).where(VenuePrice.match_id == m.id))
        db.execute(delete(PressItem).where(PressItem.match_id == m.id))
        db.execute(delete(Subscription).where(Subscription.match_id == m.id))
        db.delete(m)
    db.commit()

    t = _real_tournament(db, market)
    a = _get_or_make_player(db, market.player_a)
    b = _get_or_make_player(db, market.player_b)
    sched = market.start_date or (now + timedelta(hours=6))
    match = Match(
        tournament_id=t.id, player_a_id=a.id, player_b_id=b.id, round="—",
        surface=t.surface, best_of=3, scheduled_at=sched, status="scheduled",
        is_real=True, pm_slug=market.slug,
    )
    db.add(match)
    db.flush()

    snapshot_prices(db, match, market, now)
    db.add(Subscription(user_id="demo", match_id=match.id, created_at=now))
    db.commit()

    if fetch_intel:
        ingest_intel(db, match, [market.player_a, market.player_b], now)

    return match.id


def snapshot_prices(db, match: Match, market: LiveMarket, now: datetime) -> None:
    """Append a real Polymarket price snapshot (re-runnable -> real line movement)."""
    for side, prob in (("a", market.prob_a), ("b", market.prob_b)):
        prob = min(0.99, max(0.01, prob))
        db.add(VenuePrice(
            match_id=match.id, venue="Polymarket", venue_type="pm", side=side,
            price=round(1.0 / prob, 3), implied_prob=round(prob, 4), is_live=True,
            fetched_at=now, resolution_rule=PM_RULE,
        ))


def ingest_intel(db, match: Match, names: list[str], now: datetime) -> int:
    """Real GDELT intel for both players. Throttled (GDELT allows ~1 req / 5s)."""
    name_to_pid = {match.player_a.full_name: match.player_a_id,
                   match.player_b.full_name: match.player_b_id}
    seen = {h[0] for h in db.execute(select(PressItem.dedup_hash)).all()}
    added = 0
    for i, name in enumerate(names):
        if i:
            time.sleep(6)
        for sig in intel_mod.signals_for(name, now):
            h = intel_mod.dedup_hash(sig.claim)
            if h in seen:
                continue
            seen.add(h)
            db.add(PressItem(
                match_id=match.id, player_id=name_to_pid.get(name), signal_type=sig.signal_type,
                claim=sig.claim, source=sig.source, source_lang=sig.source_lang, url=sig.url,
                observed_at=sig.observed_at, confidence=sig.confidence, status=sig.status,
                raw_text=None, dedup_hash=h,
            ))
            added += 1
    db.commit()
    return added


if __name__ == "__main__":
    from .db import SessionLocal, init_db
    init_db()
    s = SessionLocal()
    try:
        mid = ingest_featured(s)
        if mid:
            m = s.get(Match, mid)
            print(f"Ingested live match #{mid}: {m.player_a.full_name} vs {m.player_b.full_name}")
            prices = s.execute(select(VenuePrice).where(VenuePrice.match_id == mid)).scalars().all()
            for p in prices:
                print(f"  {p.venue} {p.side}: {p.price} (implied {p.implied_prob})")
            press = s.execute(select(PressItem).where(PressItem.match_id == mid)).scalars().all()
            print(f"  intel items: {len(press)}")
        else:
            print("No live market available right now.")
    finally:
        s.close()
