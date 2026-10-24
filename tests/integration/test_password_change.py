import json

from fastapi.testclient import TestClient
from tests.conftest import PASSWORD, login
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app


def change(client, current, new):
    return client.post(
        "/api/account/password", json={"current": current, "new": new}, headers=csrf_header(client)
    )


def make(settings):
    c = TestClient(create_app(settings), follow_redirects=False)
    assert login(c).status_code == 303
    return c


def test_requires_login_and_csrf(settings):
    c = TestClient(create_app(settings), follow_redirects=False)
    assert c.post("/api/account/password", json={"current": "a", "new": "b"}).status_code == 401
    login(c)
    body = {"current": PASSWORD, "new": "another-pass"}
    assert c.post("/api/account/password", json=body).status_code == 403


def test_wrong_current_and_short_new(settings):
    c = make(settings)
    assert change(c, "nope", "long-enough-1").status_code == 403
    assert change(c, PASSWORD, "short").status_code == 422
    assert change(c, PASSWORD, PASSWORD).status_code == 422


def test_change_persists_and_replaces_env_password(settings):
    c = make(settings)
    assert change(c, PASSWORD, "brand-new-pass").status_code == 200
    # This session stays logged in.
    assert c.get("/api/config").status_code == 200
    stored = (settings.data_dir / "password.json").read_text()
    assert "brand-new-pass" not in stored and json.loads(stored)["hash"]
    # A fresh app on the same data dir: old password refused, new one accepted.
    fresh = TestClient(create_app(settings), follow_redirects=False)
    assert login(fresh, PASSWORD).status_code == 401
    assert login(fresh, "brand-new-pass").status_code == 303


def test_other_sessions_are_signed_out(settings):
    a = make(settings)
    b = TestClient(a.app, follow_redirects=False)
    assert login(b).status_code == 303
    assert change(a, PASSWORD, "brand-new-pass").status_code == 200
    assert b.get("/api/config").status_code == 401
    assert a.get("/api/config").status_code == 200
