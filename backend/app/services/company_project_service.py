"""Company running projects (docs/DECISIONS.md D8, D23).

CRUD and display only: projects are shown on the public company profile and can be picked as
context for an AI JD draft. They are never used in scoring and are not linked to jobs.
Technologies are normalized with the skills dictionary (canonical names where known, duplicates
merged ignoring case). Creation locks the `companies` row so parallel requests cannot pass the limit.
"""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Company, CompanyProject, CompanyProjectTech, User
from app.schemas.company import CompanyProjectIn, CompanyProjectOut
from app.services import ai_runtime

MAX_PROJECTS = 20


def to_out(p: CompanyProject) -> CompanyProjectOut:
    return CompanyProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        techs=[t.tech_name for t in p.techs],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def list_for_company(db: Session, company_id: int) -> list[CompanyProject]:
    return list(db.scalars(select(CompanyProject).where(CompanyProject.company_id == company_id).order_by(CompanyProject.id)))


def get_owned(db: Session, user: User, project_id: int) -> CompanyProject:
    p = db.get(CompanyProject, project_id)
    if p is None or p.company_id != user.company_id:
        raise AppError(404, "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.")
    return p


def _techs(names: list[str]) -> list[CompanyProjectTech]:
    return [CompanyProjectTech(tech_name=t) for t in ai_runtime.skills().normalize_list(names)]


def create(db: Session, user: User, body: CompanyProjectIn) -> CompanyProject:
    db.execute(select(Company.id).where(Company.id == user.company_id).with_for_update())
    count = db.scalar(select(func.count()).select_from(CompanyProject).where(CompanyProject.company_id == user.company_id))
    if count >= MAX_PROJECTS:
        db.rollback()
        raise AppError(409, "PROJECT_LIMIT", f"프로젝트는 최대 {MAX_PROJECTS}개까지 등록할 수 있습니다.")
    p = CompanyProject(company_id=user.company_id, name=body.name, description=body.description, techs=_techs(body.techs))
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update(db: Session, user: User, project_id: int, body: CompanyProjectIn) -> CompanyProject:
    p = get_owned(db, user, project_id)
    p.name = body.name
    p.description = body.description
    # Delete the old rows first: re-adding the same name in one flush would hit the unique constraint
    p.techs.clear()
    db.flush()
    p.techs.extend(_techs(body.techs))
    p.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(p)
    return p


def delete(db: Session, user: User, project_id: int) -> None:
    db.delete(get_owned(db, user, project_id))
    db.commit()
