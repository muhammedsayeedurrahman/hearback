"""What a spoken confirmation is allowed to settle.

A read-back closes the loop only if the "yes" answers the question that was asked. When the
clinician's confirmation carries a number the agent never read back — "yes, five milligrams" after
the agent said *ten* — the two sides are not talking about the same value, and treating that as a
confirmation would let a mishearing through the relay gate wearing a human's approval.

The rule is deliberately narrow: it looks at numbers only, spoken or written, and it refuses rather
than guesses. Numbers are where the risk concentrates (a dose, a rate, a pressure), a doubled
number is what the NCC MERP verbal-order rules exist to protect, and widening this to every word
would refuse honest confirmations that happen to reword the value.
"""

from __future__ import annotations

import re

from engine.models import Fact

_UNITS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_TOKEN = re.compile(r"[a-z]+|\d+(?:\.\d+)?")


def spoken_numbers(text: str) -> tuple[str, ...]:
    """Every number a sentence states, in order, however it was spoken.

    "ninety over sixty" and "90/60" both give ("90", "60"), so a value can be compared across the
    boundary between what was synthesised and what was transcribed.
    """
    tokens = _TOKEN.findall(text.lower())
    found: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token[0].isdigit():
            found.append(_trim(token))
        elif token in _TENS:
            value = _TENS[token]
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            if following in _UNITS and 0 < _UNITS[following] < 10:
                value += _UNITS[following]
                index += 1
            found.append(str(value))
        elif token in _UNITS:
            found.append(str(_UNITS[token]))
        elif token == "hundred" and found:
            found[-1] = str(int(float(found[-1])) * 100)
        index += 1
    return tuple(found)


def _trim(number: str) -> str:
    """'5.0' and '5' are the same dose; '0.5' is not."""
    return number.rstrip("0").rstrip(".") if "." in number else number


def challenged_by(fact: Fact, spoken: str) -> str | None:
    """Why this confirmation cannot settle this fact, or None if it can.

    A confirmation may restate the value it is confirming, and it may say nothing at all. What it
    may not do is introduce a number that was neither read back to the listener nor already the
    live value — that is a correction being mistaken for an agreement.
    """
    stated = spoken_numbers(spoken)
    if not stated:
        return None

    delivered = fact.current.delivered
    heard = delivered.text_heard if delivered else ""
    permitted = set(spoken_numbers(heard)) | set(spoken_numbers(fact.value))
    unheard = [number for number in stated if number not in permitted]
    if not unheard:
        return None
    return (
        f"the confirmation states {', '.join(unheard)}, which was never read back for "
        f"{fact.field} (heard: {heard.strip() or 'nothing'})"
    )
