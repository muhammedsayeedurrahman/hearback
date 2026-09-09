import type { FactStatus } from "@/lib/api";

/**
 * The six truth states, as the clinician sees them. VERIFIED is the only one that crosses the
 * relay gate, so it is the only one rendered as settled; everything else reads as outstanding.
 */
const STYLES: Record<FactStatus, string> = {
  HEARD: "border-heard/40 text-heard bg-heard/10",
  INFERRED: "border-inferred/40 text-inferred bg-inferred/10",
  CORRECTED: "border-corrected/50 text-corrected bg-corrected/10",
  CONFLICTED: "border-conflicted/60 text-conflicted bg-conflicted/15",
  VERIFIED: "border-verified/50 text-verified bg-verified/10",
  SUPERSEDED: "border-superseded/40 text-superseded bg-superseded/10",
};

export function StatusChip({ status }: { status: FactStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
