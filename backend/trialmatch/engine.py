"""Transport-independent matching pipeline.

Used by the FastAPI app and by the browser demo, where this package runs
inside Pyodide (Python compiled to WebAssembly) with no server at all.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from . import matcher
from .ctgov import SampleTrials, parse_study
from .extractor import CriteriaService, MemoryCache, RuleExtractor
from .models import MatchRequest, MatchResponse, Patient, Trial
from .patient_parser import normalize_patient, parse_rules
from .vocab import normalize_condition

SAMPLE_NOTICE = "Demo mode: results use synthetic sample trials, not real studies."
UNREACHABLE_NOTICE = "ClinicalTrials.gov could not be reached, so these results use the bundled demo trials."


class MatchInputError(ValueError):
    """The request cannot be matched (no patient, or no condition to search)."""


def resolve_patient(request: MatchRequest, parse=parse_rules) -> tuple[Patient, str]:
    """Return the structured patient and the condition to search for."""
    if request.patient is not None:
        patient = normalize_patient(request.patient)
    elif request.patient_description:
        patient = parse(request.patient_description)
    else:
        raise MatchInputError("Provide patient_description or patient.")

    condition = (request.condition or (patient.conditions[0] if patient.conditions else "")).strip()
    if not condition:
        raise MatchInputError("Could not tell which condition to search for. Add a condition.")
    # The searched condition is the reason for enrolling; count it as present.
    canonical = normalize_condition(condition)
    if canonical not in patient.conditions:
        patient = patient.model_copy(update={"conditions": [canonical, *patient.conditions]})
    return patient, condition


def run_match(
    patient: Patient,
    condition: str,
    trials: list[Trial],
    service: CriteriaService,
    data_source: Literal["clinicaltrials.gov", "sample"],
    limit: int,
    notice: str | None = None,
) -> MatchResponse:
    if data_source == "sample" and notice is None:
        notice = SAMPLE_NOTICE
    results = matcher.rank([matcher.match_trial(t, service.for_trial(t), patient) for t in trials])
    return MatchResponse(
        patient=patient,
        condition=condition,
        data_source=data_source,
        extractor=service.name,
        trials_screened=len(trials),
        results=results[:limit],
        notice=notice,
    )


# Browser entry points. Inputs and outputs are JSON strings so the JavaScript
# side never touches Python objects.

_browser_service: CriteriaService | None = None
_sample: SampleTrials | None = None


def _service() -> CriteriaService:
    global _browser_service
    if _browser_service is None:
        _browser_service = CriteriaService(RuleExtractor(), "rules", MemoryCache())
    return _browser_service


def browser_prepare(request_json: str) -> str:
    """Parse the patient and return {"patient", "condition"} or {"error"}."""
    try:
        request = MatchRequest.model_validate_json(request_json)
        patient, condition = resolve_patient(request)
    except (MatchInputError, ValueError) as exc:
        return json.dumps({"error": _message(exc)})
    return json.dumps({"patient": patient.model_dump(mode="json"), "condition": condition})


def browser_match(request_json: str, studies_json: str | None = None, live_failed: bool = False) -> str:
    """Match a patient against studies fetched by the browser, or the sample set.

    studies_json is a ClinicalTrials.gov API v2 response body. When it is
    missing or empty, the bundled sample trials are used.
    """
    global _sample
    try:
        request = MatchRequest.model_validate_json(request_json)
        patient, condition = resolve_patient(request)
    except (MatchInputError, ValueError) as exc:
        return json.dumps({"error": _message(exc)})

    studies: list[dict[str, Any]] = json.loads(studies_json).get("studies", []) if studies_json else []
    notice = None
    if studies:
        trials = [parse_study(s) for s in studies]
        source: Literal["clinicaltrials.gov", "sample"] = "clinicaltrials.gov"
    else:
        _sample = _sample or SampleTrials()
        trials = _sample.search(condition, limit=40)
        source = "sample"
        notice = UNREACHABLE_NOTICE if live_failed else None
    response = run_match(patient, condition, trials, _service(), source, request.limit, notice)
    return response.model_dump_json()


def fhir_patient(resources: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    """Structured patient and display name from FHIR resources."""
    from .fhir import display_name, patient_from_fhir

    return {"patient": patient_from_fhir(resources).model_dump(mode="json"), "name": display_name(resources)}


def browser_fhir_patient(resources_json: str) -> str:
    try:
        return json.dumps(fhir_patient(json.loads(resources_json)))
    except (ValueError, TypeError, KeyError, AttributeError):
        return json.dumps({"error": "The EHR returned data this app could not read."})


def _message(exc: Exception) -> str:
    if isinstance(exc, MatchInputError):
        return str(exc)
    return "Check the description and try again."
