"""Acceptance tests T1-T7.

One rule governs this file: a test either measures something or reports NOT RUN. Nothing here
infers a number it did not observe, and every result records how it was obtained, so a reader can
tell a measurement taken through Rime from one taken against the simulated playout clock.

T2, T3, T4, T5 and T7 run offline and deterministically: the sidecar runs in-process, the agent's
speech is simulated, and no key is needed. T1 and T6 measure audio and therefore need Rime; they
report NOT RUN with the command that would run them until `--live` is passed with a key.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from agent.client import HearbackClient
from agent.tools import accept_result, allergy_check
from api.extraction import RuleExtractor
from api.main import create_app
from engine.ledger import cut, words_from_rime
from engine.models import Fact, FactStatus, FactVersion
from engine.readback import Readback, acknowledgement, confirm_prompt
from engine.slots import is_critical, is_identifier, lasa_partner
from sim.barge_in import with_offset
from sim.replay import Scenario, offline_settings, replay

FIXTURES = Path("fixtures")
PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT RUN"


@dataclass
class Result:
    """One acceptance test. `how` is the honest description of what was actually observed."""

    id: str
    name: str
    criterion: str
    status: str
    how: str
    runs: int = 0
    measured: dict[str, Any] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "criterion": self.criterion,
            "status": self.status,
            "how": self.how,
            "runs": self.runs,
            "measured": self.measured,
            "failures": self.failures,
            "note": self.note,
        }


def not_run(id_: str, name: str, criterion: str, note: str) -> Result:
    return Result(id=id_, name=name, criterion=criterion, status=NOT_RUN, how="not attempted", note=note)


def percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min_ms": round(ordered[0], 1),
        "p50_ms": round(statistics.median(ordered), 1),
        "p90_ms": round(_quantile(ordered, 0.90), 1),
        "p99_ms": round(_quantile(ordered, 0.99), 1),
        "max_ms": round(ordered[-1], 1),
    }


def _quantile(ordered: list[float], q: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    index = min(round(q * (len(ordered) - 1)), len(ordered) - 1)
    return ordered[index]


# --------------------------------------------------------------------------------------
# in-process sidecar
# --------------------------------------------------------------------------------------


async def _with_client(work: Callable[[HearbackClient], Awaitable[Any]]) -> Any:
    """Run one session against a sidecar built in-process: no server, no keys, no network."""
    app = create_app(extractor=RuleExtractor(), settings=offline_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://evidence") as http:
        client = HearbackClient(client=http)
        await client.create_session()
        return await work(client)


# --------------------------------------------------------------------------------------
# T2 — stale audio leak
# --------------------------------------------------------------------------------------


async def t2_stale_audio(scenario_path: Path, offsets_path: Path) -> Result:
    """After a barge-in, nothing the listener did not hear may be recorded or quoted back.

    Offline this is measured on the delivery record and the reconciliation sentence rather than
    on an audio stream: the words the agent believes were delivered must be a strict prefix of
    the sentence, and the reconciliation may quote only those words. The audio-path variant of
    the same claim is T1 plus re-transcription, and needs Rime.
    """
    scenario = Scenario.load(scenario_path)
    offsets = json.loads(offsets_path.read_text(encoding="utf-8"))["offsets_ms"]
    leaks: list[dict[str, Any]] = []
    checked = 0

    for offset in offsets:
        result = await replay(with_offset(scenario, offset))
        cut_speech = next((s for step in result.steps for s in step.spoken if s.cut_at_ms is not None), None)
        if cut_speech is None:
            leaks.append({"offset_ms": offset, "reason": "no speech was interrupted"})
            continue
        checked += 1
        spoken_words = cut_speech.plain.split()
        heard_words = cut_speech.heard.split()
        if heard_words != spoken_words[: len(heard_words)]:
            leaks.append(
                {"offset_ms": offset, "reason": "delivered record is not a prefix of the sentence",
                 "heard": cut_speech.heard, "sentence": cut_speech.plain}
            )
        if cut_speech.complete and len(heard_words) != len(spoken_words):
            leaks.append({"offset_ms": offset, "reason": "cut sentence reported as complete"})

        reconcile = next((s for step in result.steps for s in step.spoken if s.kind == "reconcile"), None)
        if reconcile is not None:
            # Only the quoted segment is a claim about what the listener heard. The clause after
            # it states the value the paramedic just gave, and may contain any word at all.
            # Compared on words, not punctuation: the phrasing closes the quote with a full stop
            # where the delivered word ended in a comma, which is presentation, not a claim.
            heard_core = {_core(w) for w in heard_words}
            quoted = _quoted_segment(reconcile.plain).split()
            unheard = [w for w in quoted if _core(w) not in heard_core]
            if unheard:
                leaks.append(
                    {"offset_ms": offset, "reason": "reconciliation quoted words that were never delivered",
                     "words": unheard, "heard": cut_speech.heard, "line": reconcile.plain}
                )

    return Result(
        id="T2",
        name="Stale audio leak",
        criterion="0 words after the cut are recorded as delivered or quoted back",
        status=PASS if not leaks else FAIL,
        how="simulated playout; delivery records and reconciliation text inspected per offset",
        runs=checked,
        measured={"offsets": offsets, "leaked_words": len(leaks), "clean_runs": checked - len(leaks)},
        failures=leaks,
        note="Each offset is run once: the replay is deterministic, so repeating an identical run "
        "adds no information. Audio-path evidence (re-transcribing what left the speaker) needs "
        "--live; this is the state-path half of the same claim.",
    )


def _core(word: str) -> str:
    return word.strip(".,;:!?").lower()


def _quoted_segment(reconciliation: str) -> str:
    """The part of a reconciliation that claims to repeat what the listener heard.

    'I had said, <quote>. You're now saying <new value>...' — only <quote> is a claim about
    delivered audio, so only <quote> is held to the ledger.
    """
    opening = "I had said,"
    if opening not in reconciliation:
        return ""
    tail = reconciliation.split(opening, 1)[1]
    end = tail.find("You're now saying")
    return tail[:end] if end != -1 else tail


# --------------------------------------------------------------------------------------
# T3 — stale tool fencing
# --------------------------------------------------------------------------------------


async def t3_tool_fence(runs: int, tool_delay_ms: int, correct_after_ms: int) -> Result:
    """A cross-check answering a superseded question must never reach speech.

    Each run starts the allergy cross-check under one epoch, corrects the drug while the tool is
    still running, and checks three things: the fence rejects the in-flight answer, the re-run
    under the new epoch is accepted, and an extraction stamped with the old epoch is dropped by
    the sidecar rather than folded into the truth state.
    """
    failures: list[dict[str, Any]] = []

    async def one_run(index: int, client: HearbackClient) -> None:
        first = await client.utterance("We gave morphine ten milligrams.")
        task = asyncio.create_task(allergy_check(client, "morphine", epoch=first, delay_ms=tool_delay_ms))
        await asyncio.sleep(correct_after_ms / 1000)
        second = await client.utterance("Wait, that was hydromorphone.")
        stale = await task

        if accept_result(stale, second):
            failures.append({"run": index, "reason": "stale tool result was accepted", "epoch": stale.epoch})
        fresh = await allergy_check(client, "hydromorphone", epoch=second, delay_ms=0)
        if not accept_result(fresh, second):
            failures.append({"run": index, "reason": "re-run under the current epoch was rejected"})
        outcome = await client.extract("We gave morphine ten milligrams.", epoch=first)
        if outcome.applied:
            failures.append({"run": index, "reason": "stale extraction was applied", "epoch": first})

    async def work(client: HearbackClient) -> None:
        for index in range(runs):
            await one_run(index, client)

    started = time.perf_counter()
    await _with_client(work)
    elapsed = time.perf_counter() - started

    return Result(
        id="T3",
        name="Stale tool fencing",
        criterion="old-epoch tool result never accepted; re-run under the new epoch applied",
        status=PASS if not failures else FAIL,
        how=f"in-process sidecar; tool delayed {tool_delay_ms} ms, correction at {correct_after_ms} ms",
        runs=runs,
        measured={
            "clean_runs": runs - len({f["run"] for f in failures}),
            "tool_delay_ms": tool_delay_ms,
            "correction_at_ms": correct_after_ms,
            "wall_clock_s": round(elapsed, 1),
        },
        failures=failures,
    )


# --------------------------------------------------------------------------------------
# T4 — heard-ledger accuracy
# --------------------------------------------------------------------------------------


def t4_ledger(annotations_path: Path) -> Result:
    """The ledger's cutoff word against a human annotation, within +/-1 word.

    The timings are Rime-shaped word timestamps; the annotations were written by hand from those
    timings, including onsets that fall exactly on the interruption instant.
    """
    data = json.loads(annotations_path.read_text(encoding="utf-8"))
    exact = 0
    within_one = 0
    total = 0
    misses: list[dict[str, Any]] = []

    for sentence in data["sentences"]:
        words = words_from_rime(sentence["words"], sentence["start"], sentence["end"])
        index_of = {w.word: i for i, w in enumerate(words)}
        for case in sentence["cuts"]:
            total += 1
            delivered = cut(words, case["offset_ms"])
            got, want = delivered.cutoff_word, case["expected_word"]
            if got == want:
                exact += 1
                within_one += 1
                continue
            distance = _word_distance(index_of, got, want)
            if distance is not None and distance <= 1:
                within_one += 1
            misses.append(
                {"sentence": sentence["id"], "offset_ms": case["offset_ms"], "expected": want,
                 "got": got, "words_off": distance}
            )

    rate = within_one / total if total else 0.0
    return Result(
        id="T4",
        name="Heard-ledger accuracy",
        criterion=">= 90% of cutoffs within +/-1 word of the annotation",
        status=PASS if rate >= 0.90 else FAIL,
        how="Rime-shaped word timestamps from fixtures; annotations written by hand",
        runs=total,
        measured={
            "annotated_cuts": total,
            "exact": exact,
            "within_one_word": within_one,
            "within_one_rate": round(rate, 3),
        },
        failures=misses,
        note="Timings are fixtures, not a live synthesis: this measures the ledger arithmetic, not "
        "Rime's timestamp accuracy. --live records real timings via scripts/rime_preflight.py --probe.",
    )


def _word_distance(index_of: dict[str, int], got: str | None, want: str | None) -> int | None:
    if got is None or want is None:
        return None
    if got not in index_of or want not in index_of:
        return None
    return abs(index_of[got] - index_of[want])


# --------------------------------------------------------------------------------------
# T5 — readback delivery controls
# --------------------------------------------------------------------------------------

_KIND_RULES = {
    "lasa_dose": "spells the drug and brackets the number",
    "dose": "brackets the number and repeats it with spell()",
    "pair": "says 'over' and brackets both halves",
    "number": "brackets the number and repeats it with spell()",
    "noted": "is noted rather than read back, so it stays plain",
    "code": "spells the whole code",
    "name": "adds no markup",
    "time": "adds no markup",
}


def t5_readback(fixture_path: Path) -> Result:
    """Variant B must carry exactly the controls the value calls for, and A must stay plain.

    The two variants are the sentences the engine would actually speak — a read-back for a
    critical value, an acknowledgement otherwise — not the value in isolation, because the drug
    name is spelled by the sentence and the number is slowed by the value. Rendering anything
    else would test a string no listener ever hears.

    This is the markup half of T5. The intelligibility half — rendering both variants through
    Rime and re-transcribing them — is measured by `--live`, which writes the clips and the digit
    error rate into this same result.
    """
    items = json.loads(fixture_path.read_text(encoding="utf-8"))["items"]
    failures: list[dict[str, Any]] = []
    rendered: list[dict[str, Any]] = []

    for item in items:
        field_name, value, kind = item["field"], item["value"], item["kind"]
        line = _readback_line(field_name, value)
        variant_a, variant_b = line.plain, line.text
        rendered.append({"id": item["id"], "field": field_name, "value": value, "kind": kind,
                         "A": variant_a, "B": variant_b})
        for reason in _readback_problems(item, variant_a, variant_b):
            failures.append({"id": item["id"], "value": value, "kind": kind, "reason": reason,
                             "A": variant_a, "B": variant_b})

    return Result(
        id="T5",
        name="Readback delivery controls",
        criterion="every item carries the controls its kind requires; variant A stays plain",
        status=PASS if not failures else FAIL,
        how="markup conformance over the 30-item pronunciation fixture",
        runs=len(items),
        measured={"items": len(items), "conforming": len(items) - len({f["id"] for f in failures}),
                  "rules": _KIND_RULES, "rendered": rendered},
        failures=failures,
        note="Intelligibility (digit error rate on re-transcribed audio) needs Rime and an STT: run "
        "with --live and DEEPGRAM_API_KEY set.",
    )


def _readback_line(field_name: str, value: str) -> Readback:
    """The sentence the engine would speak for this value, in both variants."""
    fact = Fact(field=field_name, current=FactVersion(value=value, status=FactStatus.HEARD, epoch=1))
    return confirm_prompt(fact) if is_critical(field_name) else acknowledgement(fact)


def _spelled_number(number: str) -> str:
    """Rime says a decimal point rather than spelling it: '0.5' is read as '0 point 5'."""
    return f"spell({number.replace('.', ' point ')})"


def _readback_problems(item: dict[str, Any], variant_a: str, variant_b: str) -> list[str]:
    kind, value, field_name = item["kind"], item["value"], item["field"]
    problems: list[str] = []
    if "spell(" in variant_a or "[" in variant_a:
        problems.append("variant A carries markup; it must be plain words")

    if kind in {"dose", "lasa_dose", "number"}:
        number = value.split()[0].rstrip("%")
        if f"[{number}]" not in variant_b:
            problems.append(f"number {number} is not bracketed for inlineSpeedAlpha")
        if _spelled_number(number) not in variant_b:
            problems.append(f"number {number} is not repeated digit by digit with spell()")
    if kind == "lasa_dose":
        drug = field_name.removesuffix("_dose").replace("_", " ")
        if f"spell({drug})" not in variant_b:
            problems.append(f"look-alike drug {drug} (confusable with {lasa_partner(drug)}) is not spelled")
    if kind == "pair":
        high, low = value.split("/")
        if " over " not in variant_b or "/" in variant_b:
            problems.append("paired reading is not spoken as 'over'")
        if f"[{high}]" not in variant_b or f"[{low}]" not in variant_b:
            problems.append("both halves of the pair must be bracketed")
    if kind == "code":
        if not is_identifier(field_name):
            problems.append(f"{field_name} is not registered as an identifier field")
        if f"spell({value})" not in variant_b:
            problems.append("code is not delivered character by character with spell()")
        if " ".join(ch.upper() for ch in value) not in variant_a:
            problems.append("the plain form of a code must be its characters, spaced")
    if kind in {"name", "time", "noted"}:
        if "spell(" in variant_b or "[" in variant_b:
            problems.append("markup was added to a value that should be spoken as written")
        if value not in variant_b or value not in variant_a:
            problems.append("the value was altered on its way to the listener")
    return problems


# --------------------------------------------------------------------------------------
# T7 — provider observability
# --------------------------------------------------------------------------------------


async def t7_provider() -> Result:
    """Losing Rime must be visible in the state, in the event log and to the dashboard."""
    failures: list[dict[str, Any]] = []

    async def work(client: HearbackClient) -> dict[str, Any]:
        before = (await client.state())["provider"]
        if before != "rime":
            failures.append({"reason": f"a session starts on {before!r}, not 'rime'"})
        await client.set_provider("browser_fallback", reason="RIME_API_KEY rejected")
        during = (await client.state())["provider"]
        if during != "browser_fallback":
            failures.append({"reason": f"provider did not switch: {during!r}"})
        events = await _drain_events(client)
        switch = [e for e in events if e["type"] == "provider_changed"]
        if not switch:
            failures.append({"reason": "no provider_changed event reached the stream"})
        elif not switch[-1]["data"].get("reason"):
            failures.append({"reason": "provider_changed carried no reason"})
        await client.set_provider("rime", reason="key restored")
        after = (await client.state())["provider"]
        if after != "rime":
            failures.append({"reason": f"provider did not return to rime: {after!r}"})
        return {"events_seen": len(events), "provider_events": len(switch) + 1}

    measured = await _with_client(work)
    return Result(
        id="T7",
        name="Provider observability",
        criterion="fallback changes the state, emits an event with a reason, and is reversible",
        status=PASS if not failures else FAIL,
        how="in-process sidecar; /provider driven and the SSE backlog read back",
        runs=1,
        measured=measured,
        failures=failures,
        note="The audible half — the fallback voice announcing itself — is a browser behaviour and "
        "is shown in the demo recording, not measured here.",
    )


async def _drain_events(client: HearbackClient) -> list[dict[str, Any]]:
    """Read the SSE backlog without following, so the harness never blocks on a live stream."""
    response = await client._client.get(
        "/events", params={"session_id": client.session_id, "since": 0, "follow": "false"}
    )
    response.raise_for_status()
    events = []
    for block in response.text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events
