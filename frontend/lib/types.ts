// Mirrors the FastAPI response models in backend/trialmatch/models.py.

export type Verdict = "met" | "not_met" | "unknown";
export type Tier = "likely" | "possible" | "not_eligible";

export interface Criterion {
  kind: "inclusion" | "exclusion";
  category: string;
  text: string;
  field: string | null;
  operator: string | null;
  value: number | string | null;
  value_max: number | null;
  unit: string | null;
}

export interface CriterionResult {
  criterion: Criterion;
  verdict: Verdict;
  reason: string;
}

export interface Location {
  facility: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
}

export interface Trial {
  nct_id: string;
  title: string;
  status: string;
  phases: string[];
  conditions: string[];
  summary: string;
  url: string;
  locations: Location[];
}

export interface MatchResult {
  trial: Trial;
  tier: Tier;
  score: number;
  met: number;
  not_met: number;
  unknown: number;
  criteria: CriterionResult[];
  nearby_sites: Location[];
  explanation: string;
}

export interface Patient {
  age: number | null;
  sex: "male" | "female" | null;
  conditions: string[];
  medications: string[];
  labs: Record<string, number>;
  ecog: number | null;
  pregnant: boolean | null;
  state: string | null;
}

export interface MatchResponse {
  patient: Patient;
  condition: string;
  data_source: "clinicaltrials.gov" | "sample";
  extractor: "llm" | "rules";
  trials_screened: number;
  results: MatchResult[];
  notice: string | null;
}
