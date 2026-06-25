"""Analysis assembler: turns DB rows + engine outputs into the JSON payload the
dashboard and deep-dive render. Shaped per brief 5 so the frontend needs no extra
round-trips; later milestones fill in `prices` (devig/edge), `verdict`, live `feed`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, desc, or_, select

from .config import get_settings
from .engines.fatigue import load_profile_for
from .models import Match, PressItem, Subscription, VenuePrice

SURFACE_LABEL = {"grass": "Grass", "clay": "Clay", "hard": "Hard", "indoor": "Indoor",
                 "unknown": "Surface n/a"}


def _player(p) -> dict:
    return dict(id=p.id, name=p.full_name, short=p.short_name, country=p.country,
                rank=p.rank, hand=p.hand, tour=p.tour, note=p.note, press_lang=p.press_lang)


def _rel_time(target: datetime, now: datetime) -> str:
    secs = (target - now).total_seconds()
    future = secs >= 0
    secs = abs(secs)
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        s = f"{d}d {h}h"
    elif h:
        s = f"{h}h {m}m"
    else:
        s = f"{m}m"
    return f"in {s}" if future else f"{s} ago"


def _fatigue_payload(lp) -> dict:
    return dict(
        score=lp.score, band=lp.band, summary=lp.summary,
        components=[dict(key=c.key, label=c.label, detail=c.detail, contribution=c.contribution)
                    for c in lp.components],
        raw=lp.raw,
    )


def _header(m, now) -> dict:
    return dict(
        match_id=m.id,
        a=_player(m.player_a), b=_player(m.player_b),
        tournament=m.tournament.name, tier=m.tournament.tier,
        city=m.tournament.city, country=m.tournament.country,
        round=m.round, surface=m.surface, surface_label=SURFACE_LABEL.get(m.surface, m.surface.title()),
        indoor=m.tournament.indoor, best_of=m.best_of, status=m.status,
        is_real=m.is_real, pm_slug=m.pm_slug,
        scheduled_at=m.scheduled_at.isoformat(), starts_in=_rel_time(m.scheduled_at, now),
    )


# fatigue needs recent match durations. The seeded card has them; a live-ingested match
# does not (no free real-time feed) -- so we mark it unavailable rather than fake a 0.
FATIGUE_UNAVAILABLE = ("Live match-data feed not wired in V0 — the load score needs recent "
                       "match durations, which have no free real-time source.")


def _fatigue_block(db, m, player_id: int, now) -> dict:
    if m.is_real:
        return dict(available=False, reason=FATIGUE_UNAVAILABLE)
    return dict(available=True, **_fatigue_payload(load_profile_for(db, m, player_id, now)))


def _feed_for(db, m, now, limit=20) -> list[dict]:
    rows = db.execute(
        select(PressItem).where(or_(
            PressItem.match_id == m.id,
            PressItem.player_id.in_([m.player_a_id, m.player_b_id]),
        )).order_by(desc(PressItem.observed_at)).limit(limit)
    ).scalars().all()
    name = {m.player_a_id: m.player_a.short_name, m.player_b_id: m.player_b.short_name}
    return [dict(
        signal_type=r.signal_type, claim=r.claim, source=r.source, source_lang=r.source_lang,
        url=r.url, confidence=r.confidence, status=r.status,
        player=name.get(r.player_id), observed_at=r.observed_at.isoformat(),
        when=_rel_time(r.observed_at, now),
    ) for r in rows]


def _prices_latest(db, m) -> list[dict]:
    """Latest snapshot per (venue, side) -- raw decimal odds. Devig/edge added in M3."""
    rows = db.execute(
        select(VenuePrice).where(VenuePrice.match_id == m.id)
        .order_by(desc(VenuePrice.fetched_at))
    ).scalars().all()
    by_venue: dict[str, dict] = {}
    for r in rows:
        v = by_venue.setdefault(r.venue, dict(venue=r.venue, venue_type=r.venue_type,
                                              resolution_rule=r.resolution_rule, a=None, b=None,
                                              fetched_at=r.fetched_at.isoformat()))
        if v[r.side] is None:   # rows are newest-first, so first seen wins
            v[r.side] = dict(price=r.price, implied=r.implied_prob, is_live=r.is_live)
    return list(by_venue.values())


def analysis_payload(db, match_id: int, now: datetime | None = None) -> dict | None:
    now = now or get_settings().now
    m = db.get(Match, match_id)
    if m is None:
        return None
    return dict(
        header=_header(m, now),
        verdict=None,                       # M6
        fatigue=dict(a=_fatigue_block(db, m, m.player_a_id, now),
                     b=_fatigue_block(db, m, m.player_b_id, now)),
        feed=_feed_for(db, m, now),
        prices=_prices_latest(db, m),       # devig/edge layered in M3
        generated_at=now.isoformat(),
    )


def _fatigue_flag(fa, fb) -> dict | None:
    """The dashboard headline flag: who holds the freshness edge, and how big."""
    gap = abs(fa.score - fb.score)
    if gap < 12:
        return None
    fresher, cooked = (("a", fb) if fa.score < fb.score else ("b", fa))
    return dict(type="fatigue", edge_side=fresher, gap=round(gap, 1),
                text=f"{cooked.band} load on the other side ({cooked.score:.0f}/100)")


def dashboard_data(db, user_id: str, now: datetime | None = None) -> dict:
    now = now or get_settings().now
    subs = db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at)
    ).scalars().all()

    cards = []
    for sub in subs:
        m = db.get(Match, sub.match_id)
        if m is None:
            continue
        if m.is_real:
            fatigue, flag = None, None
        else:
            fa = load_profile_for(db, m, m.player_a_id, now)
            fb = load_profile_for(db, m, m.player_b_id, now)
            fatigue = dict(a=dict(score=fa.score, band=fa.band), b=dict(score=fb.score, band=fb.band))
            flag = _fatigue_flag(fa, fb)
        cards.append(dict(
            subscription_id=sub.id,
            header=_header(m, now),
            verdict=None,                   # M6 -> WATCH placeholder in UI
            fatigue=fatigue,
            flag=flag,
            prices=_prices_latest(db, m),
        ))
    cards.sort(key=lambda c: (not c["header"]["is_real"], c["header"]["scheduled_at"]))  # live first
    return dict(user_id=user_id, count=len(cards), cards=cards, generated_at=now.isoformat())
