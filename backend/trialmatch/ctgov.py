"""ClinicalTrials.gov API v2 client, plus a bundled sample dataset for offline demos."""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import TYPE_CHECKING, Any

from .models import Location, Trial
from .vocab import conditions_match, normalize_condition, state_code

if TYPE_CHECKING:
    import httpx


def _age_years(value: str | None) -> float | None:
    """'18 Years' -> 18.0, '6 Months' -> 0.5, None -> None."""
    if not value:
        return None
    m = re.match(r"(\d+(?:\.\d+)?)\s*(year|month|week|day)", value.strip(), re.IGNORECASE)
    if not m:
        return None
    n = float(m.group(1))
    return {"year": n, "month": n / 12, "week": n / 52, "day": n / 365}[m.group(2).lower()]


def parse_study(study: dict[str, Any]) -> Trial:
    """Map one API v2 study record to a Trial."""
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    elig = p.get("eligibilityModule", {})
    nct = ident.get("nctId", "")
    locations = []
    for loc in p.get("contactsLocationsModule", {}).get("locations", []) or []:
        st = loc.get("state")
        locations.append(Location(
            facility=loc.get("facility"),
            city=loc.get("city"),
            state=(state_code(st) or st) if st else None,
            country=loc.get("country"),
        ))
    sex = (elig.get("sex") or "ALL").lower()
    return Trial(
        nct_id=nct,
        title=ident.get("briefTitle") or ident.get("officialTitle") or nct,
        status=status.get("overallStatus", "UNKNOWN"),
        phases=p.get("designModule", {}).get("phases", []) or [],
        conditions=p.get("conditionsModule", {}).get("conditions", []) or [],
        summary=p.get("descriptionModule", {}).get("briefSummary", "") or "",
        eligibility_text=elig.get("eligibilityCriteria", "") or "",
        sex=sex if sex in ("male", "female") else "all",
        min_age=_age_years(elig.get("minimumAge")),
        max_age=_age_years(elig.get("maximumAge")),
        healthy_volunteers=bool(elig.get("healthyVolunteers", False)),
        locations=locations,
        url=f"https://clinicaltrials.gov/study/{nct}" if nct.startswith("NCT") and nct[3:].isdigit() else "",
    )


class ClinicalTrialsClient:
    """Searches recruiting studies. https://clinicaltrials.gov/data-api/api"""

    FIELDS = ",".join([
        "NCTId", "BriefTitle", "OfficialTitle", "OverallStatus", "Phase", "Condition", "BriefSummary",
        "EligibilityCriteria", "Sex", "MinimumAge", "MaximumAge", "HealthyVolunteers",
        "LocationFacility", "LocationCity", "LocationState", "LocationCountry",
    ])

    def __init__(self, base_url: str = "https://clinicaltrials.gov/api/v2", http: httpx.Client | None = None) -> None:
        # Imported here so the package also runs in the browser (Pyodide) without httpx.
        import httpx

        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=20.0, headers={"User-Agent": "ai-clinical-trial-matcher/1.0"})

    def search(self, condition: str, state: str | None = None, limit: int = 40) -> list[Trial]:
        params = self.search_params(condition, state, limit)
        response = self.http.get(f"{self.base_url}/studies", params=params)
        response.raise_for_status()
        return [parse_study(s) for s in response.json().get("studies", [])]

    @classmethod
    def search_params(cls, condition: str, state: str | None = None, limit: int = 40) -> dict[str, Any]:
        """Query parameters for a recruiting-studies search (shared with the browser demo)."""
        params: dict[str, Any] = {
            "query.cond": condition,
            "filter.overallStatus": "RECRUITING",
            "pageSize": min(limit, 100),
            "fields": cls.FIELDS,
            "format": "json",
        }
        if state:
            params["query.locn"] = state
        return params


class SampleTrials:
    """Bundled demo trials in the same JSON format as the API. Synthetic, not real studies."""

    def __init__(self) -> None:
        raw = resources.files("trialmatch").joinpath("sample_data/studies.json").read_text(encoding="utf-8")
        self.trials = [parse_study(s) for s in json.loads(raw)["studies"]]

    def search(self, condition: str, state: str | None = None, limit: int = 40) -> list[Trial]:
        wanted = normalize_condition(condition)
        hits = [t for t in self.trials if any(conditions_match(c, wanted) for c in t.conditions)
                or wanted.lower() in t.title.lower()]
        return hits[:limit]
