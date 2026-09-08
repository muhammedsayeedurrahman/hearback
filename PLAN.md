# Hearback — The Handover Firewall
## DataForge × Pathway × Rime — complete plan, analysis and MVP build guide

Date: 2026-09-08. Sources: Rime problem statement (Rime PS.pdf), Hearback 4-hour build plan, Rime deep-research brief (research.pdf / compass markdown), live Rime docs + catalog fetched today, LiveKit Agents docs, DecisionOS repo.

---

## 0. One-paragraph verdict

Build **Hearback**: a full-duplex voice agent that listens to a simulated paramedic → emergency-department handover, keeps a canonical *truth state* for every critical fact, kills stale Rime speech the instant a clinician corrects it, fences obsolete LLM/tool results so they can never re-enter the conversation, and relays **only verified facts** to the receiving clinician in Rime's voice. The upgrade over the original 4-hour plan is a **Heard-State Ledger**: using Rime's word-level timestamps we record exactly which words were *audibly delivered* before an interruption, so the system reconciles against what the human actually heard, not what the model generated. This is the exact full-duplex test the organisers describe in the problem statement, it is voice-necessary by construction, and it produces a repeatable acceptance test.

The research brief's alternative (a Hinglish telephony agent) is a good lane but a risky one: Coda's Hindi has only three voices, Hindi-English code-switching is undocumented, and the demo could end in a negative result. We keep its best pieces as layers on top of Hearback: a pronunciation fixture for drug names, doses, MRNs and Indian patient names, a proper latency/interruption eval harness, and an optional Hindi relay voice for the receiving nurse.

---

## 1. What the challenge actually rewards

### 1.1 Rubric (from the PS)

| Criterion | Weight | What it means for us |
|---|---|---|
| Problem and necessity of voice | 25% | Hands-busy paramedic, time-critical, both parties are already talking. Removing speech makes the product useless. |
| Hard voice engineering | 25% | Interruption + recovery, continuity during tool work, controlled delivery. The PS literally spells out our test case. |
| Rime integration and voice experience | 20% | Coda over ws3 with word timestamps, spell() for identifiers, catalog queried at startup, provider badge visible. |
| Evidence and reproducibility | 20% | RIME_EVIDENCE.md with a repeatable script, fixtures, saved clips, P50/P90 tables, cached vs uncached labelled. |
| Demo clarity | 10% | 90-second scripted scenario; one deliberate failure case; state transitions visible on a dashboard. |

40% of the score is engineering + reproducibility. An eval harness is disproportionately rewarded.

### 1.2 The PS's own full-duplex test (this is our spec)

> "Introduce a fixed delay into a tool call. While the agent is speaking or waiting, interrupt it and change one part of the request. Verify that queued Rime audio stops promptly, the updated instruction reaches the application, stale tool results are not spoken as current, background work is cancelled or reconciled correctly, and the final spoken response reflects what the user actually heard and requested."

Every clause maps to a Hearback component:

| PS clause | Hearback mechanism |
|---|---|
| queued Rime audio stops promptly | Barge-in → `{"operation":"clear"}` on ws3 + local playout flush; measured time-to-silence |
| updated instruction reaches the application | Correction is extracted into truth state with a new epoch |
| stale tool results are not spoken as current | Epoch fencing: any result stamped with an older epoch is dropped at the relay gate |
| background work cancelled or reconciled | The delayed "allergy / interaction cross-check" tool is cancelled or re-run against the new state |
| final response reflects what the user actually heard | Heard-State Ledger built from Rime word timestamps + playout clock |

### 1.3 Hard eligibility rules

- Verifiable Rime integration in code; Rime must be the primary spoken output, not a welcome message.
- Working product path (no scripted mock).
- Recorded demo ≤ 4–5 min showing user, problem, normal flow, hard voice problem, one stress case, measurement, and active provider.
- README with exact Rime model ID, speaker, language, endpoint, audio format, transport, limitations, failure behaviour.
- `RIME_EVIDENCE.md` with claim, acceptance test, procedure, result, limitations, repeatable command.
- `.env.example` with placeholders only. Pass the organiser preflight. Never commit a key.
- Fallbacks allowed but must be visible. Use synthetic patient data only.

---

## 2. Direction analysis: Hinglish telephony vs Hearback

| | Hinglish telephony agent (research brief) | Hearback handover firewall |
|---|---|---|
| Voice necessity | Strong (phone-first users) | Strong (hands busy, eyes on patient) |
| Matches a PS path | Multilingual + telephony | Interruption/recovery + continuity during tool work + controlled delivery (three paths) |
| Verified Rime capability | Hindi = 3 Coda voices (`hin`, `nadi`, `taru`); Hinglish code-switch NOT documented | Coda English, ws3 clear/timestamps: documented and used by LiveKit plugin |
| Infra risk | Twilio SIP trunk, μ-law tuning, India→US RTT | Browser mic + LiveKit room; telephony optional |
| Acceptance test | Latency + WER, may return negative results | Deterministic: stale words leaked = 0, time-to-silence, ledger accuracy |
| Demo risk | High: a bad Hindi render on stage is fatal | Low: the failure case is the feature |
| Novelty | Moderate (multilingual demos exist in LiveKit examples) | High: fact-level "what was heard" provenance; nobody in the Rime catalog does this |

