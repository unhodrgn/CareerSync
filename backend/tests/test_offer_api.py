"""Talent offers (D20): create, duplicates, re-offer, daily limit, expiry, answers, contact only after acceptance, Q10."""
import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.models import TalentOffer, User
from app.schemas.offer import OfferCreate
from app.services import offer_service, talent_service

from .conftest import auth
from .test_applications_api import job  # noqa: F401  (fixture)
from .test_jobs_api import make_published
from .test_recommendations_api import _done
from .test_talent_api import _anon, _public_seeker, _talent, queued  # noqa: F401  (queued is a fixture)

OFFERS = "/api/talent-offers"


def _eligible(client, db, job_id, email="kim@seeker.test", fit=80, name="김지원"):
    user, h, cv = _public_seeker(client, db, email, name=name)
    _done(db, job_id, cv, fit)
    return user, h


def _offer(client, world, job_id, user, **body):
    return client.post(OFFERS, json={"job_id": job_id, "anonymous_id": _anon(world, user), **body}, headers=world["recruiter"])


def _age(db, offer_id, days):
    db.get(TalentOffer, offer_id).created_at = datetime.now(UTC) - timedelta(days=days)
    db.commit()


# ── Create ──


def test_create_and_both_views(client, db, world, job, queued):
    user, h = _eligible(client, db, job)
    r = _offer(client, world, job, user, message="  백엔드 리드 포지션에 관심 있으신가요?  ")
    assert r.status_code == 201, r.json()
    sent = r.json()
    assert (sent["status"], sent["anonymous_id"], sent["message"]) == ("pending", _anon(world, user), "백엔드 리드 포지션에 관심 있으신가요?")
    assert sent["contact"] is None and sent["candidate"]["skills"]
    created = datetime.fromisoformat(sent["created_at"].replace("Z", "+00:00"))
    assert datetime.fromisoformat(sent["expires_at"].replace("Z", "+00:00")) - created == timedelta(days=14)

    mine = client.get(f"{OFFERS}/mine", headers=h).json()
    assert [(o["offer_id"], o["status"], o["company_name"], o["job"]["job_id"]) for o in mine] == [(sent["offer_id"], "pending", "Acme", job)]
    # A live offer takes the seeker off the talent list
    assert _talent(client, world, job).json()["items"] == []
    assert client.get(f"{OFFERS}/sent", headers=world["recruiter"]).json()[0]["offer_id"] == sent["offer_id"]
    assert client.get(f"{OFFERS}/sent?job_id={world['job2'].id}", headers=world["recruiter"]).json() == []


def test_message_validation(client, db, world, job, queued):
    user, _ = _eligible(client, db, job)
    assert _offer(client, world, job, user, message="x" * 1001).status_code == 422
    assert _offer(client, world, job, user, message="   ").json()["message"] is None


def test_only_seekers_the_talent_list_would_show(client, db, world, job, queued):
    low, _ = _eligible(client, db, job, "low@seeker.test", fit=30)
    hidden, hidden_h = _eligible(client, db, job, "hidden@seeker.test")
    client.put("/api/preferences/me", json={"profile_public": False}, headers=hidden_h)
    applied, applied_h = _eligible(client, db, job, "applied@seeker.test")
    assert client.post(f"/api/jobs/{job}/applications", headers=applied_h).status_code == 201
    for user in (low, hidden, applied):
        r = _offer(client, world, job, user)
        assert (r.status_code, r.json()["code"]) == (404, "TALENT_NOT_FOUND"), user.email
    r = client.post(OFFERS, json={"job_id": job, "anonymous_id": "C-0000000000"}, headers=world["recruiter"])
    assert r.json()["code"] == "TALENT_NOT_FOUND"
    r = client.post(OFFERS, json={"job_id": world["rival_job"].id, "anonymous_id": "C-0000000000"}, headers=world["recruiter"])
    assert r.json()["code"] == "JOB_NOT_FOUND"


# ── Duplicates and re-offers ──


def test_one_live_offer_per_company_and_seeker(client, db, world, job, queued):
    other = make_published(client, world["recruiter"], title="다른 공고")["id"]
    user, h = _eligible(client, db, job)
    _done(db, other, client.get("/api/cv/me", headers=h).json()["id"], 80)
    first = _offer(client, world, job, user).json()
    for job_id in (job, other):  # pending blocks every job of the company
        r = _offer(client, world, job_id, user)
        assert (r.status_code, r.json()["code"], r.json()["offer_id"]) == (409, "OFFER_EXISTS", first["offer_id"])
    client.post(f"{OFFERS}/{first['offer_id']}/accept", headers=h)
    assert _offer(client, world, other, user).json()["code"] == "OFFER_EXISTS"  # accepted blocks too


