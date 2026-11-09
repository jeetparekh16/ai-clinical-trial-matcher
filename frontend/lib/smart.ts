// SMART on FHIR standalone launch (SMART App Launch 2.x) for a public
// browser app: discovery, authorization code with PKCE (S256), token
// exchange, then reading the patient's resources. No client secret, no
// server, no library.

export const DEFAULT_FHIR_SERVER = "https://launch.smarthealthit.org/v/r4/fhir";
export const CLIENT_ID = "trial-match-demo";
const STORAGE_KEY = "trialmatch.smart";
const SCOPES = [
  "launch/patient",
  "openid",
  "fhirUser",
  "patient/Patient.read",
  "patient/Condition.read",
  "patient/Observation.read",
  "patient/MedicationRequest.read",
].join(" ");

// LOINC codes the matcher understands (labs, vitals, ECOG); keeps the
// Observation query small.
const OBSERVATION_CODES = [
  "4548-4", "17856-6", "41995-2", "33914-3", "62238-1", "48642-3", "48643-1", "98979-8", "69405-9",
  "39156-5", "8480-6", "85354-9", "55284-4", "13457-7", "18262-6", "2089-1", "10230-1", "18010-0", "8806-2", "89247-1",
].map((code) => `http://loinc.org|${code}`).join(",");

interface PendingLaunch {
  iss: string;
  tokenEndpoint: string;
  verifier: string;
  state: string;
  redirectUri: string;
}

export class SmartError extends Error {}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(bytes = 32): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(bytes)));
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64Url(new Uint8Array(digest));
}

function store(value: PendingLaunch | null) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Private mode or blocked storage: the launch cannot be completed.
  }
}

function load(): PendingLaunch | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PendingLaunch) : null;
  } catch {
    return null;
  }
}

/** The page's own URL without query or hash: the OAuth redirect URI. */
export function currentRedirectUri(): string {
  return window.location.origin + window.location.pathname;
}

/** Step 1: discover the EHR's endpoints and send the user to sign in and pick a patient. */
export async function startLaunch(iss: string): Promise<void> {
  const server = iss.replace(/\/+$/, "");
  let config: { authorization_endpoint?: string; token_endpoint?: string; code_challenge_methods_supported?: string[] };
  try {
    const response = await fetch(`${server}/.well-known/smart-configuration`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(String(response.status));
    config = await response.json();
  } catch {
    throw new SmartError(`Could not reach a SMART on FHIR server at ${server}. Check the address.`);
  }
  if (!config.authorization_endpoint || !config.token_endpoint) {
    throw new SmartError("This FHIR server does not advertise SMART on FHIR sign in.");
  }
  if (config.code_challenge_methods_supported && !config.code_challenge_methods_supported.includes("S256")) {
    throw new SmartError("This FHIR server does not support PKCE (S256), which browser apps need.");
  }

  const verifier = randomString(48);
  const state = randomString(16);
  const redirectUri = currentRedirectUri();
  store({ iss: server, tokenEndpoint: config.token_endpoint, verifier, state, redirectUri });

  const url = new URL(config.authorization_endpoint);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_ID,
    redirect_uri: redirectUri,
    scope: SCOPES,
    state,
    aud: server,
    code_challenge: await challengeFor(verifier),
    code_challenge_method: "S256",
  }).toString();
  window.location.assign(url.toString());
}

/** True when the page was opened by the EHR's redirect after sign in. */
export function isLaunchCallback(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.has("state") && (params.has("code") || params.has("error"));
}

/**
 * Step 2: exchange the code for a token, read the patient's resources, and
 * clean the code out of the address bar.
 */
export async function completeLaunch(): Promise<{ resources: unknown[]; server: string }> {
  const params = new URLSearchParams(window.location.search);
  window.history.replaceState(null, "", currentRedirectUri());
  const pending = load();
  store(null);

  if (params.get("error")) {
    throw new SmartError(`The EHR did not grant access: ${params.get("error_description") || params.get("error")}.`);
  }
  if (!pending || params.get("state") !== pending.state) {
    throw new SmartError("This sign in link has expired or was not started here. Start again.");
  }

  const tokenResponse = await fetch(pending.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code: params.get("code") ?? "",
      redirect_uri: pending.redirectUri,
      client_id: CLIENT_ID,
      code_verifier: pending.verifier,
    }),
  }).catch(() => null);
  if (!tokenResponse?.ok) throw new SmartError("The EHR rejected the sign in. Start again.");
  const token = await tokenResponse.json();
  if (!token.access_token || !token.patient) throw new SmartError("The EHR did not return a patient. Pick a patient when asked.");

  const get = async (path: string): Promise<unknown> => {
    const response = await fetch(`${pending.iss}/${path}`, {
      headers: { Authorization: `Bearer ${token.access_token}`, Accept: "application/fhir+json" },
    });
    if (!response.ok) throw new SmartError(`The EHR refused to share ${path.split("?")[0]} (${response.status}).`);
    return response.json();
  };
  const id = encodeURIComponent(token.patient);
  const [patient, conditions, observations, medications] = await Promise.all([
    get(`Patient/${id}`),
    get(`Condition?patient=${id}&_count=200`),
    get(`Observation?patient=${id}&code=${encodeURIComponent(OBSERVATION_CODES)}&_count=500`),
    get(`MedicationRequest?patient=${id}&_count=200`),
  ]);
  return { resources: [patient, conditions, observations, medications], server: pending.iss };
}
