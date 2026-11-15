"""How the LiveKit agent is wired. Real SDK objects where they are cheap to build; no room, audio, network or key.

Honest limit: nothing here runs the audio path (VAD -> STT -> end of turn -> hook) end to end. That path was read in the
SDK source (agent_activity.py `_user_turn_completed_task`) and has to be checked live with a microphone.
"""
import asyncio
import inspect
import re
from types import SimpleNamespace

import pytest
from livekit import rtc
from livekit.agents import Agent, stt
from livekit.agents.llm import ChatMessage, StopResponse

import agent as poc
from config import Settings
from groq_llm import MAX_OUTPUT_TOKENS, VoiceGroq
from guards import NAME

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
