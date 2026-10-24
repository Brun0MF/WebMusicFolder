import sys
import time

from fastapi.testclient import TestClient
from tests.conftest import FAKE_PIP, login
from tests.integration.test_live import ID
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app
from webmusicfolder.ytdlp_update import YtdlpUpdater, package_dir_for


def build(settings, fake_runner, pip="ok:2099.01.01", scenarios=None):
    package = package_dir_for(settings.data_dir)
    runner = fake_runner(scenarios=scenarios, extra_pythonpath=package)
    app = create_app(settings, runner=runner)
    app.state.updater = YtdlpUpdater(
        package, runner, pip_cmd=(sys.executable, str(FAKE_PIP)), pip_env={"FAKE_PIP": pip}
    )
    return app


def test_endpoints_require_auth_and_csrf(settings, fake_runner):
    client = TestClient(build(settings, fake_runner), follow_redirects=False)
    assert client.get("/api/ytdlp/version").status_code == 401
    assert client.post("/api/ytdlp/update").status_code in (401, 403)
    login(client)
    assert client.post("/api/ytdlp/update").status_code == 403


def test_version_then_update_shows_old_and_new(settings, fake_runner):
    client = TestClient(build(settings, fake_runner, "ok:2099.07.08"), follow_redirects=False)
    login(client)
    assert client.get("/api/ytdlp/version").json() == {"version": "2020.01.01", "updating": False}
    response = client.post("/api/ytdlp/update", headers=csrf_header(client))
    assert response.json() == {"old": "2020.01.01", "new": "2099.07.08", "changed": True}
    assert client.get("/api/ytdlp/version").json()["version"] == "2099.07.08"


def test_failed_update_returns_the_error_and_keeps_the_old_version(settings, fake_runner):
    client = TestClient(build(settings, fake_runner, "fail"), follow_redirects=False)
    login(client)
    response = client.post("/api/ytdlp/update", headers=csrf_header(client))
    assert response.status_code == 502
    assert "pip failed" in response.json()["detail"]
    assert client.get("/api/ytdlp/version").json()["version"] == "2020.01.01"


def test_update_is_refused_while_a_download_runs(settings, fake_runner):
    app = build(settings, fake_runner, scenarios={ID: "slow:30"})
    with TestClient(app, follow_redirects=False) as client:
        login(client)
        headers = csrf_header(client)
        client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
        end = time.monotonic() + 10
        while time.monotonic() < end and not client.app.state.worker.active_ids:
            time.sleep(0.05)
        response = client.post("/api/ytdlp/update", headers=headers)
        assert response.status_code == 409
        assert "idle" in response.json()["detail"]
        # Nothing was touched.
        assert not package_dir_for(settings.data_dir).exists()


def test_settings_page_renders_both_cards_with_the_account_warning(settings, fake_runner):
    client = TestClient(build(settings, fake_runner), follow_redirects=False)
    login(client)
    html = client.get("/settings").text
    assert "settingsPage()" in html
    assert "Update yt-dlp" in html
    assert "access to the Google account" in html
    assert 'id="cookies"' in html
