"""Cross-check tool.

One tool, deliberately: check a drug the paramedic named against the allergy already recorded in
this handover, and against the ISMP look-alike list. It reports a match; it never advises. The
injectable delay is the evidence fixture: with three seconds of latency the agent must stay
responsive and, if the paramedic corrects the drug meanwhile, must drop the answer to the
question nobody is asking any more.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from agent.client import HearbackClient
from engine.conflict import same_value
from engine.slots import lasa_partner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrossCheck:
    """Stamped with the epoch it was asked for, so a stale answer can be dropped on arrival."""

    epoch: int
    drug: str
    recorded_allergy: str | None
    matches_recorded_allergy: bool
    look_alike: str | None
    delayed_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "drug": self.drug,
            "recorded_allergy": self.recorded_allergy,
            "matches_recorded_allergy": self.matches_recorded_allergy,
            "look_alike": self.look_alike,
            "delayed_ms": self.delayed_ms,
        }

    @property
    def summary(self) -> str:
        if self.matches_recorded_allergy:
            return f"{self.drug} matches the recorded allergy ({self.recorded_allergy}). Flagging for the receiving team."
        if self.look_alike:
            return f"{self.drug} sounds like {self.look_alike}. Confirming the spelling before relay."
        return f"No recorded allergy conflict for {self.drug}."


async def allergy_check(client: HearbackClient, drug: str, epoch: int, delay_ms: int = 0) -> CrossCheck:
    """Look the drug up against this handover's recorded allergy. No advice, only a match."""
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)
    state = await client.state()
    allergy = state.get("facts", {}).get("allergy")
    recorded = allergy.get("value") if allergy else None
    matches = bool(recorded) and recorded.lower() != "none" and same_value(recorded, drug)
    return CrossCheck(
        epoch=epoch,
        drug=drug,
        recorded_allergy=recorded,
        matches_recorded_allergy=matches,
        look_alike=lasa_partner(drug),
        delayed_ms=delay_ms,
    )


def accept_result(result: CrossCheck, current_epoch: int) -> bool:
    """The fence again: an answer about a superseded utterance is not an answer."""
    return result.epoch == current_epoch
