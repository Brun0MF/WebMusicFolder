import os

import pytest
from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_import_external import LINK, link
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app


@pytest.fixture
def client(settings):
    c = TestClient(create_app(settings), follow_redirects=False)
    assert login(c).status_code == 303
    return c


def delete(client, path):
    return client.request(
        "DELETE", "/api/library", json={"path": path}, headers=csrf_header(client)
    )


def test_requires_csrf(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    assert client.request("DELETE", "/api/library", json={"path": "a.mp3"}).status_code == 403


def test_delete_removes_file_and_listing(client, settings, make_mp3):
    path = make_mp3(settings.music_dir / "rock" / "a.mp3", title="A")
    assert client.get("/api/library").json()["total"] == 1
    assert delete(client, "rock/a.mp3").status_code == 200
    assert not path.exists()
    assert client.get("/api/library").json()["total"] == 0


def test_delete_forgets_track_so_link_is_not_duplicate(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="Song", artist="Band")
    link(client, "a.mp3")
    assert delete(client, "a.mp3").json() == {"removed_tracks": 1}
    preview = client.post(
        "/api/submit/preview", json={"links": LINK, "subfolder": ""}, headers=csrf_header(client)
    ).json()
    assert preview["duplicates"] == []


@pytest.mark.parametrize("bad", ["../x.mp3", "/etc/passwd", "a.txt", ".hidden/a.mp3", "nope.mp3"])
def test_delete_rejects_bad_paths(client, settings, make_mp3, bad):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    assert delete(client, bad).status_code == 404


def test_delete_does_not_follow_symlink_out(client, settings, tmp_path):
    secret = tmp_path / "secret.mp3"
    secret.write_bytes(b"x")
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    os.symlink(secret, settings.music_dir / "link.mp3")
    assert delete(client, "link.mp3").status_code == 404
    assert secret.exists()
