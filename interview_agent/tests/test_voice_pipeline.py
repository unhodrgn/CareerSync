"""The audio path of a REAL AgentSession, run offline: scripted recognizer events and a fake microphone instead of a network (M5 S4).

This is the real-SDK check that the masking and the hand-over are bound to the audio path the worker uses, not only unit-tested in isolation:
recognizer events -> `InterviewerAgent.stt_node` -> end of turn -> `on_user_turn_completed` -> the controller's `submit`. Text input takes
another path (`session.run(user_input=...)` skips `on_user_turn_completed`), which is why this feeds speech events and commits the turn.

The session has no LLM, as in `build_session`: the test also proves that with none the SDK still delivers the turn to the hook and then asks
for no reply. A control runs the same pipeline with a session that has an LLM: it must call it, otherwise "ours does not" proves nothing.
(The approach is that of the PoC's tests/test_agent_pipeline.py, which is its model.)"""
import asyncio

import pytest
from livekit import rtc
from livekit.agents import Agent, AgentSession, llm, stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN
from livekit.agents.voice import io

from interview_agent import voice

RAW = "제 이름은 김철수이고 박서준 팀에서 010-1234-5678 번호로 일했습니다. 멱등성은 중요합니다."
SECRETS = ("김철수", "박서준", "1234", "5678")


class FakeMicrophone(io.AudioInput):
    """Silent 20 ms frames, so that the recognizer node has audio to forward."""

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


class CountingLLM(llm.LLM):
    """A model that records every request. Used only by the control."""

    def __init__(self):
        super().__init__()
        self.requests = 0

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        self.requests += 1
        raise RuntimeError("the control's model was asked for a reply")  # the control only needs to see that it is asked


def speech(kind, text=None):
    alternatives = [stt.SpeechData(language="ko", text=text)] if text is not None else []
    return stt.SpeechEvent(type=kind, alternatives=alternatives)


async def wait_until(predicate, timeout=8.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.02)


async def one_spoken_turn(agent, session_llm, done):
    """Speak RAW once through a real session (manual turn commit) and wait until `done()`."""
    scripted = ScriptedSTT()
    kwargs = {"llm": session_llm} if session_llm is not None else {}
    session = AgentSession(stt=scripted, turn_handling={"turn_detection": "manual", "preemptive_generation": {"enabled": False}}, **kwargs)
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
    return session, transcribed


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 40))


def test_spoken_personal_data_is_masked_before_the_hook_and_the_events_and_the_session_asks_no_model():
    received = []
    agent = voice.InterviewerAgent(("박서준",))
    agent.on_turn = received.append
    session, transcribed = run(one_spoken_turn(agent, None, done=lambda: bool(received)))
    assert session.llm is None  # nothing could be asked: there is no model on the session
    interim = [text for final, text in transcribed if not final]
    final = [text for is_final, text in transcribed if is_final]
    assert interim and final, "the session heard interim and final transcripts"
    for text in [*interim, *final, *received]:
        for secret in SECRETS:
            assert secret not in text, (secret, text)
    assert "멱등성은 중요합니다" in received[0] and len(received) == 1  # the professional content stays, and one turn is one hand-over


def test_the_control_a_session_with_a_model_does_ask_it_for_a_reply():
    """Without this the test above would prove nothing: a plain agent on a session that has an LLM asks it, and ours, on one that has none, does not."""
    model = CountingLLM()
    plain = Agent(instructions="control")
    run(one_spoken_turn(plain, model, done=lambda: model.requests > 0))
    assert model.requests >= 1
