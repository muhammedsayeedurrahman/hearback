"""Run the acceptance tests and write the evidence.

    python scripts/run_evidence.py --all
    python scripts/run_evidence.py --tests t3 t4
    python scripts/run_evidence.py --all --live      # adds T1, T6 and the audio half of T5

Offline (the default) T2, T3, T4, T5 and T7 run against a sidecar built in-process: no keys, no
network, deterministic. T1 and T6 measure audio leaving Rime and are reported as NOT RUN until
`--live` is passed with `RIME_API_KEY` set, because a latency number nobody measured is worse
than an empty cell.

Writes `evidence/results.json` and `evidence/RESULTS.md`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from sim import report
from sim.acceptance import (
    FAIL,
    FIXTURES,
    NOT_RUN,
    PASS,
    Result,
    not_run,
    percentiles,
    t2_stale_audio,
    t3_tool_fence,
    t4_ledger,
    t5_readback,
    t7_provider,
)

ALL_TESTS = ("t1", "t2", "t3", "t4", "t5", "t6", "t7")

T1_TEXT = "Confirming. morphine, five milligrams. Say yes to confirm."
T6_TEXT = "Blood pressure, ninety over sixty."

LIVE_HINT = "run with --live and RIME_API_KEY set"


async def run(args: argparse.Namespace) -> list[Result]:
    wanted = [t.lower() for t in (args.tests or ALL_TESTS)]
    config = _rime_config() if args.live else None
    results: list[Result] = []

    if "t1" in wanted:
        results.append(await _t1(config, args))
    if "t2" in wanted:
        results.append(await t2_stale_audio(args.scenario, args.offsets))
    if "t3" in wanted:
        results.append(await t3_tool_fence(args.runs, args.tool_delay_ms, args.correction_at_ms))
    if "t4" in wanted:
        results.append(t4_ledger(args.annotations))
    if "t5" in wanted:
        result = t5_readback(args.pronunciation)
        if config is not None:
            await _t5_audio(config, result, args)
        results.append(result)
    if "t6" in wanted:
        results.append(await _t6(config, args))
    if "t7" in wanted:
        results.append(await t7_provider())
    return results


def _rime_config():
    from agent.config import ConfigError, load_rime_config

    try:
        return load_rime_config()
    except ConfigError as exc:
        raise SystemExit(f"--live needs a working Rime configuration: {exc}") from None


async def _t1(config, args: argparse.Namespace) -> Result:
    """Time-to-silence: from the clear frame to the last audio frame Rime sends."""
    criterion = "P90 <= 300 ms from barge-in to the last audio frame"
    if config is None:
        return not_run("T1", "Time-to-silence", criterion, f"needs live audio from Rime: {LIVE_HINT}")

    from sim.rime_probe import ProbeError, time_to_silence

    try:
        runs = await time_to_silence(config, T1_TEXT, runs=args.runs, speak_ms=args.speak_ms)
    except ProbeError as exc:
        return Result(
            id="T1", name="Time-to-silence", criterion=criterion, status=NOT_RUN,
            how="live probe attempted", note=str(exc),
        )
    values = [r.time_to_silence_ms for r in runs]
    stats = percentiles(values)
    return Result(
        id="T1",
        name="Time-to-silence",
        criterion=criterion,
        status=PASS if stats.get("p90_ms", 1e9) <= 300 else FAIL,
        how="measured at the ws3 socket: clear frame sent -> last audio frame received",
        runs=len(runs),
        measured={**stats, "frames_after_clear_max": max((r.frames_after_clear for r in runs), default=0)},
        failures=[r.__dict__ for r in runs if r.time_to_silence_ms > 300],
        note="Socket-side, so it excludes whatever the client's playout buffer still holds; a "
        "microphone in the room would record this number plus that buffer.",
    )


async def _t6(config, args: argparse.Namespace) -> Result:
    """Time-to-first-audio, cold and warm kept in separate samples."""
    criterion = "report P50/P90/P99; cold and warm labelled separately (no target)"
    if config is None:
        return not_run("T6", "Time-to-first-audio", criterion, f"needs live audio from Rime: {LIVE_HINT}")

    from sim.rime_probe import ProbeError, time_to_first_audio

    try:
        samples = await time_to_first_audio(config, T6_TEXT, runs=args.runs)
    except ProbeError as exc:
        return Result(
            id="T6", name="Time-to-first-audio", criterion=criterion, status=NOT_RUN,
            how="live probe attempted", note=str(exc),
        )
    cold, warm = percentiles(samples["cold_ms"]), percentiles(samples["warm_ms"])
    return Result(
        id="T6",
        name="Time-to-first-audio",
        criterion=criterion,
        status=PASS,
        how="last text frame -> first audio chunk over ws3",
        runs=len(samples["cold_ms"]) + len(samples["warm_ms"]),
        measured={
            "p50_ms": warm.get("p50_ms"),
            **{f"cold_{k}": v for k, v in cold.items()},
            **{f"warm_{k}": v for k, v in warm.items()},
        },
        note="Cold opens a socket per request; warm reuses one. Pooling dominates this number, so "
        "the two samples are never merged.",
    )


async def _t5_audio(config, result: Result, args: argparse.Namespace) -> None:
    """Render both readback variants, and score them if a recogniser is available."""
    from agent.config import NUMBER_SPEED_ALPHA
    from sim.rime_probe import digit_error_rate, render_clip, transcribe

    deepgram = os.getenv("DEEPGRAM_API_KEY", "").strip()
    clips_dir = args.out / "clips"
    rendered: list[dict] = []
    errors: list[str] = []

    for item in result.measured["rendered"][: args.clips]:
        pair = {"id": item["id"], "value": item["value"]}
        for variant in ("A", "B"):
            path = clips_dir / f"{item['id']}_{variant}.wav"
            try:
                await render_clip(
                    config,
                    item[variant],
                    path,
                    inline_speed_alpha=NUMBER_SPEED_ALPHA if variant == "B" else None,
                )
            except Exception as exc:  # noqa: BLE001 - every failure is reported, never swallowed
                errors.append(f"{item['id']}{variant}: {type(exc).__name__}: {exc}")
                continue
            pair[f"clip_{variant}"] = str(path)
            if deepgram:
                heard = await transcribe(deepgram, path.read_bytes())
                pair[f"heard_{variant}"] = heard
                pair[f"der_{variant}"] = digit_error_rate(item["value"], heard)
        rendered.append(pair)

    result.measured["clips"] = rendered
    result.measured["clip_errors"] = errors
    scored = [p for p in rendered if "der_A" in p and "der_B" in p]
    if scored:
        mean_a = round(sum(p["der_A"] for p in scored) / len(scored), 4)
        mean_b = round(sum(p["der_B"] for p in scored) / len(scored), 4)
        result.measured["digit_error_rate_A"] = mean_a
        result.measured["digit_error_rate_B"] = mean_b
        result.measured["der_items"] = len(scored)
        if mean_b > mean_a:
            result.status = FAIL
            result.failures.append(
                {"reason": "variant B did not match or beat variant A on digit error rate",
                 "A": mean_a, "B": mean_b}
            )
        result.how += f"; {len(scored)} items rendered through Rime and re-transcribed"
        result.note = "Digit error rate is Levenshtein over the digit sequence recovered from the " \
                      "re-transcribed clip, normalised by the reference digits."
    elif rendered:
        result.how += f"; {len(rendered)} items rendered through Rime (clips committed, not scored)"
        result.note = "Clips rendered but not scored: set DEEPGRAM_API_KEY to measure digit error rate."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="run every test (the default)")
    parser.add_argument("--tests", nargs="*", choices=ALL_TESTS, help="run only these tests")
    parser.add_argument("--live", action="store_true", help="reach Rime for T1, T6 and T5's clips")
    parser.add_argument("--runs", type=int, default=20, help="runs per measured test")
    parser.add_argument("--tool-delay-ms", type=int, default=3000, help="injected cross-check delay")
    parser.add_argument("--correction-at-ms", type=int, default=1000, help="when the correction lands")
    parser.add_argument("--speak-ms", type=int, default=800, help="how long T1 lets the agent speak")
    parser.add_argument("--clips", type=int, default=8, help="how many T5 items to render live")
    parser.add_argument("--out", type=Path, default=Path("evidence"))
    parser.add_argument("--scenario", type=Path, default=FIXTURES / "scenario_morphine.json")
    parser.add_argument("--offsets", type=Path, default=FIXTURES / "barge_in_offsets.json")
    parser.add_argument("--annotations", type=Path, default=FIXTURES / "ledger_annotations.json")
    parser.add_argument("--pronunciation", type=Path, default=FIXTURES / "pronunciation_30.json")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    results = await run(args)
    json_path, md_path = report.write(results, args.out, live=args.live)

    width = max(len(r.name) for r in results)
    for r in results:
        print(f"  {r.id}  {r.name:<{width}}  {r.status:<8} {_headline(r)}")
    print(f"\nwrote {json_path} and {md_path}")
    return 1 if any(r.status == FAIL for r in results) else 0


def _headline(r: Result) -> str:
    if r.status == NOT_RUN:
        return r.note
    key, label = report._KEY_NUMBERS.get(r.id, ("", ""))
    value = r.measured.get(key)
    return f"{label}: {value}" if value is not None else ""


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
