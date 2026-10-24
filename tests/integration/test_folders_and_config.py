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


def post(client, url, body, method="POST"):
    return client.request(method, url, json=body, headers=csrf_header(client))


def paths(client):
    return sorted(e["path"] for e in client.get("/api/library").json()["entries"])


def test_create_folder_lists_it_even_when_empty(client, settings):
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    assert post(client, "/api/library/folders", {"name": "Rock"}).status_code == 200
    assert client.get("/api/library").json()["folders"] == [{"name": "Rock", "count": 0}]


@pytest.mark.parametrize("bad", ["a/b", "..", ".hid", "x\\y"])
def test_create_folder_rejects_bad_names(client, settings, bad):
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    assert post(client, "/api/library/folders", {"name": bad}).status_code == 422


def test_move_into_folder_and_back_updates_track(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    link(client, "a.mp3")
    res = post(client, "/api/library/move", {"paths": ["a.mp3"], "subfolder": "Rock"})
    assert res.json() == {"done": 1, "failed": []}
    assert paths(client) == ["Rock/a.mp3"]
    # The track follows the file, so the duplicate dialog points at the new place.
    preview = post(client, "/api/submit/preview", {"links": LINK, "subfolder": ""}).json()
    assert preview["duplicates"][0]["path"] == "Rock/a.mp3"
    assert (
        post(client, "/api/library/move", {"paths": ["Rock/a.mp3"], "subfolder": ""}).json()["done"]
        == 1
    )
    assert paths(client) == ["a.mp3"]


def test_move_never_overwrites_and_reports(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    make_mp3(settings.music_dir / "Rock" / "a.mp3", title="Other")
    body = post(client, "/api/library/move", {"paths": ["a.mp3", "nope.mp3"], "subfolder": "Rock"})
    out = body.json()
    assert out["done"] == 0
    assert {f["path"] for f in out["failed"]} == {"a.mp3", "nope.mp3"}
    assert paths(client) == ["Rock/a.mp3", "a.mp3"]


def test_move_rejects_bad_destination(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    assert (
        post(client, "/api/library/move", {"paths": ["a.mp3"], "subfolder": "../x"}).status_code
        == 422
    )


def test_bulk_delete(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    make_mp3(settings.music_dir / "b.mp3", title="B")
    make_mp3(settings.music_dir / "c.mp3", title="C")
    out = post(client, "/api/library/delete", {"paths": ["a.mp3", "b.mp3", "../zz.mp3"]}).json()
    assert out["done"] == 2 and len(out["failed"]) == 1
    assert paths(client) == ["c.mp3"]


def test_delete_folder_removes_files_and_tracks(client, settings, make_mp3):
    make_mp3(settings.music_dir / "Rock" / "a.mp3", title="A")
    make_mp3(settings.music_dir / "keep.mp3", title="K")
    link(client, "Rock/a.mp3")
    out = post(client, "/api/library/folders", {"name": "Rock"}, method="DELETE")
    assert out.json() == {"deleted_tracks": 1}
    assert not (settings.music_dir / "Rock").exists()
    assert paths(client) == ["keep.mp3"]
    preview = post(client, "/api/submit/preview", {"links": LINK, "subfolder": ""}).json()
    assert preview["duplicates"] == []


def test_delete_folder_rejects_unsafe(client, settings, tmp_path):
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.mp3").write_bytes(b"x")
    (settings.music_dir / "ln").symlink_to(outside, target_is_directory=True)
    assert post(client, "/api/library/folders", {"name": "ln"}, method="DELETE").status_code == 404
    assert post(client, "/api/library/folders", {"name": ".."}, method="DELETE").status_code == 422
    assert (outside / "x.mp3").exists()


def test_config_defaults_and_persistence(settings, tmp_path):
    c = TestClient(create_app(settings), follow_redirects=False)
    login(c)
    cfg = c.get("/api/config").json()
    assert cfg["music_dir"] == str(settings.music_dir) and cfg["quality"] == "v0"
    new_dir = tmp_path / "other"
    res = post(c, "/api/config", {"music_dir": str(new_dir), "quality": "320k", "concurrency": 2})
    assert res.status_code == 200
    assert new_dir.is_dir()
    # A fresh app on the same data dir picks the saved values up.
    c2 = TestClient(create_app(settings), follow_redirects=False)
    login(c2)
    cfg2 = c2.get("/api/config").json()
    assert (cfg2["music_dir"], cfg2["quality"], cfg2["concurrency"]) == (str(new_dir), "320k", 2)
    assert cfg2["default_music_dir"] == str(settings.music_dir)
    reset = post(c2, "/api/config", {"music_dir": ""}).json()
    assert reset["music_dir"] == str(settings.music_dir)


def test_config_library_follows_music_dir(client, settings, tmp_path, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    other = tmp_path / "other"
    make_mp3(other / "b.mp3", title="B")
    post(client, "/api/config", {"music_dir": str(other)})
    assert paths(client) == ["b.mp3"]


@pytest.mark.parametrize(
    "body",
    [
        {"music_dir": "relative/path"},
        {"music_dir": "/a/../b"},
        {"quality": "mp4"},
        {"concurrency": 99},
    ],
)
def test_config_rejects_bad_values(client, body):
    assert post(client, "/api/config", body).status_code == 422


def test_config_requires_csrf(client):
    assert client.post("/api/config", json={"quality": "v0"}).status_code == 403
