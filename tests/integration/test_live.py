import json
import time

import pytest
from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app

ID = "aaaaaaaaaaa"


def parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        if block.startswith("event:"):
            head, data = block.split("\n", 1)
            events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


@pytest.fixture
def idle_client(settings, fake_runner):
    # No lifespan: the worker stays stopped so items keep their state.
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    return client, csrf_header(client)


def test_events_requires_auth(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    assert client.get("/events").status_code == 303


def test_stream_starts_with_a_full_snapshot(idle_client):
    client, headers = idle_client
    client.post(
        "/api/submit/confirm", json={"items": [{"video_id": ID, "title": "A"}]}, headers=headers
    )
    client.app.state.bus.close()
    with client.stream("GET", "/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    kind, data = parse_sse(body)[0]
    assert kind == "snapshot"
    assert [(i["video_id"], i["status"]) for i in data["items"]] == [(ID, "queued")]
    assert data["paused"] is None


def test_confirm_publishes_item_events_to_subscribers(idle_client):
    client, headers = idle_client
    sub = client.app.state.bus.subscribe()
    client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
    kind, data = sub._queue.get_nowait()
    assert kind == "item" and data["video_id"] == ID


def test_cancel_removes_queued_item_and_unknown_is_404(idle_client):
    client, headers = idle_client
    client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
    item_id = client.app.state.store._state.queue[0].id
    assert client.post(f"/api/queue/{item_id}/cancel", headers=headers).status_code == 200
    assert client.app.state.store._state.queue == []
    assert client.post("/api/queue/nope/cancel", headers=headers).status_code == 404
    assert client.post("/api/queue/nope/retry", headers=headers).status_code == 404


def test_retry_only_for_failed_items(idle_client):
    client, headers = idle_client
    client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
    item_id = client.app.state.store._state.queue[0].id
    assert client.post(f"/api/queue/{item_id}/retry", headers=headers).status_code == 409


def test_actions_require_csrf(idle_client):
    client, _ = idle_client
    assert client.post("/api/queue/x/cancel").status_code == 403


def test_cancel_running_download_drops_the_item(settings, fake_runner):
    app = create_app(settings, runner=fake_runner(scenarios={ID: "slow:30"}))
    with TestClient(app, follow_redirects=False) as client:
        login(client)
        headers = csrf_header(client)
        store = client.app.state.store
        client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
        end = time.monotonic() + 10
        while time.monotonic() < end and store._state.queue[0].status != "downloading":
            time.sleep(0.05)
        item_id = store._state.queue[0].id
        sub = client.app.state.bus.subscribe()
        assert client.post(f"/api/queue/{item_id}/cancel", headers=headers).status_code == 200
        end = time.monotonic() + 10
        while time.monotonic() < end and store._state.queue:
            time.sleep(0.05)
        assert store._state.queue == []
        kinds = []
        while not sub._queue.empty():
            kinds.append(sub._queue.get_nowait()[0])
        assert "removed" in kinds
        assert list(settings.music_dir.rglob("*.mp3")) == []
