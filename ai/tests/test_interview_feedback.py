"""The final feedback of a practice interview (ai/interview/feedback.py, views.py; docs/DECISIONS.md D51, D53, D54, D63).

Real interviews are run with the engine and the rules (no model), then `make_feedback` gets only the two views. A model is a
FakeLLM (or a stub that returns whatever it is given); nothing here calls a real one. The invariants every report must keep
are checked by `check_report`: statuses come from the plan view, every strength has a quote found exactly in a candidate line
of its own topic, every sentence passes the screens, every link is in the approved file."""
import ast
import dataclasses
import json
import re
from pathlib import Path

import pytest

from ai.career.resources import load_resources
from ai.interview import (
    FeedbackReport,
    InterviewEngine,
    InterviewPlan,
    ModelInput,
    coverage_snapshot,
    feedback_request,
    is_sensitive,
    make_feedback,
    parse_feedback,
    plan_view,
    plan_view_from,
    rules_feedback,
    screen_feedback,
    transcript_view,
    transcript_view_from,
)
from ai.interview import feedback as feedback_module
from ai.interview.feedback import (
    ADVICE_KEEP,
    ADVICE_STRUCTURE,
    ADVICE_UNCOVERED,
    ADVICE_UNSURE,
    BEHAVIORAL_PRACTICE,
    FIXED_LINES,
    MAX_PRACTICE,
    NOTE_ABORTED,
    NOTE_NO_ANSWERS,
    NOTE_NO_ITEMS,
    NOTE_TIME,
)
from ai.interview.types import InterviewLimits, Turn
from ai.llm.client import LLMError
from ai.parsing.extract import PROMPT_DIR, PROMPT_VERSION
from ai.tests.helpers import FakeLLM, SKILLS
from ai.tests.interview_helpers import BLOCKLISTS, GOOD, PARTIAL_JAVA, make_engine
from ai.tests.test_interview_model_boundary import raw_serialization_uses, reads_raw_transcript

TOPICS = ("warmup", "c1", "c2", "c4", "behavioral")
SKIP = None  # a step of `play`: the candidate says nothing until the engine skips the question
NO_FOLLOWUPS = InterviewLimits(max_followups_per_item=0)
RESOURCES = load_resources()
YAML_URLS = {r.url for r in [*RESOURCES.skills.values(), *RESOURCES.certificates.values()]}
# Passages of the standard answers (tests.interview_helpers.GOOD), copied exactly
Q_W = "프로젝트에서 백엔드 개발 역할을 맡아 주문 API를 설계하고 구현했고"
Q_C1 = "Java 17과 Spring Boot를 사용해서 주문 API를 개발했고"
Q_C2 = "REST API를 설계하고 Swagger로 문서화했습니다"
Q_C4 = "컴퓨터공학 전공 수업에서 배운 자료구조"


def play(steps, *, limits=None, abort=None) -> InterviewEngine:
    engine = make_engine(limits=limits) if limits is not None else make_engine()
    engine.start()
    now = 10.0
    for step in steps:
        if engine.state.phase.value != "listening":
            break
        engine.on_silence(60.0, now) if step is SKIP else engine.on_answer(step, now)
        now += 30.0
    if abort:
        engine.abort(abort, now)
    return engine


def standard(prefix: str = "") -> InterviewEngine:
    return play([prefix + GOOD[topic] for topic in TOPICS])


def mixed() -> InterviewEngine:
    """c1 partial (no follow-ups), c2 skipped, c4 'I don't know', the others answered well."""
    return play([GOOD["warmup"], PARTIAL_JAVA, SKIP, "모르겠습니다", GOOD["behavioral"]], limits=NO_FOLLOWUPS)


def views(engine):
    return transcript_view(engine.state), plan_view(engine.state)


class RawLLM:
    """A client that hands back exactly what it is given, unvalidated, and counts its calls."""

    model = "raw-llm"

    def __init__(self, raw):
        self.raw, self.calls = raw, []

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.calls.append((system, user))
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


def reply(**sections) -> dict:
    return {"strengths": [], "gaps": [], "improvements": [], "practice_questions": [], **sections}


def strength(topic, quote, text="구체적인 사례를 들어 설명했습니다."):
    return {"topic_id": topic, "text": text, "quotes": [quote] if isinstance(quote, str) else quote}


def check_report(report: FeedbackReport, transcript, plan, urls=None) -> None:
    """The invariants of every report, whatever produced it. `urls`: the links the report may carry (default: the approved file)."""
    assert [(t.topic_id, t.status) for t in report.topics] == [(i.topic_id, i.status) for i in plan.items]  # code-owned
    assert [t.importance for t in report.topics] == [i.importance for i in plan.items]
    answers: dict[str, list[str]] = {}
    for line in transcript:
        if line.role == "candidate" and line.topic_id:
            answers.setdefault(line.topic_id, []).append(" ".join(line.text.value.split()))
    status = {t.topic_id: t.status for t in report.topics}
    for s in report.strengths:
        assert status[s.topic_id] in ("demonstrated", "partial") and s.quotes
        assert all(any(q in line for line in answers.get(s.topic_id, ())) for q in s.quotes), s
    statements = [s.text for s in report.strengths] + [g.text for g in report.gaps] + list(report.improvements) + list(report.notes)
    for text in statements:
        assert screen_feedback(text, BLOCKLISTS) == text and not is_sensitive(text), text
    for q in report.practice_questions:
        assert screen_feedback(q.question, BLOCKLISTS, "question") == q.question, q
    assert all(r.url in (YAML_URLS if urls is None else urls) for r in report.resources)
    assert report.method == "rules" or report.method.startswith("llm:")
    data = json.dumps(report.to_data(), ensure_ascii=False)
    assert not is_sensitive(data.replace("rubric_notice", ""))  # (the notice says "AI가 만든", nothing else of it matters)


