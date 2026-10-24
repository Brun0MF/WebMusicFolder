import shutil
import subprocess

import pytest

from webmusicfolder import loudness, tagging

SAMPLE_OUTPUT = """
[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -23.4 LUFS
    Threshold: -33.5 LUFS

  Loudness range:
    LRA:         3.0 LU

  Sample peak:
    Peak:       -6.0 dBFS
"""


def test_parse_summary_and_gain():
    result = loudness.parse_summary(SAMPLE_OUTPUT)
    assert result.lufs == -23.4
    assert result.gain_db == pytest.approx(5.4)
    assert result.peak == pytest.approx(0.501187, abs=1e-5)


def test_parse_summary_silence_has_zero_peak():
    text = "Summary:\n I: -70.0 LUFS\n Peak: -inf dBFS\n"
    assert loudness.parse_summary(text).peak == 0.0


def test_parse_summary_rejects_garbage():
    with pytest.raises(loudness.LoudnessError):
        loudness.parse_summary("nothing useful")


def test_formats():
    assert loudness.format_gain(-3.2149) == "-3.21 dB"
    assert loudness.format_peak(0.98765432) == "0.987654"


@pytest.fixture
def tone(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    path = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
         "-af", "volume=-20dB", "-codec:a", "libmp3lame", "-q:a", "2", str(path)],
        check=True,
    )  # fmt: skip
    return path


async def test_measure_known_tone(tone):
    result = await loudness.measure(tone)
    # ffmpeg's sine peaks at -18 dBFS, minus 20 dB: -38 dBFS. A sine reads 3 dB lower in LUFS.
    assert result.lufs == pytest.approx(-41.0, abs=1.0)
    assert result.gain_db == pytest.approx(23.0, abs=1.0)
    assert result.peak == pytest.approx(10 ** (-38 / 20), rel=0.1)


async def test_measure_failure_raises(tmp_path):
    with pytest.raises(loudness.LoudnessError):
        await loudness.measure(tmp_path / "missing.mp3")
    with pytest.raises(loudness.LoudnessError):
        await loudness.measure(tmp_path / "x.mp3", ffmpeg="/nonexistent/ffmpeg")


def test_write_tags_adds_replaygain_and_keeps_the_rest(sample_mp3, tmp_path):
    path = tmp_path / "a.mp3"
    shutil.copy(sample_mp3, path)
    tagging.write_tags(path, "T", "A", "abcdefghijk", "u", b"\xff\xd8x", ("-3.21 dB", "0.5"))
    tags = tagging.ID3(path)
    assert str(tags["TXXX:REPLAYGAIN_TRACK_GAIN"].text[0]) == "-3.21 dB"
    assert str(tags["TXXX:REPLAYGAIN_TRACK_PEAK"].text[0]) == "0.5"
    info = tagging.read_tags(path)
    assert (info.title, info.artist, info.video_id, info.has_cover) == (
        "T",
        "A",
        "abcdefghijk",
        True,
    )
    # Writing again without values removes stale ones.
    tagging.write_tags(path, "T", "A", "abcdefghijk", "u")
    assert "TXXX:REPLAYGAIN_TRACK_GAIN" not in tagging.ID3(path)