Decision: **Hearback core, with three layers borrowed from the research brief** — pronunciation fixture (controlled delivery), eval harness (reproducibility), Hindi receiver voice as a stretch (multilingual routing).

---

## 3. The upgraded idea

Pitch line: **"Most voice AI summarises what was said. Hearback guarantees what was heard."**

### 3.1 Five mechanisms that make it novel

**1. Heard-State Ledger (the moat).**
Rime ws3 returns word-level timestamps for every synthesised chunk. LiveKit's Rime plugin exposes them as TTS-aligned transcription. We combine those timestamps with the playout clock (frames actually pushed to the speaker) and the interruption instant. Result: for every spoken sentence we know the exact word at which the listener stopped hearing. Each fact in the truth state records `delivered: {text_heard, cutoff_word, cutoff_ms}`. When the paramedic interrupts "The patient received ten mill—" the ledger records that "ten" was heard and "milligrams" was not; the reconciliation question is phrased from what was heard: "I had said ten. You're now saying five. Use five milligrams as final?" LiveKit already truncates chat history to the heard portion; we push that down to the fact level and expose it on the dashboard.

**2. Epoch-fenced generation.**
Every accepted utterance increments a monotonic `state_epoch`. Every LLM extraction, tool call and TTS job is stamped with the epoch it was born under. The relay gate refuses to speak, or to apply, anything whose epoch is older than the current one. Stale-output protection is a pure function of integers, not an LLM judgement. This is the PS's "cancel or fence obsolete model and tool results".

**3. Truth-state machine with a relay gate.**
States: `HEARD`, `INFERRED`, `CORRECTED`, `CONFLICTED`, `VERIFIED`, `SUPERSEDED`. Only `VERIFIED` crosses to the receiving clinician. The application owns transitions; the LLM only extracts and phrases. Non-negotiable rule: HEARD ≠ VERIFIED.

**4. Closed-loop readback with controlled delivery.**
Aviation/ICU "read-back, hear-back". Before a fact becomes VERIFIED the agent reads it back with `spell()` for identifiers (MRN, drug codes) and slower delivery on numbers via `inlineSpeedAlpha`, using the Rime writing-for-the-ear guide. Two text variants per fixture are rendered and committed as before/after evidence (PS explicitly asks for this).

**5. Continuity during tool work.**
An "allergy and interaction cross-check" tool runs with an injected fixed delay (3 s, configurable). While it runs the agent says a short holding phrase, keeps listening, accepts a correction, and either cancels the in-flight tool or re-runs it against the new epoch. The user can ask "status?" mid-wait.

### 3.2 Differentiators that cost little

- **Provider badge**: dashboard shows `rime · coda · <speaker> · ws3 · pcm 16 kHz` live; if the fallback (browser `speechSynthesis`) ever fires, the badge turns red and the event is logged. Fallback disclosure is a PS requirement.
- **Live catalog check**: at startup fetch `https://users.rime.ai/data/voices/all-v2.json` and refuse to boot if the configured `modelId + lang + speaker` triple is absent. Log it in the demo.
- **Receiver-language routing (stretch)**: the final relay can be spoken in English (Coda `lyra`) or Hindi (Coda `nadi` / `taru`, `lang: hi`), chosen by the receiving nurse. Same truth state, two voices.
- **Immutable event log**: every transition is an append-only event; the dashboard's history panel is just a replay of the log. Doubles as the evidence artefact.

### 3.3 What we do NOT claim

No diagnosis, no prescribing, no treatment recommendations, no real patient data, no EHR integration, no authentication, no telephony in the judged flow (documented as future work).

---

## 4. User, problem, scenario

**User:** ambulance paramedic handing over to an ED triage nurse. Hands are on the patient, eyes are on monitors, environment is loud, and the handover happens by radio or at the bedside in under 60 seconds.

**Problem:** handovers fail not only because information is missing but because it *changes* mid-sentence. A dose is corrected, an allergy is remembered, a BP is re-read. Text summarisers keep the first version. Human receivers mis-hear. The next team must receive the latest verified state.

**Why voice is necessary:** neither party can type; the correction *is* spoken; the receiving side *hears* the relay. Remove speech and there is no product.

**Synthetic scenario (demo fixture `fixtures/scenario_morphine.json`):**

