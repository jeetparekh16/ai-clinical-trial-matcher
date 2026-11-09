"use client";

import { useEffect, useState } from "react";
import { ResultList } from "@/components/ResultList";
import { ENGINE, type FhirPatient, loadEngine, loadSampleRecord, patientFromFhir, runMatch } from "@/lib/engine";
import { completeLaunch, DEFAULT_FHIR_SERVER, isLaunchCallback, startLaunch } from "@/lib/smart";
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
  const [status, setStatus] = useState<string | null>(null);
  const [ehr, setEhr] = useState<(FhirPatient & { source: string }) | null>(null);
  const [fhirServer, setFhirServer] = useState(DEFAULT_FHIR_SERVER);

  useEffect(() => {
    // Back from the EHR's sign in page: finish the SMART launch.
    if (isLaunchCallback()) {
      loadFromEhr(async () => {
        setStatus("Reading the patient's record from the EHR…");
        const { resources, server } = await completeLaunch();
        return { resources, source: new URL(server).host };
      });
    } else if (ENGINE === "browser") {
      // In the browser demo, start loading the Python engine while the visitor reads.
      loadEngine().catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadFromEhr(fetchRecord: () => Promise<{ resources: unknown[]; source: string }>) {
    setLoading(true);
    setError(null);
    try {
      const { resources, source } = await fetchRecord();
      const record = await patientFromFhir(resources, setStatus);
      setEhr({ ...record, source });
      await match(record);
    } catch (e) {
      setData(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
      setStatus(null);
    }
  }

  async function signInToEhr() {
    setError(null);
    try {
      await startLaunch(fhirServer);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function match(record: FhirPatient | null) {
    const result = await runMatch(
      record
        ? { patient: record.patient, condition: condition.trim() || null, limit: 15 }
        : { patient_description: description, condition: condition.trim() || null, limit: 15 },
      setStatus,
    );
    setData(result);
  }

  async function findTrials(event?: React.FormEvent) {
    event?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await match(ehr);
    } catch (e) {
      setData(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
      setStatus(null);
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
          {ehr ? (
            <div className="ehr-patient" role="status">
              <p>
                <strong>{ehr.name ?? "EHR patient"}</strong>, from {ehr.source}
              </p>
              <button type="button" className="link" onClick={() => setEhr(null)}>
                Describe a patient instead
              </button>
            </div>
          ) : (
            <>
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
            </>
          )}

          <label htmlFor="condition">
            Condition to search <span className="optional">optional, uses the first condition found</span>
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
          {status && <p className="fine status" role="status">{status}</p>}
        </form>

        {!ehr && (
          <section className="ehr" aria-labelledby="ehr-heading">
            <h2 id="ehr-heading">Or read the patient from an EHR</h2>
            <p className="fine">
              Signs in with SMART on FHIR, the standard EHRs like Epic and Cerner use for apps, and reads conditions, labs
              and medications. The default server is the public SMART sandbox with synthetic patients.
            </p>
            <div className="ehr-actions">
              <button type="button" className="secondary" onClick={signInToEhr} disabled={loading}>
                Sign in to EHR sandbox
              </button>
              <button
                type="button"
                className="secondary"
                disabled={loading}
                onClick={() => loadFromEhr(async () => ({ resources: await loadSampleRecord(), source: "a sample FHIR record" }))}
              >
                Use a sample record
              </button>
            </div>
            <details>
              <summary>FHIR server</summary>
              <label htmlFor="fhir-server" className="sr-only">FHIR server address</label>
              <input id="fhir-server" value={fhirServer} onChange={(e) => setFhirServer(e.target.value)} spellCheck={false} />
            </details>
          </section>
        )}

        {data && (
          <section className="understood" aria-label="What we understood">
            <h2>{ehr ? "What we read from the EHR record" : "What we read from the description"}</h2>
            <ul>
              {patientFacts(data.patient).map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
            <p className="fine">{ehr ? "Facts missing from the record" : "If something is missing or wrong, edit the description. Missing facts"} show as &ldquo;Check&rdquo;, never as a pass.</p>
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
