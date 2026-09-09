"use client";

import { useState } from "react";

import type { Delivered, Fact, FactVersion, Snapshot } from "@/lib/api";
import { fieldLabel } from "@/lib/labels";
import { StatusChip } from "./StatusChip";
import { PanelHeading } from "./TranscriptPanel";

/**
 * The centre column, and the widest, because it is the product: one row per clinical fact, its
 * live value, everything it used to be, and the words that were actually delivered about it.
 *
 * The heard sub-row is the part that does not exist in an ordinary transcript view. It is not what
 * the agent said; it is what the listener got before the audio stopped, which is what the next
 * sentence has to reconcile against. It carries the only saturated red on the screen for that
 * reason — the value above it is large and calm, and the cut is the one mark that interrupts it.
 */

export function TruthStatePanel({
  snapshot,
  busy,
  onDeliver,
  onVerify,
  onResolve,
}: {
  snapshot: Snapshot | null;
  busy: boolean;
  onDeliver: (interruptedAtMs?: number) => void;
  onVerify: (field: string) => void;
  onResolve: (field: string, value: string) => void;
}) {
  const facts = Object.values(snapshot?.state.facts ?? {});
  const awaiting = new Set(snapshot?.awaiting_confirmation ?? []);
  const verified = facts.filter((f) => f.status === "VERIFIED").length;

  return (
    <section className="flex min-h-[24rem] flex-col border-edge bg-raised lg:min-h-0 lg:border-r">
      <PanelHeading hint={facts.length > 0 ? `${verified} of ${facts.length} verified` : undefined}>
        Truth state
      </PanelHeading>
      <div className="scroll min-h-0 flex-1 overflow-y-auto">
        <NextLineCard snapshot={snapshot} busy={busy} onDeliver={onDeliver} />
        <div className="divide-y divide-edge">
          {facts.length === 0 ? (
            <p className="px-4 py-4 text-[13px] leading-relaxed text-muted">
              No facts yet. Every value starts as{" "}
              <span className="font-semibold text-heard">HEARD</span> and only a human confirmation
              moves it to <span className="font-semibold text-verified">VERIFIED</span>.
            </p>
          ) : null}
          {facts.map((fact) => (
            <FactRow
              key={fact.field}
              fact={fact}
              awaiting={awaiting.has(fact.field)}
              busy={busy}
              onVerify={onVerify}
              onResolve={onResolve}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function NextLineCard({
  snapshot,
  busy,
  onDeliver,
}: {
  snapshot: Snapshot | null;
  busy: boolean;
  onDeliver: (interruptedAtMs?: number) => void;
}) {
  const [cutMs, setCutMs] = useState(1300);
  const line = snapshot?.next_line;
  if (!line) return null;

  return (
    <div className="border-b border-edge bg-panel px-4 py-3.5">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span className="flex items-center gap-1.5 font-medium text-muted">
          <span className="size-1.5 rounded-full bg-heard" />
          Agent will say
        </span>
        <span className="rounded border border-edge-strong bg-raised px-1.5 py-0.5 font-medium text-muted">
          {line.kind}
        </span>
        {line.critical ? (
          <span className="rounded border border-corrected/45 bg-corrected/10 px-1.5 py-0.5 font-semibold text-corrected">
            critical, read-back required
          </span>
        ) : null}
      </div>

      <p className="text-[16px] leading-snug font-medium text-ink">{line.plain}</p>

      {/* Exactly what goes on the wire, kept recessed so it reads as machine text, not speech. */}
      <p
        className="well mt-2.5 p-2 font-mono text-[11px] leading-relaxed break-words text-muted"
        title="what is sent to Rime"
      >
        {line.text}
        {line.inline_speed_alpha ? (
          <span className="text-heard"> · inlineSpeedAlpha {line.inline_speed_alpha}</span>
        ) : null}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onDeliver()}
          className="btn btn-solid btn-lg"
          style={{ ["--tint" as string]: "var(--color-verified)" }}
        >
          Speak in full
        </button>

        {/* One control, two parts: the button and the millisecond it stops at belong together. */}
        <div className="flex items-center gap-1.5 rounded-md border border-edge-strong bg-raised p-1">
          <button
            type="button"
            disabled={busy}
            onClick={() => onDeliver(cutMs)}
            className="btn btn-tint border-0 shadow-none"
            style={{ ["--tint" as string]: "var(--color-conflicted)" }}
            title="cut the audio mid-sentence, as a barge-in does"
          >
            Barge in at
          </button>
          <input
            type="number"
            min={0}
            step={100}
            value={cutMs}
            onChange={(event) => setCutMs(Number(event.target.value))}
            aria-label="Interrupt the audio at, in milliseconds"
            className="field tabular w-20 py-1.5 text-xs"
          />
          <span className="pr-1 text-xs text-faint">ms</span>
        </div>
      </div>
    </div>
  );
}

function FactRow({
  fact,
  awaiting,
  busy,
  onVerify,
  onResolve,
}: {
  fact: Fact;
  awaiting: boolean;
  busy: boolean;
  onVerify: (field: string) => void;
  onResolve: (field: string, value: string) => void;
}) {
  const conflicted = fact.status === "CONFLICTED";
  const verified = fact.status === "VERIFIED";

  return (
    <div className={`px-4 py-3.5 transition-colors ${conflicted ? "bg-conflicted/[0.05]" : ""}`}>
      <div className="flex items-start gap-3">
        {/* A spine in the fact's own colour: the row is scannable before any text is read. */}
        <span
          className="mt-1 w-[3px] shrink-0 self-stretch rounded-full"
          style={{
            background: verified
              ? "var(--color-verified)"
              : conflicted
                ? "var(--color-conflicted)"
                : "var(--color-edge-strong)",
          }}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[11px] font-medium text-faint">{fieldLabel(fact.field)}</span>
            <span className="tabular ml-auto text-[10px] text-faint">epoch {fact.epoch}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="text-[19px] leading-tight font-semibold tracking-tight text-ink">
              {fact.value}
            </span>
            <StatusChip status={fact.status} />
          </div>

          {fact.history.map((version, index) => (
            <div
              key={`${version.value}-${index}`}
              className="mt-2 border-l border-edge pl-2.5 text-[12px] text-superseded"
            >
              <span className="line-through">{version.value}</span>{" "}
              <span className="tabular">
                · {version.status} at epoch {version.epoch}
              </span>
              {version.delivered ? <HeardRow delivered={version.delivered} /> : null}
            </div>
          ))}

          {fact.delivered ? <HeardRow delivered={fact.delivered} /> : null}

          {conflicted ? (
            <div className="anim-alert mt-2.5 rounded-md border border-conflicted/40 bg-conflicted/[0.08] p-3">
              <p className="mb-2 text-[13px] font-semibold text-conflicted">
                Two values heard — a human has to choose.
              </p>
              <div className="flex flex-wrap gap-2">
                {[fact as FactVersion, ...fact.conflict].map((version, index) => (
                  <button
                    key={`${version.value}-${index}`}
                    type="button"
                    disabled={busy}
                    onClick={() => onResolve(fact.field, version.value)}
                    className="btn btn-tint btn-lg"
                    style={{ ["--tint" as string]: "var(--color-conflicted)" }}
                  >
                    {version.value}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {awaiting ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => onVerify(fact.field)}
              className="btn btn-tint btn-lg mt-2.5"
              style={{ ["--tint" as string]: "var(--color-verified)" }}
              title="the clinician said yes to the read-back"
            >
              Confirm read-back
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function HeardRow({ delivered }: { delivered: Delivered }) {
  const words = delivered.text_heard.trim().split(/\s+/).filter(Boolean);
  const last = words.length - 1;
  const cut = !delivered.complete;

  return (
    <div className="well mt-2 px-2.5 py-2">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[10px] font-medium text-faint">reached the listener</span>
        {delivered.complete ? (
          <span className="text-[10px] font-medium text-verified">in full</span>
        ) : (
          <span className="tabular text-[10px] font-semibold text-conflicted">
            cut at {delivered.cutoff_ms} ms
          </span>
        )}
      </div>
      <p className="anim-sweep text-[13px] leading-relaxed">
        {words.length === 0 ? (
          <span className="text-superseded">nothing was delivered</span>
        ) : (
          words.map((word, index) =>
            index === last && cut ? (
              <span key={`${word}-${index}`}>
                <span className="cut-word">{word}</span>
                <span className="cut-bar" />
              </span>
            ) : (
              <span key={`${word}-${index}`} className="text-ink">
                {word}{" "}
              </span>
            ),
          )
        )}
      </p>
    </div>
  );
}
