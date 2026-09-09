import type { FactStatus } from "@/lib/api";

/**
 * How a field is written on screen.
 *
 * The engine's field keys are identifiers — `gcs`, `spo2`, `time_of_incident`. Rendering them raw
 * puts lowercase clinical acronyms in front of a clinician, which reads as a bug in a product whose
 * entire claim is that it gets details right. Anything not listed here falls back to the key with
 * underscores opened out, so a new slot in the engine still renders sensibly without a change here.
 */
const FIELD_LABELS: Record<string, string> = {
  gcs: "GCS",
  bp: "BP",
  hr: "HR",
  rr: "RR",
  spo2: "SpO₂",
  mrn: "MRN",
  patient_name: "patient name",
  time_of_incident: "time of incident",
};

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replace(/_/g, " ");
}

/**
 * Why a fact is being held back from the relay, in the words a clinician would use.
 *
 * The gate already shows the engine's own status on the fact row. Repeating the enum here would
 * say nothing new; what the receiving end needs to know is what is missing before the value can
 * be spoken to them.
 */
const WITHHELD_REASONS: Record<FactStatus, string> = {
  HEARD: "heard once, not read back",
  INFERRED: "inferred, never stated",
  CORRECTED: "corrected, awaiting read-back",
  CONFLICTED: "two values, unresolved",
  VERIFIED: "cleared",
  SUPERSEDED: "replaced by a later value",
};

export function withheldReason(status: FactStatus): string {
  return WITHHELD_REASONS[status];
}

/**
 * Who spoke, as a clinician would name them.
 *
 * `sender` and `receiver` are the engine's roles for the two ends of a handover. Printing them
 * raw above a line of speech asks the reader to translate; the transcript should read like a
 * record of two people talking.
 */
const SPEAKER_LABELS: Record<string, string> = {
  sender: "paramedic",
  receiver: "receiving clinician",
  agent: "agent",
  system: "system",
};

export function speakerLabel(speaker: string): string {
  return SPEAKER_LABELS[speaker] ?? speaker;
}
