"""Conflict engine: decide what a new candidate means for an existing fact."""

from __future__ import annotations

import re
from enum import Enum

from engine.models import FactVersion

_UNIT_ALIASES: dict[str, str] = {
    "milligrams": "mg",
    "milligram": "mg",
    "mgs": "mg",
    "micrograms": "mcg",
    "microgram": "mcg",
    "μg": "mcg",
    "ug": "mcg",
    "millilitres": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "milliliter": "ml",
    "percent": "%",
}

_NUMBER_WORDS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "fifteen": "15",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "hundred": "100",
}


class Resolution(str, Enum):
    NEW = "new"  # field not present yet
    SAME = "same"  # same value restated
    CORRECTION = "correction"  # newer epoch supplies a different value
    CONFLICT = "conflict"  # same epoch supplies a different value


def normalize_value(value: str) -> str:
    """Canonical form used for equality: lowercase, unit aliases, number words, spacing."""
    text = value.strip().lower()
    text = re.sub(r"(\d)\s*([a-zμ%]+)", r"\1 \2", text)  # "10mg" -> "10 mg"
    tokens = [_NUMBER_WORDS.get(t, _UNIT_ALIASES.get(t, t)) for t in re.split(r"\s+", text) if t]
    text = " ".join(tokens)
    text = re.sub(r"[.,;:]+$", "", text)
    return text


def same_value(a: str, b: str) -> bool:
    return normalize_value(a) == normalize_value(b)


def resolve(existing: FactVersion | None, value: str, epoch: int) -> Resolution:
    if existing is None:
        return Resolution.NEW
    if same_value(existing.value, value):
        return Resolution.SAME
    if existing.epoch == epoch:
        return Resolution.CONFLICT
    return Resolution.CORRECTION
