import httpx
import pytest
from fastapi.testclient import TestClient

from trialmatch.api import create_app
from trialmatch.config import Settings
from trialmatch.extractor import CriteriaCache, CriteriaService, RuleExtractor


def make_client(**kwargs):
    settings = Settings(anthropic_api_key=None, data_source="sample", cache_path=":memory:")
    service = CriteriaService(RuleExtractor(), "rules", CriteriaCache(":memory:"))
    return TestClient(create_app(settings, criteria_service=service, **kwargs))


@pytest.fixture
def client():
    return make_client()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "extractor": "rules", "data_source": "sample"}


def test_match_from_description(client):
    response = client.post("/api/match", json={
        "patient_description": "58 year old woman in Maryland with type 2 diabetes, A1c 8.4%, BMI 31, eGFR 72, on metformin. Not pregnant.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["condition"] == "type 2 diabetes"
    assert data["data_source"] == "sample" and "Demo mode" in data["notice"]
    assert data["trials_screened"] == 3
    top = data["results"][0]
    assert top["trial"]["nct_id"] == "DEMO0001"
    assert top["tier"] == "likely"
    assert top["nearby_sites"][0]["state"] == "MD"
    verdicts = {c["criterion"]["text"]: c["verdict"] for c in top["criteria"]}
    assert verdicts["HbA1c between 7.5% and 10.5% at screening"] == "met"
    assert verdicts["Use of insulin within the last 90 days"] == "met"
    # Every other trial fails on a concrete, explained criterion.
    assert {r["trial"]["nct_id"]: r["tier"] for r in data["results"][1:]} == {"DEMO0002": "not_eligible", "DEMO0003": "not_eligible"}


def test_match_with_structured_patient_and_condition(client):
    response = client.post("/api/match", json={
        "patient": {"age": 30, "sex": "male", "conditions": ["MDD"], "labs": {"systolic bp": 160}},
        "condition": "depression",
        "limit": 5,
    })
    result = response.json()["results"][0]
    assert result["trial"]["nct_id"] == "DEMO0007"
    assert result["tier"] == "not_eligible"
    assert "SYSTOLIC_BP 160 is not" not in result["explanation"]  # exclusion, phrased as "Excluded"
    assert "Excluded" in result["explanation"]


def test_validation_errors(client):
    assert client.post("/api/match", json={}).status_code == 422
    assert client.post("/api/match", json={"patient_description": "A person"}).status_code == 422
    assert client.post("/api/match", json={"patient_description": "x", "limit": 0}).status_code == 422


def test_falls_back_to_sample_when_live_api_is_down():
    class DownSource:
        def search(self, *args, **kwargs):
            raise httpx.ConnectError("no route")

    client = make_client(trial_source=DownSource())
    data = client.post("/api/match", json={"patient_description": "40 year old with asthma"}).json()
    assert data["data_source"] == "sample"
    assert "could not be reached" in data["notice"]
    assert data["results"][0]["trial"]["nct_id"] == "DEMO0009"


def test_parse_patient_endpoint(client):
    data = client.post("/api/parse-patient", json={"text": "72 yo man, COPD, Ohio"}).json()
    assert data["age"] == 72 and data["sex"] == "male" and data["conditions"] == ["copd"] and data["state"] == "OH"
