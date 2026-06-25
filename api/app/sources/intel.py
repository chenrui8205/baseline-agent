"""Factual intel — REAL news via GDELT (keyless) + factual extraction.

Pipeline: GDELT DOC API returns real articles mentioning a player; we extract *discrete
facts* (injury, withdrawal, practice, conditions, lineup, motivation) — never sentiment.
With ANTHROPIC_API_KEY we use the cheap model (Haiku) for extraction/translation; without
it we fall back to a conservative keyword classifier that only surfaces items containing a
concrete signal word (so we never fabricate a signal from a generic preview).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

import httpx

from ..config import get_settings

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
SIGNAL_TYPES = ["injury", "withdrawal", "practice", "motivation", "conditions", "lineup", "other"]

# conservative keyword -> signal_type map for the no-LLM fallback
KEYWORDS = {
    "injury": ["injury", "injured", "knee", "wrist", "shoulder", "ankle", "back", "abdominal", "niggle", "strain"],
    "withdrawal": ["withdraw", "withdrew", "pulls out", "pulled out", "retire", "retired", "walkover", "out of"],
    "practice": ["practice", "practise", "hitting", "training", "session"],
    "conditions": ["heat", "wind", "rain", "delay", "late start", "night session", "travel", "jet lag"],
    "lineup": ["doubles", "schedule", "first match", "order of play"],
}


@dataclass
class Article:
    title: str
    url: str
    domain: str
    lang: str
    seen_at: datetime | None


@dataclass
class Signal:
    signal_type: str
    player: str
    claim: str
    source: str
    source_lang: str
    url: str
    observed_at: datetime
    confidence: float
    status: str            # confirmed | unconfirmed


def _parse_seendate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:                                   # GDELT format e.g. 20260623T120000Z
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def fetch_news(name: str, *, days: int = 21, max_records: int = 15, timeout: float = 25.0) -> list[Article]:
    """Real articles mentioning a player, tennis-scoped to cut noise."""
    query = f'"{name}" (tennis OR ATP OR WTA OR ITF)'
    try:
        r = httpx.get(GDELT, params={
            "query": query, "mode": "ArtList", "format": "json",
            "maxrecords": max_records, "timespan": f"{days}d", "sort": "DateDesc",
        }, timeout=timeout, headers={"User-Agent": "baseline/0.1"})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return []
    arts = []
    for a in data.get("articles", []) or []:
        arts.append(Article(
            title=(a.get("title") or "").strip(), url=a.get("url", ""),
            domain=a.get("domain", ""), lang=(a.get("language") or "en")[:2].lower(),
            seen_at=_parse_seendate(a.get("seendate")),
        ))
    return [a for a in arts if a.title and a.url]


def _heuristic_signals(articles: list[Article], player: str, now: datetime) -> list[Signal]:
    out = []
    for a in articles:
        low = a.title.lower()
        stype = next((st for st, kws in KEYWORDS.items() if any(k in low for k in kws)), None)
        if not stype:
            continue                       # no concrete signal word -> don't fabricate
        out.append(Signal(
            signal_type=stype, player=player, claim=a.title, source=a.domain or "news",
            source_lang=a.lang, url=a.url, observed_at=a.seen_at or now,
            confidence=0.35, status="unconfirmed",
        ))
    return out


def _llm_signals(articles: list[Article], player: str, now: datetime) -> list[Signal]:
    from anthropic import Anthropic

    s = get_settings()
    client = Anthropic(api_key=s.anthropic_api_key)
    headlines = [{"i": i, "title": a.title, "domain": a.domain, "lang": a.lang} for i, a in enumerate(articles)]
    prompt = (
        f"You extract FACTS about the tennis player '{player}' from news headlines. "
        "Return STRICT JSON: a list of objects {idx, signal_type, claim, confidence, status}.\n"
        f"signal_type ∈ {SIGNAL_TYPES}. 'claim' must be a short factual statement in English "
        "(translate if needed). status ∈ ['confirmed','unconfirmed'] (unconfirmed if hedged/rumor).\n"
        "RULES: Only include items that assert a concrete FACT relevant to readiness/availability "
        "(injury, withdrawal, practice, schedule, conditions, motivation). "
        "NO sentiment, NO predictions, NO crowd opinion, NO generic match previews. "
        "If a headline is just a preview/result with no fact, OMIT it. Return [] if nothing qualifies.\n\n"
        f"Headlines: {json.dumps(headlines)}"
    )
    try:
        msg = client.messages.create(
            model=s.extract_model, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        text = text[text.find("["): text.rfind("]") + 1]
        items = json.loads(text)
    except Exception:
        return _heuristic_signals(articles, player, now)
    out = []
    for it in items:
        try:
            a = articles[int(it["idx"])]
        except (KeyError, ValueError, IndexError):
            continue
        st = it.get("signal_type", "other")
        out.append(Signal(
            signal_type=st if st in SIGNAL_TYPES else "other", player=player,
            claim=(it.get("claim") or a.title)[:300], source=a.domain or "news",
            source_lang=a.lang, url=a.url, observed_at=a.seen_at or now,
            confidence=float(it.get("confidence", 0.5)),
            status="confirmed" if it.get("status") == "confirmed" else "unconfirmed",
        ))
    return out


def signals_for(name: str, now: datetime, *, days: int = 21) -> list[Signal]:
    arts = fetch_news(name, days=days)
    if not arts:
        return []
    if get_settings().has_llm:
        return _llm_signals(arts, name, now)
    return _heuristic_signals(arts, name, now)


def dedup_hash(claim: str) -> str:
    return hashlib.sha256(claim.lower().strip().encode()).hexdigest()[:32]
