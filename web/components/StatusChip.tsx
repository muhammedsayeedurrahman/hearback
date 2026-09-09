import type { FactStatus } from "@/lib/api";

/**
 * The six truth states, as the clinician sees them. VERIFIED is the only one that crosses the
 * relay gate, so it is the only one rendered as settled — a filled dot. Everything else keeps a
 * hollow dot, which reads as outstanding at a glance and survives being printed, screenshotted or
 * looked at by someone who cannot separate the colours.
 */
const TINT: Record<FactStatus, string> = {
  HEARD: "var(--color-heard)",
  INFERRED: "var(--color-inferred)",
  CORRECTED: "var(--color-corrected)",
  CONFLICTED: "var(--color-conflicted)",
  VERIFIED: "var(--color-verified)",
  SUPERSEDED: "var(--color-superseded)",
};

export function StatusChip({ status }: { status: FactStatus }) {
  const tint = TINT[status];
  const settled = status === "VERIFIED";
  const urgent = status === "CONFLICTED";

  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider"
      style={{
        color: tint,
        borderColor: `color-mix(in oklab, ${tint} ${urgent ? 55 : 32}%, var(--color-edge))`,
        background: `color-mix(in oklab, ${tint} ${urgent ? 12 : 7}%, var(--color-raised))`,
      }}
    >
      <span
        className={`size-1.5 rounded-full ${urgent ? "anim-blink" : ""}`}
        style={
          settled || urgent
            ? { background: "currentColor" }
            : { border: "1.5px solid currentColor" }
        }
      />
      {status}
    </span>
  );
}
