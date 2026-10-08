from datetime import UTC, datetime

from app.models import (
    CompanyProject,
    CompanyProjectTech,
    SeekerJobKeyword,
    SeekerPreference,
    SeekerPreferredEmploymentType,
    SeekerPreferredLocation,
    TalentOffer,
    User,
)


def test_seeker_preferences_store_recommendation_inputs(db, world):
    seeker = db.query(User).filter_by(email="me@seeker.test").one()
    preference = SeekerPreference(
        seeker_id=seeker.id,
        profile_public=True,
        profile_public_at=datetime.now(UTC),
        locations=[
            SeekerPreferredLocation(location="서울"),
            SeekerPreferredLocation(location="경기"),
        ],
        employment_types=[SeekerPreferredEmploymentType(employment_type="full_time")],
        job_keywords=[
            SeekerJobKeyword(keyword="백엔드"),
            SeekerJobKeyword(keyword="Java"),
        ],
    )
    db.add(preference)
    db.commit()
    db.refresh(preference)

    assert preference.profile_public is True
    assert [x.location for x in preference.locations] == ["서울", "경기"]
    assert [x.employment_type for x in preference.employment_types] == ["full_time"]
    assert [x.keyword for x in preference.job_keywords] == ["백엔드", "Java"]


def test_talent_offer_and_company_project_models(db, world):
    seeker = db.query(User).filter_by(email="me@seeker.test").one()

    project = CompanyProject(
        company_id=world["acme"].id,
        name="AI 채용 매칭",
        description="이력서와 공고의 적합도를 계산하는 프로젝트",
        techs=[CompanyProjectTech(tech_name="Python"), CompanyProjectTech(tech_name="FastAPI")],
    )
    offer = TalentOffer(
        company_id=world["acme"].id,
        seeker_id=seeker.id,
        job_id=world["job"].id,
    )
    db.add_all([project, offer])
    db.commit()
    db.refresh(project)
    db.refresh(offer)

    assert [x.tech_name for x in project.techs] == ["Python", "FastAPI"]
    assert offer.status == "pending"
