"""The interview engine end to end (ai/interview/engine.py, D51–D54, D57): a scripted interview reaches its terminal state, every
rule branch runs through the real engine, limits hold, spoken lines pass the guards, no personal data reaches the state or
the model input, and rules mode needs no key, no network and no service stack."""
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from ai.interview import (
    ActionKind,
    AnswerType,
    InterviewLimits,
    InterviewStateError,
    TopicStatus,
    TurnAnalysis,
    screen_spoken,
)
from ai.interview import rules
from ai.interview.types import Phase
from ai.tests.interview_helpers import (
    ACCOUNT_NAME,
    BLOCKLISTS,
    GOOD,
    OFF_TOPIC,
    PARTIAL_JAVA,
    good_answers,
    make_engine,
    make_plan,
    play,
)

REPO = Path(__file__).resolve().parents[2]
PLAN = make_plan()
TOPICS = [i.topic_id for i in PLAN.items]  # warmup, c1, c2, c4, behavioral


def at(topic_id: str, **kw):
    """An engine waiting for the answer to `topic_id`; the items before it were answered well. Returns (engine, now)."""
    engine = make_engine(**kw)
    engine.start()
    now = 10.0
    for item in engine.state.plan.items:
        if item.topic_id == topic_id:
            return engine, now
        engine.on_answer(GOOD[item.topic_id], now)
        now += 30.0
    raise AssertionError(f"no item {topic_id}")


def status(engine, topic_id: str) -> TopicStatus:
    return engine.state.status[topic_id]


# ── The scripted interview ──


def test_a_full_scripted_interview_reaches_its_terminal_state():
    engine = make_engine()
    actions = play(engine, good_answers(PLAN))
    assert [a.kind for a in actions] == [ActionKind.ASK] * 5 + [ActionKind.WRAP]
    last = actions[-1]
    assert last.done and last.reason == "plan_exhausted" and engine.state.phase is Phase.ENDED
    assert engine.state.end_reason == "plan_exhausted"
    assert [status(engine, t) for t in TOPICS] == [TopicStatus.DEMONSTRATED] * 5
    rows = {r["topic_id"]: r["status"] for r in engine.state.coverage()}
    assert rows["c3"] == "not_asked"  # the criterion the plan had no slot for is reported, not hidden
    asked = [t.text for t in engine.state.turns if t.role == "agent" and t.kind == "question"]
    assert all(q in text for q, text in zip([i.question for i in PLAN.items], asked, strict=True))  # in plan order, once each


def test_every_status_is_one_of_the_documented_six():
    assert {s.value for s in TopicStatus} == {"not_asked", "asked", "demonstrated", "partial", "not_shown", "skipped"}


def test_the_first_question_is_the_plans_first_and_it_is_marked_asked():
    engine = make_engine()
    action = engine.start()
    assert action.kind is ActionKind.ASK and PLAN.items[0].question in action.text and action.item_index == 0
    assert status(engine, "warmup") is TopicStatus.ASKED and status(engine, "c1") is TopicStatus.NOT_ASKED


def test_calls_that_do_not_fit_the_phase_are_errors_not_silent():
    engine = make_engine()
    with pytest.raises(InterviewStateError):
        engine.on_answer("답변입니다 답변입니다 답변입니다", 5.0)  # before start
    engine.start()
    with pytest.raises(InterviewStateError):
        engine.start()
    play(make_engine(), [])  # a fresh engine is untouched by the above
    done = make_engine()
    play(done, good_answers(PLAN))
    with pytest.raises(InterviewStateError):
        done.on_answer("너무 늦은 답변입니다 정말로", 400.0)
    assert done.on_silence(50, 400.0) is None


def test_an_empty_plan_ends_at_once():
    engine = make_engine(make_plan(criteria=[], cv_lines=[], questions=[]))
    engine.state.plan.items  # the behavioral question still exists: drop it to get a truly empty plan
    from ai.interview import InterviewPlan

    empty = make_engine(InterviewPlan(()))
    action = empty.start()
    assert action.done and action.kind is ActionKind.WRAP and action.reason == "empty_plan" and empty.state.phase is Phase.ENDED


