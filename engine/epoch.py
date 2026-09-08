"""Epoch fence.

Every user utterance bumps a monotonic integer epoch. Every LLM result, tool result and TTS job
is stamped with the epoch it was produced for. Anything stamped older than the current epoch is
stale and must be dropped. This is arithmetic, not an LLM judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Stamped(Generic[T]):
    epoch: int
    payload: T


def is_stale(item_epoch: int, current_epoch: int) -> bool:
    """True when the item was produced for an epoch older than the current one."""
    return item_epoch < current_epoch


def is_future(item_epoch: int, current_epoch: int) -> bool:
    """True when an item claims an epoch the state has not reached. Treated as a bug upstream."""
    return item_epoch > current_epoch


def accept(item_epoch: int, current_epoch: int) -> bool:
    """Only items stamped with exactly the current epoch pass the fence."""
    return item_epoch == current_epoch


def stamp(payload: T, epoch: int) -> Stamped[T]:
    return Stamped(epoch=epoch, payload=payload)
