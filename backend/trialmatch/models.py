"""Data models shared by the extractor, matcher and API."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Category(StrEnum):
    AGE = "age"
    SEX = "sex"
    CONDITION = "condition"
    LAB = "lab"
    MEDICATION = "medication"
    PREGNANCY = "pregnancy"
    PERFORMANCE = "performance_status"
    OTHER = "other"


Operator = Literal[">=", "<=", ">", "<", "==", "between", "present"]


class Criterion(BaseModel):
    """One eligibility rule, in a form a program can evaluate.

    Exclusion criteria describe what must NOT be true: for an exclusion with
    operator "present" and value "type 1 diabetes", a patient with type 1
    diabetes is excluded.
    """

    kind: Literal["inclusion", "exclusion"]
    category: Category
    text: str = Field(description="The original criterion text, verbatim.")
    field: str | None = Field(
        default=None,
        description="What is measured: 'age', 'sex', 'condition', 'medication', 'pregnancy', "
        "'ecog', or a lab: 'hba1c', 'egfr', 'bmi', 'ldl', 'systolic_bp', 'ejection_fraction'.",
    )
    operator: Operator | None = None
    value: float | str | None = Field(
        default=None,
        description="Threshold (number) or name (condition, medication, sex). For 'between', the lower bound.",
    )
    value_max: float | None = Field(default=None, description="Upper bound for 'between'.")
    unit: str | None = None

    @property
    def is_structured(self) -> bool:
        return self.field is not None and self.operator is not None


class Location(BaseModel):
    facility: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


class Trial(BaseModel):
    nct_id: str
    title: str
    status: str
    phases: list[str] = []
    conditions: list[str] = []
    summary: str = ""
    eligibility_text: str = ""
    sex: Literal["all", "male", "female"] = "all"
    min_age: float | None = None
    max_age: float | None = None
    healthy_volunteers: bool = False
    locations: list[Location] = []
    url: str = ""


class Patient(BaseModel):
    age: int | None = None
    sex: Literal["male", "female"] | None = None
    conditions: list[str] = []
    medications: list[str] = []
    labs: dict[str, float] = Field(default_factory=dict, description="Canonical lab name -> value.")
    ecog: int | None = None
    pregnant: bool | None = None
    state: str | None = Field(default=None, description="Two-letter US state code.")


Verdict = Literal["met", "not_met", "unknown"]


class CriterionResult(BaseModel):
    criterion: Criterion
    verdict: Verdict
    reason: str


class MatchResult(BaseModel):
    trial: Trial
    tier: Literal["likely", "possible", "not_eligible"]
    score: float = Field(description="0-100. Share of checkable criteria the patient meets, minus a penalty for unknowns.")
    met: int
    not_met: int
    unknown: int
    criteria: list[CriterionResult]
    nearby_sites: list[Location] = []
    explanation: str


class MatchRequest(BaseModel):
    patient_description: str | None = Field(default=None, max_length=4000)
    patient: Patient | None = None
    condition: str | None = Field(default=None, max_length=200, description="Condition to search trials for.")
    limit: int = Field(default=10, ge=1, le=50)


class MatchResponse(BaseModel):
    patient: Patient
    condition: str
    data_source: Literal["clinicaltrials.gov", "sample"]
    extractor: Literal["llm", "rules"]
    trials_screened: int
    results: list[MatchResult]
    notice: str | None = None


class ParsePatientRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
