"""Live Rime measurements: time-to-silence, time-to-first-audio, and rendered readback clips.

These are the parts of the evidence that cannot be simulated. Everything here needs
`RIME_API_KEY` and reaches the network, so it runs only under `run_evidence.py --live` and is
reported as NOT RUN otherwise rather than being estimated.

Two honesty notes carried into the report:

* Time-to-silence is measured at the socket — from sending `{"operation": "clear"}` to the last
  audio frame Rime sends for that context. The listener's ear is further away by whatever the
  client's playout buffer holds, so this is a lower bound on what a microphone would record, and
  the report says so.
* Time-to-first-audio is measured from the last text frame to the first `chunk`, with cold and
  warm connections kept in separate samples because pooling changes the number by more than
  anything else in the path.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx

from agent.config import RimeConfig

HTTP_TTS_URL = "https://users.rime.ai/v1/rime-tts"
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
SILENCE_WINDOW_S = 0.75


class ProbeError(RuntimeError):
    """Raised when a live probe cannot run at all, as distinct from measuring a bad number."""


def _ws_url(config: RimeConfig, lang: str = "en", inline_speed_alpha: float | None = None) -> str:
    params = {
        "speaker": config.speaker_for(lang),
        "modelId": config.model,
        "audioFormat": "pcm",
        "samplingRate": config.sample_rate,
        "lang": config.lang_code(lang),
        "speedAlpha": config.speed_alpha,
    }
    if inline_speed_alpha is not None:
        params["inlineSpeedAlpha"] = inline_speed_alpha
    return f"{config.ws_base_url}/ws3?{urlencode(params)}"


def _connect(config: RimeConfig, lang: str, inline_speed_alpha: float | None = None):
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ProbeError("the websockets package is not installed: uv pip install websockets") from exc
    return websockets.connect(
        _ws_url(config, lang, inline_speed_alpha),
        additional_headers={"Authorization": f"Bearer {config.api_key}"},
    )


@dataclass(frozen=True)
class SilenceRun:
    """One barge-in: when the clear went out, and when Rime actually stopped sending."""

    context_id: str
    spoke_ms: float
    time_to_silence_ms: float
    frames_after_clear: int


async def time_to_silence(
    config: RimeConfig, text: str, runs: int = 20, speak_ms: int = 800, lang: str = "en"
) -> list[SilenceRun]:
    """Speak, cut in after `speak_ms`, and time how long audio keeps arriving."""
    results: list[SilenceRun] = []
    for index in range(runs):
        context_id = f"hb-evidence-{index}"
        async with _connect(config, lang) as ws:
            await ws.send(json.dumps({"text": text + " ", "contextId": context_id}))
            await ws.send(json.dumps({"operation": "flush", "contextId": context_id}))

            first_chunk_at = await _await_first_chunk(ws)
            remaining = speak_ms / 1000 - (time.perf_counter() - first_chunk_at)
            if remaining > 0:
                await asyncio.sleep(remaining)

            cleared_at = time.perf_counter()
            await ws.send(json.dumps({"operation": "clear", "contextId": context_id}))
            last_at, frames = await _drain_until_silent(ws, cleared_at)

            results.append(
                SilenceRun(
                    context_id=context_id,
                    spoke_ms=round((cleared_at - first_chunk_at) * 1000, 1),
                    time_to_silence_ms=round((last_at - cleared_at) * 1000, 1),
                    frames_after_clear=frames,
                )
            )
    return results


async def _await_first_chunk(ws) -> float:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
        if message.get("type") == "chunk":
            return time.perf_counter()
        if message.get("type") == "error":
            raise ProbeError(f"Rime returned an error: {message.get('message')}")
        if message.get("type") == "done":
            raise ProbeError("synthesis finished before any audio arrived")


async def _drain_until_silent(ws, cleared_at: float) -> tuple[float, int]:
    """Keep reading until Rime goes quiet for SILENCE_WINDOW_S or says it is done."""
    last_at = cleared_at
    frames = 0
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=SILENCE_WINDOW_S)
        except TimeoutError:
            return last_at, frames
        message = json.loads(raw)
        kind = message.get("type")
        if kind == "chunk":
            last_at = time.perf_counter()
            frames += 1
        elif kind in {"done", "error"}:
            return last_at, frames


async def time_to_first_audio(
    config: RimeConfig, text: str, runs: int = 25, lang: str = "en"
) -> dict[str, list[float]]:
    """Cold (a fresh socket each time) and warm (one socket reused) kept apart."""
    cold: list[float] = []
    for _ in range(runs):
        async with _connect(config, lang) as ws:
            cold.append(await _one_ttfa(ws, text, "cold"))

    warm: list[float] = []
    async with _connect(config, lang) as ws:
        for index in range(runs):
            warm.append(await _one_ttfa(ws, text, f"warm-{index}"))
    return {"cold_ms": cold, "warm_ms": warm}


async def _one_ttfa(ws, text: str, context_id: str) -> float:
    sent_at = time.perf_counter()
    await ws.send(json.dumps({"text": text + " ", "contextId": context_id}))
    await ws.send(json.dumps({"operation": "flush", "contextId": context_id}))
    first_at = await _await_first_chunk(ws)
    await _drain_until_silent(ws, first_at)
    return round((first_at - sent_at) * 1000, 1)


async def render_clip(
    config: RimeConfig,
    text: str,
    destination: Path,
    lang: str = "en",
    inline_speed_alpha: float | None = None,
) -> Path:
    """Render one sentence to a committed WAV over the HTTP endpoint (1,000 character limit)."""
    if len(text) > 1000:
        raise ProbeError("Rime's HTTP endpoint takes at most 1,000 characters")
    payload = {
        "text": text,
        "speaker": config.speaker_for(lang),
        "modelId": config.model,
        "lang": config.lang_code(lang),
        "samplingRate": config.sample_rate,
        "speedAlpha": config.speed_alpha,
    }
    if inline_speed_alpha is not None:
        payload["inlineSpeedAlpha"] = inline_speed_alpha
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            HTTP_TTS_URL,
            headers={"Authorization": f"Bearer {config.api_key}", "Accept": "audio/wav"},
            json=payload,
        )
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
    return destination


async def transcribe(api_key: str, wav: bytes, model: str = "nova-3") -> str:
    """Re-transcribe a rendered clip so the readback can be scored on what a recogniser hears."""
    async with httpx.AsyncClient(timeout=60) as http:
        response = await http.post(
            DEEPGRAM_URL,
            params={"model": model, "smart_format": "false", "numerals": "true"},
            headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"},
            content=wav,
        )
        response.raise_for_status()
        body = response.json()
    alternatives = body["results"]["channels"][0]["alternatives"]
    return alternatives[0]["transcript"] if alternatives else ""


# --------------------------------------------------------------------------------------
# digit error rate
# --------------------------------------------------------------------------------------

_UNITS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}


def digits_of(text: str) -> str:
    """Every digit a listener would write down, in order, however it was spoken.

    'ninety over sixty' and '90/60' both reduce to '9060', so a readback can be scored on the
    numbers that matter rather than on the words wrapped around them.
    """
    out: list[str] = []
    tokens = [t.strip(".,;:?!()[]").lower() for t in text.replace("/", " ").split()]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isdigit():
            out.append(token)
        elif token.replace(".", "", 1).isdigit():
            out.append(token.replace(".", ""))
        elif token in _TENS:
            value = _TENS[token]
            nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
            if nxt in _UNITS and len(_UNITS[nxt]) == 1 and _UNITS[nxt] != "0":
                value += int(_UNITS[nxt])
                index += 1
            out.append(str(value))
        elif token in _UNITS:
            out.append(_UNITS[token])
        elif token == "hundred" and out:
            out[-1] = str(int(out[-1]) * 100)
        index += 1
    return "".join(out)


def digit_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein distance over the digit sequences, normalised by the reference length."""
    ref, hyp = digits_of(reference), digits_of(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        current = [i]
        for j, h in enumerate(hyp, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return round(previous[-1] / len(ref), 4)
