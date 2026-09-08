# Hearback: GitHub and Open-Source Feature Impact Analysis

*Research date: 2026-09-08 | Scope: open-source realtime voice systems, interruption/evaluation tooling, and verification-first clinical voice projects | Confidence: high for repository mechanics; medium for project pages and benchmark generalisation*

## Executive verdict

Hearback should keep its current architecture and borrow mechanisms, not replace the truth-state engine with another voice framework. The highest-impact feature is a **trace-complete closed-loop handover**: record the exact audio boundary that was heard, require sender confirmation, require receiver read-back, and grade every spoken claim against the immutable event ledger. This extends Hearback's existing moat instead of turning it into a generic voice assistant.

The recommended implementation order is:

1. **P0: trace-complete interruption and stale-result evidence**
2. **P0: receiver hear-back with mismatch detection**
3. **P1: ATMIST completeness and criticality-aware read-back**
4. **P1: provider-independent barge-in state plus caller-observable audio metrics**
5. **P2: tamper-evident replay, addressee gating, and multilingual relay**

Do not make telephony, a new full-duplex model, or Hindi code-switching the core product. They increase integration risk without strengthening the central claim as much as the verification and evidence layers.

## What was searched

The search covered repositories and public technical sources in four groups:

- Realtime runtimes: LiveKit Agents, Pipecat, Rime integrations, Qwen Audio Agent, AVA for Asterisk, and focused barge-in projects.
- Transport and telephony: Asterisk AudioSocket agents, Rime WebSocket integrations, and caller-side latency/stream pacing tools.
- Evaluation: Full-Duplex-Bench, quantumCF voice-agent-barge-in-tests, LangWatch Scenario, Coval benchmarks, and VAmoS/Riley patterns.
- Verification and clinical precedents: Truth-Lens/VoiceClaim Auditor, ORION, read-back projects, clinical handover research, and recent voice-agent hackathon examples.

This is a decision-oriented shortlist, not a claim that every GitHub repository containing “voice agent” was exhaustively enumerated. Repositories were selected for mechanisms that map directly to Hearback's interruption, ledger, relay, or evidence path.

## Repository comparison

