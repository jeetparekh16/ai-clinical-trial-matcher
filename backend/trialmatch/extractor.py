"""Picks the extractor (LLM or rules) and caches results in SQLite.

Extraction is the expensive step, and a trial's criteria rarely change, so
results are cached by a hash of the criteria text. Each trial is paid for
once, not once per patient search.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Literal, Protocol

from . import criteria_rules
from .models import Category, Criterion, Trial

log = logging.getLogger(__name__)


class Extractor(Protocol):
    def extract(self, eligibility_text: str) -> list[Criterion]: ...


class RuleExtractor:
    def extract(self, eligibility_text: str) -> list[Criterion]:
        return criteria_rules.extract(eligibility_text)


class MemoryCache:
    """In-process cache, used where SQLite is unavailable (the browser demo)."""

    def __init__(self) -> None:
        self._data: dict[str, list[Criterion]] = {}

    def get(self, key: str) -> list[Criterion] | None:
        return self._data.get(key)

    def put(self, key: str, extractor: str, criteria: list[Criterion]) -> None:
        self._data[key] = criteria


class CriteriaCache:
    def __init__(self, path: str) -> None:
        import sqlite3

        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS criteria (key TEXT PRIMARY KEY, extractor TEXT NOT NULL, payload TEXT NOT NULL)"
        )

    def get(self, key: str) -> list[Criterion] | None:
        with self._lock:
            row = self._db.execute("SELECT payload FROM criteria WHERE key = ?", (key,)).fetchone()
        return [Criterion.model_validate(c) for c in json.loads(row[0])] if row else None

    def put(self, key: str, extractor: str, criteria: list[Criterion]) -> None:
        payload = json.dumps([c.model_dump(mode="json") for c in criteria])
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO criteria VALUES (?, ?, ?)", (key, extractor, payload))
            self._db.commit()


class CriteriaService:
    """Returns the full list of criteria for a trial: structured fields + extracted text."""

    def __init__(self, primary: Extractor, name: Literal["llm", "rules"], cache: CriteriaCache | MemoryCache) -> None:
        self.primary = primary
        self.name = name
        self.cache = cache
        self._fallback = RuleExtractor()

    def for_trial(self, trial: Trial) -> list[Criterion]:
        structured = self._structured(trial)
        covered = {c.category for c in structured}
        # Age and sex from structured fields are authoritative; drop text duplicates.
        from_text = [c for c in self._from_text(trial.eligibility_text) if c.category not in covered]
        return structured + from_text

    def _from_text(self, text: str) -> list[Criterion]:
        if not text.strip():
            return []
        key = f"{self.name}:{hashlib.sha256(text.encode()).hexdigest()}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            criteria = self.primary.extract(text)
        except Exception as exc:  # noqa: BLE001 - never fail a search because the LLM is down
            log.warning("Primary extractor failed (%s); using rules.", exc)
            return self._fallback.extract(text)
        self.cache.put(key, self.name, criteria)
        return criteria

    @staticmethod
    def _structured(trial: Trial) -> list[Criterion]:
        """ClinicalTrials.gov stores age and sex as fields; use them directly."""
        out: list[Criterion] = []
        if trial.min_age is not None and trial.max_age is not None:
            out.append(Criterion(kind="inclusion", category=Category.AGE, text=f"Age {trial.min_age:g} to {trial.max_age:g} years",
                                 field="age", operator="between", value=trial.min_age, value_max=trial.max_age, unit="years"))
        elif trial.min_age is not None:
            out.append(Criterion(kind="inclusion", category=Category.AGE, text=f"Age {trial.min_age:g} years or older",
                                 field="age", operator=">=", value=trial.min_age, unit="years"))
        elif trial.max_age is not None:
            out.append(Criterion(kind="inclusion", category=Category.AGE, text=f"Age {trial.max_age:g} years or younger",
                                 field="age", operator="<=", value=trial.max_age, unit="years"))
        if trial.sex != "all":
            out.append(Criterion(kind="inclusion", category=Category.SEX, text=f"Sex: {trial.sex}",
                                 field="sex", operator="==", value=trial.sex))
        return out


def build_service(api_key: str | None, model: str, cache_path: str) -> CriteriaService:
    cache = CriteriaCache(cache_path)
    if api_key:
        import anthropic

        from .criteria_llm import LLMExtractor

        return CriteriaService(LLMExtractor(anthropic.Anthropic(api_key=api_key).messages, model), "llm", cache)
    return CriteriaService(RuleExtractor(), "rules", cache)
