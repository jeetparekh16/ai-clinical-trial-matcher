"""Medical vocabulary used to normalise free text: conditions, medications, labs.

Small and hand-curated on purpose. It is the offline fallback and the
normaliser for LLM output, not a replacement for a terminology service such
as UMLS or RxNorm.
"""

from __future__ import annotations

import re

# canonical name -> synonyms (lowercase). Longest synonyms are matched first.
CONDITIONS: dict[str, list[str]] = {
    "type 2 diabetes": ["type 2 diabetes", "type ii diabetes", "t2dm", "t2d", "diabetes mellitus type 2",
                        "type 2 diabetes mellitus", "non-insulin-dependent diabetes", "adult-onset diabetes"],
    "type 1 diabetes": ["type 1 diabetes", "type i diabetes", "t1dm", "t1d", "diabetes mellitus type 1",
                        "type 1 diabetes mellitus", "juvenile diabetes"],
    "hypertension": ["hypertension", "high blood pressure", "htn", "elevated blood pressure"],
    "heart failure": ["heart failure", "chf", "congestive heart failure", "hfref", "hfpef", "cardiac failure"],
    "chronic kidney disease": ["chronic kidney disease", "ckd", "renal insufficiency", "kidney disease"],
    "dialysis": ["dialysis", "hemodialysis", "end-stage renal disease", "esrd", "kidney transplant"],
    "obesity": ["obesity", "obese", "morbid obesity"],
    "asthma": ["asthma"],
    "copd": ["copd", "chronic obstructive pulmonary disease", "emphysema", "chronic bronchitis"],
    "major depressive disorder": ["major depressive disorder", "mdd", "major depression", "depression",
                                  "clinical depression"],
    "bipolar disorder": ["bipolar disorder", "bipolar"],
    "schizophrenia": ["schizophrenia", "schizoaffective"],
    "opioid use disorder": ["opioid use disorder", "oud", "opioid dependence", "opioid addiction"],
    "alcohol use disorder": ["alcohol use disorder", "aud", "alcohol dependence", "alcoholism"],
    "breast cancer": ["breast cancer", "breast carcinoma", "carcinoma of the breast"],
    "lung cancer": ["lung cancer", "non-small cell lung cancer", "nsclc", "small cell lung cancer"],
    "cancer": ["active malignancy", "malignancy", "cancer"],
    "coronary artery disease": ["coronary artery disease", "cad", "coronary heart disease"],
    "myocardial infarction": ["myocardial infarction", "heart attack", "mi"],
    "stroke": ["stroke", "cerebrovascular accident", "cva"],
    "hepatitis c": ["hepatitis c", "hcv"],
    "hiv": ["hiv", "human immunodeficiency virus"],
    "liver disease": ["liver disease", "cirrhosis", "hepatic impairment"],
    "pancreatitis": ["pancreatitis"],
    "atrial fibrillation": ["atrial fibrillation", "afib", "a-fib"],
}

MEDICATIONS: dict[str, list[str]] = {
    "insulin": ["insulin"],
    "metformin": ["metformin"],
    "glp-1 receptor agonist": ["glp-1 receptor agonist", "glp-1 agonist", "glp-1 ra", "glp-1", "semaglutide",
                               "liraglutide", "dulaglutide", "tirzepatide"],
    "sglt2 inhibitor": ["sglt2 inhibitor", "sglt-2 inhibitor", "sglt2", "empagliflozin", "dapagliflozin",
                        "canagliflozin"],
    "warfarin": ["warfarin", "coumadin"],
    "anticoagulant": ["anticoagulant", "anticoagulation", "apixaban", "rivaroxaban", "blood thinner"],
    "buprenorphine": ["buprenorphine", "suboxone"],
    "methadone": ["methadone"],
    "naltrexone": ["naltrexone", "vivitrol"],
    "opioids": ["opioid analgesic", "opioids", "oxycodone", "hydrocodone", "fentanyl"],
    "antidepressant": ["antidepressant", "ssri", "sertraline", "fluoxetine", "escitalopram"],
    "statin": ["statin", "atorvastatin", "rosuvastatin", "simvastatin"],
    "systemic corticosteroids": ["systemic corticosteroids", "oral corticosteroids", "oral steroids", "prednisone"],
    "chemotherapy": ["chemotherapy"],
    "ace inhibitor": ["ace inhibitor", "lisinopril", "enalapril"],
}

