"""Talent recommendation and offers. Companies see anonymous opted-in seekers; contact only after acceptance."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.core.deps import CompanyUser, CurrentUser, DbSession
from app.schemas.offer import OfferCreate, SeekerOffer, SentOffer
from app.schemas.talent import TalentList
from app.services import evaluation_service, offer_service, talent_service

router = APIRouter(tags=["talent"])


@router.get(
    "/jobs/{job_id}/talent",
    response_model=TalentList,
    summary="Anonymous opted-in seekers ranked by Fit for one of the company's published jobs",
)
def talent_for_job(
    job_id: int,
    background: BackgroundTasks,
    db: DbSession,
    user: CompanyUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    reco = talent_service.recommend(db, user, job_id, limit)
    for evaluation_id, token in reco.queued:
        evaluation_service.queue(background, db, evaluation_id, token)
    return reco.result


# ── Offers: company ──


@router.post("/talent-offers", response_model=SentOffer, status_code=status.HTTP_201_CREATED, summary="Send an offer to an anonymous seeker")
def create_offer(body: OfferCreate, db: DbSession, user: CompanyUser):
    return offer_service.to_sent_out(db, offer_service.create(db, user, body))


@router.get("/talent-offers/sent", response_model=list[SentOffer], summary="Offers the company sent (contact only after accepted)")
def sent_offers(db: DbSession, user: CompanyUser, job_id: int | None = None):
    return [offer_service.to_sent_out(db, o) for o in offer_service.sent(db, user, job_id)]


@router.post("/talent-offers/{offer_id}/cancel", response_model=SentOffer, summary="Cancel a pending offer")
def cancel_offer(offer_id: int, db: DbSession, user: CompanyUser):
    return offer_service.to_sent_out(db, offer_service.cancel(db, user, offer_id))


# ── Offers: seeker ──


@router.get("/talent-offers/mine", response_model=list[SeekerOffer], summary="Offers the seeker received")
def my_offers(db: DbSession, user: CurrentUser):
    return [offer_service.to_seeker_out(db, o) for o in offer_service.mine(db, user)]


@router.post("/talent-offers/{offer_id}/accept", response_model=SeekerOffer, summary="Accept: the company gets your name and email")
def accept_offer(offer_id: int, db: DbSession, user: CurrentUser):
    return offer_service.to_seeker_out(db, offer_service.respond(db, user, offer_id, accept=True))


@router.post("/talent-offers/{offer_id}/reject", response_model=SeekerOffer, summary="Reject an offer")
def reject_offer(offer_id: int, db: DbSession, user: CurrentUser):
    return offer_service.to_seeker_out(db, offer_service.respond(db, user, offer_id, accept=False))
