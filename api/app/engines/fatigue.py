"""Fatigue / Scheduling Engine (brief 1.1) -- the signature feature.

Tennis is the one sport where physical load is exactly observable, so this is 100%
deterministic: no LLM, no hallucination. We sum real court time, deciders, rest and
travel into a legible 0-100 load score ("fresh -> cooked") and keep every raw
component for transparency. The pure function `compute_load` is what the unit tests
pin; `load_profile_for` is the thin DB adapter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime


# ---- weights (sum to 100 so the weighted score lands directly on 0-100) --------
W_MIN_7D = 30.0
W_MIN_3D = 20.0
W_DECIDERS = 12.0
W_REST = 18.0
W_BACK2BACK = 6.0
W_TRAVEL = 10.0
W_LATE = 4.0

# normalization caps (minutes / counts judged "maximal")
CAP_MIN_7D = 420.0     # 7h of court time in a week reads as fully loaded
CAP_MIN_3D = 240.0     # 4h in three days
CAP_DECIDERS = 3.0
CAP_KM = 8000.0
CAP_TZ_H = 8.0


@dataclass
class MatchLite:
    """Minimal completed-match shape the engine needs (decoupled from the ORM)."""
    ended_at: datetime
    scheduled_at: datetime
    duration_min: int
    num_sets: int
    was_decider: bool
    surface: str
    late_finish: bool
    lat: float
    lng: float
    tz_offset_min: int
    continent: str


@dataclass
class Venue:
    lat: float
    lng: float
    tz_offset_min: int
    continent: str


@dataclass
class LoadComponent:
    key: str
    label: str
    detail: str
    contribution: float   # points this component added to the 0-100 score


@dataclass
class LoadProfile:
    score: float                       # 0 (fresh) .. 100 (cooked)
    band: str                          # Fresh | Rested | Worn | Heavy | Cooked
    summary: str                       # plain-English analyst line
    components: list[LoadComponent] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _band(score: float) -> str:
    if score < 25:
        return "Fresh"
    if score < 45:
        return "Rested"
    if score < 65:
        return "Worn"
    if score < 82:
        return "Heavy"
    return "Cooked"


def _fmt_hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def compute_load(
    matches: list[MatchLite],
    *,
    dest: Venue,
    surface: str,
    best_of: int,
    now: datetime,
) -> LoadProfile:
    """Pure: turn a player's recent completed matches into a load profile."""
    def days_ago(dt: datetime) -> float:
        return (now - dt).total_seconds() / 86400.0

    recent = sorted([m for m in matches if m.ended_at <= now], key=lambda m: m.ended_at)

    min_7d = sum(m.duration_min for m in recent if days_ago(m.ended_at) <= 7)
    min_3d = sum(m.duration_min for m in recent if days_ago(m.ended_at) <= 3)
    min_14d = sum(m.duration_min for m in recent if days_ago(m.ended_at) <= 14)
    deciders_7d = sum(1 for m in recent if days_ago(m.ended_at) <= 7 and m.was_decider)
    long_7d = sum(1 for m in recent if days_ago(m.ended_at) <= 7 and m.num_sets >= 3)
    late_7d = any(m.late_finish for m in recent if days_ago(m.ended_at) <= 7)

    last = recent[-1] if recent else None
    days_rest = days_ago(last.ended_at) if last else 14.0

    # back-to-back: two completed matches on consecutive calendar days within 8 days
    b2b = False
    dates = sorted({m.scheduled_at.date() for m in recent if days_ago(m.ended_at) <= 8})
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            b2b = True
            break

    # travel from the most recent venue to the upcoming venue
    travel_km = tz_delta_h = 0.0
    continent_change = False
    if last is not None:
        travel_km = haversine_km(last.lat, last.lng, dest.lat, dest.lng)
        tz_delta_h = abs(last.tz_offset_min - dest.tz_offset_min) / 60.0
        continent_change = last.continent != dest.continent

    # ---- normalized sub-scores (0..1) ----
    s_min7 = min(1.0, min_7d / CAP_MIN_7D)
    s_min3 = min(1.0, min_3d / CAP_MIN_3D)
    s_dec = min(1.0, deciders_7d / CAP_DECIDERS)
    s_rest = max(0.0, min(1.0, (3.0 - days_rest) / 3.0))   # 0d rest -> 1.0, >=3d -> 0
    s_b2b = 1.0 if b2b else 0.0
    s_travel = (min(1.0, travel_km / CAP_KM) * 0.5
                + min(1.0, tz_delta_h / CAP_TZ_H) * 0.3
                + (0.2 if continent_change else 0.0))
    s_late = 1.0 if late_7d else 0.0

    parts = [
        ("minutes_7d", "Court time (7d)", f"{_fmt_hm(min_7d)} over the last week", W_MIN_7D * s_min7),
        ("minutes_3d", "Recent load (3d)", f"{_fmt_hm(min_3d)} in the last 3 days", W_MIN_3D * s_min3),
        ("deciders", "Deciding sets", f"{deciders_7d} decider(s), {long_7d} long match(es) in 7d", W_DECIDERS * s_dec),
        ("rest", "Days of rest", f"{days_rest:.1f}d since last match", W_REST * s_rest),
        ("back_to_back", "Back-to-back", "consecutive match days" if b2b else "none", W_BACK2BACK * s_b2b),
        ("travel", "Travel", _travel_detail(travel_km, tz_delta_h, continent_change), W_TRAVEL * s_travel),
        ("late_finish", "Late finish", "late-night finish in last 7d" if late_7d else "none", W_LATE * s_late),
    ]
    score = round(sum(p[3] for p in parts), 1)
    components = [LoadComponent(k, lbl, det, round(c, 1)) for (k, lbl, det, c) in parts]

    raw = dict(
        minutes_3d=min_3d, minutes_7d=min_7d, minutes_14d=min_14d,
        deciders_7d=deciders_7d, long_matches_7d=long_7d, days_rest=round(days_rest, 1),
        back_to_back=b2b, travel_km=round(travel_km), tz_delta_h=round(tz_delta_h, 1),
        continent_change=continent_change, late_finish_7d=late_7d, matches_7d=sum(1 for m in recent if days_ago(m.ended_at) <= 7),
    )
    return LoadProfile(score=score, band=_band(score),
                       summary=_summary(score, raw, surface, best_of, last, now),
                       components=components, raw=raw)


