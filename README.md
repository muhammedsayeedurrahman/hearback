# Hearback

**The handover firewall.** A full-duplex voice agent for clinical handovers that tracks every
critical fact as HEARD, CORRECTED, VERIFIED or SUPERSEDED, kills stale Rime speech the instant a
clinician corrects it, records exactly which words were audibly delivered, fences obsolete tool
results, and relays only verified facts to the receiving clinician.

Built for DataForge × Pathway × Rime. Simulated data only. No diagnosis, no prescribing.

> Most voice AI summarises what was said. Hearback guarantees what was heard.

## Read first

- [PLAN.md](PLAN.md) — full analysis, idea, architecture, truth-state model, acceptance tests, ranked feature backlog, build timeline.
- [docs/research/](docs/research/) — problem statement, original 4-hour plan, deep-research brief, and facts verified against live Rime/LiveKit sources on 2026-09-08.

## Layout

```
agent/     LiveKit Agents (Python): STT, turn handling, Rime TTS, heard-state ledger
engine/    Pure-Python truth-state machine, epoch fence, conflict engine, relay gate + tests
api/       FastAPI sidecar: REST + SSE event stream
web/       Next.js dashboard: transcript, truth state, heard ledger, relay, provider badge
fixtures/  Scenario, pronunciation and barge-in offset fixtures
scripts/   rime_preflight.py, run_evidence.py, stress_barge_in.py
evidence/  Generated results, committed clips
```

## Rime configuration (judged flow)

| Field | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `lyra` (English relay); `nadi` / `taru` (Hindi relay, stretch) |
| Language | `en` (`hi` for Hindi relay) |
| Endpoint | `wss://users-ws.rime.ai/ws3` via LiveKit Rime plugin, `use_websocket=True` |
| Audio | PCM, 16 kHz |
| Transport | LiveKit WebRTC room |
| Catalog check | `https://users.rime.ai/data/voices/all-v2.json` at startup |
| Fallback | browser `speechSynthesis`, disclosed by a red provider badge and logged |

Copy `.env.example` to `.env` and fill in real keys. Never commit `.env`.

## Evidence

See `RIME_EVIDENCE.md` (written during the build) and `python scripts/run_evidence.py --all`.
