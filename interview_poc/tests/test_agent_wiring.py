"""How the LiveKit agent is wired. Real SDK objects where they are cheap to build; no room, audio, network or key.

Honest limit: nothing here runs the audio path (VAD -> STT -> end of turn -> hook) end to end. That path was read in the
SDK source (agent_activity.py `_user_turn_completed_task`) and has to be checked live with a microphone.
"""
import asyncio
import inspect
import logging
import re
from types import SimpleNamespace

import pytest
from livekit import rtc
from livekit.agents import Agent, AgentSession, inference, stt
from livekit.agents.inference.eot.base import _BaseStreamingTurnDetectorStream
from livekit.agents.inference.eot.languages import LOCAL_LANGUAGES
from livekit.agents.llm import ChatMessage, StopResponse
from livekit.agents.voice.endpointing import BaseEndpointing, create_endpointing
from livekit.plugins import silero

import agent as poc
from config import ENDPOINTING_MAX_DELAY_SECONDS, ENDPOINTING_MIN_DELAY_SECONDS, TURN_DETECTOR_VERSION, Settings
from groq_llm import MAX_OUTPUT_TOKENS, VoiceGroq
from guards import NAME
from metrics import RunMetrics

ON = Settings(avatar_enabled=True)
OFF = Settings(avatar_enabled=False)


def test_room_options_publish_nothing_extra_and_send_audio_to_the_avatar_only():
    on, off = poc.room_options(ON), poc.room_options(OFF)
    assert on.audio_output is False and off.audio_output is True  # avatar mode: agent audio goes to the avatar worker
    for opts in (on, off):
        assert opts.video_input is False  # the camera is never used
        assert opts.text_input is False and opts.text_output is False  # only the masked lines of poc.event reach the page
        assert opts.close_on_disconnect is True
        assert opts.delete_room_on_close is True  # documented RoomOptions field: the room goes as soon as the session ends


def test_the_session_uses_the_plugin_llm_and_no_preemptive_reply(monkeypatch):
    for name, value in (("LIVEKIT_URL", "wss://example.livekit.cloud"), ("LIVEKIT_API_KEY", "devkey"), ("LIVEKIT_API_SECRET", "s" * 40)):
        monkeypatch.setenv(name, value)
    settings = Settings(groq_api_key="test-key", llm_model="openai/gpt-oss-120b", reasoning_effort="low", avatar_enabled=True)

    async def build():
        return poc.build_session(settings, vad=None)

    session, llm = asyncio.run(build())
    assert isinstance(llm, VoiceGroq) and session.llm is llm and llm.model == "openai/gpt-oss-120b"
    assert llm.provider == "api.groq.com"  # the only LLM host of the PoC
    assert llm._opts.reasoning_effort == "low" and llm._opts.max_completion_tokens == MAX_OUTPUT_TOKENS
    assert session._opts.turn_handling["preemptive_generation"]["enabled"] is False  # a reply must never start on a raw, unfinished transcript


def _built_session(monkeypatch):
    """A real AgentSession as `build_session` makes it (no VAD, no room, no network). Dummy LiveKit credentials: the explicit
    v1 detector and the Inference STT/TTS read them at construction, and nothing connects until a session starts."""
    for name, value in (("LIVEKIT_URL", "wss://example.livekit.cloud"), ("LIVEKIT_API_KEY", "devkey"), ("LIVEKIT_API_SECRET", "s" * 40)):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LIVEKIT_DEV_MODE", raising=False)
    settings = Settings(groq_api_key="test-key", llm_model="openai/gpt-oss-120b", reasoning_effort="low", avatar_enabled=True)

    async def build():
        return poc.build_session(settings, vad=None)

    session, _ = asyncio.run(build())
    return session


def test_endpointing_gives_a_thinking_candidate_time_before_the_turn_ends(monkeypatch):
    """History: SDK default 0.3 s / 2.5 s (a ~1 s pause ended the turn), then 1.5 s / 5.0 s (a live run still cut the candidate off)."""
    assert (ENDPOINTING_MIN_DELAY_SECONDS, ENDPOINTING_MAX_DELAY_SECONDS) == (3.0, 6.0)
    session = _built_session(monkeypatch)
    endpointing = session.options.endpointing
    assert (endpointing["mode"], endpointing["min_delay"], endpointing["max_delay"]) == ("fixed", 3.0, 6.0)
    created = create_endpointing(endpointing)
    assert type(created) is BaseEndpointing  # fixed delays, not the dynamic (learning) variant
    assert (created.min_delay, created.max_delay) == (3.0, 6.0)


