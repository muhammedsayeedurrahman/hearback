"""Check the Rime voice configuration before the demo, not during it.

    python scripts/rime_preflight.py
    python scripts/rime_preflight.py --probe   # also open ws3 and ask for one sentence

Two things go wrong quietly with Rime and are worth catching early: omitting `modelId` serves
Mist v3 instead of Coda, which has no Hindi, and a speaker name can exist without being available
for the model or language you asked for. `--probe` additionally answers the open question in the
plan, which is whether Coda emits word timestamps over ws3 at all: the heard-state ledger falls
back to an estimate if it does not, and the fallback is a word less accurate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from urllib.parse import urlencode

import httpx

from agent.config import ConfigError, RimeConfig, check_catalog, load_rime_config

PROBE_TEXT = "Confirming. morphine, [10] milligrams, spell(10) milligrams."


async def fetch_catalog(config: RimeConfig) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(config.catalog_url)
        response.raise_for_status()
        body = response.json()
    if isinstance(body, dict):
        return [v for values in body.values() if isinstance(values, list) for v in values]
    return body


async def probe_ws3(config: RimeConfig, lang: str) -> dict[str, object]:
    """Synthesise one sentence and report whether chunks and timestamps come back."""
    params = {
        "speaker": config.speaker_for(lang),
        "modelId": config.model,
        "audioFormat": "pcm",
        "samplingRate": config.sample_rate,
        "lang": config.lang_code(lang),
        "speedAlpha": config.speed_alpha,
        "inlineSpeedAlpha": config.inline_speed_alpha,
    }
    url = f"{config.ws_base_url}/ws3?{urlencode(params)}"
    seen = {"chunks": 0, "timestamps": 0, "words": [], "error": None}
    try:
        import websockets

        async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {config.api_key}"}) as ws:
            await ws.send(json.dumps({"text": PROBE_TEXT + " ", "contextId": "preflight"}))
            await ws.send(json.dumps({"operation": "flush", "contextId": "preflight"}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=25))
                kind = message.get("type")
                if kind == "chunk":
                    seen["chunks"] += 1
                elif kind == "timestamps":
                    seen["timestamps"] += 1
                    seen["words"] = (message.get("word_timestamps") or {}).get("words", [])
                elif kind in {"done", "error"}:
                    if kind == "error":
                        seen["error"] = message.get("message")
                    break
            await ws.send(json.dumps({"operation": "clear", "contextId": "preflight"}))
    except ImportError:
        seen["error"] = "the websockets package is not installed; run: uv pip install websockets"
    except Exception as exc:
        seen["error"] = f"{type(exc).__name__}: {exc}"
    return seen


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="open ws3 and synthesise one sentence")
    parser.add_argument("--langs", nargs="*", default=["en", "hi"])
    args = parser.parse_args()

    try:
        config = load_rime_config()
    except ConfigError as exc:
        print(f"FAIL  {exc}")
        return 1

    print(f"model      {config.model}")
    print(f"ws base    {config.ws_base_url}   (the plugin appends /ws3)")
    print(f"sample     {config.sample_rate} Hz pcm, speedAlpha {config.speed_alpha}")

    failures = 0
    catalog = await fetch_catalog(config)
    print(f"catalog    {len(catalog)} voices from {config.catalog_url}")
    for lang in args.langs:
        ok, message = check_catalog(catalog, config, lang)
        print(f"  {lang}: {'OK  ' if ok else 'FAIL'} {message}")
        failures += 0 if ok else 1

    if args.probe:
        for lang in args.langs:
            result = await probe_ws3(config, lang)
            status = "FAIL" if result["error"] or not result["chunks"] else "OK  "
            print(f"  ws3 {lang}: {status} chunks={result['chunks']} timestamp frames={result['timestamps']}")
            if result["words"]:
                print(f"           first words: {result['words'][:6]}")
            if not result["timestamps"] and not result["error"]:
                print("           no timestamps: the ledger will fall back to a rate estimate")
            if result["error"]:
                print(f"           {result['error']}")
                failures += 1

    print("\npreflight " + ("passed" if not failures else f"failed with {failures} problem(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
