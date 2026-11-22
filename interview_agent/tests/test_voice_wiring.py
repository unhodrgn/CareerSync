"""How the voice worker is wired (M5 S4; docs/DECISIONS.md D52, D79). Real SDK objects where they are cheap to build; no room, audio, network or key.

Honest limit: nothing here talks to LiveKit. Dispatch into a room, the real recognizer and synthesizer, the turn detector on real Korean speech
and the latency are the live checklist of `interview_agent/README.md`; the offline audio path (a scripted recognizer, a fake microphone) is in
test_voice_pipeline.py."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from interview_agent import voice
from interview_agent.config import DEFAULT_AGENT_NAME, ConfigError, load_voice_settings
from interview_agent.rooms import session_id_from_metadata

VOICE = Path(voice.__file__)
SECRET = "k" * 40
LIVEKIT = {"LIVEKIT_URL": "wss://example.livekit.cloud", "LIVEKIT_API_KEY": "devkey", "LIVEKIT_API_SECRET": "s" * 40}
ENV = {"INTERVIEW_AGENT_SECRET": SECRET, **LIVEKIT}


def settings(**overrides):
    return load_voice_settings({**ENV, **overrides})


def built(monkeypatch, **overrides):
    """A real AgentSession as `build_session` makes it (no VAD, no room, no network). The Inference classes read the LiveKit credentials at
    construction; nothing connects until a session starts."""
    for name, value in LIVEKIT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LIVEKIT_DEV_MODE", raising=False)

    async def build():
        return voice.build_session(settings(**overrides), vad=None)

    return asyncio.run(build())


def voice_tree():
    return ast.parse(VOICE.read_text(encoding="utf-8"))


def keywords_of_calls(name: str) -> list[dict]:
    out = []
    for node in ast.walk(voice_tree()):
        if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == name) or (isinstance(node.func, ast.Attribute) and node.func.attr == name)):
            out.append({k.arg: k.value for k in node.keywords if k.arg})
    return out


# ── The dispatch metadata ──


@pytest.mark.parametrize(
    "metadata, expected",
    [('{"session_id": 12}', 12), ('{"session_id": 2147483647}', 2147483647), ("", None), (None, None), ("not json", None), ("[12]", None), ('{"session_id": "12"}', None),
     ('{"session_id": true}', None), ('{"session_id": 0}', None), ('{"session_id": -3}', None), ('{"session_id": 2147483648}', None), ("{}", None)],
)
def test_the_session_id_comes_only_from_the_dispatch_metadata(metadata, expected):
    assert session_id_from_metadata(metadata) == expected


# ── The session ──


def test_the_session_has_no_llm_so_no_transcript_can_reach_a_model_but_through_turn_model(monkeypatch):
    session = built(monkeypatch)
    assert session.llm is None
    assert all("llm" not in call for call in keywords_of_calls("AgentSession")), "no `llm=` is ever passed to the session"


def test_the_speech_services_are_livekit_inference_with_the_models_of_the_decision(monkeypatch):
    session = built(monkeypatch)
    assert (type(session.stt).__name__, session.stt.model, session.stt.provider) == ("STT", "deepgram/nova-3", "livekit")
    assert (type(session.tts).__name__, session.tts.model, session.tts.provider) == ("TTS", "cartesia/sonic-3", "livekit")
    assert session.tts._opts.language == "ko" and session.tts._opts.voice
    assert voice.turn_detection_label(session) == "turn-detector-v1"  # asked for by version: `start` would run the local v1-mini otherwise


def test_the_models_and_the_voice_can_be_changed_by_the_environment_without_code(monkeypatch):
    session = built(monkeypatch, INTERVIEW_AGENT_STT_MODEL="deepgram/nova-2", INTERVIEW_AGENT_TTS_MODEL="cartesia/sonic-3.5", INTERVIEW_AGENT_TTS_VOICE="voice-from-env")
    assert session.stt.model == "deepgram/nova-2" and session.tts.model == "cartesia/sonic-3.5" and session.tts._opts.voice == "voice-from-env"


def test_a_reply_never_starts_on_an_unfinished_transcript_and_the_endpointing_gives_a_thinking_candidate_time(monkeypatch):
    session = built(monkeypatch)
    assert session._opts.turn_handling["preemptive_generation"]["enabled"] is False
    endpointing = session.options.endpointing
    assert (endpointing["mode"], endpointing["min_delay"], endpointing["max_delay"]) == ("fixed", 3.0, 6.0)
    tuned = built(monkeypatch, INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS="2.5", INTERVIEW_AGENT_ENDPOINT_MAX_SECONDS="5")
    assert (tuned.options.endpointing["min_delay"], tuned.options.endpointing["max_delay"]) == (2.5, 5.0)


def test_the_room_options_use_the_microphone_only_and_delete_the_room_with_the_session():
    options = voice.room_options()
    assert options.audio_input is True and options.audio_output is True
    assert options.video_input is False and options.text_input is False and options.text_output is False
    assert options.close_on_disconnect is True and options.delete_room_on_close is True


def test_nothing_is_recorded_and_only_audio_is_subscribed_and_a_stop_forces_the_interruption_and_speech_is_not_interruptible():
    (start,) = keywords_of_calls("start")
    assert isinstance(start["record"], ast.Constant) and start["record"].value is False
    assert "room_options" in start
    (connect,) = [k for k in keywords_of_calls("connect") if "auto_subscribe" in k]
    assert ast.unparse(connect["auto_subscribe"]) == "AutoSubscribe.AUDIO_ONLY"
    (say,) = keywords_of_calls("say")
    assert ast.unparse(say["allow_interruptions"]) == "False" and ast.unparse(say["add_to_chat_ctx"]) == "False"
    (interrupt,) = keywords_of_calls("interrupt")
    assert ast.unparse(interrupt["force"]) == "True", "uninterruptible speech keeps playing unless the interruption is forced"


def test_the_agent_name_is_the_one_the_backend_dispatches():
    from interview_agent.config import agent_name_from_env

    assert DEFAULT_AGENT_NAME == "careersync-interviewer" and agent_name_from_env({}) == DEFAULT_AGENT_NAME
    assert agent_name_from_env({"INTERVIEW_AGENT_NAME": "another"}) == "another"
    registered = [k for k in keywords_of_calls("rtc_session")]
    assert registered and ast.unparse(registered[0]["agent_name"]) == "agent_name_from_env()"


def test_the_worker_needs_the_livekit_project_and_names_what_is_missing_without_a_value():
    for name in LIVEKIT:
        env = {k: v for k, v in ENV.items() if k != name}
        with pytest.raises(ConfigError) as error:
            load_voice_settings(env)
        assert name in str(error.value) and LIVEKIT[name] not in str(error.value)


@pytest.mark.parametrize(
    "overrides",
    [{"INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS": "0.1"}, {"INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS": "x"}, {"INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS": "5", "INTERVIEW_AGENT_ENDPOINT_MAX_SECONDS": "4"},
     {"INTERVIEW_AGENT_STATUS_POLL_SECONDS": "0"}, {"INTERVIEW_AGENT_STATUS_POLL_SECONDS": "99"}, {"INTERVIEW_AGENT_CONSOLE_SESSION_ID": "abc"}, {"INTERVIEW_AGENT_CONSOLE_SESSION_ID": "0"}],
)
def test_an_invalid_voice_setting_is_refused(overrides):
    with pytest.raises(ConfigError):
        settings(**overrides)


def test_the_voice_defaults_and_the_console_session():
    s = settings(INTERVIEW_AGENT_CONSOLE_SESSION_ID="12")
    assert (s.stt_model, s.tts_model, s.language, s.status_poll, s.console_session_id) == ("deepgram/nova-3", "cartesia/sonic-3", "ko", 5.0, 12)
    assert settings().console_session_id is None


# ── What is heard ──


def alternative(text):
    return SimpleNamespace(text=text, words=["raw", "words"])


def test_a_transcript_event_is_masked_in_place_and_loses_its_word_timings_only_when_it_changed():
    names = ("박서준",)
    event = SimpleNamespace(alternatives=[alternative("제 이름은 김철수이고 박서준 팀에서 일했습니다. 연락처는 010-1234-5678입니다."), alternative("멱등성은 중요합니다.")])
    assert voice.mask_event(event, names) == 1
    first, second = event.alternatives
    for secret in ("김철수", "박서준", "1234", "5678"):
        assert secret not in first.text
    assert first.words is None and second.text == "멱등성은 중요합니다." and second.words == ["raw", "words"]
    assert voice.mask_event(SimpleNamespace(alternatives=[]), names) == 0 and voice.mask_event(SimpleNamespace(), names) == 0


def test_the_hook_masks_again_hands_the_answer_over_and_never_asks_for_a_reply():
    from livekit.agents.llm import ChatMessage, StopResponse

    agent = voice.InterviewerAgent(("박서준",))
    received = []
    agent.on_turn = received.append
    message = ChatMessage(role="user", content=["박서준입니다. 멱등성은 중요합니다."])

    async def go():
        with pytest.raises(StopResponse):
            await agent.on_user_turn_completed(None, message)

    asyncio.run(go())
    assert received and "박서준" not in received[0] and "멱등성은 중요합니다" in received[0] and message.text_content == received[0]


# ── A failed setup ──


class FakeJobContext:
    """What `run_voice_interview` uses of a JobContext. `shutdown` only records: the test runs the shutdown callbacks itself, as the SDK would."""

    def __init__(self):
        self.job = SimpleNamespace(metadata='{"session_id": 12}')
        self.room = SimpleNamespace(name="room-12", on=lambda *a: None)
        self.proc = SimpleNamespace(userdata={"vad": object()})
        self.callbacks, self.reasons, self.deleted = [], [], 0

    def is_fake_job(self):
        return False

    async def connect(self, **_):
        pass

    def add_shutdown_callback(self, callback):
        self.callbacks.append(callback)

    def shutdown(self, reason=""):
        self.reasons.append(reason)

    async def delete_room(self):
        self.deleted += 1


def run_job(monkeypatch, env=None):
    reports = []
    monkeypatch.setattr(voice, "load_voice_settings", lambda: settings(**(env or {})))
    monkeypatch.setattr(voice.SessionTiming, "write", lambda self: reports.append(self.outcome) or Path("report.json"))
    ctx = FakeJobContext()

    async def main():
        await voice.run_voice_interview(ctx)
        for callback in ctx.callbacks:
            await callback(ctx.reasons[-1])

    asyncio.run(main())
    return ctx, reports


def test_a_model_client_that_fails_to_build_ends_the_job_and_deletes_the_room_so_the_candidate_can_join_again(monkeypatch):
    """The live crash of S4: the Groq client failed inside the job, before the shutdown callback existed, so the room stayed and a new join
    could not dispatch again."""
    def broken(**_):
        raise RuntimeError("Plugins must be registered on the main thread")

    monkeypatch.setattr(voice, "GroqTurnClient", broken)
    ctx, reports = run_job(monkeypatch, {"AI_MODE": "llm", "GROQ_API_KEY": "gsk_test"})
    assert ctx.reasons == ["setup_failed: RuntimeError"] and ctx.deleted == 1 and reports == ["setup_failed: RuntimeError"]


def test_a_session_that_fails_to_start_closes_the_client_leaves_through_the_runner_and_deletes_the_room(monkeypatch):
    http = SimpleNamespace(closed=False)

    async def aclose():
        http.closed = True

    http.aclose = aclose
    left = []

    class FakeRunner:
        names, timings = (), []

        def __init__(self, *_, **__):
            pass

        async def open(self):
            pass

        async def leave(self, reason):
            left.append(reason)  # the real runner posts nothing here: no turn was stored

    class BrokenSession:
        turn_detection = "turn-detector-v1"

        def on(self, _name):
            return lambda fn: fn

        async def start(self, **_):
            raise ConnectionError("no room")

    monkeypatch.setattr(voice, "make_clients", lambda *_: (http, None))
    monkeypatch.setattr(voice, "InterviewRunner", FakeRunner)
    monkeypatch.setattr(voice, "build_session", lambda *_: BrokenSession())
    ctx, _reports = run_job(monkeypatch)
    assert ctx.reasons == ["setup_failed: ConnectionError"] and left == ["agent_error"] and http.closed and ctx.deleted == 1
