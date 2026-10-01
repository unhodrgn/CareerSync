def test_owner_edits_profile(client, world):
    body = {"name": "Acme Korea", "intro": "B2B SaaS", "talent_profile": "주도적으로 문제를 정의하는 사람"}
    r = client.put("/api/companies/me", json=body, headers=world["recruiter"])
    assert r.status_code == 200
    assert r.json() == {"id": world["acme"].id, **body}


def test_public_profile(client, world):
    r = client.get(f"/api/companies/{world['acme'].id}", headers=world["seeker"])
    assert r.status_code == 200 and r.json()["name"] == "Acme"
    assert set(r.json()) == {"id", "name", "intro", "talent_profile"}
    assert client.get("/api/companies/9999", headers=world["seeker"]).status_code == 404


def test_seeker_cannot_edit(client, world):
    assert client.put("/api/companies/me", json={"name": "x"}, headers=world["seeker"]).status_code == 403
    assert client.get("/api/companies/me", headers=world["seeker"]).status_code == 403


def test_limits(client, world):
    r = client.put("/api/companies/me", json={"name": "Acme", "talent_profile": "가" * 1001}, headers=world["recruiter"])
    assert r.status_code == 422