def test_reoffer_rules(client, db, world, job, queued):
    other = make_published(client, world["recruiter"], title="다른 공고")["id"]
    user, h = _eligible(client, db, job)
    _done(db, other, client.get("/api/cv/me", headers=h).json()["id"], 80)

    rejected = _offer(client, world, job, user).json()
    client.post(f"{OFFERS}/{rejected['offer_id']}/reject", headers=h)
    assert _offer(client, world, job, user).json()["code"] == "OFFER_REJECTED"  # not the same job again
    cancelled = _offer(client, world, other, user)  # another job is fine
    assert cancelled.status_code == 201
    client.post(f"{OFFERS}/{cancelled.json()['offer_id']}/cancel", headers=world["recruiter"])
    expired = _offer(client, world, other, user)  # after a cancellation, the same job is fine
    assert expired.status_code == 201
    _age(db, expired.json()["offer_id"], 15)
    again = _offer(client, world, other, user)  # an expired offer no longer blocks
    assert again.status_code == 201
    statuses = {o["offer_id"]: o["status"] for o in client.get(f"{OFFERS}/mine", headers=h).json()}
    assert statuses[expired.json()["offer_id"]] == "expired" and statuses[again.json()["offer_id"]] == "pending"


def test_daily_limit(client, db, world, job, queued, monkeypatch):
    monkeypatch.setattr(settings, "OFFER_DAILY_LIMIT", 2)
    users = [_eligible(client, db, job, f"s{i}@seeker.test")[0] for i in range(3)]
    first = _offer(client, world, job, users[0]).json()
    assert _offer(client, world, job, users[1]).status_code == 201
    r = _offer(client, world, job, users[2])
    assert (r.status_code, r.json()["code"]) == (429, "OFFER_DAILY_LIMIT")
    _age(db, first["offer_id"], 1)  # sent yesterday: no longer counted
    assert _offer(client, world, job, users[2]).status_code == 201


# ── Answers ──


def test_accept_reveals_contact_only_then(client, db, world, job, queued):
    user, h = _eligible(client, db, job, name="김지원")
    offer = _offer(client, world, job, user).json()
    assert offer["contact"] is None
    r = client.post(f"{OFFERS}/{offer['offer_id']}/accept", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["responded_at"]
    sent = client.get(f"{OFFERS}/sent", headers=world["recruiter"]).json()[0]
    assert sent["contact"] == {"display_name": "김지원", "email": "kim@seeker.test"}
    r = client.post(f"{OFFERS}/{offer['offer_id']}/reject", headers=h)
    assert (r.status_code, r.json()["code"], r.json()["status"]) == (409, "OFFER_NOT_PENDING", "accepted")


def test_reject_and_cancel(client, db, world, job, queued):
    other = make_published(client, world["recruiter"], title="다른 공고")["id"]
    user, h = _eligible(client, db, job)
    _done(db, other, client.get("/api/cv/me", headers=h).json()["id"], 80)
    offer = _offer(client, world, job, user).json()
    assert client.post(f"{OFFERS}/{offer['offer_id']}/reject", headers=h).json()["status"] == "rejected"
    assert client.get(f"{OFFERS}/sent", headers=world["recruiter"]).json()[0]["contact"] is None

    offer = _offer(client, world, other, user).json()
    r = client.post(f"{OFFERS}/{offer['offer_id']}/cancel", headers=world["rival"])
    assert (r.status_code, r.json()["code"]) == (404, "OFFER_NOT_FOUND")
    assert client.post(f"{OFFERS}/{offer['offer_id']}/cancel", headers=world["recruiter"]).json()["status"] == "cancelled"
    assert client.post(f"{OFFERS}/{offer['offer_id']}/accept", headers=h).json()["code"] == "OFFER_NOT_PENDING"


def test_expired_offers_cannot_be_answered(client, db, world, job, queued):
    user, h = _eligible(client, db, job)
    offer = _offer(client, world, job, user).json()
    _age(db, offer["offer_id"], 14)
    for path, headers in (("accept", h), ("reject", h), ("cancel", world["recruiter"])):
        r = client.post(f"{OFFERS}/{offer['offer_id']}/{path}", headers=headers)
        assert (r.status_code, r.json()["code"]) == (409, "OFFER_EXPIRED"), path
    assert client.get(f"{OFFERS}/mine", headers=h).json()[0]["status"] == "expired"


def test_who_may_do_what(client, db, world, job, queued):
    user, h = _eligible(client, db, job)
    _, other_h = _eligible(client, db, job, "lee@seeker.test", name="이수진")
    offer = _offer(client, world, job, user).json()
    r = client.post(f"{OFFERS}/{offer['offer_id']}/accept", headers=other_h)
    assert (r.status_code, r.json()["code"]) == (404, "OFFER_NOT_FOUND")
    assert client.get(f"{OFFERS}/mine", headers=other_h).json() == []
    assert client.get(f"{OFFERS}/mine", headers=world["recruiter"]).json()["code"] == "SEEKER_ONLY"
    assert client.post(f"{OFFERS}/{offer['offer_id']}/accept", headers=world["recruiter"]).status_code == 403
    assert client.post(OFFERS, json={"job_id": job, "anonymous_id": "x"}, headers=h).status_code == 403
    assert client.get(f"{OFFERS}/sent", headers=world["rival"]).json() == []
    assert client.get(f"{OFFERS}/mine").status_code == 401


# ── Q10: the seeker leaves the pool while an offer is pending ──


@pytest.mark.parametrize("leave", ["opt_out", "withdraw_consent"])
def test_pending_offer_survives_leaving_the_pool(client, db, world, job, queued, leave):
    user, h = _eligible(client, db, job)
    offer = _offer(client, world, job, user).json()
    if leave == "opt_out":
        client.put("/api/preferences/me", json={"profile_public": False}, headers=h)
    else:
        assert client.delete("/api/users/me/consent/ai", headers=h).status_code == 200
    sent = client.get(f"{OFFERS}/sent", headers=world["recruiter"]).json()[0]
    assert (sent["anonymous_id"], sent["candidate"], sent["status"]) == (offer["anonymous_id"], None, "pending")
    assert client.post(f"{OFFERS}/{offer['offer_id']}/accept", headers=h).json()["status"] == "accepted"
    sent = client.get(f"{OFFERS}/sent", headers=world["recruiter"]).json()[0]
    assert sent["candidate"] is None and sent["contact"]["email"] == "kim@seeker.test"


# ── Anonymous ID key ──


def test_anonymous_id_uses_its_own_secret(monkeypatch):
    base = talent_service.anonymous_id(1, 2)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "rotated-jwt-secret")
    assert talent_service.anonymous_id(1, 2) == base
    monkeypatch.setattr(settings, "TALENT_ID_SECRET", "rotated-talent-secret")
    assert talent_service.anonymous_id(1, 2) != base


