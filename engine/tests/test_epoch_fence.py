import pytest

from engine.epoch import accept, is_future, is_stale, stamp
from engine.models import Candidate, FactStatus
from engine.state import TransitionError, apply_extraction, new_session, next_epoch


def test_fence_arithmetic():
    assert is_stale(3, 4)
    assert not is_stale(4, 4)
    assert is_future(5, 4)
    assert accept(4, 4)
    assert not accept(3, 4)


def test_stamp_carries_epoch():
    s = stamp({"field": "bp"}, 7)
    assert s.epoch == 7 and s.payload["field"] == "bp"


def test_stale_llm_result_is_dropped_and_logged():
    s = new_session("s")
    s = next_epoch(s, "morphine ten", at_ms=0)  # epoch 1
    s = next_epoch(s, "wait, five", at_ms=500)  # epoch 2, user corrected before LLM returned
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg")], epoch=1, at_ms=900)
    assert s.fact("morphine_dose") is None
    assert s.events[-1].type == "stale_llm"
    assert s.events[-1].data["dropped"] == 1
    assert s.events[-1].data["current_epoch"] == 2


def test_current_epoch_result_applies_after_stale_one():
    s = new_session("s")
    s = next_epoch(s, "morphine ten", at_ms=0)
    s = next_epoch(s, "wait, five", at_ms=500)
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg")], epoch=1, at_ms=900)
    s = apply_extraction(s, [Candidate("morphine_dose", "5 mg")], epoch=2, at_ms=1000)
    assert s.fact("morphine_dose").value == "5 mg"
    assert s.fact("morphine_dose").status is FactStatus.HEARD


def test_future_epoch_is_a_bug_upstream():
    s = next_epoch(new_session("s"), "x", at_ms=0)
    with pytest.raises(TransitionError):
        apply_extraction(s, [Candidate("bp", "90/60")], epoch=5, at_ms=1)
