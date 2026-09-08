from agent.ledger import MS_PER_WORD, SpeechTracker

TIMED = [("Confirming. ", 0.0, 0.6), ("Morphine, ", 0.7, 1.3), ("ten ", 1.5, 1.9), ("milligrams. ", 1.95, 2.6)]


class FakeClock:
    """Playout time under test control, so a barge-in lands on an exact millisecond."""

    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


def _tracker():
    clock = FakeClock()
    return SpeechTracker(clock), clock


def test_word_timestamps_give_the_exact_cutoff_word():
    tracker, clock = _tracker()
    tracker.begin(epoch=1, text="Confirming. Morphine, ten milligrams.", fields=["morphine_dose"])
    tracker.add_words(TIMED)
    clock.now = 1840
    (report,) = tracker.finish(interrupted=True)
    assert report.field == "morphine_dose" and report.speech_epoch == 1
    assert report.delivered.cutoff_word == "ten"
    assert report.delivered.text_heard == "Confirming. Morphine, ten"
    assert report.payload["interrupted_at_ms"] == 1840
    assert report.payload["words"][2] == {"word": "ten", "start_ms": 1500, "end_ms": 1900}


def test_an_uninterrupted_sentence_is_delivered_whole():
    tracker, clock = _tracker()
    tracker.begin(epoch=1, text="Allergy, penicillin, verified.", fields=["allergy"])
    tracker.add_words(TIMED)
    clock.now = 2700
    (report,) = tracker.finish(interrupted=False)
    assert report.delivered.complete is True
    assert "interrupted_at_ms" not in report.payload


def test_one_sentence_can_report_for_every_fact_it_spoke():
    tracker, _ = _tracker()
    tracker.begin(epoch=2, text="Blood pressure 90 over 60, heart rate 122.", fields=["bp", "hr"])
    tracker.add_words(TIMED)
    reports = tracker.finish(interrupted=False)
    assert [r.field for r in reports] == ["bp", "hr"]
    assert {r.speech_epoch for r in reports} == {2}


def test_truncated_transcript_is_the_first_fallback():
    tracker, clock = _tracker()
    tracker.begin(epoch=1, text="Confirming. Morphine, ten milligrams.", fields=["morphine_dose"])
    clock.now = 1840
    (report,) = tracker.finish(interrupted=True, heard_text="Confirming. Morphine, ten")
    assert report.delivered.cutoff_word == "ten" and report.delivered.complete is False
    assert report.payload == {
        "field": "morphine_dose",
        "speech_epoch": 1,
        "text": "Confirming. Morphine, ten milligrams.",
        "heard_text": "Confirming. Morphine, ten",
    }


def test_playout_estimate_is_the_last_fallback_and_does_not_claim_completeness():
    tracker, clock = _tracker()
    text = "Confirming. Morphine, ten milligrams."
    tracker.begin(epoch=1, text=text, fields=["morphine_dose"])
    clock.now = 1000
    (report,) = tracker.finish(interrupted=True)
    assert report.payload["duration_ms"] == len(text.split()) * MS_PER_WORD
    assert report.delivered.complete is False
    assert report.delivered.cutoff_word == "ten"


def test_the_estimate_drifts_a_word_which_is_why_timestamps_are_worth_having():
    """Same barge-in instant, with and without Rime timings: an evenly spread guess lands late."""
    estimated, estimated_clock = _tracker()
    estimated.begin(epoch=1, text="Confirming. Morphine, ten milligrams.", fields=["morphine_dose"])
    estimated_clock.now = 1000
    (guess,) = estimated.finish(interrupted=True)

    timed, timed_clock = _tracker()
    timed.begin(epoch=1, text="Confirming. Morphine, ten milligrams.", fields=["morphine_dose"])
    timed.add_words(TIMED)
    timed_clock.now = 1000
    (truth,) = timed.finish(interrupted=True)

    assert guess.delivered.cutoff_word == "ten"
    assert truth.delivered.cutoff_word == "Morphine,"


def test_words_arriving_without_a_live_sentence_are_ignored():
    tracker, _ = _tracker()
    tracker.add_words(TIMED)
    assert tracker.current is None
    assert tracker.finish(interrupted=True) == ()


def test_finishing_clears_the_live_sentence():
    tracker, _ = _tracker()
    tracker.begin(epoch=1, text="Allergy, penicillin.", fields=["allergy"])
    assert tracker.current is not None
    tracker.finish(interrupted=False)
    assert tracker.current is None