```
Paramedic: "42-year-old male, road traffic accident, GCS 14."
Paramedic: "Allergies none. Patient received 10 milligrams morphine at 14:05."
Paramedic: "BP 90 over 60, pulse 118."
Agent (readback starts): "Confirming. Morphine, ten milli—"
Paramedic: "WAIT. It was 5 milligrams."               ← barge-in
Agent: "I had said ten. You're now saying five. Use five milligrams as final?"
Paramedic: "Yes."
Agent: "Five milligrams morphine, verified."
Paramedic: "Run the allergy check."                     ← tool with 3 s delay
Agent: "Checking allergies, one second."
Paramedic: "Actually, he's allergic to penicillin."     ← correction during tool work
Agent: (tool result from epoch 6 dropped; re-run on epoch 7)
Agent: "Updated. Penicillin allergy noted. Confirm?"
Paramedic: "Confirm."
Nurse presses Relay → Rime speaks only VERIFIED facts.
```

---

## 5. Architecture

```
Browser (paramedic)                       Browser (receiving nurse)
  mic ──► LiveKit room ◄── audio out        dashboard + Relay button
                 │
                 ▼
        LiveKit Agent (Python)  ────────────────────────────────────┐
          STT: Deepgram nova-3 (streaming, interim results)        │
          Turn detection: LiveKit turn detector + Silero VAD        │
          Interruption: adaptive mode, user_interruption_detected   │
          LLM: fast model (Claude Haiku 4.5 / Groq Llama) →        │
               strict JSON fact extraction, epoch-stamped           │
          Tools: allergy_check(delay_ms) — epoch-stamped            │
          TTS: rime.TTS(model="coda", use_websocket=True)           │
               → wss://users-ws.rime.ai/ws3, pcm, word timestamps   │
                 │                                                  │
                 ▼                                                  │
        Truth-State Engine (pure Python, immutable, event-sourced)  │
          ├─ state machine (HEARD/INFERRED/CORRECTED/CONFLICTED/    │
          │                 VERIFIED/SUPERSEDED)                    │
          ├─ epoch fence  (drops anything stamped < current epoch)  │
          ├─ heard ledger (word timestamps × playout clock ×        │
          │                interruption instant)                    │
          └─ relay gate   (VERIFIED only)                           │
                 │                                                  │
                 ▼                                                  │
        FastAPI sidecar: REST + SSE /events ──► Next.js dashboard ◄─┘
```

**Architecture rule:** the application owns canonical state, transitions, epoch fence, relay gate and heard ledger. The LLM extracts and phrases. It never decides whether a stale fact is allowed through.

### 5.1 Why LiveKit Agents (and Plan B)

LiveKit Agents (Python `livekit-agents[rime]~=1.5`) is the organiser-recommended runtime. It gives adaptive interruption (distinguishes real barge-ins from "uh-huh"), semantic turn detection, first-party Rime plugin with ws3 streaming and TTS-aligned transcripts, events `user_interruption_detected` / `agent_false_interruption`, `SpeechHandle.interrupted`, automatic chat-history truncation to the heard portion, and a SIP path if we ever want telephony.

Plan B (if LiveKit setup burns more than 90 minutes): FastAPI + browser `AudioWorklet` + Deepgram WS + Rime ws3 directly. You own barge-in yourself: on VAD onset send `{"operation":"clear"}` to ws3 and flush the worklet ring buffer. More code, more control, same evidence. Keep the truth-state engine identical so the swap is transport-only.

### 5.2 Exact Rime configuration (goes verbatim in README)

| Field | Value |
|---|---|
| Model ID | `coda` (flagship, May 2026; Arcana is sunset on cloud) |
| Speaker (English relay) | `lyra` (Coda default in LiveKit plugin; confirm against catalog at boot) |
| Speaker (Hindi relay, stretch) | `nadi` or `taru` (`lang: hi`; catalog today lists `hin`, `nadi`, `taru`) |
| Language | `en` (BCP-47; `eng` also accepted) |
| Endpoint | `wss://users-ws.rime.ai/ws3` via LiveKit plugin `use_websocket=True` |
| Audio format | `pcm`, 16 000 Hz (plugin default; Coda native is 24 kHz) |
| Transport | LiveKit WebRTC room to browser |
| Delivery controls | `spell()` for MRN/codes, `speedAlpha` 0.95, `inlineSpeedAlpha` on numbers in readback (Coda: >1.0 = faster) |
| Cancellation | ws3 `{"operation":"clear"}` (plugin does this on interruption) |
| Catalog check | `GET https://users.rime.ai/data/voices/all-v2.json` at startup |
| Fallback (disclosed) | browser `speechSynthesis`, badge turns red, event logged |

Quirks to remember: omitting `modelId` silently serves Mist v3 (no Hindi). Coda has no SSML and no `phonemizeBetweenBrackets`; only `spell()` is inline. `speedAlpha` is inverted on Mist v2. Unsupported speaker+lang pairs may not error, so validate against the catalog.

---

## 6. Truth-state model

### 6.1 States and transitions

