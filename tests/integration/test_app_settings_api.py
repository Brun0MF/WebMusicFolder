from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app


def build(settings):
    client = TestClient(create_app(settings), follow_redirects=False)
    assert login(client).status_code == 303
    return client


def test_requires_auth_and_csrf(settings):
    anon = TestClient(create_app(settings), follow_redirects=False)
    assert anon.get("/api/settings").status_code == 401
    client = build(settings)
    assert client.post("/api/settings", json={"sponsorblock": True}).status_code == 403


def test_defaults_are_off(settings):
    assert build(settings).get("/api/settings").json() == {
        "sponsorblock": False,
        "replaygain": False,
    }


def test_partial_update_and_persistence(settings):
    client = build(settings)
    headers = csrf_header(client)
    response = client.post("/api/settings", json={"sponsorblock": True}, headers=headers)
    assert response.json() == {"sponsorblock": True, "replaygain": False}
    client.post("/api/settings", json={"replaygain": True}, headers=headers)
    # A new app on the same data dir reads the stored values.
    again = build(settings)
    assert again.get("/api/settings").json() == {"sponsorblock": True, "replaygain": True}


def test_rejects_non_boolean(settings):
    client = build(settings)
    response = client.post(
        "/api/settings", json={"sponsorblock": "maybe"}, headers=csrf_header(client)
    )
    assert response.status_code == 422
