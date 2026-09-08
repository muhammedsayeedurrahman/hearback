"""Sweep barge-in offsets against the critical read-back.

    python scripts/stress_barge_in.py
    python scripts/stress_barge_in.py --json evidence/barge_in.json

For each offset the agent is cut off mid-sentence and must report the exact word the listener
was on, then quote that word back in the reconciliation. The acceptance condition is not that a
particular word is chosen, but that the word quoted back is always the word actually delivered:
the reconciliation may never claim the listener heard something they did not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sim.barge_in import probe
from sim.replay import Scenario

OFFSETS = Path("fixtures/barge_in_offsets.json")
SCENARIO = Path("fixtures/scenario_morphine.json")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=SCENARIO)
    parser.add_argument("--offsets", type=Path, default=OFFSETS)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    scenario = Scenario.load(args.scenario)
    offsets = json.loads(args.offsets.read_text(encoding="utf-8"))["offsets_ms"]
    probes = [await probe(scenario, offset) for offset in offsets]

    print(f"{'offset':>8}  {'cutoff word':<16} {'quoted back':<12} heard")
    for p in probes:
        print(f"{p.offset_ms:>8}  {str(p.cutoff_word):<16} {str(p.quoted_back):<12} {p.heard!r}")
    failures = [p for p in probes if not p.quoted_back]
    print()
    print(f"{len(probes) - len(failures)}/{len(probes)} offsets reconciled against the delivered words")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"probes": [p.to_dict() for p in probes], "failures": len(failures)}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