# ── Every rule branch, through the engine ──


@pytest.mark.parametrize("silent", ["", "음...", "어 음"])
def test_an_empty_answer_is_clarified_once_then_the_item_is_skipped(silent):
    engine, now = at("c1")
    first = engine.on_answer(silent, now)
    assert first.kind is ActionKind.CLARIFY and first.text == rules.CLARIFY_TEXT and status(engine, "c1") is TopicStatus.ASKED
    second = engine.on_answer(silent, now + 20)
    assert second.kind is ActionKind.ASK and second.topic_id == "c2" and second.reason.startswith("skipped:")
    assert status(engine, "c1") is TopicStatus.SKIPPED
    assert second.text.startswith("괜찮습니다. 다음 질문으로 넘어가겠습니다.")


@pytest.mark.parametrize("brief", ["네", "그렇습니다", "글쎄요"])
def test_a_very_short_answer_is_asked_about_once_then_accepted_and_never_skipped(brief):
    engine, now = at("c1")
    first = engine.on_answer(brief, now)
    assert first.kind is ActionKind.CLARIFY and first.text == rules.ELABORATE_TEXT and first.reason == "too_short"
    assert status(engine, "c1") is TopicStatus.ASKED
    second = engine.on_answer(brief, now + 20)
    assert second.kind is ActionKind.ASK and second.topic_id == "c2" and second.reason == "too_short_again"
    assert status(engine, "c1") is TopicStatus.NOT_SHOWN  # taken as given: it showed nothing, but it was not skipped
    assert second.text.startswith("답변 감사합니다. 다음 질문입니다.")  # the neutral thanks, not the skip line


def test_a_repeat_request_repeats_the_question_once_then_the_item_is_skipped():
    engine, now = at("c1")
    item = PLAN.items[1]
    first = engine.on_answer("다시 한번 말씀해 주세요", now)
    assert first.kind is ActionKind.REPEAT and item.question in first.text and status(engine, "c1") is TopicStatus.ASKED
    second = engine.on_answer("다시 한번 말씀해 주세요", now + 20)
    assert second.kind is ActionKind.ASK and status(engine, "c1") is TopicStatus.SKIPPED


def test_a_request_to_explain_gets_the_shorter_wording():
    engine, now = at("c1")
    action = engine.on_answer("무슨 뜻인가요?", now)
    assert action.kind is ActionKind.REPEAT and action.text == PLAN.items[1].rephrase


def test_a_clarify_and_a_repeat_request_do_not_use_up_each_others_budget():
    engine, now = at("c1")
    assert engine.on_answer("네", now).kind is ActionKind.CLARIFY
    assert engine.on_answer("다시 한번 말씀해 주세요", now + 10).kind is ActionKind.REPEAT  # still allowed once
    assert engine.on_answer("네", now + 20).kind is ActionKind.ASK  # the clarify budget is spent: accepted as it is
    assert status(engine, "c1") is TopicStatus.NOT_SHOWN


def test_an_off_topic_answer_is_redirected_once_then_the_item_is_skipped():
    engine, now = at("c2")
    first = engine.on_answer(OFF_TOPIC, now)
    assert first.kind is ActionKind.REDIRECT and "프로젝트 경험" in first.text
    second = engine.on_answer(OFF_TOPIC, now + 20)
    assert second.kind is ActionKind.ASK and status(engine, "c2") is TopicStatus.SKIPPED


def test_dont_know_marks_not_shown_and_continues_without_a_follow_up():
    engine, now = at("c1")
    action = engine.on_answer("잘 모르겠습니다", now)
    assert action.kind is ActionKind.ASK and action.topic_id == "c2" and action.reason == "dont_know"
    assert status(engine, "c1") is TopicStatus.NOT_SHOWN
    assert engine.state.followups_used.get("c1", 0) == 0