def make(engine, *, llm=None, resources=RESOURCES, skills=SKILLS):
    transcript, plan = views(engine)
    report = make_feedback(transcript, plan, resources=resources, skills=skills, blocklists=BLOCKLISTS, llm=llm)
    check_report(report, transcript, plan, urls={r.url for r in [*resources.skills.values(), *resources.certificates.values()]} if resources else set())
    return report


# ── The views, and the persisted-session constructors ──


def test_every_line_carries_its_topic():
    transcript, plan = views(standard())
    candidate = [t.topic_id for t in transcript if t.role == "candidate"]
    assert candidate == list(TOPICS) and plan.topic_ids == TOPICS
    assert all(t.topic_id in TOPICS for t in transcript if t.role == "agent" and t.kind in ("question", "follow_up"))


def _persist(engine):
    """What a backend would store, and rebuild from: the turns, the plan the engine ran, the coverage snapshot."""
    turns = [Turn(**{**t.to_dict()}) for t in engine.state.turns]
    plan = InterviewPlan.from_dict(json.loads(json.dumps(engine.state.plan.to_dict())))
    snapshot = json.loads(json.dumps(coverage_snapshot(engine.state)))
    return turns, plan, snapshot


@pytest.mark.parametrize("scenario", [standard, mixed, lambda: play([GOOD["warmup"], GOOD["c1"]], abort="client_left")])
def test_persisted_views_equal_the_live_views_and_give_the_same_report(scenario):
    engine = scenario()
    transcript, plan = views(engine)
    turns, stored_plan, snapshot = _persist(engine)
    rebuilt_plan = plan_view_from(stored_plan, snapshot, blocklists=BLOCKLISTS)
    rebuilt = transcript_view_from(turns, rebuilt_plan.topic_ids)
    assert rebuilt_plan == plan and rebuilt == transcript
    live = make_feedback(transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS)
    again = make_feedback(rebuilt, rebuilt_plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS)
    assert live == again


def test_the_snapshot_holds_codes_only():
    engine = mixed()
    snapshot = coverage_snapshot(engine.state)
    text = json.dumps(snapshot, ensure_ascii=False)
    assert set(snapshot) == {"phase", "end_reason", "status", "levels"}
    assert snapshot["status"]["c2"] == "skipped" and snapshot["status"]["c1"] == "partial"
    for raw in (*(t.text for t in engine.state.turns), *(i.question for i in engine.state.plan.items), "Java 활용 능력"):
        assert raw not in text


@pytest.mark.parametrize("bad", [None, "x", [1, 2], 5, {"status": "weird", "levels": 3, "phase": {"x": 1}}, {"status": {"c1": "weird", "warmup": 7}, "levels": {"c1": {"p1": "great", 5: "partial"}}}])
def test_a_malformed_snapshot_is_read_defensively(bad):
    engine = standard()
    view = plan_view_from(engine.state.plan, bad)
    assert [i.status for i in view.items] == ["not_asked"] * len(TOPICS)
    assert view.phase == "ended" and view.end_reason is None
    assert all(level in ("demonstrated", "partial", "not_shown") for i in view.items for _, level in i.levels)


def test_a_snapshot_end_reason_is_kept_only_as_a_code():
    engine = standard()
    assert plan_view_from(engine.state.plan, {"end_reason": "time"}).end_reason == "time"
    assert plan_view_from(engine.state.plan, {"end_reason": "Client left the room! 010-1234"}).end_reason is None


def test_persisted_turns_are_read_defensively():
    good = Turn(1, "candidate", "answer", 0, "Java로 API를 개발했습니다.", "rules", {"quotes": ["Java로 API를 개발했습니다"], "points": {"p1": "demonstrated", "p2": "great"}, "answer_type": "answered"})
    odd = [
        Turn(2, "candidate", "answer", 99, "범위 밖의 순서입니다.", "rules", None),
        Turn(3, "candidate", "answer", True, "불리언 순서입니다.", "rules", None),  # type: ignore[arg-type]
        Turn(4, "candidate", "answer", None, "순서가 없습니다.", "rules", {"quotes": "not a list", "points": ["x"], "answer_type": "Bad Type!"}),
        Turn(5, "system", "note", 0, "알 수 없는 역할입니다.", "rules", None),  # type: ignore[arg-type]
        Turn(6, "candidate", "answer", 0, "저는 스물일곱 살입니다.", "rules", None),
    ]
    view = transcript_view_from([good, *odd], ["c1"])
    assert [t.seq for t in view] == [1, 2, 3, 4]  # the unknown role and the all-disclosure line are gone
    assert [t.topic_id for t in view] == ["c1", None, None, None]
    assert view[0].points == (("p1", "demonstrated"),) and [q.value for q in view[0].quotes] == ["Java로 API를 개발했습니다"]
    assert view[3].quotes == () and view[3].points == () and view[3].answer_type is None


def test_a_persisted_plan_is_validated_again():
    engine = standard()
    data = json.loads(json.dumps(engine.state.plan.to_dict()))
    data["items"][1]["question"] = "군 복무는 어디서 하셨나요?"
    forged = InterviewPlan.from_dict(data)
    view = plan_view_from(forged, coverage_snapshot(engine.state), blocklists=BLOCKLISTS)
    assert "c1" not in view.topic_ids and "c1:question" in view.issues
    assert [u.criterion_id for u in view.uncovered if u.reason == "no_question"] == [1]


# ── make_feedback takes the two views and nothing else ──


