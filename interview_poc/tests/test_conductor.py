"""The interview flow, driven with fakes: no LiveKit, no audio, no network, no key."""
import asyncio

import pytest

import prompts
from conductor import Hooks, InterviewConductor, SayOutcome, Stage
from groq_llm import LlmResult, LlmUnavailable
from metrics import RunMetrics

GOOD_FOLLOWUP = "방금 말씀하신 멱등 키는 어떻게 만료 시간을 관리하나요?"
GOOD_CLOSING = "멱등 키 사례까지 들어 설명해 주셔서 감사합니다."
ANSWER_1 = "멱등성은 같은 요청을 여러 번 보내도 결과가 같은 성질이라 결제 재시도에 중요합니다."
ANSWER_2 = "멱등 키를 헤더에 넣고 서버가 같은 키의 결과를 저장해 두었다가 돌려줍니다."


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class Harness:
    def __init__(self, outputs=(GOOD_FOLLOWUP, GOOD_CLOSING), llm_error=None, deliver=True, **timing):
        self.clock = Clock()
        self.said, self.shown, self.llm_calls, self.ended = [], [], [], []
        self.outputs = list(outputs)
        self.llm_error = llm_error
        self.deliver = deliver

        async def say(text, step, n):
            self.said.append((step, text))
            return SayOutcome(self.deliver, f"speech-{len(self.said)}")

        async def show(role, text, n):
            self.shown.append((role, text))

        async def complete(system, user):
            self.llm_calls.append((system, user))
            await asyncio.sleep(0.01)  # a real call suspends: other turns can arrive meanwhile
            if self.llm_error:
                raise self.llm_error
            return LlmResult(self.outputs.pop(0), 0.4, 0.9, "openai/gpt-oss-120b")

        async def end(reason):
            self.ended.append(reason)

        self.metrics = RunMetrics(clock=self.clock)
        self.conductor = InterviewConductor(Hooks(say, show, complete, end, self.clock), self.metrics, **timing)

    def run(self, coro):
        return asyncio.run(coro)

    @property
    def spoken(self):
        return " ".join(text for _, text in self.said)


def opened(**kw):
    h = Harness(**kw)
    h.run(h.conductor.run_opening())
    return h


def test_opening_discloses_the_ai_then_asks_one_predefined_question():
    h = opened()
    assert [step for step, _ in h.said] == ["opening", "question"]
    assert "AI" in h.said[0][1] and "가상 아바타" in h.said[0][1]  # clear disclosure, spoken first
    assert h.said[1][1] == prompts.QUESTION
    assert h.conductor.stage is Stage.WAIT_ANSWER_1 and h.llm_calls == []  # the script needs no LLM


def test_full_interview_flow():
    h = opened()

    async def interview():
        await h.conductor.on_candidate_turn(ANSWER_1)
        assert h.conductor.stage is Stage.WAIT_ANSWER_2
        await h.conductor.on_candidate_turn(ANSWER_2)

    h.run(interview())
    assert [step for step, _ in h.said] == ["opening", "question", "followup", "closing"]
    assert h.said[2][1] == GOOD_FOLLOWUP
    assert GOOD_CLOSING in h.said[3][1] and prompts.CLOSING_SUFFIX in h.said[3][1]
    assert h.ended == ["completed"] and h.conductor.stage is Stage.ENDED
    assert len(h.llm_calls) == 2  # one follow-up, one closing reply
    assert [role for role, _ in h.conductor.transcript] == ["agent", "agent", "candidate", "agent", "candidate", "agent"]
    summary = h.metrics.summary()
    assert summary["end_reason"] == "completed" and [t["turn"] for t in summary["turns"]] == [1, 2]
    assert summary["turns"][0]["llm_total_s"] == 0.9 and summary["turns"][0]["llm_ttft_s"] == 0.4


def test_nothing_the_ai_says_scores_or_decides():
    h = opened()
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    h.run(h.conductor.on_candidate_turn(ANSWER_2))
    for word in ("합격", "불합격", "탈락", "점수", "채용"):
        assert word not in h.spoken.replace("점수나 합격 여부는 판단하지 않습니다", "")  # only the disclosure may name them, to deny them


