export type TrustLevel =
  | "unconfirmed"
  | "indicative"
  | "probable"
  | "confirmed"
  | "indisputable";

export interface TrustItem {
  id: string;
  title: string;
  summary: string;
  trust_score: number;
  trust_level: TrustLevel;
  sources: string[];
  object_id?: string | null;
}

export interface JourneyStep {
  id: string;
  step_order: number;
  label: string;
  actor_name: string | null;
  status: string;
}

export interface Journey {
  id: string;
  title: string;
  total_steps: number;
  current_step: number;
  progress_bar: string;
  steps: JourneyStep[];
}

export interface Dashboard {
  greeting: string;
  focus: string;
  state: string;
  trust_items: TrustItem[];
  active_journeys: Journey[];
  mistral_available: boolean;
  session_id?: string;
  actor_id?: string;
  presentation_mode?: string;
}

export interface CapabilityMatch {
  adapter_id: string;
  adapter_name: string;
  action: string;
  resource: string;
  required_assurance: string | null;
  assurance_met: boolean;
}

export interface PlannedIntent {
  intent_id: string;
  raw_input: string;
  category: string;
  action: string;
  confidence: number;
  trust_level: TrustLevel;
  trust_score: number;
  rationale: string;
  parse_mode: string;
  status: string;
  capability_match: CapabilityMatch | null;
  can_execute: boolean;
  block_reason: string | null;
}

const API = "";
const SESSION_KEY = "eira_session_id";

let sessionId: string | null = null;

function loadStoredSession(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

sessionId = loadStoredSession();

export interface OidcConfig {
  issuer: string | null;
  client_id: string | null;
  redirect_uri: string;
  scopes: string;
  mock_enabled: boolean;
  login_mode: "mock" | "oidc";
  login_path: string;
  callback_path: string;
}

export interface LoginResult {
  session_id: string;
  actor_id: string;
  actor_name?: string;
  org_unit?: string;
  assurance_level: string;
}

export function getSessionId(): string | null {
  return sessionId;
}

export function setSessionId(id: string): void {
  sessionId = id;
  try {
    localStorage.setItem(SESSION_KEY, id);
  } catch {
    /* private mode */
  }
}

export function clearSessionId(): void {
  sessionId = null;
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* private mode */
  }
}

export function consumeSessionFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  const sid = params.get("session_id");
  const authError = params.get("auth_error");
  if (authError) {
    params.delete("auth_error");
    const query = params.toString();
    const next = `${window.location.pathname}${query ? `?${query}` : ""}`;
    window.history.replaceState({}, "", next);
    throw new Error(authError);
  }
  if (!sid) return null;

  setSessionId(sid);
  params.delete("session_id");
  const query = params.toString();
  const next = `${window.location.pathname}${query ? `?${query}` : ""}`;
  window.history.replaceState({}, "", next);
  return sid;
}

function apiHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  if (sessionId) headers["X-EIRA-Session-Id"] = sessionId;
  return headers;
}

export async function fetchOidcConfig(): Promise<OidcConfig> {
  const res = await fetch(`${API}/v1/auth/oidc/config`);
  if (!res.ok) throw new Error("OIDC config unavailable");
  return res.json();
}

export async function mockLogin(body: {
  email: string;
  name?: string;
  org_unit?: string;
}): Promise<LoginResult> {
  const res = await fetch(`${API}/v1/auth/oidc/mock-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "Mock login failed");
  }
  const data: LoginResult = await res.json();
  setSessionId(data.session_id);
  return data;
}

export function startOidcLogin(): void {
  window.location.assign(`${API}/v1/auth/oidc/login`);
}

export async function fetchDashboard(): Promise<Dashboard> {
  const res = await fetch(`${API}/v1/dashboard`, { headers: apiHeaders() });
  if (!res.ok) throw new Error("Dashboard unavailable");
  const data: Dashboard = await res.json();
  if (data.session_id) setSessionId(data.session_id);
  return data;
}

export async function planIntent(raw_input: string): Promise<PlannedIntent> {
  const res = await fetch(`${API}/v1/intent/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...apiHeaders() },
    body: JSON.stringify({
      raw_input,
      focus: "Kommunepilot",
      use_mistral: true,
    }),
  });
  if (!res.ok) throw new Error("Intent plan failed");
  return res.json();
}

export async function advanceJourney(journeyId: string): Promise<Journey> {
  const res = await fetch(`${API}/v1/journeys/${journeyId}/advance`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Advance failed");
  return res.json();
}
