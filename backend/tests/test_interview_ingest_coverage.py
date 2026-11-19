"""The coverage snapshot of a practice interview (M4 S3a): its shape, and the structural rules between one snapshot and the next.

The agent is the source of the coverage; the backend checks the shape and the rules and stores it, and never works out or improves a
status. The rules are the ones the real engine obeys, and this file proves that against the real engine in both directions: scripted
interviews produce every allowed status transition, and randomized ones never produce a transition, a level change or a status the
rules would refuse. Then whole randomized interviews are posted through the backend, which must accept them all."""
import random

import pytest
from sqlalchemy import update

from ai.interview import AnswerType, InterviewEngine, InterviewPlan, PlanCriterion, TurnAnalysis, coverage_snapshot
from ai.interview.types import LEVEL_RANK
from app.core.config import settings
from app.models import InterviewSession, InterviewTurn
from app.services import ai_runtime, career_service
from app.services import interview_ingest_service as ingest
from app.services import interview_plan_service as plans
from app.services import interview_service as svc

from .interview_fixtures import SAMPLE_CV, Agent, Clock, build_world, new_session, turn_rows
from .test_interview_ingest_turns import ANSWER, cov, ev, plan_of, refuse, rec, row, started

# What a topic's status may do between two snapshots, written out here on purpose and not imported from the service. Taken from the
# engine: asked, then each answer re-derives the status from the best level of every point, a silence or skip ends it as `skipped`.
STATUSES = ["not_asked", "asked", "partial", "not_shown", "demonstrated", "skipped"]
LEGAL = {
    ("not_asked", "not_asked"), ("not_asked", "asked"),
    ("asked", "asked"), ("asked", "demonstrated"), ("asked", "partial"), ("asked", "not_shown"), ("asked", "skipped"),
    ("partial", "partial"), ("partial", "demonstrated"), ("partial", "skipped"),
    ("not_shown", "not_shown"), ("not_shown", "partial"), ("not_shown", "demonstrated"), ("not_shown", "skipped"),
    ("demonstrated", "demonstrated"), ("demonstrated", "skipped"),
    ("skipped", "skipped"),
}


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


# ── The shape ──


def snapshot_with(plan, **changes):
    base = cov(plan)
    base.update(changes)
    return base


SHAPE = [
    ("a key missing", lambda p: {k: v for k, v in cov(p).items() if k != "levels"}, "keys"),
    ("a key extra", lambda p: {**cov(p), "note": "x"}, "keys"),
    ("not a mapping", lambda p: ["listening"], "keys"),
    ("the phase of an end on a turn", lambda p: snapshot_with(p, phase="ended"), "phase"),
    ("an unknown phase", lambda p: snapshot_with(p, phase="running"), "phase"),
    ("an end reason while listening", lambda p: snapshot_with(p, end_reason="time"), "end_reason"),
    ("status that is not a mapping", lambda p: snapshot_with(p, status=["asked"]), "shape"),
    ("levels that are not a mapping", lambda p: snapshot_with(p, levels=["p1"]), "shape"),
    ("a topic missing from the status", lambda p: snapshot_with(p, status={t: s for t, s in cov(p)["status"].items() if t != "behavioral"}), "topics"),
    ("a topic of no plan in the status", lambda p: snapshot_with(p, status={**cov(p)["status"], "c99": "asked"}), "topics"),
    ("an unknown status", lambda p: snapshot_with(p, status={**cov(p)["status"], "c2": "great"}), "status"),
    ("a level for a topic of no plan", lambda p: snapshot_with(p, levels={"c99": {}}), "levels"),
    ("a point of no rubric", lambda p: snapshot_with(p, levels={"c1": {"p9": "partial"}}), "levels"),
    ("an unknown level", lambda p: snapshot_with(p, levels={"c1": {"p1": "excellent"}}), "levels"),
    ("levels of a topic that are not a mapping", lambda p: snapshot_with(p, levels={"c1": ["p1"]}), "levels"),
    ("too many topics", lambda p: snapshot_with(p, status={f"c{i}": "asked" for i in range(70)}), "shape"),
]


@pytest.mark.parametrize("name, build, field", SHAPE, ids=[s[0] for s in SHAPE])
def test_a_snapshot_of_the_wrong_shape_is_refused(db, clock, sid, name, build, field):
    plan = plan_of(db, sid)
    refuse(db, sid, ev(plan, coverage=build(plan)), clock, 422, "INTERVIEW_BAD_COVERAGE", field=field)
    assert row(db, sid).status == "created" and row(db, sid).coverage is None


