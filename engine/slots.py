"""Handover slots and criticality.

ATMIST order for the relay (Age, Time, Mechanism, Injuries, Signs, Treatment) plus the AMBO
tail (Allergies, Medications, Background, Other). The critical tier is justified by omission
statistics in the handover literature: allergies, medications, airway, hypoxia and hypotension
are the facts most often dropped, so they require read-back before relay.
"""

from __future__ import annotations

from dataclasses import dataclass

SLOT_ORDER: tuple[str, ...] = (
    "identity",
    "age",
    "time_of_incident",
    "mechanism",
    "injuries",
    "signs",
    "treatment",
    "allergies",
    "medications",
    "background",
    "other",
)

_FIELD_TO_SLOT: dict[str, str] = {
    "patient_name": "identity",
    "mrn": "identity",
    "sex": "identity",
    "age": "age",
    "time_of_incident": "time_of_incident",
    "mechanism": "mechanism",
    "injuries": "injuries",
    "airway": "signs",
    "bp": "signs",
    "hr": "signs",
    "rr": "signs",
    "spo2": "signs",
    "gcs": "signs",
    "temperature": "signs",
    "allergy": "allergies",
    "background": "background",
}

CRITICAL_FIELDS: frozenset[str] = frozenset({"allergy", "airway", "spo2", "bp"})
CRITICAL_SUFFIXES: tuple[str, ...] = ("_dose", "_drug_time")

# Look-alike / sound-alike names (ISMP confused drug names) that force spell() in readback.
LASA_PAIRS: dict[str, str] = {
    "hydralazine": "hydroxyzine",
    "hydroxyzine": "hydralazine",
    "morphine": "hydromorphone",
    "hydromorphone": "morphine",
    "metoprolol": "misoprostol",
    "amiodarone": "amantadine",
    "clonidine": "clonazepam",
    "clonazepam": "clonidine",
    "dopamine": "dobutamine",
    "dobutamine": "dopamine",
    "ketorolac": "ketamine",
    "ketamine": "ketorolac",
    "tramadol": "trazodone",
    "vinblastine": "vincristine",
}


@dataclass(frozen=True)
class SlotView:
    slot: str
    fields: tuple[str, ...]


def slot_for(field: str) -> str:
    if field in _FIELD_TO_SLOT:
        return _FIELD_TO_SLOT[field]
    if field.endswith("_dose") or field.endswith("_drug_time"):
        return "treatment"
    if field.endswith("_med"):
        return "medications"
    return "other"


def is_critical(field: str) -> bool:
    return field in CRITICAL_FIELDS or field.endswith(CRITICAL_SUFFIXES)


def drug_name(field: str) -> str | None:
    for suffix in CRITICAL_SUFFIXES:
        if field.endswith(suffix):
            return field[: -len(suffix)].replace("_", " ")
    return None


def lasa_partner(name: str) -> str | None:
    return LASA_PAIRS.get(name.strip().lower())


def ordered_fields(fields: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Sort fields into ATMIST-AMBO order, keeping insertion order within a slot."""
    rank = {slot: i for i, slot in enumerate(SLOT_ORDER)}
    indexed = list(enumerate(fields))
    return tuple(f for _, f in sorted(indexed, key=lambda p: (rank[slot_for(p[1])], p[0])))


def completeness(fields: list[str] | tuple[str, ...]) -> dict[str, bool]:
    present = {slot_for(f) for f in fields}
    return {slot: slot in present for slot in SLOT_ORDER}
