"use client";

import { useState } from "react";

import type { Relay, Snapshot } from "@/lib/api";
import { fieldLabel, withheldReason } from "@/lib/labels";
import { PanelHeading } from "./TranscriptPanel";

/**
 * The receiving end. This column is the relay gate made visible: what will be spoken to the nurse
 * and — just as important — what is being held back, and in plain words why.
 *
 * The stress controls sit here rather than on a hidden debug page because they are the point of
 * the demo: a judge should be able to delay the cross-check, break the voice provider, and watch
 * the gate hold. They are boxed off at the bottom so nobody mistakes them for clinical controls.
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
    <section className="flex min-h-[24rem] flex-col lg:min-h-0">
      <PanelHeading hint={facts.length > 0 ? `${verified.length} of ${facts.length} pass` : undefined}>
        Relay to the receiving clinician
      </PanelHeading>

      <div className="scroll min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-3.5">
        <Section label="Verified, will be spoken" tint="var(--color-verified)" count={verified.length}>
          {verified.length === 0 ? (
            <p className="text-[12px] text-muted">Nothing has been confirmed yet.</p>
          ) : (
            <ul className="space-y-1">
              {verified.map((fact) => (
                <li
                  key={fact.field}
                  className="flex items-baseline gap-2 rounded border border-verified/25 bg-verified/[0.06] px-2 py-1.5 text-[13px]"
                >
                  <span className="size-1.5 shrink-0 translate-y-[-1px] rounded-full bg-verified" />
                  <span className="text-[11px] text-muted">{fieldLabel(fact.field)}</span>
                  <span className="ml-auto font-semibold text-ink">{fact.value}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section label="Held back" tint="var(--color-superseded)" count={withheld.length}>
          {withheld.length === 0 ? (
            <p className="text-[12px] text-muted">Nothing is being withheld.</p>
          ) : (
            <ul className="space-y-1">
              {withheld.map((fact) => (
                <li
                  key={fact.field}
                  className="flex items-baseline gap-2 rounded border border-edge px-2 py-1.5 text-[12px]"
                >
                  <span className="font-medium text-muted">{fieldLabel(fact.field)}</span>
                  <span className="ml-auto text-right text-superseded">
                    {withheldReason(fact.status)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <div className="flex items-center gap-2">
          <div
            role="group"
            aria-label="Relay language"
            className="flex overflow-hidden rounded-md border border-edge-strong bg-raised text-xs"
          >
            {(["en", "hi"] as const).map((code) => (
              <button
                key={code}
                type="button"
                aria-pressed={lang === code}
                onClick={() => setLang(code)}
                className={`min-h-10 cursor-pointer px-3 font-semibold tracking-wider transition-colors ${
                  lang === code
                    ? "bg-heard text-white"
                    : "text-muted hover:bg-panel hover:text-ink"
                }`}
              >
                {code.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={busy || verified.length === 0}
            onClick={() => onRelay(lang)}
            className="btn btn-solid btn-lg flex-1"
            style={{ ["--tint" as string]: "var(--color-verified)" }}
          >
            Relay verified facts
          </button>
        </div>

        {relay ? (
          <div className="space-y-2">
            <p className="raised p-3 text-[13px] leading-relaxed text-ink">{relay.plain}</p>
            <p
              className="well p-2 font-mono text-[11px] leading-relaxed break-words text-muted"
              title="exactly what is sent to Rime"
            >
              {relay.text}
            </p>
            {relay.withheld.length > 0 ? (
              <p className="rounded border border-corrected/40 bg-corrected/10 px-2 py-1.5 text-[12px] text-corrected">
                withheld from the relay: {relay.withheld.map(fieldLabel).join(", ")}
              </p>
            ) : null}
            <Completeness completeness={relay.completeness} />
          </div>
        ) : null}

        <div className="space-y-3 rounded-md border border-dashed border-edge-strong bg-panel p-3">
          <div className="text-[11px] font-medium text-muted">Stress the system</div>

          <label className="flex items-center gap-2 text-[12px]">
            <span className="text-muted">cross-check delay</span>
            <input
              type="number"
              min={0}
              step={500}
              value={toolDelay}
              onChange={(event) => onToolDelay(Number(event.target.value))}
              disabled={busy}
              className="field tabular ml-auto w-24 py-1.5 text-xs"
            />
            <span className="text-faint">ms</span>
          </label>

          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onRime
                ? onProvider("browser_fallback", "Rime unreachable (demo)")
                : onProvider("rime", "Rime restored")
            }
            className="btn btn-tint w-full"
            style={{
              ["--tint" as string]: onRime ? "var(--color-conflicted)" : "var(--color-verified)",
            }}
          >
            {onRime ? "Simulate losing Rime" : "Restore Rime"}
          </button>
          <p className="text-[11px] leading-relaxed text-faint">
            The fallback voice announces itself before it speaks, the badge turns red and the switch
            is logged. Nothing is ever relayed silently on a different voice.
          </p>
        </div>
      </div>
    </section>
  );
}

function Section({
  label,
  tint,
  count,
  children,
}: {
  label: string;
  tint: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 text-[11px]">
        <span className="font-medium text-muted">{label}</span>
        <span className="tabular font-semibold" style={{ color: tint }}>
          {count}
        </span>
      </div>
      {children}
    </div>
  );
}

function Completeness({ completeness }: { completeness: Record<string, boolean> }) {
  const covered = Object.values(completeness).filter(Boolean).length;
  const total = Object.keys(completeness).length;
  const pct = total === 0 ? 0 : Math.round((covered / total) * 100);

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 text-[11px]">
        <span className="font-medium text-muted">ATMIST-AMBO coverage</span>
        <span className="tabular ml-auto font-semibold text-ink">
          {covered}/{total}
        </span>
      </div>

      {/* A handover with gaps is still relayable; the bar says how much of the frame was filled. */}
      <div
        role="progressbar"
        aria-valuenow={covered}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label="ATMIST-AMBO coverage"
        className="mb-2 h-1.5 overflow-hidden rounded-full bg-well"
      >
        <div
          className="h-full rounded-full bg-verified transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex flex-wrap gap-1">
        {Object.entries(completeness).map(([slot, present]) => (
          <span
            key={slot}
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              present
                ? "border-verified/40 bg-verified/[0.08] font-medium text-verified"
                : "border-edge text-superseded"
            }`}
          >
            {SLOT_LABELS[slot] ?? slot}
          </span>
        ))}
      </div>
    </div>
  );
}
