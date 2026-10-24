import os
import stat
import time

from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_live import ID
from tests.integration.test_submit import csrf_header
from tests.unit.test_cookies import JAR

from webmusicfolder.main import create_app


def make_client(settings, fake_runner, **kwargs):
    client = TestClient(create_app(settings, runner=fake_runner(**kwargs)), follow_redirects=False)
    login(client)
    return client, csrf_header(client)


def test_requires_auth_and_csrf(settings, fake_runner):
    anon = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    assert anon.get("/api/cookies").status_code == 401
    assert anon.post("/api/cookies", json={"text": JAR}).status_code in (401, 403)
    client, _ = make_client(settings, fake_runner)
    assert client.post("/api/cookies", json={"text": JAR}).status_code == 403
    assert client.delete("/api/cookies").status_code == 403


def test_paste_stores_the_file_and_never_returns_its_content(settings, fake_runner):
    client, headers = make_client(settings, fake_runner)
    assert client.get("/api/cookies").json() == {
        "loaded": False,
        "saved_at": None,
        "browser": None,
    }
    response = client.post("/api/cookies", json={"text": JAR}, headers=headers)
    body = response.json()
    assert response.status_code == 200 and body["loaded"] and body["saved_at"]
    assert "secretvalue123" not in response.text
    assert "secretvalue123" not in client.get("/api/cookies").text
    path = settings.data_dir / "cookies.txt"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_invalid_content_is_rejected_with_a_message(settings, fake_runner):
    client, headers = make_client(settings, fake_runner)
    response = client.post("/api/cookies", json={"text": "not a cookie file"}, headers=headers)
    assert response.status_code == 422
    assert "Netscape" in response.json()["detail"]
    assert not (settings.data_dir / "cookies.txt").exists()


def test_delete_removes_the_file(settings, fake_runner):
    client, headers = make_client(settings, fake_runner)
    client.post("/api/cookies", json={"text": JAR}, headers=headers)
    response = client.delete("/api/cookies", headers=headers)
    assert response.json()["loaded"] is False
    assert not (settings.data_dir / "cookies.txt").exists()


def test_cookies_file_is_not_served_as_static_or_page(settings, fake_runner):
    client, headers = make_client(settings, fake_runner)
    client.post("/api/cookies", json={"text": JAR}, headers=headers)
    for path in ("/cookies.txt", "/static/cookies.txt", "/data/cookies.txt"):
        assert "secretvalue123" not in client.get(path).text


def _download_and_read_cookie_arg(client, headers, state_dir):
    client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
    marker = state_dir / f"cookies_{ID}"
    end = time.monotonic() + 15
    while time.monotonic() < end and not marker.exists():
        time.sleep(0.05)
    return marker.read_text()


def test_downloads_use_the_cookies_only_while_the_file_exists(settings, fake_runner):
    app = create_app(settings, runner=fake_runner())
    state_dir = fake_runner.state_dir
    with TestClient(app, follow_redirects=False) as client:
        login(client)
        headers = csrf_header(client)
        client.post("/api/cookies", json={"text": JAR}, headers=headers)
        assert _download_and_read_cookie_arg(client, headers, state_dir) == str(
            settings.data_dir / "cookies.txt"
        )
        # After deleting, the next run gets no --cookies at all.
        client.delete("/api/cookies", headers=headers)
        (state_dir / f"cookies_{ID}").unlink()
        other = "bbbbbbbbbbb"
        client.post("/api/submit/confirm", json={"items": [{"video_id": other}]}, headers=headers)
        marker = state_dir / f"cookies_{other}"
        end = time.monotonic() + 15
        while time.monotonic() < end and not marker.exists():
            time.sleep(0.05)
        assert marker.read_text() == ""


def _marker(state_dir, name, vid):
    marker = state_dir / f"{name}_{vid}"
    end = time.monotonic() + 15
    while time.monotonic() < end and not marker.exists():
        time.sleep(0.05)
    return marker.read_text()


def test_browser_source_is_used_until_a_cookies_file_is_uploaded(settings, fake_runner):
    from dataclasses import replace

    app = create_app(replace(settings, cookies_from_browser="firefox:work"), runner=fake_runner())
    state_dir = fake_runner.state_dir
    with TestClient(app, follow_redirects=False) as client:
        login(client)
        headers = csrf_header(client)
        assert client.get("/api/cookies").json()["browser"] == "firefox:work"
        client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
        assert _marker(state_dir, "browser", ID) == "firefox:work"
        assert _marker(state_dir, "cookies", ID) == ""

        # An uploaded file takes precedence: the next run gets --cookies only.
        client.post("/api/cookies", json={"text": JAR}, headers=headers)
        other = "bbbbbbbbbbb"
        client.post("/api/submit/confirm", json={"items": [{"video_id": other}]}, headers=headers)
        assert _marker(state_dir, "cookies", other) == str(settings.data_dir / "cookies.txt")
        assert _marker(state_dir, "browser", other) == ""
