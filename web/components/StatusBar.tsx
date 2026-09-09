"use client";

import type { Connection } from "@/lib/useHandover";
import type { HearbackEvent, Snapshot } from "@/lib/api";

/**
 * The masthead of the record. It answers the only question a clinician has mid-handover — is it
 * safe to pass this on yet? — and then shows the mechanism, so a judge can watch the epoch move
 * and the ledger cut land rather than take the state's word for it.
 *
 * The phase is sized and coloured to be read from across a room, and announced to a screen reader
 * when it changes, because it is a state transition rather than a decoration.
 *
 * Capitals are reserved for the machine's own vocabulary — the phase, the six truth states, the
 * provider name are literal values the engine emits. Every label a human wrote stays in sentence
 * case, so the two can never be confused for each other.
 */

export type Phase =
  | "Connecting"
  | "Listening"
  | "Speaking"
  | "Verifying"
  | "Conflict"
  | "Safe to relay";

export function phaseOf(snapshot: Snapshot | null): Phase {
  if (!snapshot) return "Connecting";
  const facts = Object.values(snapshot.state.facts);
  if (facts.some((f) => f.status === "CONFLICTED")) return "Conflict";
  if (snapshot.next_line) return "Speaking";
  if (snapshot.awaiting_confirmation.length > 0) return "Verifying";
  if (facts.length > 0 && facts.every((f) => f.status === "VERIFIED")) return "Safe to relay";
  return "Listening";
}

export const PHASE_TINT: Record<Phase, string> = {
  Connecting: "var(--color-superseded)",
  Listening: "var(--color-heard)",
  Speaking: "var(--color-heard)",
  Verifying: "var(--color-corrected)",
  Conflict: "var(--color-conflicted)",
  "Safe to relay": "var(--color-verified)",
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
  const live = connection === "live";

  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-edge bg-raised px-4 py-3">
      <div className="flex items-center gap-2.5">
        <Mark />
        <div className="leading-none">
          <div className="text-[15px] font-semibold tracking-tight text-ink">Hearback</div>
          <div className="mt-1 text-[11px] text-faint">handover firewall</div>
        </div>
      </div>

      {/* The phase owns the loudest colour on the bar; everything else stays grey until it matters. */}
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2 rounded-md border px-3 py-1.5"
        style={{
          color: PHASE_TINT[phase],
          borderColor: `color-mix(in oklab, ${PHASE_TINT[phase]} 35%, var(--color-edge))`,
          background: `color-mix(in oklab, ${PHASE_TINT[phase]} 9%, var(--color-raised))`,
        }}
      >
        <span
          className={`size-2 rounded-full ${phase === "Conflict" ? "anim-blink" : ""}`}
          style={{ background: "currentColor" }}
        />
        <span className="text-[13px] font-semibold tracking-[0.06em] uppercase">{phase}</span>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <Readout label="epoch">
          <span className="text-ink">{snapshot?.state.epoch ?? "—"}</span>
        </Readout>

        <Readout label="last ledger cut">
          {lastCut ? (
            <span className="text-ink">
              <span className="font-semibold text-conflicted">{String(lastCut.data.cutoff_word)}</span>
              <span className="text-faint"> at </span>
              {String(lastCut.data.cutoff_ms)}
              <span className="text-faint"> ms</span>
            </span>
          ) : (
            <span className="text-faint">—</span>
          )}
        </Readout>

        <Readout label="stale writes fenced">
          <span className={dropped > 0 ? "font-semibold text-corrected" : "text-faint"}>
            {dropped}
          </span>
        </Readout>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-3">
        {error ? (
          <span
            role="alert"
            className="rounded border border-conflicted/40 bg-conflicted/[0.08] px-2 py-1 text-[11px] font-medium text-conflicted"
          >
            {error}
          </span>
        ) : null}

        <Readout label="session">
          <span className="font-mono text-[11px] text-muted">{sessionId ?? "—"}</span>
        </Readout>

        <Badge
          tint={
            live
              ? "var(--color-verified)"
              : connection === "offline"
                ? "var(--color-conflicted)"
                : "var(--color-superseded)"
          }
          dot
        >
          {live ? "stream live" : connection === "offline" ? "stream down" : "connecting"}
        </Badge>

        <Badge
          tint={onRime ? "var(--color-verified)" : "var(--color-conflicted)"}
          title={
            onRime ? "Rime is speaking" : "Rime is unavailable; the fallback voice announces itself"
          }
        >
          <span className="text-faint">voice</span>
          <span className="font-semibold tracking-wider uppercase">{provider}</span>
        </Badge>
      </div>
    </header>
  );
}

/** The product in one glyph: speech delivered, then stopped. Same geometry as the favicon. */
function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7 shrink-0" role="img" aria-label="Hearback">
      <rect width="32" height="32" rx="7" fill="var(--color-well)" />
      <g fill="var(--color-heard)">
        <rect x="6" y="13" width="2.5" height="6" rx="1.25" />
        <rect x="10" y="9" width="2.5" height="14" rx="1.25" />
        <rect x="14" y="11" width="2.5" height="10" rx="1.25" />
      </g>
      <rect x="19" y="6" width="2" height="20" rx="1" fill="var(--color-conflicted)" />
      <rect x="23" y="12" width="2.5" height="8" rx="1.25" fill="var(--color-edge-strong)" />
    </svg>
  );
}

/** A gauge: quiet label, loud value, fixed digits so columns of numbers line up. */
function Readout({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="leading-tight">
      <div className="text-[11px] text-faint">{label}</div>
      <div className="tabular mt-0.5 text-[13px] font-medium">{children}</div>
    </div>
  );
}

function Badge({
  tint,
  title,
  dot,
  children,
}: {
  tint: string;
  title?: string;
  dot?: boolean;
  children: React.ReactNode;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[11px]"
      style={{
        color: tint,
        borderColor: `color-mix(in oklab, ${tint} 32%, var(--color-edge))`,
        background: `color-mix(in oklab, ${tint} 7%, var(--color-raised))`,
      }}
    >
      {dot ? <span className="size-1.5 rounded-full" style={{ background: "currentColor" }} /> : null}
      {children}
    </span>
  );
}
