# Open-source voice agents, hackathon precedents and clinical handover: research report

*Generated: 2026-09-08 | Sources: 96 | Confidence: High for framework mechanics and clinical evidence, Medium for hackathon winner details (several projects have no public repo)*

Purpose: find ideas and features for Hearback from GitHub, Devpost, lablab, Cerebral Valley, vendor blogs and the clinical handover literature. Three research agents ran in parallel; this is the synthesis. The resulting ranked features are in `PLAN.md` §11b (F10 to F19).

## Executive summary

LiveKit Agents already ships the two primitives Hearback depends on: Rime ws3 word timestamps arrive as `TimedString` objects when `use_websocket=True`, and `AgentSession(use_tts_aligned_transcript=True)` truncates the assistant turn to the words actually played when an interruption happens. Nobody in open source has turned that signal into a fact-level ledger, and nobody has shipped a HEARD / CORRECTED / VERIFIED / SUPERSEDED state machine for voice. The stale-result problem Hearback's epoch fence solves is a documented, open pain point in LiveKit itself (issue #3702, the async-tools blog). Pipecat and Rime both already carry a per-turn `contextId`, so the epoch can ride natively on the TTS channel. No Devpost, lablab or vendor hackathon project does paramedic-to-ED handover, and no voice hackathon winner from 2025 to 2026 shipped interruption or confirmation mechanics; judges rewarded latency numbers with a stated definition, "it just works" reliability, and one memorable demo moment. The clinical literature supplies exact slot lists (IMIST-AMBO, ATMIST, DENIM), a read-back grammar (NCC MERP), a look-alike drug list (ISMP) and omission statistics that justify which facts must be verified first.

## 1. Interruption and barge-in mechanics in open source

### LiveKit Agents (the framework we build on)

