import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webmusicfolder.config import Settings
from webmusicfolder.main import create_app

PASSWORD = "correct horse"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        password=PASSWORD,
        music_dir=tmp_path / "music",
        data_dir=tmp_path / "data",
        port=8080,
        secret=None,
        concurrency=1,
        quality="v0",
        puid=1000,
        pgid=1000,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), follow_redirects=False)


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no csrf token in page"
    return match.group(1)


def login(client: TestClient, password: str = PASSWORD):
    token = extract_csrf(client.get("/login").text)
    return client.post("/login", data={"password": password, "csrf_token": token})


FAKE_RUNNER = Path(__file__).parent / "fixtures" / "fake_runner.py"


@pytest.fixture(scope="session")
def sample_mp3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real one second MP3 generated with ffmpeg."""
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("media") / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "5",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def fake_runner(tmp_path: Path, sample_mp3: Path):
    """Factory for a RunnerSpec running the fake script with scripted scenarios."""
    import json
    import sys

    from webmusicfolder.runner_client import RunnerSpec

    state_dir = tmp_path / "fake_state"
    state_dir.mkdir()

    def make(scenarios=None, titles=None, flat=None, search=None, **spec_kwargs) -> RunnerSpec:
        env = {
            "FAKE_SCENARIOS": json.dumps(scenarios or {}),
            "FAKE_TITLES": json.dumps(titles or {}),
            "FAKE_FLAT": json.dumps(flat or {}),
            "FAKE_SEARCH": json.dumps(search or {}),
            "FAKE_MP3": str(sample_mp3),
            "FAKE_STATE_DIR": str(state_dir),
        }
        return RunnerSpec(cmd=(sys.executable, str(FAKE_RUNNER)), env=env, **spec_kwargs)

    make.state_dir = state_dir
    return make


@pytest.fixture
def make_mp3(sample_mp3: Path):
    """Factory copying the sample MP3 to dest, optionally tagged like the app (or not)."""
    import shutil

    from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TXXX

    def make(dest: Path, title=None, artist=None, album=None, video_id=None, cover=None) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(sample_mp3, dest)
        tags = ID3()
        if title:
            tags.add(TIT2(encoding=3, text=title))
        if artist:
            tags.add(TPE1(encoding=3, text=artist))
        if album:
            tags.add(TALB(encoding=3, text=album))
        if video_id:
            tags.add(TXXX(encoding=3, desc="youtube_id", text=video_id))
        if cover:
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="c", data=cover))
        if tags:
            tags.save(dest, v2_version=4)
        return dest

    return make


FAKE_PIP = Path(__file__).parent / "fixtures" / "fake_pip.py"


@pytest.fixture
def make_updater(tmp_path: Path, fake_runner):
    """Factory for a YtdlpUpdater wired to the fake runner and the fake pip script."""
    import sys

    from webmusicfolder.ytdlp_update import YtdlpUpdater

    package_dir = tmp_path / "data" / "ytdlp_pkg"

    def make(pip: str = "ok:2099.01.01", **kwargs) -> YtdlpUpdater:
        runner = fake_runner(extra_pythonpath=package_dir)
        return YtdlpUpdater(
            package_dir,
            runner,
            pip_cmd=(sys.executable, str(FAKE_PIP)),
            pip_env={"FAKE_PIP": pip},
            **kwargs,
        )

    make.package_dir = package_dir
    return make
