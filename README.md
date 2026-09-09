# Hearback

**The handover firewall.** A full-duplex voice agent for clinical handovers that tracks every
critical fact as heard, corrected, verified or superseded, kills stale Rime speech the instant a
clinician corrects it, records exactly which words were audibly delivered, fences obsolete tool
results, and relays only verified facts to the receiving clinician.

> Most voice AI summarises what was said. Hearback guarantees what was heard.

Built for **DataForge × Pathway × Rime**. Simulated data only. No diagnosis, no prescribing, no
treatment decisions.

---

## The problem

A paramedic hands a patient over to an emergency-department nurse in under sixty seconds, hands on
the patient, eyes on the monitors, in a loud environment. Handovers fail not only because
information is missing but because it **changes mid-sentence**: a dose is corrected, an allergy is
remembered, a blood pressure is re-read. Summarisers keep the first version. Humans mis-hear. The
next team must receive the latest verified state.

Neither party can type. The correction is spoken. The receiving side hears the relay. Remove
speech and there is no product.

## What Hearback does

```
Paramedic:  "Patient received 10 milligrams morphine at 14:05."
Agent:      "Confirming. Morphine, ten milli—"
Paramedic:  "WAIT. It was 5 milligrams."            ← barge-in
System:     Rime audio cleared in <300 ms · ledger cut at "ten"
            10 mg → SUPERSEDED · 5 mg → CORRECTED · epoch 4 → 5
Agent:      "I had said ten. You're now saying five. Use five milligrams as final?"
Paramedic:  "Yes."
Agent:      "Five milligrams morphine, verified."
Nurse:      presses Relay → Rime speaks only VERIFIED facts
```

## Core mechanisms

| Mechanism | What it does |
|---|---|
| **Truth-state machine** | Every fact is `HEARD`, `INFERRED`, `CORRECTED`, `CONFLICTED`, `VERIFIED` or `SUPERSEDED`. Only `VERIFIED` crosses to the receiving clinician. The application owns transitions; the LLM only extracts and phrases. |
| **Epoch fence** | Every utterance bumps an integer epoch. Every LLM result, tool result and TTS job is stamped with its epoch. Anything older than the current epoch is dropped. Stale-output protection is arithmetic, not an LLM judgement. |
| **Heard-State Ledger** | Rime ws3 word timestamps × playout clock × interruption instant give the exact word at which the listener stopped hearing. Each fact records what was audibly delivered. Reconciliation is phrased from what was heard. |
| **Closed-loop readback** | Critical values are read back with `spell()` for identifiers and slower numbers via `inlineSpeedAlpha`, and require explicit confirmation before `VERIFIED`. |
| **Confirmation guard** | A "yes" only settles the question that was asked. If the confirming turn names a number the agent never read back — "yes, five milligrams" after the agent said *ten* — the confirmation is refused and logged, and the value stays behind the relay gate. |
| **Continuity during tool work** | The allergy cross-check tool runs with an injected 3 s delay. The agent keeps listening, accepts corrections mid-wait, and re-runs the tool under the new epoch. |

