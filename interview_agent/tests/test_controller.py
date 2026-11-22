"""The rules of the voice conversation (M5 S4; docs/DECISIONS.md D54, D79), with a fake runner and a fake voice: no LiveKit, no backend.

The same controller runs against the real runner and the real application in backend/tests/test_interview_voice_controller.py."""
import asyncio

import pytest

from interview_agent.controller import GREETING, VoiceController
from interview_agent.runner import Stopped
from interview_agent.timing import SessionTiming


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeRunner:
    """What the controller uses of `InterviewRunner`: `engine`, `finished`, `stopped`, `timings`, and the async calls."""

    def __init__(self):
        self.engine = object()
        self.finished = False
        self.stopped = None
        self.timings = []
        self.calls = []
        self.start_lines = ["첫 질문입니다."]
        self.answers = []  # one item per answer: a list of lines, or an exception to raise
        self.answer_delay = 0.0
        self.silence_result = None
        self.check_result = {"status": "live", "ai_consent": True}
        self.left = []

    async def start(self):
        self.calls.append("start")
        return list(self.start_lines)

    async def answer(self, text):
        self.calls.append(("answer", text))
        if self.answer_delay:
            await asyncio.sleep(self.answer_delay)
        item = self.answers.pop(0) if self.answers else ["다음 질문입니다."]
        if isinstance(item, BaseException):
            raise item
        if item and item[-1].startswith("CLOSING"):
            self.finished, self.stopped = True, "completed"
        return item

    async def silence(self, seconds):
        self.calls.append(("silence", round(seconds, 1)))
        return self.silence_result

    async def check(self):
        self.calls.append("check")
        if isinstance(self.check_result, BaseException):
            raise self.check_result
        return self.check_result

    async def leave(self, reason):
        self.calls.append(("leave", reason))
        self.left.append(reason)
        self.finished, self.stopped = True, "aborted"


class Voice:
    """`say` and `interrupt` of the worker. `hold` makes a line last until released."""

    def __init__(self, fail=False):
        self.spoken = []
        self.interrupts = 0
        self.fail = fail
        self.hold = None

    async def say(self, text):
        self.spoken.append(text)
        if self.hold is not None:
            await self.hold.wait()
        return not self.fail

    def interrupt(self):
        self.interrupts += 1


def make(**kw):
    runner, voice, clock = kw.pop("runner", None) or FakeRunner(), kw.pop("voice", None) or Voice(), Clock()
    poll = kw.pop("poll", 5.0)
    controller = VoiceController(runner, say=voice.say, interrupt=voice.interrupt, clock=clock, status_poll_seconds=poll, **kw)
    return controller, runner, voice, clock


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 10))


async def settle(controller):
    while controller._tasks:
        await asyncio.gather(*list(controller._tasks), return_exceptions=True)


# ── The opening ──


def test_the_opening_says_it_is_an_ai_then_stores_the_first_question_then_speaks_it():
    async def go():
        controller, runner, voice, _ = make()
        await controller.run_opening()
        return controller, runner, voice

    controller, runner, voice = run(go())
    assert voice.spoken == [GREETING, "첫 질문입니다."] and "AI" in GREETING and "연습" in GREETING
    assert runner.calls == ["start"] and not controller.busy and not controller.done.is_set()


def test_an_answer_before_the_opening_is_over_is_dropped():
    async def go():
        controller, runner, voice, _ = make()
        voice.hold = asyncio.Event()  # the greeting is still being spoken
        opening = asyncio.create_task(controller.run_opening())
        await asyncio.sleep(0.01)
        accepted = controller.submit("너무 일찍 말한 답")
        voice.hold.set()
        await opening
        return accepted, controller, runner

    accepted, controller, runner = run(go())
    assert accepted is False and controller.dropped_turns == 1 and all(not isinstance(c, tuple) for c in runner.calls)


# ── One answer at a time ──


