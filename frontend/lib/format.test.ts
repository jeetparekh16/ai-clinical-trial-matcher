import assert from "node:assert/strict";
import { test } from "node:test";
import { groupByTier, patientFacts, phaseLabel, verdictLabel } from "./format.ts";
import type { MatchResult, Patient } from "./types.ts";

test("patientFacts lists what was understood", () => {
  const patient: Patient = {
    age: 58, sex: "female", conditions: ["type 2 diabetes"], medications: ["metformin"],
    labs: { hba1c: 8.4, egfr: 72 }, ecog: null, pregnant: false, state: "MD",
  };
  assert.deepEqual(patientFacts(patient), [
    "58 years, female", "Type 2 diabetes", "Takes metformin", "HbA1c 8.4%", "eGFR 72", "Not pregnant", "Lives in MD",
  ]);
});

test("groupByTier keeps order and drops empty tiers", () => {
  const r = (id: string, tier: MatchResult["tier"]) => ({ trial: { nct_id: id }, tier }) as MatchResult;
  const groups = groupByTier([r("A", "likely"), r("B", "not_eligible"), r("C", "likely")]);
  assert.deepEqual(groups.map((g) => [g.tier, g.results.map((x) => x.trial.nct_id)]), [["likely", ["A", "C"]], ["not_eligible", ["B"]]]);
});

test("phaseLabel", () => {
  assert.equal(phaseLabel(["PHASE2", "PHASE3"]), "Phase 2/Phase 3");
  assert.equal(phaseLabel(["NA"]), null);
});

test("verdictLabel reads naturally for exclusions", () => {
  assert.equal(verdictLabel("inclusion", "met"), "Meets");
  assert.equal(verdictLabel("exclusion", "met"), "Clear");
  assert.equal(verdictLabel("exclusion", "not_met"), "Excluded");
  assert.equal(verdictLabel("exclusion", "unknown"), "Check");
});