# ── Real concurrency: PostgreSQL only ──

on_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)


def _parallel(db, n, work):
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(n)
    outcomes, lock = [], threading.Lock()

    def run(i):
        session = sessions()
        try:
            barrier.wait()
            result = work(session, i)
        except AppError as e:
            result = e.code
        finally:
            session.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return sorted(outcomes)


def _recruiter(session):
    return session.scalars(select(User).where(User.email == "hr@acme.test")).one()


@on_postgres
def test_pg_parallel_offers_to_one_seeker_create_one(client, db, world, job, queued):
    user, _ = _eligible(client, db, job)
    body = OfferCreate(job_id=job, anonymous_id=_anon(world, user))
    outcomes = _parallel(db, 6, lambda s, i: offer_service.create(s, _recruiter(s), body) and "created")
    assert outcomes == ["OFFER_EXISTS"] * 5 + ["created"]
    assert len(db.scalars(select(TalentOffer)).all()) == 1


@on_postgres
def test_pg_parallel_offers_respect_the_daily_limit(client, db, world, job, queued, monkeypatch):
    monkeypatch.setattr(settings, "OFFER_DAILY_LIMIT", 3)
    users = [_eligible(client, db, job, f"s{i}@seeker.test")[0] for i in range(6)]
    bodies = [OfferCreate(job_id=job, anonymous_id=_anon(world, u)) for u in users]
    outcomes = _parallel(db, 6, lambda s, i: offer_service.create(s, _recruiter(s), bodies[i]) and "created")
    assert outcomes == ["OFFER_DAILY_LIMIT"] * 3 + ["created"] * 3


@on_postgres
def test_pg_accept_and_cancel_race_has_one_winner(client, db, world, job, queued):
    for round_ in range(3):
        user, _ = _eligible(client, db, job, f"r{round_}@seeker.test")
        offer_id = _offer(client, world, job, user).json()["offer_id"]

        def answer(session, i, user_id=user.id):
            if i % 2:
                offer_service.cancel(session, _recruiter(session), offer_id)
                return "cancelled"
            offer_service.respond(session, session.get(User, user_id), offer_id, accept=True)
            return "accepted"

        outcomes = _parallel(db, 4, answer)
        assert len([o for o in outcomes if o in ("accepted", "cancelled")]) == 1, outcomes
        assert outcomes.count("OFFER_NOT_PENDING") == 3
