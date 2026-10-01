"""Company evaluation criteria: validation, guardrail, lifecycle rules and the read path for scoring.

Rules (see README "Scoring Rules"):
- 1 to CRITERIA_MAX_ITEMS items per job, names unique (case-insensitive), integer weights summing to 100.
- Every save passes the criteria guardrail (ai/guardrails); blocked attempts are logged.
- Draft job: the set is replaced freely. Published or closed job: only weights and order may change.
- Scoring and recommendation read criteria through `load_for_scoring` only.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ai.guardrails.blocklist import Blocklist, load_blocklist
from ai.guardrails.criteria import GuardrailHit, GuardrailResult, check_criterion
from app.core.config import settings
from app.models import CriteriaGuardrailLog, JobCriterion, JobPosting, User
from app.models.job import JobStatus
from app.schemas.criteria import CriterionIn


class CriteriaError(Exception):
    """Business-rule error rendered as {"code", "message", **extra} by the handler in main.py."""

    def __init__(self, status_code: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra


def blocklist() -> Blocklist:
    return load_blocklist(settings.BLOCKLIST_PATH)


def check(name: str, description: str) -> GuardrailResult:
    return check_criterion(name, description, blocklist())


def importance_level(weight: int) -> str:
    if weight >= settings.IMPORTANCE_HIGH:
        return "높음"
    if weight >= settings.IMPORTANCE_MID:
        return "보통"
    return "낮음"


def hit_dict(hit: GuardrailHit, index: int | None = None) -> dict:
    return {
        "index": index,
        "field": hit.field,
        "rule_id": hit.rule_id,
        "category": hit.category,
        "matched": hit.matched,
        "reason": hit.reason,
        "law_ref": hit.law_ref,
    }


# ── Access ──


def get_owned_job(db: Session, job_id: int, user: User) -> JobPosting:
    """The job if it belongs to the user's company. 404 otherwise, so other companies' job ids are not probeable."""
    job = db.get(JobPosting, job_id)
    if job is None or user.role != "company" or job.company_id != user.company_id:
        raise CriteriaError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")
    return job


def get_published_job(db: Session, job_id: int) -> JobPosting:
    job = db.get(JobPosting, job_id)
    if job is None or job.status != JobStatus.PUBLISHED:
        raise CriteriaError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")
    return job


# ── Validation ──


def _validate_shape(items: list[CriterionIn]) -> None:
    if not 1 <= len(items) <= settings.CRITERIA_MAX_ITEMS:
        raise CriteriaError(
            422,
            "CRITERIA_COUNT_INVALID",
            f"평가 항목은 1개 이상 {settings.CRITERIA_MAX_ITEMS}개 이하로 설정해야 합니다.",
            count=len(items),
        )
    counts = Counter(item.name.strip().lower() for item in items)
    if duplicates := sorted(name for name, n in counts.items() if n > 1):
        raise CriteriaError(422, "CRITERIA_DUPLICATE_NAME", "평가 항목 이름이 중복되었습니다.", names=duplicates)
    total = sum(item.weight for item in items)
    if total != settings.CRITERIA_WEIGHT_TOTAL:
        raise CriteriaError(
            422,
            "WEIGHT_SUM_INVALID",
            f"가중치 합계는 {settings.CRITERIA_WEIGHT_TOTAL}이어야 합니다. (현재 {total})",
            total=total,
        )


def _enforce_guardrail(db: Session, job: JobPosting, items: list[CriterionIn]) -> str:
    """Reject the whole set if any item is blocked, logging each hit. Returns the blocklist version."""
    bl = blocklist()
    blocked = []
    for index, item in enumerate(items):
        for hit in check_criterion(item.name, item.description, bl).hits:
            blocked.append(hit_dict(hit, index))
            db.add(
                CriteriaGuardrailLog(
                    company_id=job.company_id,
                    job_id=job.id,
                    input_name=item.name,
                    input_description=item.description,
                    rule_id=hit.rule_id,
                    category=hit.category,
                    law_ref=hit.law_ref,
                    blocklist_version=bl.version,
                )
            )
    if blocked:
        db.commit()  # keep the audit log even though the save is rejected
        raise CriteriaError(422, "CRITERIA_BLOCKED", "사용할 수 없는 평가 기준이 포함되어 있습니다.", items=blocked)
    return bl.version


def _enforce_lock(job: JobPosting, items: list[CriterionIn]) -> None:
    """After publish, the same criteria (ids, names, rubrics, categories) must come back; only weights and order change."""
    existing = {c.id: c for c in job.criteria}
    incoming_ids = [item.id for item in items]
    if sorted(i for i in incoming_ids if i is not None) != sorted(existing) or None in incoming_ids:
        raise CriteriaError(409, "CRITERIA_LOCKED", "게시된 공고는 평가 항목을 추가하거나 삭제할 수 없습니다. 가중치만 변경할 수 있습니다.")
    for item in items:
        current = existing[item.id]
        if (item.name, item.description, item.category) != (current.name, current.description, current.category):
            raise CriteriaError(409, "CRITERIA_LOCKED", "게시된 공고는 평가 항목 내용을 수정할 수 없습니다. 가중치만 변경할 수 있습니다.")


# ── Writes ──


def replace_set(db: Session, job: JobPosting, items: list[CriterionIn]) -> JobPosting:
    _validate_shape(items)
    version = _enforce_guardrail(db, job, items)

    if job.status == JobStatus.DRAFT:
        # No scores exist before publish, so a draft set is simply rebuilt; ids are stable from publish on.
        job.criteria.clear()
        db.flush()
        for position, item in enumerate(items):
            job.criteria.append(
                JobCriterion(
                    name=item.name,
                    description=item.description,
                    category=item.category,
                    weight=item.weight,
                    position=position,
                    guardrail_version=version,
                )
            )
    else:
        _enforce_lock(job, items)
        by_id = {c.id: c for c in job.criteria}
        for position, item in enumerate(items):
            criterion = by_id[item.id]
            criterion.weight = item.weight
            criterion.position = position
            criterion.guardrail_version = version

    job.criteria_updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job


def copy_set(db: Session, target: JobPosting, source: JobPosting) -> JobPosting:
    if target.status != JobStatus.DRAFT:
        raise CriteriaError(409, "CRITERIA_LOCKED", "게시된 공고에는 평가 기준을 복사할 수 없습니다.")
    items = [
        CriterionIn(name=c.name, description=c.description, category=c.category, weight=c.weight)
        for c in source.criteria
    ]
    return replace_set(db, target, items)


# ── Reads ──


def assert_publishable(job: JobPosting) -> None:
    """A job can be published only with a complete set that passes the current blocklist."""
    items = [
        CriterionIn(id=c.id, name=c.name, description=c.description, category=c.category, weight=c.weight)
        for c in job.criteria
    ]
    _validate_shape(items)
    blocked = [hit_dict(hit, i) for i, item in enumerate(items) for hit in check(item.name, item.description).hits]
    if blocked:
        raise CriteriaError(422, "CRITERIA_BLOCKED", "사용할 수 없는 평가 기준이 포함되어 있습니다.", items=blocked)


@dataclass(frozen=True)
class ScoringCriterion:
    id: int
    name: str
    description: str
    category: str
    weight: int
    # Weight renormalized over usable criteria so they still sum to 100
    effective_weight: float


@dataclass(frozen=True)
class ExcludedCriterion:
    id: int
    name: str
    hits: tuple[GuardrailHit, ...]


@dataclass(frozen=True)
class ScoringCriteria:
    job_id: int
    items: tuple[ScoringCriterion, ...]
    # Criteria a newer blocklist now blocks: skipped in scoring, shown to the company as a warning
    excluded: tuple[ExcludedCriterion, ...]
    blocklist_version: str
    criteria_updated_at: datetime | None


def load_for_scoring(db: Session, job_id: int) -> ScoringCriteria:
    """The only read path for scoring and recommendation.

    Per-criterion scores are keyed by ScoringCriterion.id; weighted totals are
    sum(effective_weight * score) / 100, computed with the weights returned here at read time.
    """
    job = db.get(JobPosting, job_id)
    if job is None:
        raise CriteriaError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")
    bl = blocklist()
    usable, excluded = [], []
    for c in job.criteria:
        result = check_criterion(c.name, c.description, bl)
        if result.allowed:
            usable.append(c)
        else:
            excluded.append(ExcludedCriterion(id=c.id, name=c.name, hits=result.hits))
    total = sum(c.weight for c in usable)
    items = tuple(
        ScoringCriterion(
            id=c.id,
            name=c.name,
            description=c.description,
            category=c.category,
            weight=c.weight,
            effective_weight=c.weight * settings.CRITERIA_WEIGHT_TOTAL / total,
        )
        for c in usable
    )
    return ScoringCriteria(
        job_id=job.id,
        items=items,
        excluded=tuple(excluded),
        blocklist_version=bl.version,
        criteria_updated_at=job.criteria_updated_at,
    )
