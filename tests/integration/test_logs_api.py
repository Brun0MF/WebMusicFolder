import time

from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_live import ID
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app


def wait_for(predicate, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_logs_endpoint_requires_auth(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    assert client.get("/api/logs").status_code == 401


def test_failing_download_shows_its_lines_in_the_log(settings, fake_runner):
    runner = fake_runner(scenarios={ID: "error:unavailable"})
    with TestClient(create_app(settings, runner=runner), follow_redirects=False) as client:
        login(client)
        headers = csrf_header(client)
        client.post(
            "/api/submit/confirm",
            json={"items": [{"video_id": ID, "title": "Broken"}]},
            headers=headers,
        )
        logs = client.app.state.logs
        assert wait_for(
            lambda: any(e["line"].startswith("ERROR: unavailable") for e in logs.lines())
        )
        entries = client.get("/api/logs").json()["entries"]
        lines = [e["line"] for e in entries]
        assert any("fake start" in line for line in lines)
        assert any(line.startswith("ERROR: unavailable: ") for line in lines)
        assert {e["title"] for e in entries} == {"Broken"}
        only = client.get("/api/logs", params={"item": entries[0]["item"]}).json()["entries"]
        assert len(only) == len(entries)
        assert client.get("/api/logs", params={"item": "nope"}).json()["entries"] == []


def test_log_lines_are_published_on_the_event_stream(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    sub = client.app.state.bus.subscribe()
    client.app.state.logs.add("hello", "id1", "Song")
    kind, data = sub._queue.get_nowait()
    assert kind == "log" and data["line"] == "hello" and data["item"] == "id1"


def test_logs_page_renders(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    assert "logsPage()" in client.get("/logs").text


def test_retry_failed_requeues_every_failed_item_and_only_those(settings, fake_runner):
    ids = ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    headers = csrf_header(client)
    client.post(
        "/api/submit/confirm", json={"items": [{"video_id": v} for v in ids]}, headers=headers
    )
    store = client.app.state.store
    state = store._state
    state.queue[0].status = "failed"
    state.queue[0].error = "private: Private video, upload cookies"
    state.queue[1].status = "failed"
    state.queue[1].attempts = 2
    sub = client.app.state.bus.subscribe()
    response = client.post("/api/queue/retry_failed", headers=headers)
    assert response.json() == {"requeued": 2}
    assert [i.status for i in store._state.queue] == ["queued"] * 3
    assert [i.error for i in store._state.queue] == [None] * 3
    assert [i.attempts for i in store._state.queue] == [0, 0, 0]
    kinds = []
    while not sub._queue.empty():
        kinds.append(sub._queue.get_nowait()[0])
    assert kinds.count("item") == 2
    assert client.post("/api/queue/retry_failed", headers=headers).json() == {"requeued": 0}


def test_retry_failed_requires_csrf(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    assert client.post("/api/queue/retry_failed").status_code == 403


def test_one_private_video_fails_with_a_cookie_hint_and_others_finish(settings, fake_runner):
    ids = ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]
    runner = fake_runner(scenarios={ids[1]: "error:private"})
    with TestClient(create_app(settings, runner=runner), follow_redirects=False) as client:
        login(client)
        headers = csrf_header(client)
        client.post(
            "/api/submit/confirm", json={"items": [{"video_id": v} for v in ids]}, headers=headers
        )
        store = client.app.state.store
        assert wait_for(lambda: all(i.status in ("done", "failed") for i in store._state.queue))
        by_id = {i.video_id: i for i in store._state.queue}
        assert by_id[ids[0]].status == by_id[ids[2]].status == "done"
        failed = by_id[ids[1]]
        assert failed.status == "failed"
        assert failed.error == "private: Private video, upload cookies: fake private error"


def test_password_and_cookie_path_in_runner_output_are_scrubbed(settings, fake_runner):
    from tests.conftest import PASSWORD

    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    cookies = str(client.app.state.download_ctx.cookies)
    client.app.state.logs.add(f"leak {PASSWORD} and {cookies}", "i", "T")
    text = str(client.app.state.logs.lines())
    assert PASSWORD not in text and cookies not in text


def _queue_of(client, statuses):
    ids = [f"{chr(97 + n) * 11}" for n in range(len(statuses))]
    headers = csrf_header(client)
    client.post(
        "/api/submit/confirm", json={"items": [{"video_id": v} for v in ids]}, headers=headers
    )
    for item, status in zip(client.app.state.store._state.queue, statuses, strict=True):
        item.status = status
    return headers


def test_dismiss_all_removes_done_and_failed_only(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    headers = _queue_of(client, ["done", "failed", "queued"])
    sub = client.app.state.bus.subscribe()
    assert client.post("/api/queue/dismiss_all", headers=headers).json() == {"dismissed": 2}
    assert [i.status for i in client.app.state.store._state.queue] == ["queued"]
    kinds = []
    while not sub._queue.empty():
        kinds.append(sub._queue.get_nowait()[0])
    assert kinds.count("removed") == 2


def test_cancel_all_drops_queued_and_keeps_finished(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    headers = _queue_of(client, ["done", "queued", "queued", "failed"])
    assert client.post("/api/queue/cancel_all", headers=headers).json() == {"cancelled": 2}
    assert [i.status for i in client.app.state.store._state.queue] == ["done", "failed"]


def test_bulk_queue_actions_require_csrf(settings, fake_runner):
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    assert client.post("/api/queue/cancel_all").status_code == 403
    assert client.post("/api/queue/dismiss_all").status_code == 403
