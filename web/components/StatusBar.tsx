"use client";

import type { Connection } from "@/lib/useHandover";
import type { HearbackEvent, Snapshot } from "@/lib/api";

/**
 * One line that answers the only question a clinician has mid-handover: is it safe to pass this
 * on yet? Everything else on the bar — the epoch, the last ledger cut, the provider — is there so
 * a judge can watch the mechanism move rather than take the state's word for it.
 */

export type Phase = "Connecting" | "Listening" | "Speaking" | "Verifying" | "Conflict" | "Safe to relay";

export function phaseOf(snapshot: Snapshot | null): Phase {
  if (!snapshot) return "Connecting";
  const facts = Object.values(snapshot.state.facts);
  if (facts.some((f) => f.status === "CONFLICTED")) return "Conflict";
  if (snapshot.next_line) return "Speaking";
  if (snapshot.awaiting_confirmation.length > 0) return "Verifying";
  if (facts.length > 0 && facts.every((f) => f.status === "VERIFIED")) return "Safe to relay";
  return "Listening";
}

const PHASE_STYLE: Record<Phase, string> = {
  Connecting: "text-muted",
  Listening: "text-heard",
  Speaking: "text-heard",
  Verifying: "text-corrected",
  Conflict: "text-conflicted",
  "Safe to relay": "text-verified",
};

export function StatusBar({
  snapshot,
  events,
  connection,
  sessionId,
  error,
}: {
  snapshot: Snapshot | null;
  events: HearbackEvent[];
  connection: Connection;
  sessionId: string | null;
  error: string | null;
}) {
  const phase = phaseOf(snapshot);
  const provider = snapshot?.state.provider ?? "rime";
  const onRime = provider === "rime";
  const lastCut = [...events].reverse().find((e) => e.type === "ledger_cut" && e.data.cutoff_word);
  const dropped = events.filter((e) => e.type === "stale_llm").length;

  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-edge bg-panel px-4 py-2 text-xs">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold tracking-wide text-ink">HEARBACK</span>
        <span className="text-muted">handover firewall</span>
      </div>

      <div className={`font-semibold tracking-wide ${PHASE_STYLE[phase]}`}>{phase.toUpperCase()}</div>

      <div className="tabular text-muted">
        epoch <span className="text-ink">{snapshot?.state.epoch ?? "—"}</span>
      </div>

      <div className="tabular text-muted">
        last ledger cut{" "}
        <span className="text-ink">
          {lastCut ? `${String(lastCut.data.cutoff_word)} @ ${String(lastCut.data.cutoff_ms)} ms` : "—"}
        </span>
      </div>

      <div className="tabular text-muted">
        stale dropped <span className="text-ink">{dropped}</span>
      </div>

      <div className="ml-auto flex items-center gap-4">
        {error ? <span className="text-conflicted">{error}</span> : null}
        <span className="tabular text-muted">
          session <span className="text-ink">{sessionId ?? "—"}</span>
        </span>
        <span
          className={`rounded border px-2 py-0.5 font-semibold ${
            connection === "live"
              ? "border-verified/50 text-verified"
              : connection === "offline"
                ? "border-conflicted/60 text-conflicted"
                : "border-edge text-muted"
          }`}
        >
          {connection === "live" ? "STREAM LIVE" : connection === "offline" ? "STREAM DOWN" : "CONNECTING"}
        </span>
        <span
          title={onRime ? "Rime is speaking" : "Rime is unavailable; the fallback voice announces itself"}
          className={`rounded border px-2 py-0.5 font-semibold ${
            onRime ? "border-verified/50 text-verified" : "border-conflicted/60 text-conflicted"
          }`}
        >
          VOICE: {provider.toUpperCase()}
        </span>
      </div>
    </header>
  );
}
