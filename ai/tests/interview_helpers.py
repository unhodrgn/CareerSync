"""Shared data for the practice-interview engine tests (ai/interview/, docs/DECISIONS.md D51–D54, D57): real blocklists, the
sample CV masked like an upload, a job with criteria of every importance, and answers that hit the rules' cue words."""
from pathlib import Path

from ai.career.interview import Question, cv_excerpts
from ai.guardrails.blocklist import load_blocklist
from ai.interview import InterviewEngine, InterviewLimits, PlanCriterion, build_plan, evidence_lines
from ai.interview.types import DEFAULT_LIMITS
from ai.parsing.pii import mask_pii
from ai.tests.helpers import EMBEDDER, SAMPLE_CV, SKILLS

DATA = Path(__file__).resolve().parents[2] / "data"
BLOCKLISTS = [load_blocklist(DATA / "blocklist.yaml"), load_blocklist(DATA / "interview_blocklist.yaml")]
ACCOUNT_NAME = "김지원"
MASKED_CV = mask_pii(SAMPLE_CV, [ACCOUNT_NAME]).text
CV_LINES = evidence_lines(cv_excerpts(MASKED_CV, "백엔드 개발자 Java Spring API", EMBEDDER))


def crit(cid: int, name: str, category: str, description: str, importance: str, position: int | None = None) -> PlanCriterion:
    return PlanCriterion(cid, name, category, description, importance, cid if position is None else position)  # type: ignore[arg-type]


# Two 핵심, one 중요, one 일반: with the default cap (5) the plan is warm-up, c1, c2, c4, behavioral and c3 has no slot
CRITERIA = [
    crit(1, "Java 활용 능력", "skill", "Java 17, Spring Boot 사용 경험", "핵심"),
    crit(2, "프로젝트 경험", "project", "REST API를 설계하고 문서화한 경험", "핵심"),
    crit(3, "협업 태도", "other", "코드 리뷰 문화", "일반"),
    crit(4, "관련 전공", "education", "", "중요"),
]


def make_plan(criteria=None, questions=(), cv_lines=None, limits: InterviewLimits = DEFAULT_LIMITS, bank_method: str = "rules", depth: int = 2):
    return build_plan(
        CRITERIA if criteria is None else criteria,
        questions,
        MASKED_CV,
        CV_LINES if cv_lines is None else cv_lines,
        BLOCKLISTS,
        limits,
        SKILLS,
        bank_method,
        depth,
    )


def make_engine(plan=None, limits: InterviewLimits = DEFAULT_LIMITS, names=(ACCOUNT_NAME,)) -> InterviewEngine:
    return InterviewEngine(make_plan() if plan is None else plan, blocklists=BLOCKLISTS, limits=limits, names=names)


def q(question: str, criterion_id: int | None = None, kind: str = "technical", cv_quote: str | None = None, depth: int | None = None) -> Question:
    """A question of a D21 bank."""
    return Question(question, criterion_id, None, kind, "확인", ("구체적으로",), cv_quote, depth)  # type: ignore[arg-type]


# Answers that demonstrate every rubric point of the item they are meant for (the rules look for cue words)
GOOD = {
    "warmup": "프로젝트에서 백엔드 개발 역할을 맡아 주문 API를 설계하고 구현했고, 그 결과 조회 속도가 개선되어 많이 배웠습니다.",
    "c1": "Java 17과 Spring Boot를 사용해서 주문 API를 개발했고 실무에서 계속 사용하고 있습니다.",
    "c2": "REST API를 설계하고 Swagger로 문서화했습니다. 프로젝트에서 팀 리더 역할을 맡아 설계와 개발을 진행했습니다.",
    "c3": "코드 리뷰 문화를 만들 때 팀 상황에서 제가 규칙을 제안했고 그 결과 배운 점이 많았습니다.",
    "c4": "컴퓨터공학 전공 수업에서 배운 자료구조와 학습한 내용을 프로젝트 과제에 적용하고 활용했습니다. 실습 경험도 있습니다.",
    "behavioral": "당시 팀 프로젝트 상황에서 제가 의견 조율을 진행했고 그 결과 개선되어 많이 배웠습니다.",
}
# A partial answer for the Java item: shows "Java" but nothing about Spring Boot
PARTIAL_JAVA = "Java를 공부했고 알고리즘 문제도 풀었습니다. 열심히 했습니다."
OFF_TOPIC = "오늘 점심은 뭐 먹을까요 날씨가 좋네요 정말 좋아요"


def play(engine: InterviewEngine, answers: list[str], *, start: float = 10.0, step: float = 30.0):
    """Start the interview and feed the answers; returns the actions in order (the first is the opening question)."""
    actions = [engine.start()]
    now = start
    for answer in answers:
        if actions[-1].done:
            break
        actions.append(engine.on_answer(answer, now))
        now += step
    return actions


def good_answers(plan) -> list[str]:
    return [GOOD[item.topic_id] for item in plan.items]
