"""Synthetic odds time-series for the seeded demo card.

The live clients (polymarket.py, oddsapi.py) produce the *same row shape*, so the
pricing engine and the UI can't tell seeded from live. We deliberately bake in a
realistic line drift (with a touch of venue disagreement and noise) so the
line-movement ticker and the cross-venue table have something true to render.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class PriceRow:
    venue: str
    venue_type: str       # book | pm
    side: str             # a | b
    price: float          # decimal odds
    implied_prob: float
    fetched_at: datetime
    resolution_rule: str | None = None


# venue -> (type, overround target, resolution rule)
VENUES = {
    "Pinnacle":    ("book", 1.025, "Retirement: action if 1 set completed, else void."),
    "DraftKings":  ("book", 1.055, "Retirement before completion: bet voided (push)."),
    "Polymarket":  ("pm",   1.000, "Resolves to match result; walkover/retirement -> advancing player wins."),
}


def _odds_from_prob(prob: float, overround_share: float) -> tuple[float, float]:
    """Return (decimal_price, implied_prob_with_vig) for one side."""
    implied = min(0.97, max(0.03, prob * overround_share))
    return round(1.0 / implied, 3), round(implied, 4)


def generate_price_series(
    *,
    base_prob_a: float,
    final_prob_a: float,
    now: datetime,
    hours: int = 36,
    step_min: int = 90,
    seed: int = 0,
) -> list[PriceRow]:
    """Drift side-A fair prob from base->final over `hours`, emit per-venue snapshots.

    Books carry an overround (vig) split across both sides; the PM is ~vig-free.
    Small per-venue offsets create genuine cross-venue disagreement to price against.
    """
    rng = random.Random(seed)
    rows: list[PriceRow] = []
    n = max(1, (hours * 60) // step_min)
    start = now - timedelta(hours=hours)

    venue_bias = {v: rng.uniform(-0.012, 0.012) for v in VENUES}

    for i in range(n + 1):
        t = start + timedelta(minutes=i * step_min)
        frac = i / n
        # ease-in-out drift + mild noise
        eased = base_prob_a + (final_prob_a - base_prob_a) * (0.5 - 0.5 * math.cos(math.pi * frac))
        noise = rng.uniform(-0.006, 0.006)
        prob_a = min(0.93, max(0.07, eased + noise))

        for venue, (vtype, overround, rule) in VENUES.items():
            pa = min(0.93, max(0.07, prob_a + venue_bias[venue]))
            pb = 1.0 - pa
            # split the overround across both sides
            share = overround ** 0.5
            price_a, imp_a = _odds_from_prob(pa, share)
            price_b, imp_b = _odds_from_prob(pb, share)
            rows.append(PriceRow(venue, vtype, "a", price_a, imp_a, t, rule))
            rows.append(PriceRow(venue, vtype, "b", price_b, imp_b, t, rule))
    return rows