| Status | Meaning | Can relay? | Enters via |
|---|---|---|---|
| HEARD | Explicit value detected in speech, not confirmed | No | extraction |
| INFERRED | System inferred it (e.g. unit) | No | extraction |
| CORRECTED | Human supplied a newer value for a field that had one | No, verify first | extraction on existing field |
| CONFLICTED | Two values within the same epoch window disagree | No, resolve | conflict engine |
| VERIFIED | Human explicitly confirmed after readback | **Yes** | `/verify` or spoken "yes/confirm" |
| SUPERSEDED | Older value replaced by newer | No | automatic on CORRECTED/VERIFIED |

### 6.2 State object (immutable; every change is a new object + an event)

```json
{
  "session_id": "s_01",
  "epoch": 7,
  "facts": {
    "morphine_dose": {
      "value": "5 mg", "status": "VERIFIED", "epoch": 5,
      "delivered": {"text_heard": "Five milligrams morphine, verified.", "cutoff_word": null},
      "history": [
        {"value": "10 mg", "status": "SUPERSEDED", "epoch": 2,
         "delivered": {"text_heard": "Confirming. Morphine, ten", "cutoff_word": "ten", "cutoff_ms": 1840}}
      ]
    },
    "allergy": {"value": "penicillin", "status": "VERIFIED", "epoch": 7,
                "history": [{"value": "none", "status": "SUPERSEDED", "epoch": 2}]},
    "bp": {"value": "90/60", "status": "HEARD", "epoch": 3}
  },
  "events": ["... append-only ..."]
}
```

### 6.3 Epoch fence

```
on_user_utterance(text):        epoch += 1; extract(text, epoch)
on_llm_result(r):               if r.epoch < epoch: drop + log("stale_llm")
on_tool_result(t):              if t.epoch < epoch: drop + log("stale_tool"); rerun(t, epoch)
on_tts_request(sentence):       stamp(sentence, epoch)
on_playout_frame(f):            if f.epoch < epoch: flush + log("stale_audio")
on_interruption(at_ms):         ledger.cut(current_speech, at_ms)   # uses word timestamps
```

---

## 7. API surface (keep it this small)

| Method | Path | Purpose |
|---|---|---|
| POST | `/session` | Create simulated handover session, returns LiveKit token |
| POST | `/utterance` | Accept transcript text (fallback when streaming voice is unstable) |
| POST | `/extract` | LLM → structured facts, epoch-stamped |
| POST | `/verify` | Mark a field VERIFIED after explicit confirmation |
| POST | `/resolve` | Resolve CONFLICTED with the authoritative value |
| GET | `/state` | Current truth state |
| GET | `/events` | SSE stream of transitions, ledger cuts, provider status |
| POST | `/relay` | Generate and speak final handover from VERIFIED facts only (`lang=en|hi`) |
| POST | `/stress/tool-delay` | Set injected delay for the cross-check tool (evidence fixture) |

---

## 8. Dashboard (do not overbuild)

Three columns plus a status bar.

- **Left, Live conversation:** streaming transcript; latest utterance highlighted; interruption instants marked with a red tick.
- **Centre, Truth state:** one row per fact with status chip. SUPERSEDED rows shown struck through under the live value. A **Heard** sub-row shows the words that were audibly delivered, with the cutoff word highlighted.
- **Right, Relay:** only VERIFIED facts; a Relay button; the language selector (EN/HI); the Rime provider badge.
- **Status bar:** `Listening · Speaking · Verifying · Conflict · Safe to relay`, plus live epoch number and last time-to-silence measurement.

Reuse from DecisionOS: Next.js 16 + Tailwind + dark-mode setup, the `useWebSpeechRecognition` hook (as the text-fallback input), toast pattern. Do not reuse Supabase, auth, Kanban or calendar.

---

## 9. Evidence: acceptance tests (contents of RIME_EVIDENCE.md)

**Hard voice claim:** when a clinician corrects the agent while it is speaking or while a tool runs, stale Rime audio stops within 300 ms (P90), no stale words are spoken after the cut, obsolete tool results never reach speech, and the final relay contains only values the clinician explicitly verified.

| # | Test | Procedure | Pass criterion |
|---|---|---|---|
| T1 | Time-to-silence | Script plays fixture utterances into the room, injects barge-in at fixed offsets (0.5 s, 1.5 s, 3.0 s into agent speech), 20 runs each | P90 ≤ 300 ms from barge-in onset to last audio frame; measured on playout side |
| T2 | Stale audio leak | Same runs; re-transcribe agent audio after the cut with STT | Stale words spoken after cut = 0 in 60/60 runs |
| T3 | Stale tool fencing | Tool delay 3 s; correction injected at 1 s; 20 runs | Old-epoch tool result never spoken; new-epoch re-run applied; 20/20 |
| T4 | Heard-ledger accuracy | 20 interrupted clips, human-annotated cutoff word vs ledger cutoff | ≥ 90% within ±1 word |
| T5 | Readback intelligibility | 30 fixtures: drug names (morphine, metoprolol, amiodarone), doses, MRN codes, Indian patient names, times. Render variant A (raw) and B (spell()/inlineSpeedAlpha), re-transcribe, digit WER | Variant B digit WER ≤ variant A; clips committed under `evidence/clips/` |
| T6 | Time-to-first-audio | End of user turn → first Rime frame, 50 turns; cold and warm connections labelled separately | Report P50/P90/P99; no target, honest numbers |
| T7 | Provider observability | Kill Rime key mid-session | Badge turns red, fallback logged, judged flow re-run on Rime |

