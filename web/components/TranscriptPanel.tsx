"use client";

import { useEffect, useRef, useState } from "react";

import type { HearbackEvent } from "@/lib/api";
import { speakerLabel } from "@/lib/labels";

/**
 * The conversation as the system recorded it — including the parts that never reached the
 * listener. An interrupted line is shown cut, with the word the listener was on, because that is
 * the version the agent has to reconcile against.
 *
 * Who is speaking is carried by a coloured spine rather than by a bubble on one side: this is a
 * record of a handover, not a chat, and the paramedic and the agent are peers in it.
 *
 * The composer is the documented text fallback: when streaming speech is unstable, a turn can be
 * posted as text and the truth state continues unchanged. The scripted turns above it are numbered
 * because they are genuinely a sequence — the handover only makes sense played in order, with the
 * correction landing after the dose has been read back.
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
    <section className="flex min-h-[24rem] flex-col border-edge lg:min-h-0 lg:border-r">
      <PanelHeading hint={lines.length > 0 ? `${lines.length} turns` : undefined}>
        Live conversation
      </PanelHeading>

      <div className="scroll min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {lines.length === 0 ? <EmptyTranscript /> : null}
        {lines.map((line, index) => (
          <TranscriptLine key={line.seq} line={line} latest={index === lines.length - 1} />
        ))}
        <div ref={foot} />
      </div>

      <div className="border-t border-edge bg-panel p-3">
        <div className="scroll -mx-1 mb-2 flex gap-2 overflow-x-auto px-1 pb-1.5">
          {PROMPTS.map((prompt, index) => (
            <button
              key={prompt}
              type="button"
              disabled={busy}
              onClick={() => send(prompt)}
              title={prompt}
              aria-label={`Say turn ${index + 1}: ${prompt}`}
              className="btn shrink-0 gap-2 px-2.5 text-[11px]"
            >
              <span className="tabular font-semibold text-faint">{index + 1}</span>
              <span className="max-w-[22ch] truncate">{prompt}</span>
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
            aria-label="What the paramedic said"
            className="field min-w-0 flex-1 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="btn btn-solid btn-lg"
            style={{ ["--tint" as string]: "var(--color-heard)" }}
          >
            Say
          </button>
        </form>
      </div>
    </section>
  );
}

function EmptyTranscript() {
  return (
    <div className="raised p-4">
      <p className="text-sm font-medium text-ink">Nothing said yet.</p>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
        Play the scripted handover from the buttons below, in order — the morphine dose is corrected
        partway through, which is the moment the ledger has to survive. Or type a turn yourself.
      </p>
    </div>
  );
}

function TranscriptLine({ line, latest }: { line: Line; latest: boolean }) {
  /* System notes sit on a rail rather than in a card: they are the machine narrating itself. */
  if (line.kind === "note") {
    return (
      <p className="flex gap-2 border-l-2 border-edge-strong py-1 pl-3 text-[11px] leading-relaxed text-muted">
        <span className="tabular shrink-0 font-medium text-superseded">e{line.epoch}</span>
        <span>{line.text}</span>
      </p>
    );
  }

  const said = line.kind === "said";
  const words = line.text.split(/\s+/).filter(Boolean);
  const head = line.cut ? words.slice(0, -1) : words;
  const tail = line.cut ? words[words.length - 1] : null;

  return (
    <div
      className={`border-l-[3px] py-2 pr-3 pl-3 transition-colors ${
        latest ? "bg-raised" : ""
      } ${line.cut ? "border-l-conflicted" : said ? "border-l-edge-strong" : "border-l-heard"}`}
    >
      <div className="mb-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px]">
        <span className={`font-semibold ${said ? "text-ink" : "text-heard"}`}>
          {speakerLabel(line.who)}
        </span>
        <span className="tabular text-faint">epoch {line.epoch}</span>
        {line.cut ? (
          <span
            className="tabular ml-auto rounded border border-conflicted/40 bg-conflicted/10 px-1.5 py-0.5 font-semibold text-conflicted"
            title="the audio stopped here"
          >
            cut at {line.cut.ms} ms
          </span>
        ) : null}
      </div>

      {/* Delivered words paint in the order the listener received them; the cut is where they stop. */}
      <p className={`text-[15px] leading-relaxed max-sm:text-base ${said ? "" : "anim-sweep"}`}>
        {head.join(" ")}
        {tail ? (
          <>
            {" "}
            <span className="cut-word">{tail}</span>
            <span className="cut-bar" />
          </>
        ) : null}
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

export function PanelHeading({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <h2 className="flex items-baseline gap-2 border-b border-edge bg-panel px-4 py-2.5 text-[13px] font-semibold text-ink">
      {children}
      {hint ? <span className="tabular ml-auto text-[11px] font-normal text-faint">{hint}</span> : null}
    </h2>
  );
}
