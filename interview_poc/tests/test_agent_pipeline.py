"""The audio path of a REAL AgentSession, run offline: scripted STT events and a fake microphone instead of a network.

This is the real-SDK check that the masking is bound to the audio path (the path the PoC uses), not just unit-tested
in isolation: STT events -> `PracticeInterviewer.stt_node` -> end of turn -> `on_user_turn_completed` -> conductor.
Text input takes a different path (`session.run(user_input=...)` skips `on_user_turn_completed`), which is why this test
feeds speech events and commits the turn instead.

A control runs the same pipeline with a plain Agent: it must call the LLM, otherwise "the PoC agent does not" proves nothing.
"""
import asyncio

import pytest
from livekit import rtc
from livekit.agents import Agent, AgentSession, stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN
from livekit.agents.voice import io

import agent as poc
from groq_llm import VoiceGroq
from test_groq_llm import FakeClient

RAW = "제 이름은 김철수이고 박서준 팀에서 010-1234-5678 번호로 일했습니다. 멱등성은 중요합니다."
SECRETS = ("김철수", "박서준", "1234", "5678")


class FakeMicrophone(io.AudioInput):
    """Silent 20 ms frames, so the STT node has audio to forward."""

    def __init__(self):
        super().__init__(label="fake-microphone")

    async def __anext__(self):
        await asyncio.sleep(0.02)
        return rtc.AudioFrame(data=bytes(640), sample_rate=16000, num_channels=1, samples_per_channel=320)


class ScriptedStream(stt.RecognizeStream):
    def __init__(self, *, owner, conn_options, queue):
        super().__init__(stt=owner, conn_options=conn_options)
        self._queue = queue

    async def _run(self):
        async def drain():
            async for _ in self._input_ch:
                pass

        drain_task = asyncio.create_task(drain())
        try:
            while True:
                self._event_ch.send_nowait(await self._queue.get())
        finally:
            drain_task.cancel()


class ScriptedSTT(stt.STT):
    """Emits exactly the speech events a test puts in `queue`."""

    def __init__(self):
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True))
        self.queue: asyncio.Queue = asyncio.Queue()

    async def _recognize_impl(self, *args, **kwargs):
        raise NotImplementedError

    def stream(self, *, language=NOT_GIVEN, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return ScriptedStream(owner=self, conn_options=conn_options, queue=self.queue)


def speech(kind, text=None):
    alternatives = [stt.SpeechData(language="ko", text=text)] if text is not None else []
    return stt.SpeechEvent(type=kind, alternatives=alternatives)


async def wait_until(predicate, timeout=8.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.02)


async def one_spoken_turn(agent, llm, done):
    """Speak RAW once through a real session (manual turn commit) and wait until `done()`."""
    scripted = ScriptedSTT()
    session = AgentSession(stt=scripted, llm=llm, turn_handling={"turn_detection": "manual", "preemptive_generation": {"enabled": False}})
    session.input.audio = FakeMicrophone()
    transcribed = []
    session.on("user_input_transcribed", lambda ev: transcribed.append((ev.is_final, ev.transcript)))
    await session.start(agent=agent, record=False)
    try:
        scripted.queue.put_nowait(speech(stt.SpeechEventType.START_OF_SPEECH))
        scripted.queue.put_nowait(speech(stt.SpeechEventType.INTERIM_TRANSCRIPT, "제 이름은 김철수"))
        scripted.queue.put_nowait(speech(stt.SpeechEventType.FINAL_TRANSCRIPT, RAW))
        scripted.queue.put_nowait(speech(stt.SpeechEventType.END_OF_SPEECH))
        await wait_until(lambda: any(final for final, _ in transcribed))
        session.commit_user_turn()
        await wait_until(done)
    finally:
        await session.aclose()
    return transcribed


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 40))


def test_spoken_personal_data_is_masked_before_the_hook_the_events_and_the_llm():
    received = []
    client = FakeClient()
    llm = VoiceGroq(model="openai/gpt-oss-120b", api_key="test-key", client=client)

    class RecordingConductor:
        async def on_candidate_turn(self, text):
            received.append(text)

    interviewer = poc.PracticeInterviewer(names=("박서준",))
    interviewer.conductor = RecordingConductor()
    transcribed = run(one_spoken_turn(interviewer, llm, done=lambda: bool(received)))

    # the events the session (and so the page and the logs) saw: interim and final, both masked
    assert [final for final, _ in transcribed] == [False, True]
    for _, text in transcribed:
        assert not any(s in text for s in SECRETS), text
    # the real on_user_turn_completed got the masked turn, exactly once
    assert received == ["제 이름은 [이름]이고 [이름] 팀에서 [전화번호] 번호로 일했습니다. 멱등성은 중요합니다."]
    # and StopResponse kept the default pipeline from calling the LLM at all (the conductor decides every reply)
    assert client.calls == []


def test_control_a_plain_agent_does_call_the_llm_so_the_check_above_means_something():
    client = FakeClient()
    llm = VoiceGroq(model="openai/gpt-oss-120b", api_key="test-key", client=client)
    plain = Agent(instructions="Answer briefly.")
    run(one_spoken_turn(plain, llm, done=lambda: bool(client.calls)))
    assert len(client.calls) == 1  # the default reply path reached the (fake) model
    assert [m["role"] for m in client.calls[0]["messages"]][-1] == "user"  # and it is the user turn, never a trailing assistant message
