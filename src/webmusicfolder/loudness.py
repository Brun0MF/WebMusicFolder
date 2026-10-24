"""Loudness measurement with ffmpeg and ReplayGain 2.0 values."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

# ReplayGain 2.0 reference level in LUFS.
REFERENCE_LUFS = -18.0
MEASURE_TIMEOUT_S = 120.0

_INTEGRATED = re.compile(r"^\s*I:\s+(-?\d+(?:\.\d+)?)\s+LUFS", re.MULTILINE)
_PEAK = re.compile(r"^\s*Peak:\s+(-?\d+(?:\.\d+)?|-inf)\s+dBFS", re.MULTILINE)


class LoudnessError(RuntimeError):
    """The file could not be measured."""


@dataclass(frozen=True)
class Loudness:
    # Integrated loudness in LUFS.
    lufs: float
    # Sample peak as a linear value, 1.0 is full scale.
    peak: float

    @property
    def gain_db(self) -> float:
        return REFERENCE_LUFS - self.lufs


def parse_summary(text: str) -> Loudness:
    """Read the `Summary:` block ebur128 prints at the end of the run."""
    summary = text.rsplit("Summary:", 1)[-1]
    integrated = _INTEGRATED.findall(summary)
    peak = _PEAK.findall(summary)
    if not integrated or not peak:
        raise LoudnessError("ffmpeg printed no loudness summary")
    lufs = float(integrated[-1])
    peak_db = peak[-1]
    return Loudness(lufs=lufs, peak=0.0 if peak_db == "-inf" else 10 ** (float(peak_db) / 20))


async def measure(path: Path, ffmpeg: str = "ffmpeg") -> Loudness:
    """Measure integrated loudness and sample peak; the file is only read."""
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=sample",
            "-f",
            "null",
            "-",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise LoudnessError(f"cannot run ffmpeg: {exc}") from exc
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), MEASURE_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise LoudnessError("loudness measurement timed out") from None
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        raise LoudnessError(f"ffmpeg exited with code {proc.returncode}")
    return parse_summary(stderr.decode("utf-8", "replace"))


def format_gain(gain_db: float) -> str:
    return f"{gain_db:.2f} dB"


def format_peak(peak: float) -> str:
    return f"{peak:.6f}"
