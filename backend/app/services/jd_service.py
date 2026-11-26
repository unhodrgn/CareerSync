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
from app.schemas.cv import BlockedSuggestion, DroppedSentence, CriteriaPreviewIn, CriteriaPreviewOut, JdAnalysisOut, JdDraftIn, JdDraftOut, JdDraftSections
from app.services import ai_runtime, criteria_service, job_service

KST = timezone(timedelta(hours=9))
MAJOR_REQUIRED_REASON = "An education (major) criterion must name at least one major."

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

def preview(body: CriteriaPreviewIn, company_id: int | None = None) -> CriteriaPreviewOut:
    """Analyze unsaved source material; internal specifications are never published or stored."""
    llm, limited = ai_runtime.llm(), False
    if llm is not None and company_id is not None and not take_preview_llm_slot(company_id):
        llm, limited = None, True
    label = "내부 프로젝트 기술서" if body.source_type == "project_spec" else "채용공고 원문"
    analysis, method = analyze_jd(
        body.title, f"{label}\n{body.text}", body.min_experience_years,
        ai_runtime.skills(), llm,
    )
    analysis.criteria, blocked = screen_suggestions(analysis.criteria)
    return CriteriaPreviewOut(analysis=analysis, blocked=blocked, method=method, limited=limited)


# ── /jd-draft & /criteria-preview limits ──

_lock = threading.Lock()
_drafts: dict[tuple[int, date], int] = {}
_previews: dict[tuple[int, date], int] = {}


def _take_slot(buckets: dict[tuple[int, date], int], company_id: int, limit: int) -> bool:
    today = datetime.now(KST).date()
    with _lock:
        for key in [k for k in buckets if k[1] != today]:
            del buckets[key]
        used = buckets.get((company_id, today), 0)
        if used >= limit:
            return False
        buckets[(company_id, today)] = used + 1
        return True


def take_llm_slot(company_id: int) -> bool:
    """Count one LLM draft for today (KST); False when the daily limit is reached."""
    return _take_slot(_drafts, company_id, settings.JD_DAILY_LLM_DRAFTS)


def take_preview_llm_slot(company_id: int) -> bool:
    """Count one LLM criteria preview for today (KST); False when the daily limit is reached."""
    return _take_slot(_previews, company_id, settings.COMPANY_DAILY_LLM_PREVIEWS)


def reset_counts() -> None:
    with _lock:
        _drafts.clear()
        _previews.clear()


def _projects(db: Session, company_id: int, ids: list[int]) -> list[CompanyProject]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    found = {
        p.id: p
        for p in db.scalars(select(CompanyProject).where(CompanyProject.id.in_(ids), CompanyProject.company_id == company_id))
    }
    if len(found) != len(ids):
        raise AppError(404, "PROJECT_NOT_FOUND", "Project not found.")
    return [found[i] for i in ids]


def draft(db: Session, user: User, job_id: int, body: JdDraftIn) -> JdDraftOut:
    job = job_service.get_owned_job(db, job_id, user)
    if job.status != JobStatus.DRAFT:
        raise AppError(409, "JOB_NOT_DRAFT", "An AI draft can only be created for a draft job.")
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
