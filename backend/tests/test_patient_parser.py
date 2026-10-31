from types import SimpleNamespace

from trialmatch.models import Patient
from trialmatch.patient_parser import LLMPatientParser, normalize_patient, parse_rules


def test_parses_a_typical_description():
    p = parse_rules("58 year old woman in Maryland with type 2 diabetes, A1c 8.4%, BMI 31, eGFR 72, on metformin. Not pregnant.")
    assert p.age == 58
    assert p.sex == "female"
    assert p.state == "MD"
    assert p.conditions == ["type 2 diabetes"]
    assert p.medications == ["metformin"]
    assert p.labs == {"hba1c": 8.4, "bmi": 31.0, "egfr": 72.0}
    assert p.pregnant is False


def test_shorthand_and_negation():
    p = parse_rules("67yo M, Dallas, TX. HTN and CHF (LVEF 35%). No history of diabetes or stroke. Takes lisinopril. ECOG 1")
    assert p.age == 67
    assert p.conditions == ["hypertension", "heart failure"]
    assert p.medications == ["ace inhibitor"]
    assert p.labs["ejection_fraction"] == 35.0
    assert p.ecog == 1
    assert p.state == "TX"


def test_male_pronoun_and_state_name():
    p = parse_rules("He is 34, lives in New York, and has opioid use disorder; currently on methadone.")
    assert p.sex == "male"
    assert p.age is None or p.age == 34
    assert p.state == "NY"
    assert p.conditions == ["opioid use disorder"]
    assert p.medications == ["methadone"]


def test_normalize_patient_maps_synonyms():
    p = normalize_patient(Patient(conditions=["T2DM", "high blood pressure"], medications=["Ozempic semaglutide"],
                                  labs={"Hemoglobin A1c": 9.1, "unknown lab": 3}, state="maryland"))
    assert p.conditions == ["type 2 diabetes", "hypertension"]
    assert p.medications == ["glp-1 receptor agonist"]
    assert p.labs == {"hba1c": 9.1}
    assert p.state == "MD"


def test_llm_parser_uses_tool_output():
    block = SimpleNamespace(type="tool_use", name="record_patient", input={
        "age": 45, "sex": "female", "conditions": ["Type II diabetes"], "medications": [], "labs": {"A1c": 7.9}, "state": "VA",
    })
    calls = []

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content=[block])

    p = LLMPatientParser(Messages(), "test-model").parse("45F with T2D, A1c 7.9, Virginia")
    assert p.conditions == ["type 2 diabetes"] and p.labs == {"hba1c": 7.9} and p.state == "VA"
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "record_patient"}
