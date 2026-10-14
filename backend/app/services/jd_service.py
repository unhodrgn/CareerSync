"""JD help for companies: criteria suggestions from a JD (`/analyze`) and AI JD drafts (docs/DECISIONS.md D24).

- `/analyze` (issue 7): suggestions that saving would reject — a criteria guardrail hit, or an education
  criterion without a major (D13) — are left out and listed in `blocked`; the rest are rescaled to 100.
  Nothing is logged to `criteria_guardrail_logs`: these are AI suggestions, not company input.
- `/jd-draft`: only for the company's own draft job; nothing is saved. In AI_MODE=llm a company gets at most
  JD_DAILY_LLM_DRAFTS LLM drafts per day (KST); over that the template comes back with `limited: true`.
  The count lives in process memory, so it resets on restart and assumes one backend process (D24).
"""
import threading
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.jd.draft import DraftInput, ProjectInfo, make_draft
from ai.parsing.extract import analyze_jd, fix_weights
from ai.parsing.profile import SuggestedCriterion
from ai.scoring.scorers import education_target
from app.core.config import settings
from app.core.errors import AppError
from app.models import Company, CompanyProject, User
from app.models.job import JobStatus
from app.schemas.cv import BlockedSuggestion, DroppedSentence, JdAnalysisOut, JdDraftIn, JdDraftOut, JdDraftSections
from app.services import ai_runtime, criteria_service, job_service

KST = timezone(timedelta(hours=9))
MAJOR_REQUIRED_REASON = "학력(전공) 항목에는 평가할 전공을 하나 이상 적어야 합니다."

# ── /analyze ──


def screen_suggestions(items: list[SuggestedCriterion]) -> tuple[list[SuggestedCriterion], list[BlockedSuggestion]]:
    kept, blocked = [], []
    for item in items:
        result = criteria_service.check(item.name, item.description)
        if not result.allowed:
            hit = result.hits[0]
            blocked.append(BlockedSuggestion(name=item.name, code="CRITERIA_BLOCKED", reason=f"{hit.reason} ({hit.law_ref})"))
        elif item.category == "education" and education_target(item.name, item.description) == ([], False):
            blocked.append(BlockedSuggestion(name=item.name, code="CRITERIA_MAJOR_REQUIRED", reason=MAJOR_REQUIRED_REASON))
        else:
            kept.append(item)
    return (fix_weights(kept) if blocked else kept), blocked


def analyze(db: Session, user: User, job_id: int) -> JdAnalysisOut:
    job = job_service.get_owned_job(db, job_id, user)
    analysis, method = analyze_jd(job.title, job.description, job.min_experience_years, ai_runtime.skills(), ai_runtime.llm())
    analysis.criteria, blocked = screen_suggestions(analysis.criteria)
    return JdAnalysisOut(job_id=job.id, analysis=analysis, blocked=blocked, method=method)


# ── /jd-draft ──

_lock = threading.Lock()
_drafts: dict[tuple[int, date], int] = {}


def take_llm_slot(company_id: int) -> bool:
    """Count one LLM draft for today (KST); False when the daily limit is reached."""
    today = datetime.now(KST).date()
    with _lock:
        for key in [k for k in _drafts if k[1] != today]:
            del _drafts[key]
        used = _drafts.get((company_id, today), 0)
        if used >= settings.JD_DAILY_LLM_DRAFTS:
            return False
        _drafts[(company_id, today)] = used + 1
        return True


def reset_counts() -> None:
    with _lock:
        _drafts.clear()


def _projects(db: Session, company_id: int, ids: list[int]) -> list[CompanyProject]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    found = {
        p.id: p
        for p in db.scalars(select(CompanyProject).where(CompanyProject.id.in_(ids), CompanyProject.company_id == company_id))
    }
    if len(found) != len(ids):
        raise AppError(404, "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.")
    return [found[i] for i in ids]


def draft(db: Session, user: User, job_id: int, body: JdDraftIn) -> JdDraftOut:
    job = job_service.get_owned_job(db, job_id, user)
    if job.status != JobStatus.DRAFT:
        raise AppError(409, "JOB_NOT_DRAFT", "작성 중인 공고에서만 AI 초안을 만들 수 있습니다.")
    projects = _projects(db, job.company_id, body.project_ids)
    company = db.get(Company, job.company_id)
    inp = DraftInput(
        title=job.title,
        employment_type=job.employment_type,
        min_experience_years=job.min_experience_years,
        keywords=tuple(body.keywords),
        notes=body.notes.strip(),
        company_name=company.name,
        company_intro=company.intro,
        talent_profile=company.talent_profile,
        projects=tuple(ProjectInfo(p.name, p.description, tuple(t.tech_name for t in p.techs)) for p in projects),
    )
    llm, limited = ai_runtime.llm(), False
    if llm is not None and not take_llm_slot(job.company_id):
        llm, limited = None, True
    result, method = make_draft(inp, ai_runtime.skills(), criteria_service.blocklist(), llm)
    return JdDraftOut(
        job_id=job.id,
        description=result.description,
        sections=JdDraftSections(
            intro=result.intro,
            responsibilities=result.responsibilities,
            requirements=result.requirements,
            preferred=result.preferred,
        ),
        dropped=[DroppedSentence(text=d.text, reason=d.reason) for d in result.dropped],
        method=method,
        limited=limited,
    )
