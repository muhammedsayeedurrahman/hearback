"""Epoch-stamped Rime ws3 transport (feature F10).

The stock LiveKit Rime plugin gives every stream a random `contextId` and, when the agent is
interrupted, simply drops the stream: it sends `flush` and `eos` but never
`{"operation": "clear"}`. Rime therefore keeps generating audio for a context nobody will listen
to, on a pooled connection the next sentence will reuse.

Hearback needs both halves fixed, because the epoch fence has to hold on the wire and not just in
the process:

  * `contextId` carries the epoch, so every audio frame can be traced to the utterance it answers
    and stale audio is identifiable rather than merely improbable.
  * an interruption sends `clear` for that context before the connection goes back to the pool.

`_run` is adapted from livekit-plugins-rime 1.8.0 (Apache-2.0) because the context id is a local
inside the original. Pin the plugin version: this file reaches into its internals.
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import logging
from collections.abc import Callable
from urllib.parse import urlencode

import aiohttp
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIError,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.agents.voice.io import TimedString
from livekit.plugins.rime import tts as rime_tts

logger = logging.getLogger(__name__)

WordSink = Callable[[list[tuple[str, float, float]]], None]
EpochSource = Callable[[], int]

CONTEXT_PREFIX = "hb"


def context_id_for(epoch: int, sequence: int) -> str:
    """`hb-e3-7`: readable in a Rime log, parseable back into the epoch it belongs to."""
    return f"{CONTEXT_PREFIX}-e{epoch}-{sequence}"


def epoch_of(context_id: str) -> int | None:
    """Recover the epoch from a context id, or None when it was not one of ours."""
    parts = context_id.split("-")
    if len(parts) != 3 or parts[0] != CONTEXT_PREFIX or not parts[1].startswith("e"):
        return None
    try:
        return int(parts[1][1:])
    except ValueError:
        return None


def clear_frame(context_id: str) -> str:
    """The frame the stock plugin never sends."""
    return json.dumps({"operation": "clear", "contextId": context_id})


class EpochRimeTTS(rime_tts.TTS):
    """Rime ws3 with the epoch on the wire and inline speed control for spoken numbers."""

    def __init__(
        self,
        *,
        epoch_source: EpochSource,
        on_words: WordSink | None = None,
        inline_speed_alpha: float | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._epoch_source = epoch_source
        self._on_words = on_words
        self._inline_speed_alpha = inline_speed_alpha
        self._sequence = itertools.count(1)
        self._cleared: list[str] = []

    @property
    def cleared_contexts(self) -> tuple[str, ...]:
        """Contexts explicitly cancelled at Rime. Evidence for the barge-in write-up."""
        return tuple(self._cleared)

    def next_context_id(self) -> str:
        return context_id_for(self._epoch_source(), next(self._sequence))

    def note_words(self, words: list[tuple[str, float, float]]) -> None:
        if self._on_words and words:
            self._on_words(words)

    def note_cleared(self, context_id: str) -> None:
        self._cleared.append(context_id)

    def _ws_url(self) -> str:
        url = super()._ws_url()
        if self._inline_speed_alpha is None:
            return url
        return f"{url}&{urlencode({'inlineSpeedAlpha': self._inline_speed_alpha})}"

    def stream(self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> "EpochStream":
        if not self._use_websocket:
            raise RuntimeError("Hearback requires use_websocket=True: ws3 carries the word timestamps")
        stream = EpochStream(tts=self, conn_options=conn_options)
        self._streams.add(stream)
        return stream


class EpochStream(rime_tts.SynthesizeStream):
    """One utterance, tagged with the epoch it answers and cancelled at Rime when interrupted."""

    def __init__(self, *, tts: EpochRimeTTS, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, conn_options=conn_options)
        self._tts: EpochRimeTTS = tts
        self.context_id = ""

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        request_id = utils.shortuuid()
        context_id = self._tts.next_context_id()
        self.context_id = context_id
        output_emitter.initialize(
            request_id=request_id,
            sample_rate=self._tts.sample_rate,
            num_channels=rime_tts.NUM_CHANNELS,
            mime_type="audio/pcm",
            stream=True,
        )
        output_emitter.start_segment(segment_id=context_id)

        sent_stream = self._tts._sentence_tokenizer.stream()
        input_sent_event = asyncio.Event()
        empty_input = False

        async def _input_task() -> None:
            async for data in self._input_ch:
                if isinstance(data, self._FlushSentinel):
                    sent_stream.flush()
                    continue
                sent_stream.push_text(data)
            sent_stream.end_input()

        async def _send_task(ws: aiohttp.ClientWebSocketResponse) -> None:
            nonlocal empty_input
            sent_count = 0
            async for ev in sent_stream:
                await ws.send_str(json.dumps({"text": ev.token + " ", "contextId": context_id}))
                self._mark_started()
                input_sent_event.set()
                sent_count += 1
            if sent_count == 0:
                empty_input = True
                input_sent_event.set()
                output_emitter.end_input()
                return
            await ws.send_str(json.dumps({"operation": "flush", "contextId": context_id}))

        async def _recv_task(ws: aiohttp.ClientWebSocketResponse) -> None:
            await input_sent_event.wait()
            if empty_input:
                return
            while True:
                msg = await ws.receive(timeout=self._conn_options.timeout)
                if msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    raise APIStatusError("Rime ws closed unexpectedly", request_id=request_id)
                if msg.type == aiohttp.WSMsgType.ERROR:
                    raise APIConnectionError(f"Rime ws error: {ws.exception()}")
                if msg.type != aiohttp.WSMsgType.TEXT:
                    logger.warning("unexpected Rime ws message type %s", msg.type)
                    continue
                data = json.loads(msg.data)
                kind = data.get("type")
                if kind == "chunk":
                    output_emitter.push(base64.b64decode(data["data"]))
                elif kind == "timestamps":
                    for word, start, end in _timestamps(data):
                        output_emitter.push_timed_transcript(
                            TimedString(text=word + " ", start_time=start, end_time=end)
                        )
                    self._tts.note_words(_timestamps(data))
                elif kind == "done":
                    output_emitter.end_input()
                    break
                elif kind == "error":
                    raise APIError(f"Rime ws error: {data.get('message', '(no message)')}")

        try:
            async with self._tts._pool.connection(timeout=self._conn_options.timeout) as ws:
                tasks = [
                    asyncio.create_task(_input_task()),
                    asyncio.create_task(_send_task(ws)),
                    asyncio.create_task(_recv_task(ws)),
                ]
                try:
                    await asyncio.gather(*tasks)
                except asyncio.CancelledError:
                    await self._clear(ws, context_id)
                    raise
                finally:
                    input_sent_event.set()
                    await sent_stream.aclose()
                    await utils.aio.gracefully_cancel(*tasks)
        except asyncio.TimeoutError:
            raise APITimeoutError() from None
        except aiohttp.ClientResponseError as e:
            raise APIStatusError(message=e.message, status_code=e.status, request_id=None, body=None) from None
        except APIError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise APIConnectionError(f"Rime WS error: {e}") from e

    async def _clear(self, ws: aiohttp.ClientWebSocketResponse, context_id: str) -> None:
        """Tell Rime to stop generating for this context before the socket returns to the pool."""
        try:
            await asyncio.shield(ws.send_str(clear_frame(context_id)))
            self._tts.note_cleared(context_id)
            logger.debug("cleared Rime context %s on interruption", context_id)
        except Exception as exc:
            logger.warning("could not clear Rime context %s: %s", context_id, exc)


def _timestamps(data: dict) -> list[tuple[str, float, float]]:
    timings = data.get("word_timestamps") or {}
    words = timings.get("words") or []
    starts = timings.get("start") or []
    ends = timings.get("end") or []
    return [(w, s, e) for w, s, e in zip(words, starts, ends)]
