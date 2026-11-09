import builtins
import importlib
import json
import sys

from tests.test_ctgov import API_STUDY
from trialmatch import engine

REQUEST = json.dumps({
    "patient_description": "58 year old woman in Maryland with type 2 diabetes, A1c 8.4%, BMI 31, eGFR 72, on metformin. Not pregnant.",
    "limit": 5,
})


def test_browser_match_with_sample_trials():
    data = json.loads(engine.browser_match(REQUEST))
    assert data["data_source"] == "sample"
    assert data["notice"] == engine.SAMPLE_NOTICE
    assert data["results"][0]["trial"]["nct_id"] == "DEMO0001"
    assert data["results"][0]["tier"] == "likely"


def test_browser_match_with_studies_fetched_by_the_browser():
    data = json.loads(engine.browser_match(REQUEST, json.dumps({"studies": [API_STUDY]})))
    assert data["data_source"] == "clinicaltrials.gov"
    assert data["notice"] is None
    assert data["results"][0]["trial"]["nct_id"] == "NCT01234567"


def test_browser_match_reports_unreachable_api():
    data = json.loads(engine.browser_match(REQUEST, None, live_failed=True))
    assert data["notice"] == engine.UNREACHABLE_NOTICE


def test_browser_errors_are_messages_not_exceptions():
    assert json.loads(engine.browser_match(json.dumps({"patient_description": "A person"}))) == {
        "error": "Could not tell which condition to search for. Add a condition.",
    }
    assert "error" in json.loads(engine.browser_match("{not json"))
    prepared = json.loads(engine.browser_prepare(REQUEST))
    assert prepared["condition"] == "type 2 diabetes" and prepared["patient"]["age"] == 58


def test_engine_imports_without_server_dependencies(monkeypatch):
    """The browser build has no httpx, fastapi, anthropic or sqlite3."""
    blocked = {"httpx", "fastapi", "anthropic", "sqlite3", "uvicorn"}
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in blocked:
            raise ImportError(f"{name} is not available in the browser")
        return real_import(name, *args, **kwargs)

    for mod in [m for m in sys.modules if m.startswith("trialmatch")]:
        monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setattr(builtins, "__import__", guarded)
    fresh = importlib.import_module("trialmatch.engine")
    assert json.loads(fresh.browser_match(REQUEST))["results"]
