"""LiveKit entrypoint for the Hearback voice agent.

The dialogue is not generated. Deepgram transcribes, the sidecar's engine decides what the state
now is and what sentence that warrants, and Rime speaks exactly that sentence. No LLM sits in the
speaking path, which is what makes "guarantees what was heard" a claim rather than a hope.

Each turn:
  1. a final transcript opens a new epoch, and anything still in flight for the old one is stale;
  2. if the agent was mid-sentence, the heard-state ledger records the word it was cut off at;
  3. a bare "yes" verifies whatever was just read back;
  4. extraction proposes candidates, the engine folds them in and returns the next line;
  5. the agent speaks it and reports what was delivered.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.voice import SpeechHandle
from livekit.plugins import deepgram, silero

from agent.client import HearbackClient, NextLine
from agent.config import AgentConfig, load_agent_config
from agent.ledger import SpeechTracker
from agent.rime_ws3 import EpochRimeTTS
from engine.dialogue import is_affirmation, is_negation

logger = logging.getLogger("hearback.agent")

INSTRUCTIONS = (
    "You are a clinical handover scribe. You never diagnose, prescribe or advise on treatment. "
    "You read back what the paramedic said and confirm it."
)

# F12: critical read-backs can be made uninterruptible. Off by default, because the barge-in
# demonstration depends on being able to cut into one mid-word.
UNINTERRUPTIBLE_CRITICAL = os.getenv("HEARBACK_UNINTERRUPTIBLE_CRITICAL", "").lower() in {"1", "true", "yes"}


class HearbackRunner:
    """Owns the turn loop. Holds no clinical state: the sidecar does.

    Speaking runs as a separate task so a new turn can arrive mid-sentence. That is the whole
    point: the turn loop must never be blocked by the agent's own voice.
    """

    def __init__(self, session: AgentSession, client: HearbackClient, config: AgentConfig) -> None:
        self._session = session
        self._client = client
        self._config = config
        self._started_at = time.monotonic()
        self._epoch = 0
        self._tracker = SpeechTracker(self._now_ms)
        self._speech: asyncio.Task[None] | None = None
        self._handle: SpeechHandle | None = None
        self._turns: asyncio.Queue[str] = asyncio.Queue()

    @property
    def epoch(self) -> int:
        return self._epoch

    def _now_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    def note_words(self, words: list[tuple[str, float, float]]) -> None:
        self._tracker.add_words(words)

    def submit(self, transcript: str) -> None:
        """Called from the event handler, which must not block the session loop."""
        self._turns.put_nowait(transcript)

    async def run(self) -> None:
        while True:
            transcript = await self._turns.get()
            try:
                await self._handle_turn(transcript)
            except Exception:
                logger.exception("turn failed; the handover continues")

    async def aclose(self) -> None:
        await self._stop_speaking(interrupted=False)

    async def _handle_turn(self, transcript: str) -> None:
        self._epoch = await self._client.utterance(transcript)
        await self._stop_speaking(interrupted=True)
        await self._apply_confirmation(transcript)

        outcome = await self._client.extract(transcript, epoch=self._epoch)
        if not outcome.applied:
            logger.info("dropped a stale extraction for epoch %s", outcome.requested_epoch)
        if outcome.error:
            logger.warning("extraction degraded to %s: %s", outcome.source, outcome.error)
        if outcome.next_line is not None:
            self._speech = asyncio.ensure_future(self._speak_until_silent(outcome.next_line, self._epoch))

    async def _stop_speaking(self, interrupted: bool) -> None:
        """Cut the agent off and record exactly how much of the sentence landed."""
        task, self._speech = self._speech, None
        if task is None or task.done():
            return
        if self._handle is not None and not self._handle.interrupted:
            self._handle.interrupt()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        for report in self._tracker.finish(interrupted=interrupted):
            await self._client.delivery(**report.payload)
            logger.info("heard up to %r on %s", report.delivered.cutoff_word, report.field)

    async def _apply_confirmation(self, transcript: str) -> None:
        """A bare "yes" verifies whatever was just read back. A "no" verifies nothing."""
        if is_negation(transcript) or not is_affirmation(transcript):
            return
        for field in await self._client.awaiting_confirmation():
            await self._client.verify(field)
            logger.info("verified %s on confirmation", field)

    async def _speak_until_silent(self, line: NextLine, epoch: int) -> None:
        """Say what the engine asks for, then ask again, until it has nothing more to say."""
        current: NextLine | None = line
        while current is not None:
            self._tracker.begin(epoch, current.text, current.fields)
            allow_interruptions = not (current.critical and UNINTERRUPTIBLE_CRITICAL)
            self._handle = self._session.say(current.text, allow_interruptions=allow_interruptions)
            await self._handle.wait_for_playout()
            for report in self._tracker.finish(interrupted=self._handle.interrupted):
                await self._client.delivery(**report.payload)
            current = await self._client.next_line()
        self._handle = None


def build_tts(config: AgentConfig, epoch_source, on_words) -> EpochRimeTTS:
    rime = config.rime
    return EpochRimeTTS(
        epoch_source=epoch_source,
        on_words=on_words,
        inline_speed_alpha=rime.inline_speed_alpha,
        api_key=rime.api_key,
        base_url=rime.ws_base_url,
        model=rime.model,
        speaker=rime.speaker_for(config.lang),
        lang=rime.lang_code(config.lang),
        sample_rate=rime.sample_rate,
        speed_alpha=rime.speed_alpha,
        use_websocket=True,
        segment="immediate",
    )


async def entrypoint(ctx: JobContext) -> None:
    config = load_agent_config()
    if not config.can_transcribe:
        raise RuntimeError("DEEPGRAM_API_KEY is not set; the agent cannot hear")

    client = HearbackClient(base_url=config.api_base_url)
    await client.create_session(session_id=ctx.room.name)
    logger.info("handover session %s ready", client.session_id)

    runner_ref: dict[str, HearbackRunner] = {}
    tts = build_tts(
        config,
        epoch_source=lambda: runner_ref["runner"].epoch if "runner" in runner_ref else 0,
        on_words=lambda words: runner_ref["runner"].note_words(words) if "runner" in runner_ref else None,
    )

    session = AgentSession(
        stt=deepgram.STT(model=config.stt_model, api_key=config.deepgram_api_key, language="multi"),
        tts=tts,
        vad=silero.VAD.load(),
        turn_handling={
            "endpointing": {"min_delay": 0.3},
            "interruption": {"enabled": True, "min_duration": 0.2},
        },
    )
    runner = HearbackRunner(session, client, config)
    runner_ref["runner"] = runner

    @session.on("user_input_transcribed")
    def _on_transcript(event) -> None:
        if event.is_final and event.transcript.strip():
            runner.submit(event.transcript.strip())

    @session.on("error")
    def _on_error(event) -> None:
        logger.error("session error: %s", event)
        asyncio.ensure_future(client.set_provider("fallback", reason=str(event)))

    await ctx.connect()
    await session.start(agent=Agent(instructions=INSTRUCTIONS), room=ctx.room)
    try:
        await runner.run()
    finally:
        await runner.aclose()
        await client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
