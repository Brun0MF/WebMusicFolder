import asyncio

import pytest

from webmusicfolder import errors
from webmusicfolder.errors import DownloadError
from webmusicfolder.runner_client import run_download, run_runner

URL = "https://www.youtube.com/watch?v={}"


async def test_success_returns_result_and_streams_events(fake_runner, tmp_path):
    events, logs = [], []
    result = await run_download(
        fake_runner(titles={"okAAAAAAAAA": "My Song"}),
        URL.format("okAAAAAAAAA"),
        tmp_path / "t",
        "v0",
        on_event=events.append,
        on_log=logs.append,
    )
    assert result.video_id == "okAAAAAAAAA"
    assert result.title == "My Song"
    assert result.path.is_file() and result.cover and result.cover.is_file()
    assert [e["type"] for e in events][:2] == ["log", "progress"]
    assert any("fake start" in line for line in logs)


@pytest.mark.parametrize("code", errors.ERROR_CODES)
async def test_error_event_maps_to_code(fake_runner, tmp_path, code):
    vid = "errAAAAAAAA"
    spec = fake_runner(scenarios={vid: f"error:{code}"})
    with pytest.raises(DownloadError) as exc:
        await run_download(spec, URL.format(vid), tmp_path / "t", "v0")
    assert exc.value.code == code


async def test_crash_without_event_uses_stderr_tail(fake_runner, tmp_path):
    vid = "crashAAAAAA"
    spec = fake_runner(scenarios={vid: "crash"})
    with pytest.raises(DownloadError) as exc:
        await run_download(spec, URL.format(vid), tmp_path / "t", "v0")
    assert "boom" in exc.value.message
    assert exc.value.code == errors.CODE_UNKNOWN


async def test_hang_is_killed_after_idle_timeout(fake_runner, tmp_path):
    vid = "hangAAAAAAA"
    spec = fake_runner(scenarios={vid: "hang"}, idle_timeout_s=0.5)
    with pytest.raises(DownloadError) as exc:
        await run_download(spec, URL.format(vid), tmp_path / "t", "v0")
    assert exc.value.retryable


async def test_cancel_kills_the_process(fake_runner, tmp_path):
    vid = "hangAAAAAAA"
    spec = fake_runner(scenarios={vid: "hang"})
    task = asyncio.create_task(run_download(spec, URL.format(vid), tmp_path / "t", "v0"))
    marker = fake_runner.state_dir / f"start_{vid}"
    for _ in range(100):
        if marker.exists():
            break
        await asyncio.sleep(0.05)
    pid = int(marker.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(100):
        try:
            import os

            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    pytest.fail("runner process still alive after cancel")


async def test_flat_mode_events(fake_runner):
    flat = {"u": [{"id": "a" * 11, "title": "A"}, {"id": "b" * 11, "skip": "private"}]}
    events = []
    done = await run_runner(fake_runner(flat=flat), ["flat", "u"], events.append)
    assert done["count"] == 1
    assert [e["type"] for e in events] == ["entry", "skipped", "done"]


def test_classify_error_samples():
    cases = {
        "ERROR: [youtube] x: Private video. Sign in if you've been granted access": "private",
        "ERROR: [youtube] x: Video unavailable": "unavailable",
        "ERROR: [youtube] x: This video is unavailable": "unavailable",
        "Sign in to confirm your age. This video may be inappropriate": "age_restricted",
        "Unable to download webpage: <urlopen error [Errno -3] Temporary failure>": "network",
        "ERROR: Postprocessing: ffmpeg not found": "ffmpeg",
        "[Errno 28] No space left on device": "disk_full",
        "[Errno 13] Permission denied: '/music/x'": "permission",
        "something odd": "unknown",
    }
    for text, code in cases.items():
        assert errors.classify_error(text) == code, text


async def test_real_runner_reports_the_installed_yt_dlp_version():
    from yt_dlp.version import __version__

    from webmusicfolder.runner_client import RunnerSpec, run_runner

    done = await run_runner(RunnerSpec(), ["version"])
    assert done["version"] == __version__


def test_runner_logger_does_not_double_the_error_prefix():
    import io
    import json

    from webmusicfolder.ytdlp_runner import Emitter, _Logger

    out = io.StringIO()
    logger = _Logger(Emitter(out))
    logger.error("ERROR: [youtube] x: gone")
    logger.error("plain failure")
    lines = [json.loads(line)["line"] for line in out.getvalue().splitlines()]
    assert lines == ["ERROR: [youtube] x: gone", "ERROR: plain failure"]


def test_download_args_only_carry_sponsorblock_when_enabled(tmp_path):
    from webmusicfolder.runner_client import build_download_args

    base = build_download_args("u", tmp_path, "v0", None)
    assert "--sponsorblock" not in base
    assert build_download_args("u", tmp_path, "v0", None, True) == [*base, "--sponsorblock"]


def test_cookie_args_precedence(tmp_path):
    from webmusicfolder.runner_client import cookie_args

    present = tmp_path / "c.txt"
    present.write_text("x")
    assert cookie_args(None, None) == []
    assert cookie_args(tmp_path / "missing.txt", None) == []
    assert cookie_args(tmp_path / "missing.txt", "firefox") == ["--cookies-from-browser", "firefox"]
    assert cookie_args(present, "firefox") == ["--cookies", str(present)]
