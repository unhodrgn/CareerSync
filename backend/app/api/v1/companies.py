"""Company profile: name, intro, 인재상."""
from fastapi import APIRouter

from app.core.deps import CompanyUser, CurrentUser, DbSession
from app.core.errors import AppError
from app.models import Company
from app.schemas.company import CompanyOut, CompanyUpdate

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


@router.get("/{company_id}", response_model=CompanyOut, summary="Public company profile")
def get_company(company_id: int, db: DbSession, user: CurrentUser):
    company = db.get(Company, company_id)
    if company is None:
        raise AppError(404, "COMPANY_NOT_FOUND", "기업을 찾을 수 없습니다.")
    return company
