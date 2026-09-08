import pytest

from engine.ledger import WordTiming, cut, cut_from_text, estimate_words, words_from_rime
from engine.models import Candidate, FactStatus
from engine.readback import reconciliation
from engine.state import apply_extraction, new_session, next_epoch, record_delivery

WORDS = (
    WordTiming("Confirming.", 0, 600),
    WordTiming("Morphine,", 700, 1300),
    WordTiming("ten", 1500, 1900),
    WordTiming("milligrams.", 1950, 2600),
)


def test_cut_mid_word_counts_started_word_as_heard():
    d = cut(WORDS, interrupted_at_ms=1840)
    assert d.text_heard == "Confirming. Morphine, ten"
    assert d.cutoff_word == "ten"
    assert d.cutoff_ms == 1840
    assert d.complete is False


def test_cut_before_first_word_hears_nothing():
    d = cut(WORDS, interrupted_at_ms=0)
    assert d.text_heard == "" and d.cutoff_word is None and d.complete is False


def test_cut_after_end_is_complete():
    d = cut(WORDS, interrupted_at_ms=5000)
    assert d.complete is True
    assert d.cutoff_word == "milligrams."


def test_no_interruption_is_complete_delivery():
    d = cut(WORDS, interrupted_at_ms=None)
    assert d.complete and d.cutoff_word is None


def test_words_from_rime_converts_seconds_and_offsets():
    words = words_from_rime(["a", "b"], [0.0, 0.5], [0.4, 0.9], offset_ms=100)
    assert words == (WordTiming("a", 100, 500), WordTiming("b", 600, 1000))


def test_words_from_rime_rejects_misaligned_arrays():
    with pytest.raises(ValueError):
        words_from_rime(["a"], [0.0, 0.5], [0.4])


def test_cut_from_text_fallback():
    d = cut_from_text("Confirming. Morphine, ten milligrams.", "Confirming. Morphine, ten")
    assert d.cutoff_word == "ten" and d.complete is False
    full = cut_from_text("a b", "a b")
    assert full.complete is True


def test_estimate_words_spreads_duration_evenly():
    words = estimate_words("one two three four", 2000)
    assert [w.start_ms for w in words] == [0, 500, 1000, 1500]
    assert estimate_words("", 100) == ()


def test_record_delivery_attaches_to_superseded_version_and_reconciles_from_heard_text():
    s = new_session("s")
    s = next_epoch(s, "morphine ten", at_ms=0)
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg")], epoch=1, at_ms=1)
    # Agent starts the readback for epoch 1; user barges in at 1840 ms.
    s = next_epoch(s, "wait, it was five", at_ms=1840)
    s = apply_extraction(s, [Candidate("morphine_dose", "5 mg")], epoch=2, at_ms=1900)
    s = record_delivery(s, "morphine_dose", cut(WORDS, 1840), at_ms=1850, speech_epoch=1)
    fact = s.fact("morphine_dose")
    assert fact.status is FactStatus.CORRECTED
    old = fact.history[0]
    assert old.status is FactStatus.SUPERSEDED
    assert old.delivered.cutoff_word == "ten"
    assert fact.current.delivered is None
    text = reconciliation(fact).text
    assert "Confirming. Morphine, ten" in text
    assert "5 milligrams" in text


def test_record_delivery_on_current_version():
    s = new_session("s")
    s = next_epoch(s, "bp ninety over sixty", at_ms=0)
    s = apply_extraction(s, [Candidate("bp", "90/60")], epoch=1, at_ms=1)
    s = record_delivery(s, "bp", cut(WORDS, None), at_ms=5, speech_epoch=1)
    assert s.fact("bp").current.delivered.complete is True
    assert s.events[-1].type == "ledger_cut"