Ranked backlog of further features (F1–F19: receiver hear-back, ATMIST completeness, fast-path
barge-in keywords, criticality tiers, session replay, latency HUD, noise stress, audible fallback,
Hindi relay, epoch on the wire via Rime `contextId`, SCOPE readback classifier, uninterruptible
critical readback, look-alike drug spell-out, interruption quarantine, Hamming event taxonomy,
barge-in regression suite, backchannel-aware barge-in, tamper-evident record, addressee gating) is
in [PLAN.md](PLAN.md#11b-high-impact-features-ranked).

## Architecture

```
Browser (paramedic)  ──mic──►  LiveKit room  ◄──audio──  Browser (receiving nurse)
                                    │
                                    ▼
                      LiveKit Agent (Python)
                        STT  Deepgram nova-3, streaming
                        Turn LiveKit turn detector + Silero VAD, adaptive interruption
                        LLM  fast model, strict-JSON fact extraction, epoch-stamped
                        Tool allergy_check(delay_ms), epoch-stamped
                        TTS  rime.TTS(model="coda", use_websocket=True) → ws3, PCM, word timestamps
                                    │
                                    ▼
                      Truth-State Engine (pure Python, immutable, event-sourced)
                        state machine · epoch fence · heard ledger · relay gate
                                    │
                                    ▼
                      FastAPI sidecar (REST + SSE /events)  ──►  Next.js dashboard
```

Rule: the application owns canonical state, transitions, the epoch fence, the relay gate and the
ledger. The LLM never decides whether a stale fact is allowed through.

## Rime configuration (judged flow)

| Field | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `lyra` (English relay); `nadi` / `taru` (Hindi relay, stretch, `lang: hi`) |
| Language | `en` |
| Endpoint | `wss://users-ws.rime.ai/ws3` via the LiveKit Rime plugin, `use_websocket=True` |
| Audio format | PCM, 16 kHz |
| Transport | LiveKit WebRTC room to browser |
| Delivery controls | `spell()` for MRN and codes; `speedAlpha` 0.95; `inlineSpeedAlpha` on numbers in readback |
| Cancellation | ws3 `{"operation": "clear"}` on interruption |
| Catalog check | `GET https://users.rime.ai/data/voices/all-v2.json` at startup; boot refuses if the model + language + speaker triple is missing |
| Fallback (disclosed) | browser `speechSynthesis`; the fallback voice announces itself, the dashboard badge turns red, the event is logged |

## Third-party services

| Service | Role | Key |
|---|---|---|
| Rime | Primary spoken output | `RIME_API_KEY` |
| LiveKit Cloud | Realtime transport, turn detection, interruption | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| Deepgram | Streaming speech recognition | `DEEPGRAM_API_KEY` |
| Anthropic | Fact extraction and phrasing | `ANTHROPIC_API_KEY` |

## Setup

```bash
git clone https://github.com/hameed0342j/hearback-h.git
cd hearback-h
uv venv && uv pip install -e ".[dev]"
```

**Without any keys** — the engine, the sidecar, the dashboard and the whole evidence suite run
offline. This is the demo that still works when the venue wi-fi does not:

```bash
pytest -q                                                   # 183 tests
python scripts/run_scenario.py fixtures/scenario_morphine.json   # the handover as a transcript
python scripts/run_evidence.py --all                        # regenerates evidence/RESULTS.md

uvicorn api.main:app --reload                               # sidecar on :8000
cd web && npm install && npm run dev                        # dashboard on :3000
```

**With keys**, for the voice path:

```bash
cp .env.example .env               # fill in real keys; never commit .env
python scripts/rime_preflight.py --probe   # catalog check, then one sentence over ws3
python -m agent.main dev                   # joins the LiveKit room
python scripts/run_evidence.py --all --live
```

## Evidence

The hard voice claim, the procedure, the results and — just as important — what has **not** been
measured live in [RIME_EVIDENCE.md](RIME_EVIDENCE.md). The generated tables are
[evidence/RESULTS.md](evidence/RESULTS.md) and `evidence/results.json`.

```bash
python scripts/run_evidence.py --all          # T2 T3 T4 T5 T7, offline and deterministic
python scripts/run_evidence.py --all --live   # adds T1, T6 and T5's rendered clips
```

| Test | Pass criterion | Status |
|---|---|---|
| T1 Time-to-silence | P90 ≤ 300 ms from barge-in onset to last audio frame | **not run** — needs `--live` |
| T2 Stale audio leak | 0 words after the cut recorded as delivered or quoted back | pass, 12/12 offsets |
| T3 Stale tool fencing | old-epoch result never accepted; re-run applied | pass, 20/20 |
| T4 Heard-ledger accuracy | ≥ 90 % within ±1 word of annotated cutoff | pass, 24/24 within ±1 word (23 exact) |
| T5 Readback delivery controls | every item carries the controls its kind requires | pass, 30/30 |
| T6 Time-to-first-audio | P50/P90/P99, cold and warm labelled | **not run** — needs `--live` |
| T7 Provider observability | fallback changes state, emits a reason, reverses | pass |

The 300 ms figure is a **target** until T1 has been run against Rime. Nothing in this repository
reports a latency number that was not measured.

## Known limitations and failure behaviour

- Browser audio only in the judged flow; telephony is documented future work.
- English STT only; the Hindi relay is a stretch and unmeasured for code-switching.
- If Rime is unreachable the fallback voice announces itself and the session continues with the
  badge red; nothing is relayed silently.
- If STT drops, transcript text can be posted to `/utterance` and the truth state continues.
- Small samples are labelled exploratory in the evidence file.

## Repository layout

```
agent/      LiveKit Agents (Python): STT, turn handling, epoch-stamped Rime ws3, ledger, tools
engine/     Pure-Python truth-state machine, epoch fence, conflict engine, relay gate, tests
api/        FastAPI sidecar: REST + SSE event stream
web/        Next.js dashboard: transcript, truth state, heard ledger, relay, provider badge
sim/        Deterministic replay, barge-in sweep, acceptance tests T1-T7, live Rime probes
fixtures/   Scenario, pronunciation, ledger-annotation and barge-in offset fixtures
scripts/    rime_preflight.py, run_scenario.py, run_evidence.py, stress_barge_in.py
evidence/   Generated results.json and RESULTS.md, plus clips once rendered live
docs/       PLAN.md companion material and research sources
```

## Dashboard

Three columns, in the order a handover moves.

- **Live conversation** — every turn, and the agent's speech as the listener received it: an
  interrupted line is shown cut, with the word the audio stopped on. Turns can be typed, which is
  the documented text fallback when streaming speech is unstable.
- **Truth state** — one row per fact with its status chip, superseded values struck through
  beneath it, and a *heard* sub-row highlighting the cutoff word. The sentence the engine wants
  spoken next is shown in both forms: as words, and as the marked-up text sent to Rime. It can be
  delivered in full or cut off at a chosen millisecond, which is how the barge-in is demonstrated
  without a microphone.
- **Relay** — what will be spoken to the receiving clinician, what is being held back and why,
  ATMIST-AMBO coverage, and the stress controls: the injected cross-check delay and a switch that
  simulates losing Rime so the badge, the event and the announced fallback can be seen.

The dashboard holds no truth state of its own. It renders `/state` and posts what the clinician
does, so nothing on screen can disagree with the state the relay gate consults.

- [PLAN.md](PLAN.md): full analysis, idea, architecture, truth-state model, acceptance tests, feature backlog, build timeline.
- [docs/research/](docs/research/): problem statement, original 4-hour plan, deep-research brief, facts verified against live Rime and LiveKit sources on 2026-09-08, and the [open-source and hackathon research report](docs/research/opensource-and-hackathon-research.md) (96 sources) behind features F10–F19.
- [docs/research/github-and-feature-impact-analysis.md](docs/research/github-and-feature-impact-analysis.md): related open-source repositories, reusable mechanisms, feature impact ranking, and implementation recommendations.

## Safety

Synthetic patients only. Hearback does not diagnose, prescribe or recommend treatment. It decides
what is safe to pass forward, and a human confirms every critical value before it is relayed.

## License

MIT
