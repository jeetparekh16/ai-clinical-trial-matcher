"""Turns a plain-English patient description into a structured Patient.

Example: "58 year old woman in Maryland with type 2 diabetes, A1c 8.4%,
eGFR 72, on metformin" -> Patient(age=58, sex="female", state="MD", ...).

With an API key, the LLM does the parsing (handles any phrasing); without
one, regular expressions cover the common patterns.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .models import Patient
from .vocab import (
    LABS,
    US_STATES,
    find_conditions,
    find_labs,
    find_medications,
    normalize_condition,
    normalize_lab,
    normalize_medication,
    state_code,
)

_NEGATION = re.compile(r"\b(no|not|denies|without|negative for|never)\b[^.;,]{0,40}$", re.IGNORECASE)


def parse_rules(text: str) -> Patient:
    t = " " + text.strip() + " "
    lower = t.lower()

    age = None
    m = re.search(r"\b(\d{1,3})\s*(?:-|\s)?\s*(?:years?|yrs?|yo|y/o|y\.o\.)\b", lower) or re.search(r"\baged?\s*(\d{1,3})\b", lower)
    if m and 0 < int(m.group(1)) < 120:
        age = int(m.group(1))

    sex = None
    if re.search(r"\b(woman|female|she|her|lady|girl|mother)\b", lower):
        sex = "female"
    elif re.search(r"\b(man|male|he|his|gentleman|boy|father)\b", lower):
        sex = "male"
    if re.search(r"\b(\d{1,3})\s*(?:yo|y/o)?\s*f\b", lower) and sex is None:
        sex = "female"

    conditions = [c for c in find_conditions(t) if not _negated(t, c)]
    medications = [m for m in find_medications(t) if not _negated(t, m)]

    labs: dict[str, float] = {}
    for lab, _, end in find_labs(t):
        num = re.match(r"\s*(?:of|is|was|=|:|at)?\s*(\d+(?:\.\d+)?)", t[end:end + 20], re.IGNORECASE)
        if num and lab not in labs:
            labs[lab] = float(num.group(1))

    ecog = None
    m = re.search(r"ecog(?:\s*(?:performance status|ps))?\s*(?:of|is|=|:)?\s*([0-4])\b", lower)
    if m:
        ecog = int(m.group(1))

    pregnant = None
    if re.search(r"\b(not|isn't|is not|non)[- ]?pregnant\b", lower):
        pregnant = False
    elif re.search(r"\b(pregnant|pregnancy|breast-?feeding|lactating)\b", lower):
        pregnant = True

    return Patient(age=age, sex=sex, conditions=conditions, medications=medications, labs=labs,
                   ecog=ecog, pregnant=pregnant, state=_find_state(t))


def _negated(text: str, canonical: str) -> bool:
    """True if every mention of the term is preceded by a negation ("no history of asthma")."""
    from .vocab import CONDITIONS, MEDICATIONS

    synonyms = CONDITIONS.get(canonical) or MEDICATIONS.get(canonical) or [canonical]
    mentions = [m for s in synonyms for m in re.finditer(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", text, re.IGNORECASE)]
    return bool(mentions) and all(_NEGATION.search(text[max(0, m.start() - 60):m.start()]) for m in mentions)


def _find_state(text: str) -> str | None:
    lower = text.lower()
    for name in sorted(US_STATES, key=len, reverse=True):
        if re.search(rf"\b(?:in|from|lives in|located in|near)\s+{re.escape(name)}\b", lower):
            return US_STATES[name]
    m = re.search(r",\s*([A-Z]{2})\b", text)
    if m and state_code(m.group(1)):
        return m.group(1)
    for name in sorted(US_STATES, key=len, reverse=True):
        # Skip names that are also common first names or a city.
        if name not in ("washington", "georgia") and re.search(rf"\b{re.escape(name)}\b", lower):
            return US_STATES[name]
    return None


_PATIENT_TOOL = {
    "name": "record_patient",
    "description": "Record the structured patient profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "age": {"type": ["integer", "null"]},
            "sex": {"type": ["string", "null"], "enum": ["male", "female", None]},
            "conditions": {"type": "array", "items": {"type": "string"}, "description": "Current diagnoses, generic names."},
            "medications": {"type": "array", "items": {"type": "string"}, "description": "Current medications."},
            "labs": {
                "type": "object",
                "description": f"Lab values keyed by: {', '.join(LABS)}.",
                "additionalProperties": {"type": "number"},
            },
            "ecog": {"type": ["integer", "null"]},
            "pregnant": {"type": ["boolean", "null"]},
            "state": {"type": ["string", "null"], "description": "Two-letter US state code."},
        },
        "required": ["conditions", "medications", "labs"],
    },
}


class LLMPatientParser:
    def __init__(self, messages: Any, model: str) -> None:
        self.messages = messages
        self.model = model

    def parse(self, text: str) -> Patient:
        response = self.messages.create(
            model=self.model,
            max_tokens=1024,
            system="Extract a structured patient profile from the description. Only record facts stated; use null when unknown. "
                   "Conditions the patient does NOT have must be left out.",
            tools=[_PATIENT_TOOL],
            tool_choice={"type": "tool", "name": "record_patient"},
            messages=[{"role": "user", "content": text}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                data = block.input if isinstance(block.input, dict) else json.loads(block.input)
                return normalize_patient(Patient.model_validate(data))
        raise ValueError("Model did not return a patient profile.")


def normalize_patient(patient: Patient) -> Patient:
    labs = {}
    for name, value in patient.labs.items():
        key = normalize_lab(name)
        if key:
            labs[key] = value
    return patient.model_copy(update={
        "conditions": list(dict.fromkeys(normalize_condition(c) for c in patient.conditions)),
        "medications": list(dict.fromkeys(normalize_medication(m) for m in patient.medications)),
        "labs": labs,
        "state": state_code(patient.state) if patient.state else None,
    })
