import pytest
from fastapi.testclient import TestClient
from mutagen.id3 import ID3
from tests.conftest import login
from tests.integration.test_submit import PL, csrf_header

from webmusicfolder.main import create_app

VID = "abcdefghijk"
LINK = f"https://youtu.be/{VID}"


@pytest.fixture
def client(settings):
    c = TestClient(create_app(settings), follow_redirects=False)
    assert login(c).status_code == 303
    return c


def link(client, path, url=LINK):
    return client.post(
        "/api/library/link", json={"path": path, "link": url}, headers=csrf_header(client)
    )


def source_of(client, path):
    entries = client.get("/api/library").json()["entries"]
    return next(e["source"] for e in entries if e["path"] == path)


def test_requires_csrf(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    body = {"path": "a.mp3", "link": LINK}
    assert client.post("/api/library/link", json=body).status_code == 403


def test_link_turns_external_into_app_and_keeps_tags(client, settings, make_mp3):
    path = make_mp3(
        settings.music_dir / "rock" / "a.mp3", title="Song", artist="Band", cover=b"\xff\xd8c"
    )
    before = ID3(path)
    assert source_of(client, "rock/a.mp3") == "External"

    assert link(client, "rock/a.mp3").status_code == 200

    assert source_of(client, "rock/a.mp3") == "App"
    after = ID3(path)
    assert str(after["TXXX:youtube_id"].text[0]) == VID
    assert str(after["TXXX:youtube_url"].text[0]).endswith(VID)
    for key in before:
        assert after[key].pprint() == before[key].pprint()
    assert not list(path.parent.glob(".*.part"))


def test_linked_file_is_a_duplicate_afterwards(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="Song", artist="Band")
    link(client, "a.mp3")
    preview = client.post(
        "/api/submit/preview", json={"links": LINK, "subfolder": ""}, headers=csrf_header(client)
    ).json()
    assert [d["kind"] for d in preview["duplicates"]] == ["exists"]
    assert preview["duplicates"][0]["path"] == "a.mp3"


def test_file_without_tags_gets_a_tag(client, settings, make_mp3):
    path = make_mp3(settings.music_dir / "plain.mp3")
    assert link(client, "plain.mp3").status_code == 200
    assert str(ID3(path)["TXXX:youtube_id"].text[0]) == VID


def test_conflicts(client, settings, make_mp3):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    make_mp3(settings.music_dir / "b.mp3", title="B")
    assert link(client, "a.mp3").status_code == 200
    # Same video on another file, and the already linked file again.
    assert link(client, "b.mp3").status_code == 409
    assert link(client, "a.mp3", f"https://youtu.be/{'x' * 11}").status_code == 409


@pytest.mark.parametrize(
    ("path", "url", "status"),
    [
        ("a.mp3", PL, 422),
        ("a.mp3", "https://example.com/watch?v=abcdefghijk", 422),
        ("a.mp3", "not a link", 422),
        ("missing.mp3", LINK, 404),
        ("../outside.mp3", LINK, 404),
        ("a.txt", LINK, 404),
    ],
)
def test_rejections(client, settings, make_mp3, path, url, status):
    make_mp3(settings.music_dir / "a.mp3", title="A")
    (settings.music_dir / "a.txt").write_text("x")
    assert link(client, path, url).status_code == status


def test_symlink_escape_is_refused(client, settings, make_mp3, tmp_path):
    outside = make_mp3(tmp_path / "outside" / "o.mp3", title="O")
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    (settings.music_dir / "evil.mp3").symlink_to(outside)
    assert link(client, "evil.mp3").status_code == 404
    assert "TXXX:youtube_id" not in ID3(outside)


def test_write_failure_leaves_the_original_untouched(client, settings, make_mp3, monkeypatch):
    path = make_mp3(settings.music_dir / "a.mp3", title="A")
    original = path.read_bytes()
    from webmusicfolder import importer

    def boom(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(importer.ID3, "save", boom)
    assert link(client, "a.mp3").status_code == 500
    assert path.read_bytes() == original
    assert not list(settings.music_dir.glob(".*.part"))
