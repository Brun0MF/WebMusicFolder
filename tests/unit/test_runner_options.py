from pathlib import Path

from webmusicfolder import ytdlp_runner as runner


class _Sink:
    def write(self, _text):
        pass

    def flush(self):
        pass


EM = runner.Emitter(_Sink())


def keys(options):
    return [pp["key"] for pp in options["postprocessors"]]


def test_default_options_have_no_sponsorblock():
    options = runner.build_options(Path("/t"), "v0", None, EM)
    assert keys(options) == ["FFmpegExtractAudio", "FFmpegThumbnailsConvertor"]


def test_sponsorblock_order_and_categories():
    options = runner.build_options(Path("/t"), "v0", None, EM, sponsorblock=True)
    assert keys(options) == [
        "SponsorBlock",
        "FFmpegExtractAudio",
        "FFmpegThumbnailsConvertor",
        "ModifyChapters",
    ]
    cats = options["postprocessors"][0]["categories"]
    assert cats == runner.SPONSORBLOCK_CATEGORIES
    assert "intro" not in cats and "outro" not in cats
    assert options["postprocessors"][-1]["remove_sponsor_segments"] == cats


def test_sponsorblock_options_are_accepted_by_yt_dlp():
    import yt_dlp

    options = runner.build_options(Path("/t"), "v0", None, EM, sponsorblock=True)
    with yt_dlp.YoutubeDL(options) as ydl:
        assert ydl is not None


def test_mp3_duration(sample_mp3):
    assert runner.mp3_duration_s(sample_mp3) == 1
    assert runner.mp3_duration_s(Path("/nonexistent.mp3")) is None


class _Lines:
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)

    def flush(self):
        pass


def _fake_extract(tmp_path, calls, fail_with=None):
    def extract(_url, options):
        calls.append(any(pp["key"] == "SponsorBlock" for pp in options["postprocessors"]))
        if fail_with and calls[-1]:
            raise RuntimeError(fail_with)
        (tmp_path / "abcdefghijk.mp3").write_bytes(b"x")
        return {"id": "abcdefghijk", "title": "T", "duration": 99}

    return extract


def test_sponsorblock_outage_falls_back_to_a_plain_download(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        runner,
        "_extract",
        _fake_extract(tmp_path, calls, "Unable to communicate with SponsorBlock"),
    )
    sink = _Lines()
    runner.run_download("u", tmp_path, "v0", None, runner.Emitter(sink), sponsorblock=True)
    assert calls == [True, False]
    assert "SponsorBlock failed" in "".join(sink.lines)
    # The cut did not happen, so the duration comes from yt-dlp, not from the file.
    assert '"duration_s": 99' in "".join(sink.lines)


def test_other_errors_are_not_retried(tmp_path, monkeypatch):
    import pytest

    calls = []
    monkeypatch.setattr(runner, "_extract", _fake_extract(tmp_path, calls, "Video unavailable"))
    with pytest.raises(RuntimeError):
        runner.run_download("u", tmp_path, "v0", None, runner.Emitter(_Lines()), sponsorblock=True)
    assert calls == [True]


def test_apply_cookies_precedence():
    options = {}
    runner.apply_cookies(options, None, None)
    assert options == {}
    runner.apply_cookies(options, None, "firefox:work")
    assert options == {"cookiesfrombrowser": ("firefox", "work")}
    both = {}
    runner.apply_cookies(both, Path("/c.txt"), "firefox")
    assert both == {"cookiefile": "/c.txt"}
    plain = {}
    runner.apply_cookies(plain, None, "chrome")
    assert plain == {"cookiesfrombrowser": ("chrome", None)}


def test_browser_option_is_accepted_by_yt_dlp():
    import yt_dlp

    options = runner.build_options(Path("/t"), "v0", None, EM, browser="firefox:x")
    # Constructing the object parses the option; reading the browser happens lazily.
    assert options["cookiesfrombrowser"] == ("firefox", "x")
    assert yt_dlp.YoutubeDL is not None