Repeatable command: `python scripts/run_evidence.py --all` writes `evidence/results.json` and `evidence/RESULTS.md`.

Limitations to disclose: simulated audio (browser mic, not telephony); English STT only in judged flow; Hindi relay is a stretch and unmeasured for code-switching; small samples labelled exploratory.

---

## 10. Build plan

### 10.1 Day 0 (prep, 2 hours, before the event if allowed)

- Rime account, key, run `scripts/rime_preflight.py` (fetch catalog, render one sentence with `coda`/`lyra`, print TTFA).
- LiveKit Cloud project, Deepgram key, LLM key. `.env.example` with placeholders.
- Clone LiveKit `agent-starter-python`, confirm a voice loop works with Rime as TTS.
- Write the scenario fixture and the 30-item pronunciation fixture.

### 10.2 Core 4-hour path (matches the original plan, priorities unchanged)

| Time | Build | Done when |
|---|---|---|
| 0:00–0:30 | Skeleton | Agent joins room, dashboard loads, catalog check passes |
| 0:30–1:15 | Voice loop | Speak → STT → LLM → Rime speaks back |
| 1:15–2:00 | Truth state | Facts land as JSON with statuses; events stream to dashboard |
| 2:00–2:45 | Conflict + epoch fence | Correction supersedes old value; stale LLM result dropped |
| 2:45–3:20 | Stale kill switch + ledger | Barge-in stops audio; cutoff word recorded and shown |
| 3:20–3:45 | Dashboard | Judge sees transcript, state, conflict, relay |
| 3:45–4:00 | Rehearse | 90-second demo works three times in a row |

### 10.3 Day 2 — evidence and hardening

- `scripts/run_evidence.py` for T1–T7; fixtures in `fixtures/`; results tables auto-generated.
- Tool-delay stress path and status queries ("what's the status?") during tool work.
- Readback with `spell()` and `inlineSpeedAlpha`; commit variant clips.
- README with the exact Rime configuration table above.

### 10.4 Day 3 — polish and demo

- Hindi relay voice (only if catalog and a quick listen pass; otherwise document as future work).
- Record 4-minute demo: user + problem (20 s), normal flow (60 s), kill switch (40 s), tool-delay stress (40 s), evidence table (30 s), provider badge + fallback (20 s).
- Final preflight, secret scan, tag release.

### 10.5 Team split (≤ 4)

1. **Voice:** LiveKit agent, Rime plugin, interruption events, playout clock, ledger cut.
2. **Intelligence:** extraction prompt + JSON schema, truth-state engine, epoch fence, conflict engine, unit tests.
3. **Frontend:** dashboard, SSE client, state chips, ledger view, provider badge.
4. **Evidence + demo:** harness scripts, fixtures, RIME_EVIDENCE.md, README, recording, pitch.

If time gets tight: Truth state → epoch fence → kill switch → ledger → dashboard polish → Hindi.

### 10.6 Cut list

Telephony, EHR, auth, real data, diagnosis, treatment advice, fine-tuning, custom STT, analytics, huge eval suite, multi-patient sessions.

---

## 11. Repo layout

```
hearback/
  agent/                  # LiveKit Agents (Python)
    main.py               # AgentSession wiring, events → engine
    tts_config.py         # Rime config + catalog preflight
    ledger.py             # heard-state ledger (timestamps × playout clock)
    tools.py              # allergy_check with injectable delay
  engine/                 # pure Python, no I/O
    state.py              # immutable truth state + transitions
    epoch.py              # fence
    conflict.py
    relay.py              # VERIFIED-only text builder
    tests/
  api/                    # FastAPI sidecar: REST + SSE
  web/                    # Next.js dashboard (reuse DecisionOS scaffolding)
  fixtures/               # scenario_morphine.json, pronunciation_30.json, barge_in_offsets.json
  scripts/                # rime_preflight.py, run_evidence.py, stress_barge_in.py
  evidence/               # results.json, RESULTS.md, clips/
  README.md  RIME_EVIDENCE.md  .env.example
```

---

## 11b. High-impact features, ranked

Each feature is scored on rubric impact and build cost. Build in this order once the core success condition passes three times in a row. None of these should start before that.