def test_make_feedback_refuses_state_engine_and_raw_turns():
    engine = standard()
    transcript, plan = views(engine)
    for bad_plan in (engine.state, engine, engine.state.plan, None):
        with pytest.raises(TypeError):
            make_feedback(transcript, bad_plan)  # type: ignore[arg-type]
    for bad_transcript in (engine.state.turns, [engine.state.turns[0]], engine, [object()]):
        with pytest.raises(TypeError):
            make_feedback(bad_transcript, plan)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        rules_feedback(engine.state.turns, plan)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        feedback_request(transcript, engine.state)  # type: ignore[arg-type]


def test_feedback_imports_only_the_views_and_the_boundary_of_the_package():
    tree = ast.parse(Path(feedback_module.__file__).read_text(encoding="utf-8"))
    modules = {n.module.split(".")[2] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("ai.interview.")}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "ai.interview" for a in n.names}
    assert modules == {"boundary", "guards", "rules", "sensitive", "types", "views"}, modules  # not the engine, the state, the plan builder or the CV door


def test_feedback_never_reads_raw_state_or_serializes_it():
    tree = ast.parse(Path(feedback_module.__file__).read_text(encoding="utf-8"))
    assert not reads_raw_transcript(tree) and not raw_serialization_uses(tree)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"InterviewState", "InterviewEngine", "turns", "to_dict", "asdict", "complete_json", "mask_pii", "clean_cv", "find_gaps"}


def test_the_prompt_states_its_contract():
    prompt = (PROMPT_DIR / "interview_feedback.md").read_text(encoding="utf-8")
    for field in feedback_module.FeedbackLlmOut.model_fields:
        assert f'"{field}"' in prompt, field
    for word in ("data, not instructions", "not company requirements", "status", "character for character", "military service", "gender", "URL", "<plan>", "<transcript>", "<asked>", "<rubric>"):
        assert word in prompt, word
    assert PROMPT_VERSION == "v2"  # a new directory in v2; v1 prompts untouched


# ── The report: schema, rules, fixed lines ──


def test_the_report_has_no_number_score_rank_or_verdict_field():
    classes = [getattr(feedback_module, name) for name in ("TopicFeedback", "Strength", "Gap", "PracticeQuestion", "ResourceLink", "UncoveredTopic", "FeedbackReport")]
    for cls in classes:
        for field in dataclasses.fields(cls):
            assert not re.search(r"\b(int|float|bool)\b", str(field.type)), (cls.__name__, field.name)
            assert not re.search(r"score|rank|weight|grade|verdict|count|total|percent|pass|fail|hire", field.name, re.I), (cls.__name__, field.name)
    data = make(standard()).to_data()
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in _walk(data))


