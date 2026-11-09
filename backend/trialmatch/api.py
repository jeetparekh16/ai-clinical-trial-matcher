"""FastAPI application: patient description in, ranked and explained trial matches out."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .ctgov import ClinicalTrialsClient, SampleTrials
from .engine import UNREACHABLE_NOTICE, MatchInputError, resolve_patient, run_match
from .extractor import CriteriaService, build_service
from .models import MatchRequest, MatchResponse, ParsePatientRequest, Patient, Trial
from .patient_parser import LLMPatientParser, parse_rules

log = logging.getLogger(__name__)


class TrialSource(Protocol):
    def search(self, condition: str, state: str | None = None, limit: int = 40) -> list[Trial]: ...


class PatientParser(Protocol):
    def parse(self, text: str) -> Patient: ...


class RulePatientParser:
    def parse(self, text: str) -> Patient:
        return parse_rules(text)


def create_app(
    settings: Settings | None = None,
    trial_source: TrialSource | None = None,
    criteria_service: CriteriaService | None = None,
    patient_parser: PatientParser | None = None,
) -> FastAPI:
    settings = settings or Settings()
    sample = SampleTrials()
    live_mode = settings.data_source == "live" and trial_source is None
    source: TrialSource = trial_source or (ClinicalTrialsClient(settings.ctgov_base_url) if live_mode else sample)
    service = criteria_service or build_service(settings.anthropic_api_key, settings.llm_model, settings.cache_path)
    rules_parser = RulePatientParser()
    parser: PatientParser = patient_parser or (
        LLMPatientParser(__import__("anthropic").Anthropic(api_key=settings.anthropic_api_key).messages, settings.llm_model)
        if settings.llm_enabled else rules_parser
    )

    app = FastAPI(
        title="AI Clinical Trial Matcher",
        version="1.0.0",
        description="Matches a patient description to recruiting clinical trials, with a per-criterion explanation.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def parse_patient(text: str) -> Patient:
        try:
            return parser.parse(text)
        except Exception as exc:  # noqa: BLE001 - degrade to rules rather than fail
            log.warning("Patient parser failed (%s); using rules.", exc)
            return rules_parser.parse(text)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "extractor": service.name,
            "data_source": "clinicaltrials.gov" if isinstance(source, ClinicalTrialsClient) else "sample",
        }

    @app.post("/api/parse-patient", response_model=Patient)
    def parse_patient_endpoint(body: ParsePatientRequest) -> Patient:
        return parse_patient(body.text)

    @app.post("/api/match", response_model=MatchResponse)
    def match(body: MatchRequest) -> MatchResponse:
        try:
            patient, condition = resolve_patient(body, parse=parse_patient)
        except MatchInputError as exc:
            raise HTTPException(422, str(exc)) from exc

        data_source = "clinicaltrials.gov" if isinstance(source, ClinicalTrialsClient) else "sample"
        notice = None
        try:
            trials = source.search(condition, state=None, limit=settings.max_trials_screened)
        except httpx.HTTPError as exc:
            log.warning("ClinicalTrials.gov unavailable (%s); using sample trials.", exc)
            trials = sample.search(condition, limit=settings.max_trials_screened)
            data_source = "sample"
            notice = UNREACHABLE_NOTICE
        return run_match(patient, condition, trials, service, data_source, body.limit, notice)

    return app


app = create_app()
