"""The candidate's own words (docs/DECISIONS.md D59, D61): a disclosure of age, gender or military service that the candidate
volunteers must not reach any model input, whether it goes to the turn analysis, the follow-up, the quotes, `previous` and
`asked` of the next turn, or the views a later feedback step reads. What the candidate said about their work stays.

The examples are the forms the first vocabulary missed (the M2 security review) and the plain ones, in Korean and English,
mixed in one answer with professional content. No real model: FakeLLM only."""
import re

import pytest

from ai.interview import (
    ActionKind,
    AnswerType,
    TurnAnalysis,
    analyze_turn,
    is_sensitive,
    plan_view,
    prepare_turn,
    transcript_view,
)
from ai.interview.sensitive import SafeText
from ai.tests.helpers import FakeLLM
from ai.tests.interview_helpers import GOOD, PARTIAL_JAVA, make_engine

# (answer, fragments that must not reach a model, professional fragment that must)
SAMPLES = [
    ("저는 1997년에 태어났습니다. Java로 주문 API를 개발했습니다.", ["1997년", "태어"], "Java로 주문 API를 개발했습니다."),
    ("20대 후반입니다. Spring Boot로 결제 서비스를 운영했습니다.", ["20대", "후반"], "Spring Boot로 결제 서비스를 운영했습니다."),
    ("서른이에요 그리고 Java로 API를 설계했습니다", ["서른"], "Java로 API를 설계했습니다"),
    ("스물일곱입니다. MySQL 인덱스 튜닝으로 조회 속도를 개선했습니다.", ["스물일곱"], "MySQL 인덱스 튜닝으로 조회 속도를 개선했습니다."),
    ("만 27이에요. Docker로 Java 서비스 배포를 자동화했습니다.", ["27"], "Docker로 Java 서비스 배포를 자동화했습니다."),
    ("통신병으로 근무했습니다. Java 서버 운영 경험이 있습니다.", ["통신병"], "Java 서버 운영 경험이 있습니다."),
    ("면제 판정을 받았습니다. Java Redis 캐시를 설계했습니다.", ["면제", "판정"], "Java Redis 캐시를 설계했습니다."),
    ("공익 판정이었습니다. Kotlin과 Java로 API를 만들었습니다.", ["공익"], "Kotlin과 Java로 API를 만들었습니다."),
    ("해병으로 지냈습니다. Spring으로 Java 서비스를 개발했습니다.", ["해병"], "Spring으로 Java 서비스를 개발했습니다."),
    ("저는 여자라서 어려움이 있었지만 Java를 열심히 공부했습니다", ["여자"], "Java를 열심히 공부했습니다"),
    (
        "저는 27살이고 남자입니다. 병역은 군필입니다. 1997년생이에요. Java 17과 Spring Boot를 사용해서 주문 API를 개발했습니다.",
        ["27살", "남자", "병역", "군필", "1997년생"],
        "Java 17과 Spring Boot를 사용해서 주문 API를 개발했습니다.",
    ),
    ("I am 27 years old, but I built order APIs with Spring Boot and Java.", ["27", "years old"], "I built order APIs with Spring Boot and Java."),
    ("I am a mother of two. I designed REST APIs with Java.", ["mother"], "I designed REST APIs with Java."),
    ("Mr. Kim here and I served in the army. I tuned MySQL indexes for the Java service.", ["army", "Mr."], "I tuned MySQL indexes for the Java service."),
    ("In my late twenties I moved to backend, building APIs with Kotlin and Java.", ["twenties"], "building APIs with Kotlin and Java."),
    ("I am a female veteran of the Korean army. I used Java and Spring Boot daily.", ["female", "veteran", "army"], "I used Java and Spring Boot daily."),
]


def at(topic_id="c1"):
    """An engine waiting for the answer to `topic_id`, the items before it answered well. Returns (engine, now)."""
    engine = make_engine()
    engine.start()
    now = 10.0
    for item in engine.state.plan.items:
        if item.topic_id == topic_id:
            return engine, now
        engine.on_answer(GOOD[item.topic_id], now)
        now += 30.0
    raise AssertionError(topic_id)


def leaked(text: str, fragments) -> list[str]:
    return [f for f in fragments if f.lower() in text.lower()]


