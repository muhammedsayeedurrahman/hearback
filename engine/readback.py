"""Closed-loop readback phrasing for Rime.

Follows the NCC MERP verbal-order rules: numbers stated twice, once as a word and once digit by
digit; look-alike drug names spelled out. Rime inline controls used: `spell()` for digit-by-digit
and letter-by-letter delivery, and `[brackets]` so `inlineSpeedAlpha` can slow the number.
Coda supports no SSML, so these are the only controls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.models import Fact, FactStatus
from engine.slots import drug_name, is_critical, lasa_partner

FIELD_LABELS: dict[str, str] = {
    "bp": "blood pressure",
    "hr": "heart rate",
    "rr": "respiratory rate",
    "spo2": "oxygen saturation",
    "gcs": "G C S",
    "mrn": "M R N",
    "time_of_incident": "time of incident",
    "allergy": "allergy",
    "airway": "airway",
}

_NUM_UNIT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Zμ%/]+)?\s*$")
# Paired readings (blood pressure, ratios) are spoken "ninety over sixty", never "ninety slash sixty".
_PAIR = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")

# Slow-down factor applied to bracketed tokens through Rime's inlineSpeedAlpha parameter.
NUMBER_SPEED_ALPHA = "0.8"


@dataclass(frozen=True)
class Readback:
    text: str
    inline_speed_alpha: str | None
    critical: bool


def label(field: str) -> str:
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    drug = drug_name(field)
    if drug:
        return drug if field.endswith("_dose") else f"time of {drug}"
    return field.replace("_", " ")


def spoken_value(field: str, value: str) -> str:
    """Render a value the NCC MERP way: '[5] milligrams, spell(5) milligrams'."""
    pair = _PAIR.match(value)
    if pair:
        high, low = pair.group(1), pair.group(2)
        return f"[{high}] over [{low}], spell({high}) over spell({low})"
    m = _NUM_UNIT.match(value)
    if not m:
        return _maybe_spell_drug(field, value)
    number, unit = m.group(1), m.group(2) or ""
    unit_word = _unit_word(unit)
    digits = number.replace(".", " point ")
    first = f"[{number}] {unit_word}".strip()
    second = f"spell({digits}) {unit_word}".strip()
    return f"{first}, {second}"


def confirm_prompt(fact: Fact) -> Readback:
    """The sentence the agent speaks before a critical fact can become VERIFIED."""
    name = label(fact.field)
    body = spoken_value(fact.field, fact.value)
    drug = drug_name(fact.field)
    spelled = f" spell({drug}) ," if drug and lasa_partner(drug) else ""
    text = f"Confirming. {name},{spelled} {body}. Say yes to confirm."
    return Readback(text=_tidy(text), inline_speed_alpha=NUMBER_SPEED_ALPHA, critical=is_critical(fact.field))


def acknowledgement(fact: Fact) -> Readback:
    name = label(fact.field)
    text = f"{name.capitalize()} noted as {fact.value}."
    return Readback(text=_tidy(text), inline_speed_alpha=None, critical=is_critical(fact.field))


def verified_line(fact: Fact) -> Readback:
    text = f"{label(fact.field).capitalize()}, {spoken_value(fact.field, fact.value)}, verified."
    return Readback(text=_tidy(text), inline_speed_alpha=NUMBER_SPEED_ALPHA, critical=is_critical(fact.field))


def reconciliation(fact: Fact) -> Readback | None:
    """After a mid-sentence correction: phrase from what the listener actually heard."""
    if fact.status is not FactStatus.CORRECTED or not fact.history:
        return None
    old = fact.history[-1]
    heard = old.delivered.text_heard if old.delivered else ""
    old_said = f"I had said {old.value}" if not heard else f"I had said, {heard}"
    text = f"{old_said}. You're now saying {fact.value}. Use {fact.value} as final?"
    return Readback(text=_tidy(text), inline_speed_alpha=None, critical=is_critical(fact.field))


def conflict_prompt(fact: Fact) -> Readback | None:
    if fact.status is not FactStatus.CONFLICTED:
        return None
    values = [fact.current.value] + [v.value for v in fact.conflict]
    joined = " or ".join(values)
    text = f"I heard two values for {label(fact.field)}: {joined}. Which one is right?"
    return Readback(text=_tidy(text), inline_speed_alpha=None, critical=is_critical(fact.field))


def _maybe_spell_drug(field: str, value: str) -> str:
    partner = lasa_partner(value)
    if partner:
        return f"{value}, spell({value})"
    return value


def _unit_word(unit: str) -> str:
    table = {
        "mg": "milligrams",
        "mcg": "micrograms",
        "ml": "millilitres",
        "g": "grams",
        "%": "percent",
        "l": "litres",
        "lpm": "litres per minute",
        "mmhg": "millimetres of mercury",
    }
    return table.get(unit.lower(), unit)


def _tidy(text: str) -> str:
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
