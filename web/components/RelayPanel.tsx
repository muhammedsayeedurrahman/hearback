"use client";

import { useState } from "react";

import type { Relay, Snapshot } from "@/lib/api";
import { PanelHeading } from "./TranscriptPanel";

/**
 * The receiving end. This column is the relay gate made visible: what will be spoken to the nurse,
 * and — just as important — what is being held back and why.
 *
 * The stress controls sit here rather than in a hidden debug page because they are the point of
 * the demo: a judge should be able to delay the cross-check, break the voice provider, and watch
 * the gate hold.
 */

const SLOT_LABELS: Record<string, string> = {
  identity: "Identity",
  age: "Age",
  time_of_incident: "Time",
  mechanism: "Mechanism",
  injuries: "Injuries",
  signs: "Signs",
  treatment: "Treatment",
  allergies: "Allergies",
  medications: "Medications",
  background: "Background",
  other: "Other",
};

export function RelayPanel({
  snapshot,
  relay,
  busy,
  onRelay,
  onProvider,
  onToolDelay,
}: {
  snapshot: Snapshot | null;
  relay: Relay | null;
  busy: boolean;
  onRelay: (lang: "en" | "hi") => void;
  onProvider: (provider: string, reason: string) => void;
  onToolDelay: (delayMs: number) => void;
}) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const facts = Object.values(snapshot?.state.facts ?? {});
  const verified = facts.filter((f) => f.status === "VERIFIED");
  const withheld = facts.filter((f) => f.status !== "VERIFIED");
  const onRime = (snapshot?.state.provider ?? "rime") === "rime";
  const toolDelay = snapshot?.stress.tool_delay_ms ?? 0;

  return (
    <section className="flex min-h-0 flex-col">
      <PanelHeading>Relay to the receiving clinician</PanelHeading>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        <div>
          <div className="mb-1 flex items-center gap-2 text-[11px] tracking-wider text-muted uppercase">
            <span>verified · will be spoken</span>
            <span className="tabular text-verified">{verified.length}</span>
          </div>
          {verified.length === 0 ? (
            <p className="text-xs text-muted">Nothing has been confirmed yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {verified.map((fact) => (
                <li key={fact.field} className="flex gap-2">
                  <span className="text-muted">{fact.field.replace(/_/g, " ")}</span>
                  <span className="ml-auto text-ink">{fact.value}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-1 text-[11px] tracking-wider text-muted uppercase">
            held back · not verified
          </div>
          {withheld.length === 0 ? (
            <p className="text-xs text-muted">Nothing is being withheld.</p>
          ) : (
            <ul className="space-y-1 text-xs">
              {withheld.map((fact) => (
                <li key={fact.field} className="flex gap-2 text-superseded">
                  <span>{fact.field.replace(/_/g, " ")}</span>
                  <span className="ml-auto">{fact.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex overflow-hidden rounded border border-edge text-xs">
            {(["en", "hi"] as const).map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLang(code)}
                className={`px-2 py-1 ${lang === code ? "bg-heard/15 text-heard" : "text-muted"}`}
              >
                {code.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={busy || verified.length === 0}
            onClick={() => onRelay(lang)}
            className="rounded border border-verified/50 px-3 py-1.5 text-sm text-verified hover:bg-verified/10 disabled:opacity-40"
          >
            Relay verified facts
          </button>
        </div>

        {relay ? (
          <div className="space-y-2">
            <p className="rounded border border-edge bg-panel p-2 text-sm">{relay.plain}</p>
            <p
              className="rounded border border-edge bg-board p-2 font-mono text-[11px] break-words text-muted"
              title="exactly what is sent to Rime"
            >
              {relay.text}
            </p>
            {relay.withheld.length > 0 ? (
              <p className="text-xs text-corrected">
                withheld from the relay: {relay.withheld.join(", ")}
              </p>
            ) : null}
            <Completeness completeness={relay.completeness} />
          </div>
        ) : null}

        <div className="space-y-2 border-t border-edge pt-3">
          <div className="text-[11px] tracking-wider text-muted uppercase">Stress the system</div>

          <label className="flex items-center gap-2 text-xs">
            <span className="text-muted">cross-check delay</span>
            <input
              type="number"
              min={0}
              step={500}
              value={toolDelay}
              onChange={(event) => onToolDelay(Number(event.target.value))}
              disabled={busy}
              className="tabular w-24 rounded border border-edge bg-board px-1.5 py-1 outline-none focus:border-heard/60"
            />
            <span className="text-muted">ms</span>
          </label>

          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onRime
                ? onProvider("browser_fallback", "Rime unreachable (demo)")
                : onProvider("rime", "Rime restored")
            }
            className={`w-full rounded border px-2 py-1.5 text-xs ${
              onRime
                ? "border-conflicted/60 text-conflicted hover:bg-conflicted/10"
                : "border-verified/50 text-verified hover:bg-verified/10"
            } disabled:opacity-40`}
          >
            {onRime ? "Simulate losing Rime" : "Restore Rime"}
          </button>
          <p className="text-[11px] text-muted">
            The fallback voice announces itself before it speaks, the badge turns red and the switch
            is logged. Nothing is ever relayed silently on a different voice.
          </p>
        </div>
      </div>
    </section>
  );
}

function Completeness({ completeness }: { completeness: Record<string, boolean> }) {
  const covered = Object.values(completeness).filter(Boolean).length;
  const total = Object.keys(completeness).length;
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-[11px] tracking-wider text-muted uppercase">
        <span>ATMIST-AMBO coverage</span>
        <span className="tabular">
          {covered}/{total}
        </span>
      </div>
      <div className="flex flex-wrap gap-1">
        {Object.entries(completeness).map(([slot, present]) => (
          <span
            key={slot}
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              present ? "border-verified/50 text-verified" : "border-edge text-superseded"
            }`}
          >
            {SLOT_LABELS[slot] ?? slot}
          </span>
        ))}
      </div>
    </div>
  );
}
