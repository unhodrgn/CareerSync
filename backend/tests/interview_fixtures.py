"""Builders and a fixture shared by the practice-interview schema tests (M4 S1): rows for the tables the interview tables
point at, an InterviewSession with valid defaults, and an SQLite engine that enforces foreign keys."""
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai.interview import InterviewEngine, InterviewLimits, InterviewPlan, TurnAnalysis, coverage_snapshot  # noqa: F401  (TurnAnalysis: for the tests)
from ai.llm.client import LLMError
from app.core.config import settings
from app.db.session import Base
from app.models import Company, CvDocument, CvProfile, InterviewSession, InterviewTurn, JobCriterion, JobPosting, User
from app.services import interview_ingest_service as ingest
from app.services import interview_service
from app.services.career_service import interview_blocklists

CONSENT_VERSION = "2026-11-26"
LIMITS = {"max_questions": 5, "max_seconds": 600, "max_followups_per_item": 2, "max_clarifies_per_item": 1}


@pytest.fixture
def fk_db():
    """An in-memory SQLite database that enforces foreign keys (the shared `db` fixture does not: SQLite ignores them by
    default), so a cascade can be tested at the database level."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@dataclass(frozen=True)
class Ids:
    seeker_id: int
    job_id: int
    cv_id: int


def add_seeker(db: Session, email: str = "s1@interview.test") -> User:
    user = User(email=email, password_hash="x", role="seeker")
    db.add(user)
    db.flush()
    return user


def build_ids(db: Session, email: str = "s1@interview.test") -> Ids:
    """A seeker with a CV profile, and a job of a company, committed."""
    seeker = add_seeker(db, email)
    company = Company(name=f"Acme {email}")
    db.add(company)
    db.flush()
    job = JobPosting(company_id=company.id, title="Backend Engineer", description="Java/Spring")
    document = CvDocument(seeker_id=seeker.id, file_name="cv.pdf", sha256="0" * 64, pages=1, masked_text="경력\n- Java")
    db.add_all([job, document])
    db.flush()
    profile = CvProfile(cv_document_id=document.id, seeker_id=seeker.id, version=1, schema_version="cv_profile.v1", method="rules")
    db.add(profile)
    db.commit()
    return Ids(seeker.id, job.id, profile.id)


def make_session(ids: Ids, **overrides) -> InterviewSession:
    """An InterviewSession with every required column set; override what a test is about."""
    now = datetime.now(UTC)
    values = {
        "seeker_id": ids.seeker_id,
        "job_id": ids.job_id,
        "cv_profile_id": ids.cv_id,
        "status": "created",
        "prompt_version": "v1",
        "limits": dict(LIMITS),
        "consent_version": CONSENT_VERSION,
        "consent_at": now,
        "expires_at": now + timedelta(days=30),
    }
    values.update(overrides)
    return InterviewSession(**values)


# ── S2: a seeker who can start a practice interview, a clock that can move, and a planning model that records how it was called ──

# A masked CV as it is stored (Q24: it still has what the interview must not use). The lines before the first section heading and
# the 인적사항 block are removed by `clean_cv`; the rest is the cleaned CV.
SAMPLE_CV = """홍길동 | 서울특별시 강남구 테헤란로 123 거주중인 개발자
성별: 남
경력
- Java와 Spring Boot로 주문 API를 개발했습니다 (2022.03-2024.02)
- 결제 서비스 모니터링 대시보드를 구축하고 장애 대응을 담당했습니다
프로젝트
- 주문 처리 시스템 리팩터링: 트랜잭션 경계를 정리하고 테스트 커버리지를 높였습니다
인적사항
병역: 군필 (육군 병장 만기전역 2018년)
취미: 등산과 마라톤을 즐기는 사람입니다
기술
Java, Spring Boot, MySQL
"""
REMOVED_LINES = (
    "홍길동 | 서울특별시 강남구 테헤란로 123 거주중인 개발자",
    "병역: 군필 (육군 병장 만기전역 2018년)",
    "취미: 등산과 마라톤을 즐기는 사람입니다",
)
KEPT_LINES = (
    "Java와 Spring Boot로 주문 API를 개발했습니다 (2022.03-2024.02)",
    "결제 서비스 모니터링 대시보드를 구축하고 장애 대응을 담당했습니다",
    "주문 처리 시스템 리팩터링: 트랜잭션 경계를 정리하고 테스트 커버리지를 높였습니다",
    "Java, Spring Boot, MySQL",
)
# (name, category, weight, description)
CRITERIA = (
    ("Java", "skill", 50, "Java 개발 경험"),
    ("Spring Boot", "skill", 30, "Spring Boot 실무 경험"),
    ("협업", "other", 20, "팀 협업 경험"),
)


class Clock:
    """A clock a test can move. Aware UTC, like the real one."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 16, 3, 0, tzinfo=UTC)  # 12:00 KST

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class World:
    user: User
    job_id: int
    cv_profile_id: int
    cv_document_id: int


