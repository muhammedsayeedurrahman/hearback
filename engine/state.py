"""Truth-state transitions. Every function returns a new TruthState."""

from __future__ import annotations

from engine import confirmation, conflict
from engine.epoch import is_future, is_stale
from engine.slots import is_critical
from engine.models import (
    RELAYABLE,
    VERIFIABLE,
    Candidate,
    Delivered,
    Fact,
    FactStatus,
    FactVersion,
    TruthState,
)


class TransitionError(Exception):
    """Raised when a transition is not allowed from the current status."""


def new_session(session_id: str, at_ms: int = 0) -> TruthState:
    return TruthState(session_id=session_id).with_event("session_created", at_ms)


def next_epoch(state: TruthState, utterance: str, at_ms: int, speaker: str = "sender") -> TruthState:
    """A user utterance opens a new epoch. Everything produced for older epochs is now stale."""
    bumped = state.with_epoch(state.epoch + 1)
    return bumped.with_event("utterance", at_ms, text=utterance, speaker=speaker)


def apply_extraction(state: TruthState, candidates: tuple[Candidate, ...] | list[Candidate], epoch: int, at_ms: int) -> TruthState:
    """Fold LLM candidates into the truth state, subject to the epoch fence."""
    if is_stale(epoch, state.epoch):
        return state.with_event("stale_llm", at_ms, epoch=epoch, dropped=len(candidates), current_epoch=state.epoch)
    if is_future(epoch, state.epoch):
        raise TransitionError(f"extraction epoch {epoch} is ahead of state epoch {state.epoch}")

    result = state
    for cand in candidates:
        result = _apply_candidate(result, cand, epoch, at_ms)
    return result


def _apply_candidate(state: TruthState, cand: Candidate, epoch: int, at_ms: int) -> TruthState:
    existing = state.fact(cand.field)
    current = existing.current if existing else None
    outcome = conflict.resolve(current, cand.value, epoch)
    status_new = FactStatus.INFERRED if cand.inferred else FactStatus.HEARD
    version = FactVersion(value=cand.value, status=status_new, epoch=epoch, source_text=cand.source_text)

    if outcome is conflict.Resolution.NEW:
        fact = Fact(field=cand.field, current=version)
        return _put(state, fact).with_event("fact_added", at_ms, epoch=epoch, field=cand.field, value=cand.value, status=status_new.value)

    assert existing is not None and current is not None
    if outcome is conflict.Resolution.SAME:
        return state.with_event("fact_restated", at_ms, epoch=epoch, field=cand.field, value=cand.value, status=current.status.value)

    if outcome is conflict.Resolution.CONFLICT:
        conflicted = Fact(
            field=cand.field,
            current=current.with_status(FactStatus.CONFLICTED),
            history=existing.history,
            conflict=existing.conflict + (version,),
        )
        return _put(state, conflicted).with_event(
            "fact_conflicted", at_ms, epoch=epoch, field=cand.field, values=[current.value, cand.value]
        )

    corrected = Fact(
        field=cand.field,
        current=version.with_status(FactStatus.CORRECTED),
        history=existing.history + (current.with_status(FactStatus.SUPERSEDED),) + tuple(
            v.with_status(FactStatus.SUPERSEDED) for v in existing.conflict
        ),
    )
    return _put(state, corrected).with_event(
        "fact_corrected", at_ms, epoch=epoch, field=cand.field, old=current.value, new=cand.value,
        old_status=current.status.value,
    )


def verify_unchallenged(state: TruthState, at_ms: int) -> TruthState:
    """Settle non-critical facts the sender heard read back and did not correct.

    Critical facts always need an explicit yes; that is the whole point of the critical tier.
    For the rest, the agent's acknowledgement is the read-back, and a following turn that does
    not correct it is the confirmation, which is how a spoken handover actually works.
    """
    result = state
    for field in tuple(state.facts):
        fact = result.facts[field]
        if is_critical(field) or fact.status not in {FactStatus.HEARD, FactStatus.INFERRED}:
            continue
        if fact.current.delivered is None or fact.current.epoch >= state.epoch:
            continue
        settled = Fact(field=field, current=fact.current.with_status(FactStatus.VERIFIED), history=fact.history)
        result = _put(result, settled).with_event(
            "fact_verified", at_ms, field=field, value=fact.value, by="unchallenged"
        )
    return result


