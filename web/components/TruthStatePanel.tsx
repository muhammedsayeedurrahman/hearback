"use client";

import { useState } from "react";

import type { Delivered, Fact, FactVersion, Snapshot } from "@/lib/api";
import { StatusChip } from "./StatusChip";
import { PanelHeading } from "./TranscriptPanel";

/**
 * The centre column: one row per clinical fact, its live value, everything it used to be, and the
 * words that were actually delivered about it.
 *
 * The heard sub-row is the part that does not exist in an ordinary transcript view. It is not what
 * the agent said; it is what the listener got before the audio stopped, which is what the next
 * sentence has to reconcile against.
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

  return (
    <section className="flex min-h-0 flex-col border-r border-edge">
      <PanelHeading>Truth state</PanelHeading>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <NextLineCard snapshot={snapshot} busy={busy} onDeliver={onDeliver} />
        <div className="divide-y divide-edge">
          {facts.length === 0 ? (
            <p className="px-4 py-3 text-xs text-muted">
              No facts yet. Every value starts as HEARD and only a human confirmation moves it to
              VERIFIED.
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
    <div className="border-b border-edge bg-panel px-4 py-3">
      <div className="mb-1 flex items-center gap-2 text-[11px] tracking-wider text-muted uppercase">
        <span>agent will say</span>
        <span className="rounded border border-edge px-1.5 py-0.5">{line.kind}</span>
        {line.critical ? (
          <span className="rounded border border-corrected/50 px-1.5 py-0.5 text-corrected">
            critical · read-back required
          </span>
        ) : null}
      </div>

      <p className="text-sm text-ink">{line.plain}</p>
      <p className="mt-1 font-mono text-[11px] break-words text-muted" title="what is sent to Rime">
        {line.text}
        {line.inline_speed_alpha ? (
          <span className="text-heard"> · inlineSpeedAlpha {line.inline_speed_alpha}</span>
        ) : null}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <button
          type="button"
          disabled={busy}
          onClick={() => onDeliver()}
          className="rounded border border-verified/50 px-2 py-1 text-verified hover:bg-verified/10 disabled:opacity-40"
        >
          Speak in full
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDeliver(cutMs)}
          className="rounded border border-conflicted/60 px-2 py-1 text-conflicted hover:bg-conflicted/10 disabled:opacity-40"
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
          className="tabular w-20 rounded border border-edge bg-board px-1.5 py-1 outline-none focus:border-heard/60"
        />
        <span className="text-muted">ms</span>
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
  return (
    <div className={`px-4 py-3 ${conflicted ? "bg-conflicted/5" : ""}`}>
      <div className="flex items-baseline gap-2">
        <span className="text-xs text-muted">{fact.field.replace(/_/g, " ")}</span>
        <span className="text-base text-ink">{fact.value}</span>
        <StatusChip status={fact.status} />
        <span className="tabular ml-auto text-[11px] text-muted">epoch {fact.epoch}</span>
      </div>

      {fact.history.map((version, index) => (
        <p key={`${version.value}-${index}`} className="mt-1 text-xs text-superseded">
          <span className="line-through">{version.value}</span>{" "}
          <span className="tabular">· {version.status} at epoch {version.epoch}</span>
          {version.delivered ? <HeardRow delivered={version.delivered} /> : null}
        </p>
      ))}

      {fact.delivered ? <HeardRow delivered={fact.delivered} /> : null}

      {conflicted ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-conflicted">two values heard — a human has to choose:</span>
          {[fact as FactVersion, ...fact.conflict].map((version, index) => (
            <button
              key={`${version.value}-${index}`}
              type="button"
              disabled={busy}
              onClick={() => onResolve(fact.field, version.value)}
              className="rounded border border-conflicted/60 px-2 py-1 text-conflicted hover:bg-conflicted/10 disabled:opacity-40"
            >
              {version.value}
            </button>
          ))}
        </div>
      ) : null}

      {awaiting ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onVerify(fact.field)}
          className="mt-2 rounded border border-verified/50 px-2 py-1 text-xs text-verified hover:bg-verified/10 disabled:opacity-40"
          title="the clinician said yes to the read-back"
        >
          Confirm read-back
        </button>
      ) : null}
    </div>
  );
}

function HeardRow({ delivered }: { delivered: Delivered }) {
  const words = delivered.text_heard.trim().split(/\s+/).filter(Boolean);
  const last = words.length - 1;
  return (
    <span className="mt-1 block text-xs">
      <span className="text-muted">heard: </span>
      {words.length === 0 ? (
        <span className="text-superseded">nothing was delivered</span>
      ) : (
        words.map((word, index) => (
          <span
            key={`${word}-${index}`}
            className={
              index === last && !delivered.complete
                ? "rounded bg-conflicted/20 px-1 text-conflicted"
                : "text-ink/80"
            }
          >
            {word}{" "}
          </span>
        ))
      )}
      {delivered.complete ? (
        <span className="text-verified">· delivered in full</span>
      ) : (
        <span className="tabular text-conflicted">· cut at {delivered.cutoff_ms} ms</span>
      )}
    </span>
  );
}