def build_world(
    db: Session,
    *,
    email: str = "s1@interview.test",
    masked_cv: str = SAMPLE_CV,
    criteria=CRITERIA,
    confirmed: bool = True,
    ai_consent: bool = True,
    status: str = "published",
    deadline: date | None = None,
    role: str = "seeker",
) -> World:
    """A seeker with AI consent and a confirmed CV, and a published job with criteria (each argument turns one gate off)."""
    now = datetime.now(UTC)
    company = Company(name=f"Acme {email}")
    db.add(company)
    db.flush()
    user = User(
        email=email,
        password_hash="x",
        role=role,
        company_id=company.id if role == "company" else None,
        consent_privacy_at=now if ai_consent else None,
        consent_ai_at=now if ai_consent else None,
        consent_version=settings.CONSENT_VERSION if ai_consent else None,
    )
    job = JobPosting(company_id=company.id, title="Backend Engineer", description="Java/Spring 백엔드 API 개발", status=status, deadline=deadline)
    db.add_all([user, job])
    db.flush()
    for position, (name, category, weight, description) in enumerate(criteria):
        db.add(JobCriterion(job_id=job.id, name=name, description=description, category=category, weight=weight, position=position, guardrail_version="test"))
    document = CvDocument(seeker_id=user.id, file_name="cv.pdf", sha256="0" * 64, pages=1, masked_text=masked_cv)
    db.add(document)
    db.flush()
    profile = CvProfile(
        cv_document_id=document.id, seeker_id=user.id, version=1, schema_version="cv_profile.v1", method="rules", confirmed_at=now if confirmed else None
    )
    db.add(profile)
    db.commit()
    return World(user, job.id, profile.id, document.id)


class PlanLLM:
    """The planning model: one question per criterion of the prompt, recording every request. No network.

    `question(criterion_id, name)` writes each question's text; `cv_quote` makes every question quote a CV line (verified by the
    D21 planner against the cleaned CV); `on_call(llm)` runs inside the call (to move the clock, or to act as another request);
    `fail` raises LLMError, which the planner turns into the template."""

    model = "fake-llm"

    def __init__(self, db: Session | None = None, *, question: Callable[[int, str], str] | None = None, cv_quote: str | None = None, fail: bool = False, on_call=None):
        self.db, self.fail, self.on_call, self.cv_quote = db, fail, on_call, cv_quote
        self.question = question or (lambda _cid, name: f"{name} 관련 경험을 말씀해 주세요.")
        self.calls: list[tuple[str, str]] = []
        self.in_transaction: list[bool] = []

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.calls.append((system, user))
        if self.db is not None:
            self.in_transaction.append(self.db.in_transaction())
        if self.on_call is not None:
            self.on_call(self)
        if self.fail:
            raise LLMError("down")
        lines = re.search(r"<criteria>\n(.*?)\n</criteria>", user, re.S).group(1).splitlines()
        questions = []
        for line in lines:
            cid, name = line.split(" | ")[:2]
            base = self.question(int(cid), name)
            for depth in (1, 2, 3):
                q_text = base if depth == 2 or not base else f"{base} (단계 {depth})"
                questions.append(
                    {
                        "question": q_text,
                        "criterion_id": int(cid),
                        "kind": "experience",
                        "depth": depth,
                        "intent": "경험 확인",
                        "answer_tips": ["구체적으로"],
                        "cv_quote": self.cv_quote,
                    }
                )
        return schema.model_validate({"questions": questions})


