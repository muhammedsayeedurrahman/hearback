"""Closed-loop readback phrasing for Rime.

Follows the NCC MERP verbal-order rules: numbers stated twice, once as a word and once digit by
digit; look-alike drug names spelled. Rime inline controls used: `spell()` for digit-by-digit and
letter-by-letter delivery, and `[brackets]` so `inlineSpeedAlpha` can slow the number. Coda
supports no SSML, so these are the only controls.

Every line is built in two forms at once. `text` carries the control markup and goes to Rime;
`plain` is the same sentence as words, and it is what the heard-state ledger records. Deriving
the plain form by stripping markup afterwards would leave the doubled number reading as two
separate values, so both are generated from the same source instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.models import Fact, FactStatus
from engine.slots import drug_name, is_critical, is_identifier, lasa_partner

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
    plain: str = ""

    def __post_init__(self) -> None:
        if not self.plain:
            object.__setattr__(self, "plain", self.text)


def label(field: str) -> str:
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    drug = drug_name(field)
    if drug:
        return drug if field.endswith("_dose") else f"time of {drug}"
    return field.replace("_", " ")


def display_label(field: str) -> str:
    """Sentence case that survives an initialism: 'G C S' must not become 'G c s'."""
    name = label(field)
    return name[:1].upper() + name[1:]


def spoken_value(field: str, value: str) -> str:
    """Render a value the NCC MERP way: '[5] milligrams, spell(5) milligrams'."""
    if is_identifier(field):
        return f"spell({value})"
    pair = _PAIR.match(value)
    if pair:
        high, low = pair.group(1), pair.group(2)
        return f"[{high}] over [{low}], spell({high}) over spell({low})"
    match = _NUM_UNIT.match(value)
    if not match:
        return _maybe_spell_drug(value)
    number, unit_word = match.group(1), _unit_word(match.group(2) or "")
    digits = number.replace(".", " point ")
    first = f"[{number}] {unit_word}".strip()
    second = f"spell({digits}) {unit_word}".strip()
    return f"{first}, {second}"


def plain_value(field: str, value: str) -> str:
    """The same value as words: what a listener would report having heard."""
    if is_identifier(field):
        return spaced(value)
    pair = _PAIR.match(value)
    if pair:
        return f"{pair.group(1)} over {pair.group(2)}"
    match = _NUM_UNIT.match(value)
    if not match:
        return value
    return f"{match.group(1)} {_unit_word(match.group(2) or '')}".strip()


def confirm_prompt(fact: Fact) -> Readback:
    """The sentence the agent speaks before a critical fact can become VERIFIED."""
    name = label(fact.field)
    drug = drug_name(fact.field)
    spelled = f" spell({drug}) ," if drug and lasa_partner(drug) else ""
    return Readback(
        text=_tidy(f"Confirming. {name},{spelled} {spoken_value(fact.field, fact.value)}. Say yes to confirm."),
        plain=_tidy(f"Confirming. {name}, {plain_value(fact.field, fact.value)}. Say yes to confirm."),
        inline_speed_alpha=NUMBER_SPEED_ALPHA,
        critical=is_critical(fact.field),
    )


def acknowledgement(fact: Fact) -> Readback:
    """Non-critical facts are noted, not read back — except codes, which are always spelled."""
    name = display_label(fact.field)
    if is_identifier(fact.field):
        return Readback(
            text=_tidy(f"{name} noted as {spoken_value(fact.field, fact.value)}."),
            plain=_tidy(f"{name} noted as {plain_value(fact.field, fact.value)}."),
            inline_speed_alpha=None,
            critical=is_critical(fact.field),
        )
    text = _tidy(f"{name} noted as {fact.value}.")
    return Readback(text=text, plain=text, inline_speed_alpha=None, critical=is_critical(fact.field))


def verified_line(fact: Fact) -> Readback:
    name = display_label(fact.field)
    return Readback(
        text=_tidy(f"{name}, {spoken_value(fact.field, fact.value)}, verified."),
        plain=_tidy(f"{name}, {plain_value(fact.field, fact.value)}, verified."),
        inline_speed_alpha=NUMBER_SPEED_ALPHA,
        critical=is_critical(fact.field),
    )


def reconciliation(fact: Fact) -> Readback | None:
    """After a mid-sentence correction: phrase from what the listener actually heard."""
    if fact.status is not FactStatus.CORRECTED or not fact.history:
        return None
    old = fact.history[-1]
    heard = (old.delivered.text_heard if old.delivered else "").rstrip(" .,;")
    new_value = plain_value(fact.field, fact.value)
    opening = f"I had said {plain_value(fact.field, old.value)}" if not heard else f"I had said, {heard}"
    text = _tidy(f"{opening}. You're now saying {new_value}. Use {new_value} as final?")
    return Readback(text=text, plain=text, inline_speed_alpha=None, critical=is_critical(fact.field))


def conflict_prompt(fact: Fact) -> Readback | None:
    if fact.status is not FactStatus.CONFLICTED:
        return None
    values = [fact.current.value] + [v.value for v in fact.conflict]
    joined = " or ".join(plain_value(fact.field, v) for v in values)
    text = _tidy(f"I heard two values for {label(fact.field)}: {joined}. Which one is right?")
    return Readback(text=text, plain=text, inline_speed_alpha=None, critical=is_critical(fact.field))


def spaced(value: str) -> str:
    """'A472913' as a listener would report hearing it, character by character."""
    return " ".join(ch.upper() for ch in value if not ch.isspace())


def _maybe_spell_drug(value: str) -> str:
    return f"{value}, spell({value})" if lasa_partner(value) else value


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