def test_the_session_asks_for_the_full_v1_turn_detector_with_local_fallback(monkeypatch):
    """Without `version`, `agent.py start` silently runs the local v1-mini (dev/console run v1): the version must be explicit."""
    assert TURN_DETECTOR_VERSION == "v1"
    session = _built_session(monkeypatch)
    detector = session.turn_detection
    assert isinstance(detector, inference.TurnDetector)
    assert detector.model == "turn-detector-v1"  # the cloud model, not "turn-detector-v1-mini"
    assert detector.describe_options()["local_fallback"] is True  # a failure, timeout or used-up allowance degrades to the mini
    assert "local_fallback=True" in inspect.getsource(poc.build_session)  # stated here, not left to the SDK default
    assert "ko" in LOCAL_LANGUAGES  # the model a fallback lands on ships a Korean threshold in the pinned SDK


def test_explicit_v1_needs_livekit_credentials_instead_of_silently_using_the_mini(monkeypatch):
    for name in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_INFERENCE_API_KEY", "LIVEKIT_INFERENCE_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="LIVEKIT_API_KEY"):
        inference.TurnDetector(version="v1")  # an explicit v1 never degrades quietly at construction


def test_the_korean_stt_configuration_is_unchanged(monkeypatch):
    session = _built_session(monkeypatch)
    assert (poc.STT_MODEL, poc.LANGUAGE) == ("deepgram/nova-3", "ko")
    assert session.stt.model == "deepgram/nova-3"
    assert str(session.stt._opts.language) == "ko"  # explicit Korean, no auto-detection and no "multi"
    assert session.stt._opts.extra_kwargs == {}  # no keyterm biasing or other Deepgram options in this change


def test_silero_vad_settings_are_unchanged():
    """The delay is measured from the last speech, so a minimum below Silero's own silence window changes nothing (the original bug)."""
    defaults = {name: p.default for name, p in inspect.signature(silero.VAD.load).parameters.items()}
    assert defaults["min_silence_duration"] == 0.55  # SDK defaults, and prewarm passes no override
    assert defaults["min_speech_duration"] == 0.05
    assert defaults["activation_threshold"] == 0.5
    assert defaults["prefix_padding_duration"] == 0.5
    assert "silero.VAD.load()" in inspect.getsource(poc.prewarm)
    assert ENDPOINTING_MIN_DELAY_SECONDS > defaults["min_silence_duration"]
    assert ENDPOINTING_MAX_DELAY_SECONDS >= ENDPOINTING_MIN_DELAY_SECONDS


def test_preemptive_generation_and_interruption_are_untouched_by_the_turn_detection_change(monkeypatch):
    session = _built_session(monkeypatch)
    assert session.options.preemptive_generation["enabled"] is False  # same turn_handling dict as the endpointing

    async def baseline():
        return AgentSession(vad=None).options.interruption  # no turn_handling at all: the SDK's interruption defaults

    assert dict(session.options.interruption) == dict(asyncio.run(baseline()))


def test_the_detector_model_is_logged_at_startup_and_watched_for_the_whole_session(monkeypatch):
    session = _built_session(monkeypatch)
    assert poc.turn_detection_label(session) == "turn-detector-v1"
    assert poc.turn_detection_label(SimpleNamespace(turn_detection="vad")) == "vad"  # a mode string has no model attribute
    assert poc.turn_detection_label(SimpleNamespace(turn_detection=None)) == "None"
    source = inspect.getsource(poc.run_interview)  # a lint: the watch starts right after the session is built, before it runs
    assert source.index("build_session(") < source.index("TurnDetectorWatch(") < source.index("session.start(")
    assert "turn detection: requested=%s, local_fallback=on, model=%s" in source  # the one-time startup line
    assert source.count("watch.check(") >= 3  # agent state, user state and SDK metric events
    assert 'state["watch"].check("shutdown")' in source  # a fallback in the last seconds still reaches the report