| # | Feature | Rubric axes hit | Effort | Build when |
|---|---|---|---|---|
| F1 | Receiver hear-back (double loop) | Voice necessity, hard engineering, demo | 2 h | Day 2 morning |
| F2 | ATMIST completeness tracker | Voice necessity, demo, domain credibility | 1.5 h | Day 2 morning |
| F3 | Fast-path barge-in keywords | Hard engineering, evidence | 1.5 h | Day 2 afternoon |
| F4 | Criticality tiers with spoken "unverified" tagging | Controlled delivery, Rime integration | 1 h | Day 2 afternoon |
| F5 | Session replay and "what was heard" audio inspector | Evaluation and observability, evidence | 2 h | Day 2 evening |
| F6 | Latency budget HUD and filler priming | Perceived response time, evidence | 1.5 h | Day 3 morning |
| F7 | Siren-noise stress test | Adverse audio conditions, evidence | 1 h | Day 3 morning |
| F8 | Audible provider fallback | Rime integration rule, cheap | 20 min | Day 2, any gap |
| F9 | Hindi receiver relay | Multilingual routing | 1 h + listen test | Day 3, only if it passes |
| F10 | Epoch on the wire: Rime `contextId` = Deepgram `turn_index` | Hard engineering, Rime integration | 1 h | Day 1, with the core |
| F11 | SCOPE readback classifier with Slot F1 | Evidence, domain credibility | 1.5 h | Day 2 morning |
| F12 | Uninterruptible critical readback with buffered corrections | Controlled delivery, hard engineering | 45 min | Day 2 afternoon |
| F13 | LASA drug list forces `spell()`; NCC MERP number grammar | Rime integration, controlled delivery | 1 h | Day 2 afternoon |
| F14 | Quarantine and history rewrite on interruption | Hard engineering, correctness | 1 h | Day 2 afternoon |
| F15 | Hamming event taxonomy and live interruption metrics | Evaluation and observability | 1 h | Day 2 evening |
| F16 | Barge-in regression suite (quantumCF scenarios) in CI | Evidence, reproducibility | 1.5 h | Day 3 morning |
| F17 | Backchannel-aware barge-in with Deepgram keyterms | Adverse audio, hard engineering | 1 h | Day 3 morning |
| F18 | Tamper-evident relay record (hash chain) | Safety framing, cheap | 30 min | Any gap |
| F19 | Addressee gating and post-TTS echo guard | Adverse audio | 1 h | Day 3, if time |

### F1. Receiver hear-back (double loop)

Today the loop closes when the *sender* confirms. Real hear-back closes when the *receiver* repeats the critical value back. After Relay, the agent asks the nurse to repeat the critical facts ("Say back the morphine dose and the allergy"). STT captures the readback, the engine compares against VERIFIED values, and a mismatch flips the fact to CONFLICTED with both values shown. Handover status becomes `RECEIVED` only when both ends match. This makes the product a true firewall on both sides and gives the demo a second "aha" moment. Evidence: 20 scripted readbacks with 5 deliberate mis-hearings, all 5 caught.

### F2. ATMIST completeness tracker

Paramedic handovers follow ATMIST: Age, Time of incident, Mechanism, Injuries, Signs (vitals), Treatment given. The engine maps extracted facts onto these six slots and shows a completeness bar. At the end of the sender's turn the agent asks only for the missing slots ("I have no time of incident. When did it happen?"). This is real domain vocabulary, judges recognise it instantly, and it costs one dictionary plus one prompt. The relay is spoken in ATMIST order.

### F3. Fast-path barge-in keywords

Adaptive interruption waits for the interruption model to decide. We add a second, faster trigger: when STT interim text starts with a correction marker ("wait", "no", "stop", "actually", "correction", "sorry") while the agent is speaking, send the ws3 clear immediately and flush playout, before end-of-turn is detected. Backchannels ("okay", "yeah", "mm-hmm") never trigger it. Evidence: time-to-silence P90 with and without the fast path, plus a 40-utterance backchannel-vs-correction set with false-stop rate. This is the single strongest number in RIME_EVIDENCE.md.

### F4. Criticality tiers with spoken "unverified" tagging

Facts are tiered: **critical** (allergies, drug doses, times of drugs) require readback and confirmation; **informational** (vitals, mechanism, age) can be relayed while still HEARD but the voice says so. The relay text is generated as "Unverified: BP ninety over sixty" for HEARD facts and plain for VERIFIED ones, with a short pause before the tag. Two rendered variants per fact (with and without the tag, same voice and model) are saved as the before/after evidence the PS asks for. Keeps the demo short because only two facts need readback.

### F5. Session replay and "what was heard" audio inspector

Every session records the event log, the user audio, and the agent audio with word timestamps. A Replay button re-feeds the recorded user audio into the engine deterministically and diffs the resulting truth state against the original. The inspector shows agent audio as a waveform with word boundaries and the ledger cutoff drawn on it, so a judge can click the interruption instant and hear exactly where the listener stopped hearing. This is the "Evaluation and observability" path in the PS, and it is what makes T4 (ledger accuracy) reproducible instead of hand-annotated.

