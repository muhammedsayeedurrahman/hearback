"""Deterministic fact extraction.

Used offline, in CI and as the fallback whenever the LLM call fails. It is intentionally narrow:
it proposes candidates for the ATMIST-AMBO slots and nothing else. Deciding what a candidate
means — new value, restatement, correction or conflict — is the engine's job, not the extractor's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from engine.conflict import normalize_value, words_to_digits
from engine.models import Candidate

# Words that sit where a drug name would, and are never drug names.
_NOT_A_DRUG = frozenset(
    {
        "given", "gave", "give", "dose", "doses", "total", "about", "around", "roughly",
        "another", "further", "approximately", "with", "the", "and", "she", "he", "they",
        "was", "were", "has", "had", "have", "received", "receive", "patient", "just",
        "already", "then", "also", "plus", "over", "under", "still", "now", "him", "her",
    }
)

_UNIT = r"mg|mcg|ug|g|ml|milligrams?|micrograms?|grams?|millilitres?|milliliters?"
_MECHANISMS = (
    "fall from height",
    "road traffic collision",
    "motorcycle collision",
    "pedestrian struck",
    "stabbing",
    "assault",
    "crush injury",
    "burn",
)


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    build: Callable[[re.Match[str]], Candidate | None]


def _simple(field: str, value_of: Callable[[re.Match[str]], str]) -> Callable[[re.Match[str]], Candidate]:
    def build(match: re.Match[str]) -> Candidate:
        return Candidate(field=field, value=value_of(match), source_text=match.group(0).strip())

    return build


def _dose(drug_group: int, number_group: int, unit_group: int) -> Callable[[re.Match[str]], Candidate | None]:
    def build(match: re.Match[str]) -> Candidate | None:
        drug = match.group(drug_group).lower()
        if drug in _NOT_A_DRUG:
            return None
        value = normalize_value(f"{match.group(number_group)} {match.group(unit_group)}")
        return Candidate(field=f"{drug}_dose", value=value, source_text=match.group(0).strip())

    return build


_RULES: tuple[Rule, ...] = (
    Rule(
        re.compile(r"\b(?:bp|b\.p\.|blood pressure)\D{0,14}?(\d{2,3})\s*(?:/|over)\s*(\d{2,3})"),
        _simple("bp", lambda m: f"{m.group(1)}/{m.group(2)}"),
    ),
    Rule(
        re.compile(r"\b(?:hr|heart rate|pulse)\D{0,14}?(\d{2,3})\b"),
        _simple("hr", lambda m: m.group(1)),
    ),
    Rule(
        re.compile(r"\b(?:rr|resp rate|respiratory rate|resps|respirations)\D{0,14}?(\d{1,2})\b"),
        _simple("rr", lambda m: m.group(1)),
    ),
    Rule(
        re.compile(r"\b(?:spo2|sats?|saturations?|oxygen saturation)\D{0,14}?(\d{2,3})\s*%?"),
        _simple("spo2", lambda m: f"{m.group(1)}%"),
    ),
    Rule(re.compile(r"\bgcs\D{0,14}?(\d{1,2})\b"), _simple("gcs", lambda m: m.group(1))),
    Rule(
        re.compile(r"\b(\d{1,3})[\s-]*(?:year|yr|y)[\s-]*old\b|\bage\D{0,6}(\d{1,3})\b"),
        _simple("age", lambda m: m.group(1) or m.group(2)),
    ),
    Rule(
        re.compile(r"\b(?:nka|no known allergies|no allergies|allerg(?:y|ies)\s*(?:are\s*)?(?:nil|none))\b"),
        _simple("allergy", lambda _m: "none"),
    ),
    Rule(
        re.compile(r"\ballergic to\s+([a-z][a-z\- ]{2,28})|\ballerg(?:y|ies)\s*(?:to|:)\s+([a-z][a-z\- ]{2,28})"),
        _simple("allergy", lambda m: _trim(m.group(1) or m.group(2))),
    ),
    Rule(
        re.compile(rf"\b(?:airway\s+(?:is\s+)?)(patent|clear|compromised|obstructed|secured|maintained)\b"),
        _simple("airway", lambda m: m.group(1)),
    ),
    Rule(
        re.compile(rf"\b([a-z]{{4,20}})\s+(\d+(?:\.\d+)?)\s*({_UNIT})\b"),
        _dose(1, 2, 3),
    ),
    Rule(
        re.compile(rf"\b(\d+(?:\.\d+)?)\s*({_UNIT})\s+(?:of\s+)?([a-z]{{4,20}})\b"),
        _dose(3, 1, 2),
    ),
    Rule(
        re.compile(r"\b(?:at|around|since)\s+(\d{1,2})[:.](\d{2})\s*(?:hours|hrs|h)?\b"),
        _simple("time_of_incident", lambda m: f"{int(m.group(1)):02d}:{m.group(2)}"),
    ),
    Rule(
        re.compile(rf"\b({'|'.join(_MECHANISMS)})\b"),
        _simple("mechanism", lambda m: m.group(1)),
    ),
    Rule(
        re.compile(r"\b(?:mechanism(?: of injury)?|moi)\s*(?:is|was|:)?\s+([a-z][a-z0-9\- ]{3,50})"),
        _simple("mechanism", lambda m: _trim(m.group(1))),
    ),
    Rule(
        re.compile(r"\b(?:(open|closed|suspected|obvious)\s+)?(femur|tibia|humerus|pelvis|skull|rib|wrist)\s+fracture\b"),
        _simple("injuries", lambda m: " ".join(p for p in (m.group(1), m.group(2), "fracture") if p)),
    ),
)


def _trim(text: str) -> str:
    return re.sub(r"\s+(?:and|but|the|with|at|on|in)$", "", text.strip().rstrip(".,;"))


def extract(text: str) -> tuple[Candidate, ...]:
    """Propose candidates from one utterance. Repeats collapse; genuine disagreements do not."""
    prepared = words_to_digits(text.lower())
    found: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for rule in _RULES:
        for match in rule.pattern.finditer(prepared):
            candidate = rule.build(match)
            if candidate is None:
                continue
            key = (candidate.field, normalize_value(candidate.value))
            if key in seen:
                continue
            seen.add(key)
            found.append(candidate)
    return tuple(found)