class _IdleTransport:
    """Stands in for the cloud connection so no socket is opened: it never answers and only has to exist."""

    session_id = None

    def attach(self, stream):
        pass

    def detach(self):
        pass

    def push_frame(self, frame):
        pass

    def run_inference(self, request_id, *, chat_ctx=None):
        pass

    def on_start_of_turn(self, elapsed):
        pass

    def flush(self):
        pass

    async def run(self):
        await asyncio.sleep(3600)


def _fallback_scenario(local_fallback: bool):
    """Real SDK detector and stream classes, a fake transport: what the watch sees when the SDK swaps the model."""

    async def scenario():
        detector = inference.TurnDetector(
            version="v1", api_key="k", api_secret="s", base_url="https://example.invalid", local_fallback=local_fallback
        )
        stream = _BaseStreamingTurnDetectorStream(
            detector=detector, opts=detector._opts, transport=_IdleTransport(), model="turn-detector-v1", local_fallback=local_fallback
        )
        metrics = RunMetrics()
        watch = poc.TurnDetectorWatch(SimpleNamespace(turn_detection=detector), metrics, requested="v1")
        await asyncio.sleep(0.05)  # the stream's transport task is running, as in a session
        switched = stream._fallback_to_local(reason=TimeoutError("eot prediction timed out"))  # what a timeout or an Inference error does
        await asyncio.sleep(0.05)
        noticed = watch.check("test")
        result = SimpleNamespace(
            switched=switched,
            noticed=noticed,
            detector_model=detector.model,
            stream_model=stream.model,
            stream_is_fallback=stream.is_fallback,
            report=metrics.summary()["turn_detector"],
        )
        await stream.aclose()
        return result

    return asyncio.run(scenario())


def test_a_runtime_fallback_to_the_local_model_is_observable():
    """Pinned-SDK contract the watch relies on (livekit-agents 1.8.12): the detector's public `model` follows the fallback."""
    r = _fallback_scenario(local_fallback=True)
    assert r.switched is True and r.noticed is True
    assert r.detector_model == r.stream_model == "turn-detector-v1-mini" and r.stream_is_fallback is True
    assert r.report["requested"] == "v1" and r.report["model_at_start"] == "turn-detector-v1"
    assert r.report["model_at_end"] == "turn-detector-v1-mini" and r.report["fell_back"] is True
    assert r.report["fallback_at_s"] is not None and r.report["cloud_predictions"] == 0


def test_without_local_fallback_the_model_would_not_change_which_is_why_it_stays_on():
    r = _fallback_scenario(local_fallback=False)
    assert r.switched is False and r.noticed is False and r.detector_model == "turn-detector-v1"
    assert r.report["fell_back"] is False and "fallback_at_s" not in r.report


def test_the_watch_reports_a_fallback_once_in_the_log_and_the_run_report(caplog):
    detector = SimpleNamespace(model="turn-detector-v1")
    metrics = RunMetrics()
    watch = poc.TurnDetectorWatch(SimpleNamespace(turn_detection=detector), metrics, requested="v1")
    assert watch.initial == "turn-detector-v1"
    with caplog.at_level(logging.WARNING, logger="interview_poc.agent"):
        assert watch.check("user_state") is False  # unchanged: silent
        assert caplog.records == []
        detector.model = "turn-detector-v1-mini"  # the SDK swaps the model in place
        assert watch.check("user_state") is True
        assert watch.check("metrics") is False and watch.check("shutdown") is False  # said once, not on every event
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert "turn-detector-v1 -> turn-detector-v1-mini" in message and "user_state" in message
    marks = [m for m in metrics.marks if m["name"] == "turn_detector_fallback"]
    assert len(marks) == 1 and marks[0]["from_model"] == "turn-detector-v1" and marks[0]["to_model"] == "turn-detector-v1-mini"
    assert metrics.summary()["turn_detector"]["fell_back"] is True


