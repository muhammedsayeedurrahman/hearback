# RIME_EVIDENCE

Voice evidence for Hearback. Everything below was produced by `scripts/run_evidence.py`; the
machine-readable output is `evidence/results.json` and the generated table is
[`evidence/RESULTS.md`](evidence/RESULTS.md). Where a test has not been run, it says so and says
what it would take to run it. No number in this file was estimated, extrapolated or rounded up
from a smaller sample.

---

## 1. The hard voice claim

> When a clinician corrects the agent **while it is speaking** or **while a tool is running**, the
> stale answer never reaches the listener: audio for the superseded utterance is cancelled at Rime,
> the record of what was heard is cut at the last word actually delivered, obsolete tool results are
> dropped by epoch arithmetic rather than by a model's judgement, and only values a human explicitly
> confirmed are relayed to the receiving clinician.

The claim is falsifiable in four independent ways, and each has a test: audio that keeps playing
after a cut (T1, T2), a ledger that misreports what was heard (T4), a tool answer to a superseded
question reaching speech (T3), and an unverified value crossing the relay gate (T2's relay
assertion, plus the engine's gate tests).

### Why voice is load-bearing

A paramedic's hands are on the patient and the correction is spoken mid-sentence. Remove speech and
the correction becomes a form field, the barge-in disappears, and there is nothing left to build.
The failure mode this product addresses — *the fact changed while the machine was still talking
about the old one* — only exists in a spoken channel.

---

## 2. What Rime does here

Rime is the only path by which anything is spoken: the read-back the paramedic confirms, the
reconciliation after a barge-in, and the relay to the receiving nurse. It is not a play button on a
transcript.

| Field | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `lyra` (English), `nadi` (Hindi relay, stretch) |
| Endpoint | `wss://users-ws.rime.ai/ws3`, `use_websocket=True` |
| Audio | PCM, 16 kHz, `speedAlpha` 0.95 |
| Delivery controls | `spell()` for drug names on the ISMP look-alike list and for identifiers; `[brackets]` with `inlineSpeedAlpha` 0.8 to slow spoken numbers |
| Cancellation | `{"operation": "clear", "contextId": ...}` on interruption — `agent/rime_ws3.py` |
| Epoch on the wire | `contextId` is `hb-e<epoch>-<n>`, so a frame can be traced to the utterance it answers |
| Catalog check | `GET https://users.rime.ai/data/voices/all-v2.json` at boot; the agent refuses to start if the model + language + speaker triple is missing |

Two of these are ours rather than the plugin's, and matter to the claim. The stock
`livekit-plugins-rime` stream sends `flush` and `eos` on interruption but never `clear`, so Rime
keeps generating audio for a context nobody will hear, on a pooled connection the next sentence
reuses. `agent/rime_ws3.py` sends `clear` for the interrupted context and puts the epoch in the
`contextId`. Both are covered by `agent/tests/test_rime_ws3.py`.

---

## 3. Procedure

```bash
uv venv && uv pip install -e ".[dev]"
python scripts/run_evidence.py --all          # T2 T3 T4 T5 T7 — offline, deterministic, no keys
python scripts/run_evidence.py --all --live   # adds T1, T6 and the audio half of T5
```

Offline the sidecar runs in-process over an ASGI transport, the agent's speech is simulated against
a playout clock, and the extractor is the rule-based one — so the same command produces the same
numbers on any machine, with no account anywhere. `--live` needs `RIME_API_KEY`; the digit error
rate additionally needs `DEEPGRAM_API_KEY`.

The distinction that matters when reading section 4: **simulated playout** means the interruption
instant and the word timings come from fixtures rather than from a sound card. It exercises the
ledger arithmetic, the epoch fence and the relay gate exactly as they run in production, and it does
not exercise the audio path. Tests that need the audio path are not reported as passing on the
strength of a simulation.

---

## 4. Results

From `evidence/results.json`, commit `767afcb`, offline mode.

| # | Test | Pass criterion | Result | Status |
|---|---|---|---|---|
| T1 | Time-to-silence | P90 ≤ 300 ms, barge-in to last audio frame | — | **NOT RUN** (needs `--live`) |
| T2 | Stale audio leak | 0 words after the cut recorded as delivered or quoted back | 12 / 12 offsets clean, 0 leaked words | **PASS** |
| T3 | Stale tool fencing | old-epoch tool result never accepted; re-run applied | 20 / 20 runs clean | **PASS** |
| T4 | Heard-ledger accuracy | ≥ 90 % of cutoffs within ±1 word of annotation | 24 / 24 within ±1 word, 23 exact | **PASS** |
| T5 | Readback delivery controls | every item carries the controls its kind requires | 30 / 30 conforming | **PASS** |
| T6 | Time-to-first-audio | report P50/P90/P99, cold and warm | — | **NOT RUN** (needs `--live`) |
| T7 | Provider observability | fallback changes state, emits an event with a reason, reverses | 1 / 1 | **PASS** |

### T2 — stale audio leak

Twelve barge-in offsets from 120 ms to 5,000 ms are swept through the scripted handover. At each
offset the harness asserts that the words the agent believes were delivered are a strict prefix of
the sentence, that a cut sentence is never recorded as complete, and that the reconciliation quotes
**only** words that were delivered. Each offset runs once because the replay is deterministic;
repeating an identical run would add a number, not a fact.

This is the state-path half of the claim. The audio-path half — recording what actually left the
speaker and re-transcribing it — is T1 plus re-transcription and needs Rime.

### T3 — stale tool fencing

Twenty runs, each: name a drug, start the allergy cross-check with a **3,000 ms** injected delay,
correct the drug at **1,000 ms**, then check that the in-flight answer is rejected by the fence, that
the re-run under the new epoch is accepted, and that an extraction stamped with the old epoch is
dropped by the sidecar rather than folded into the truth state. 20/20, no exceptions. The fence is
integer comparison in `engine/epoch.py`; no model is consulted.

### T4 — heard-ledger accuracy

Four sentences with Rime-shaped word timestamps, 24 hand-annotated cutoffs, including three
deliberate boundary cases: an interruption exactly on a word onset, one 10 ms before an onset, and
one before any word has begun. All 24 fell within ±1 word and 23 matched the annotated word
exactly, so the criterion is met with one cutoff inside the tolerance rather than on it.

That one is L3 — *"M R N noted as A four seven two nine one three."* — cut at 1,900 ms. `A` ends at
1,800 ms and `four` begins at 1,860 ms, so the cut lands 40 ms into `four`. The ledger counts a word
as delivered once its onset has passed and reports `four`; the annotation says `A`, on the judgement
that 40 ms of a word is not something a listener heard. The disagreement is the convention at a word
boundary, not an arithmetic error, and it is recorded in `evidence/results.json` under T4's
`failures` rather than smoothed away.

This measures the ledger arithmetic against annotations, not Rime's timestamp accuracy. Real
timestamps are what `scripts/rime_preflight.py --probe` fetches, and whether Coda emits them over
ws3 at all is the open question that probe answers.

### T5 — readback delivery controls

All 30 pronunciation fixtures — look-alike drugs, doses, paired vitals, alphanumeric codes, Indian
patient names, times — rendered in both variants and checked against the rule for their kind: a
look-alike drug must be spelled, a number must be bracketed *and* repeated with `spell()`, a paired
reading must be spoken as "over" and never as a slash, a code must be spelled character by
character, and a name or a time must reach the listener unaltered. Variant A must carry no markup at
all, since it is the record of what a listener would report hearing.

The intelligibility half — rendering both variants through Rime, re-transcribing them and comparing
digit error rates — is implemented in `sim/rime_probe.py` and runs under `--live`. It has not been
run, so no WER is claimed here.

### Beyond the seven: the confirmation guard

Not one of T1–T7, and worth stating because it closes the other half of the read-back loop. A
confirmation is only allowed to settle the values the listener actually heard read back: if the
confirming turn names a number that appeared neither in the delivered read-back nor in the live
value, the engine refuses it, logs `confirmation_challenged` with the reason, and leaves the fact
unverified. Both sides believing they agreed is precisely the failure this product exists to catch.

`fixtures/scenario_mishearing.json` is that case end to end — the agent reads back ten milligrams
in full, the paramedic answers "yes, five milligrams is correct", and the relay carries nothing:

```bash
python scripts/run_scenario.py fixtures/scenario_mishearing.json
```

The rule is deliberately narrow. It compares numbers only, spoken or written, because that is
where mishearing concentrates and because widening it to every word would refuse honest
confirmations that reword the value. Covered by `engine/tests/test_confirmation.py` and pinned end
to end in `sim/tests/test_replay.py`.

### T7 — provider observability

Losing Rime is driven through `/provider`, and the harness checks the state changes, an event
carrying a reason reaches the SSE stream, and the switch reverses. The audible half — the fallback
voice announcing itself before it speaks — is a browser behaviour shown in the demo recording rather
than measured here.

---

## 5. What has not been measured

Stated plainly, because the gap between these two lists is the whole value of the file.

- **T1 and T6 have not been run.** No time-to-silence and no time-to-first-audio number exists in
  this repository. The probes are written (`sim/rime_probe.py`) and wired into the harness; they
  need `RIME_API_KEY` and a network. Until then the 300 ms figure in the README is a **target**, not
  a result.
- **T5's digit error rate has not been measured.** The clips are not yet in `evidence/clips/`.
- **T1 measures the socket, not the ear.** When it is run, it will time from the `clear` frame to
  the last audio frame Rime sends. A listener is further away by whatever the client's playout
  buffer holds, so the number will be a lower bound on what a microphone in the room would record.
- **No end-to-end run through LiveKit has been measured.** The agent (`agent/main.py`) is written
  against `livekit-agents ~=1.5` and the plugin internals it adapts are pinned, but the evidence
  here comes from the in-process sidecar.
- **Simulated audio throughout.** Browser mic, not telephony. English STT only. The Hindi relay is
  unmeasured for code-switching.
- **Small samples.** 12 offsets, 20 runs, 24 cutoffs, 30 fixtures. Enough to catch a regression,
  not enough to characterise a distribution. Nothing here is labelled as more than it is.

---

## 6. How to reproduce every number

```bash
git clone https://github.com/hameed0342j/hearback-h.git && cd hearback-h
uv venv && uv pip install -e ".[dev]"
pytest -q                                     # 183 unit tests
python scripts/run_scenario.py fixtures/scenario_morphine.json   # the handover, as a transcript
python scripts/stress_barge_in.py             # the barge-in sweep on its own
python scripts/run_evidence.py --all          # regenerates evidence/results.json and RESULTS.md
```

With keys:

```bash
cp .env.example .env                          # fill in RIME_API_KEY at minimum
python scripts/rime_preflight.py --probe      # catalog check, then one sentence over ws3
python scripts/run_evidence.py --all --live   # T1, T6, and T5's clips
```
