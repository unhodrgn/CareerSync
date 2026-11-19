"""Builders shared by the feedback service tests (M4 S3b): finished interviews, hand-made ones with a plan of our choosing, a model that
records how it was called, and the state of a session's feedback columns. Synthetic data only; no network, no real model."""
from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from ai.interview import InterviewPlan, PlanItem, RubricPoint
from ai.interview.rules import GENERIC_REPHRASE
from ai.llm.client import LLMError
from app.models import InterviewSession, InterviewTurn
from app.models.interview import QuotaKind
from app.services import ai_runtime
from app.services import interview_quota_service as quota
from app.services.interview_plan_service import plan_digest

from .interview_fixtures import LIMITS, Agent, Clock, World, new_session  # noqa: F401  (re-exported for the tests)

ANSWER_TEXT = "Java와 Spring Boot로 REST API를 설계하고 트랜잭션 처리와 단위 테스트를 적용해서 장애를 줄였습니다. 팀원들과 코드 리뷰로 협업했습니다."

# A reply that survives every check of `parse_feedback`: one improvement, no quote, no technology name, nothing about the company
USABLE = {"strengths": [], "gaps": [], "improvements": ["답변은 상황과 역할, 해결 과정과 결과의 순서로 구성해 보세요."], "practice_questions": []}


class Crash(BaseException):
    """A process that dies mid-call. Not an Exception, so nothing in the service may swallow it as a model failure."""


class SpyLLM:
    """The feedback model: records every request and whether the session had a transaction open, then answers `reply`, fails, or crashes.

    `on_call(llm)` runs inside the call, where no transaction of the service is open: a test acts as another request there."""

    def __init__(self, db=None, *, model="spy-llm", reply=None, fail=False, crash=False, on_call=None):
        self.db, self.model, self.reply, self.fail, self.crash, self.on_call = db, model, reply, fail, crash, on_call
        self.calls: list[tuple[str, str, type]] = []
        self.in_transaction: list[bool] = []

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.calls.append((system, user, schema))
        if self.db is not None:
            self.in_transaction.append(self.db.in_transaction())
        if self.on_call is not None:
            self.on_call(self)
        if self.crash:
            raise Crash()
        if self.fail:
            raise LLMError("down")
        return {key: list(value) for key, value in (USABLE if self.reply is None else self.reply).items()}


def install(monkeypatch, llm) -> None:
    """The service takes its model from `ai_runtime.llm()`: None is rules mode."""
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)


def finished_session(db, world: World, clock: Clock, *, text: str = ANSWER_TEXT, names=()) -> int:
    """A session the real engine ran to its end in rules mode (completed, with a closing line), through the real ingest."""
    sid = new_session(db, world, clock)
    agent = Agent(db, sid, clock, names=names)
    agent.start()
    for _ in range(30):
        if agent.engine.state.phase.value in ("ended", "aborted"):
            break
        agent.answer(text)
    assert agent.engine.state.phase.value == "ended"
    return sid


def row(db, session_id: int) -> InterviewSession:
    db.rollback()
    db.expire_all()
    return db.get(InterviewSession, session_id)


def feedback_used(db, world: World, clock: Clock) -> int:
    value = quota.used(db, world.user.id, QuotaKind.FEEDBACK_MODEL, now=clock())
    db.rollback()
    return value


def other_session(db):
    """A second database session on the same engine: another request. The service holds no transaction while a model is called, so
    on the single connection of the SQLite fixture it can run inside the call."""
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)()


# ── A session made by hand, with a plan of our choosing ──


def plan_item(n: int, name: str, *, kind: str = "technical", importance: str = "핵심") -> PlanItem:
    """An item that passes `validate_plan` as it is (kind "bogus" makes `validate_plan` drop it)."""
    return PlanItem(
        topic_id=f"c{n}",
        kind=kind,
        question=f"{name}를 실무에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요.",
        rephrase=GENERIC_REPHRASE,
        rubric=(
            RubricPoint("p1", f"{name}의 핵심 개념과 동작 방식", ("개념", "동작"), 1),
            RubricPoint("p2", f"{name}를 사용한 실제 사례", ("사용", "적용"), 1),
        ),
        topic_keywords=(name.lower().replace(" ", ""),),
        criterion_id=n,
        criterion_name=name,
        importance=importance,
        intent=f"{name} 경험 확인",
        answer_tips=("구체적으로 설명해 보세요",),
    )


def covered(plan_items, statuses: dict[str, str], phase: str = "ended", end_reason: str | None = "plan_exhausted") -> dict:
    topics = [i.topic_id for i in plan_items]
    levels = {t: {"p1": "demonstrated", "p2": "demonstrated"} for t, s in statuses.items() if s == "demonstrated"}
    return {"phase": phase, "end_reason": end_reason, "status": {t: statuses.get(t, "not_asked") for t in topics}, "levels": levels}


def candidate_turn(seq: int, index: int, text: str, quote: str) -> dict:
    analysis = {"answer_type": "answered", "points": {"p1": "demonstrated", "p2": "demonstrated"}, "quotes": [quote], "method": "rules"}
    return {"seq": seq, "role": "candidate", "kind": "answer", "item_index": index, "text": text, "analysis": analysis}


def agent_turn(seq: int, index: int, text: str) -> dict:
    return {"seq": seq, "role": "agent", "kind": "question", "item_index": index, "text": text, "analysis": None}


def hand_session(
    db,
    world: World,
    clock: Clock,
    items,
    *,
    turns=(),
    coverage=None,
    status: str = "completed",
    plan_data="auto",
    sha256="auto",
    end_reason: str | None = "plan_exhausted",
) -> int:
    """A finished session whose plan, digest, coverage and turns are written directly. `plan_data="auto"`: the plan of `items`;
    `sha256="auto"`: its digest (None: no digest; a string: that digest)."""
    data = InterviewPlan(tuple(items), ()).to_dict() if plan_data == "auto" else plan_data
    now = clock()
    session = InterviewSession(
        seeker_id=world.user.id,
        job_id=world.job_id,
        cv_profile_id=world.cv_profile_id,
        status=status,
        end_reason=end_reason,
        plan=data,
        plan_method="rules",
        plan_sha256=(plan_digest(data) if isinstance(data, dict) else None) if sha256 == "auto" else sha256,
        prompt_version="v1",
        limits=dict(LIMITS),
        coverage=coverage,
        consent_version="2026-11-16",
        consent_at=now,
        created_at=now,
        ended_at=now,
        expires_at=now + timedelta(days=30),
    )
    db.add(session)
    db.flush()
    for turn in turns:
        db.add(InterviewTurn(session_id=session.id, method="rules", masked_kinds={}, created_at=now, **turn))
    db.commit()
    return session.id


def askable_session(db, world: World, clock: Clock) -> int:
    """A finished session written by hand whose plan is a fixed point of the validation and has a candidate answer: a model is asked
    for it. Cheap, so the concurrency tests make many."""
    items = [plan_item(1, "Java"), plan_item(2, "Spring Boot"), plan_item(3, "협업", kind="behavioral")]
    quote = "Java 트랜잭션 처리를 직접 설계했습니다"
    turns = [agent_turn(1, 0, "Java를 실무에서 어떻게 사용했는지 설명해 주세요."), candidate_turn(2, 0, f"저는 {quote}. 그래서 장애가 줄었습니다.", quote)]
    return hand_session(db, world, clock, items, turns=turns, coverage=covered(items, {"c1": "demonstrated"}))