def test_a_partial_answer_gets_a_follow_up_on_the_missing_point_and_is_marked_partial():
    engine, now = at("c1")
    action = engine.on_answer(PARTIAL_JAVA, now)
    assert action.kind is ActionKind.FOLLOW_UP and "Spring Boot 사용 경험" in action.text and action.reason == "missing_point:p2"
    assert status(engine, "c1") is TopicStatus.PARTIAL
    done = engine.on_answer(GOOD["c1"], now + 30)  # the follow-up is answered: both points are now shown
    assert done.kind is ActionKind.ASK and done.topic_id == "c2" and status(engine, "c1") is TopicStatus.DEMONSTRATED


def test_follow_ups_stop_at_the_limit_and_never_repeat_a_line():
    engine, now = at("c1")
    actions = [engine.on_answer(PARTIAL_JAVA, now + 30 * n) for n in range(3)]
    assert [a.kind for a in actions] == [ActionKind.FOLLOW_UP, ActionKind.FOLLOW_UP, ActionKind.ASK]
    assert engine.state.followups_used["c1"] == InterviewLimits().max_followups_per_item == 2
    follow_ups = [a.text for a in actions[:2]]
    assert len(set(follow_ups)) == 2  # the second differs from the first
    assert status(engine, "c1") is TopicStatus.PARTIAL and actions[2].topic_id == "c2"
    assert len(set(engine.state.asked)) == len(engine.state.asked)  # nothing was asked twice


def test_a_complete_answer_moves_on_with_a_neutral_thanks_and_no_judgement():
    engine, now = at("c1")
    action = engine.on_answer(GOOD["c1"], now)
    assert action.kind is ActionKind.ASK and action.text.startswith("답변 감사합니다. 다음 질문입니다.")


def test_a_larger_follow_up_budget_is_honoured():
    engine, now = at("c1", limits=InterviewLimits(max_followups_per_item=0))
    assert engine.on_answer(PARTIAL_JAVA, now).kind is ActionKind.ASK  # no follow-up budget at all


# ── Time and silence ──


def test_too_little_time_wraps_up_after_recording_the_answer():
    engine, _ = at("c1")
    action = engine.on_answer(GOOD["c1"], InterviewLimits().max_seconds - 10)
    assert action.done and action.reason == "time" and engine.state.phase is Phase.ENDED
    assert status(engine, "c1") is TopicStatus.DEMONSTRATED  # the answer still counted
    assert status(engine, "c2") is TopicStatus.NOT_ASKED


def test_silence_gets_one_nudge_then_a_skip():
    engine, now = at("c1")
    assert engine.on_silence(19.0, now + 19) is None
    nudge = engine.on_silence(20.0, now + 20)
    assert nudge.kind is ActionKind.NUDGE and "천천히" in nudge.text and status(engine, "c1") is TopicStatus.ASKED
    assert engine.on_silence(30.0, now + 30) is None  # one nudge per item
    skip = engine.on_silence(45.0, now + 45)
    assert skip.kind is ActionKind.ASK and skip.topic_id == "c2" and skip.reason == "skipped:silence"
    assert status(engine, "c1") is TopicStatus.SKIPPED
    assert engine.on_silence(20.0, now + 70).kind is ActionKind.NUDGE  # the next item gets its own nudge


def test_silence_near_the_end_wraps_up():
    engine, now = at("c1")
    action = engine.on_silence(5.0, InterviewLimits().max_seconds - 5)
    assert action.done and action.reason == "time"


def test_silence_before_the_first_question_or_after_the_end_does_nothing():
    assert make_engine().on_silence(60.0, 60.0) is None


