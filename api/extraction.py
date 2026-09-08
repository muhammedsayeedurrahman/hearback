"""Fact extraction. The model proposes; the engine disposes.

The LLM is asked for one thing only: a JSON list of field/value candidates from a single
utterance. It never sees the truth state, never decides what is verified and never phrases what
the agent says. When it fails or times out, the deterministic rule extractor takes over so the
handover keeps working rather than going silent.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from api import rules
from api.settings import Settings
from engine.models import Candidate

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

SYSTEM_PROMPT = """You extract clinical facts from one utterance of a paramedic-to-hospital handover.

Return JSON only, shaped: {"facts": [{"field": str, "value": str, "inferred": bool, "source_text": str}]}

Rules:
- One entry per distinct fact stated in THIS utterance. Nothing carried over, nothing invented.
- If the speaker states two different values for the same field, return both. Do not pick a winner.
- field is snake_case from: patient_name, mrn, sex, age, time_of_incident, mechanism, injuries,
  airway, bp, hr, rr, spo2, gcs, temperature, allergy, background, <drug>_dose, <drug>_drug_time.
- value is the shortest faithful string: "10 mg", "90/60", "94%", "penicillin", "none".
- inferred is true only when the value is implied rather than said outright.
- source_text is the span of the utterance the fact came from.
- No diagnosis, no treatment advice, no commentary. Facts only. Empty list if there are none."""


@dataclass(frozen=True)
class ExtractionResult:
    candidates: tuple[Candidate, ...]
    source: str
    error: str | None = None


class Extractor(Protocol):
    name: str

    async def extract(self, text: str) -> ExtractionResult: ...


class RuleExtractor:
    """Deterministic, offline, and the reason CI never needs an API key."""

    name = "rules"

    async def extract(self, text: str) -> ExtractionResult:
        return ExtractionResult(candidates=rules.extract(text), source=self.name)


class ClaudeExtractor:
    name = "claude"

    def __init__(self, api_key: str, model: str, timeout_s: float = 8.0) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_s)
        self._model = model
        self._fallback = RuleExtractor()

    async def extract(self, text: str) -> ExtractionResult:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=700,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            payload = "".join(block.text for block in response.content if block.type == "text")
            return ExtractionResult(candidates=_parse(payload), source=self.name)
        except Exception as exc:  # network, quota, malformed JSON: the handover must not stop
            logger.warning("extraction fell back to rules: %s", exc)
            fallback = await self._fallback.extract(text)
            return ExtractionResult(candidates=fallback.candidates, source="rules-fallback", error=str(exc))


def _parse(payload: str) -> tuple[Candidate, ...]:
    fenced = _FENCE.search(payload)
    body = json.loads(fenced.group(1) if fenced else payload)
    facts = body.get("facts", []) if isinstance(body, dict) else body
    if not isinstance(facts, list):
        raise ValueError("extraction payload has no fact list")
    return tuple(c for c in (_candidate(f) for f in facts) if c is not None)


def _candidate(raw: Any) -> Candidate | None:
    if not isinstance(raw, dict):
        return None
    field = str(raw.get("field") or "").strip()
    value = str(raw.get("value") or "").strip()
    if not field or not value:
        return None
    return Candidate(
        field=re.sub(r"[^a-z0-9_]", "_", field.lower()),
        value=value,
        inferred=bool(raw.get("inferred")),
        source_text=str(raw.get("source_text") or "")[:200],
    )


def build_extractor(settings: Settings) -> Extractor:
    """`rules` forces offline mode; `auto` uses Claude when a key is configured."""
    if settings.extractor == "rules":
        return RuleExtractor()
    if settings.anthropic_api_key:
        return ClaudeExtractor(settings.anthropic_api_key, settings.extraction_model)
    if settings.extractor == "claude":
        raise RuntimeError("HEARBACK_EXTRACTOR=claude but ANTHROPIC_API_KEY is not set")
    logger.info("no ANTHROPIC_API_KEY: using the deterministic rule extractor")
    return RuleExtractor()