def _travel_detail(km: float, tz_h: float, continent_change: bool) -> str:
    if km < 50:
        return "same venue / no travel"
    bits = [f"{int(round(km))} km"]
    if tz_h >= 1:
        bits.append(f"{tz_h:.0f}h time shift")
    if continent_change:
        bits.append("cross-continent")
    return ", ".join(bits)


def _summary(score: float, raw: dict, surface: str, best_of: int, last, now: datetime) -> str:
    drivers: list[str] = []
    if raw["minutes_3d"] >= 150:
        drivers.append(f"{_fmt_hm(raw['minutes_3d'])} of court time in 3 days")
    elif raw["minutes_7d"] >= 240:
        drivers.append(f"{_fmt_hm(raw['minutes_7d'])} on court this week")
    if raw["deciders_7d"] >= 1:
        drivers.append(f"{raw['deciders_7d']} deciding set(s)")
    if raw["days_rest"] <= 2:
        drivers.append(f"only {raw['days_rest']:.0f}d rest")
    if raw["back_to_back"]:
        drivers.append("back-to-back days")
    if raw["continent_change"] or raw["travel_km"] >= 1500:
        drivers.append(_travel_detail(raw["travel_km"], raw["tz_delta_h"], raw["continent_change"]))
    if raw["late_finish_7d"]:
        drivers.append("a late-night finish")

    band = _band(score)
    bo = f"best-of-{best_of}"
    if not drivers:
        return f"Fresh: light recent schedule into a {bo} on {surface}. Load {score:.0f}/100."
    lead = "; ".join(drivers[:3])
    return f"{band} ({score:.0f}/100): carrying {lead} into a {bo} on {surface}."


# ----------------------------------------------------------------- DB adapter
def load_profile_for(db, match, player_id: int, now: datetime) -> LoadProfile:
    """Gather a player's completed matches before `match` and compute their load."""
    from sqlalchemy import or_, select

    from ..models import Match

    rows = db.execute(
        select(Match).where(
            Match.status.in_(("completed", "retired")),
            Match.scheduled_at < match.scheduled_at,
            or_(Match.player_a_id == player_id, Match.player_b_id == player_id),
        )
    ).scalars().all()

    lites: list[MatchLite] = []
    for m in rows:
        t = m.tournament
        ended = m.ended_at or m.scheduled_at
        local_hour = ((ended.hour * 60 + ended.minute) + t.tz_offset_min) % (24 * 60) // 60
        lites.append(MatchLite(
            ended_at=ended, scheduled_at=m.scheduled_at,
            duration_min=m.duration_min or 0, num_sets=m.num_sets or 0,
            was_decider=m.was_decider, surface=m.surface,
            late_finish=(local_hour >= 22 or local_hour < 4),
            lat=t.lat, lng=t.lng, tz_offset_min=t.tz_offset_min, continent=t.continent,
        ))

    dest_t = match.tournament
    dest = Venue(dest_t.lat, dest_t.lng, dest_t.tz_offset_min, dest_t.continent)
    return compute_load(lites, dest=dest, surface=match.surface, best_of=match.best_of, now=now)
