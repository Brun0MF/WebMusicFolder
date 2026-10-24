"""Update yt-dlp into the data volume so a YouTube breakage does not need a new image."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import sys
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

from webmusicfolder.errors import DownloadError
from webmusicfolder.runner_client import RunnerSpec, run_runner

PIP_TIMEOUT_S = 300.0
STDERR_TAIL_LINES = 8
PACKAGE_DIR_NAME = "ytdlp_pkg"


class UpdateError(Exception):
    """The update failed; the previous version is still in place."""


class UpdateBusyError(UpdateError):
    """Another update is already running."""


@dataclass(frozen=True)
class UpdateResult:
    old: str
    new: str

    @property
    def changed(self) -> bool:
        return self.old != self.new


def package_dir_for(data_dir: Path) -> Path:
    return data_dir / PACKAGE_DIR_NAME


def default_pip_cmd() -> tuple[str, ...]:
    return (sys.executable, "-m", "pip")


class YtdlpUpdater:
    """Installs into a temp directory, checks it, then swaps it into place."""

    def __init__(
        self,
        package_dir: Path,
        runner: RunnerSpec,
        pip_cmd: tuple[str, ...] | None = None,
        pip_env: dict[str, str] | None = None,
        timeout_s: float = PIP_TIMEOUT_S,
    ) -> None:
        self.package_dir = package_dir
        self._runner = runner
        self._pip_cmd = pip_cmd or default_pip_cmd()
        self._pip_env = pip_env or {}
        self._timeout_s = timeout_s
        self._lock = asyncio.Lock()
        self._version: str | None = None
        self.recover()

    @property
    def updating(self) -> bool:
        return self._lock.locked()

    @property
    def _staging(self) -> Path:
        return self.package_dir.with_name(f"{self.package_dir.name}.new")

    @property
    def _previous(self) -> Path:
        return self.package_dir.with_name(f"{self.package_dir.name}.old")

    def recover(self) -> None:
        """Finish or undo a swap that a crash interrupted, and drop leftovers."""
        if not self.package_dir.exists() and self._previous.exists():
            os.replace(self._previous, self.package_dir)
        shutil.rmtree(self._staging, ignore_errors=True)
        shutil.rmtree(self._previous, ignore_errors=True)

    async def version(self, refresh: bool = False) -> str:
        """The yt-dlp version the runner will use; cached until the next update."""
        if self._version is None or refresh:
            self._version = await self._query_version(self._runner)
        return self._version

    async def _query_version(self, spec: RunnerSpec) -> str:
        try:
            done = await run_runner(spec, ["version"])
        except DownloadError as exc:
            raise UpdateError(f"Cannot read the yt-dlp version: {exc.message}") from exc
        version = str(done.get("version") or "")
        if not version:
            raise UpdateError("Cannot read the yt-dlp version: empty answer")
        return version

    async def update(self) -> UpdateResult:
        """Install the latest yt-dlp. Raises UpdateError and keeps the old version on failure."""
        if self._lock.locked():
            raise UpdateBusyError("An update is already running")
        async with self._lock:
            old = await self.version(refresh=True)
            staging = self._staging
            shutil.rmtree(staging, ignore_errors=True)
            try:
                await self._pip_install(staging)
                # Prove the new package imports before it replaces the working one.
                candidate = replace(self._runner, extra_pythonpath=staging)
                await self._query_version(candidate)
                self._swap(staging)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            self._version = None
            return UpdateResult(old=old, new=await self.version())

    def _swap(self, staging: Path) -> None:
        """Replace the package directory with two renames; a crash in between is recovered."""
        had_old = self.package_dir.exists()
        if had_old:
            shutil.rmtree(self._previous, ignore_errors=True)
            os.replace(self.package_dir, self._previous)
        try:
            os.replace(staging, self.package_dir)
        except OSError as exc:
            if had_old:
                os.replace(self._previous, self.package_dir)
            raise UpdateError(f"Cannot install the update: {exc}") from exc
        shutil.rmtree(self._previous, ignore_errors=True)

    async def _pip_install(self, target: Path) -> None:
        self.package_dir.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            *self._pip_cmd,
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            "--no-input",
            "--no-cache-dir",
            "--target",
            str(target),
            "yt-dlp[default]",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self._pip_env},
            start_new_session=True,
        )
        assert proc.stderr is not None
        tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)

        async def drain() -> None:
            async for raw in proc.stderr:  # type: ignore[union-attr]
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    tail.append(line)

        drainer = asyncio.create_task(drain())
        try:
            await asyncio.wait_for(proc.wait(), self._timeout_s)
            await drainer
        except TimeoutError:
            _kill(proc)
            await proc.wait()
            raise UpdateError(f"pip timed out after {self._timeout_s:.0f}s") from None
        except BaseException:
            _kill(proc)
            drainer.cancel()
            raise
        if proc.returncode != 0:
            detail = " | ".join(tail) or f"pip exited with code {proc.returncode}"
            raise UpdateError(f"pip failed: {detail[:400]}")
        if not target.is_dir():
            raise UpdateError("pip finished but installed nothing")


def _kill(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
