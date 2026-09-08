"""Replay a scripted handover and print it as a transcript.

    python scripts/run_scenario.py fixtures/scenario_morphine.json
    python scripts/run_scenario.py fixtures/scenario_morphine.json --json evidence/scenario.json

No microphone, no API keys, no running server: the sidecar runs in-process. This is the demo
that still works when the venue wi-fi does not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sim.replay import ReplayResult, Scenario, replay

BAR = "-" * 78


def render(result: ReplayResult) -> str:
    lines = [f"Scenario: {result.scenario}", BAR]
    for step in result.steps:
        lines.append(f"[epoch {step.epoch}] paramedic: {step.said}")
        if not step.applied:
            lines.append("            (extraction dropped: stale epoch)")
        if step.verified:
            lines.append(f"            verified: {', '.join(step.verified)}")
        for spoken in step.spoken:
            lines.append(f"            agent ({spoken.kind}): {spoken.text}")
            if spoken.cut_at_ms is not None:
                lines.append(f"              cut at {spoken.cut_at_ms} ms")
                lines.append(f"              heard: {spoken.heard!r} (cutoff word {spoken.cutoff_word!r})")
    lines += [BAR, "RELAY (verified facts only)", result.relay["plain"]]
    withheld = result.relay["withheld"]
    lines.append(f"withheld: {', '.join(withheld) if withheld else 'nothing'}")
    lines.append(f"slots covered: {sum(result.relay['completeness'].values())}/{len(result.relay['completeness'])}")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--lang", default="en", choices=["en", "hi"])
    parser.add_argument("--json", type=Path, help="also write the machine-readable result here")
    args = parser.parse_args()

    result = await replay(Scenario.load(args.scenario), lang=args.lang)
    print(render(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
