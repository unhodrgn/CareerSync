from app.core.security import create_access_token

from .conftest import PASSWORD

SEEKER = {
    "email": "Kim@Example.com",
    "password": "pass1234",
    "role": "seeker",
    "display_name": "김지원",
    "consent_privacy": True,
    "consent_ai": True,
}
COMPANY = {**SEEKER, "email": "hr@newco.test", "role": "company", "display_name": "인사팀", "company_name": "뉴코"}


def register(client, body):
    return client.post("/api/auth/register", json=body)


def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_register_seeker_then_login_and_me(client, db):
    r = register(client, SEEKER)
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["email"] == "kim@example.com"  # stored lowercased
    assert body["role"] == "seeker" and body["company_id"] is None
    assert body["consent_version"]
    assert "password" not in str(body)

    r = login(client, "KIM@example.com", "pass1234")
    assert r.status_code == 200
    token = r.json()
    assert token["token_type"] == "bearer" and token["expires_in"] == 7200
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.json()["id"] == body["id"]
    assert "password_hash" not in me.json()


def test_register_company_creates_company(client):
    body = register(client, COMPANY).json()
    assert body["company_id"] is not None
    token = login(client, COMPANY["email"], COMPANY["password"]).json()["access_token"]
    company = client.get("/api/companies/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert company["name"] == "뉴코"


def test_company_requires_company_name(client):
    assert register(client, {**COMPANY, "company_name": None}).status_code == 422


def test_duplicate_email_case_insensitive(client):
    register(client, SEEKER)
    r = register(client, {**SEEKER, "email": "kim@EXAMPLE.com"})
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_TAKEN"


def test_consent_required(client):
    assert register(client, {**SEEKER, "consent_privacy": False}).status_code == 422
    assert register(client, {**SEEKER, "consent_ai": False}).status_code == 422


def test_weak_password_and_bad_email(client):
    assert register(client, {**SEEKER, "password": "short1"}).status_code == 422
    assert register(client, {**SEEKER, "password": "onlyletters"}).status_code == 422
    assert register(client, {**SEEKER, "password": "12345678"}).status_code == 422
    assert register(client, {**SEEKER, "email": "not-an-email"}).status_code == 422


def test_login_failures_look_the_same(client, world):
    wrong_password = login(client, "hr@acme.test", "wrong-pass1")
    unknown_email = login(client, "nobody@acme.test", PASSWORD)
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert login(client, "hr@acme.test", PASSWORD).status_code == 200


def test_expired_and_tampered_tokens(client, world):
    expired = create_access_token(1, expires_minutes=-1)
    assert client.get("/api/users/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    good = world["seeker"]["Authorization"]
    tampered = good[:-2] + ("aa" if not good.endswith("aa") else "bb")
    assert client.get("/api/users/me", headers={"Authorization": tampered}).status_code == 401
    assert client.get("/api/users/me").status_code == 401