def test_abort_keeps_the_coverage_and_stops_everything():
    engine, now = at("c2")
    engine.abort("candidate_left", now + 5)
    assert engine.state.phase is Phase.ABORTED and engine.state.end_reason == "candidate_left"
    assert status(engine, "warmup") is TopicStatus.DEMONSTRATED and status(engine, "c2") is TopicStatus.ASKED
    assert status(engine, "c4") is TopicStatus.NOT_ASKED
    with pytest.raises(InterviewStateError):
        engine.on_answer("늦은 답변입니다 정말로 정말로", now + 10)
    engine.abort("again")  # safe to call twice
    assert engine.state.end_reason == "candidate_left"


# ── A model's analysis (M2) goes through the same gate ──


def test_a_model_cannot_overrule_an_empty_answer():
    engine, now = at("c1")
    claim = TurnAnalysis(AnswerType.ANSWERED, {"p1": "demonstrated", "p2": "demonstrated"}, method="llm:fake")
    assert engine.on_answer("음", now, claim).kind is ActionKind.CLARIFY
    assert status(engine, "c1") is TopicStatus.ASKED  # the claimed coverage was not taken


def test_a_models_analysis_is_sanitized_and_its_method_recorded():
    engine, now = at("c1")
    answer = GOOD["c1"]
    claim = TurnAnalysis(
        AnswerType.ANSWERED,
        {"p1": "demonstrated", "p2": "demonstrated", "p9": "demonstrated"},
        quotes=("Spring Boot를 사용해서 주문 API를 개발했고", "답변에 없는 지어낸 문장입니다"),
        method="llm:fake",
    )
    engine.on_answer(answer, now, claim)
    recorded = [t for t in engine.state.turns if t.role == "candidate"][-1]
    assert recorded.method == "llm:fake"
    assert set(recorded.analysis["points"]) == {"p1", "p2"}  # the unknown point id was dropped
    assert recorded.analysis["quotes"] == ["Spring Boot를 사용해서 주문 API를 개발했고"]  # the invented quote was dropped


def test_a_models_follow_up_is_used_when_it_passes_and_replaced_when_it_does_not():
    good = "그 프로젝트에서 가장 어려웠던 기술적 문제는 무엇이었나요?"
    engine, now = at("c1")
    claim = TurnAnalysis(AnswerType.PARTIAL, {"p1": "demonstrated", "p2": "not_shown"}, suggested_follow_up=good, method="llm:fake")
    assert engine.on_answer(PARTIAL_JAVA, now, claim).text == good

    for bad in ("결혼 계획이 있으신가요?", "합격 가능성은 어느 정도라고 보시나요?", PLAN.items[1].question):
        engine, now = at("c1")
        claim = TurnAnalysis(AnswerType.PARTIAL, {"p1": "demonstrated", "p2": "not_shown"}, suggested_follow_up=bad, method="llm:fake")
        action = engine.on_answer(PARTIAL_JAVA, now, claim)
        assert action.kind is ActionKind.FOLLOW_UP and action.text != bad and "Spring Boot 사용 경험" in action.text, bad


# ── Spoken output ──


def _long_dialog():
    engine = make_engine()
    answers = ["네", "네", "다시 한번 말씀해 주세요", GOOD["c1"], PARTIAL_JAVA, PARTIAL_JAVA, OFF_TOPIC, OFF_TOPIC, "잘 모르겠습니다", GOOD["behavioral"], GOOD["behavioral"]]
    return engine, play(engine, answers)


def test_every_spoken_line_passes_the_guards():
    for engine, actions in (_long_dialog(), (lambda e: (e, play(e, good_answers(PLAN))))(make_engine())):
        for action in actions:
            assert screen_spoken(action.text, BLOCKLISTS, "closing" if action.done else "question") is not None, action.text
        for turn in engine.state.turns:
            if turn.role == "agent":
                assert screen_spoken(turn.text, BLOCKLISTS, "closing" if turn.kind == "closing" else "question") is not None, turn.text


def test_no_verdict_word_url_or_placeholder_is_ever_spoken():
    _, actions = _long_dialog()
    from ai.interview.guards import VERDICT_WORDS

    for action in actions:
        assert not any(w in action.text for w in VERDICT_WORDS) and "[" not in action.text and "http" not in action.text