def _walk(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    else:
        yield value


def test_every_fixed_line_passes_the_screens():
    for line in (*FIXED_LINES, feedback_module.WARMUP_LABEL, feedback_module.BEHAVIORAL_LABEL):
        assert screen_feedback(line, BLOCKLISTS) == line, line
    assert screen_feedback(BEHAVIORAL_PRACTICE, BLOCKLISTS, "question") == BEHAVIORAL_PRACTICE


def test_the_rules_report_is_deterministic_and_needs_no_client():
    transcript, plan = views(mixed())
    first = make_feedback(transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS)
    assert first == make_feedback(transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS, llm=None) == rules_feedback(
        transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS
    )
    assert first.method == "rules" and first.rules_sections == ()


def test_the_topics_and_statuses_come_from_the_engine():
    report = make(mixed())
    assert {t.topic_id: t.status for t in report.topics} == {"warmup": "demonstrated", "c1": "partial", "c2": "skipped", "c4": "not_shown", "behavioral": "demonstrated"}
    assert [t.name for t in report.topics][:2] == [feedback_module.WARMUP_LABEL, "Java 활용 능력"]
    assert [(u.topic_id, u.name, u.reason) for u in report.uncovered] == [("c3", "협업 태도", "no_slot")]
    assert {t.importance for t in report.topics} <= {"core", "important", "general", None}


def test_the_rules_report_of_a_mixed_interview():
    report = make(mixed())
    assert [s.topic_id for s in report.strengths] == ["c1", "warmup", "behavioral"]  # by importance, then plan order
    assert [g.topic_id for g in report.gaps] == ["c1", "c2", "c4", "c4"]  # at most four; the criterion that was not asked is in `uncovered`
    assert "skipped" in next(g.text for g in report.gaps if g.topic_id == "c2")
    assert report.improvements == (ADVICE_STRUCTURE, ADVICE_UNSURE, ADVICE_UNCOVERED, ADVICE_KEEP)
    assert [q.topic_id for q in report.practice_questions] == ["c1", "c2", "c4"] and len(report.practice_questions) <= MAX_PRACTICE
    assert {r.topic_id for r in report.resources} == {"c1"}  # a link only where the criterion names a skill


def test_a_fully_demonstrated_interview_has_no_gap_to_work_on_except_what_was_not_asked():
    report = make(standard())
    assert [g.topic_id for g in report.gaps] == ["c3"]
    assert report.improvements == (ADVICE_UNCOVERED, ADVICE_KEEP)
    assert [s.topic_id for s in report.strengths] == ["c1", "c2", "c4", "warmup"]  # at most four
    assert all(s.quotes for s in report.strengths)


def test_rules_strengths_need_a_stored_quote_that_is_in_the_candidates_lines():
    transcript, plan = views(standard())
    stripped = tuple(dataclasses.replace(t, quotes=()) for t in transcript)  # no analysis stored a quote
    assert rules_feedback(stripped, plan, blocklists=BLOCKLISTS).strengths == ()
    foreign = tuple(dataclasses.replace(t, quotes=(type(t.text)("다른 곳에서 가져온 문장입니다."),)) if t.role == "candidate" else t for t in transcript)
    assert rules_feedback(foreign, plan, blocklists=BLOCKLISTS).strengths == ()


# ── Empty, aborted and unfinished interviews ──


def test_an_interview_with_no_answer_gives_a_note_and_never_asks_a_model():
    llm = FakeLLM(reply(improvements=["연습 방법을 알려 드립니다."]))
    engine = play([], abort="client_left")
    report = make(engine, llm=llm)
    assert llm.calls == [] and report.method == "rules"
    assert NOTE_NO_ANSWERS in report.notes and NOTE_ABORTED in report.notes
    assert [t.status for t in report.topics][0] in ("asked", "not_asked") and report.strengths == ()
    assert ADVICE_UNCOVERED in report.improvements and all("was not covered" in g.text for g in report.gaps)


def test_an_interview_aborted_in_the_middle_reports_what_it_covered():
    engine = play([GOOD["warmup"], GOOD["c1"]], abort="client_left")
    report = make(engine)
    status = {t.topic_id: t.status for t in report.topics}
    assert status["warmup"] == "demonstrated" and status["c2"] == "asked" and status["c4"] == "not_asked" and NOTE_ABORTED in report.notes
    assert {s.topic_id for s in report.strengths} <= {"warmup", "c1"} and NOTE_NO_ANSWERS not in report.notes


def test_a_time_out_is_noted_only_when_something_was_left():
    engine = make_engine()
    engine.start()
    engine.on_answer(GOOD["warmup"], 580.0)  # no time left: the engine wraps up
    assert engine.state.end_reason == "time"
    assert NOTE_TIME in make(engine).notes
    assert NOTE_TIME not in make(standard()).notes


def test_an_empty_plan_gives_the_no_questions_note():
    engine = InterviewEngine(InterviewPlan(()), blocklists=BLOCKLISTS)
    engine.start()
    llm = FakeLLM(reply())
    report = make(engine, llm=llm)
    assert report.topics == () and report.notes[:1] == (NOTE_NO_ITEMS,) and llm.calls == []


# ── The request ──


def test_the_request_is_a_boundary_input_with_the_four_sections():
    transcript, plan = views(mixed())
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    assert isinstance(request.model_input, ModelInput) and request.model_input.purpose == "feedback"
    assert request.system == (PROMPT_DIR / "interview_feedback.md").read_text(encoding="utf-8")
    for tag in ("plan", "rubric", "asked", "transcript"):
        assert request.user.count(f"<{tag}>") == 1 and request.user.count(f"</{tag}>") == 1
    assert "c2 | 프로젝트 경험 | core | skipped" in request.user and "c3 | 협업 태도 | general | not_asked" in request.user
    assert "c1.p2 | Spring Boot 사용 경험 | not_shown" in request.user
    assert "c1 | candidate | " + PARTIAL_JAVA in request.user and "| interviewer | " in request.user
    assert not is_sensitive(request.user)


def test_one_request_is_made_and_it_is_exactly_the_prepared_one():
    engine = standard()
    transcript, plan = views(engine)
    llm = FakeLLM(reply(improvements=["답변 구성을 이어 가 보세요."]))
    make_feedback(transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS, llm=llm)
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    assert llm.calls == [(request.system, request.user)]


def test_a_long_transcript_is_cut_and_the_quote_check_uses_what_was_sent(monkeypatch):
    monkeypatch.setattr(feedback_module, "MAX_TRANSCRIPT_CHARS", 700)
    transcript, plan = views(standard())
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    assert Q_C4 not in request.user and Q_W in request.user  # the late turns did not fit
    out, reason = parse_feedback(request, reply(strengths=[strength("c4", Q_C4), strength("warmup", Q_W)]))
    assert reason == "ok" and [s.topic_id for s in out.strengths] == ["warmup"] and out.dropped == ("strength:quote",)


# ── Evidence: exact quotes from the candidate's own lines of the same topic ──


def merged(engine, response, **kw):
    return make(engine, llm=FakeLLM(response), **kw)


def test_a_valid_model_report_is_used_and_the_code_keeps_what_is_its_own():
    engine = mixed()
    answer = reply(
        strengths=[strength("warmup", Q_W, "이력서의 경험에서 맡은 역할과 구현 내용을 설명했습니다."), strength("behavioral", "의견 조율을 진행했고", "협업 상황에서 본인의 행동을 설명했습니다.")],
        gaps=[{"topic_id": "c1", "text": "Spring Boot를 어떻게 사용했는지는 아직 설명하지 않았습니다."}],
        improvements=["답변을 상황과 역할, 결과 순서로 구성해 보세요."],
        practice_questions=[{"topic_id": "c1", "question": "Spring Boot 사용 경험을 실제 프로젝트 사례로 설명해 보세요."}],
    )
    report = merged(engine, answer)
    assert report.method == "llm:fake-llm" and report.rules_sections == ()
    assert [s.topic_id for s in report.strengths] == ["warmup", "behavioral"]
    assert [g.topic_id for g in report.gaps] == ["c1"] and len(report.improvements) == 1 and len(report.practice_questions) == 1
    rules = make(engine)
    assert report.topics == rules.topics and report.uncovered == rules.uncovered and report.notes == rules.notes  # not the model's to say


@pytest.mark.parametrize(
    ("quote", "valid"),
    [
        (Q_C1, True),
        (Q_C1.replace(" ", "  "), True),  # whitespace is collapsed, nothing else
        ("Java 17과  Spring Boot를 사용해서 주문 API를 개발했고", True),
        ("Java 17과 Spring Boot를 사용해서 주문 API를 만들었고", False),  # one word changed
        ("Java 17과 Spring Boot를 사용해서 주문 API를 개발하고", False),  # an ending changed
        ("java 17과 spring boot를 사용해서 주문 api를 개발했고", False),  # the case changed
        ("Java 17과 Spring Boot를 사용해서 ... 개발했고", False),  # shortened with an ellipsis
        ("Spring Boot를 활용해 주문 서비스를 개발했습니다", False),  # a paraphrase
        ("Java", False),  # too short to be evidence
        ("Java 17과 Spring Boot를 사용해서 주문 API를 개발했고 실무에서 계속 사용하고 있습니다. 그리고 더 많은 것을 했습니다", False),  # more than was said
        ("[이름]님의 경험을 설명했습니다", False),  # a placeholder
    ],
)
def test_a_quote_must_be_exact(quote, valid):
    report = merged(standard(), reply(strengths=[strength("c1", quote)]))
    assert bool(report.strengths and report.strengths[0].text == "구체적인 사례를 들어 설명했습니다.") is valid
    if valid:
        assert report.strengths[0].quotes == (" ".join(quote.split()),)


def test_an_interviewer_quote_is_not_evidence():
    engine = standard()
    transcript, plan = views(engine)
    question = next(t.text.value for t in transcript if t.role == "agent" and t.topic_id == "c1" and t.kind == "question")
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    out, _ = parse_feedback(request, reply(strengths=[strength("c1", question[:60]), strength("c1", Q_C1, "근거를 들어 설명했습니다.")]))
    assert [s.quotes for s in out.strengths] == [(Q_C1,)] and out.dropped == ("strength:quote",)


def test_a_quote_from_another_topic_is_not_evidence():
    report = merged(standard(), reply(strengths=[strength("c1", Q_C2), strength("c2", Q_C1), strength("c2", Q_C2, "문서화한 경험을 설명했습니다.")]))
    assert [(s.topic_id, s.quotes) for s in report.strengths] == [("c2", (Q_C2,))]


def test_a_strength_without_a_valid_quote_is_dropped_and_nothing_else_is_affected():
    report = merged(
        standard(),
        reply(
            strengths=[strength("c1", "지어낸 문장입니다 가나다라마바"), strength("c2", Q_C2, "문서화한 경험을 설명했습니다."), strength("c4", [])],
            gaps=[{"topic_id": "c3", "text": "협업 태도는 이번 연습에서 다루지 못했습니다."}],
            improvements=["핵심 내용을 먼저 말하고 사례로 이어 가 보세요."],
        ),
    )
    assert report.method == "llm:fake-llm"
    assert [(s.topic_id, s.quotes) for s in report.strengths] == [("c2", (Q_C2,))]  # the other two are dropped, this one stays
    assert [g.topic_id for g in report.gaps] == ["c3"] and report.improvements == ("핵심 내용을 먼저 말하고 사례로 이어 가 보세요.",)
    assert report.rules_sections == ("practice_questions",)


def test_when_every_strength_is_invalid_that_section_alone_falls_back_to_the_rules():
    rules = make(standard())
    report = merged(standard(), reply(strengths=[strength("c1", "지어낸 문장입니다 가나다라마바")], improvements=["핵심 내용을 먼저 말하고 사례로 이어 가 보세요."]))
    assert report.method == "llm:fake-llm" and report.strengths == rules.strengths  # the rules section, with verified quotes
    assert report.improvements == ("핵심 내용을 먼저 말하고 사례로 이어 가 보세요.",) and "strengths" in report.rules_sections and "improvements" not in report.rules_sections


@pytest.mark.parametrize("bad", [dict(topic_id="c3"), dict(topic_id="c99"), dict(topic_id=""), dict(topic_id="warmup;drop")])
def test_a_strength_for_an_unknown_or_unasked_topic_is_dropped(bad):
    request = feedback_request(*views(standard()), blocklists=BLOCKLISTS, skills=SKILLS)
    out, _ = parse_feedback(request, reply(strengths=[{**strength("c1", Q_C1), **bad}], improvements=["답변을 이어 가 보세요."]))
    assert out.strengths == () and out.dropped[0] == "strength:topic"


def test_a_strength_for_a_topic_that_showed_nothing_is_dropped_and_the_code_keeps_the_statuses():
    engine = mixed()  # c4: not_shown, c2: skipped
    transcript, plan = views(engine)
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    out, _ = parse_feedback(request, reply(strengths=[strength("c4", "모르겠습니다"), strength("c2", Q_C2)], gaps=[{"topic_id": "warmup", "text": "맡은 역할을 설명하지 않았습니다."}]))
    assert out is None  # a strength on not_shown, a strength on skipped, a gap on a demonstrated topic: nothing usable
    assert {t.topic_id: t.status for t in make(engine, llm=FakeLLM(reply(strengths=[strength("c4", "모르겠습니다")]))).topics}["c4"] == "not_shown"


def test_the_model_cannot_set_a_status_or_add_a_field():
    engine = standard()
    for extra in ({"statuses": {"c1": "demonstrated"}}, {"score": 80}, {"resources": [{"url": "https://evil.example/x"}]}, {"topics": []}):
        llm = RawLLM({**reply(improvements=["답변을 이어 가 보세요."]), **extra})
        report = make(engine, llm=llm)
        assert report.method == "rules" and len(llm.calls) == 1  # a schema error: the complete rules report
    nested = reply(strengths=[{**strength("c1", Q_C1), "status": "demonstrated"}])
    assert make(engine, llm=RawLLM(nested)).method == "rules"


# ── Sensitive information ──

DISCLOSURES = ["저는 스물일곱 살입니다. ", "통신병으로 근무했습니다. ", "저는 여자라서 어려움이 있었지만 ", "I am a mother of two. ", "20대 후반입니다. "]


@pytest.mark.parametrize("prefix", DISCLOSURES)
def test_a_disclosure_in_the_answers_reaches_neither_the_request_nor_the_report(prefix):
    engine = standard(prefix)
    transcript, plan = views(engine)
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    gone = {"스물일곱": "스물일곱", "통신병": "통신병", "여자라서": "여자", "mother": "mother", "20대": "20대"}
    marker = next(m for k, m in gone.items() if k in prefix)
    assert marker not in request.user and Q_C1 in request.user  # the professional part of the answer is still there
    disclosure = prefix.strip()
    for quote in (disclosure, prefix + Q_C1):  # the model never saw the disclosure, so it cannot be quoted
        report = merged(engine, reply(strengths=[strength("c1", quote)], improvements=["답변을 이어 가 보세요."]))
        assert not any(marker in s.quotes[0] for s in report.strengths)
    report = make(engine)
    assert marker not in json.dumps(report.to_data(), ensure_ascii=False)


def test_a_mixed_sentence_keeps_its_professional_clause_as_evidence():
    engine = play([GOOD["warmup"], "저는 27살이고 " + GOOD["c1"], GOOD["c2"], GOOD["c4"], GOOD["behavioral"]])
    transcript, plan = views(engine)
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    assert "27" not in request.user and Q_C1 in request.user
    report = merged(engine, reply(strengths=[strength("c1", Q_C1)]))
    assert [(s.topic_id, s.quotes) for s in report.strengths] == [("c1", (Q_C1,))]


@pytest.mark.parametrize(
    "text",
    [
        "스물일곱 살이라는 점이 장점입니다.", "27세 개발자로서 잘 설명했습니다.", "여성 지원자로서 인상적이었습니다.", "군 복무 경험이 도움이 되었습니다.",
        "As a mother of two, you explained well.", "통신병 경험을 살려 답변했습니다.", "20대 후반답게 설명했습니다.",
    ],
)
def test_a_generated_sentence_about_the_topics_is_dropped_everywhere(text):
    out, _ = parse_feedback(
        feedback_request(*(views(standard())), blocklists=BLOCKLISTS, skills=SKILLS),
        reply(
            strengths=[strength("c1", Q_C1, text)], gaps=[{"topic_id": "c3", "text": text}], improvements=[text, "답변을 이어 가 보세요."],
            practice_questions=[{"topic_id": "c1", "question": text.rstrip(".") + "?"}],
        ),
    )
    assert out.strengths == () and out.gaps == () and out.improvements == ("답변을 이어 가 보세요.",) and out.practice_questions == ()


# ── Screens: verdicts, ranks, scores, placeholders, URLs, blocklists ──

BAD_SENTENCES = [
    "이 답변이라면 합격입니다.", "채용하기에 적합한 답변이었습니다.", "탈락할 수 있는 답변이었습니다.", "불합격 가능성이 있습니다.",
    "상위 10%에 해당합니다.", "총점 80점 수준입니다.", "100점 만점에 70점입니다.", "3개 중 2개를 설명했습니다.", "다른 지원자보다 잘했습니다.",
    "평균보다 높은 수준입니다.", "You would pass this interview.", "Your score is high.", "You would be hired.", "[이름]님은 잘했습니다.",
    "https://example.com/guide 를 참고하세요.", "docs.example.io/guide 를 참고하세요.", "연락은 hr@example.com 으로 하세요.", "```json\n{}\n```",
    "회사가 요구하는 수준에 못 미칩니다.", "이 직무에서 필수로 알아야 하는 지식입니다.", "기업이 기대하는 답변이었습니다.", "The company requires more experience.",
    "결혼 계획이 있어도 잘 설명했습니다.", "자녀 계획에 대해서도 말씀해 보세요.", "종교와 상관없이 설명했습니다.", "정말 잘 설명했나요?", "가" * 250,
]


@pytest.mark.parametrize("text", BAD_SENTENCES)
def test_a_bad_sentence_is_rejected_in_every_section_and_a_good_one_next_to_it_survives(text):
    good = "답변을 이어 가 보세요."
    out, reason = parse_feedback(
        feedback_request(*(views(standard())), blocklists=BLOCKLISTS, skills=SKILLS),
        reply(
            strengths=[strength("c1", Q_C1, text), strength("c2", Q_C2, "문서화한 경험을 설명했습니다.")],
            gaps=[{"topic_id": "c3", "text": text}, {"topic_id": "c3", "text": "협업 태도는 다루지 못했습니다."}],
            improvements=[text, good],
            practice_questions=[{"topic_id": "c1", "question": text}, {"topic_id": "c1", "question": "Spring Boot 사용 경험을 실제 프로젝트 사례로 설명해 보세요."}],
        ),
    )
    assert reason == "ok"
    assert [s.topic_id for s in out.strengths] == ["c2"] and [g.text for g in out.gaps] == ["협업 태도는 다루지 못했습니다."]
    assert out.improvements == (good,) and [q.question for q in out.practice_questions] == ["Spring Boot 사용 경험을 실제 프로젝트 사례로 설명해 보세요."]


@pytest.mark.parametrize("text", ["Java 17 경험을 설명했습니다.", "REST API 설계 경험을 설명했습니다.", "프로젝트에서 팀 리더 역할을 설명했습니다."])
def test_the_score_screen_lets_ordinary_numbers_and_words_through(text):
    assert screen_feedback(text, BLOCKLISTS) == text


def test_a_generated_sentence_may_not_invent_a_technology_or_a_certification():
    transcript, plan = views(standard())
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    out, _ = parse_feedback(
        request,
        reply(
            strengths=[strength("c1", Q_C1, "Java와 Spring Boot로 주문 API를 만든 경험을 설명했습니다."), strength("c2", Q_C2, "Kubernetes 배포 경험을 설명했습니다.")],
            gaps=[{"topic_id": "c3", "text": "협업 도구인 Jira 사용은 다루지 못했습니다."}, {"topic_id": "c3", "text": "쿠버네티스 활용은 다루지 못했습니다."}],
            improvements=["정보처리기사 준비 경험도 함께 말해 보세요.", "답변을 이어 가 보세요."],
        ),
    )
    assert [s.topic_id for s in out.strengths] == ["c1"] and out.gaps == () and out.improvements == ("답변을 이어 가 보세요.",)
    assert set(out.dropped) == {"strength:text", "gap:text", "improvement:text"}


# ── Practice questions ──


def _practice(engine, *questions):
    request = feedback_request(*(views(engine)), blocklists=BLOCKLISTS, skills=SKILLS)
    out, _ = parse_feedback(request, reply(practice_questions=[{"topic_id": t, "question": q} for t, q in questions], improvements=["답변을 이어 가 보세요."]))
    return out


def test_practice_questions_must_be_grounded_new_and_screened():
    engine = standard()
    asked = next(i.question.value for i in plan_view(engine.state).items if i.topic_id == "c1")
    out = _practice(
        engine,
        ("c1", "Spring Boot 사용 경험을 실제 프로젝트 사례로 설명해 보세요."),  # grounded in the c1 rubric
        ("c2", "REST API 문서화를 어떻게 진행했는지 설명해 보세요."),
        ("c1", asked),  # exactly a question already asked
        ("c1", asked.replace("설명해 주세요", "말씀해 주세요")),  # nearly the same
        ("c1", "Spring Boot 사용 경험을 실제 프로젝트 사례로 설명해 보세요!"),  # the same suggestion twice
        ("c1", "좋아하는 영화를 소개해 보세요."),  # not about the topic
        ("c1", "Kubernetes 배포 경험을 설명해 보세요."),  # a technology that is not in the plan
        ("c1", "Spring Boot 기반 쿠버네티스 배포 경험을 설명해 보세요."),  # a Korean name of one
        ("c99", "Spring Boot 사용 경험을 설명해 보세요."),  # no such topic
        ("c1", "합격하려면 Spring Boot 사용 경험을 어떻게 설명해야 하나요?"),
        ("c1", "Spring Boot " + "사용 경험을 아주 길게 " * 20 + "설명해 보세요."),
    )
    assert [(q.topic_id, q.question) for q in out.practice_questions] == [
        ("c1", "Spring Boot 사용 경험을 실제 프로젝트 사례로 설명해 보세요."),
        ("c2", "REST API 문서화를 어떻게 진행했는지 설명해 보세요."),
    ]
    assert out.dropped.count("practice:grounding") == 1 and out.dropped.count("practice:duplicate") == 3 and out.dropped.count("practice:topic") == 1


def test_rejected_practice_suggestions_fall_back_to_the_rubric_templates():
    engine = mixed()
    rules = make(engine)
    report = merged(engine, reply(practice_questions=[{"topic_id": "c1", "question": "좋아하는 영화를 소개해 보세요."}], improvements=["답변을 이어 가 보세요."]))
    assert report.method == "llm:fake-llm" and report.practice_questions == rules.practice_questions and "practice_questions" in report.rules_sections
    assert report.practice_questions and all(feedback_module._grounded_in(q.question, q.topic_id, feedback_module._context(*_ctx_args(engine))) for q in report.practice_questions)


def _ctx_args(engine):
    transcript, plan = views(engine)
    return transcript, plan, SKILLS


def test_rules_practice_questions_repeat_nothing_that_was_asked():
    engine = mixed()
    transcript, plan = views(engine)
    asked = {i.question.value for i in plan.items} | {t.text.value for t in transcript if t.role == "agent" and t.kind in ("question", "follow_up")}
    report = rules_feedback(transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS)
    assert report.practice_questions and not any(q.question in asked for q in report.practice_questions)
    assert len({q.question for q in report.practice_questions}) == len(report.practice_questions)


# ── Resources ──


def test_links_come_only_from_the_approved_file_and_only_for_gap_topics():
    report = make(mixed())
    assert report.resources and all(r.url in YAML_URLS and r.topic_id.startswith("c") for r in report.resources)
    assert {(r.skill, r.url) for r in report.resources} >= {("Java", "https://dev.java/learn/"), ("Spring", "https://spring.io/guides")}
    assert make(standard()).resources == ()  # no gap on a criterion with a skill


def test_a_resource_marked_unverified_is_never_shown(tmp_path):
    path = tmp_path / "resources.yaml"
    path.write_text(
        'version: "t"\nskills:\n  Java: {title: "Java ok", url: "https://example.org/java"}\n  Spring: {title: "Spring hidden", url: "https://example.org/spring", verified: false}\ncertificates: {}\n',
        encoding="utf-8",
    )
    report = make(mixed(), resources=load_resources(path))
    assert [(r.skill, r.url) for r in report.resources] == [("Java", "https://example.org/java")]


def test_the_model_cannot_add_a_link_and_a_link_in_its_text_is_dropped():
    report = merged(
        mixed(),
        reply(gaps=[{"topic_id": "c1", "text": "https://evil.example/learn 에서 Spring Boot를 배워 보세요."}, {"topic_id": "c1", "text": "Spring Boot를 어떻게 사용했는지는 아직 설명하지 않았습니다."}], improvements=["답변을 이어 가 보세요."]),
    )
    assert [g.text for g in report.gaps] == ["Spring Boot를 어떻게 사용했는지는 아직 설명하지 않았습니다."]
    assert report.resources and all(r.url in YAML_URLS for r in report.resources)
    assert "evil" not in json.dumps(report.to_data())


def test_no_links_without_resources_or_skills_and_none_read_the_cv():
    transcript, plan = views(mixed())
    assert rules_feedback(transcript, plan, blocklists=BLOCKLISTS).resources == ()
    assert rules_feedback(transcript, plan, resources=RESOURCES, blocklists=BLOCKLISTS).resources == ()
    # the warm-up question quotes a line of the CV: its words never decide a link
    assert all(r.topic_id != "warmup" for r in make(mixed()).resources)


# ── Fallbacks ──


def test_no_client_gives_the_rules_report():
    assert make(mixed()).method == "rules"


@pytest.mark.parametrize("failure", [LLMError("boom"), RuntimeError("boom"), TimeoutError("late"), ConnectionError("down"), ValueError("odd")])
def test_a_failing_call_gives_the_complete_rules_report(failure):
    engine = mixed()
    llm = RawLLM(failure)
    report = make(engine, llm=llm)
    assert len(llm.calls) == 1 and report == make(engine)


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all", "", "{", "[1, 2, 3]", "null", 42, b"\xff\xfe", {"strengths": "not a list"}, {"strengths": [{"topic_id": "c1"}]},
        {"gaps": [{"topic_id": 1, "text": "x"}]}, {"improvements": [5]}, {"unknown": 1}, {}, reply(),
        reply(strengths=[strength("c1", "지어낸 문장입니다 가나다라마바")]),  # nothing usable survives
        reply(improvements=["이 지원자는 합격입니다."], gaps=[{"topic_id": "c1", "text": "상위 10%입니다."}]),
    ],
)
def test_an_invalid_or_empty_answer_gives_the_complete_rules_report(raw):
    engine = standard()
    llm = RawLLM(raw)
    report = make(engine, llm=llm)
    assert report == make(engine) and report.method == "rules" and report.rules_sections == () and len(llm.calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(reply(improvements=["답변을 이어 가 보세요."]), ensure_ascii=False),
        "```json\n" + json.dumps(reply(improvements=["답변을 이어 가 보세요."]), ensure_ascii=False) + "\n```",
        json.dumps(reply(improvements=["답변을 이어 가 보세요."]), ensure_ascii=False).encode("utf-8"),
        feedback_module.FeedbackLlmOut(improvements=["답변을 이어 가 보세요."]),
    ],
)
def test_a_valid_answer_is_accepted_as_text_fenced_text_bytes_or_the_model_object(raw):
    report = make(standard(), llm=RawLLM(raw))
    assert report.method == "llm:raw-llm" and report.improvements == ("답변을 이어 가 보세요.",)


