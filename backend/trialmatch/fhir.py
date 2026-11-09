"""Builds a Patient from FHIR R4 resources (Patient, Condition, Observation, MedicationRequest).

This is what lets the matcher read a patient straight from an EHR through a
SMART on FHIR launch instead of a typed description. Codes are matched by
LOINC (labs) and SNOMED CT (conditions) first, then by display text through
the shared vocabulary.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .models import Patient
from .patient_parser import normalize_patient
from .vocab import find_conditions, find_medications, state_code

# LOINC codes for the labs the matcher understands. Several codes per lab
# because EHRs and Synthea use different variants.
LOINC_LABS: dict[str, str] = {
    "4548-4": "hba1c", "17856-6": "hba1c", "41995-2": "hba1c",
    "33914-3": "egfr", "62238-1": "egfr", "48642-3": "egfr", "48643-1": "egfr", "98979-8": "egfr", "69405-9": "egfr",
    "39156-5": "bmi",
    "8480-6": "systolic_bp",
    "13457-7": "ldl", "18262-6": "ldl", "2089-1": "ldl",
    "10230-1": "ejection_fraction", "18010-0": "ejection_fraction", "8806-2": "ejection_fraction",
}
ECOG_LOINC = {"89247-1", "89262-0"}
BP_PANEL_LOINC = {"85354-9", "55284-4"}

SNOMED_CONDITIONS: dict[str, str] = {
    "44054006": "type 2 diabetes",
    "46635009": "type 1 diabetes",
    "38341003": "hypertension", "59621000": "hypertension",
    "84114007": "heart failure", "88805009": "heart failure", "42343007": "heart failure",
    "709044004": "chronic kidney disease", "431855005": "chronic kidney disease", "433144002": "chronic kidney disease",
    "414916001": "obesity", "162864005": "obesity", "408512008": "obesity",
    "195967001": "asthma", "233678006": "asthma",
    "13645005": "copd", "185086009": "copd",
    "35489007": "major depressive disorder", "370143000": "major depressive disorder", "36923009": "major depressive disorder",
    "13746004": "bipolar disorder",
    "58214004": "schizophrenia",
    "5602001": "opioid use disorder",
    "7200002": "alcohol use disorder",
    "254837009": "breast cancer",
    "254637007": "lung cancer", "162573006": "lung cancer",
    "53741008": "coronary artery disease",
    "22298006": "myocardial infarction", "401303003": "myocardial infarction",
    "230690007": "stroke",
    "49436004": "atrial fibrillation",
    "50711007": "hepatitis c",
    "86406008": "hiv",
}
PREGNANCY_SNOMED = {"77386006", "72892002"}
INACTIVE_STATUSES = {"inactive", "resolved", "remission", "entered-in-error"}


def _codings(concept: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((concept or {}).get("coding") or [])


def _concept_text(concept: dict[str, Any] | None) -> str:
    concept = concept or {}
    parts = [concept.get("text") or ""] + [c.get("display") or "" for c in _codings(concept)]
    return " ".join(p for p in parts if p)


def _status(resource: dict[str, Any], field: str) -> str:
    value = resource.get(field)
    if isinstance(value, dict):
        codes = [c.get("code", "") for c in _codings(value)]
        return codes[0] if codes else ""
    return value or ""


def _when(resource: dict[str, Any]) -> str:
    return resource.get("effectiveDateTime") or (resource.get("effectivePeriod") or {}).get("start") or resource.get("issued") or ""


def _age(birth_date: str | None, today: date) -> int | None:
    if not birth_date:
        return None
    try:
        born = date.fromisoformat(birth_date[:10])
    except ValueError:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def flatten(resources: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Accepts a list of resources, a Bundle, or a list mixing both."""
    items = resources if isinstance(resources, list) else [resources]
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("resourceType") == "Bundle":
            out.extend(flatten([e["resource"] for e in item.get("entry") or [] if "resource" in e]))
        else:
            out.append(item)
    return out