# ── S3a: an Interview Agent for the tests ──


def new_session(db: Session, world: World, clock: Clock) -> int:
    """A created session (rules mode) for the world's seeker; its plan is the stored canonical one."""
    created = interview_service.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-26", clock=clock)
    return created.view.id


def turn_rows(db: Session, session_id: int) -> list[InterviewTurn]:
    db.expire_all()
    return list(db.query(InterviewTurn).filter_by(session_id=session_id).order_by(InterviewTurn.seq))


class Agent:
    """Plays the Interview Agent: a real InterviewEngine over the plan the backend stored, posting what it says and hears.

    Each method moves the backend clock and the engine's own clock by the same seconds, calls the engine, and posts the turns it
    added (with the coverage snapshot after the call) through `record_turn`; a closing line or an abort goes through `record_end`.
    `last` holds the results of the last call, and `events` every event posted so far."""

    def __init__(self, db: Session, session_id: int, clock: Clock, *, names=()):
        row = db.get(InterviewSession, session_id)
        self.plan = InterviewPlan.from_dict(row.plan)
        self.engine = InterviewEngine(self.plan, blocklists=interview_blocklists(), limits=InterviewLimits(**row.limits), names=list(names))
        self.db, self.session_id, self.clock = db, session_id, clock
        self.elapsed = 0.0
        self.sent = 0
        self.last: list = []
        self.events: list = []

    def topic_of(self, index):
        return self.plan.items[index].topic_id if index is not None and 0 <= index < len(self.plan.items) else None

    def turn_events(self):
        """The turns the engine added since the last call, as events; the closing line is not one (it goes with the end)."""
        state = self.engine.state
        # A turn event always says `listening` with no end reason, even when this call ended the interview: the end event carries the
        # final phase and reason. The agent has to do this, because the engine's snapshot after its last call already says `ended`.
        coverage = coverage_snapshot(state) | {"phase": "listening", "end_reason": None}
        out = []
        for turn in state.turns[self.sent :]:
            if turn.kind != "closing":
                out.append(ingest.TurnEvent(turn.seq, turn.role, turn.kind, turn.item_index, self.topic_of(turn.item_index), turn.text, turn.method, turn.analysis, turn.masked_kinds, coverage))
        return out

    def end_event(self):
        """The end event of the engine as it is now: its final snapshot and, if it wrapped up, the closing line (no topic, as the engine's action has none)."""
        state = self.engine.state
        closing = next((t for t in state.turns if t.kind == "closing"), None)
        line = None if closing is None else ingest.TurnEvent(closing.seq, "agent", "closing", closing.item_index, None, closing.text, closing.method, None, closing.masked_kinds, None)
        return ingest.EndEvent(coverage_snapshot(state), line)

    def post(self):
        results = [self._send(ingest.record_turn, event) for event in self.turn_events()]
        self.sent = len(self.engine.state.turns)
        if self.engine.state.phase.value in ("ended", "aborted"):
            results.append(self._send(ingest.record_end, self.end_event()))
        self.last = results
        return results

    def _send(self, call, event):
        self.events.append(event)
        return call(self.db, self.session_id, event, clock=self.clock)

    def _move(self, seconds):
        self.clock.advance(seconds)
        self.elapsed += seconds

    def start(self):
        self.engine.start()
        return self.post()

    def answer(self, text, seconds=20.0, analysis=None):
        self._move(seconds)
        self.engine.on_answer(text, self.elapsed, analysis)
        return self.post()

    def silence(self, silent_seconds, seconds=None):
        self._move(silent_seconds if seconds is None else seconds)
        self.engine.on_silence(silent_seconds, self.elapsed)
        return self.post()

    def abort(self, reason="candidate_left", seconds=5.0):
        self._move(seconds)
        self.engine.abort(reason, self.elapsed)
        return self.post()
