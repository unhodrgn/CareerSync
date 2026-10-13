"""GET/PUT /api/preferences/me: seeker-only, whole-set replace, talent-pool opt-in timestamp."""
from datetime import UTC, datetime

from sqlalchemy import select

from ai.scoring.pref import JobFacts, pref_score
from app.models import SeekerPreference, User
from app.services import preference_service

from .conftest import _PASSWORD_HASH, auth

URL = "/api/preferences/me"
EMPTY = {"locations": [], "employment_types": [], "job_keywords": [], "profile_public": False}


def _seeker(db, email="pref@seeker.test"):
    now = datetime.now(UTC)
    user = User(email=email, password_hash=_PASSWORD_HASH, role="seeker", consent_privacy_at=now, consent_ai_at=now)
    db.add(user)
    db.commit()
    return user, auth(user)


def _body(r):
    return {k: r.json()[k] for k in EMPTY}


def test_get_before_saving_returns_empty_without_creating_a_row(client, db):
    _, h = _seeker(db)
    r = client.get(URL, headers=h)
    assert r.status_code == 200
    assert _body(r) == EMPTY and r.json()["profile_public_at"] is None and r.json()["updated_at"] is None
    assert db.scalars(select(SeekerPreference)).all() == []


def test_put_replaces_the_whole_set(client, db):
    _, h = _seeker(db)
    first = {"locations": ["서울", "판교"], "employment_types": ["full_time"], "job_keywords": ["백엔드", "Java"], "profile_public": False}
    r = client.put(URL, json=first, headers=h)
    assert r.status_code == 200, r.json()
    assert _body(r) == first and _body(client.get(URL, headers=h)) == first
    second = {**EMPTY, "locations": ["부산"]}
    assert _body(client.put(URL, json=second, headers=h)) == second
    assert _body(client.get(URL, headers=h)) == second
    assert len(db.scalars(select(SeekerPreference)).all()) == 1


def test_duplicates_are_merged_and_whitespace_trimmed(client, db):
    _, h = _seeker(db)
    body = {
        "locations": [" 서울  강남구 ", "서울 강남구", "판교"],
        "employment_types": ["intern", "intern", "contract"],
        "job_keywords": ["Java", "java", "JAVA ", "백엔드"],
    }
    r = client.put(URL, json=body, headers=h)
    assert r.status_code == 200, r.json()
    assert r.json()["locations"] == ["서울 강남구", "판교"]
    assert r.json()["employment_types"] == ["intern", "contract"]
    assert r.json()["job_keywords"] == ["Java", "백엔드"]


def test_validation(client, db):
    _, h = _seeker(db)
    bad = [
        {"locations": [f"지역{i}" for i in range(11)]},
        {"job_keywords": ["a"]},  # under 2 characters
        {"job_keywords": ["x" * 101]},
        {"employment_types": ["part_time"]},
        {"profile_public": "maybe"},
    ]
    for body in bad:
        assert client.put(URL, json={**EMPTY, **body}, headers=h).status_code == 422, body


def test_profile_public_at_tracks_the_opt_in(client, db):
    _, h = _seeker(db)
    on = client.put(URL, json={**EMPTY, "profile_public": True}, headers=h).json()
    assert on["profile_public"] is True and on["profile_public_at"] is not None
    still_on = client.put(URL, json={**EMPTY, "profile_public": True, "locations": ["서울"]}, headers=h).json()
    assert still_on["profile_public_at"] == on["profile_public_at"]  # unchanged while it stays on
    off = client.put(URL, json=EMPTY, headers=h).json()
    assert off["profile_public"] is False and off["profile_public_at"] is None


def test_seeker_only_and_own_only(client, db, world):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json=EMPTY).status_code == 401
    for method in ("GET", "PUT"):
        r = client.request(method, URL, json=EMPTY, headers=world["recruiter"])
        assert (r.status_code, r.json()["code"]) == (403, "SEEKER_ONLY")
    _, kim = _seeker(db, "kim@seeker.test")
    _, lee = _seeker(db, "lee@seeker.test")
    client.put(URL, json={**EMPTY, "locations": ["서울"]}, headers=kim)
    assert client.get(URL, headers=lee).json()["locations"] == []


def test_saved_preferences_feed_pref(client, db):
    user, h = _seeker(db)
    client.put(URL, json={**EMPTY, "locations": ["서울"], "job_keywords": ["Java"]}, headers=h)
    prefs = preference_service.to_preferences(preference_service.get_mine(db, user))
    busan = JobFacts(title="Java 백엔드 개발자", location="부산", employment_type="full_time")
    assert pref_score(prefs, busan).score == 50.0  # 2 fields filled, 1 matches