def patient_from_fhir(resources: list[dict[str, Any]] | dict[str, Any], today: date | None = None) -> Patient:
    today = today or date.today()
    items = flatten(resources)

    patient_resource = next((r for r in items if r.get("resourceType") == "Patient"), {})
    gender = patient_resource.get("gender")
    addresses = patient_resource.get("address") or []
    state = state_code(addresses[0].get("state", "")) if addresses and addresses[0].get("state") else None

    conditions: list[str] = []
    pregnant: bool | None = None
    for r in items:
        if r.get("resourceType") != "Condition" or _status(r, "clinicalStatus") in INACTIVE_STATUSES:
            continue
        if _status(r, "verificationStatus") in {"refuted", "entered-in-error"}:
            continue
        codes = {c.get("code") for c in _codings(r.get("code"))}
        if codes & PREGNANCY_SNOMED:
            pregnant = True
            continue
        mapped = [SNOMED_CONDITIONS[c] for c in codes if c in SNOMED_CONDITIONS]
        conditions.extend(mapped or find_conditions(_concept_text(r.get("code")))[:1])

    # Latest value wins for each lab.
    labs: dict[str, tuple[str, float]] = {}
    ecog: tuple[str, int] | None = None

    def keep(lab: str, value: Any, when: str) -> None:
        if isinstance(value, (int, float)) and (lab not in labs or when >= labs[lab][0]):
            labs[lab] = (when, float(value))

    for r in items:
        if r.get("resourceType") != "Observation" or r.get("status") in {"entered-in-error", "cancelled"}:
            continue
        when = _when(r)
        codes = {c.get("code") for c in _codings(r.get("code"))}
        value = (r.get("valueQuantity") or {}).get("value")
        for code in codes:
            if code in LOINC_LABS:
                keep(LOINC_LABS[code], value, when)
            elif code in ECOG_LOINC:
                score = value if value is not None else r.get("valueInteger")
                if score is None:
                    score = next((c.get("code") for c in _codings(r.get("valueCodeableConcept")) if (c.get("code") or "").isdigit()), None)
                if score is not None and (ecog is None or when >= ecog[0]):
                    ecog = (when, int(float(score)))
        if codes & BP_PANEL_LOINC:
            for component in r.get("component") or []:
                for c in _codings(component.get("code")):
                    if c.get("code") in LOINC_LABS:
                        keep(LOINC_LABS[c["code"]], (component.get("valueQuantity") or {}).get("value"), when)

    medications: list[str] = []
    for r in items:
        kind = r.get("resourceType")
        if kind not in {"MedicationRequest", "MedicationStatement"}:
            continue
        if (r.get("status") or "active") not in {"active", "intended", "on-hold"}:
            continue
        text = _concept_text(r.get("medicationCodeableConcept")) or ((r.get("medicationReference") or {}).get("display") or "")
        found = find_medications(text)
        medications.extend(found[:1] or ([text.strip().lower()] if text.strip() else []))

    patient = Patient(
        age=_age(patient_resource.get("birthDate"), today),
        sex=gender if gender in ("male", "female") else None,
        conditions=list(dict.fromkeys(conditions)),
        medications=list(dict.fromkeys(medications)),
        labs={lab: value for lab, (_, value) in labs.items()},
        ecog=ecog[1] if ecog else None,
        pregnant=pregnant if pregnant else (False if gender == "male" else None),
        state=state,
    )
    return normalize_patient(patient)


def display_name(resources: list[dict[str, Any]] | dict[str, Any]) -> str | None:
    """Patient's display name, for the UI only."""
    patient = next((r for r in flatten(resources) if r.get("resourceType") == "Patient"), None)
    names = (patient or {}).get("name") or []
    if not names:
        return None
    name = names[0]
    if name.get("text"):
        return name["text"]
    return " ".join([*(name.get("given") or []), name.get("family") or ""]).strip() or None