def test_the_size_limit_applies_to_the_stored_form(db, clock, sid, monkeypatch):
    plan = plan_of(db, sid)
    monkeypatch.setattr(settings, "INTERVIEW_COVERAGE_MAX_BYTES", 100)
    refuse(db, sid, ev(plan), clock, 422, "INTERVIEW_BAD_COVERAGE", field="size")
    monkeypatch.setattr(settings, "INTERVIEW_COVERAGE_MAX_BYTES", 4096)
    assert rec(db, sid, ev(plan), clock).outcome == "stored"
    assert settings.INTERVIEW_COVERAGE_MAX_BYTES == 4096


def test_the_stored_snapshot_is_the_sanitized_one_in_plan_order(db, clock, sid):
    plan = plan_of(db, sid)
    shuffled = dict(reversed(list(cov(plan)["status"].items())))
    rec(db, sid, ev(plan, coverage={**cov(plan), "status": shuffled}), clock)
    stored = row(db, sid).coverage
    assert list(stored["status"]) == [i.topic_id for i in plan.items] and stored == cov(plan)


# ── The rules between two snapshots ──


def prepare(db, sid, clock, previous, answered=(0,)):
    """A live session whose stored coverage is `previous` and that has a candidate answer for each item index in `answered`
    (written directly, so the rules under test are the only ones in play). The sequence number of the next turn."""
    plan = started(db, sid, clock)
    seq = 1
    for index in answered:
        seq += 1
        db.add(InterviewTurn(session_id=sid, seq=seq, role="candidate", kind="answer", item_index=index, text="답변", method="rules", analysis=dict(ANSWER)))
    db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(coverage=previous))
    db.commit()
    return plan, seq + 1


def next_event(plan, seq, coverage):
    return ev(plan, seq, "agent", "nudge", 0, coverage=coverage)


@pytest.mark.parametrize("old", STATUSES)
@pytest.mark.parametrize("new", STATUSES)
def test_every_status_transition_is_allowed_or_refused_as_the_engine_does(db, clock, sid, old, new):
    topic = "c1"
    plan = plan_of(db, sid)
    previous = cov(plan, {topic: old})
    plan, seq = prepare(db, sid, clock, previous)
    event = next_event(plan, seq, cov(plan, {topic: new}))
    if (old, new) in LEGAL:
        assert rec(db, sid, event, clock).outcome == "stored"
        assert row(db, sid).coverage["status"][topic] == new
    else:
        refuse(db, sid, event, clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_transition")
        assert row(db, sid).coverage == previous and len(turn_rows(db, sid)) == seq - 1  # nothing of the refused turn is stored


def test_the_first_snapshot_starts_from_nothing_asked(db, clock, sid):
    plan = plan_of(db, sid)
    # from the implicit start state only "not asked" and "asked" are possible
    for status in ("partial", "not_shown", "demonstrated", "skipped"):
        refuse(db, sid, ev(plan, coverage=cov(plan, {"c1": status})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_transition")
    assert rec(db, sid, ev(plan, coverage=cov(plan, {"c1": "asked", "c2": "not_asked"})), clock).started is True


def test_a_topic_never_goes_back_to_not_asked(db, clock, sid):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "asked", "c2": "asked"}), answered=())
    refuse(db, sid, next_event(plan, seq, cov(plan, {"c1": "asked", "c2": "not_asked"})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_transition")


# ── Levels ──


def rubric_ids(plan, topic="c1"):
    return [p.id for p in next(i for i in plan.items if i.topic_id == topic).rubric]


def test_levels_may_stay_or_rise_and_new_points_may_appear(db, clock, sid):
    plan = plan_of(db, sid)
    p1, p2, p3 = rubric_ids(plan)
    previous = cov(plan, {"c1": "partial"}, levels={"c1": {p1: "partial"}})
    plan, seq = prepare(db, sid, clock, previous)
    steps = [{p1: "partial"}, {p1: "demonstrated"}, {p1: "demonstrated", p2: "not_shown"}, {p1: "demonstrated", p2: "partial", p3: "demonstrated"}]
    for levels in steps:
        assert rec(db, sid, next_event(plan, seq, cov(plan, {"c1": "partial"}, levels={"c1": levels})), clock).outcome == "stored"
        seq += 1
    assert row(db, sid).coverage["levels"] == {"c1": {p1: "demonstrated", p2: "partial", p3: "demonstrated"}}


@pytest.mark.parametrize(
    "before, after",
    [
        ({"p1": "demonstrated"}, {"p1": "partial"}),
        ({"p1": "partial"}, {"p1": "not_shown"}),
        ({"p1": "demonstrated"}, {"p1": "not_shown"}),
        ({"p1": "partial"}, {}),  # a point never disappears
        ({"p1": "partial", "p2": "demonstrated"}, {"p1": "demonstrated"}),
    ],
)
def test_a_level_never_goes_down_and_a_point_never_disappears(db, clock, sid, before, after):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "partial"}, levels={"c1": before}))
    refuse(db, sid, next_event(plan, seq, cov(plan, {"c1": "partial"}, levels={"c1": after})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="level_regressed")


def test_a_topic_whose_levels_disappear_is_refused(db, clock, sid):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "partial"}, levels={"c1": {"p1": "partial"}}))
    refuse(db, sid, next_event(plan, seq, cov(plan, {"c1": "partial"}, levels={})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="level_regressed")


# ── A status or a level that only an answer can give needs a stored answer ──


@pytest.mark.parametrize("status", ["demonstrated", "partial", "not_shown"])
def test_a_status_that_only_an_answer_can_give_needs_a_stored_candidate_answer(db, clock, sid, status):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "asked", "c2": "asked"}), answered=(0,))
    refuse(db, sid, next_event(plan, seq, cov(plan, {"c1": "asked", "c2": status})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_without_answer")
    assert rec(db, sid, next_event(plan, seq, cov(plan, {"c1": status, "c2": "asked"})), clock).outcome == "stored"  # c1 has an answer


def test_the_answer_of_this_very_turn_counts(db, clock, sid):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "asked", "c2": "asked"}), answered=(0,))
    answer = ev(plan, seq, "candidate", "answer", 1, coverage=cov(plan, {"c1": "asked", "c2": "partial"}), analysis=dict(ANSWER))
    assert rec(db, sid, answer, clock).outcome == "stored"