def test_the_report_is_the_rules_report_when_the_seam_matches_the_vocabulary(monkeypatch):
    """compose refuses a request that still matches the vocabulary: no model is asked."""
    engine = standard()
    transcript, plan = views(engine)

    def refuse(*args, **kwargs):
        raise ValueError("matches the vocabulary")

    monkeypatch.setattr(feedback_module, "compose", refuse)
    llm = FakeLLM(reply(improvements=["답변을 이어 가 보세요."]))
    assert make_feedback(transcript, plan, resources=RESOURCES, skills=SKILLS, blocklists=BLOCKLISTS, llm=llm).method == "rules" and llm.calls == []


def test_a_client_that_returns_a_report_for_a_disclosure_only_interview_is_not_asked():
    engine = play(["저는 스물일곱 살입니다", "통신병으로 근무했습니다"])
    llm = FakeLLM(reply(improvements=["답변을 이어 가 보세요."]))
    report = make(engine, llm=llm)
    assert llm.calls == [] and report.method == "rules" and NOTE_NO_ANSWERS in report.notes


def test_a_gap_on_the_warm_up_never_gets_a_link():
    """The warm-up question quotes a line of the CV (with Java and Spring in it); its words must never decide a link."""
    engine = play(["모르겠습니다", GOOD["c1"], GOOD["c2"], GOOD["c4"], GOOD["behavioral"]])
    report = make(engine)
    assert {t.topic_id: t.status for t in report.topics}["warmup"] == "not_shown"
    assert "warmup" in [g.topic_id for g in report.gaps] and all(r.topic_id != "warmup" for r in report.resources)
    assert report.resources == ()  # nothing else had a gap on a criterion that names a skill


def test_a_strength_on_a_topic_that_showed_nothing_is_dropped_even_with_a_real_quote():
    """c1 ends `skipped` after two off-topic answers, so the candidate's lines exist and can be quoted exactly: only the status,
    which the engine owns, keeps the model from calling it a strength."""
    off = "오늘 점심은 뭐 먹을까요 날씨가 좋네요 정말 좋아요"
    engine = play([GOOD["warmup"], off, off, GOOD["c2"], GOOD["c4"], GOOD["behavioral"]])
    transcript, plan = views(engine)
    assert {i.topic_id: i.status for i in plan.items}["c1"] == "skipped"
    request = feedback_request(transcript, plan, blocklists=BLOCKLISTS, skills=SKILLS)
    out, _ = parse_feedback(request, reply(strengths=[strength("c1", "오늘 점심은 뭐 먹을까요", "점심 이야기를 나누었습니다."), strength("c2", Q_C2, "문서화한 경험을 설명했습니다.")]))
    assert [s.topic_id for s in out.strengths] == ["c2"] and out.dropped == ("strength:topic",)
