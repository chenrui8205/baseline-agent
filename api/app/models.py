"""ORM models. Fictional players/tournaments are used for the seeded demo so that
nothing in the intel feed (injuries, withdrawals) is a false claim about a real
athlete; the live odds/intel clients are written to work against real data too."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(80))
    short_name: Mapped[str] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(String(3))           # ISO-3166 alpha-2/3
    tour: Mapped[str] = mapped_column(String(4))              # ATP | WTA
    hand: Mapped[str] = mapped_column(String(1))              # R | L
    dob: Mapped[date] = mapped_column(Date)
    rank: Mapped[int] = mapped_column(Integer)
    height_cm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    press_lang: Mapped[str] = mapped_column(String(2), default="en")  # primary press language
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tier: Mapped[str] = mapped_column(String(20))             # ATP 250 | Masters 1000 | Grand Slam ...
    surface: Mapped[str] = mapped_column(String(10))          # grass | clay | hard | indoor
    indoor: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(3))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    tz_offset_min: Mapped[int] = mapped_column(Integer, default=0)  # minutes from UTC
    continent: Mapped[str] = mapped_column(String(2))         # EU | NA | SA | AS | OC | AF
    altitude_m: Mapped[int] = mapped_column(Integer, default=0)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    player_a_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    player_b_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    round: Mapped[str] = mapped_column(String(20))
    surface: Mapped[str] = mapped_column(String(10))
    best_of: Mapped[int] = mapped_column(Integer, default=3)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="scheduled")  # scheduled | completed | retired

    # Populated for completed/retired matches; drive the fatigue + form engines.
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_sets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    was_decider: Mapped[bool] = mapped_column(Boolean, default=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    retired_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    retired_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)

    tournament: Mapped[Tournament] = relationship(lazy="joined")
    player_a: Mapped[Player] = relationship(foreign_keys=[player_a_id], lazy="joined")
    player_b: Mapped[Player] = relationship(foreign_keys=[player_b_id], lazy="joined")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VenuePrice(Base):
    """One side, one venue, one point in time. The time series powers line movement;
    devig + edge are computed in the pricing engine across the two sides at a snapshot."""
    __tablename__ = "venue_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    venue: Mapped[str] = mapped_column(String(24))            # Pinnacle | DraftKings | Polymarket ...
    venue_type: Mapped[str] = mapped_column(String(4))        # book | pm
    side: Mapped[str] = mapped_column(String(1))              # a | b
    price: Mapped[float] = mapped_column(Float)               # decimal odds
    implied_prob: Mapped[float] = mapped_column(Float)        # raw 1/price (with vig)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolution_rule: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class PressItem(Base):
    __tablename__ = "press_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matches.id"), nullable=True, index=True)
    player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    signal_type: Mapped[str] = mapped_column(String(16))     # injury|withdrawal|practice|motivation|conditions|lineup|other
    claim: Mapped[str] = mapped_column(Text)                  # factual, English-normalized
    source: Mapped[str] = mapped_column(String(80))
    source_lang: Mapped[str] = mapped_column(String(2))
    url: Mapped[str] = mapped_column(String(400))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(12), default="unconfirmed")  # confirmed | unconfirmed
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), index=True)


class Verdict(Base):
    __tablename__ = "verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    call: Mapped[str] = mapped_column(String(8))             # BET | LEAN | PASS | WATCH
    side: Mapped[str] = mapped_column(String(4))             # a | b | none
    thesis: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    model_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_venue: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    drivers_json: Mapped[str] = mapped_column(Text, default="[]")  # structured "why"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
