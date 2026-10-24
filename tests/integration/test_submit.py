import time

import pytest
from fastapi.testclient import TestClient
from tests.conftest import login

from webmusicfolder.main import create_app

PL = "https://www.youtube.com/playlist?list=PLabcdef123456"


def csrf_header(client):
    page = client.get("/")
    import re

    match = re.search(r'"X-CSRF-Token": "([^"]+)"', page.text)
    assert match
    return {"X-CSRF-Token": match.group(1)}


@pytest.fixture
def app_client(settings, fake_runner):
    def build(**runner_kwargs):
        app = create_app(settings, runner=fake_runner(**runner_kwargs))
        client = TestClient(app, follow_redirects=False)
        assert login(client).status_code == 303
        return client

    return build


def test_folders_lists_existing_subfolders(app_client, settings):
    for name in ("geek", "Rock", ".hidden"):
        (settings.music_dir / name).mkdir(parents=True)
    client = app_client()
    assert client.get("/api/folders").json() == {"folders": ["geek", "Rock"]}


def test_api_requires_auth(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    assert client.get("/api/folders").status_code == 401
    assert client.post("/api/submit/preview", json={"links": ""}).status_code == 401


def test_post_requires_csrf(app_client):
    client = app_client()
    r = client.post("/api/submit/preview", json={"links": "", "subfolder": ""})
    assert r.status_code == 403


def test_preview_counts_and_invalid_lines(app_client):
    client = app_client(flat={PL: [{"id": f"p{i:010d}", "title": f"T{i}"} for i in range(10)]})
    headers = csrf_header(client)
    text = "\n".join(
        [
            "https://youtu.be/aaaaaaaaaaa",
            "https://youtu.be/bbbbbbbbbbb",
            "https://www.youtube.com/watch?v=ccccccccccc",
            PL,
            "https://evil.example/watch?v=ddddddddddd",
            "nonsense",
        ]
    )
    r = client.post(
        "/api/submit/preview", json={"links": text, "subfolder": "geek"}, headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 13
    assert [link["kind"] for link in body["links"]] == ["video"] * 3 + ["playlist"] + [
        "invalid"
    ] * 2
    assert body["links"][3]["count"] == 10
    assert body["links"][4]["error"] and body["links"][5]["error"]
    assert len(body["items"]) == 13


@pytest.mark.parametrize("bad", ["../x", "a/b", ".hidden", "x" * 81])
def test_bad_subfolder_is_422_on_both_endpoints(app_client, bad):
    client = app_client()
    headers = csrf_header(client)
    r = client.post("/api/submit/preview", json={"links": "", "subfolder": bad}, headers=headers)
    assert r.status_code == 422
    r = client.post("/api/submit/confirm", json={"items": [], "subfolder": bad}, headers=headers)
    assert r.status_code == 422


def test_confirm_creates_items_once_and_rejects_bad_ids(app_client, settings):
    client = app_client()
    headers = csrf_header(client)
    items = [{"video_id": "aaaaaaaaaaa", "title": "A"}, {"video_id": "bbbbbbbbbbb"}]
    r = client.post(
        "/api/submit/confirm",
        json={"subfolder": "geek", "items": [*items, items[0]]},
        headers=headers,
    )
    assert r.json() == {"queued": 2, "ignored": 1}
    queue = client.app.state.store._state.queue
    assert [(i.video_id, i.subfolder, i.status, i.title) for i in queue] == [
        ("aaaaaaaaaaa", "geek", "queued", "A"),
        ("bbbbbbbbbbb", "geek", "queued", "bbbbbbbbbbb"),
    ]
    assert queue[0].url == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    again = client.post("/api/submit/confirm", json={"items": items[:1]}, headers=headers)
    assert again.json() == {"queued": 0, "ignored": 1}
    bad = client.post(
        "/api/submit/confirm", json={"items": [{"video_id": "../../etc"}]}, headers=headers
    )
    assert bad.status_code == 422


def test_confirm_wakes_worker_which_downloads(settings, fake_runner):
    app = create_app(settings, runner=fake_runner(titles={"aaaaaaaaaaa": "Wake Up"}))
    with TestClient(app, follow_redirects=False) as client:
        assert login(client).status_code == 303
        headers = csrf_header(client)
        r = client.post(
            "/api/submit/confirm",
            json={"subfolder": "geek", "items": [{"video_id": "aaaaaaaaaaa"}]},
            headers=headers,
        )
        assert r.json()["queued"] == 1
        target = settings.music_dir / "geek" / "Wake Up.mp3"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not target.exists():
            time.sleep(0.05)
        assert target.is_file()
    assert app.state.store._state.queue[0].status in ("done", "downloading", "queued")
