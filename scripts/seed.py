"""Seed demo data: two companies with recruiters, one seeker, jobs with criteria.

Run after migrations:  cd backend && alembic upgrade head && python ../scripts/seed.py
Safe to run again: accounts that already exist are skipped. All accounts use the password printed below.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from sqlalchemy import func, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import Company, User  # noqa: E402
from app.schemas.auth import RegisterIn  # noqa: E402
from app.schemas.company import CompanyUpdate  # noqa: E402
from app.schemas.criteria import CriterionIn  # noqa: E402
from app.schemas.job import JobCreate  # noqa: E402
from app.services import auth_service, criteria_service, job_service  # noqa: E402

PASSWORD = "demo1234"

COMPANIES = [
    {
        "email": "hr@nextcode.test",
        "display_name": "넥스트코드 인사팀",
        "profile": CompanyUpdate(
            name="넥스트코드",
            intro="중소기업용 ERP SaaS를 만드는 B2B 스타트업입니다.",
            talent_profile="문제를 스스로 정의하고, 코드 리뷰로 함께 성장하는 개발자",
        ),
        "jobs": [
            (
                JobCreate(
                    title="백엔드 개발자 (Java/Spring)",
                    description="Spring Boot 기반 ERP API 개발 및 운영. PostgreSQL 쿼리 최적화, 배치 작업 설계.",
                    min_experience_years=2,
                    location="서울 강남구",
                    salary_note="회사 내규에 따름",
                ),
                [
                    CriterionIn(name="Java 활용 능력", category="skill", weight=30, description="Java 17, 컬렉션·동시성 이해"),
                    CriterionIn(name="Spring 경험", category="skill", weight=25, description="Spring Boot, JPA 실무 경험"),
                    CriterionIn(name="DB 경험", category="skill", weight=20, description="PostgreSQL 쿼리 튜닝, 인덱스 설계"),
                    CriterionIn(name="프로젝트 경험", category="project", weight=15, description="API 서버를 직접 설계·배포한 경험"),
                    CriterionIn(name="관련 자격증", category="certificate", weight=10, description="정보처리기사 등"),
                ],
                True,
            ),
            (
                JobCreate(
                    title="프론트엔드 개발자 (React)",
                    description="React/TypeScript로 ERP 관리 화면 개발.",
                    employment_type="contract",
                    location="서울 강남구",
                ),
                [
                    CriterionIn(name="React 경험", category="skill", weight=50),
                    CriterionIn(name="TypeScript", category="skill", weight=30),
                    CriterionIn(name="UI 프로젝트 경험", category="project", weight=20),
                ],
                False,  # left as a draft
            ),
        ],
    },
    {
        "email": "hr@cloudlab.test",
        "display_name": "클라우드랩 채용담당",
        "profile": CompanyUpdate(
            name="클라우드랩",
            intro="데이터 파이프라인과 AI 에이전트 솔루션을 만듭니다.",
            talent_profile="데이터로 판단하고 새로운 기술을 빠르게 익히는 사람",
        ),
        "jobs": [
            (
                JobCreate(
                    title="데이터 엔지니어",
                    description="Airflow·Spark 기반 데이터 파이프라인 구축, AWS 운영.",
                    min_experience_years=None,
                    location="경기 성남시 판교",
                    salary_note="협의",
                ),
                [
                    CriterionIn(name="Python 활용 능력", category="skill", weight=30),
                    CriterionIn(name="데이터 파이프라인 경험", category="experience", weight=30),
                    CriterionIn(name="AWS 클라우드 운영 경험", category="skill", weight=20),
                    CriterionIn(name="컴퓨터공학 관련 전공", category="education", weight=20),
                ],
                True,
            ),
        ],
    },
]

SEEKER = {"email": "seeker@demo.test", "display_name": "데모 구직자"}


def _exists(db, email: str) -> bool:
    return db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None


def _register(db, email: str, display_name: str, role: str, company_name: str | None = None) -> User:
    return auth_service.register(
        db,
        RegisterIn(
            email=email,
            password=PASSWORD,
            role=role,
            display_name=display_name,
            company_name=company_name,
            consent_privacy=True,
            consent_ai=True,
        ),
    )


def main() -> None:
    db = SessionLocal()
    try:
        for spec in COMPANIES:
            if _exists(db, spec["email"]):
                print(f"skip  {spec['email']} (exists)")
                continue
            user = _register(db, spec["email"], spec["display_name"], "company", spec["profile"].name)
            company = db.get(Company, user.company_id)
            company.intro = spec["profile"].intro
            company.talent_profile = spec["profile"].talent_profile
            db.commit()
            for job_in, criteria, publish in spec["jobs"]:
                job = job_service.create(db, user, job_in)
                criteria_service.replace_set(db, job, criteria)
                if publish:
                    job_service.publish(db, job)
                print(f"job   {company.name} · {job.title} ({job.status})")
            print(f"added {spec['email']}")
        if _exists(db, SEEKER["email"]):
            print(f"skip  {SEEKER['email']} (exists)")
        else:
            _register(db, SEEKER["email"], SEEKER["display_name"], "seeker")
            print(f"added {SEEKER['email']}")
        print(f"\nAll demo accounts use the password: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