def test_the_turn_hook_masks_the_message_and_suppresses_the_default_reply():
    received = []

    class FakeConductor:
        async def on_candidate_turn(self, text):
            received.append(text)

    async def scenario():
        interviewer = poc.PracticeInterviewer(names=("박서준",))
        interviewer.conductor = FakeConductor()
        message = ChatMessage(role="user", content=["제 이름은 박서준이고 010-1234-5678 입니다. 멱등성은 중요합니다."])
        with pytest.raises(StopResponse):
            await interviewer.on_user_turn_completed(None, message)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return message

    message = asyncio.run(scenario())
    assert "박서준" not in message.text_content and "1234" not in message.text_content  # what the framework would send on
    assert NAME in message.text_content and "[전화번호]" in message.text_content
    assert received == [message.text_content]  # the conductor gets the masked text


def test_the_stt_node_masks_interim_and_final_transcripts(monkeypatch):
    def event(kind, text):
        return stt.SpeechEvent(type=kind, alternatives=[stt.SpeechData(language="ko", text=text)])

    async def fake_default(agent, audio, model_settings):
        yield event(stt.SpeechEventType.INTERIM_TRANSCRIPT, "제 이름은 김철수")
        yield event(stt.SpeechEventType.FINAL_TRANSCRIPT, "제 이름은 김철수입니다 메일은 kim@example.com")
        yield stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)

    monkeypatch.setattr(Agent.default, "stt_node", staticmethod(fake_default))

    async def collect():
        interviewer = poc.PracticeInterviewer()
        return [e async for e in interviewer.stt_node(None, None)]

    events = asyncio.run(collect())
    texts = [e.alternatives[0].text for e in events if e.alternatives]
    assert texts == [f"제 이름은 {NAME}", f"제 이름은 {NAME}입니다 메일은 [이메일]"]  # interim and final, both masked
    assert len(events) == 3  # nothing dropped: only the text changed


def _participant(kind, ready=None):
    attributes = {poc.READY_ATTRIBUTE: ready} if ready is not None else {}
    return SimpleNamespace(kind=kind, attributes=attributes)


def _room(*participants):
    return SimpleNamespace(
        remote_participants={f"p{i}": p for i, p in enumerate(participants)},
        on=lambda *a, **k: None,
        off=lambda *a, **k: None,
    )


def test_the_agent_waits_for_the_candidate_page_before_speaking():
    standard, agent_kind = rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD, rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
    assert asyncio.run(poc.wait_candidate_ready(_room(_participant(standard, "1")), timeout=0.2)) is True
    assert asyncio.run(poc.wait_candidate_ready(_room(_participant(standard)), timeout=0.05)) is False  # not ready: start anyway, after the timeout
    assert asyncio.run(poc.wait_candidate_ready(_room(_participant(agent_kind, "1")), timeout=0.05)) is False  # an agent cannot vouch for the candidate


def test_the_interview_ends_when_the_candidate_leaves_for_any_reason():
    """close_on_disconnect only covers CLIENT_INITIATED, ROOM_DELETED and USER_REJECTED; a dropped connection is not covered."""
    standard, agent_kind = rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD, rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
    aborted, spawned = [], []

    class FakeConductor:
        def abort(self, reason):
            aborted.append(reason)
            return ("abort", reason)

    handler = poc.candidate_left_handler(FakeConductor(), spawned.append)
    handler(SimpleNamespace(kind=agent_kind))  # the agent or the avatar worker leaving is not the candidate
    assert aborted == [] and spawned == []
    handler(SimpleNamespace(kind=standard))
    assert aborted == ["candidate_left"] and spawned == [("abort", "candidate_left")]


def test_privacy_and_lifecycle_settings_are_present_in_the_entrypoint():
    """A lint, not a behaviour test: these lines are the privacy and shutdown rules of the PoC."""
    source = inspect.getsource(poc.run_interview)
    assert "record=False" in source  # no audio, transcript, trace or log upload to LiveKit Cloud (the default follows a project setting)
    assert "AutoSubscribe.AUDIO_ONLY" in source
    assert "show_ai_avatar_disclosure=True" in source
    assert "wait_for_join" in source
    assert source.index("avatar.start(") < source.index("session.start(") < source.index("conductor.run_opening()")  # avatar first, then the interview
    assert re.search(r"session\.shutdown\(drain=True\).*?closed\.wait\(\).*?ctx\.shutdown\(", source, re.S)  # request, confirm the close event, then leave
    assert "delete_room" in source
    assert 'ctx.room.on("participant_disconnected"' in source  # the candidate leaving ends the (billed) avatar session