def test_an_answer_is_handled_and_its_lines_are_spoken_in_order():
    async def go():
        controller, runner, voice, _ = make()
        runner.answers = [["감사합니다.", "다음 질문입니다."]]
        await controller.run_opening()
        voice.spoken.clear()
        assert controller.submit("저는 Java로 개발했습니다.") is True and controller.busy
        await settle(controller)
        return controller, runner, voice

    controller, runner, voice = run(go())
    assert ("answer", "저는 Java로 개발했습니다.") in runner.calls and voice.spoken == ["감사합니다.", "다음 질문입니다."]
    assert not controller.busy and not controller.done.is_set()


def test_an_answer_while_busy_is_dropped_and_counted_and_the_first_one_is_not_disturbed():
    async def go():
        controller, runner, voice, _ = make(timing=SessionTiming(1))
        await controller.run_opening()
        runner.answer_delay = 0.05
        assert controller.submit("첫 답") is True
        assert controller.submit("겹친 답") is False and controller.submit("또 겹친 답") is False
        await settle(controller)
        return controller, runner

    controller, runner = run(go())
    assert [c for c in runner.calls if isinstance(c, tuple)] == [("answer", "첫 답")]
    assert controller.dropped_turns == 2 and controller.timing.dropped_turns == 2


def test_the_closing_line_is_spoken_and_then_the_interview_is_done():
    async def go():
        controller, runner, voice, _ = make()
        runner.answers = [["답변 감사합니다.", "CLOSING 수고하셨습니다."]]
        await controller.run_opening()
        controller.submit("마지막 답")
        await settle(controller)
        return controller, voice

    controller, voice = run(go())
    assert voice.spoken[-1] == "CLOSING 수고하셨습니다." and controller.done.is_set() and controller.outcome == "completed"
    assert controller.submit("끝난 뒤의 답") is False  # nothing is handled after the end


def test_a_line_that_could_not_be_spoken_is_counted_and_the_interview_goes_on():
    async def go():
        controller, runner, voice, _ = make(voice=Voice(fail=True), timing=SessionTiming(1))
        runner.answers = [["다음 질문입니다.", "CLOSING 끝."]]
        await controller.run_opening()
        controller.submit("답")
        await settle(controller)
        return controller

    controller = run(go())
    assert controller.speech_failures == 4 and controller.timing.speech_failures == 4  # the greeting, the question, two lines
    assert controller.outcome == "completed"


# ── Stopping ──


@pytest.mark.parametrize("reason", ["gone", "ended_elsewhere", "consent_withdrawn", "refused", "unreachable"])
def test_a_stop_from_the_runner_interrupts_the_speech_and_posts_and_says_nothing_more(reason):
    async def go():
        controller, runner, voice, _ = make()
        runner.answers = [Stopped(reason)]
        await controller.run_opening()
        voice.spoken.clear()
        controller.submit("답")
        await settle(controller)
        return controller, voice, runner

    controller, voice, runner = run(go())
    assert controller.outcome == reason and controller.done.is_set() and voice.interrupts == 1 and voice.spoken == []
    assert runner.left == []  # no end event from the controller: the runner decides what is posted


def test_the_status_poll_runs_every_few_seconds_and_stops_everything_when_the_session_is_over():
    async def go():
        controller, runner, voice, clock = make()
        await controller.run_opening()
        await controller.tick()
        assert "check" not in runner.calls  # not yet
        clock.advance(5)
        await controller.tick()
        assert runner.calls.count("check") == 1
        runner.check_result = Stopped("consent_withdrawn")
        clock.advance(5)
        await controller.tick()
        return controller, voice

    controller, voice = run(go())
    assert controller.outcome == "consent_withdrawn" and controller.done.is_set() and voice.interrupts == 1


def test_an_unreadable_status_is_not_a_stop():
    async def go():
        controller, runner, voice, clock = make()
        runner.check_result = None  # the runner's answer when the backend did not respond
        await controller.run_opening()
        clock.advance(6)
        await controller.tick()
        return controller

    assert not run(go()).done.is_set()


def test_the_candidate_leaving_posts_the_aborted_end_and_speaks_nothing():
    async def go():
        controller, runner, voice, _ = make()
        await controller.run_opening()
        voice.spoken.clear()
        await controller.candidate_left()
        await controller.candidate_left()  # a second departure changes nothing
        return controller, runner, voice

    controller, runner, voice = run(go())
    assert runner.left == ["candidate_left"] and controller.outcome == "aborted" and voice.spoken == []


