import pytest
from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app

IDS = [f"vid{n:08d}" for n in range(3)]
TABLE = {"song": [{"id": i, "title": f"T{i}", "channel": "C", "duration_s": 60} for i in IDS]}


@pytest.fixture
def client(settings, fake_runner):
    c = TestClient(create_app(settings, runner=fake_runner(search=TABLE)), follow_redirects=False)
    assert login(c).status_code == 303
    return c


def test_requires_auth_and_csrf(settings, fake_runner, client):
    anon = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    assert anon.post("/api/search", json={"q": "song"}).status_code in (401, 403)
    assert client.post("/api/search", json={"q": "song"}).status_code == 403


def test_results(client):
    response = client.post("/api/search", json={"q": "song"}, headers=csrf_header(client))
    body = response.json()
    assert [r["video_id"] for r in body["results"]] == IDS
    assert all(r["state"] is None for r in body["results"])


@pytest.mark.parametrize("q", ["", "   ", "x" * 300])
def test_bad_query_is_422(client, q):
    assert client.post("/api/search", json={"q": q}, headers=csrf_header(client)).status_code == 422


def test_failure_is_502_with_message(client):
    response = client.post("/api/search", json={"q": "nope"}, headers=csrf_header(client))
    assert response.status_code == 502
    assert response.json()["detail"]


async def test_marks_downloaded_and_queued(settings, fake_runner, make_mp3):
    from webmusicfolder.models import QueueItem, Track

    app = create_app(settings, runner=fake_runner(search=TABLE))
    make_mp3(settings.music_dir / "a.mp3", title="a", video_id=IDS[0])
    await app.state.store.upsert_track(
        Track(IDS[0], "u", "a", "x", 1, "", "a.mp3", "2026-01-01T00:00:00Z", "v0")
    )
    await app.state.store.add_queue_items(
        [QueueItem(id="q1", video_id=IDS[1], url="u", title="b", subfolder="", added_at="x")]
    )
    c = TestClient(app, follow_redirects=False)
    login(c)
    states = {
        r["video_id"]: r["state"]
        for r in c.post("/api/search", json={"q": "song"}, headers=csrf_header(c)).json()["results"]
    }
    assert states == {IDS[0]: "exists", IDS[1]: "queued", IDS[2]: None}
