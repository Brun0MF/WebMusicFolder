import os

import pytest
from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app

JPEG = b"\xff\xd8\xff\xe0cover\xff\xd9"


@pytest.fixture
def client(settings, fake_runner, make_mp3):
    music = settings.music_dir
    make_mp3(music / "geek" / "a.mp3", "Alpha", "Zed", "Alb", cover=JPEG)
    make_mp3(music / "b.mp3", "Beta", "Yan")
    c = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(c)
    return c


def test_requires_auth(settings, fake_runner):
    c = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    assert c.get("/api/library").status_code == 401
    assert c.get("/api/library/cover?path=a.mp3").status_code == 401


def test_list_with_filters(client):
    body = client.get("/api/library").json()
    assert body["total"] == 2 and body["count"] == 2
    assert body["subfolders"] == ["", "geek"]
    assert {e["path"] for e in body["entries"]} == {"geek/a.mp3", "b.mp3"}
    assert client.get("/api/library", params={"q": "yan"}).json()["count"] == 1
    assert client.get("/api/library", params={"subfolder": "geek"}).json()["count"] == 1
    both = client.get("/api/library", params={"subfolder": "", "q": "beta"}).json()
    assert [e["path"] for e in both["entries"]] == ["b.mp3"]
    assert client.get("/api/library", params={"source": "External"}).json()["count"] == 2
    assert client.get("/api/library", params={"source": "App"}).json()["count"] == 0
    assert client.get("/api/library", params={"source": "bogus"}).status_code == 422


def test_rescan_picks_up_new_files(client, settings, make_mp3):
    assert client.get("/api/library").json()["total"] == 2
    make_mp3(settings.music_dir / "new.mp3", "New")
    headers = csrf_header(client)
    assert client.post("/api/library/rescan", headers=headers).json() == {"total": 3}
    assert client.post("/api/library/rescan").status_code == 403


def test_cover_image_and_placeholder(client):
    ok = client.get("/api/library/cover", params={"path": "geek/a.mp3"})
    assert ok.status_code == 200 and ok.content == JPEG
    assert ok.headers["content-type"] == "image/jpeg"
    none = client.get("/api/library/cover", params={"path": "b.mp3"})
    assert none.status_code == 200 and none.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in none.content


@pytest.mark.parametrize(
    "bad", ["../data/state.json", "/etc/passwd", "geek/../../x.mp3", "nope.mp3", "geek"]
)
def test_cover_rejects_traversal_and_missing(client, bad):
    assert client.get("/api/library/cover", params={"path": bad}).status_code == 404


def test_cover_does_not_follow_symlink_out(client, settings, make_mp3, tmp_path):
    secret = make_mp3(tmp_path / "outside" / "s.mp3", "s", cover=JPEG)
    os.symlink(secret, settings.music_dir / "link.mp3")
    assert client.get("/api/library/cover", params={"path": "link.mp3"}).status_code == 404
