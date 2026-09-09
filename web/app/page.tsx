"use client";

import { RelayPanel } from "@/components/RelayPanel";
import { StatusBar } from "@/components/StatusBar";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { TruthStatePanel } from "@/components/TruthStatePanel";
import { API_BASE } from "@/lib/api";
import { useHandover } from "@/lib/useHandover";

/**
 * Three columns and a status bar, in the order a handover actually moves: what was said, what the
 * system believes and heard, what is safe to pass on.
 */
export default function Dashboard() {
  const handover = useHandover();
  const unreachable = handover.connection === "offline" && !handover.snapshot;

  return (
    <main className="flex h-screen flex-col">
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
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)_minmax(0,0.85fr)]">
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
    </main>
  );
}

function SidecarDown() {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md space-y-3 rounded border border-conflicted/50 bg-panel p-5 text-sm">
        <p className="font-semibold text-conflicted">The sidecar is not answering.</p>
        <p className="text-muted">
          The dashboard holds no state of its own, so there is nothing to show until the truth-state
          service is up. Start it with:
        </p>
        <pre className="overflow-x-auto rounded border border-edge bg-board p-2 font-mono text-xs text-ink">
          uvicorn api.main:app --reload
        </pre>
        <p className="text-muted">
          Expected at <span className="text-ink">{API_BASE}</span> — override with{" "}
          <span className="text-ink">NEXT_PUBLIC_HEARBACK_API</span>.
        </p>
      </div>
    </div>
  );
}
