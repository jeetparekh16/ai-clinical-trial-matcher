// Runs a match either through the FastAPI backend ("server") or entirely in
// the visitor's browser with Pyodide ("browser"), which is how the free
// GitHub Pages demo works: the same Python package, no server.

import type { MatchResponse } from "./types";

export interface MatchRequest {
  patient_description?: string | null;
  patient?: unknown;
  condition?: string | null;
  limit?: number;
}

export const ENGINE: "server" | "browser" = process.env.NEXT_PUBLIC_ENGINE === "browser" ? "browser" : "server";
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const PYODIDE_URL = process.env.NEXT_PUBLIC_PYODIDE_URL ?? "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
const CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies";
const CTGOV_FIELDS = [
  "NCTId", "BriefTitle", "OfficialTitle", "OverallStatus", "Phase", "Condition", "BriefSummary",
  "EligibilityCriteria", "Sex", "MinimumAge", "MaximumAge", "HealthyVolunteers",
  "LocationFacility", "LocationCity", "LocationState", "LocationCountry",
].join(",");

export class MatchError extends Error {}

export async function runMatch(request: MatchRequest, onStatus?: (status: string) => void): Promise<MatchResponse> {
  return ENGINE === "browser" ? browserMatch(request, onStatus) : serverMatch(request);
}

async function serverMatch(request: MatchRequest): Promise<MatchResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_PATH}/api/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new MatchError("The matching service is not running. Start the backend on port 8000.");
  }
  const body = await response.json();
  if (!response.ok) {
    throw new MatchError(typeof body.detail === "string" ? body.detail : "Check the description and try again.");
  }
  return body as MatchResponse;
}

// Minimal typing for the parts of Pyodide used here.
interface Pyodide {
  loadPackage(names: string[]): Promise<void>;
  unpackArchive(buffer: ArrayBuffer, format: string, options?: { extractDir?: string }): void;
  runPython(code: string): unknown;
  globals: { get(name: string): (...args: unknown[]) => string };
}

declare global {
  interface Window {
    loadPyodide?: (options: { indexURL: string }) => Promise<Pyodide>;
  }
}

let pyodidePromise: Promise<Pyodide> | null = null;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new MatchError("Could not load the in-browser Python runtime. Check your connection."));
    document.head.appendChild(script);
  });
}

/** Loads Pyodide, pydantic and the trialmatch package once per page. */
export function loadEngine(onStatus?: (status: string) => void): Promise<Pyodide> {
  if (!pyodidePromise) {
    pyodidePromise = (async () => {
      onStatus?.("Loading the matching engine (first time only)…");
      if (!window.loadPyodide) await loadScript(`${PYODIDE_URL}pyodide.js`);
      const pyodide = await window.loadPyodide!({ indexURL: PYODIDE_URL });
      await pyodide.loadPackage(["pydantic"]);
      const archive = await fetch(`${BASE_PATH}/py/trialmatch.zip`).then((r) => {
        if (!r.ok) throw new MatchError("Could not load the matcher package.");
        return r.arrayBuffer();
      });
      pyodide.unpackArchive(archive, "zip", { extractDir: "/home/pyodide/app" });
      pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide/app'); from trialmatch.engine import browser_prepare, browser_match");
      return pyodide;
    })().catch((error) => {
      pyodidePromise = null;
      throw error;
    });
  }
  return pyodidePromise;
}

async function fetchLiveStudies(condition: string): Promise<string | null> {
  const params = new URLSearchParams({
    "query.cond": condition,
    "filter.overallStatus": "RECRUITING",
    pageSize: "40",
    fields: CTGOV_FIELDS,
    format: "json",
  });
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    const response = await fetch(`${CTGOV_URL}?${params}`, { signal: controller.signal });
    clearTimeout(timer);
    if (!response.ok) return null;
    const text = await response.text();
    return JSON.parse(text).studies?.length ? text : null;
  } catch {
    return null;
  }
}

async function browserMatch(request: MatchRequest, onStatus?: (status: string) => void): Promise<MatchResponse> {
  const pyodide = await loadEngine(onStatus);
  const prepared = JSON.parse(pyodide.globals.get("browser_prepare")(JSON.stringify(request)));
  if (prepared.error) throw new MatchError(prepared.error);

  onStatus?.(`Searching ClinicalTrials.gov for ${prepared.condition}…`);
  const studies = await fetchLiveStudies(prepared.condition);
  onStatus?.("Checking eligibility criteria…");
  const result = JSON.parse(pyodide.globals.get("browser_match")(JSON.stringify(request), studies, studies === null));
  if (result.error) throw new MatchError(result.error);
  return result as MatchResponse;
}