| Repository | Distinctive mechanism | Hearback use | Effort | Impact |
|---|---|---|---:|---:|
| [livekit/agents](https://github.com/livekit/agents) | Adaptive interruption, semantic turn detection, aligned transcripts, tool lifecycle | Keep as the transport/runtime; expose explicit events into the engine | Medium | Very high |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) | Typed frame processors, audio contexts, interruption callbacks, context-based TTS gating | Borrow provider-independent audio/context boundaries | Medium | High |
| [rimelabs/rime-livekit-agents](https://github.com/rimelabs/rime-livekit-agents) | Official Rime streaming and dynamic voice/language examples | Validate the adapter boundary and catalog-driven voice selection | Low | High for Rime compliance |
| [hkjarral/AVA-AI-Voice-Agent-for-Asterisk](https://github.com/hkjarral/AVA-AI-Voice-Agent-for-Asterisk) | Late-output quarantine, heard-prefix history handling, post-TTS protection | Quarantine old-epoch work and prevent echo-triggered interruptions | Medium | High |
| [ictinnovations/asterisk-ai-voice-agent](https://github.com/ictinnovations/asterisk-ai-voice-agent) | 20 ms pacing, bounded queues, AudioSocket framing and flush behavior | Add playout-side accounting and queue flush checks | Medium | High for future telephony |
| [shnavii11/barge-in-voice-agent](https://github.com/shnavii11/barge-in-voice-agent) | Epoch-tagged TTS invalidation, reversible duck then hard stop, played-audio context | Compare soft interruption and hard correction paths | Low | High |
| [rogerchappel/bargekit](https://github.com/rogerchappel/bargekit) | Small deterministic turn-taking state machine and synthetic fixtures | Keep barge-in policy testable outside provider callbacks | Low | Medium-high |
| [attenlabs/saa-sdk](https://github.com/attenlabs/saa-sdk) | Addressee detection before STT | Add only for multi-speaker/noisy deployment; not core MVP | Medium | Medium |
| [QwenAudio/qwen-audio-agent](https://github.com/QwenAudio/qwen-audio-agent) | Conversation loop continues while background tasks run | Borrow task lifecycle and progress narration | High to adopt; low to borrow | High |
| [DanielLin94144/Full-Duplex-Bench](https://github.com/DanielLin94144/Full-Duplex-Bench) | Human disfluencies, self-correction, chained tools, task/turn metrics | Add self-correction fixtures and joint speech/state grading | Medium | Very high |
| [quantumCF/voice-agent-barge-in-tests](https://github.com/quantumCF/voice-agent-barge-in-tests) | `did_yield`, time-to-yield, talk-over duration across eight scenarios | Add correction, backchannel, echo, noise and telephony regressions | Low | Very high |
| [langwatch/scenario](https://github.com/langwatch/scenario) | Multi-turn scenario DSL, assertions, audio injection, CI batches | Express end-to-end handover journeys as deterministic scenarios | Medium | High |
| [coval-ai/benchmarks](https://github.com/coval-ai/benchmarks) | Frozen fixtures, hashes, warm/cold labels, TTFA and provider metadata | Make evidence reproducible and auditable | Low-medium | Very high |
| [ictinnovations/telephony-voice-agent-benchmark](https://github.com/ictinnovations/telephony-voice-agent-benchmark) | Caller-observable first-audio, pacing, cutoff and wasted-rendered-audio metrics | Measure what was sent/heard, not only internal queue state | Low | High |
| [veris-ai/riley-agent](https://github.com/veris-ai/riley-agent) | Full trace assertions over audio, transcript, tools, arguments and returned state | Check “spoken claim equals verified state” | Medium | Very high |
| [rand0wn/voice-eval](https://github.com/rand0wn/voice-eval) | Scenario, tool, latency and audio artifact evaluation | Inspect for lightweight CI report ideas | Low | Medium; less independently validated |
| [hamza08003/Truth-Lens](https://github.com/hamza08003/Truth-Lens) | Atomic speech claims with graded verification | Borrow claim-level UI language, not its authority model | Medium | High |

### Important source corrections

- The verified Full-Duplex-Bench repository is `DanielLin94144/Full-Duplex-Bench`; the similarly named organisation path is not the canonical source.
- `openbenchmarks/voice-agent-latency` and `omnistream/playback` were not verified as the repositories previously named. Use Coval and the ICT benchmark as the dependable references for those ideas.
- ORION, Second Voice, SOFIA, AgentWard, and related hackathon projects are useful product precedents, but several are project pages rather than public, maintained implementation repositories. Treat their features as inspiration, not reusable code.

## Feature analysis

### 1. Trace-complete closed loop: highest impact

**Feature.** A handover is complete only when the sender confirms critical facts and the receiver repeats them back correctly. The event trace must prove that the final spoken claim corresponds to a `VERIFIED` fact at the current epoch.

**Why it matters.** Hearback already protects the sender-to-agent boundary. Receiver hear-back closes the second boundary: the system can detect a nurse mis-hearing “fifteen” as “fifty” instead of assuming relay success. VAmoS-style trace assertions also expose “say/do” mismatches where an agent claims an action that the tool/state trace does not support.

**Implementation mapping.**

- Add `RECEIVED` as a handover-level status; keep fact statuses unchanged.
- Add `/receiver-readback` or an equivalent engine operation accepting extracted `{field, value}` candidates.
- Compare normalized values through the existing conflict engine.
- Correct readback transitions the fact to `RECEIVED`; mismatch creates `CONFLICTED` and a new epoch.
- Relay generation must emit a trace event containing fact ID, value, epoch, and spoken text hash.
- Add an assertion: every critical spoken claim has a matching current `VERIFIED` fact.

**Evidence.** Run 20 receiver read-backs with five deliberate mismatches. Required result: all five mismatches are surfaced and no mismatched handover reaches `RECEIVED`.

**Impact: 5/5 | Effort: 3/5 | Recommendation: build next.**

### 2. Trace-complete interruption and stale-result evidence

**Feature.** Every run emits a timeline for user onset, interruption decision, Rime clear, last audible frame, ledger cutoff word, epoch changes, stale tool results, and final relay.

**Why it matters.** A queue being flushed internally does not prove that the listener stopped hearing audio. The ICT benchmark adds caller-observable pacing and wasted-audio measurements; Coval adds fixture hashes and warm/cold metadata. Together they make T1-T4 defensible.

**Implementation mapping.**

- Extend `Event.data` with monotonic timestamps and a `measurement_vantage` field.
- Record `rime_clear_sent_ms`, `last_played_frame_ms`, `cutoff_word`, `cutoff_confidence`, and `wasted_audio_ms`.
- Store scenario version, fixture SHA-256, model, speaker, codec, transport, region, and warm/cold status.
- Keep the existing `cut()` function as the canonical ledger calculation; do not infer hearing from transcript text alone when word timestamps exist.
- Add a trace validator that fails if an old-epoch word is marked audible after the cut.

**Impact: 5/5 | Effort: 2/5 | Recommendation: build alongside the core.**

### 3. Self-correction and disfluency fixture suite

**Feature.** Test fillers, pauses, false starts, backchannels, self-corrections, double-talk, echo bleed, and rapid turns, not only clean “WAIT, it was five” audio.

**Why it matters.** Full-Duplex-Bench reports that self-correction is difficult even for strong realtime systems. A correction is not merely an interruption; it changes the canonical fact and invalidates work already in flight.

**Implementation mapping.**

- Add a fixture schema with `audio`, `expected_interruption`, `expected_epoch_delta`, `expected_cutoff`, `expected_fact_transition`, and `expected_relay_exclusions`.
- Port the eight quantumCF scenario categories and add `correction_mid_readback`.
- Keep backchannel cases separate from correction cases so false-stop rate is measurable.
- Grade both acoustic behavior (`did_yield`, `talk_over_ms`) and semantic behavior (fact/epoch/relay assertions).

**Impact: 5/5 | Effort: 2/5 | Recommendation: P0 evidence work.**

### 4. ATMIST completeness plus criticality-aware delivery

**Feature.** Track Age, Time, Mechanism, Injuries, Signs, and Treatment, then require read-back for the high-risk subset: allergies, medications/doses, airway, oxygenation, and hypotension.

**Why it matters.** This is the most useful domain feature that does not require a new model. It makes omissions visible while preserving the core safety rule that `HEARD` is not `VERIFIED`.

**Implementation mapping.**

- Extend `slots.py` with treatment, medications, and drug-time mappings where missing.
- Keep `CRITICAL_FIELDS` explicit and versioned; do not let the LLM decide criticality.
- Ask only for missing ATMIST slots after the sender turn.
- Build relay text in slot order and mark non-critical unverified facts explicitly if the product policy allows them.

**Impact: 4/5 | Effort: 2/5 | Recommendation: P1.**

### 5. Epoch on the wire and context-aware cancellation

**Feature.** Carry the engine epoch into Rime `contextId`, tool task identity, and the STT turn identity where available; send an explicit TTS clear and quarantine late events.

**Why it matters.** The current engine has a correct local fence, but a provider/runtime can still deliver queued audio unless cancellation and context identity are explicit. Pipecat's audio-context gating and Rime's context IDs are the clearest patterns.

**Implementation mapping.**

- Stamp every provider request with the current epoch.
- Reject stale `chunk`, `timestamps`, `done`, tool, and extraction events before playout or state mutation.
- On interruption: increment epoch, send Rime clear, flush local audio, and log late packets as quarantined rather than silently dropping them.
- Ensure the LiveKit plugin version actually sends the required clear operation; add an adapter test around this behavior.

**Impact: 5/5 | Effort: 3/5 | Recommendation: P0 if the live agent path is active.**

### 6. Backchannel-aware fast-path correction detection

**Feature.** Recognize correction markers such as “wait,” “no,” “stop,” and “actually” during agent speech, while not treating “yeah,” “okay,” or “mm-hmm” as hard interruptions.

**Why it matters.** It improves time-to-silence without waiting for a full end-of-turn, but a naive keyword trigger can create false stops.

**Implementation mapping.**

- Use interim STT only as a fast cancellation hint, never as a state mutation.
- Require a correction marker plus a minimum acoustic/linguistic confidence threshold.
- Keep the full turn detector as the authority for accepting the correction.
- Measure false-stop rate on backchannels and time-to-yield on corrections.

**Impact: 4/5 | Effort: 2/5 | Recommendation: P1 after baseline interruption works.**

### 7. Tamper-evident replay

**Feature.** Hash-chain the event log and preserve audio/transcript/timestamp artifacts for replay.

**Why it matters.** It strengthens the “handover firewall” audit story and makes the evidence artifact inspectable, but it does not improve live correctness by itself.

**Implementation mapping.**

- Hash canonical serialized events with SHA-256 and include the previous hash.
- Store the final relay record with verified facts, epochs, confirmation events, and heard boundaries.
- Add replay validation that detects a changed event or missing link.

**Impact: 3/5 | Effort: 1/5 | Recommendation: cheap P2 polish.**

### 8. Addressee gating and echo protection

**Feature.** Avoid interrupting on speech directed at a colleague/patient or on the tail of Hearback's own audio.

**Why it matters.** This matters in a real ambulance, but it adds a hosted inference dependency and can hide speech that should have been reviewed. It is a deployment feature, not the strongest hackathon differentiator.

**Implementation mapping.**

- Start with a 350 ms post-TTS echo-protection window and explicit event logging.
- Treat addressee confidence as a routing signal, never as permission to delete raw audio.
- Preserve all audio for replay and allow a wake phrase fallback.

**Impact: 3/5 | Effort: 3/5 | Recommendation: only after noise tests.**

### 9. Hindi receiver relay and telephony

**Feature.** Relay verified facts in Hindi or carry the experience over SIP/PSTN.

**Why it matters.** It can broaden access, but it is not the unique correctness claim and has meaningful unverified quality/network risk. The existing Rime research also flags that Hindi-English code-switching is not a proven single-voice path.

**Implementation mapping.**

- Keep language selection after verification, so translation/rendering can never change canonical facts.
- Run a short pronunciation and digit intelligibility gate before enabling it in a demo.
- Treat telephony as a transport adapter; reuse the same engine, epoch, ledger, and relay tests.

**Impact: 3/5 | Effort: 4/5 | Recommendation: stretch only.**

## Final build decision

### Build now

- Keep the immutable engine and relay gate.
- Add trace-complete event fields and a validator.
- Add receiver hear-back and mismatch transitions.
- Add self-correction/disfluency fixtures.
- Add caller-observable cutoff and wasted-audio metrics.
- Verify explicit Rime clear/context behavior in the active LiveKit adapter.

### Build if the baseline passes three times

- ATMIST completeness.
- Criticality-aware read-back grammar and LASA fixtures.
- Fast correction path with backchannel regression cases.
- Tamper-evident relay record.

### Defer

- Telephony as the judged path.
- Full replacement with Pipecat or Qwen Audio Agent.
- Addressee inference as a required dependency.
- Hindi-English code-switching as a core promise.

## Sources

- [LiveKit Agents](https://github.com/livekit/agents)
- [Pipecat](https://github.com/pipecat-ai/pipecat)
- [Rime LiveKit Agents](https://github.com/rimelabs/rime-livekit-agents)
- [AVA for Asterisk](https://github.com/hkjarral/AVA-AI-Voice-Agent-for-Asterisk)
- [Asterisk AI Voice Agent](https://github.com/ictinnovations/asterisk-ai-voice-agent)
- [Barge-in Voice Agent](https://github.com/shnavii11/barge-in-voice-agent)
- [Bargekit](https://github.com/rogerchappel/bargekit)
- [Selective Auditory Attention SDK](https://github.com/attenlabs/saa-sdk)
- [Qwen Audio Agent](https://github.com/QwenAudio/qwen-audio-agent)
- [Full-Duplex-Bench](https://github.com/DanielLin94144/Full-Duplex-Bench)
- [Voice Agent Barge-in Tests](https://github.com/quantumCF/voice-agent-barge-in-tests)
- [LangWatch Scenario](https://github.com/langwatch/scenario)
- [Coval Benchmarks](https://github.com/coval-ai/benchmarks)
- [Telephony Voice Agent Benchmark](https://github.com/ictinnovations/telephony-voice-agent-benchmark)
- [Riley Agent](https://github.com/veris-ai/riley-agent)
- [Truth-Lens / VoiceClaim Auditor](https://github.com/hamza08003/Truth-Lens)
- [Rime ws3 reference](https://docs.rime.ai/api-reference/endpoint/websockets-json)
- [LiveKit async tools](https://livekit.com/blog/async-tools-voice-agents)
- [IMIST-AMBO handover guidance](https://psnet.ahrq.gov/node/41559/psn-pdf)
- [NCC MERP verbal medication recommendations](https://www.nccmerp.org/recommendations-reduce-medication-errors-associated-verbal-medication-orders-and-prescriptions)

## Methodology and limitations

Searches were grouped by mechanism rather than by popularity. Repository claims were checked against README/source links where available; project pages and vendor benchmarks are labelled as lower-confidence evidence. Star counts were intentionally omitted because they change and do not measure suitability. Benchmark numbers should be treated as directional: datasets, regions, providers, and grading models differ. Before implementation, pin the repository commit or package version and rerun the relevant behavior against Hearback's own fixtures.