### F6. Latency budget HUD and filler priming

Per turn, the status bar shows the four segments: end of user turn → STT final, → LLM first token, → Rime first byte, → first speaker frame. LiveKit exposes these as metrics. Filler priming: as soon as end-of-turn fires, the agent speaks a one-word acknowledgement ("Okay.") from a pre-synthesised Rime clip while the LLM works, then continues. Evidence: perceived-response-time P50/P90 over 50 turns with priming on and off, cold and warm labelled.

### F7. Siren-noise stress test

Mix an ambulance siren and cabin noise track into the user audio at 0, 10 and 20 dB signal-to-noise in the harness. Report STT word error rate on the scenario, false-interruption rate, and whether the fast-path keywords still fire. Negative results are fine and are non-duplicative evidence. No telephony needed.

### F8. Audible provider fallback

When Rime is unreachable, the fallback voice says "Rime unavailable. Fallback voice active." before anything else, the badge turns red, and the event is logged with a timestamp. Twenty minutes of work that satisfies the PS's disclosure rule in a way judges can hear.

### F9. Hindi receiver relay

Unchanged from the stretch goal: Coda `nadi` or `taru`, `lang: hi`, selected by the receiving nurse. Only ships if a five-sentence listen test passes on Day 3. Never in the judged flow otherwise.

### F10. Epoch on the wire

The epoch is not only an integer inside the engine. Every ws3 request carries `contextId = str(epoch)`, so every `chunk`, `timestamps` and `done` event from Rime comes back stamped, and Rime itself keeps only the newest context. Deepgram Flux increments `turn_index` on every end of turn, which gives the same number on the STT side for free. Any Rime event or tool result whose id is not the current epoch is dropped before it reaches playout, the same gate Pipecat uses (`audio_context_available`). Because the LiveKit Rime plugin sends `flush` and `eos` but never `clear`, we subclass it and send `{"operation": "clear"}` on `SpeechHandle.interrupted`. Evidence: T2 and T3 become a count of dropped stale contexts, visible in the event log. Sources: Rime ws3 reference, Pipecat Rime service, Deepgram Flux state, LiveKit plugin source (see docs/research/opensource-and-hackathon-research.md).

### F11. SCOPE readback classifier

After every readback (sender confirm in the core, receiver hear-back in F1) the engine classifies each fact using the air-traffic-control readback taxonomy from SCOPE: **Correct**, **Incorrect** (a safety-critical element changed), **Incomplete** (an element missing), **Non-standard** (right content, wrong phraseology), **Unknown** (not a readback). Correct → VERIFIED; Incorrect → CONFLICTED with both values; Incomplete → re-ask only the missing element; Non-standard → VERIFIED with a note. Report Slot F1 over the fixture set in RIME_EVIDENCE.md. This is a published, citable measure nobody in the hackathon space uses, and it gives the dashboard a per-fact reason for every transition.

### F12. Uninterruptible critical readback with buffered corrections

Allergy and drug-dose readbacks are spoken with `allow_interruptions=False` so a two-second readback always completes, matching Hamming's "non-interruptible disclosure" scenario. Speech during that window is still transcribed and buffered. If the buffer starts with a correction marker (F3 list) the readback is treated as rejected the instant it ends, and the buffered utterance becomes the next epoch without the user repeating it. Evidence: "repeated user speech rate" (Hamming) with and without buffering.

### F13. Look-alike drug list and read-back grammar

Ship a fixture built from the ISMP Confused Drug Names list (look-alike, sound-alike pairs such as hydralazine/hydroxyzine, and the fifteen/fifty, sixteen/sixty number pairs). When an extracted drug is on the list, the readback must use `spell()` and the phonetic alphabet, and the dashboard shows the pair it could be confused with. All numbers in critical readbacks follow NCC MERP: stated twice, once as a word and once digit by digit ("fifty milligrams, five-zero milligrams"), with `inlineSpeedAlpha` on the digits. The same list feeds Deepgram keyterm prompting so STT hears the names it will have to spell. Evidence for T5 becomes the digit WER on the LASA fixture, variant A versus B.

### F14. Quarantine and history rewrite on interruption

Borrowed from AVA for Asterisk. On barge-in: the interrupted assistant turn is replaced in LLM history by its heard prefix only (from the ledger), any LLM or TTS output that arrives late for the old epoch is quarantined in the log rather than discarded silently, and the next extraction prompt is focused on the correction. Tool results are committed to the engine before the agent starts speaking about them, which avoids LiveKit issue #3702 where results are lost and tools re-run. EHR-style writes use `on_duplicate="reject"`.

### F15. Hamming event taxonomy and live metrics

