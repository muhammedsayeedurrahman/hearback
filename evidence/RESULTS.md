# Evidence results

Generated 2026-09-09 16:44:40Z · commit `3681bc4` · mode: offline (no keys, no network)

Regenerate with `python scripts/run_evidence.py --all` (add `--live` with a Rime key for T1, T6 and the audio half of T5).

**Claim under test.** When a clinician corrects the agent while it is speaking or while a tool is running, the stale answer never reaches the listener: audio for the superseded utterance is cancelled at Rime, the record of what was heard is cut at the last word actually delivered, obsolete tool results are dropped by epoch arithmetic, and only values a human explicitly confirmed are relayed to the receiving clinician.

| Test | Name | Status | Runs | Key number |
|---|---|---|---|---|
| T1 | Time-to-silence | NOT RUN | — | — |
| T2 | Stale audio leak | **PASS** | 12 | clean runs: 12 |
| T3 | Stale tool fencing | **PASS** | 20 | clean runs: 20 |
| T4 | Heard-ledger accuracy | **PASS** | 24 | within +/-1 word: 1.0 |
| T5 | Readback delivery controls | **PASS** | 30 | conforming items: 30 |
| T6 | Time-to-first-audio | NOT RUN | — | — |
| T7 | Provider observability | **PASS** | 1 | provider events: 2 |

---

## T1 — Time-to-silence

- **Criterion:** P90 <= 300 ms from barge-in to the last audio frame
- **Status:** NOT RUN
- **How measured:** not attempted
- **Scope:** needs live audio from Rime: run with --live and RIME_API_KEY set

## T2 — Stale audio leak

- **Criterion:** 0 words after the cut are recorded as delivered or quoted back
- **Status:** **PASS**
- **How measured:** simulated playout; delivery records and reconciliation text inspected per offset
- **Runs:** 12
- **Scope:** Each offset is run once: the replay is deterministic, so repeating an identical run adds no information. Audio-path evidence (re-transcribing what left the speaker) needs --live; this is the state-path half of the same claim.

| Measure | Value |
|---|---|
| leaked_words | 0 |
| clean_runs | 12 |

## T3 — Stale tool fencing

- **Criterion:** old-epoch tool result never accepted; re-run under the new epoch applied
- **Status:** **PASS**
- **How measured:** in-process sidecar; tool delayed 3000 ms, correction at 1000 ms
- **Runs:** 20

| Measure | Value |
|---|---|
| clean_runs | 20 |
| tool_delay_ms | 3000 |
| correction_at_ms | 1000 |
| wall_clock_s | 60.2 |

## T4 — Heard-ledger accuracy

- **Criterion:** >= 90% of cutoffs within +/-1 word of the annotation
- **Status:** **PASS**
- **How measured:** Rime-shaped word timestamps from fixtures; annotations written by hand
- **Runs:** 24
- **Scope:** Timings are fixtures, not a live synthesis: this measures the ledger arithmetic, not Rime's timestamp accuracy. --live records real timings via scripts/rime_preflight.py --probe.

| Measure | Value |
|---|---|
| annotated_cuts | 24 |
| exact | 23 |
| within_one_word | 24 |
| within_one_rate | 1.0 |

**1 failure(s):**

```json
[
  {
    "sentence": "L3",
    "offset_ms": 1900,
    "expected": "A",
    "got": "four",
    "words_off": 1
  }
]
```

## T5 — Readback delivery controls

- **Criterion:** every item carries the controls its kind requires; variant A stays plain
- **Status:** **PASS**
- **How measured:** markup conformance over the 30-item pronunciation fixture
- **Runs:** 30
- **Scope:** Intelligibility (digit error rate on re-transcribed audio) needs Rime and an STT: run with --live and DEEPGRAM_API_KEY set.

| Measure | Value |
|---|---|
| items | 30 |
| conforming | 30 |

## T6 — Time-to-first-audio

- **Criterion:** report P50/P90/P99; cold and warm labelled separately (no target)
- **Status:** NOT RUN
- **How measured:** not attempted
- **Scope:** needs live audio from Rime: run with --live and RIME_API_KEY set

## T7 — Provider observability

- **Criterion:** fallback changes the state, emits an event with a reason, and is reversible
- **Status:** **PASS**
- **How measured:** in-process sidecar; /provider driven and the SSE backlog read back
- **Runs:** 1
- **Scope:** The audible half — the fallback voice announcing itself — is a browser behaviour and is shown in the demo recording, not measured here.

| Measure | Value |
|---|---|
| events_seen | 2 |
| provider_events | 2 |

