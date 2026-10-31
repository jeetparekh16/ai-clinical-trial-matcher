"""Settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None)
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-haiku-5-5"))
    # "live" queries ClinicalTrials.gov; "sample" uses the bundled demo trials.
    data_source: str = field(default_factory=lambda: os.getenv("TRIAL_DATA_SOURCE", "live"))
    cache_path: str = field(default_factory=lambda: os.getenv("CRITERIA_CACHE_PATH", ".cache/criteria.sqlite3"))
    ctgov_base_url: str = field(default_factory=lambda: os.getenv("CTGOV_BASE_URL", "https://clinicaltrials.gov/api/v2"))
    max_trials_screened: int = field(default_factory=lambda: int(os.getenv("MAX_TRIALS_SCREENED", "40")))
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)