def test_no_raw_personal_data_reaches_the_llm_the_page_or_the_transcript():
    h = opened()
    raw_1 = "제 이름은 김철수이고 연락처는 010-1234-5678, 메일은 kim@example.com 입니다. " + ANSWER_1
    raw_2 = "참고로 제 번호는 공일공 일이삼사 오육칠팔이고, " + ANSWER_2
    h.run(h.conductor.on_candidate_turn(raw_1))
    h.run(h.conductor.on_candidate_turn(raw_2))
    sent_to_llm = "\n".join(system + "\n" + user for system, user in h.llm_calls)
    shown = "\n".join(text for _, text in h.shown)
    kept = "\n".join(text for _, text in h.conductor.transcript)
    for secret in ("김철수", "1234", "5678", "kim@example", "일이삼사"):
        assert secret not in sent_to_llm and secret not in shown and secret not in kept
    assert "[이름]" in sent_to_llm and "[전화번호]" in sent_to_llm and "[이메일]" in sent_to_llm
    assert ANSWER_1 in sent_to_llm  # the technical content itself is kept


def test_configured_synthetic_names_are_masked_before_the_llm():
    h = Harness(names=("박서준",))
    h.run(h.conductor.run_opening())
    h.run(h.conductor.on_candidate_turn("박서준이 만든 결제 서비스에서 멱등 키를 썼습니다."))
    assert "박서준" not in h.llm_calls[0][1] and "[이름]" in h.llm_calls[0][1]


def test_the_llm_sees_only_the_question_and_the_masked_answers():
    h = opened()
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    h.run(h.conductor.on_candidate_turn(ANSWER_2))
    follow_up_input, closing_input = h.llm_calls[0][1], h.llm_calls[1][1]
    assert follow_up_input == prompts.followup_input(prompts.QUESTION, ANSWER_1)
    assert closing_input == prompts.closing_input(prompts.QUESTION, ANSWER_1, GOOD_FOLLOWUP, ANSWER_2)


def test_a_bad_followup_is_replaced_by_the_fixed_question_not_spoken():
    h = opened(outputs=("결혼은 하셨나요?", GOOD_CLOSING))
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    assert h.said[-1] == ("followup", prompts.FALLBACK_FOLLOWUP)
    assert "결혼" not in h.spoken and h.conductor.fallbacks == ["followup"]


def test_a_bad_closing_is_replaced_by_the_fixed_line():
    h = opened(outputs=(GOOD_FOLLOWUP, "합격하실 것 같습니다. 점수는 90점입니다."))
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    h.run(h.conductor.on_candidate_turn(ANSWER_2))
    assert h.said[-1] == ("closing", prompts.FALLBACK_CLOSING)
    assert "합격하실" not in h.spoken and h.ended == ["completed"]


NATURAL_CLOSING = "결제 재시도 상황에서 멱등성을 강조해 설명해 주신 점이 인상적이었습니다. 감사합니다."
# The reply that failed the first live Groq check: a placeholder used as the candidate's name
PLACEHOLDER_CLOSING = "[이름]님, 결제 재시도 상황에서 멱등성을 강조한 설명이 인상적였습니다. 감사합니다."
PLACEHOLDER_FOLLOWUP = "[이름]님은 멱등 키를 어떻게 만료시키나요?"


def screen_fallback_steps(h):
    return [m["step"] for m in h.metrics.marks if m["name"] == "screen_fallback"]


def test_valid_replies_are_spoken_as_written_without_fallback():
    h = opened(outputs=(GOOD_FOLLOWUP, NATURAL_CLOSING))
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    h.run(h.conductor.on_candidate_turn(ANSWER_2))
    assert h.said[2] == ("followup", GOOD_FOLLOWUP)
    assert h.said[3] == ("closing", f"{NATURAL_CLOSING} {prompts.CLOSING_SUFFIX}")
    assert h.conductor.fallbacks == [] and screen_fallback_steps(h) == []
    assert h.ended == ["completed"]


def test_a_closing_with_a_placeholder_speaks_the_fixed_line_and_the_session_still_completes():
    h = opened(outputs=(GOOD_FOLLOWUP, PLACEHOLDER_CLOSING))
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    h.run(h.conductor.on_candidate_turn(ANSWER_2))
    assert h.said[-1] == ("closing", prompts.FALLBACK_CLOSING)
    shown = "\n".join(text for _, text in h.shown)
    for leaked in ("[이름]", "인상적였습니다"):  # neither the page, the transcript nor the speech carries the rejected reply
        assert leaked not in h.spoken and leaked not in shown
        assert leaked not in "\n".join(text for _, text in h.conductor.transcript)
    assert h.conductor.fallbacks == ["closing"] and screen_fallback_steps(h) == ["closing"]
    assert h.conductor.stage is Stage.ENDED and h.conductor.end_reason == "completed"
    assert h.ended == ["completed"] and h.metrics.summary()["end_reason"] == "completed"