# canonical lab -> (synonyms, default unit)
LABS: dict[str, tuple[list[str], str]] = {
    "hba1c": (["hba1c", "hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin", "glycosylated hemoglobin", "a1c"], "%"),
    "egfr": (["egfr", "estimated glomerular filtration rate", "glomerular filtration rate", "gfr"], "mL/min/1.73m2"),
    "bmi": (["bmi", "body mass index"], "kg/m2"),
    "ldl": (["ldl-c", "ldl cholesterol", "ldl"], "mg/dL"),
    "systolic_bp": (["systolic blood pressure", "systolic bp", "sbp"], "mmHg"),
    "ejection_fraction": (["left ventricular ejection fraction", "lvef", "ejection fraction"], "%"),
}

US_STATES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "washington dc": "DC", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
    "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def _compile(table: dict[str, list[str]]) -> list[tuple[re.Pattern[str], str]]:
    pairs = [(syn, canon) for canon, syns in table.items() for syn in syns]
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return [(re.compile(r"(?<![\w-])" + re.escape(syn) + r"(?![\w-])", re.IGNORECASE), canon) for syn, canon in pairs]


_CONDITION_PATTERNS = _compile(CONDITIONS)
_MEDICATION_PATTERNS = _compile(MEDICATIONS)
_LAB_PATTERNS = _compile({k: v[0] for k, v in LABS.items()})


def _find_all(patterns: list[tuple[re.Pattern[str], str]], text: str) -> list[str]:
    """Canonical terms found in text, in order of first appearance, longest match wins."""
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for pattern, canon in patterns:
        for m in pattern.finditer(text):
            if any(m.start() < end and m.end() > start for start, end in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), canon))
    seen: list[str] = []
    for _, canon in sorted(found):
        if canon not in seen:
            seen.append(canon)
    return seen


def find_conditions(text: str) -> list[str]:
    return _find_all(_CONDITION_PATTERNS, text)


def find_medications(text: str) -> list[str]:
    return _find_all(_MEDICATION_PATTERNS, text)


def find_labs(text: str) -> list[tuple[str, int, int]]:
    """(canonical lab, start, end) for each lab mention."""
    out = []
    for pattern, canon in _LAB_PATTERNS:
        for m in pattern.finditer(text):
            if not any(m.start() < e and m.end() > s for _, s, e in out):
                out.append((canon, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


# When a criterion names several conditions, these qualifiers are the point
# ("chronic kidney disease requiring dialysis" is about dialysis).
SPECIFIC_CONDITIONS = ("dialysis",)


def normalize_condition(name: str) -> str:
    found = find_conditions(name)
    return found[0] if found else name.strip().lower()


def normalize_medication(name: str) -> str:
    found = find_medications(name)
    return found[0] if found else name.strip().lower()


def normalize_lab(name: str) -> str | None:
    key = name.strip().lower().replace(" ", "_")
    if key in LABS:
        return key
    found = find_labs(name)
    return found[0][0] if found else None


def conditions_match(patient_condition: str, criterion_condition: str) -> bool:
    """True if a patient's condition satisfies a criterion's condition.

    "cancer" in a criterion (e.g. "active malignancy") is matched by any
    specific cancer the patient has.
    """
    p = normalize_condition(patient_condition)
    c = normalize_condition(criterion_condition)
    if p == c:
        return True
    if c == "cancer" and "cancer" in p:
        return True
    return c in p or p in c


def medications_match(patient_med: str, criterion_med: str) -> bool:
    p = normalize_medication(patient_med)
    c = normalize_medication(criterion_med)
    if p == c:
        return True
    # Warfarin is an anticoagulant; a criterion about anticoagulants covers it.
    if c == "anticoagulant" and p == "warfarin":
        return True
    return False


def state_code(text: str) -> str | None:
    t = text.strip().lower()
    if len(t) == 2 and t.upper() in US_STATES.values():
        return t.upper()
    return US_STATES.get(t)