def test_asked_and_skipped_need_no_answer(db, clock, sid):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "asked", "c2": "asked"}), answered=())
    assert rec(db, sid, next_event(plan, seq, cov(plan, {"c1": "asked", "c2": "skipped", "c3": "asked"})), clock).outcome == "stored"


def test_levels_of_a_topic_nobody_answered_are_refused(db, clock, sid):
    plan = plan_of(db, sid)
    plan, seq = prepare(db, sid, clock, cov(plan, {"c1": "asked", "c2": "asked"}), answered=(0,))
    refuse(db, sid, next_event(plan, seq, cov(plan, {"c1": "asked", "c2": "asked"}, levels={"c2": {}})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_without_answer")


def test_the_backend_does_not_improve_or_infer_a_status_from_what_was_said(db, clock, sid):
    """Whatever the answer says and whatever its analysis claims, the status stored is the one in the snapshot."""
    plan = started(db, sid, clock)
    points = {p: "demonstrated" for p in rubric_ids(plan)}
    keywords = "Java Spring Boot API 개발 장애 테스트 모니터링 협업 소통 문서화 코드 리뷰"
    rec(db, sid, ev(plan, 2, "candidate", "answer", text=keywords, analysis={**ANSWER, "points": points}, coverage=cov(plan)), clock)
    stored = row(db, sid).coverage
    assert stored["status"]["c1"] == "asked" and stored["levels"] == {}


# ── Against the real engine ──

CRIT = [
    PlanCriterion(1, "Java", "skill", "Java 개발 경험", "핵심", 0),
    PlanCriterion(2, "Spring Boot", "skill", "Spring Boot 실무", "핵심", 1),
    PlanCriterion(3, "MySQL", "skill", "MySQL 운영", "중요", 2),
    PlanCriterion(4, "협업", "other", "팀 협업 경험", "중요", 3),
]
TEXTS = [
    "", "네", "음 글쎄요 잘 모르겠습니다", "다시 한 번 말씀해 주시겠어요", "질문이 무슨 뜻인지 잘 모르겠어요 설명해 주세요",
    "저는 어제 점심으로 김치찌개를 먹었고 날씨가 좋아서 산책을 했습니다 정말 즐거웠어요",
    "Java와 Spring Boot로 주문 API를 개발했고 트랜잭션 경계를 정리해서 장애를 줄였습니다 테스트 커버리지도 높였습니다",
    "MySQL 인덱스 설계와 쿼리 튜닝으로 응답 시간을 줄였고 모니터링 대시보드를 구축해서 운영했습니다 장애 대응도 담당했습니다",
    "팀 협업에서는 코드 리뷰와 문서화를 통해 갈등을 조정하고 일정을 맞추기 위해 서로 소통했습니다 그래서 프로젝트를 성공적으로 마쳤습니다",
]


def engine_plan() -> InterviewPlan:
    sealed = plans.build_canonical_plan(
        stored_cv=SAMPLE_CV, job_title="Backend Engineer", job_text="Java/Spring 백엔드 API 개발", criteria=CRIT,
        blocklists=career_service.interview_blocklists(), embedder=ai_runtime.embedder(), skills=ai_runtime.skills(),
        limits=plans.limits_from_settings(), llm=None,
    )
    return InterviewPlan.from_dict(sealed.data)


PLAN = engine_plan()


class Watch:
    """Runs a real engine and records every transition of every topic between two snapshots, and checks the invariants."""

    def __init__(self):
        self.engine = InterviewEngine(PLAN, blocklists=career_service.interview_blocklists())
        self.engine.start()
        self.previous = {"status": {i.topic_id: "not_asked" for i in PLAN.items}, "levels": {}}
        self.transitions: set[tuple[str, str]] = set()
        self.problems: list[str] = []
        self.look()

    def look(self):
        snap = coverage_snapshot(self.engine.state)
        for topic, new in snap["status"].items():
            self.transitions.add((self.previous["status"][topic], new))
        for topic, points in self.previous["levels"].items():
            for pid, level in points.items():
                now = snap["levels"].get(topic, {}).get(pid)
                if now is None or LEVEL_RANK[now] < LEVEL_RANK[level]:
                    self.problems.append("level regressed")
        answered = {t.item_index for t in self.engine.state.turns if t.role == "candidate"}
        for index, item in enumerate(PLAN.items):
            if (snap["status"][item.topic_id] in ("demonstrated", "partial", "not_shown") or item.topic_id in snap["levels"]) and index not in answered:
                self.problems.append("status without answer")
        self.previous = snap

    def answer(self, text="Java와 Spring Boot로 API를 개발하고 운영했습니다 장애 대응도 했습니다", analysis=None, at=20.0):
        self.engine.on_answer(text, at, analysis)
        self.look()

    def silence(self, seconds=46, at=20.0):
        self.engine.on_silence(seconds, at)
        self.look()

    def points(self, level, only=None):
        return {p.id: level for p in self.engine.state.current.rubric if only is None or p.id in only}

    def analysis(self, level, only=None, kind=AnswerType.ANSWERED):
        return TurnAnalysis(kind, self.points(level, only), (), None, "llm:fake")

    def first_point(self):
        return {self.engine.state.current.rubric[0].id}


def scripted():
    """One scenario per allowed transition, on the real engine. Each returns the Watch that ran it."""
    runs = {}
    w = Watch()
    runs["start"] = w  # not_asked -> asked
    w = Watch(); w.answer(analysis=w.analysis("demonstrated")); runs["asked -> demonstrated"] = w
    w = Watch(); w.answer(analysis=w.analysis("demonstrated", w.first_point())); runs["asked -> partial"] = w
    w = Watch(); w.answer("잘 모르겠습니다"); runs["asked -> not_shown"] = w
    w = Watch(); w.silence(46); runs["asked -> skipped"] = w
    w = Watch(); w.answer(analysis=w.analysis("demonstrated", w.first_point(), AnswerType.PARTIAL)); w.answer(analysis=w.analysis("demonstrated")); runs["partial -> demonstrated"] = w
    w = Watch(); w.answer(analysis=w.analysis("demonstrated", w.first_point(), AnswerType.PARTIAL)); w.silence(46); runs["partial -> skipped"] = w
    w = Watch(); w.answer(analysis=w.analysis("not_shown", None, AnswerType.PARTIAL)); w.answer(analysis=w.analysis("demonstrated", w.first_point(), AnswerType.PARTIAL)); runs["not_shown -> partial"] = w
    w = Watch(); w.answer(analysis=w.analysis("not_shown", None, AnswerType.PARTIAL)); w.answer(analysis=w.analysis("demonstrated")); runs["not_shown -> demonstrated"] = w
    w = Watch(); w.answer(analysis=w.analysis("not_shown", None, AnswerType.PARTIAL)); w.silence(46); runs["not_shown -> skipped"] = w
    w = Watch(); w.answer(analysis=w.analysis("demonstrated", None, AnswerType.OFF_TOPIC)); w.silence(46); runs["demonstrated -> skipped"] = w
    return runs


def test_the_real_engine_produces_every_transition_the_rules_allow_and_no_other():
    runs = scripted()
    seen = set().union(*(w.transitions for w in runs.values()))
    assert {t for t in seen if t[0] != t[1]} == {t for t in LEGAL if t[0] != t[1]}  # every allowed change was made by the engine
    for name, (old, new) in {"asked -> demonstrated": ("asked", "demonstrated"), "demonstrated -> skipped": ("demonstrated", "skipped"), "not_shown -> partial": ("not_shown", "partial")}.items():
        assert (old, new) in runs[name].transitions, name
    assert seen <= LEGAL
    assert all(not w.problems for w in runs.values())


def test_the_service_table_is_exactly_what_the_real_engine_does():
    table = {(old, new) for old, news in ingest.STATUS_TRANSITIONS.items() for new in news}
    assert table == LEGAL
    assert set(ingest.STATUS_TRANSITIONS) == set(STATUSES) and ingest.NEEDS_ANSWER == {"demonstrated", "partial", "not_shown"}


def fuzz(seed):
    rng = random.Random(seed)
    w = Watch()
    clock = 0.0
    for _ in range(80):
        if w.engine.state.phase.value != "listening":
            break
        clock += rng.uniform(5, 70)
        roll = rng.random()
        if roll < 0.18:
            w.engine.on_silence(rng.choice([10, 21, 30, 46, 60]), clock)
        elif roll < 0.21:
            w.engine.abort(rng.choice(["candidate_left", "session_closed:x"]), clock)
        else:
            item = w.engine.state.current
            analysis = None
            if rng.random() > 0.4:
                points = {p.id: rng.choice(list(LEVEL_RANK)) for p in item.rubric if rng.random() < 0.7}
                analysis = TurnAnalysis(rng.choice([AnswerType.ANSWERED, AnswerType.PARTIAL, AnswerType.OFF_TOPIC, AnswerType.DONT_KNOW]), points, (), None, "llm:fake")
            w.engine.on_answer(rng.choice(TEXTS), clock, analysis)
        w.look()
    return w


def test_randomized_interviews_on_the_real_engine_never_break_the_rules():
    seen, problems = set(), []
    for seed in range(300):
        w = fuzz(seed)
        seen |= w.transitions
        problems += w.problems
    assert problems == [] and seen <= LEGAL  # nothing outside the table, no regressed level, no status without an answer
    assert len(seen) >= 15  # and the run was varied (the rarest transitions are the scripted test's job: it makes every one)


# ── Whole interviews through the backend ──


def drive(agent: Agent, rng: random.Random):
    """Randomized candidate behaviour on the real engine, posting everything; the budget is kept under 600 seconds on purpose
    (an answer received after it is refused, which is its own test)."""
    agent.start()
    for _ in range(80):
        if agent.engine.state.phase.value != "listening":
            return
        seconds = min(rng.uniform(5, 70), max(1.0, 595 - agent.elapsed))
        roll = rng.random()
        if roll < 0.18:
            agent.silence(rng.choice([10, 21, 30, 46]), seconds=seconds)
        elif roll < 0.21:
            agent.abort(rng.choice(["candidate_left", "session_closed:x"]), seconds=min(5.0, seconds))
        else:
            item = agent.engine.state.current
            analysis = None
            if rng.random() > 0.4:
                points = {p.id: rng.choice(list(LEVEL_RANK)) for p in item.rubric if rng.random() < 0.7}
                analysis = TurnAnalysis(rng.choice([AnswerType.ANSWERED, AnswerType.PARTIAL, AnswerType.OFF_TOPIC, AnswerType.DONT_KNOW]), points, (), None, "llm:fake")
            agent.answer(rng.choice(TEXTS), seconds=seconds, analysis=analysis)


@pytest.mark.parametrize("seed", range(24))
def test_the_backend_accepts_whole_randomized_interviews_from_the_real_engine(db, world, clock, seed):
    sid = new_session(db, world, clock)
    agent = Agent(db, sid, clock, names=[world.user.display_name])
    drive(agent, random.Random(1000 + seed))
    engine = agent.engine
    r = row(db, sid)
    assert r.status == {"ended": "completed", "aborted": "aborted", "listening": "live"}[engine.state.phase.value]
    stored = turn_rows(db, sid)
    expected = [t for t in engine.state.turns]
    assert [(t.seq, t.role, t.kind, t.item_index, t.text) for t in stored] == [(t.seq, t.role, t.kind, t.item_index, t.text) for t in expected]
    if engine.state.phase.value != "listening":
        assert r.coverage["status"] == coverage_snapshot(engine.state)["status"] and r.coverage["levels"] == coverage_snapshot(engine.state)["levels"]
        assert r.coverage["phase"] == engine.state.phase.value
        expected_reason = ingest.normalize_end_reason(engine.state.end_reason)
        assert r.end_reason == expected_reason and r.ended_at is not None and r.active_until is None