- With `rime.TTS(use_websocket=True)` the plugin declares `aligned_transcript=True` and converts ws3 `timestamps` events into `TimedString(text, start_time, end_time)` pushed through `push_timed_transcript()` ([plugin source](https://raw.githubusercontent.com/livekit/agents/main/livekit-plugins/livekit-plugins-rime/livekit/plugins/rime/tts.py)).
- `TranscriptSynchronizer` paces text by the real timestamps and, on interruption, `mark_playback_finished(interrupted=True)` reports only `forwarded_text`, the words actually played ([synchronizer source](https://raw.githubusercontent.com/livekit/agents/main/livekit-agents/livekit/agents/voice/transcription/synchronizer.py); [text docs](https://docs.livekit.io/agents/multimodality/text/)).
- `agent_activity.py` stores the truncated message with `interrupted=True` and `playback_position`. There is no epoch counter; `speech_handle.id` is the only per-utterance identity, and tool outputs are "ignored, tasks not cancelled" on interrupt ([agent_activity source](https://raw.githubusercontent.com/livekit/agents/main/livekit-agents/livekit/agents/voice/agent_activity.py)).
- Interruption knobs: `min_duration`, `min_words`, `false_interruption_timeout` (2.0 s default), `resume_false_interruption`, `discard_audio_if_uninterruptible`; turn detection modes `turn_detector | vad | stt | realtime_llm | manual` ([turns docs](https://docs.livekit.io/agents/build/turns/)). Adaptive mode with `backchannel_boundary` needs LiveKit Cloud inference ([adaptive docs](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/); reported 86 % precision, 100 % recall at 500 ms, 216 ms median trigger, [blog](https://livekit.com/blog/adaptive-interruption-handling)).
- `session.say(text, allow_interruptions=False)` for must-complete announcements; `SpeechHandle.interrupted`, `wait_for_playout()`, `preemptive_generation` ([speech docs](https://docs.livekit.io/agents/build/speech/)).
- Async tools: `ctx.update()`, `ctx.with_filler()`, `ToolFlag.CANCELLABLE`, `cancel_task()`, `on_duplicate="allow|reject|replace|confirm"`, `ctx.disallow_interruptions()`. The blog states plainly "Interruption ≠ cancellation ... the tool's result gets discarded but code continues running" ([async tools blog](https://livekit.com/blog/async-tools-voice-agents)).
- Known bugs to design around: [#3702](https://github.com/livekit/agents/issues/3702) tool results lost on interruption causing duplicate execution; [#5038](https://github.com/livekit/agents/issues/5038) interrupted speech dropped before first frame; [#5092](https://github.com/livekit/agents/issues/5092) responses API breaks on interrupt during tool call; [#4560](https://github.com/livekit/agents/issues/4560) `disallow_interruptions()` not covering the whole tool execution; [#4183](https://github.com/livekit/agents/issues/4183) heard boundary lost.
- The LiveKit Rime plugin sends `flush` and `eos` with `contextId` but does not send `{"operation":"clear"}` on interruption. Hearback should add that ([plugin source](https://raw.githubusercontent.com/livekit/agents/main/livekit-plugins/livekit-plugins-rime/livekit/plugins/rime/tts.py)).
- Testing: `session.run(user_input=...)`, `result.expect.next_event().is_message(role="assistant").judge(llm, intent=...)`, `.no_more_events()` ([testing docs](https://docs.livekit.io/agents/start/testing/)).
- Example repos: [python-agents-examples](https://github.com/livekit-examples/python-agents-examples) (312 stars) has `uninterruptable/`, `transcription_node/` (modify transcripts before the LLM, the hook point for fact extraction), `metrics_tts/`, and a background observer agent in `doheny-surf-desk/`. [rime-livekit-agents](https://github.com/rimelabs/rime-livekit-agents) (59 stars) overrides the STT node to intercept speech events and switch Rime voices per detected language; no interruption or timestamp features.

### Pipecat

- `TTSService` audio contexts: `create_audio_context`, `audio_context_available`, `on_audio_context_interrupted`, `add_word_timestamps`; frames with an unknown context are dropped ([tts_service API](https://reference-server.pipecat.ai/en/latest/api/pipecat.services.tts_service.html)).
- `RimeTTSService` uses ws3, sends clear on interruption via `_close_context()`, and accumulates word offsets across segments with `_cumulative_time = ends[-1] + _cumulative_time` ([rime service source](https://reference-server.pipecat.ai/en/latest/_modules/pipecat/services/rime/tts.html)).
- `MinWordsUserTurnStartStrategy` and `KrispVivaIPUserTurnStartStrategy` for word-gated barge-in ([turn strategies](https://docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies)).

### Rime ws3

- Client sends `{"text","contextId"}`, `{"operation":"clear"|"flush"|"eos"}`; server emits `chunk`, `timestamps` (`words[]`, `start[]`, `end[]`, seconds from synthesis start), `done`, `error`, each with `contextId`. "Rime will not maintain multiple simultaneous context ids" ([ws3 reference](https://docs.rime.ai/api-reference/endpoint/websockets-json)). Word timestamps are documented for English and Spanish only. Rime's own framing: word timestamps "keep its transcript aligned with what the caller actually heard" ([Rime LiveKit page](https://www.rime.ai/resources/livekit-integration)).

### Other repositories worth borrowing from

| Repo | Stars | Borrow |
|---|---|---|
| [AVA for Asterisk](https://github.com/hkjarral/AVA-AI-Voice-Agent-for-Asterisk) | 1.2k | Barge-in "quarantines" late LLM/TTS work and removes the interrupted exchange from weak-model history; gating tokens per queued audio; `post_tts_end_protection_ms` 350 ms self-echo guard; `provider_grace_ms` 500 ms ([architecture doc](https://github.com/hkjarral/AVA-AI-Voice-Agent-for-Asterisk/blob/main/docs/contributing/architecture-deep-dive.md)) |
| [FireRedChat](https://github.com/FireRedTeam/FireRedChat) | 587 | Personalised VAD so only the enrolled speaker can barge in ([paper](https://arxiv.org/pdf/2509.06502)) |
| [qwen-audio-agent](https://github.com/QwenAudio/qwen-audio-agent) | 2.4k | Foreground/background split: answer immediately, delegate slow work, surface when idle |
| [hermes-agent PR #74223](https://github.com/NousResearch/hermes-agent/pull/74223) | — | One turn listener armed at submit, disarmed only after TTS finishes; noise floor captured at turn start; windowed-majority trigger (≥80 % of 300 ms) so intra-word dips do not reset detection; pre-roll capture keeps the first syllable |
| [playclock](https://github.com/laconhub/playclock) | 1 | Server-side playback timeline reconstructing which chunk was playing at any instant without client callbacks |
| [saa-sdk](https://github.com/attenlabs/saa-sdk) | 120 | Addressee detection before STT ("was this directed at the agent?"), 0.86 F1 audio-only, LiveKit client |
| [voiceloop](https://github.com/todoforai/voiceloop) | — | Barge-in on transcribed words rather than mic energy |
| [bargekit](https://github.com/rogerchappel/bargekit) | — | Deterministic level-driven barge-in state engine with synthetic fixtures for tuning |
| [omnistream](https://github.com/huzjie/omnistream) | — | Hash-chained audit log plus deterministic record/replay |
| [walkie-talkie](https://github.com/lilyzhng/walkie-talkie) | — | OpenAI Voice Hack Night: sub-230 ms, mid-sentence pivots |

### Backchannel detection

Deepgram's guide uses a seven-token list (affirmative `mhmm`, `uh-huh` hold; negative `mm-mm`, `uh-uh`, `nuh-uh` yield) with `filler_words=true`, a 2 s continuation window on word timestamps, and logs `{agent_speaking, transcript, decision, caller_next_action}` to compute a false-interruption rate ([Deepgram guide](https://deepgram.com/learn/backchannels-vs-interruptions-voice-agents)). Deepgram Flux exposes `StartOfTurn`, `EagerEndOfTurn`, `TurnResumed` ("signals when to cancel a draft response") and `turn_index`, a free STT-side epoch ([Flux state](https://developers.deepgram.com/docs/flux/state); [LiveKit Flux](https://docs.livekit.io/agents/models/stt/plugins/deepgram/)).

## 2. Hackathon precedents

### Voice-agent hackathon winners 2025 to 2026

| Event | Winner / notable | What judges rewarded | Source |
|---|---|---|---|
| SF Voice Agent Hackathon (AssemblyAI × LiveKit × Rime), Sep 2025 | Voxy (grand), Podweaver (most technical, 250 ms ad-insertion timing); Pathfinder, Scam Fighters, True Voice non-winners | "The platform just works"; timing precision. No Rime word timestamps shown by anyone | [AssemblyAI](https://www.assemblyai.com/blog/voice-agent-hackathon-sept-19) |
| ElevenLabs Worldwide 2025 | GibberLink (global), DeepSky airspace safety (Warsaw), Pep (online) | One unforgettable demo moment; DeepSky's <3 s alert prioritisation | [ElevenLabs](https://elevenlabs.io/blog/announcing-the-winners-of-the-elevenlabs-worldwide-hackathon); [DeepSky](https://devpost.com/software/deepsky) |
| AssemblyAI Voice Agents Challenge 2025 | Hogwarts Spell Caster (real-time, sub-300 ms), AI✧Debate, Wynnie | A named latency number; a finalist was called out for not using the streaming endpoint | [AssemblyAI](https://www.assemblyai.com/blog/these-7-voice-ai-projects-just-blew-us-away) |
| Vapi Build Challenge 2025 | FROSTai hands-free field techs, Candling triage | Voice that "completes a job" | [Vapi](https://vapi.ai/blog/meet-the-winners-of-the-vapi-build-challenge-2025) |
| Gemini Live Agent Challenge (1,536 entries) | ORION surgical co-pilot (grand), drone-copilot | Hands-free necessity; "latency, interruption handling, barge-in matter"; post-action verbal confirmation | [Google](https://cloud.google.com/blog/topics/developers-practitioners/winners-and-highlights-of-the-gemini-live-agent-challenge); [ORION](https://devpost.com/software/orion-operating-room-intelligent-orchestration-node); [drone-copilot](https://devpost.com/software/drone-copilot) |
| ElevenHacks 2026 (BALLHARD) | "Sub-300 ms barge-in latency measured from VAD rising edge to TTS halt" | A metric with its measurement definition (page partially verified, 403) | [ElevenHacks](https://hacks.elevenlabs.io/hackathons/9) |
| OpenAI Voice Hack Night, May 2026 | Surgical Triage, Voice Arena, Coval | PHI firewall so raw tool output never reaches the model; Coval showed "interruption rate analysis" | [Cerebral Valley](https://cerebralvalley.ai/e/openai-voice-hack-night/hackathon/gallery) |
| UC Berkeley AI Hackathon 2024 | Dispatch AI 911 copilot | "The AI never closes the loop"; live synced transcript | [Devpost](https://devpost.com/software/dispatch-ai) |
| YC Voice Agents Hackathon, May 2026 | winners not found | Starter: [pipecat yc starter](https://github.com/pipecat-ai/yc-voice-agents-hackathon) with Cekura auto-generated test scenarios | [YC](https://events.ycombinator.com/voice-agents-hackathon26) |

### Clinical and verification-first projects

- **ORION**: 8 sub-agents including a Handoff_Agent (SBAR), wake-word filtering, argument whitelists, "clinical values only from tools", 4 s tool-call dedup cache, timestamped medicolegal event log. No latency or interruption evidence ([Devpost](https://devpost.com/software/orion-operating-room-intelligent-orchestration-node)).
- **Code Blue Co-pilot** (Out-Of-Pocket 2025): cardiac-arrest recorder with timed verbal reminders ([OOP](https://www.outofpocket.health/p/oops-2025-healthcare-ai-hackathon-projects)).
- **Second Voice** (OpenAI Build Week 1st): nothing spoken without explicit confirmation ([Devpost](https://devpost.com/software/second-voice-uk1peq)).
- **VoiceClaim Auditor** (NativeBuilder 2nd): live speech split into atomic assertions with graded labels ([lablab](https://lablab.ai/ai-hackathons/nativebuilder-build-without-limits/3-musketeers/voiceclaim-auditor-real-time-claim-verification); [repo](https://github.com/hamza08003/Truth-Lens)).
- **AgentWard**: allergen guardrail across 11 drug classes, human-in-the-loop gate, an Observer agent auditing every output ([lablab](https://lablab.ai/ai-hackathons/band-of-agents-hackathon/medchain/agentward-multi-agent-clinical-command-console)).
- **Emi** (NexHacks): SHA-256 hash of the intake record as tamper evidence ([Devpost](https://devpost.com/software/health-nfedwy)).
- **SOFIA** (Amazon Nova): completeness state machine for intake ([Devpost](https://devpost.com/software/sophia-voice-first-ai-triage-assistant)).
- **FlowPilot** (Rime user): "preventing overlapping voice alerts required a queuing system" ([Devpost](https://devpost.com/software/flow-pilot)).
- Rime's own Devpost prize tiers: "Best real-world application", "Most advanced use of Rime API", "Most fun/creative" ([GTC hackathon](https://ai-agents-hackathon-gtc.devpost.com/)).

### What judges consistently reward

1. Voice is necessary, not decorative (hands and eyes occupied).
2. One concrete hard-voice number with its measurement definition.
3. The human stays the authority; safety is structural, not prompted.
4. Visible use of the sponsor's hard feature.
5. One unforgettable demo moment.
6. Candour about limitations plus open artefacts.

### Gaps nobody has filled

No open-source EMS or paramedic handover voice app. No project uses Rime word timestamps. No project publishes degraded-audio results. No hackathon winner demonstrated interruption or read-back mechanics. Closest academic work (SCOPE ATC readback monitor, VOICE stroke agent) released no code ([SCOPE](https://arxiv.org/html/2605.29543v1); [VOICE](https://arxiv.org/abs/2507.22898)).

## 3. Clinical handover structure and vocabulary

### Slot lists

| Mnemonic | Slots | Source |
|---|---|---|
| IMIST-AMBO (ambulance to ED) | Identify; Mechanism; Injuries; Signs; Treatment; Allergies; Medications; Background; Other | [AHRQ PSNet](https://psnet.ahrq.gov/node/41559/psn-pdf) |
| ATMIST (UK JRCALC) | Age; Time; Mechanism; Injuries; Signs; Treatment. One speaker, 60 s, questions held to the end | [RCEM Learning](https://www.rcemlearning.co.uk/modules/handover-skills-to-enhancing-the-phem-em-interface/lessons/handover-tools/topic/handover-tools/) |
| ATMIST-AMBO (BCEHS) | ATMIST plus Allergies, Medications, Background, Other | [BCEHS](https://handbook.bcehs.ca/clinical-practice-guidelines/a-general/a03-clinical-handover-communication/) |
| I-PASS (inpatient) | Illness severity; Patient summary; Action list; Situation awareness; Synthesis by receiver | [NEJM](https://www.nejm.org/doi/full/10.1056/NEJMsa1405556); [AHRQ](https://www.ahrq.gov/teamstepps-program/curriculum/communication/tools/ipass.html) |
| DENIM (10 essential trauma variables) | Gender; Age; Mechanism; Injuries; Airway; Breathing; Circulation; Disability; Treatment; History. Rejects "ABCD stable" as too vague | [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5504644/) |

### What goes wrong, with numbers

- ED staff retained only 56.6 % of verbal handover content; imposing structure alone did not improve recall ([Talbot & Bleetman](https://pmc.ncbi.nlm.nih.gov/articles/PMC2660073/)).
- EMS to trauma team: airway communicated 22 %, medications 59 %, allergies 54 %; 35 % of trauma-team questions asked for information already given ([CJEM](https://www.cambridge.org/core/journals/canadian-journal-of-emergency-medicine/article/clinical-handover-from-emergency-medical-services-to-the-trauma-team-a-gap-analysis/5FEB0BDA1D3140E419310879BA37C86B)).
- India prehospital signout, 1,163 transfers: 8.6 % complete; allergies 39.7 %, medications 39.0 % ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7047340/)).
- 74 % of hypoxia and 42 % of hypotension not communicated across 721 handovers ([WestJEM](https://westjem.com/articles/prospective-observational-multisite-study-of-handover-in-the-emergency-department-theory-versus-practice.html)).
- I-PASS cut medical errors from 33.8 to 18.3 per 100 admissions without lengthening handoffs ([NEJM](https://www.nejm.org/doi/full/10.1056/NEJMsa1405556)). Handoff miscommunication contributes to about 80 % of serious errors ([NCBI](https://www.ncbi.nlm.nih.gov/books/NBK549899/)).

### Read-back rules

- Joint Commission: write down, then read back ([ISMP](https://www.ismp.org/sites/default/files/attachments/2018-03/NurseAdviseERR201706.pdf)).
- NCC MERP: numbers stated twice, digit by digit ("fifty milligrams, five-zero milligrams"); drug name spelled, brand and generic; phonetic alphabet; no abbreviations ([NCC MERP](https://www.nccmerp.org/recommendations-reduce-medication-errors-associated-verbal-medication-orders-and-prescriptions)). Fifteen/fifty and sixteen/sixty are the classic confusions ([PA Patient Safety](https://patientsafety.pa.gov/ADVISORIES/Pages/200606_01b.aspx)).
- Readback/hearback is "the fundamental mechanism of closed loop communication" ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1549374104300535)).
- SCOPE's readback taxonomy for air traffic control: Correct / Incorrect (safety-critical element changed) / Incomplete (missing element) / Non-standard (right content, wrong phraseology) / Unknown; metrics Slot F1 and Semantic Frame Accuracy ([arXiv](https://arxiv.org/html/2605.29543v1)).

### Medical vocabulary for STT and TTS

- "Metoprolol succinate almost never transcribed correctly"; numbers, negation and laterality highest risk ([scoping review](https://pmc.ncbi.nlm.nih.gov/articles/PMC13127238/)); "4 to 5" becomes "45" ([arXiv](https://arxiv.org/pdf/2602.00981)); patient-side WER 53 % vs agent 1.8 % in MMedFD ([arXiv](https://arxiv.org/html/2509.19817)).
- Deepgram Keyterm Prompting on Nova-3, Nova-3 Medical and Flux, up to 500 tokens ([Deepgram](https://developers.deepgram.com/docs/keyterm)).
- ISMP Confused Drug Names 2023 ([PDF](https://www.ismp.org/system/files/resources/2023-10/ISMP_ConfusedDrugNames_2023.pdf)); FDA/ISMP Tall Man letters ([PDF](https://online.ecri.org/hubfs/ISMP/Resources/ISMP_Look-Alike_Tallman_Letters.pdf)); openFDA NDC download ([openFDA](https://open.fda.gov/data/downloads/)).
- Rime custom pronunciation `{phonetic}` works on Mist v2, not Coda ([Rime docs](https://docs.rime.ai/docs/custom-pronunciation)).

## 4. Evaluation and observability tools

| Tool | What it measures | Reuse in Hearback | Source |
|---|---|---|---|
| quantumCF barge-in tests | `did_yield`, `time_to_yield_sec`, `talk_over_sec` over 8 scenarios (hard interruption, backchannel, filler start, correction, 8 kHz telephony, double talk, echo bleed, rapid turns); `--fail-on-regression`; LiveKit adapter | Adopt scenario set, add "correction mid-readback" | [GitHub](https://github.com/quantumCF/voice-agent-barge-in-tests) |
| tvbench | Opening latency, frame pacing, barge-in responsiveness (how long the agent keeps talking after the caller starts) | Metric definition for T1 | [GitHub](https://github.com/ictinnovations/telephony-voice-agent-benchmark) |
| Full-Duplex-Bench | Stop latency, response latency, categorical behaviour under overlap (interruption, backchannel, side conversation, ambient speech) | Fixed-offset overlap injection method | [GitHub](https://github.com/DanielLin94144/Full-Duplex-Bench); [paper](https://arxiv.org/abs/2507.23159) |
| EchoChain | State-update reasoning under interruption; no realtime voice model exceeded 50 %; failure modes contextual inertia, interruption amnesia, objective displacement | Our baseline to beat, and the fixture shape | [arXiv](https://arxiv.org/abs/2604.16456) |
| Hamming runbook | Eight metrics: false interruption rate, missed interruption rate, resume success, repeated user speech, silence after interruption, task completion after interruption, escalation, P95 turn latency; event taxonomy `interruption.candidate_detected / decision_made / recovered / false_positive` with playback position and policy version; required scenarios include "true correction at 1 s" and "non-interruptible legal disclosure" | Event names and metric set for the log and HUD | [Hamming](https://hamming.ai/resources/voice-agent-interruption-handling-runbook); [metrics guide](https://hamming.ai/resources/voice-agent-evaluation-metrics-guide) |
| Coval methodology | TTFA includes leading silence; jiwer 4.0.0 with whisper normaliser; −20 dBFS RMS; SHA-256 fixtures; p50/p95/p99 never mean | Evidence file conventions | [methodology](https://github.com/coval-ai/benchmarks/blob/main/docs/methodology.md); [latency guide](https://www.coval.ai/blog/how-to-measure-voice-ai-latency-the-complete-guide/) |
| openbenchmarks voice-agent-latency | TTFAB (caller stops → agent audio starts), median and tail ratio, deterministic offline analyser | Report tail ratio not just p50 | [GitHub](https://github.com/openbenchmarks-labs/voice-agent-latency) |
| langwatch/scenario | Multi-turn simulation and judge with noise and interruption simulation, latency percentiles | Optional CI harness | [GitHub](https://github.com/langwatch/scenario) |
| τ-Voice (tau2-bench) | Task completion under accents, noise, natural interruptions | Method reference | [README](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/voice/README.md) |
| LiveKit native tests | `session.run()` with `.judge()` on messages and tool calls | Unit tests for the state machine | [docs](https://docs.livekit.io/agents/start/testing/) |
| HumDial / IHBench | Interruption vs rejection taxonomy; recovery quality as a distinct axis | Report recovery separately from stop latency | [HumDial](https://arxiv.org/html/2604.21406v2); [IHBench](https://arxiv.org/abs/2606.19595) |

Also useful: Picovoice names "stale responses after barge-in" as a top failure mode ([Picovoice](https://picovoice.ai/guide/voice-agents/common-failure-modes/)); SignalWire's "stale response" essay states the principle of validating "is this response still valid right now?" before playback ([SignalWire](https://signalwire.com/blogs/developers/the-stale-response)); OpenAI Realtime admits it cannot precisely align transcript and audio for truncation ([OpenAI](https://developers.openai.com/api/docs/guides/realtime-conversations)).

## Key takeaways

- Lean on LiveKit's `TimedString` and truncated-on-interrupt transcript; the novel work is mapping heard words to fact IDs, not measuring playout.
- Make the epoch concrete on the wire: epoch = Rime `contextId` = Deepgram Flux `turn_index`; send ws3 `clear` ourselves because the plugin does not.
- Classify every readback with the SCOPE taxonomy and report Slot F1; this is a published, citable measure nobody in the hackathon space uses.
- Uninterruptible critical readbacks with buffered input, and correction words as a fast-yield class, come straight from Hamming's required scenarios.
- Ship a barge-in regression suite and publish the metric with its definition ("VAD rising edge to TTS halt") because that is what past judges rewarded.
- Use IMIST-AMBO slots and the omission statistics to justify the critical tier: allergies, medications, airway and hypoxia are the most-dropped facts.
- NCC MERP grammar decides how Rime speaks numbers and drug names; the ISMP list decides when to force `spell()`.
- Quarantine late output and rewrite history on interruption (AVA pattern) so the correction turn stays focused and tools do not double-execute.
- Add a tamper-evident hash of the relayed record and an observer gate; both are cheap and match what verification-first hackathon projects were rewarded for.

## Sources

Framework and API: LiveKit Rime plugin source, LiveKit synchronizer and agent_activity source, LiveKit turns, speech, text, adaptive interruption, testing and Deepgram plugin docs, LiveKit async-tools and adaptive-interruption blogs, LiveKit issues #3702, #4183, #4560, #5038, #5092, python-agents-examples, rime-livekit-agents, rime-multilingual-demo, voice-agent-hackathon template, Pipecat tts_service and Rime service references, Pipecat turn strategies, Pipecat v1.0.0 and v0.0.104 release notes, Rime ws3 reference, Rime streaming docs, Rime custom pronunciation, Rime LiveKit page, Deepgram backchannel guide, Deepgram Flux state and eager EOT docs, Deepgram keyterm docs.

Repositories: AVA for Asterisk (and architecture doc), FireRedChat (and paper), qwen-audio-agent, hermes-agent PR #74223, playclock, saa-sdk, voiceloop, bargekit, omnistream, full_duplex_assistant, walkie-talkie, Truth-Lens, AI-ATC, readback, Healthcare-AI-Voice-agent, primock57, Hogwards-Legacy-Cast, AIDebate.

Hackathons: AssemblyAI Sep-19 blog, AssemblyAI seven projects blog, ElevenLabs winners blog, ElevenHacks page, Vapi Build Challenge blog, Google Gemini Live Agent Challenge blog, Cerebral Valley OpenAI Voice Hack Night gallery, Out-Of-Pocket 2025, YC voice hackathon page and starter, Devpost pages for ORION, Dispatch AI, DeepSky, drone-copilot, Second Voice, SOFIA, Emi, FlowPilot, Fireflai, NagarDrishti, lablab pages for VoiceClaim Auditor, Discharge Buddy, AgentWard, Rime GTC and MCP hackathon pages.

Clinical: AHRQ PSNet IMIST-AMBO, RCEM Learning ATMIST, BCEHS handover guideline, NEJM I-PASS, AHRQ I-PASS, DENIM consensus, Talbot & Bleetman, CJEM gap analysis, India prehospital signout study, WestJEM handover study, NCBI handoff chapter, ISMP read-back advisory, NCC MERP recommendations, PA Patient Safety advisory, ScienceDirect closed-loop paper, SCOPE paper, VOICE paper, medical STT scoping review, MMedFD, "4 to 5" paper, ISMP confused drug names, Tall Man letters, openFDA.

Evaluation: quantumCF barge-in tests, tvbench, Full-Duplex-Bench and paper, EchoChain, HumDial, IHBench, Hamming runbook and metrics guide, Coval methodology, Coval latency guide, coval-ai/benchmarks, openbenchmarks voice-agent-latency, langwatch/scenario, voicetest, tau2-bench voice README and paper, Picovoice failure modes, SignalWire stale response, OpenAI Realtime docs, Artificial Analysis TTS methodology, TTS intelligibility paper.

## Methodology

Three parallel agents ran roughly 60 web searches and 97 page fetches on 2026-09-08 covering: (1) GitHub voice-agent repositories, interruption mechanics, evaluation tooling, readback and epoch patterns; (2) Devpost, lablab, Cerebral Valley and vendor hackathon galleries; (3) clinical handover structure, medical vocabulary and evaluation methodology. Star counts are as of the fetch date. Unverified items: no public repos exist for Voxy, Podweaver, Pathfinder, Scam Fighters, True Voice or DeepSky; YC May-2026 winners not found; the ElevenHacks page returned 403 so BALLHARD's claim is partially verified; Coda `timestamps` on ws3 is documented for English and Spanish and should be confirmed live before T4 depends on it; "epoch fencing" is not a named pattern in the literature.
