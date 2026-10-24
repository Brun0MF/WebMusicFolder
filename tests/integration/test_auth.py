import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from tests.conftest import PASSWORD, extract_csrf, login

from webmusicfolder.auth import require_auth
from webmusicfolder.main import create_app

PAGES = ["/", "/library", "/logs", "/settings"]


@pytest.mark.parametrize("path", PAGES)
def test_pages_redirect_to_login_when_anonymous(client, path):
    r = client.get(path)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_api_returns_401_when_anonymous(settings):
    app = create_app(settings)

    @app.get("/api/ping", dependencies=[Depends(require_auth)])
    async def ping():
        return {"ok": True}

    c = TestClient(app, follow_redirects=False)
    assert c.get("/api/ping").status_code == 401


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert 'name="password"' in r.text


def test_login_success_sets_cookie_and_opens_pages(client):
    r = login(client)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    for path in PAGES:
        assert client.get(path).status_code == 200


def test_login_wrong_password(client):
    r = login(client, "nope")
    assert r.status_code == 401
    assert "Wrong password" in r.text
    assert client.get("/").status_code == 303


def test_all_tabs_share_layout(client):
    login(client)
    for path in PAGES:
        html = client.get(path).text
        for label in ("Downloads", "Library", "Logs", "Settings"):
            assert f">{label}</a>" in html
        assert 'class="tabs"' in html


def test_logout(client):
    login(client)
    token = extract_csrf(client.get("/").text)
    r = client.post("/logout", data={"csrf_token": token})
    assert r.status_code == 303
    assert client.get("/").status_code == 303


def test_rate_limit_after_five_failures(client):
    for _ in range(5):
        assert login(client, "bad").status_code == 401
    r = login(client, "bad")
    assert r.status_code == 429
    # Even the right password is refused while blocked.
    assert login(client, PASSWORD).status_code == 429


def test_post_without_csrf_rejected(client):
    r = client.post("/login", data={"password": PASSWORD})
    assert r.status_code == 403
    client.get("/login")
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": "wrong"})
    assert r.status_code == 403


def test_csrf_header_accepted(client):
    token = extract_csrf(client.get("/login").text)
    r = client.post("/login", data={"password": PASSWORD}, headers={"X-CSRF-Token": token})
    assert r.status_code == 303