# ── The turn analysis input ──


@pytest.mark.parametrize(("answer", "gone", "kept"), SAMPLES)
def test_a_disclosure_in_a_mixed_answer_never_reaches_the_turn_input(answer, gone, kept):
    engine, _ = at("c1")
    request = prepare_turn(engine, answer)
    assert request is not None, "the professional part of the answer is enough to ask a model"
    assert leaked(request.user, gone) == [] and not is_sensitive(request.user)
    assert kept.lower() in request.user.lower()
    direct = engine.turn_context(answer).to_text()  # a caller that skips prepare_turn
    assert leaked(direct, gone) == [] and kept.lower() in direct.lower()


@pytest.mark.parametrize(("answer", "gone", "kept"), SAMPLES)
def test_a_model_that_echoes_the_disclosure_is_rejected_and_the_rules_decide(answer, gone, kept):
    engine, _ = at("c1")
    request = prepare_turn(engine, answer)
    disclosure = max((s for s in re.split(r"(?<=[.!?])\s+", answer) if is_sensitive(s)), key=len).strip(" .")  # long enough to be a quote
    echoed = {"answer_type": "answered", "points": [{"id": "p1", "level": "demonstrated"}, {"id": "p2", "level": "demonstrated"}], "quotes": [disclosure], "follow_up": None}
    turn = analyze_turn(FakeLLM(echoed), engine, answer)
    assert turn.analysis is None and turn.reason == "invented_quote"  # the model never saw it, so it cannot quote it
    assert request is not None  # (the same answer is askable; the quote is what was refused)


def test_a_model_quote_of_the_professional_part_is_kept_and_the_call_carried_no_disclosure():
    engine, _ = at("c1")
    answer = "저는 스물일곱 살입니다. Java 17과 Spring Boot를 사용해서 주문 API를 개발했고 실무에서 계속 사용하고 있습니다."
    ok = {
        "answer_type": "answered",
        "points": [{"id": "p1", "level": "demonstrated"}, {"id": "p2", "level": "demonstrated"}],
        "quotes": ["Java 17과 Spring Boot를 사용해서 주문 API를 개발했고"],
        "follow_up": None,
    }
    llm = FakeLLM(ok)
    turn = analyze_turn(llm, engine, answer)
    assert turn.reason == "ok" and turn.analysis.quotes == ("Java 17과 Spring Boot를 사용해서 주문 API를 개발했고",)
    assert len(llm.calls) == 1 and leaked(llm.calls[0][1], ["스물일곱", "27"]) == []


@pytest.mark.parametrize(
    "follow_up",
    ["27살이신데 Java는 어떻게 쓰셨나요?", "20대 후반이시라면 Java 경험은 어땠나요?", "군 복무 때도 Java를 쓰셨나요?", "As a woman, how did you use Java?"],
)
def test_a_follow_up_that_carries_a_disclosure_is_dropped_on_its_own(follow_up):
    engine, _ = at("c1")
    partial = {
        "answer_type": "partial",
        "points": [{"id": "p1", "level": "demonstrated"}, {"id": "p2", "level": "not_shown"}],
        "quotes": ["Java를 공부했고 알고리즘 문제도 풀었습니다"],
        "follow_up": follow_up,
    }
    turn = analyze_turn(FakeLLM(partial), engine, PARTIAL_JAVA)
    assert turn.reason == "ok" and turn.dropped == ("follow_up",) and turn.analysis.suggested_follow_up is None


@pytest.mark.parametrize("follow_up", ["27살이신데 Java는 어떻게 쓰셨나요?", "여자 개발자로서 Java 경험은 어땠나요?", "통신병 때 Java를 쓰셨나요?"])
def test_the_engine_never_speaks_a_follow_up_with_a_disclosure(follow_up):
    engine, now = at("c1")
    claim = TurnAnalysis(AnswerType.PARTIAL, {"p1": "demonstrated", "p2": "not_shown"}, suggested_follow_up=follow_up, method="llm:fake")
    action = engine.on_answer(PARTIAL_JAVA, now, claim)
    assert action.kind is ActionKind.FOLLOW_UP and not is_sensitive(action.text)


# ── Evidence and quotes ──


