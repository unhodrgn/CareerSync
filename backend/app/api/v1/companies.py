"""Company profile (name, intro, 인재상) and running projects (D23)."""
from fastapi import APIRouter, status

from app.core.deps import CompanyUser, CurrentUser, DbSession
from app.core.errors import AppError
from app.models import Company
from app.schemas.company import CompanyOut, CompanyProjectIn, CompanyProjectOut, CompanyPublicOut, CompanyUpdate
from app.services import company_project_service as projects

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/me", response_model=CompanyOut, summary="Own company profile")
def get_my_company(db: DbSession, user: CompanyUser):
    return db.get(Company, user.company_id)


@router.put("/me", response_model=CompanyOut, summary="Edit own company profile")
def update_my_company(body: CompanyUpdate, db: DbSession, user: CompanyUser):
    company = db.get(Company, user.company_id)
    company.name = body.name.strip()
    company.intro = body.intro
    company.talent_profile = body.talent_profile
    db.commit()
    db.refresh(company)
    return company


@router.get("/me/projects", response_model=list[CompanyProjectOut], summary="Own running projects")
def list_my_projects(db: DbSession, user: CompanyUser):
    return [projects.to_out(p) for p in projects.list_for_company(db, user.company_id)]


@router.post(
    "/me/projects",
    response_model=CompanyProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a running project (not used in scoring)",
)
def create_project(body: CompanyProjectIn, db: DbSession, user: CompanyUser):
    return projects.to_out(projects.create(db, user, body))


@router.put("/me/projects/{project_id}", response_model=CompanyProjectOut, summary="Replace a running project")
def update_project(project_id: int, body: CompanyProjectIn, db: DbSession, user: CompanyUser):
    return projects.to_out(projects.update(db, user, project_id, body))


@router.delete("/me/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a running project")
def delete_project(project_id: int, db: DbSession, user: CompanyUser):
    projects.delete(db, user, project_id)


@router.get("/{company_id}", response_model=CompanyPublicOut, summary="Public company profile with its running projects")
def get_company(company_id: int, db: DbSession, user: CurrentUser):
    company = db.get(Company, company_id)
    if company is None:
        raise AppError(404, "COMPANY_NOT_FOUND", "기업을 찾을 수 없습니다.")
    return CompanyPublicOut(
        id=company.id,
        name=company.name,
        intro=company.intro,
        talent_profile=company.talent_profile,
        projects=[projects.to_out(p) for p in projects.list_for_company(db, company.id)],
    )
