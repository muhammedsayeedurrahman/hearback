/**
 * Client for the Hearback sidecar.
 *
 * The dashboard holds no truth state of its own: it renders what `/state` returns and posts what
 * the clinician does. Anything else would be a second copy of the state, drifting from the one the
 * relay gate actually consults.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_HEARBACK_API?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export type FactStatus =
  | "HEARD"
  | "INFERRED"
  | "CORRECTED"
  | "CONFLICTED"
  | "VERIFIED"
  | "SUPERSEDED";

export interface Delivered {
  text_heard: string;
  cutoff_word: string | null;
  cutoff_ms: number | null;
  complete: boolean;
}

export interface FactVersion {
  value: string;
  status: FactStatus;
  epoch: number;
  source_text: string;
  delivered: Delivered | null;
}

export interface Fact extends FactVersion {
  field: string;
  history: FactVersion[];
  conflict: FactVersion[];
}

export interface TruthState {
  session_id: string;
  epoch: number;
  provider: string;
  facts: Record<string, Fact>;
  event_count: number;
}

export interface NextLine {
  kind: "confirm" | "reconcile" | "conflict" | "acknowledge" | string;
  text: string;
  plain: string;
  fields: string[];
  inline_speed_alpha: string | null;
  critical: boolean;
}

export interface Relay {
  text: string;
  plain: string;
  lang: "en" | "hi";
  ready: boolean;
  fields: string[];
  withheld: string[];
  inline_speed_alpha: string | null;
  completeness: Record<string, boolean>;
}

export interface Snapshot {
  state: TruthState;
  stress: { tool_delay_ms: number; extract_delay_ms: number };
  next_line: NextLine | null;
  awaiting_confirmation: string[];
  session_id?: string;
  epoch?: number;
  applied?: boolean;
  requested_epoch?: number;
  source?: string;
  error?: string | null;
  relay?: Relay;
  delivered?: Delivered;
  /** The sidecar's verdict on whether this turn was a confirmation. Only /utterance sets it. */
  confirmation?: { affirmation: boolean; negation: boolean };
  /** Whether /verify settled the fact, and why it did not. */
  verified?: boolean;
  challenge?: string | null;
}

export interface HearbackEvent {
  seq: number;
  type: string;
  epoch: number;
  at_ms: number;
  data: Record<string, unknown>;
}

/** Every event the engine can emit. EventSource has no wildcard, so the list has to be explicit. */
export const EVENT_TYPES = [
  "session_created",
  "utterance",
  "stale_llm",
  "fact_added",
  "fact_restated",
  "fact_conflicted",
  "fact_corrected",
  "fact_verified",
  "conflict_resolved",
  "ledger_cut",
  "provider_changed",
  "relay_requested",
  "confirmation_challenged",
] as const;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return unwrap<T>(response);
}

async function get<T>(path: string, params: Record<string, string>): Promise<T> {
  const query = new URLSearchParams(params).toString();
  return unwrap<T>(await fetch(`${API_BASE}${path}?${query}`));
}

async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  let detail = response.statusText;
  try {
    const body = await response.json();
    detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
  } catch {
    /* the body was not JSON; the status text is all there is */
  }
  throw new ApiError(detail, response.status);
}

export const api = {
  health: () => get<{ status: string; extractor: string; livekit_configured: boolean }>("/health", {}),

  createSession: (identity = "paramedic") => post<Snapshot>("/session", { identity }),

  state: (sessionId: string) => get<Snapshot>("/state", { session_id: sessionId }),

  /** Report a finished turn. The returned epoch stamps everything produced in answer to it. */
  utterance: (sessionId: string, text: string, speaker: "sender" | "receiver" = "sender") =>
    post<Snapshot>("/utterance", { session_id: sessionId, text, speaker }),

  extract: (sessionId: string, text: string, epoch: number) =>
    post<Snapshot>("/extract", { session_id: sessionId, text, epoch }),

  /**
   * Confirm a read-back. Passing the confirming turn lets the engine refuse a "yes" that names a
   * value the listener was never read back; a click on a displayed value carries no turn, because
   * the click itself is the confirmation of what is on screen.
   */
  verify: (sessionId: string, field: string, spoken?: string) =>
    post<Snapshot>("/verify", { session_id: sessionId, field, ...(spoken ? { spoken } : {}) }),

  resolve: (sessionId: string, field: string, value: string) =>
    post<Snapshot>("/resolve", { session_id: sessionId, field, value }),

  /** What the listener actually got of a spoken sentence, and where it was cut off. */
  delivery: (
    sessionId: string,
    field: string,
    speechEpoch: number,
    text: string,
    durationMs: number,
    interruptedAtMs?: number,
  ) =>
    post<Snapshot>("/delivery", {
      session_id: sessionId,
      field,
      speech_epoch: speechEpoch,
      text,
      duration_ms: durationMs,
      ...(interruptedAtMs === undefined ? {} : { interrupted_at_ms: interruptedAtMs }),
    }),

  relay: (sessionId: string, lang: "en" | "hi") =>
    post<Snapshot>("/relay", { session_id: sessionId, lang }),

  provider: (sessionId: string, provider: string, reason: string) =>
    post<Snapshot>("/provider", { session_id: sessionId, provider, reason }),

  toolDelay: (sessionId: string, delayMs: number, target: "tool" | "extract" = "tool") =>
    post<Snapshot>("/stress/tool-delay", { session_id: sessionId, delay_ms: delayMs, target }),

  eventsUrl: (sessionId: string, since = 0) =>
    `${API_BASE}/events?session_id=${encodeURIComponent(sessionId)}&since=${since}`,
};

/** Coda at speedAlpha 0.95 averages about 2.8 words a second; used to time simulated speech. */
export const MS_PER_WORD = 360;

export function speechDurationMs(text: string): number {
  return Math.max(text.trim().split(/\s+/).length * MS_PER_WORD, 1);
}
