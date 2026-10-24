import json

import pytest

from webmusicfolder.models import AppSettings, QueueItem, State, Track


def _full_state() -> State:
    track = Track(
        video_id="abc",
        url="https://youtu.be/abc",
        title="Título ç",
        artist="Chan",
        duration_s=213,
        subfolder="geek",
        relpath="geek/Título ç.mp3",
        downloaded_at="2026-10-24T12:00:00Z",
        quality="v0",
    )
    item = QueueItem(
        id="1",
        video_id="abc",
        url="https://youtu.be/abc",
        title="t",
        subfolder="geek",
        added_at="2026-10-24T11:59:00Z",
        status="failed",
        attempts=2,
        error="boom",
        overwrite=True,
        finished_at="2026-10-24T12:01:00Z",
    )
    return State(
        settings=AppSettings(quality="320k", concurrency=2), tracks={"abc": track}, queue=[item]
    )


def test_round_trip_through_json():
    state = _full_state()
    text = json.dumps(state.to_dict())
    assert State.from_dict(json.loads(text)) == state


def test_empty_state_round_trip():
    assert State.from_dict(State().to_dict()) == State()


def test_unknown_keys_are_ignored():
    data = State().to_dict()
    data["settings"]["future_flag"] = True
    data["extra"] = 1
    assert State.from_dict(data) == State()


def test_missing_optional_sections_use_defaults():
    assert State.from_dict({"version": 1}) == State()


def test_missing_version_is_an_error():
    with pytest.raises(KeyError):
        State.from_dict({})


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"version": 1, "tracks": []},
        {"version": 1, "queue": {}},
        {"version": 1, "queue": [{"id": "1"}]},
        {"version": 1, "queue": ["x"]},
        {"version": 1, "tracks": {"a": {"video_id": "a"}}},
    ],
)
def test_malformed_input_raises(bad):
    with pytest.raises((ValueError, TypeError, KeyError)):
        State.from_dict(bad)


def test_invalid_queue_status_rejected():
    data = _full_state().to_dict()
    data["queue"][0]["status"] = "weird"
    with pytest.raises(ValueError):
        State.from_dict(data)
