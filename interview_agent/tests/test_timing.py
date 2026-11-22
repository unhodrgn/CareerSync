"""The timing report (M5 S4): the arithmetic, and that nothing but numbers and codes can be in it."""
import json

from interview_agent.timing import SessionTiming


class Clock:
    def __init__(self):
        self.now = 50.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def one_turn(timing, clock, *, stt=0.4, endpointing=3.2, processing=1.1, tts=0.6, model=("ok", 0.8)):
    timing.mark("user_stopped")
    clock.advance(stt)
    timing.mark("stt_final")
    clock.advance(endpointing - stt)
    timing.mark("turn_committed")
    clock.advance(processing)
    timing.runner_done(model)
    timing.reply_handed_to_speech()
    clock.advance(tts)
    timing.agent_started_speaking()


def test_each_gap_is_derived_from_the_marks():
    clock = Clock()
    timing = SessionTiming(7, clock=clock)
    one_turn(timing, clock)
    (turn,) = timing.summary()["turns"]
    assert turn["stt_delay_s"] == 0.4 and turn["endpointing_s"] == 3.2 and turn["processing_s"] == 1.1 and turn["tts_start_s"] == 0.6
    assert turn["gap_s"] == 4.9 and turn["model"] == {"outcome": "ok", "seconds": 0.8}


def test_a_pause_inside_an_answer_does_not_leave_an_orphan_turn_and_the_last_stop_counts():
    clock = Clock()
    timing = SessionTiming(7, clock=clock)
    timing.mark("user_stopped")  # a pause...
    clock.advance(1.0)
    timing.mark("user_stopped")  # ...and the answer went on: the stop that counts is this one
    timing.mark("stt_final")
    clock.advance(0.5)
    timing.mark("stt_final")  # the last final transcript counts
    clock.advance(2.5)
    timing.mark("turn_committed")
    timing.runner_done(None)
    timing.reply_handed_to_speech()
    clock.advance(0.5)
    timing.agent_started_speaking()
    (turn,) = timing.summary()["turns"]
    assert turn["stt_delay_s"] == 0.5 and turn["endpointing_s"] == 3.0 and turn["gap_s"] == 3.5
    assert turn["model"] == {"outcome": "skipped", "seconds": None}  # the rules decided alone


def test_marks_without_an_open_turn_are_dropped_and_the_first_time_of_a_mark_stays():
    clock = Clock()
    timing = SessionTiming(7, clock=clock)
    timing.mark("turn_committed")
    assert timing.turns == []
    timing.mark("user_stopped")
    timing.mark("turn_committed")
    first = timing.turns[0]["turn_committed"]
    clock.advance(9)
    timing.mark("turn_committed")
    assert timing.turns[0]["turn_committed"] == first


def test_the_opening_a_nudge_and_a_reply_that_never_started_are_kept_apart():
    clock = Clock()
    timing = SessionTiming(7, clock=clock)
    timing.reply_handed_to_speech(opening=True)
    clock.advance(0.9)
    timing.agent_started_speaking()
    timing.reply_handed_to_speech(nudge=True)  # a nudge belongs to no answer
    clock.advance(0.4)
    timing.agent_started_speaking()
    summary = timing.summary()
    assert summary["opening"]["say_to_first_audio_s"] == 0.9 and summary["nudges"] == 1 and summary["turns"] == []


def test_the_headline_numbers_over_several_turns():
    clock = Clock()
    timing = SessionTiming(7, clock=clock)
    for tts in (0.5, 0.9, 0.7):
        one_turn(timing, clock, tts=tts)
        clock.advance(5)
    gaps = timing.summary()["gap_s"]
    assert gaps == {"count": 3, "min": 4.8, "median": 5.0, "max": 5.2}


def test_a_fallback_of_the_turn_detector_is_recorded():
    timing = SessionTiming(7)
    timing.note_detector(requested="v1", at_start="turn-detector-v1")
    assert timing.detector["fell_back"] is False
    timing.note_detector(requested="v1", now="turn-detector-v1-mini")
    assert timing.detector == {"requested": "v1", "model_at_start": "turn-detector-v1", "model_at_end": "turn-detector-v1-mini", "fell_back": True}


def test_the_written_report_holds_numbers_and_codes_only(tmp_path):
    clock = Clock()
    timing = SessionTiming(7, clock=clock)
    timing.settings = {"stt_model": "deepgram/nova-3", "endpointing_min_s": 3.0}
    one_turn(timing, clock)
    timing.note_llm([("ok", 0.8), ("timeout", 3.0)])
    timing.outcome = "completed"
    path = timing.write(tmp_path)
    assert path.parent == tmp_path and path.name.startswith("session-7-") and path.suffix == ".json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["session_id"] == 7 and report["outcome"] == "completed" and report["llm_calls"][1] == {"outcome": "timeout", "seconds": 3.0}

    def strings(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value

    allowed = {"completed", "ok", "timeout", "skipped", "deepgram/nova-3"}
    leaked = [s for s in strings(report) if s not in allowed and not s.replace("_", "").isalnum() and "-" not in s]
    assert leaked == [], "a report holds keys, codes and numbers, never a sentence"
