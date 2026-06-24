"""Seed a coherent, fictional grass-season demo, anchored to DEMO_NOW (2026-06-23).

Players and tournaments are invented so nothing in the intel feed is a false claim
about a real athlete. Match histories are hand-tuned so the fatigue and form engines
have genuine stories to surface:
  * Brandt  -> cooked: a 3h12m three-setter 2 days ago + short rest.
  * Devin   -> fresh: quick straight-set wins, a walkover in his favour.
  * Whitman -> travel-fatigued: won a US grass final 3 days ago, flew to London.
  * Quiroga -> clay specialist on his weakest surface (grass).
  * Hradec  -> veteran with a managed knee + a recent in-match retirement.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from sqlalchemy import delete

from .config import DEMO_NOW
from .db import SessionLocal, init_db
from .models import (
    Match,
    PressItem,
    Player,
    Subscription,
    Tournament,
    VenuePrice,
    Verdict,
)
from .sources.synthetic import generate_price_series

NOW = DEMO_NOW


def H(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


# ---------------------------------------------------------------- tournaments
TOURNAMENTS = {
    "hurlingham": dict(name="Hurlingham Grass Championships", tier="ATP/WTA 500", surface="grass",
                       indoor=False, city="London", country="GB", lat=51.47, lng=-0.21,
                       tz_offset_min=60, continent="EU", altitude_m=10),
    "rhineland": dict(name="Rhineland Grass Open", tier="ATP 500", surface="grass",
                      indoor=False, city="Halle", country="DE", lat=52.06, lng=8.37,
                      tz_offset_min=120, continent="EU", altitude_m=110),
    "carolina": dict(name="Carolina Grass Invitational", tier="ATP 250", surface="grass",
                     indoor=False, city="Charlotte", country="US", lat=35.23, lng=-80.84,
                     tz_offset_min=-240, continent="NA", altitude_m=229),
    "cotedazur": dict(name="Cote d'Azur Open", tier="ATP 250", surface="clay",
                      indoor=False, city="Nice", country="FR", lat=43.70, lng=7.27,
                      tz_offset_min=120, continent="EU", altitude_m=15),
    "paris": dict(name="Paris Clay Major", tier="Grand Slam", surface="clay",
                  indoor=False, city="Paris", country="FR", lat=48.85, lng=2.25,
                  tz_offset_min=120, continent="EU", altitude_m=35),
}

# ---------------------------------------------------------------- players
PLAYERS = {
    "brandt":   dict(full_name="Lars Brandt", short_name="L. Brandt", country="DE", tour="ATP",
                     hand="R", dob=date(1999, 4, 12), rank=14, height_cm=188, press_lang="de",
                     note="Aggressive baseliner, comfortable on grass."),
    "devin":    dict(full_name="Theo Devin", short_name="T. Devin", country="FR", tour="ATP",
                     hand="L", dob=date(2002, 8, 3), rank=9, height_cm=185, press_lang="fr",
                     note="Lefty shotmaker; quick through early rounds this week."),
    "sorensen": dict(full_name="Niko Sorensen", short_name="N. Sorensen", country="DK", tour="ATP",
                     hand="R", dob=date(1996, 11, 20), rank=22, height_cm=193, press_lang="en",
                     note="Big serve; managing his schedule this week."),
    "hradec":   dict(full_name="Viktor Hradec", short_name="V. Hradec", country="CZ", tour="ATP",
                     hand="R", dob=date(1994, 7, 30), rank=27, height_cm=190, press_lang="cs",
                     note="Veteran; recurring right-knee issue."),
    "quiroga":  dict(full_name="Pablo Quiroga", short_name="P. Quiroga", country="ES", tour="ATP",
                     hand="R", dob=date(2003, 1, 9), rank=11, height_cm=180, press_lang="es",
                     note="Clay specialist; grass is his weakest surface."),
    "whitman":  dict(full_name="Cole Whitman", short_name="C. Whitman", country="US", tour="ATP",
                     hand="R", dob=date(2004, 3, 18), rank=31, height_cm=198, press_lang="en",
                     note="Huge serve, grass-friendly; just flew in from the US."),
    "bellandi": dict(full_name="Marco Bellandi", short_name="M. Bellandi", country="IT", tour="ATP",
                     hand="R", dob=date(1998, 2, 15), rank=18, height_cm=183, press_lang="it",
                     note="Clay-leaning all-courter."),
    "kovic":    dict(full_name="Andrej Kovic", short_name="A. Kovic", country="RS", tour="ATP",
                     hand="R", dob=date(2000, 5, 22), rank=16, height_cm=196, press_lang="sr",
                     note="Big serve, streaky returner."),
    "carbonell": dict(full_name="Ines Carbonell", short_name="I. Carbonell", country="ES", tour="WTA",
                      hand="R", dob=date(2001, 9, 14), rank=12, height_cm=175, press_lang="es",
                      note="Counterpuncher; strong return."),
    "falk":     dict(full_name="Greta Falk", short_name="G. Falk", country="DE", tour="WTA",
                     hand="R", dob=date(1997, 12, 1), rank=19, height_cm=178, press_lang="de",
                     note="Flat hitter; rewards short points."),
    "marchetti": dict(full_name="Sofia Marchetti", short_name="S. Marchetti", country="IT", tour="WTA",
                      hand="R", dob=date(1999, 6, 25), rank=15, height_cm=173, press_lang="it",
                      note="Aggressive off both wings."),
    "lindqvist": dict(full_name="Mara Lindqvist", short_name="M. Lindqvist", country="SE", tour="WTA",
                      hand="L", dob=date(2005, 2, 10), rank=25, height_cm=180, press_lang="en",
                      note="Young lefty riser."),
}


def _dt(days: float, hour: int, minute: int = 0) -> datetime:
    """A datetime `days` before NOW, at the given UTC hour:minute."""
    base = (NOW - timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base


# completed matches: (winner, loser, tkey, round, days_ago, hour_utc, dur_min, sets, decider, score, retired_by)
COMPLETED = [
    # --- Brandt: heavy recent load (3h12m decider 2 days ago) + a final 5 days back
    ("brandt", "kovic", "hurlingham", "R16", 2, 17, 192, 3, True, "6-7(5) 7-6(4) 7-5", None),
    ("brandt", "bellandi", "rhineland", "F", 5, 14, 134, 3, True, "7-5 4-6 6-4", None),
    ("brandt", "whitman", "rhineland", "SF", 6, 12, 96, 2, False, "7-6(3) 6-4", None),
    ("quiroga", "brandt", "paris", "R16", 24, 12, 168, 4, False, "6-3 6-4 4-6 6-2", None),
    # --- Devin: fresh, quick wins + a walkover in his favour
    ("devin", "sorensen", "hurlingham", "R16", 2, 12, 88, 2, False, "6-4 6-4", None),
    ("devin", "kovic", "hurlingham", "R32", 3, 11, 0, 0, False, "w/o", None),  # walkover -> no court time
    ("devin", "bellandi", "rhineland", "QF", 7, 13, 99, 2, False, "7-5 6-3", None),
    # --- Whitman: won a US grass final 3 days ago, then flew to London
    ("whitman", "kovic", "carolina", "F", 3, 22, 158, 3, True, "7-6(4) 6-7(5) 7-6(8)", None),
    ("whitman", "bellandi", "carolina", "SF", 4, 20, 104, 2, False, "7-6(2) 7-5", None),
    # --- Quiroga: clay specialist; lost early on grass, strong on clay
    ("kovic", "quiroga", "rhineland", "R32", 7, 15, 78, 2, False, "6-4 6-4", None),
    ("quiroga", "bellandi", "cotedazur", "F", 17, 14, 142, 3, True, "6-2 4-6 6-3", None),
    ("quiroga", "brandt", "paris", "R16", 24, 12, 168, 4, False, "(see above)", None),
    # --- Sorensen: moderate load, big-serve quick matches
    ("sorensen", "bellandi", "hurlingham", "R32", 3, 13, 92, 2, False, "7-6(4) 7-6(2)", None),
    ("sorensen", "kovic", "rhineland", "R16", 6, 16, 110, 3, True, "6-4 3-6 7-6(5)", None),
    # --- Hradec: veteran, a recent in-match retirement (knee)
    ("kovic", "hradec", "rhineland", "R32", 7, 17, 64, 2, False, "6-4 2-1 ret.", "hradec"),
    ("hradec", "bellandi", "cotedazur", "QF", 18, 13, 121, 3, True, "4-6 6-3 6-4", None),
    # --- WTA
    ("carbonell", "lindqvist", "hurlingham", "R16", 2, 10, 138, 3, True, "4-6 6-3 7-5", None),
    ("carbonell", "falk", "rhineland", "SF", 6, 12, 96, 2, False, "6-4 7-5", None),
    ("falk", "marchetti", "hurlingham", "R16", 2, 11, 74, 2, False, "6-2 6-3", None),
    ("falk", "lindqvist", "rhineland", "QF", 7, 14, 88, 2, False, "6-4 6-4", None),
    ("marchetti", "carbonell", "cotedazur", "F", 17, 13, 151, 3, True, "7-6(5) 4-6 6-4", None),
    ("lindqvist", "falk", "cotedazur", "SF", 18, 12, 119, 3, True, "6-7(3) 6-4 6-2", None),
]

# upcoming card: (a, b, round, days_ahead, hour_utc, best_of)
UPCOMING = [
    ("brandt", "devin", "QF", 1, 14, 3),
    ("sorensen", "hradec", "QF", 1, 16, 3),
    ("quiroga", "whitman", "QF", 2, 13, 3),
    ("carbonell", "falk", "QF", 1, 11, 3),
    ("marchetti", "lindqvist", "QF", 2, 15, 3),
]

# press items: (player, match_idx_in_upcoming|None, signal, claim, source, lang, conf, status, hours_ago)
PRESS = [
    ("sorensen", 1, "withdrawal", "Sorensen withdrew from the doubles draw to protect his schedule before the singles quarterfinal.",
     "DR Sport", "en", 0.85, "confirmed", 6),
    ("hradec", 1, "injury", "Hradec said his right knee was 'managed, not fully right' in his post-match press conference.",
     "Sport.cz", "cs", 0.6, "unconfirmed", 26),
    ("brandt", 0, "conditions", "Brandt requested a later start time, citing recovery from his three-set Round of 16.",
     "Tennis Magazin", "de", 0.7, "confirmed", 10),
    ("devin", 0, "practice", "Devin completed a full 90-minute grass practice on the show court; reported moving freely.",
     "L'Equipe", "fr", 0.65, "confirmed", 8),
    ("whitman", 2, "conditions", "Whitman landed in London on Sunday after winning the Carolina final; first grass practice was Monday.",
     "Tennis.com", "en", 0.75, "confirmed", 28),
    ("quiroga", 2, "motivation", "Quiroga downplayed his grass expectations, calling the grass swing 'a bonus' before the US hard-court stretch.",
     "Marca", "es", 0.5, "unconfirmed", 40),
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        # wipe (idempotent reseed)
        for model in (Verdict, VenuePrice, PressItem, Subscription, Match, Player, Tournament):
            db.execute(delete(model))
        db.commit()

        tour_ids: dict[str, int] = {}
        for key, t in TOURNAMENTS.items():
            row = Tournament(**t)
            db.add(row)
            db.flush()
            tour_ids[key] = row.id

        pl_ids: dict[str, int] = {}
        for key, p in PLAYERS.items():
            row = Player(**p)
            db.add(row)
            db.flush()
            pl_ids[key] = row.id

        # completed matches
        for (w, l, tkey, rnd, days_ago, hour, dur, sets_, decider, score, ret_by) in COMPLETED:
            t = TOURNAMENTS[tkey]
            sched = _dt(days_ago, hour)
            ended = sched + timedelta(minutes=dur)
            local_hour = (ended + timedelta(minutes=t["tz_offset_min"])).hour
            late = local_hour >= 22 or local_hour < 4
            m = Match(
                tournament_id=tour_ids[tkey], player_a_id=pl_ids[w], player_b_id=pl_ids[l],
                round=rnd, surface=t["surface"], best_of=5 if t["tier"] == "Grand Slam" else 3,
                scheduled_at=sched, status="retired" if ret_by else "completed",
                duration_min=dur, num_sets=sets_, was_decider=decider, ended_at=ended,
                score=score, winner_id=pl_ids[w],
                retired_flag=bool(ret_by), retired_by_id=pl_ids[ret_by] if ret_by else None,
            )
            db.add(m)
        db.commit()

        # upcoming card
        upcoming_ids: list[int] = []
        for (a, b, rnd, days_ahead, hour, bo) in UPCOMING:
            t = TOURNAMENTS["hurlingham"]
            sched = (NOW + timedelta(days=days_ahead)).replace(hour=hour, minute=0, second=0, microsecond=0)
            m = Match(
                tournament_id=tour_ids["hurlingham"], player_a_id=pl_ids[a], player_b_id=pl_ids[b],
                round=rnd, surface=t["surface"], best_of=bo, scheduled_at=sched, status="scheduled",
            )
            db.add(m)
            db.flush()
            upcoming_ids.append(m.id)
        db.commit()

        # subscriptions: follow the three ATP quarterfinals by default
        for mid in upcoming_ids[:3]:
            db.add(Subscription(user_id="demo", match_id=mid, created_at=NOW - timedelta(hours=12)))

        # press items
        for (pkey, midx, sig, claim, src, lang, conf, status, hrs) in PRESS:
            mid = upcoming_ids[midx] if midx is not None else None
            db.add(PressItem(
                match_id=mid, player_id=pl_ids[pkey], signal_type=sig, claim=claim,
                source=src, source_lang=lang, url=f"https://example.test/{H(src, claim)}",
                observed_at=NOW - timedelta(hours=hrs), confidence=conf, status=status,
                raw_text=None, dedup_hash=H(claim),
            ))
        db.commit()

        # synthetic odds series per upcoming match. base_prob/final_prob for side A.
        # Brandt(A) vs Devin(B): market drifts toward Devin -> A's fair prob falls ~6pts.
        drifts = {
            upcoming_ids[0]: (0.545, 0.485, 11),   # Brandt fades as fatigue news lands
            upcoming_ids[1]: (0.520, 0.560, 22),   # Sorensen firms after Hradec knee news
            upcoming_ids[2]: (0.430, 0.405, 33),   # Quiroga (clay) drifts down vs Whitman on grass
            upcoming_ids[3]: (0.620, 0.635, 44),   # Carbonell steady-favourite
            upcoming_ids[4]: (0.500, 0.520, 55),   # Marchetti edges up
        }
        for mid, (base, final, sd) in drifts.items():
            for r in generate_price_series(base_prob_a=base, final_prob_a=final, now=NOW, seed=sd):
                db.add(VenuePrice(
                    match_id=mid, venue=r.venue, venue_type=r.venue_type, side=r.side,
                    price=r.price, implied_prob=r.implied_prob, is_live=False,
                    fetched_at=r.fetched_at, resolution_rule=r.resolution_rule,
                ))
        db.commit()

        print(f"Seeded: {len(PLAYERS)} players, {len(TOURNAMENTS)} tournaments, "
              f"{len(COMPLETED)} completed + {len(UPCOMING)} upcoming matches, "
              f"{len(PRESS)} press items, prices for {len(drifts)} matchups.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
