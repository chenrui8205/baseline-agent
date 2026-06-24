"""Fatigue engine tests -- this pure-math layer is the quality bar (brief 7)."""
from datetime import datetime, timedelta

from app.engines.fatigue import MatchLite, Venue, compute_load, haversine_km

NOW = datetime(2026, 6, 23, 12, 0, 0)
LONDON = Venue(lat=51.47, lng=-0.21, tz_offset_min=60, continent="EU")


def mk(days_ago, dur, sets_, decider, *, cont="EU", lat=51.47, lng=-0.21, tz=60, late=False):
    ended = NOW - timedelta(days=days_ago)
    return MatchLite(
        ended_at=ended, scheduled_at=ended - timedelta(minutes=dur),
        duration_min=dur, num_sets=sets_, was_decider=decider, surface="grass",
        late_finish=late, lat=lat, lng=lng, tz_offset_min=tz, continent=cont,
    )


def load(matches):
    return compute_load(matches, dest=LONDON, surface="grass", best_of=3, now=NOW)


def test_cooked_beats_fresh():
    cooked = load([mk(2, 192, 3, True), mk(5, 134, 3, True), mk(6, 96, 2, False)])
    fresh = load([mk(2, 88, 2, False)])
    assert cooked.score > fresh.score
    assert cooked.band in ("Heavy", "Cooked")
    assert fresh.band in ("Fresh", "Rested")


def test_components_sum_to_score():
    p = load([mk(1, 180, 3, True), mk(2, 120, 2, False)])
    assert abs(sum(c.contribution for c in p.components) - p.score) < 0.2


def test_score_bounds():
    empty = load([])
    maxed = load([mk(1, 300, 5, True, late=True), mk(2, 240, 3, True),
                  mk(0, 200, 3, True, cont="NA", lat=35.2, lng=-80.8, tz=-240)])
    assert empty.score == 0 or empty.band == "Fresh"
    assert 0 <= empty.score <= 100 and 0 <= maxed.score <= 100
    assert maxed.score > 80


def test_travel_continent_change():
    p = load([mk(3, 158, 3, True, cont="NA", lat=35.23, lng=-80.84, tz=-240)])
    assert p.raw["continent_change"] is True
    assert p.raw["travel_km"] > 4000
    assert p.raw["tz_delta_h"] >= 4


def test_more_rest_lowers_load():
    near = load([mk(2, 150, 3, True)])
    far = load([mk(9, 150, 3, True)])   # outside the 7d window + more rest
    assert far.score < near.score


def test_back_to_back_detected():
    p = load([mk(2, 110, 2, False), mk(3, 95, 2, False)])  # consecutive days
    assert p.raw["back_to_back"] is True


def test_haversine_london_charlotte():
    km = haversine_km(51.47, -0.21, 35.23, -80.84)
    assert 6000 < km < 7200


# ---- integration against the seeded demo ----
def test_seed_brandt_more_cooked_than_devin():
    from sqlalchemy import and_, select

    from app.config import get_settings
    from app.db import SessionLocal
    from app.engines.fatigue import load_profile_for
    from app.models import Match, Player

    db = SessionLocal()
    try:
        s = get_settings()
        brandt = db.execute(select(Player).where(Player.short_name == "L. Brandt")).scalar_one()
        devin = db.execute(select(Player).where(Player.short_name == "T. Devin")).scalar_one()
        match = db.execute(select(Match).where(and_(
            Match.status == "scheduled",
            Match.player_a_id == brandt.id, Match.player_b_id == devin.id))).scalar_one()
        lb = load_profile_for(db, match, brandt.id, s.now)
        ld = load_profile_for(db, match, devin.id, s.now)
        assert lb.score > ld.score          # Brandt carries the 3h12m decider
        assert lb.raw["minutes_7d"] > ld.raw["minutes_7d"]
    finally:
        db.close()
