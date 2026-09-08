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
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
}

_TENS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_UNITS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_COMPOUND = re.compile(rf"\b({'|'.join(_TENS)})[\s-]({'|'.join(_UNITS)})\b", re.IGNORECASE)
_SPOKEN = re.compile(rf"\b({'|'.join(_NUMBER_WORDS)})\b", re.IGNORECASE)


class Resolution(str, Enum):
    NEW = "new"  # field not present yet
    SAME = "same"  # same value restated
    CORRECTION = "correction"  # newer epoch supplies a different value
    CONFLICT = "conflict"  # same epoch supplies a different value


def words_to_digits(text: str) -> str:
    """Spoken numbers to digits: "ninety four over sixty" -> "94 over 60"."""
    joined = _COMPOUND.sub(
        lambda m: str(int(_NUMBER_WORDS[m.group(1).lower()]) + int(_NUMBER_WORDS[m.group(2).lower()])),
        text,
    )
    return _SPOKEN.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], joined)


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
