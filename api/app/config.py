"""Central configuration. Everything is environment-overridable so the app runs
with zero setup (seeded demo) but lights up live sources when keys are present."""
from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # api/
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# The demo data is anchored to a fixed "now" so fatigue math (days rest, minutes
# in the last 7 days, etc.) stays coherent regardless of the wall clock.
# Naive UTC throughout: SQLite drops tzinfo, so we keep everything tz-naive-UTC
# to avoid aware/naive subtraction errors.
DEMO_NOW = datetime(2026, 6, 23, 12, 0, 0)


class Settings:
    db_path: str = os.environ.get("BASELINE_DB", str(DATA_DIR / "baseline.db"))

    # Live-source credentials. Absent -> graceful fallback to seeded/synthetic data.
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    odds_api_key: str = os.environ.get("THE_ODDS_API_KEY", "")

    # Tiered models: cheap one for high-volume extraction, strong one for the verdict.
    extract_model: str = os.environ.get("BASELINE_EXTRACT_MODEL", "claude-haiku-4-5-20251001")
    verdict_model: str = os.environ.get("BASELINE_VERDICT_MODEL", "claude-opus-4-8")

    demo_user_id: str = "demo"

    @property
    def now(self) -> datetime:
        """Reference clock. Pinned to the demo anchor so seeded data reads correctly;
        override with BASELINE_LIVE=1 to use the real wall clock for live operation."""
        if os.environ.get("BASELINE_LIVE") == "1":
            return datetime.utcnow()
        return DEMO_NOW

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
