"use client";

import { useState } from "react";
import { groupByTier, phaseLabel, TIER_LABEL, verdictLabel } from "@/lib/format";
import type { CriterionResult, MatchResponse, MatchResult } from "@/lib/types";

export function ResultList({ data }: { data: MatchResponse }) {
  const groups = groupByTier(data.results);
  return (
    <>
      <header className="summary">
        <p>
          Screened <strong>{data.trials_screened}</strong> recruiting {data.trials_screened === 1 ? "trial" : "trials"} for{" "}
          <strong>{data.condition}</strong>
        </p>
        <p className="fine">
          Criteria read by {data.extractor === "llm" ? "the LLM" : "the built-in rule parser (add an API key to use the LLM)"}.
          {data.data_source === "sample" ? " Showing demo trials." : " Source: ClinicalTrials.gov."}
        </p>
        {data.notice && <p className="notice">{data.notice}</p>}
      </header>

      {groups.length === 0 && <p className="empty">No recruiting trials found for this condition. Try a broader term.</p>}

      {groups.map((group) => (
        <section key={group.tier} className={`tier tier-${group.tier}`} aria-labelledby={`tier-${group.tier}`}>
          <h2 id={`tier-${group.tier}`}>
            {TIER_LABEL[group.tier]} <span className="count">{group.results.length}</span>
          </h2>
          <ol className="trials">
            {group.results.map((result) => (
              <TrialRow key={result.trial.nct_id} result={result} defaultOpen={group.tier === "likely"} />
            ))}
          </ol>
        </section>
      ))}
    </>
  );
}

function TrialRow({ result, defaultOpen }: { result: MatchResult; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const { trial } = result;
  const phase = phaseLabel(trial.phases);
  const inclusion = result.criteria.filter((c) => c.criterion.kind === "inclusion");
  const exclusion = result.criteria.filter((c) => c.criterion.kind === "exclusion");
  const panelId = `criteria-${trial.nct_id}`;

  return (
    <li className="trial">
      <div className="trial-head">
        <Tally result={result} />
        <div className="trial-text">
          <h3>{trial.title}</h3>
          <p className="meta">
            {trial.url ? (
              <a href={trial.url} target="_blank" rel="noreferrer">
                {trial.nct_id}
              </a>
            ) : (
              <span>{trial.nct_id}</span>
            )}
            {phase && <span>{phase}</span>}
            {result.nearby_sites[0] && (
              <span>
                {result.nearby_sites[0].facility}, {result.nearby_sites[0].city}
              </span>
            )}
          </p>
          <p className="explanation">{result.explanation}</p>
        </div>
      </div>
      <button className="toggle" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        {open ? "Hide criteria" : `Show all ${result.criteria.length} criteria`}
      </button>
      {open && (
        <div id={panelId} className="criteria">
          <CriteriaTable title="To join, the patient must" rows={inclusion} />
          <CriteriaTable title="The patient must not have" rows={exclusion} />
        </div>
      )}
    </li>
  );
}

/** Three counts that summarize a trial at a glance: met, failed, needs checking. */
function Tally({ result }: { result: MatchResult }) {
  return (
    <div className="tally" aria-label={`${result.met} criteria met, ${result.not_met} failed, ${result.unknown} to check`}>
      <span className="t-met">{result.met}</span>
      <span className="t-fail">{result.not_met}</span>
      <span className="t-check">{result.unknown}</span>
    </div>
  );
}

function CriteriaTable({ title, rows }: { title: string; rows: CriterionResult[] }) {
  if (rows.length === 0) return null;
  return (
    <table>
      <caption>{title}</caption>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className={`v-${row.verdict}`}>
            <td className="verdict">
              <span className="mark" aria-hidden="true">{row.verdict === "met" ? "✓" : row.verdict === "not_met" ? "✕" : "?"}</span>
              {verdictLabel(row.criterion.kind, row.verdict)}
            </td>
            <td>
              <span className="ctext">{row.criterion.text}</span>
              <span className="reason">{row.reason}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
