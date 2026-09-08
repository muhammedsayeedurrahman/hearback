# Facts verified against live sources on 2026-09-08

Everything below was fetched from docs.rime.ai, users.rime.ai, docs.livekit.io or the
LiveKit GitHub tracker on this date. Re-verify before submission; the challenge requires the
catalog at submission time.

## Rime models

| Model ID | Released | Languages | Notes |
|---|---|---|---|
| `coda` | May 2026 | en, ar, fr, de, hi, it, ja, pt, es | Flagship. Word-level timestamps on ws3. No SSML, no inline phonemes; `spell()` only. Native 24 kHz. Default speaker in LiveKit plugin: `lyra`. |
| `mistv3` | Mar 2026 | en, fr, de, es | Fastest (37 ms P50 TTFA in Rime's own benchmark). No Hindi. **Served if `modelId` is omitted.** |
| `mistv2` | Feb 2025 | en, fr, de, es | Only model with `phonemizeBetweenBrackets`. `speedAlpha` inverted (<1.0 = faster). |
| `arcana` | – | – | Sunset on cloud (requests routed to Coda since 2026-08-15). Do not build on it. |

## Live catalog (users.rime.ai/data/voices/all-v2.json), fetched today

- Top-level keys: `mist`, `mistv2`, `arcana`, `mistv3`, `coda`.
- `coda` speakers by language: eng 151, jpn 13, spa 40, por 11, ger 9, fra 8, ara 7, **hin 3**, ita 3.
- `coda/hin` speakers: `hin`, `nadi`, `taru`.
- `coda/eng` first entries: adeline, albion, alfhild, alma, alpine, amarante, ana, andromeda.
- `mistv3/eng` first entries: alexis, alpine, astra, bayou, blaze, blossom, boulder, breeze.
- Demographics endpoint: `users.rime.ai/data/voices/voice_details.json` (fields renamed Nov 2025: `modelId`, `speaker`, `dialect`).

## Rime endpoints

| Purpose | Endpoint |
|---|---|
| HTTP synthesis / streaming | `POST https://users.rime.ai/v1/rime-tts`, `Accept: audio/mpeg | audio/L16 | audio/pcm | audio/wav | audio/mulaw | audio/ogg` |
| WebSocket, plain text (Mist v2) | `wss://users-ws.rime.ai/ws?speaker=..&modelId=mistv2&audioFormat=..`; commands `<CLEAR>`, `<FLUSH>`, `<EOS>` |
| WebSocket JSON (all models) | `wss://users-ws.rime.ai/ws3`; send `{"text": ..}`, `{"operation": "clear"}`, `{"operation": "eos"}`; receive `chunk` (base64 audio), `timestamps` (word-level), `done`, `error`; context IDs for selective cancel |
| SSE (Mist v2 only) | `POST /v1/rime-tts` with `Accept: text/event-stream` |
| Text normalisation preview | `POST https://optimize.rime.ai/textnorm` |
| Out-of-vocabulary check | `POST https://users.rime.ai/oov` |

Auth: `Authorization: Bearer $RIME_API_KEY`. 1 000 characters per request. No India/APAC regional endpoint documented.

## Request parameters

`speaker`, `text`, `modelId`, `lang` (BCP-47 `en`/`hi`, legacy `eng`/`hin` accepted), `samplingRate` (4000–44100, default 22050), `speedAlpha` (Coda/Mist v3: >1.0 faster), `timeScaleFactor` (Coda/Mist v3, HTTP only), `inlineSpeedAlpha` (comma list applied to `[bracketed]` words), `pauseBetweenBrackets` (`<200>` ms, Mist family), `phonemizeBetweenBrackets` (Mist v2 only), `noTextNormalization` (Mist family), `segment` (`bySentence` default | `immediate` | `never`), `spell()` inline.

## Writing for the ear (Brooke Larson, Rime)

Contractions; start with And/But/So; drop formal connectors; sprinkle single disfluencies (two "um"s is a bug); punctuation is prosody (comma short pause, period falling, question rising, ellipsis hesitant); sentences under 25 words, ideally under 15; show don't tell; no dashes inside numeric IDs; `spell()` for codes and SKUs but not phone numbers; full drop-in system prompt is published at docs.rime.ai/docs/prompting.

## LiveKit Agents

- Install: `uv add "livekit-agents[rime]~=1.5"`; Node `@livekit/agents-plugin-rime@1.x`. Env var `RIME_API_KEY`.
- `rime.TTS(model="coda", speaker="lyra", audio_format="pcm", sample_rate=16000, speed_alpha=1.0, use_websocket=True, segment="bySentence")`. Coda ignores `reduce_latency`, `pause_between_brackets`, `phonemize_between_brackets`.
- Interruption: `interruption.mode="adaptive"` (default on Cloud; CNN model that rejects backchannels) or `"vad"`; `resume_false_interruption`, `false_interruption_timeout`; `session.interrupt()`; events `user_interruption_detected`, `agent_false_interruption`.
- On interruption the framework truncates chat history to the portion the user heard (needs synchronized transcription, which ws3 word timestamps enable).
- `session.say()` / `generate_reply()` return `SpeechHandle` with `.interrupted`, `.wait_for_playout()`, `allow_interruptions`.
- Turn detection: turn-detector model (semantic) + Silero VAD; resamples to 16 kHz internally so 8 kHz telephony works. Suggested VAD silence for healthcare ~600 ms.
- Known issue livekit/agents#5038: with `resume_false_interruption=True` a response can be dropped from `chat_ctx` if audio pauses before the first frame; keep our own event log as the source of truth rather than relying on `chat_ctx`.

## Hackathon context

- DataForge 2026, KDAG IIT Kharagpur, sponsors Pathway and Rime. Prize pool ₹3,00,000. Teams ≤ 4.
- Rubric: 25 voice necessity, 25 hard voice engineering, 20 Rime integration, 20 evidence, 10 demo.
- Required artefacts: demo ≤ 5 min, repo, README with exact Rime config, `RIME_EVIDENCE.md`, `.env.example`, organiser preflight.
- Prior Rime hackathon (SF, Sep 2025) winners had a clear voice-necessary problem plus a measurable outcome.
- Rime pricing: about $0.05 per 1 000 characters for Coda; new accounts start with free Starter minutes (verify in dashboard).
