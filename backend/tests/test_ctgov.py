import httpx

from trialmatch.ctgov import ClinicalTrialsClient, SampleTrials, parse_study

# Shape of a real ClinicalTrials.gov API v2 response (trimmed).
API_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT01234567", "briefTitle": "A Study of Drug X in Type 2 Diabetes"},
        "statusModule": {"overallStatus": "RECRUITING"},
        "designModule": {"phases": ["PHASE3"]},
        "conditionsModule": {"conditions": ["Type 2 Diabetes Mellitus"]},
        "descriptionModule": {"briefSummary": "Summary."},
        "eligibilityModule": {
            "eligibilityCriteria": "Inclusion Criteria:\n\n* HbA1c 7-10%\n\nExclusion Criteria:\n\n* Pregnancy",
            "healthyVolunteers": False,
            "sex": "ALL",
            "minimumAge": "18 Years",
            "maximumAge": "6 Months",
        },
        "contactsLocationsModule": {"locations": [
            {"facility": "Clinic A", "city": "Baltimore", "state": "Maryland", "country": "United States"},
            {"facility": "Clinic B", "city": "Toronto", "state": "Ontario", "country": "Canada"},
        ]},
    }
}


def test_parse_study():
    t = parse_study(API_STUDY)
    assert t.nct_id == "NCT01234567"
    assert t.url == "https://clinicaltrials.gov/study/NCT01234567"
    assert t.min_age == 18 and t.max_age == 0.5
    assert t.sex == "all" and t.phases == ["PHASE3"]
    assert [loc.state for loc in t.locations] == ["MD", "Ontario"]


def test_client_queries_recruiting_studies():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        seen["path"] = request.url.path
        return httpx.Response(200, json={"studies": [API_STUDY]})

    client = ClinicalTrialsClient(http=httpx.Client(transport=httpx.MockTransport(handler)))
    trials = client.search("type 2 diabetes", limit=5)
    assert [t.nct_id for t in trials] == ["NCT01234567"]
    assert seen["path"] == "/api/v2/studies"
    assert seen["query.cond"] == "type 2 diabetes"
    assert seen["filter.overallStatus"] == "RECRUITING"
    assert seen["pageSize"] == "5"
    assert "EligibilityCriteria" in seen["fields"]


def test_sample_trials_search_by_synonym():
    sample = SampleTrials()
    assert len(sample.trials) == 12
    ids = [t.nct_id for t in sample.search("T2DM")]
    assert ids == ["DEMO0001", "DEMO0002", "DEMO0003"]
    assert all(t.url == "" for t in sample.trials), "Demo trials must not link to real studies"
