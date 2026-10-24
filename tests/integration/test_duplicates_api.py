import time

import pytest
from fastapi.testclient import TestClient
from tests.conftest import login
from tests.integration.test_submit import csrf_header

from webmusicfolder.main import create_app

ID = "aaaaaaaaaaa"
URL = f"https://www.youtube.com/watch?v={ID}"


@pytest.fixture
def running(settings, fake_runner):
    app = create_app(settings, runner=fake_runner(titles={ID: "Known"}))
    with TestClient(app, follow_redirects=False) as client:
        assert login(client).status_code == 303
        yield client, csrf_header(client), settings


def wait_for(predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("timeout")


def download_once(client, headers, settings, subfolder="geek"):
    client.post(
        "/api/submit/confirm",
        json={"subfolder": subfolder, "items": [{"video_id": ID}]},
        headers=headers,
    )
    wait_for(lambda: (settings.music_dir / subfolder / "Known.mp3").is_file())
    wait_for(lambda: client.app.state.store._state.queue[-1].status == "done")


def preview(client, headers):
    return client.post(
        "/api/submit/preview", json={"links": URL, "subfolder": ""}, headers=headers
    ).json()


def test_known_link_is_reported_with_its_path(running):
    client, headers, settings = running
    assert preview(client, headers)["duplicates"] == []
    download_once(client, headers, settings)
    dup = preview(client, headers)["duplicates"]
    assert [(d["video_id"], d["kind"], d["path"]) for d in dup] == [
        (ID, "exists", "geek/Known.mp3")
    ]


def test_skip_adds_nothing_and_redownload_adds_one_in_the_original_folder(running):
    client, headers, settings = running
    download_once(client, headers, settings)
    skipped = client.post(
        "/api/submit/confirm",
        json={"subfolder": "other", "items": [{"video_id": ID}]},
        headers=headers,
    )
    assert skipped.json() == {"queued": 0, "ignored": 1}
    again = client.post(
        "/api/submit/confirm",
        json={"subfolder": "other", "items": [{"video_id": ID, "overwrite": True}]},
        headers=headers,
    )
    assert again.json()["queued"] == 1
    item = client.app.state.store._state.queue[-1]
    assert item.overwrite and item.subfolder == "geek"
    wait_for(lambda: client.app.state.store._state.queue[-1].status == "done")
    assert not (settings.music_dir / "other").exists()
    assert [p.name for p in (settings.music_dir / "geek").iterdir()] == ["Known.mp3"]


def test_deleted_file_is_new_again(running):
    client, headers, settings = running
    download_once(client, headers, settings)
    (settings.music_dir / "geek" / "Known.mp3").unlink()
    assert preview(client, headers)["duplicates"] == []
    r = client.post(
        "/api/submit/confirm",
        json={"subfolder": "geek", "items": [{"video_id": ID}]},
        headers=headers,
    )
    assert r.json()["queued"] == 1


def test_queued_item_is_reported_as_in_queue(settings, fake_runner):
    # Without a lifespan the worker never starts, so the item stays queued.
    app = create_app(settings, runner=fake_runner())
    client = TestClient(app, follow_redirects=False)
    login(client)
    headers = csrf_header(client)
    client.post("/api/submit/confirm", json={"items": [{"video_id": ID}]}, headers=headers)
    dup = preview(client, headers)["duplicates"]
    assert [(d["video_id"], d["kind"]) for d in dup] == [(ID, "queued")]


def test_external_file_never_triggers_the_dialog(settings, fake_runner, make_mp3):
    make_mp3(settings.music_dir / "Known.mp3", title="Known", video_id=ID)
    client = TestClient(create_app(settings, runner=fake_runner()), follow_redirects=False)
    login(client)
    assert preview(client, csrf_header(client))["duplicates"] == []
