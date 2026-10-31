import type { MatchResult, Patient, Tier, Verdict } from "./types.ts";

const LAB_LABELS: Record<string, [string, string]> = {
  hba1c: ["HbA1c", "%"],
  egfr: ["eGFR", ""],
  bmi: ["BMI", ""],
  ldl: ["LDL", "mg/dL"],
  systolic_bp: ["Systolic BP", "mmHg"],
  ejection_fraction: ["LVEF", "%"],
};

/** Short facts the system read from the description, for the "We understood" panel. */
export function patientFacts(p: Patient): string[] {
  const facts: string[] = [];
  if (p.age !== null || p.sex) facts.push([p.age !== null ? `${p.age} years` : null, p.sex].filter(Boolean).join(", "));
  facts.push(...p.conditions.map(capitalize));
  facts.push(...p.medications.map((m) => `Takes ${m}`));
  for (const [key, value] of Object.entries(p.labs)) {
    const [label, unit] = LAB_LABELS[key] ?? [key, ""];
    facts.push(`${label} ${value}${unit === "%" ? "%" : unit ? ` ${unit}` : ""}`);
  }
  if (p.ecog !== null) facts.push(`ECOG ${p.ecog}`);
  if (p.pregnant === true) facts.push("Pregnant");
  if (p.pregnant === false) facts.push("Not pregnant");
  if (p.state) facts.push(`Lives in ${p.state}`);
  return facts;
}

export const TIER_LABEL: Record<Tier, string> = {
  likely: "Likely eligible",
  possible: "Possibly eligible",
  not_eligible: "Not eligible",
};

/** Inclusion rows are met or failed; exclusion rows are clear or excluding. */
export function verdictLabel(kind: "inclusion" | "exclusion", verdict: Verdict): string {
  if (verdict === "unknown") return "Check";
  if (kind === "inclusion") return verdict === "met" ? "Meets" : "Fails";
  return verdict === "met" ? "Clear" : "Excluded";
}

/** Groups results by tier, keeping the API's ranking inside each group. */
export function groupByTier(results: MatchResult[]): { tier: Tier; results: MatchResult[] }[] {
  const order: Tier[] = ["likely", "possible", "not_eligible"];
  return order
    .map((tier) => ({ tier, results: results.filter((r) => r.tier === tier) }))
    .filter((group) => group.results.length > 0);
}

export function phaseLabel(phases: string[]): string | null {
  const named = phases.filter((p) => p && p !== "NA").map((p) => p.replace("PHASE", "Phase ").replace("EARLY_", "Early "));
  return named.length ? named.join("/") : null;
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
