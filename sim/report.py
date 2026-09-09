"""Render acceptance results as JSON and as a table a judge can read in thirty seconds.

The report never smooths anything over: a NOT RUN test keeps its row, keeps the reason it did not
run, and keeps the command that would run it.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sim.acceptance import FAIL, NOT_RUN, PASS, Result

HEADLINE = (
    "When a clinician corrects the agent while it is speaking or while a tool is running, the "
    "stale answer never reaches the listener: audio for the superseded utterance is cancelled at "
    "Rime, the record of what was heard is cut at the last word actually delivered, obsolete tool "
    "results are dropped by epoch arithmetic, and only values a human explicitly confirmed are "
    "relayed to the receiving clinician."
)

_KEY_NUMBERS = {
    "T1": ("p90_ms", "P90 time-to-silence"),
    "T2": ("clean_runs", "clean runs"),
    "T3": ("clean_runs", "clean runs"),
    "T4": ("within_one_rate", "within +/-1 word"),
    "T5": ("conforming", "conforming items"),
    "T6": ("p50_ms", "P50 time-to-first-audio"),
    "T7": ("provider_events", "provider events"),
}


def commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def write(results: list[Result], out_dir: Path, live: bool) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ"),
        "commit": commit(),
        "mode": "live (Rime reached)" if live else "offline (no keys, no network)",
        "headline_claim": HEADLINE,
    }
    payload = {"meta": meta, "results": [r.to_dict() for r in results]}
    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path = out_dir / "RESULTS.md"
    md_path.write_text(render(meta, results), encoding="utf-8")
    return json_path, md_path


def render(meta: dict[str, Any], results: list[Result]) -> str:
    lines = [
        "# Evidence results",
        "",
        f"Generated {meta['generated_utc']} · commit `{meta['commit']}` · mode: {meta['mode']}",
        "",
        (
            "Regenerate with `python scripts/run_evidence.py --all` (add `--live` with a Rime key "
            "for T1, T6 and the audio half of T5)."
        ),
        "",
        "**Claim under test.** " + meta["headline_claim"],
        "",
        "| Test | Name | Status | Runs | Key number |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        key, label = _KEY_NUMBERS.get(r.id, ("", ""))
        value = r.measured.get(key)
        number = f"{label}: {value}" if value is not None else "—"
        lines.append(f"| {r.id} | {r.name} | {_badge(r.status)} | {r.runs or '—'} | {number} |")

    lines += ["", "---", ""]
    for r in results:
        lines += _section(r)
    return "\n".join(lines) + "\n"


def _badge(status: str) -> str:
    return {PASS: "**PASS**", FAIL: "**FAIL**", NOT_RUN: "NOT RUN"}.get(status, status)


def _section(r: Result) -> list[str]:
    lines = [
        f"## {r.id} — {r.name}",
        "",
        f"- **Criterion:** {r.criterion}",
        f"- **Status:** {_badge(r.status)}",
        f"- **How measured:** {r.how}",
    ]
    if r.runs:
        lines.append(f"- **Runs:** {r.runs}")
    if r.note:
        lines.append(f"- **Scope:** {r.note}")
    numbers = {k: v for k, v in r.measured.items() if _is_scalar(v)}
    if numbers:
        lines += ["", "| Measure | Value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in numbers.items()]
    if r.failures:
        lines += ["", f"**{len(r.failures)} failure(s):**", "", "```json",
                  json.dumps(r.failures[:10], indent=2), "```"]
    lines.append("")
    return lines


def _is_scalar(value: Any) -> bool:
    """Only flat values become table rows; nested detail stays in results.json."""
    return isinstance(value, (int, float, str, bool)) or value is None
