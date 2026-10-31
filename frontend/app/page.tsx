"use client";

import { useState } from "react";
import { ResultList } from "@/components/ResultList";
import { patientFacts } from "@/lib/format";
import type { MatchResponse } from "@/lib/types";

const EXAMPLES = [
  {
    label: "Diabetes, Maryland",
    text: "58 year old woman in Maryland with type 2 diabetes, A1c 8.4%, BMI 31, eGFR 72, on metformin. Not pregnant.",
  },
  {
    label: "Heart failure, DC",
    text: "71 year old man in Washington DC with heart failure, LVEF 35%, hospitalized last spring. Hypertension. eGFR 48.",
  },
  {
    label: "Depression",
    text: "34 year old woman in California with major depressive disorder, two antidepressants tried without relief. Systolic BP 128.",
  },
];

export default function Home() {
  const [description, setDescription] = useState(EXAMPLES[0].text);
  const [condition, setCondition] = useState("");
  const [data, setData] = useState<MatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function findTrials(event?: React.FormEvent) {
    event?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patient_description: description, condition: condition.trim() || null, limit: 15 }),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : "Check the description and try again.";
        throw new Error(detail);
      }
      setData(body as MatchResponse);
    } catch (e) {
      setData(null);
      setError(e instanceof TypeError ? "The matching service is not running. Start the backend on port 8000." : (e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="shell">
      <aside className="intake">
        <p className="brand">Trial Match</p>
        <h1>Which trials could this patient join?</h1>
        <p className="lede">
          Describe the patient the way you would in a referral note. Each trial&rsquo;s eligibility criteria are turned
          into rules and checked one by one, so you can see exactly why a trial fits or not.
        </p>

        <form onSubmit={findTrials} className="form">
          <label htmlFor="description">Patient</label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            maxLength={4000}
            required
          />
          <div className="examples" role="group" aria-label="Example patients">
            {EXAMPLES.map((ex) => (
              <button key={ex.label} type="button" className="example" aria-pressed={description === ex.text} onClick={() => setDescription(ex.text)}>
                {ex.label}
              </button>
            ))}
          </div>

          <label htmlFor="condition">
            Condition to search <span className="optional">optional, uses the first one in the description</span>
          </label>
          <input
            id="condition"
            value={condition}
            onChange={(e) => setCondition(e.target.value)}
            placeholder="e.g. type 2 diabetes"
            maxLength={200}
          />

          <button type="submit" className="primary" disabled={loading}>
            {loading ? "Checking trials…" : "Find trials"}
          </button>
        </form>

        {data && (
          <section className="understood" aria-label="What we understood">
            <h2>What we read from the description</h2>
            <ul>
              {patientFacts(data.patient).map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
            <p className="fine">If something is missing or wrong, edit the description. Missing facts show as &ldquo;Check&rdquo;, never as a pass.</p>
          </section>
        )}
      </aside>

      <main className="results" aria-live="polite" aria-busy={loading}>
        {error && <p className="error" role="alert">{error}</p>}
        {!data && !error && (
          <div className="empty">
            <p>Pick an example or describe a patient, then choose <strong>Find trials</strong>.</p>
            <p className="fine">Trials come from ClinicalTrials.gov. Results are a screening aid for the study team, not a medical decision.</p>
          </div>
        )}
        {data && <ResultList data={data} />}
      </main>
    </div>
  );
}