def test_a_followup_with_a_placeholder_speaks_the_fixed_question_and_the_interview_goes_on():
    h = opened(outputs=(PLACEHOLDER_FOLLOWUP, NATURAL_CLOSING))
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    assert h.said[-1] == ("followup", prompts.FALLBACK_FOLLOWUP)
    assert "[이름]" not in h.spoken and h.conductor.stage is Stage.WAIT_ANSWER_2
    assert h.conductor.fallbacks == ["followup"] and screen_fallback_steps(h) == ["followup"]
    h.run(h.conductor.on_candidate_turn(ANSWER_2))  # the fallback does not break the rest of the flow
    assert h.said[-1] == ("closing", f"{NATURAL_CLOSING} {prompts.CLOSING_SUFFIX}")
    assert h.ended == ["completed"] and h.conductor.fallbacks == ["followup"]


def test_llm_failure_ends_politely_without_trying_another_model():
    h = opened(llm_error=LlmUnavailable("http_400", "reasoning_effort is not supported"))
    h.run(h.conductor.on_candidate_turn(ANSWER_1))
    assert h.said[-1] == ("llm_error", prompts.LLM_ERROR_TEXT)
    assert h.ended == ["llm_error:http_400"]
    assert len(h.llm_calls) == 1  # one attempt: no retry, no other model
    assert any(m["name"] == "llm_error" and m["code"] == "http_400" for m in h.metrics.marks)


def test_a_second_turn_while_the_first_is_handled_is_ignored():
    h = opened()

    async def both():
        await asyncio.gather(h.conductor.on_candidate_turn(ANSWER_1), h.conductor.on_candidate_turn("아, 그리고 하나 더"))

    h.run(both())
    assert len(h.llm_calls) == 1 and h.conductor.stage is Stage.WAIT_ANSWER_2


def test_empty_turns_and_turns_before_the_question_are_ignored():
    h = Harness()
    h.run(h.conductor.on_candidate_turn("안녕하세요"))  # before the opening
    assert h.llm_calls == [] and h.conductor.stage is Stage.NEW
    h.run(h.conductor.run_opening())
    h.run(h.conductor.on_candidate_turn("   "))
    assert h.llm_calls == [] and h.conductor.stage is Stage.WAIT_ANSWER_1


# ── timers and endings ──


def test_silence_ends_the_practice_politely():
    h = opened()
    h.clock.advance(31)
    h.run(h.conductor.tick())
    assert h.said[-1] == ("no_answer", prompts.NO_ANSWER_TEXT) and h.ended == ["no_answer"]


def test_a_candidate_who_is_speaking_is_not_timed_out_and_the_idle_clock_restarts():
    h = opened()
    h.conductor.set_candidate_speaking(True)
    h.clock.advance(60)
    h.run(h.conductor.tick())
    assert h.ended == []
    h.conductor.set_candidate_speaking(False)  # stopped speaking just now
    h.clock.advance(5)
    h.run(h.conductor.tick())
    assert h.ended == []


def test_time_limit_closes_politely_once_the_candidate_pauses():
    h = opened(answer_idle=1000)
    h.clock.advance(141)
    h.run(h.conductor.tick())
    assert h.said[-1] == ("time_up", prompts.TIME_UP_TEXT) and h.ended == ["time_limit"]


def test_hard_stop_leaves_without_speaking_even_mid_response():
    h = opened()
    h.conductor.stage = Stage.RESPONDING_1
    h.clock.advance(169)
    h.run(h.conductor.tick())
    assert h.ended == ["hard_stop"] and h.said[-1][0] == "question"


def test_ticks_after_the_end_do_nothing():
    h = opened()
    h.clock.advance(31)
    h.run(h.conductor.tick())
    h.clock.advance(500)
    h.run(h.conductor.tick())
    assert h.ended == ["no_answer"]


def test_abort_ends_without_speaking():
    h = opened()
    spoken_before = len(h.said)
    h.run(h.conductor.abort("session_closed:participant_disconnected"))
    assert h.ended == ["session_closed:participant_disconnected"] and len(h.said) == spoken_before


def test_abort_after_the_end_does_nothing():
    h = opened()
    h.run(h.conductor.abort("candidate_left"))
    h.run(h.conductor.abort("session_closed:user_initiated"))  # the session close event arrives after the departure
    assert h.ended == ["candidate_left"] and h.conductor.stage is Stage.ENDED and h.metrics.end_reason == "candidate_left"


def test_an_opening_that_cannot_be_spoken_ends_the_session():
    h = Harness(deliver=False)
    h.run(h.conductor.run_opening())
    assert h.ended == ["speech_failed"] and h.llm_calls == []