def test_rules_quotes_never_carry_a_disclosure():
    engine, now = at("c1")
    engine.on_answer("저는 27살이고 남자입니다. Java 17과 Spring Boot를 사용해서 주문 API를 개발했습니다.", now)
    quotes = [q for t in engine.state.turns if t.role == "candidate" and t.analysis for q in t.analysis["quotes"]]
    assert quotes and not any(is_sensitive(q) for q in quotes)


def test_a_mixed_sentence_gives_no_quote_that_carries_the_disclosure():
    engine, now = at("c1")
    engine.on_answer("27살인데 Java 17과 Spring Boot를 사용해서 주문 API를 개발했습니다.", now)
    quotes = [q for t in engine.state.turns if t.role == "candidate" and t.analysis for q in t.analysis["quotes"]]
    assert not any(is_sensitive(q) for q in quotes)


def test_a_model_quote_that_matches_the_vocabulary_is_dropped_by_the_engine():
    """Defense in depth: even if a quote with a disclosure reached the engine (a caller that skipped `parse_turn`), it is not
    stored as evidence."""
    engine, now = at("c1")
    answer = "서른이에요 그리고 Java 17과 Spring Boot를 사용해서 주문 API를 개발했습니다."  # (with "저는" it would be masked as a name)
    claim = TurnAnalysis(AnswerType.ANSWERED, {"p1": "demonstrated", "p2": "demonstrated"}, ("서른이에요 그리고", "Java 17과 Spring Boot를 사용해서"), method="llm:fake")
    engine.on_answer(answer, now, claim)
    last = [t for t in engine.state.turns if t.role == "candidate"][-1]
    assert last.analysis["quotes"] == ["Java 17과 Spring Boot를 사용해서"]


# ── Later turns and the views a feedback step reads ──


def test_the_next_turn_input_does_not_remember_the_disclosure():
    engine, now = at("c1")
    engine.on_answer("20대 후반입니다. " + GOOD["c1"], now)
    request = prepare_turn(engine, "REST API를 설계하고 Swagger로 문서화했습니다. 프로젝트에서 설계와 개발을 진행했습니다.")
    assert request is not None and "<previous>" in request.user
    assert leaked(request.user, ["20대", "후반"]) == [] and GOOD["c1"] in request.user


def _interview_with_disclosures(prefix: str):
    engine = make_engine()
    action, now = engine.start(), 10.0
    while not action.done:
        action = engine.on_answer(prefix + GOOD[engine.state.current.topic_id], now)
        now += 30.0
    return engine


def test_the_transcript_view_is_the_safe_form_of_the_raw_transcript():
    engine = _interview_with_disclosures("저는 스물일곱입니다. 통신병으로 근무했습니다. ")
    raw = " ".join(t.text for t in engine.state.turns if t.role == "candidate")
    assert "스물일곱" in raw and "통신병" in raw  # the stored transcript is the candidate's, as said: it is not model input
    view = transcript_view(engine.state)
    assert view and all(isinstance(t.text, SafeText) for t in view)
    assert not any(is_sensitive(t.text.value) or any(is_sensitive(q.value) for q in t.quotes) for t in view)
    candidate = [t for t in view if t.role == "candidate"]
    assert candidate and all(GOOD[engine.state.plan.items[i].topic_id] in t.text.value for i, t in enumerate(candidate[: len(engine.state.plan.items)]))


def test_a_turn_that_is_only_a_disclosure_is_left_out_of_the_view():
    engine, now = at("c1")
    engine.on_answer("저는 스물일곱입니다 그리고 통신병이었습니다", now)
    texts = [t.text.value for t in transcript_view(engine.state) if t.role == "candidate"]
    assert not any("스물일곱" in t or "통신병" in t for t in texts)


def test_the_plan_view_is_made_of_safe_text_with_the_statuses():
    engine = _interview_with_disclosures("")
    view = plan_view(engine.state)
    assert view.items and all(isinstance(i.question, SafeText) and isinstance(i.criterion_name, SafeText) for i in view.items)
    assert all(isinstance(text, SafeText) for i in view.items for _, text in i.rubric)
    assert {i.status for i in view.items} <= {"demonstrated", "partial", "not_shown", "skipped", "asked", "not_asked"}
    assert all(not is_sensitive(i.question.value) for i in view.items)