def test_the_whole_run_is_deterministic():
    runs = []
    for _ in range(2):
        engine, _actions = _long_dialog()
        runs.append(json.dumps(engine.state.to_dict(), ensure_ascii=False, sort_keys=True))
    assert runs[0] == runs[1]


# ── Privacy (AI rule 3, D53) ──

SECRETS = ("kim@example.com", "010-1234-5678", "970512-2345678", "박서준", ACCOUNT_NAME, "jiwon kim")
PRIVATE_ANSWER = (
    "제 이메일은 kim@example.com 이고 번호는 010-1234-5678 입니다. 주민번호는 970512-2345678 이에요. 저는 박서준입니다. "
    "김지원이라고도 합니다. Jiwon Kim 으로도 씁니다. Java 17과 Spring Boot를 사용해서 주문 API를 개발했습니다."
)


def test_no_personal_data_reaches_the_state_or_the_model_input():
    engine, now = at("c1")
    engine.on_answer(PRIVATE_ANSWER, now)
    dump = json.dumps(engine.state.to_dict(), ensure_ascii=False).lower()
    for secret in SECRETS:
        assert secret.lower() not in dump, secret
    answer_turn = [t for t in engine.state.turns if t.role == "candidate"][-1]
    assert "[이메일]" in answer_turn.text and "[전화번호]" in answer_turn.text and "[이름]" in answer_turn.text
    assert answer_turn.masked_kinds.get("email") == 1 and answer_turn.masked_kinds.get("phone") == 1  # counts, never the text

    for given in (PRIVATE_ANSWER, answer_turn.text):  # even a raw transcript handed to the model input is masked again
        context = make_engine_context(PRIVATE_ANSWER if given is PRIVATE_ANSWER else given)
        for secret in SECRETS:
            assert secret.lower() not in context.lower(), secret


def make_engine_context(answer: str) -> str:
    engine, _ = at("c1")
    return engine.turn_context(answer).to_text()


def test_the_model_input_holds_only_masked_text_and_the_plans_own_words():
    engine, now = at("c1")
    engine.on_answer(PARTIAL_JAVA, now)
    text = engine.turn_context("Spring Boot로 주문 API를 개발했습니다").to_text()
    item = PLAN.items[1]
    assert item.question in text and "Java 활용 능력 (핵심)" in text and "Spring Boot 사용 경험" in text
    assert "<answer>\nSpring Boot로 주문 API를 개발했습니다\n</answer>" in text
    assert "weight" not in text.lower()
    assert all(t.text in text for t in engine.state.turns[-4:])  # the recent masked lines give a model its context


# ── Rules mode needs nothing ──


def test_rules_mode_needs_no_key_no_network_and_no_model(monkeypatch):
    monkeypatch.setenv("AI_MODE", "rules")
    for name in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*_a, **_k):
        raise AssertionError("the engine touched the network")

    for target in ("connect", "connect_ex", "send", "sendall"):
        monkeypatch.setattr(socket.socket, target, refuse)
    for target in ("create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, target, refuse)
    import ai.llm.client as client

    monkeypatch.setattr(client, "get_llm_client", refuse)
    monkeypatch.setattr(client, "AnthropicClient", refuse)

    engine = make_engine()
    actions = play(engine, good_answers(PLAN))
    assert actions[-1].done and actions[-1].reason == "plan_exhausted"


def test_the_engine_pulls_in_no_service_stack():
    """In a clean interpreter, importing the engine must not import the app, a model SDK, LiveKit or a database."""
    banned = ["app", "anthropic", "livekit", "groq", "openai", "sqlalchemy", "fastapi", "sentence_transformers", "httpx", "aiohttp", "requests", "torch"]
    code = f"import ai.interview, sys; print(sorted(m for m in {banned!r} if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", out.stdout
