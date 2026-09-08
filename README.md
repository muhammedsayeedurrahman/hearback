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
git clone https://github.com/muhammedsayeedurrahman/hearback.git
cd hearback
cp .env.example .env            # fill in real keys; never commit .env

# agent + engine + api
uv venv && uv pip install -e ".[dev]"
python scripts/rime_preflight.py   # fetches catalog, renders one sentence, prints TTFA
python -m agent.main dev           # joins the LiveKit room

# dashboard
cd web && npm install && npm run dev
```

## Evidence

The hard voice claim, acceptance tests, procedure, results and limitations live in
`RIME_EVIDENCE.md` (written during the build). Reproduce everything with:

```bash
python scripts/run_evidence.py --all
```

| Test | Pass criterion |
|---|---|
| T1 Time-to-silence | P90 ≤ 300 ms from barge-in onset to last audio frame |
| T2 Stale audio leak | 0 stale words after the cut in 60 of 60 runs |
| T3 Stale tool fencing | Old-epoch result never spoken, 20 of 20 |
| T4 Heard-ledger accuracy | ≥ 90 % within ±1 word of annotated cutoff |
| T5 Readback intelligibility | Variant B (spell + slowed numbers) digit WER ≤ variant A; clips committed |
| T6 Time-to-first-audio | P50/P90/P99, cold and warm labelled |
| T7 Provider observability | Fallback announced, badge red, event logged |

## Known limitations and failure behaviour

- Browser audio only in the judged flow; telephony is documented future work.
- English STT only; the Hindi relay is a stretch and unmeasured for code-switching.
- If Rime is unreachable the fallback voice announces itself and the session continues with the
  badge red; nothing is relayed silently.
- If STT drops, transcript text can be posted to `/utterance` and the truth state continues.
- Small samples are labelled exploratory in the evidence file.

## Repository layout

```
agent/      LiveKit Agents (Python): STT, turn handling, Rime TTS, heard-state ledger, tools
engine/     Pure-Python truth-state machine, epoch fence, conflict engine, relay gate, tests
api/        FastAPI sidecar: REST + SSE event stream
web/        Next.js dashboard: transcript, truth state, heard ledger, relay, provider badge
fixtures/   Scenario, pronunciation and barge-in offset fixtures
scripts/    rime_preflight.py, run_evidence.py, stress_barge_in.py
evidence/   Generated results and committed clips
docs/       PLAN.md companion material and research sources
```

- [PLAN.md](PLAN.md): full analysis, idea, architecture, truth-state model, acceptance tests, feature backlog, build timeline.
- [docs/research/](docs/research/): problem statement, original 4-hour plan, deep-research brief, facts verified against live Rime and LiveKit sources on 2026-09-08, and the [open-source and hackathon research report](docs/research/opensource-and-hackathon-research.md) (96 sources) behind features F10–F19.

## Safety

Synthetic patients only. Hearback does not diagnose, prescribe or recommend treatment. It decides
what is safe to pass forward, and a human confirms every critical value before it is relayed.

## License

MIT
