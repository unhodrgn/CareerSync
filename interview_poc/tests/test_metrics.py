"""Timing report: derived figures are right, and the report holds numbers only (no transcript, no audio)."""
import json
from types import SimpleNamespace

from metrics import RunMetrics


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def build():
    clock = Clock()
    m = RunMetrics(clock=clock)

    def at(t, name, **fields):
        clock.t = t
        m.mark(name, **fields)

    at(1.0, "avatar_start")
    at(4.5, "avatar_joined")
    at(6.0, "say_called", step="opening", n=None, speech_id="s1")
    at(6.9, "agent_speaking")
    at(20.0, "user_state", state="speaking")
    at(25.0, "user_state", state="listening")
    at(25.9, "turn_completed", n=1)
    at(27.0, "llm_done", n=1, ttft_s=0.8, total_s=1.1)
    at(27.1, "say_called", step="followup", n=1, speech_id="s2")
    at(28.0, "agent_speaking")
    clock.t = 40.0
    m.finish("completed")
    m.note_sdk_metric(SimpleNamespace(type="eou_metrics", end_of_utterance_delay=0.7, transcription_delay=0.4, on_user_turn_completed_delay=0.01))
    m.note_sdk_metric(SimpleNamespace(type="tts_metrics", speech_id="s2", ttfb=0.45, audio_duration=3.0))
    m.note_sdk_metric(SimpleNamespace(type="avatar_metrics", playback_latency=0.3, avatar_joined_time=1.0, session_started_time=0.5))
    m.note_sdk_metric(SimpleNamespace(type="llm_metrics"))  # ignored
    return m


def test_derived_figures():
    s = build().summary()
    assert s["total_session_seconds"] == 40.0 and s["end_reason"] == "completed"
    assert s["avatar_time_to_join_s"] == 3.5
    assert s["time_to_first_avatar_audio_s"] == 0.9
    turn = s["turns"][0]
    assert turn["stt_transcription_delay_s"] == 0.4 and turn["end_of_utterance_delay_s"] == 0.7
    assert turn["llm_ttft_s"] == 0.8 and turn["llm_total_s"] == 1.1
    assert turn["tts_ttfb_s"] == 0.45
    assert turn["say_to_avatar_audio_s"] == 0.9
    assert turn["user_stopped_to_avatar_audio_s"] == 3.0  # 25.0 (listening) -> 28.0 (avatar speaking)
    assert s["avatar_sdk_metrics"][0]["playback_latency_s"] == 0.3


def test_report_has_numbers_only_and_is_written_to_the_given_folder(tmp_path):
    m = build()
    m.marks.append({"name": "x", "t": 1.0})
    path = m.write(tmp_path / "runs")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.parent == tmp_path / "runs" and data["end_reason"] == "completed"

    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                assert k not in ("text", "transcript", "audio", "answer", "question"), k
                yield from walk(v)
        elif isinstance(value, list):
            for v in value:
                yield from walk(v)
        else:
            yield value

    allowed_labels = {"completed", "followup", "closing"}  # reason and step names, never spoken or transcribed text
    for leaf in walk(data):
        assert isinstance(leaf, (int, float, type(None), bool)) or leaf in allowed_labels or str(leaf).startswith("20"), leaf


def test_finish_is_idempotent():
    m = RunMetrics(clock=Clock())
    m.finish("first")
    m.finish("second")
    assert m.end_reason == "first"