def test_a_closed_transport_is_an_aborted_end_with_its_reason():
    async def go():
        controller, runner, voice, _ = make()
        await controller.run_opening()
        await controller.candidate_left("session_closed:participant_disconnected")
        return runner

    assert run(go()).left == ["session_closed:participant_disconnected"]


def test_an_unexpected_error_aborts_with_agent_error_and_stops():
    async def go():
        controller, runner, voice, _ = make()
        runner.answers = [RuntimeError("boom")]
        await controller.run_opening()
        controller.submit("답")
        await settle(controller)
        return controller, runner, voice

    controller, runner, voice = run(go())
    assert runner.left == ["agent_error"] and controller.outcome == "agent_error" and voice.interrupts == 1


def test_finishing_cancels_an_answer_that_is_still_being_handled():
    async def go():
        controller, runner, voice, _ = make()
        runner.answer_delay = 5
        await controller.run_opening()
        controller.submit("느린 답")
        await asyncio.sleep(0.02)
        assert controller.busy
        await controller.finish("gone")
        await asyncio.sleep(0.02)
        return controller

    controller = run(go())
    assert controller.outcome == "gone" and not controller.busy and not controller._tasks


def test_the_first_outcome_stays():
    async def go():
        controller, *_ = make()
        await controller.finish("completed")
        await controller.finish("gone")
        return controller

    assert run(go()).outcome == "completed"


# ── Silence ──


def test_silence_is_counted_from_the_end_of_the_opening_and_only_while_nobody_speaks():
    async def go():
        controller, runner, voice, clock = make(poll=1000.0)  # the status poll has its own test
        runner.silence_result = ["천천히 생각하셔도 됩니다."]
        await controller.run_opening()
        clock.advance(21)
        await controller.tick()
        spoken_after_silence = list(voice.spoken)
        runner.calls.clear()
        controller.set_candidate_speaking(True)
        clock.advance(30)
        await controller.tick()  # the candidate is speaking: no silence is counted
        controller.set_candidate_speaking(False)
        clock.advance(2)
        await controller.tick()
        return runner.calls, spoken_after_silence

    calls, spoken = run(go())
    assert spoken[-1] == "천천히 생각하셔도 됩니다."
    assert calls == [("silence", 2.0)]  # the speech of the candidate reset the clock: two seconds since it stopped


def test_no_silence_is_handed_over_while_an_answer_is_being_handled_or_when_the_runner_is_finished():
    async def go():
        controller, runner, voice, clock = make()
        await controller.run_opening()
        runner.answer_delay = 0.05
        controller.submit("답")
        clock.advance(30)
        await controller.tick()
        busy_calls = [c for c in runner.calls if isinstance(c, tuple) and c[0] == "silence"]
        await settle(controller)
        runner.finished = True
        clock.advance(30)
        await controller.tick()
        return busy_calls, [c for c in runner.calls if isinstance(c, tuple) and c[0] == "silence"]

    busy_calls, all_calls = run(go())
    assert busy_calls == [] and all_calls == []


def test_the_silence_of_a_stop_is_handled_like_any_other_stop():
    async def go():
        controller, runner, voice, clock = make()
        await controller.run_opening()

        async def stops(seconds):
            raise Stopped("ended_elsewhere")

        runner.silence = stops
        clock.advance(25)
        await controller.tick()
        return controller

    assert run(go()).outcome == "ended_elsewhere"


# ── The report ──


def test_the_controller_hands_the_marks_to_the_timing_report():
    async def go():
        timing = SessionTiming(5, clock=Clock())
        controller, runner, voice, _ = make(timing=timing)
        runner.timings = []
        await controller.run_opening()
        timing.mark("user_stopped")
        timing.mark("turn_committed")
        runner.answers = [["다음 질문입니다."]]
        controller.submit("답")
        await settle(controller)
        return timing

    timing = run(go())
    turn = timing.turns[0]
    assert {"user_stopped", "turn_committed", "runner_done", "say_called"} <= set(turn)
    assert "say_called" in timing.opening
