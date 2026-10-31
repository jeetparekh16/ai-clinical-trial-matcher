from trialmatch.matcher import evaluate, match_trial, rank
from trialmatch.models import Category, Criterion, Location, Patient, Trial


def crit(kind="inclusion", category=Category.LAB, field="hba1c", op=">=", value=7.0, value_max=None):
    return Criterion(kind=kind, category=category, text="t", field=field, operator=op, value=value, value_max=value_max)


PATIENT = Patient(age=58, sex="female", conditions=["type 2 diabetes"], medications=["metformin"],
                  labs={"hba1c": 8.4, "egfr": 72}, pregnant=False, state="MD")


def test_lab_thresholds():
    assert evaluate(crit(op="between", value=7.5, value_max=10.5), PATIENT).verdict == "met"
    assert evaluate(crit(op=">=", value=9), PATIENT).verdict == "not_met"
    assert evaluate(crit(field="ldl", op="<", value=100), PATIENT).verdict == "unknown"


def test_exclusion_logic_is_inverted():
    egfr_low = crit(kind="exclusion", field="egfr", op="<", value=30)
    assert evaluate(egfr_low, PATIENT).verdict == "met"
    t1d = crit(kind="exclusion", category=Category.CONDITION, field="condition", op="present", value="type 1 diabetes")
    assert evaluate(t1d, PATIENT).verdict == "met"
    t2d = crit(kind="exclusion", category=Category.CONDITION, field="condition", op="present", value="type 2 diabetes")
    result = evaluate(t2d, PATIENT)
    assert result.verdict == "not_met" and result.reason.startswith("Excluded")


def test_cancer_criterion_matches_specific_cancers():
    malignancy = crit(kind="exclusion", category=Category.CONDITION, field="condition", op="present", value="cancer")
    assert evaluate(malignancy, Patient(conditions=["breast cancer"])).verdict == "not_met"
    assert evaluate(malignancy, Patient(conditions=["asthma"])).verdict == "met"


def test_unknowns_are_not_failures():
    assert evaluate(crit(category=Category.AGE, field="age", op=">=", value=18), Patient()).verdict == "unknown"
    assert evaluate(Criterion(kind="inclusion", category=Category.OTHER, text="Able to consent"), PATIENT).verdict == "unknown"
    # Medication inclusion with no medication list given.
    med = crit(category=Category.MEDICATION, field="medication", op="present", value="insulin")
    assert evaluate(med, Patient(conditions=["type 2 diabetes"])).verdict == "unknown"
    assert evaluate(med, PATIENT).verdict == "not_met"


def test_pregnancy_unknown_for_women_but_not_men():
    preg = crit(kind="exclusion", category=Category.PREGNANCY, field="pregnancy", op="present", value="pregnant")
    assert evaluate(preg, Patient(sex="female")).verdict == "unknown"
    assert evaluate(preg, Patient(sex="male")).verdict == "met"
    assert evaluate(preg, Patient(sex="female", pregnant=True)).verdict == "not_met"


def _trial(nct, state="MD"):
    return Trial(nct_id=nct, title=nct, status="RECRUITING", locations=[Location(facility="Clinic", state=state)])


def test_tiers_and_ranking():
    good = match_trial(_trial("A"), [crit(), crit(field="egfr", op=">=", value=30)], PATIENT)
    unsure = match_trial(_trial("B", "CA"), [crit(), crit(field="ldl", op="<", value=100), crit(field="bmi", op="<", value=40)], PATIENT)
    failed = match_trial(_trial("C"), [crit(op=">=", value=9)], PATIENT)

    assert good.tier == "likely" and good.nearby_sites and "Has a site in MD" in good.explanation
    assert unsure.tier == "possible" and not unsure.nearby_sites
    assert failed.tier == "not_eligible" and failed.score == 0 and "HbA1c 8.4 is not at least 9" in failed.explanation
    assert [r.trial.nct_id for r in rank([failed, unsure, good])] == ["A", "B", "C"]