def verify(
    state: TruthState, field: str, at_ms: int, by: str = "sender", spoken: str | None = None
) -> TruthState:
    """Settle a fact on an explicit human confirmation.

    When the confirming turn is supplied, it must agree with what was read back: a "yes" carrying a
    number the listener never heard is a correction wearing an agreement's clothes, and it is
    refused and logged rather than applied. The fact stays unverified, so the relay gate holds and
    the value has to be read back again.
    """
    fact = _require(state, field)
    if fact.status not in VERIFIABLE:
        raise TransitionError(f"{field} is {fact.status.value}; cannot verify")

    challenge = confirmation.challenged_by(fact, spoken) if spoken else None
    if challenge:
        return state.with_event(
            "confirmation_challenged", at_ms, field=field, value=fact.value, by=by, reason=challenge
        )

    verified = Fact(field=field, current=fact.current.with_status(FactStatus.VERIFIED), history=fact.history)
    return _put(state, verified).with_event("fact_verified", at_ms, field=field, value=fact.value, by=by)


def resolve_conflict(state: TruthState, field: str, value: str, at_ms: int, by: str = "sender") -> TruthState:
    """A human picks the authoritative value for a CONFLICTED fact. It becomes VERIFIED."""
    fact = _require(state, field)
    if fact.status is not FactStatus.CONFLICTED:
        raise TransitionError(f"{field} is {fact.status.value}; nothing to resolve")
    candidates = (fact.current,) + fact.conflict
    chosen = next((v for v in candidates if conflict.same_value(v.value, value)), None)
    if chosen is None:
        raise TransitionError(f"{value!r} is not one of the conflicting values for {field}")
    losers = tuple(v.with_status(FactStatus.SUPERSEDED) for v in candidates if v is not chosen)
    resolved = Fact(
        field=field,
        current=chosen.with_status(FactStatus.VERIFIED),
        history=fact.history + losers,
    )
    return _put(state, resolved).with_event("conflict_resolved", at_ms, field=field, value=chosen.value, by=by)


def record_delivery(state: TruthState, field: str, delivered: Delivered, at_ms: int, speech_epoch: int) -> TruthState:
    """Attach what the listener heard to the version that was being spoken."""
    fact = _require(state, field)
    in_history = any(v.epoch == speech_epoch for v in fact.history)
    if in_history:
        history = tuple(v.with_delivered(delivered) if v.epoch == speech_epoch else v for v in fact.history)
        updated = Fact(field=field, current=fact.current, history=history, conflict=fact.conflict)
    else:
        updated = Fact(field=field, current=fact.current.with_delivered(delivered), history=fact.history, conflict=fact.conflict)
    return _put(state, updated).with_event(
        "ledger_cut", at_ms, epoch=speech_epoch, field=field, **delivered.to_dict()
    )


def set_provider(state: TruthState, provider: str, at_ms: int, reason: str = "") -> TruthState:
    if provider == state.provider:
        return state
    return state.with_provider(provider).with_event("provider_changed", at_ms, provider=provider, reason=reason)


def relayable(state: TruthState) -> tuple[Fact, ...]:
    """The relay gate: only VERIFIED facts cross to the receiving clinician."""
    return tuple(f for f in state.facts.values() if f.status in RELAYABLE)


def pending(state: TruthState) -> tuple[Fact, ...]:
    return tuple(f for f in state.facts.values() if f.status not in RELAYABLE)


def _put(state: TruthState, fact: Fact) -> TruthState:
    facts = dict(state.facts)
    facts[fact.field] = fact
    return state.with_facts(facts)


def _require(state: TruthState, field: str) -> Fact:
    fact = state.fact(field)
    if fact is None:
        raise TransitionError(f"unknown field {field!r}")
    return fact
