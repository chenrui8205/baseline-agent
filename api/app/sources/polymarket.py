"""Polymarket (Gamma API) client — REAL, live, keyless prediction-market odds.

Gamma returns tennis head-to-head markets as events titled "Tournament: A vs B" with
two outcomes (the player names) and `outcomePrices` (probabilities, ~vig-free). We pick a
current, liquid, competitive singles match and map it into our schema. This is the live
half of the user's "fully real on one match".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import httpx

GAMMA = "https://gamma-api.polymarket.com"
NOISE = {"over", "under", "yes", "no"}
SKIP_WORDS = ("winner", "doubles")


@dataclass
class LiveMarket:
    slug: str
    title: str
    tournament: str
    player_a: str
    player_b: str
    prob_a: float          # Polymarket implied prob (≈ no-vig)
    prob_b: float
    start_date: datetime | None
    liquidity: float
    volume: float


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def _tournament_of(title: str) -> str:
    return title.split(":")[0].strip() if ":" in title else "Tennis"


def fetch_h2h(*, limit: int = 200, tour_only: bool = False, min_liquidity: float = 800.0,
              timeout: float = 25.0) -> list[LiveMarket]:
    """Return current head-to-head singles markets, most-liquid first."""
    r = httpx.get(f"{GAMMA}/events", params={
        "closed": "false", "tag_slug": "tennis", "limit": limit,
        "order": "startDate", "ascending": "false",
    }, timeout=timeout)
    r.raise_for_status()
    out: list[LiveMarket] = []
    for e in r.json():
        title = e.get("title", "")
        tl = title.lower()
        if " vs " not in tl or any(w in tl for w in SKIP_WORDS):
            continue
        if tour_only and any(w in tl for w in ("itf", "qualification", "qualifying", "challenger")):
            continue
        for m in e.get("markets", []):
            if m.get("closed") or not m.get("active"):
                continue
            try:
                outs = json.loads(m.get("outcomes", "[]"))
                prices = [float(p) for p in json.loads(m.get("outcomePrices", "[]"))]
            except (ValueError, TypeError):
                continue
            if len(outs) != 2 or len(prices) != 2:
                continue
            if any(o.strip().lower() in NOISE for o in outs):
                continue
            liq = float(m.get("liquidity") or 0)
            if liq < min_liquidity:
                continue
            out.append(LiveMarket(
                slug=e.get("slug", ""), title=title, tournament=_tournament_of(title),
                player_a=outs[0].strip(), player_b=outs[1].strip(),
                prob_a=prices[0], prob_b=prices[1],
                start_date=_parse_dt(e.get("startDate")),
                liquidity=liq, volume=float(m.get("volume") or 0),
            ))
    out.sort(key=lambda lm: -lm.liquidity)
    return out


def pick_featured(markets: list[LiveMarket]) -> LiveMarket | None:
    """Prefer a competitive, liquid line (avoids 0.99/0.01 blowouts)."""
    competitive = [m for m in markets if 0.25 <= m.prob_a <= 0.75 and m.volume > 50]
    pool = competitive or markets
    return pool[0] if pool else None
