import json
from pathlib import Path

import pytest

from webmusicfolder.errors import ERROR_CODES, USER_MESSAGES, DownloadError, classify_error

SAMPLES = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "ytdlp_errors.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s["message"][:50])
def test_real_yt_dlp_messages_map_to_the_expected_code(sample):
    assert classify_error(sample["message"]) == sample["code"]


def test_every_code_has_a_user_message():
    assert set(USER_MESSAGES) == set(ERROR_CODES)


def test_private_video_message_asks_for_cookies():
    assert USER_MESSAGES["private"] == "Private video, upload cookies"


def test_only_network_errors_are_retryable():
    assert DownloadError("network", "x").retryable
    assert not DownloadError("login", "x").retryable
    assert DownloadError("bogus", "x").code == "unknown"


def test_format_error_puts_the_readable_message_before_the_raw_text():
    from webmusicfolder.queue_worker import format_error

    assert format_error("private", "fake raw") == "private: Private video, upload cookies: fake raw"
    # The runner already prefixes the readable message; it is not repeated.
    already = "Private video, upload cookies: ERROR: [youtube] x: Private video"
    assert format_error("private", already) == f"private: {already}"
    assert format_error("disk_full", "") == "disk_full: Disk full"
