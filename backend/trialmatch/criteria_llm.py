"""LLM eligibility criteria extractor (structured output via tool use).

The model reads the free-text criteria and records them through a tool whose
input schema is the `Criterion` model, so the response is always valid,
typed JSON. Output is normalised through vocab.py so LLM and rule results
share the same condition, medication and lab names.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from .models import Category, Criterion
from .vocab import normalize_condition, normalize_lab, normalize_medication

SYSTEM_PROMPT = """You convert clinical trial eligibility criteria into structured rules a program can check.

Rules:
- Return one item per bullet of the original text, keeping its order. Copy the bullet text verbatim into "text".
- "kind" is "inclusion" or "exclusion", taken from the section the bullet is in.
- Exclusion items describe what must NOT be true. "No history of stroke" under exclusions is {"kind":"exclusion","category":"condition","field":"condition","operator":"present","value":"stroke"}.
- Use these fields: "age" (years), "sex" ("male"/"female", operator "=="), "condition", "medication", "pregnancy",
  "ecog", and labs "hba1c" (%), "egfr" (mL/min/1.73m2), "bmi" (kg/m2), "ldl" (mg/dL), "systolic_bp" (mmHg), "ejection_fraction" (%).
- Conditions and medications use operator "present" and a short generic name in "value" (e.g. "type 2 diabetes", "insulin").
- Numeric ranges use operator "between" with "value" (low) and "value_max" (high). "ECOG 0-1" is operator "<=" value 1.
- If a bullet cannot be expressed with these fields (consent, willingness, investigator judgment, procedures), use category "other" and leave field, operator and value null. Never invent thresholds."""

_TOOL = {
    "name": "record_criteria",
    "description": "Record the structured eligibility criteria.",
    "input_schema": {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["inclusion", "exclusion"]},
                        "category": {"type": "string", "enum": [c.value for c in Category]},
                        "text": {"type": "string"},
                        "field": {"type": ["string", "null"]},
                        "operator": {"type": ["string", "null"], "enum": [">=", "<=", ">", "<", "==", "between", "present", None]},
                        "value": {"type": ["number", "string", "null"]},
                        "value_max": {"type": ["number", "null"]},
                        "unit": {"type": ["string", "null"]},
                    },
                    "required": ["kind", "category", "text"],
                },
            }
        },
        "required": ["criteria"],
    },
}


class MessagesClient(Protocol):
    """The part of anthropic.Anthropic().messages this module uses (eases testing)."""

    def create(self, **kwargs: Any) -> Any: ...


class LLMExtractor:
    def __init__(self, messages: MessagesClient, model: str, max_tokens: int = 4096) -> None:
        self.messages = messages
        self.model = model
        self.max_tokens = max_tokens

    def extract(self, eligibility_text: str) -> list[Criterion]:
        response = self.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_criteria"},
            messages=[{"role": "user", "content": f"Eligibility criteria:\n\n{eligibility_text}"}],
        )
        payload = _tool_input(response)
        return [c for c in (_to_criterion(raw) for raw in payload.get("criteria", [])) if c is not None]


def _tool_input(response: Any) -> dict[str, Any]:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "record_criteria":
            data = block.input
            return json.loads(data) if isinstance(data, str) else dict(data)
    raise ValueError("Model did not return structured criteria.")


def _to_criterion(raw: dict[str, Any]) -> Criterion | None:
    try:
        c = Criterion.model_validate(raw)
    except Exception:  # noqa: BLE001 - one malformed item should not drop the rest
        return None
    if c.category == Category.CONDITION and isinstance(c.value, str):
        c.value = normalize_condition(c.value)
    elif c.category == Category.MEDICATION and isinstance(c.value, str):
        c.value = normalize_medication(c.value)
    elif c.category == Category.LAB and c.field:
        c.field = normalize_lab(c.field) or c.field
    if c.operator == "between" and c.value_max is None:
        c.operator = ">="
    return c
