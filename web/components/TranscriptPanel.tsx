"use client";

import { useEffect, useRef, useState } from "react";

import type { HearbackEvent } from "@/lib/api";

/**
 * The conversation as the system recorded it — including the parts that never reached the
 * listener. An interrupted line is shown cut, with the word the listener was on, because that is
 * the version the agent will reconcile against.
 *
 * The composer is the documented text fallback: when streaming speech is unstable, a turn can be
 * posted as text and the truth state continues unchanged.
 */

const PROMPTS = [
  "This is a 34 year old male, fall from height at 14:05, GCS 13.",
  "BP is ninety over sixty, sats 91 percent.",
  "He's allergic to penicillin.",
  "We gave morphine ten milligrams.",
  "Wait, that was morphine five milligrams.",
  "Yes, five milligrams is correct.",
];

interface Line {
  seq: number;
  kind: "said" | "spoken" | "note";
  who: string;
  text: string;
  epoch: number;
  cut?: { word: string; ms: number };
}

export function TranscriptPanel({
  events,
  onSay,
  busy,
}: {
  events: HearbackEvent[];
  onSay: (text: string) => void;
  busy: boolean;
}) {
  const [draft, setDraft] = useState("");
  const foot = useRef<HTMLDivElement>(null);
  const lines = toLines(events);

  useEffect(() => {
    foot.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines.length]);

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSay(trimmed);
    setDraft("");
  };

  return (
    <section className="flex min-h-0 flex-col border-r border-edge">
      <PanelHeading>Live conversation</PanelHeading>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {lines.length === 0 ? (
          <p className="text-xs text-muted">
            Nothing said yet. Post a turn below, or run the agent to feed this from speech.
          </p>
        ) : null}
        {lines.map((line, index) => (
          <TranscriptLine key={line.seq} line={line} latest={index === lines.length - 1} />
        ))}
        <div ref={foot} />
      </div>

      <div className="border-t border-edge p-3">
        <div className="mb-2 flex flex-wrap gap-1">
          {PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              disabled={busy}
              onClick={() => send(prompt)}
              title={prompt}
              className="max-w-full truncate rounded border border-edge px-2 py-1 text-[11px] text-muted hover:border-heard/60 hover:text-ink disabled:opacity-40"
            >
              {prompt}
            </button>
          ))}
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            send(draft);
          }}
          className="flex gap-2"
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Type what the paramedic said…"
            className="min-w-0 flex-1 rounded border border-edge bg-board px-2 py-1.5 text-sm outline-none placeholder:text-muted focus:border-heard/60"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="rounded border border-heard/50 px-3 py-1.5 text-sm text-heard hover:bg-heard/10 disabled:opacity-40"
          >
            Say
          </button>
        </form>
      </div>
    </section>
  );
}

function TranscriptLine({ line, latest }: { line: Line; latest: boolean }) {
  if (line.kind === "note") {
    return (
      <p className="tabular text-[11px] text-muted">
        <span className="text-superseded">e{line.epoch}</span> {line.text}
      </p>
    );
  }
  const said = line.kind === "said";
  return (
    <div
      className={`rounded border px-2.5 py-2 text-sm ${
        latest ? "border-heard/50 bg-heard/5" : "border-edge bg-panel"
      }`}
    >
      <div className="mb-0.5 flex items-center gap-2 text-[11px] text-muted">
        <span className={said ? "text-ink" : "text-heard"}>{line.who}</span>
        <span className="tabular">epoch {line.epoch}</span>
        {line.cut ? (
          <span className="tabular text-conflicted" title="the audio stopped here">
            ▌cut at {line.cut.ms} ms on “{line.cut.word}”
          </span>
        ) : null}
      </div>
      <p className={line.cut ? "text-ink" : ""}>
        {line.text}
        {line.cut ? <span className="text-conflicted"> —</span> : null}
      </p>
    </div>
  );
}

function toLines(events: HearbackEvent[]): Line[] {
  const lines: Line[] = [];
  for (const event of events) {
    if (event.type === "utterance") {
      lines.push({
        seq: event.seq,
        kind: "said",
        who: String(event.data.speaker ?? "sender"),
        text: String(event.data.text ?? ""),
        epoch: event.epoch,
      });
    } else if (event.type === "ledger_cut") {
      const heard = String(event.data.text_heard ?? "");
      const complete = Boolean(event.data.complete);
      lines.push({
        seq: event.seq,
        kind: "spoken",
        who: "agent",
        text: heard || "(nothing was delivered)",
        epoch: event.epoch,
        cut: complete
          ? undefined
          : { word: String(event.data.cutoff_word ?? "—"), ms: Number(event.data.cutoff_ms ?? 0) },
      });
    } else if (event.type === "stale_llm") {
      lines.push({
        seq: event.seq,
        kind: "note",
        who: "system",
        text: `fenced: dropped ${event.data.dropped} extracted value(s) stamped epoch ${event.data.epoch} — the clinician had already moved on`,
        epoch: event.epoch,
      });
    } else if (event.type === "confirmation_challenged") {
      lines.push({
        seq: event.seq,
        kind: "note",
        who: "system",
        text: `confirmation refused for ${event.data.field}: ${event.data.reason}`,
        epoch: event.epoch,
      });
    } else if (event.type === "provider_changed") {
      lines.push({
        seq: event.seq,
        kind: "note",
        who: "system",
        text: `voice provider → ${event.data.provider}${event.data.reason ? ` (${event.data.reason})` : ""}`,
        epoch: event.epoch,
      });
    } else if (event.type === "relay_requested") {
      lines.push({
        seq: event.seq,
        kind: "note",
        who: "system",
        text: `relay spoken in ${event.data.lang}: ${(event.data.fields as string[])?.length ?? 0} verified fact(s)`,
        epoch: event.epoch,
      });
    }
  }
  return lines;
}

export function PanelHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="border-b border-edge px-4 py-2 text-[11px] font-semibold tracking-widest text-muted uppercase">
      {children}
    </h2>
  );
}
