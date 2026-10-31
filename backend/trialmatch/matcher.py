"""Evaluates a patient against a trial's structured criteria and ranks trials.

Deliberately deterministic: the LLM only converts text into rules. Whether a
patient meets a rule is decided by plain code, so every verdict is
explainable and repeatable, and the model cannot hallucinate eligibility.
"""

from __future__ import annotations

from .models import Category, Criterion, CriterionResult, Location, MatchResult, Patient, Trial, Verdict
from .vocab import conditions_match, medications_match

LAB_NAMES = {"hba1c": "HbA1c", "egfr": "eGFR", "bmi": "BMI", "ldl": "LDL", "systolic_bp": "Systolic BP",
             "ejection_fraction": "LVEF"}


def _compare(actual: float, c: Criterion) -> bool:
    v = float(c.value)  # type: ignore[arg-type]
    match c.operator:
        case ">=":
            return actual >= v
        case "<=":
            return actual <= v
        case ">":
            return actual > v
        case "<":
            return actual < v
        case "==":
            return actual == v
        case "between":
            return v <= actual <= float(c.value_max)  # type: ignore[arg-type]
    raise ValueError(c.operator)


def _describe(c: Criterion) -> str:
    unit = "%" if c.unit == "%" else (f" {c.unit}" if c.unit and c.unit != "years" else "")
    if c.operator == "between":
        return f"between {c.value:g} and {c.value_max:g}{unit}"
    words = {">=": "at least", "<=": "at most", ">": "above", "<": "below", "==": "exactly"}
    op = words.get(c.operator or "", c.operator)
    return f"{op} {c.value:g}{unit}" if isinstance(c.value, (int, float)) else f"{op} {c.value}"


def holds(c: Criterion, p: Patient) -> tuple[bool | None, str]:
    """Whether the criterion's statement is true for the patient (None = unknown)."""
    if not c.is_structured:
        return None, "Needs manual review: not something a program can check."
    field = c.field or ""
    try:
        if c.category == Category.AGE or field == "age":
            if p.age is None:
                return None, "Patient age not provided."
            ok = _compare(p.age, c)
            return ok, f"Age {p.age} is {'' if ok else 'not '}{_describe(c)}."
        if c.category == Category.SEX or field == "sex":
            if p.sex is None:
                return None, "Patient sex not provided."
            ok = p.sex == str(c.value).lower()
            return ok, f"Patient is {p.sex}; trial requires {c.value}." if not ok else f"Patient is {p.sex}."
        if c.category == Category.PREGNANCY:
            if p.pregnant is None:
                return (False, "Pregnancy not mentioned; assumed not pregnant (confirm).") if p.sex == "male" else (None, "Pregnancy status not provided.")
            return p.pregnant, "Patient is pregnant or breastfeeding." if p.pregnant else "Patient is not pregnant."
        if c.category == Category.PERFORMANCE:
            if p.ecog is None:
                return None, "ECOG performance status not provided."
            ok = _compare(p.ecog, c)
            return ok, f"ECOG {p.ecog} is {'' if ok else 'not '}{_describe(c)}."
        if c.category == Category.LAB:
            name = LAB_NAMES.get(field, field)
            if field not in p.labs:
                return None, f"{name} value not provided."
            ok = _compare(p.labs[field], c)
            return ok, f"{name} {p.labs[field]:g} is {'' if ok else 'not '}{_describe(c)}."
        if c.category == Category.CONDITION:
            hit = next((pc for pc in p.conditions if conditions_match(pc, str(c.value))), None)
            if hit:
                return True, f"Patient has {hit}."
            # Absence of a condition in a free-text description is weak evidence.
            return False, f"No {c.value} reported."
        if c.category == Category.MEDICATION:
            hit = next((pm for pm in p.medications if medications_match(pm, str(c.value))), None)
            return (True, f"Patient takes {hit}.") if hit else (False, f"No {c.value} reported.")
    except (TypeError, ValueError):
        return None, "Criterion could not be evaluated."
    return None, "Needs manual review."


def evaluate(c: Criterion, p: Patient) -> CriterionResult:
    result, reason = holds(c, p)
    verdict: Verdict
    if result is None:
        verdict = "unknown"
    elif c.kind == "inclusion":
        verdict = "met" if result else "not_met"
    else:
        verdict = "not_met" if result else "met"
        if result:
            reason = f"Excluded: {reason}"
    # An inclusion condition the patient was never asked about is unknown, not failed.
    if verdict == "not_met" and c.kind == "inclusion" and c.category in (Category.MEDICATION,) and not p.medications:
        verdict, reason = "unknown", "Medications not provided."
    return CriterionResult(criterion=c, verdict=verdict, reason=reason)


def match_trial(trial: Trial, criteria: list[Criterion], patient: Patient) -> MatchResult:
    results = [evaluate(c, patient) for c in criteria]
    met = sum(r.verdict == "met" for r in results)
    not_met = sum(r.verdict == "not_met" for r in results)
    unknown = sum(r.verdict == "unknown" for r in results)

    checkable = met + not_met
    base = met / checkable if checkable else 0.0
    score = round(max(0.0, base * 100 - 3 * unknown), 1) if not not_met else 0.0
    if not_met:
        tier = "not_eligible"
    elif met >= 2 and unknown <= max(2, met):
        tier = "likely"
    else:
        tier = "possible"

    nearby = [loc for loc in trial.locations if patient.state and loc.state == patient.state][:3]
    if tier != "not_eligible" and patient.state and nearby:
        score = min(100.0, score + 5)

    return MatchResult(
        trial=trial,
        tier=tier,
        score=score,
        met=met,
        not_met=not_met,
        unknown=unknown,
        criteria=results,
        nearby_sites=nearby,
        explanation=_explain(tier, results, nearby, patient),
    )


def _explain(tier: str, results: list[CriterionResult], nearby: list[Location], patient: Patient) -> str:
    if tier == "not_eligible":
        failed = [r.reason for r in results if r.verdict == "not_met"][:2]
        return "Not eligible: " + " ".join(failed)
    met = sum(r.verdict == "met" for r in results)
    unknown = sum(r.verdict == "unknown" for r in results)
    parts = [f"Meets {met} checkable criteria with none failed."]
    if unknown:
        parts.append(f"{unknown} {'needs' if unknown == 1 else 'need'} confirmation by the study team.")
    if nearby:
        parts.append(f"Has a site in {patient.state}.")
    elif patient.state:
        parts.append(f"No site listed in {patient.state}.")
    return " ".join(parts)


def rank(results: list[MatchResult]) -> list[MatchResult]:
    order = {"likely": 0, "possible": 1, "not_eligible": 2}
    return sorted(results, key=lambda r: (order[r.tier], -r.score, r.unknown, r.trial.nct_id))
