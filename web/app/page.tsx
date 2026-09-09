"use client";

import { PHASE_TINT, StatusBar, phaseOf } from "@/components/StatusBar";
import { RelayPanel } from "@/components/RelayPanel";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { TruthStatePanel } from "@/components/TruthStatePanel";
import { API_BASE } from "@/lib/api";
import { useHandover } from "@/lib/useHandover";

/**
 * The whole live record is one sheet on the desk: three columns in the order a handover actually
 * moves — what was said, what the system believes and heard, what is safe to pass on.
 *
 * The centre column is the widest because it is the product. The phase runs along the top edge of
 * the sheet as a single coloured rule, and the paper behind it takes the same colour, so the state
 * of the handover is legible from across a room before a word has been read.
 *
 * On a phone the columns stack and the page scrolls; forcing three panels into one screen height
 * would make each of them useless.
 */
export default function Dashboard() {
  const handover = useHandover();
  const unreachable = handover.connection === "offline" && !handover.snapshot;
  const phase = phaseOf(handover.snapshot);

  return (
    <main className="board flex min-h-screen flex-col p-2 sm:p-3 lg:h-screen" data-phase={phase}>
      <div className="sheet flex flex-1 flex-col overflow-hidden lg:min-h-0">
        <div className="h-[3px] shrink-0" style={{ background: PHASE_TINT[phase] }} />

        <StatusBar
          snapshot={handover.snapshot}
          events={handover.events}
          connection={handover.connection}
          sessionId={handover.sessionId}
          error={handover.error}
        />

        {unreachable ? (
          <SidecarDown />
        ) : (
          <div className="grid flex-1 grid-cols-1 divide-y divide-edge lg:min-h-0 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)_minmax(0,0.9fr)] lg:divide-y-0">
            <TranscriptPanel events={handover.events} onSay={handover.say} busy={handover.busy} />
            <TruthStatePanel
              snapshot={handover.snapshot}
              busy={handover.busy}
              onDeliver={handover.deliver}
              onVerify={handover.verify}
              onResolve={handover.resolve}
            />
            <RelayPanel
              snapshot={handover.snapshot}
              relay={handover.relay}
              busy={handover.busy}
              onRelay={handover.buildRelay}
              onProvider={handover.setProvider}
              onToolDelay={handover.setToolDelay}
            />
          </div>
        )}
      </div>
    </main>
  );
}

function SidecarDown() {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="raised max-w-md space-y-3 p-6 text-sm">
        <div className="flex items-center gap-2">
          <span className="anim-blink size-2 rounded-full bg-conflicted" />
          <p className="font-semibold text-conflicted">The sidecar is not answering.</p>
        </div>
        <p className="leading-relaxed text-muted">
          The dashboard holds no state of its own, so there is nothing to show until the truth-state
          service is up. Start it with:
        </p>
        <pre className="well scroll overflow-x-auto p-3 font-mono text-xs text-ink">
          uvicorn api.main:app --reload
        </pre>
        <p className="leading-relaxed text-muted">
          Expected at <span className="font-mono text-ink">{API_BASE}</span> — override with{" "}
          <span className="font-mono text-ink">NEXT_PUBLIC_HEARBACK_API</span>.
        </p>
      </div>
    </div>
  );
}
