"""Rule-based eligibility criteria extractor.

Turns ClinicalTrials.gov free-text eligibility criteria into structured
`Criterion` objects with regular expressions and the vocabulary in vocab.py.
It runs offline with no API key, and it is the baseline the LLM extractor is
measured against in eval/.
"""

from __future__ import annotations

import re

from .models import Category, Criterion
from .vocab import LABS, SPECIFIC_CONDITIONS, find_conditions, find_labs, find_medications

_SECTION = re.compile(r"^\s*(inclusion|exclusion)\s+criteria\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[*\-•●]|\d{1,2}[.)]|[a-z][.)])\s+", re.IGNORECASE)

_NUM = r"(\d+(?:\.\d+)?)"
# Order matters: two-word phrases before single symbols.
_COMPARATORS: list[tuple[str, str]] = [
    (r"≥|>=|=>|greater than or equal to|at least|no less than|minimum of", ">="),
    (r"≤|<=|=<|less than or equal to|at most|no more than|up to|maximum of", "<="),
    (r">|greater than|more than|above|exceeding|over", ">"),
    (r"<|less than|below|under|lower than", "<"),
]
_POST_COMPARATORS: list[tuple[str, str]] = [
    (r"or (?:more|higher|greater|above|older)", ">="),
    (r"or (?:less|lower|below|younger)", "<="),
]


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return (kind, bullet text) pairs from a ClinicalTrials.gov criteria block."""
    text = text.replace("\r\n", "\n")
    parts = _SECTION.split(text)
    if len(parts) < 3:
        # No headers: treat everything as inclusion.
        return [("inclusion", b) for b in _bullets(text)]
    out: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        kind = parts[i].lower()
        out.extend((kind, b) for b in _bullets(parts[i + 1]))
    return out


def _bullets(block: str) -> list[str]:
    bullets: list[str] = []
    current: list[str] = []
    for line in block.split("\n"):
        if not line.strip():
            if current:
                bullets.append(" ".join(current))
                current = []
            continue
        if _BULLET.match(line):
            if current:
                bullets.append(" ".join(current))
            current = [_BULLET.sub("", line, count=1).strip()]
        else:
            current.append(line.strip())
    if current:
        bullets.append(" ".join(current))
    return [re.sub(r"\s+", " ", b).strip() for b in bullets if len(b.strip()) > 2]


def parse_threshold(text: str) -> tuple[str, float, float | None] | None:
    """Find a numeric condition such as '≥ 7.5', 'between 7 and 10', '18 years or older'.

    Returns (operator, value, value_max) or None.
    """
    t = text.lower()
    m = re.search(rf"between\s+{_NUM}\s*%?\s*(?:and|to|-|–)\s*{_NUM}", t) or \
        re.search(rf"(?<![\w.]){_NUM}\s*%?\s*(?:-|–|to)\s*{_NUM}(?!\s*(?:hours|days|weeks|months)\b)", t) or \
        re.search(rf"from\s+{_NUM}\s*%?\s*(?:to|-|–)\s*{_NUM}", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo < hi:
            return "between", lo, hi
    for pattern, op in _COMPARATORS:
        m = re.search(rf"(?:{pattern})\s*(?:of\s+|than\s+)?{_NUM}", t)
        if m:
            return op, float(m.group(1)), None
    for pattern, op in _POST_COMPARATORS:
        m = re.search(rf"{_NUM}\s*(?:%|years?(?: of age)?|[a-z/²0-9.]+)?\s*(?:{pattern})", t)
        if m:
            return op, float(m.group(1)), None
    return None


def _lab_criterion(kind: str, text: str) -> Criterion | None:
    labs = find_labs(text)
    if not labs:
        return None
    lab, _, end = labs[0]
    # Look for the threshold after the lab name first, then anywhere.
    threshold = parse_threshold(text[end:]) or parse_threshold(text)
    if not threshold:
        return None
    op, value, value_max = threshold
    return Criterion(kind=kind, category=Category.LAB, text=text, field=lab, operator=op,
                     value=value, value_max=value_max, unit=LABS[lab][1])


def _age_criterion(kind: str, text: str) -> Criterion | None:
    t = text.lower()
    if not re.search(r"\b(age|aged|years? old|years of age|years or older|adults?)\b", t):
        return None
    threshold = parse_threshold(t)
    if not threshold:
        return None
    op, value, value_max = threshold
    if not 0 < value < 120:
        return None
    return Criterion(kind=kind, category=Category.AGE, text=text, field="age", operator=op,
                     value=value, value_max=value_max, unit="years")


def _ecog_criterion(kind: str, text: str) -> Criterion | None:
    t = text.lower()
    if "ecog" not in t and "performance status" not in t:
        return None
    m = re.search(r"(?:ecog|performance status)[^0-9]{0,40}?([0-4])\s*(?:-|–|to|or|,)\s*(?:[0-4]\s*(?:,|or)\s*)?([0-4])", t)
    if m:
        return Criterion(kind=kind, category=Category.PERFORMANCE, text=text, field="ecog", operator="<=",
                         value=float(max(int(m.group(1)), int(m.group(2)))))
    threshold = parse_threshold(t)
    if threshold:
        op, value, value_max = threshold
        return Criterion(kind=kind, category=Category.PERFORMANCE, text=text, field="ecog", operator=op,
                         value=value, value_max=value_max)
    return None


def _pregnancy_criterion(kind: str, text: str) -> Criterion | None:
    if re.search(r"\b(pregnan\w*|breast[- ]?feeding|lactating|nursing)\b", text, re.IGNORECASE):
        if re.search(r"contracepti|childbearing potential must|negative pregnancy test", text, re.IGNORECASE) and kind == "inclusion":
            return None
        return Criterion(kind=kind, category=Category.PREGNANCY, text=text, field="pregnancy", operator="present",
                         value="pregnant or breastfeeding")
    return None


def _sex_criterion(kind: str, text: str) -> Criterion | None:
    t = text.lower()
    if re.fullmatch(r"(?:\w+\s){0,3}(women|females?)(\s\w+){0,3}", t) or re.search(r"\b(post-?menopausal women|female participants only|women only)\b", t):
        return Criterion(kind=kind, category=Category.SEX, text=text, field="sex", operator="==", value="female")
    if re.search(r"\b(male participants only|men only)\b", t):
        return Criterion(kind=kind, category=Category.SEX, text=text, field="sex", operator="==", value="male")
    return None


def _medication_criterion(kind: str, text: str) -> Criterion | None:
    meds = find_medications(text)
    if not meds:
        return None
    t = text.lower()
    if not re.search(r"\b(taking|treated|treatment|therapy|use of|using|receiving|on|received|current|stable dose|prescribed)\b", t):
        return None
    return Criterion(kind=kind, category=Category.MEDICATION, text=text, field="medication", operator="present",
                     value=meds[0])


def _condition_criterion(kind: str, text: str) -> Criterion | None:
    conditions = find_conditions(text)
    if not conditions:
        return None
    specific = [c for c in conditions if c in SPECIFIC_CONDITIONS]
    return Criterion(kind=kind, category=Category.CONDITION, text=text, field="condition", operator="present",
                     value=(specific or conditions)[0])


# Most specific first: a bullet like "HbA1c 7-10% in patients with T2D" is a
# lab criterion, not a condition criterion.
_RULES = (_pregnancy_criterion, _ecog_criterion, _lab_criterion, _age_criterion, _sex_criterion,
          _medication_criterion, _condition_criterion)


_INTENT = re.compile(r"^\s*(?:participants? (?:must be |is )?)?(willing|able|agrees?|consents?|provides?|capable)\b", re.IGNORECASE)


def classify(kind: str, text: str) -> Criterion:
    # "Willing to start buprenorphine" is about consent, not current medication.
    if _INTENT.match(text):
        return Criterion(kind=kind, category=Category.OTHER, text=text)
    for rule in _RULES:
        criterion = rule(kind, text)
        if criterion is not None:
            return criterion
    return Criterion(kind=kind, category=Category.OTHER, text=text)


def extract(eligibility_text: str) -> list[Criterion]:
    out: list[Criterion] = []
    for kind, bullet in split_sections(eligibility_text):
        criterion = classify(kind, bullet)
        out.append(criterion)
        # "Bipolar disorder or schizophrenia" under exclusions excludes both.
        if kind == "exclusion" and criterion.category == Category.CONDITION:
            for extra in find_conditions(bullet):
                if extra != criterion.value and extra not in SPECIFIC_CONDITIONS and criterion.value not in SPECIFIC_CONDITIONS:
                    out.append(criterion.model_copy(update={"value": extra}))
    return out
