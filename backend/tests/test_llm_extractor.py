from types import SimpleNamespace

from trialmatch.criteria_llm import LLMExtractor
from trialmatch.extractor import CriteriaCache, CriteriaService
from trialmatch.models import Category, Trial


class FakeMessages:
    def __init__(self, items=None, fail=False):
        self.items = items or []
        self.fail = fail
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("API down")
        return SimpleNamespace(content=[
            SimpleNamespace(type="text", text="Here you go"),
            SimpleNamespace(type="tool_use", name="record_criteria", input={"criteria": self.items}),
        ])


ITEMS = [
    {"kind": "inclusion", "category": "lab", "text": "A1c 7-10%", "field": "HbA1c", "operator": "between", "value": 7, "value_max": 10},
    {"kind": "exclusion", "category": "condition", "text": "T1DM", "field": "condition", "operator": "present", "value": "T1DM"},
    {"kind": "exclusion", "category": "medication", "text": "Ozempic", "field": "medication", "operator": "present", "value": "semaglutide"},
    {"kind": "inclusion", "category": "other", "text": "Signed consent"},
    {"kind": "inclusion", "category": "not-a-category", "text": "broken item is skipped"},
]


def test_llm_output_is_validated_and_normalised():
    messages = FakeMessages(ITEMS)
    criteria = LLMExtractor(messages, "test-model").extract("Inclusion Criteria: ...")
    assert [c.category for c in criteria] == [Category.LAB, Category.CONDITION, Category.MEDICATION, Category.OTHER]
    assert criteria[0].field == "hba1c"
    assert criteria[1].value == "type 1 diabetes"
    assert criteria[2].value == "glp-1 receptor agonist"
    call = messages.calls[0]
    assert call["model"] == "test-model"
    assert call["tool_choice"] == {"type": "tool", "name": "record_criteria"}
    assert "Never invent thresholds" in call["system"]


def _trial(text):
    return Trial(nct_id="NCT1", title="t", status="RECRUITING", eligibility_text=text, min_age=18)


def test_service_caches_by_criteria_text():
    messages = FakeMessages(ITEMS)
    service = CriteriaService(LLMExtractor(messages, "m"), "llm", CriteriaCache(":memory:"))
    first = service.for_trial(_trial("criteria v1"))
    second = service.for_trial(_trial("criteria v1"))
    assert first == second and len(messages.calls) == 1
    service.for_trial(_trial("criteria v2"))
    assert len(messages.calls) == 2
    # Structured age from the trial record comes first.
    assert first[0].field == "age" and first[0].value == 18


def test_service_falls_back_to_rules_when_llm_fails():
    service = CriteriaService(LLMExtractor(FakeMessages(fail=True), "m"), "llm", CriteriaCache(":memory:"))
    criteria = service.for_trial(_trial("Exclusion Criteria:\n\n* eGFR < 30"))
    assert [(c.field, c.operator, c.value) for c in criteria[1:]] == [("egfr", "<", 30.0)]