Rename and extend the event log to Hamming's runbook taxonomy: `user.speech_started`, `user.speech_stopped`, `agent.speech_started`, `agent.speech_interrupted {playback_position_ms, heard_boundary_word}`, `interruption.candidate_detected`, `interruption.decision_made {policy_version}`, `interruption.recovered`, `interruption.false_positive`, `silence.timeout`. The dashboard computes false-interruption rate, missed-interruption rate, resume success rate and repeated-user-speech rate live during the demo. Judges see standard industry metric names, and the log is the same one F5 replays.

### F16. Barge-in regression suite in CI

Adopt the eight scenarios from quantumCF's voice-agent-barge-in-tests (hard interruption, backchannel "mhm", filler start, correction, 8 kHz telephony, double talk, echo bleed, rapid turn-taking), add a ninth "correction mid-readback", and run them with `--fail-on-regression` in GitHub Actions against the Plan B transport. Each scenario reports `did_yield`, `time_to_yield`, and `talk_over` with the metric defined as "VAD rising edge to last Rime frame", the definition a previous winning team stated on stage. Fixtures are SHA-256 pinned, Coval style.

### F17. Backchannel-aware barge-in with keyterms

Deepgram `filler_words=true` plus the seven-token list: affirmative backchannels (`mhmm`, `uh-huh`, `okay`, `yeah`) hold the floor; negative ones (`mm-mm`, `uh-uh`, `nuh-uh`) yield. A two-second continuation window on word timestamps decides whether a backchannel became a real turn. The ATMIST slot vocabulary, drug names and units go into Deepgram keyterm prompting (up to 500 tokens). Evidence joins F3: false-stop rate on the 40-utterance set, and a keyterm-on versus keyterm-off WER on the medical vocabulary.

### F18. Tamper-evident relay record

Every relayed handover produces a record: the VERIFIED facts, their epochs, who confirmed what and when, and the heard boundaries. The record is hashed with SHA-256 and chained to the previous record in the session log, so an edit anywhere breaks the chain. Thirty minutes of work that turns the "handover firewall" story into something auditable, and it matches what verification-first hackathon projects were rewarded for.

### F19. Addressee gating and echo guard

Paramedics talk to the patient, to colleagues and to the agent. Two cheap guards from the field: a 350 ms post-TTS protection window so the agent's own tail does not trigger a barge-in (AVA's `post_tts_end_protection_ms`), and an addressee check so speech not directed at the agent is transcribed but does not interrupt (attenlabs saa-sdk has a LiveKit client; a wake-phrase such as "Hearback" is the fallback). Only if time remains on Day 3.

### Critical tier, justified by the data

The omission statistics from the handover literature set the order of the critical tier in F4: allergies (communicated in 54 % of EMS handovers, 39.7 % in the Indian study), medications (59 % / 39.0 %), airway (22 %), hypoxia (74 % not communicated), hypotension (42 % not communicated). Those five slots require readback; everything else relays as HEARD with the spoken tag. Cite the numbers in the README and on the pitch slide.

### Explicitly not adding

Telephony, EHR, multi-patient, auth, real data, diagnosis, treatment suggestions. Each of these costs more than a day or breaks the safety framing.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LiveKit setup eats the morning | Plan B transport (FastAPI + AudioWorklet + ws3) with identical engine |
| Adaptive interruption treats "yes" as a barge-in | Use LiveKit `interruption.mode="adaptive"`; short confirmations handled as turn, not interruption; test with fixture |
| India→US RTT inflates TTFA | Report it honestly; pre-warm ws3; `segment="immediate"`; short system prompt; cold vs warm labelled |
| Word timestamps not surfaced by plugin version | Fall back to playout-clock estimate using chunk boundaries; document accuracy drop in T4 |
| LLM extracts wrong value | Extraction is HEARD only; nothing relays without readback + confirm |
| Hindi voice sounds poor | Keep as stretch; never in the judged flow unless it passes a listen test |
| Rime `timestamps` events not emitted for Coda | Documented for English and Spanish on ws3; verify at preflight, fall back to `mistv3` for the readback voice and record the swap in RIME_EVIDENCE.md |
| Plugin never sends ws3 `clear` | Subclass the LiveKit Rime TTS (F10); T2 proves it |
| Secret leaks in a screenshot | `.env.example` only; gitleaks pre-commit; badge shows provider, never key |

---

## 13. Pitch (final 30 seconds)

"Critical handovers don't fail only because information is missing. They fail because information changes. Hearback is a real-time voice handover firewall. Every fact is tracked as heard, corrected, verified or superseded. When a clinician corrects the agent mid-sentence, we kill the stale Rime audio, record exactly which words were heard, fence the obsolete results, and make sure only the verified version reaches the next team. We don't make AI understand the handover. We make sure the next team hears the right version of it."

**Success condition for the build:** one old value is corrected live, the stale audio stops, the ledger shows the cutoff word, the old value is blocked, the new value is verified, and the receiving clinician hears only the corrected value. When that works three times in a row, stop adding features and start measuring.
