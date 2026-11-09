import json
from datetime import date
from importlib import resources

from trialmatch.fhir import display_name, flatten, patient_from_fhir

BUNDLE = json.loads(resources.files("trialmatch").joinpath("sample_data/sample_patient_bundle.json").read_text())
TODAY = date(2026, 11, 9)


def test_sample_bundle_maps_to_patient():
    p = patient_from_fhir(BUNDLE, today=TODAY)
    assert p.age == 58
    assert p.sex == "female"
    assert p.state == "MD"
    # Resolved asthma is ignored; SNOMED codes map to canonical names.
    assert p.conditions == ["type 2 diabetes", "hypertension"]
    # Stopped insulin is ignored; RxNorm display text is normalised.
    assert p.medications == ["metformin", "ace inhibitor"]
    # The latest HbA1c wins; systolic BP comes from the blood pressure panel component.
    assert p.labs == {"hba1c": 8.4, "egfr": 72.0, "bmi": 31.2, "systolic_bp": 138.0}
    assert display_name(BUNDLE) == "Ana Rivera"


def test_age_before_and_after_birthday():
    patient = {"resourceType": "Patient", "birthDate": "1968-11-10", "gender": "male"}
    assert patient_from_fhir([patient], today=TODAY).age == 57
    assert patient_from_fhir([patient], today=date(2026, 11, 10)).age == 58
    # Men are recorded as not pregnant; women stay unknown unless the record says so.
    assert patient_from_fhir([patient], today=TODAY).pregnant is False


def test_text_only_codes_pregnancy_and_ecog():
    items = [
        {"resourceType": "Patient", "gender": "female", "birthDate": "1990-01-01"},
        {"resourceType": "Condition", "code": {"text": "Major depression, recurrent"}},
        {"resourceType": "Condition", "code": {"coding": [{"system": "http://snomed.info/sct", "code": "77386006", "display": "Pregnancy"}]}},
        {"resourceType": "Condition", "verificationStatus": {"coding": [{"code": "refuted"}]}, "code": {"text": "Asthma"}},
        {"resourceType": "Observation", "status": "final", "code": {"coding": [{"system": "http://loinc.org", "code": "89247-1"}]},
         "valueCodeableConcept": {"coding": [{"code": "1"}]}, "effectiveDateTime": "2026-01-01"},
        {"resourceType": "Observation", "status": "entered-in-error", "code": {"coding": [{"code": "4548-4"}]}, "valueQuantity": {"value": 12}},
        {"resourceType": "MedicationStatement", "status": "active", "medicationReference": {"display": "Sertraline 50 mg"}},
    ]
    p = patient_from_fhir(items, today=TODAY)
    assert p.conditions == ["major depressive disorder"]
    assert p.pregnant is True
    assert p.ecog == 1
    assert p.labs == {}
    assert p.medications == ["antidepressant"]


def test_flatten_accepts_nested_bundles_and_lists():
    nested = [{"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient", "id": "a"}}, {"search": {}}]}, {"resourceType": "Condition"}]
    assert [r["resourceType"] for r in flatten(nested)] == ["Patient", "Condition"]
    assert patient_from_fhir([], today=TODAY).age is None


def test_frontend_sample_record_matches_backend_copy():
    from pathlib import Path

    frontend_copy = Path(__file__).resolve().parents[2] / "frontend/public/fhir/sample_patient_bundle.json"
    assert json.loads(frontend_copy.read_text()) == BUNDLE
