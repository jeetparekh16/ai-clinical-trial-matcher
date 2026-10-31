import pytest

from trialmatch.criteria_rules import classify, extract, parse_threshold, split_sections
from trialmatch.models import Category


def test_split_sections_handles_headers_and_wrapped_lines():
    text = """Inclusion Criteria:

* Adults with type 2 diabetes
  diagnosed at least 1 year ago
* HbA1c 7-10%

Exclusion Criteria:

1. Pregnancy
2. eGFR < 30
"""
    assert split_sections(text) == [
        ("inclusion", "Adults with type 2 diabetes diagnosed at least 1 year ago"),
        ("inclusion", "HbA1c 7-10%"),
        ("exclusion", "Pregnancy"),
        ("exclusion", "eGFR < 30"),
    ]


def test_split_sections_without_headers_is_inclusion():
    assert split_sections("* Age 18 or older\n* Asthma") == [("inclusion", "Age 18 or older"), ("inclusion", "Asthma")]


@pytest.mark.parametrize("text,expected", [
    ("HbA1c between 7.5% and 10.5%", ("between", 7.5, 10.5)),
    ("HbA1c 7-10%", ("between", 7.0, 10.0)),
    ("BMI ≥ 30 kg/m2", (">=", 30.0, None)),
    ("eGFR less than 30", ("<", 30.0, None)),
    ("at least 8%", (">=", 8.0, None)),
    ("18 years or older", (">=", 18.0, None)),
    ("140 mmHg or higher", (">=", 140.0, None)),
    ("no more than 2 prior regimens", ("<=", 2.0, None)),
    ("diagnosis of asthma", None),
])
def test_parse_threshold(text, expected):
    assert parse_threshold(text) == expected


@pytest.mark.parametrize("kind,text,category,field,op,value", [
    ("inclusion", "HbA1c between 7.5% and 10.5% at screening", Category.LAB, "hba1c", "between", 7.5),
    ("exclusion", "eGFR < 30 mL/min/1.73m2", Category.LAB, "egfr", "<", 30.0),
    ("inclusion", "Age 18 to 65 years", Category.AGE, "age", "between", 18.0),
    ("inclusion", "ECOG performance status 0-1", Category.PERFORMANCE, "ecog", "<=", 1.0),
    ("inclusion", "ECOG 0, 1 or 2", Category.PERFORMANCE, "ecog", "<=", 2.0),
    ("exclusion", "Pregnant or breastfeeding women", Category.PREGNANCY, "pregnancy", "present", "pregnant or breastfeeding"),
    ("exclusion", "Currently taking warfarin", Category.MEDICATION, "medication", "present", "warfarin"),
    ("exclusion", "History of type 1 diabetes", Category.CONDITION, "condition", "present", "type 1 diabetes"),
    ("inclusion", "Diagnosis of T2DM", Category.CONDITION, "condition", "present", "type 2 diabetes"),
    ("exclusion", "Chronic kidney disease requiring dialysis", Category.CONDITION, "condition", "present", "dialysis"),
    ("inclusion", "Postmenopausal women", Category.SEX, "sex", "==", "female"),
])
def test_classify(kind, text, category, field, op, value):
    c = classify(kind, text)
    assert (c.category, c.field, c.operator, c.value) == (category, field, op, value)
    assert c.text == text and c.kind == kind


@pytest.mark.parametrize("text", [
    "Willing to start buprenorphine treatment",
    "Able to provide written informed consent",
    "Any condition that, in the investigator's opinion, makes participation unsafe",
])
def test_unstructured_bullets_become_other(text):
    c = classify("inclusion", text)
    assert c.category == Category.OTHER and not c.is_structured


def test_inclusion_pregnancy_test_requirement_is_not_an_exclusion():
    assert classify("inclusion", "Women of childbearing potential must have a negative pregnancy test").category != Category.PREGNANCY


def test_exclusion_with_several_conditions_excludes_each():
    criteria = extract("Exclusion Criteria:\n\n* Bipolar disorder or schizophrenia")
    assert [c.value for c in criteria] == ["bipolar disorder", "schizophrenia"]
    assert all(c.kind == "exclusion" for c in criteria)
