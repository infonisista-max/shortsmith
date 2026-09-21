"""Thin subprocess wrappers around the local ffmpeg/ffprobe binaries.

Argv lists only, never a shell. FFmpeg is a local dependency (CLAUDE.md); the
binaries are resolved from PATH at call time so tests and smoke share one path.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from shortsmith import subproc

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


class FFmpegError(RuntimeError):
    """ffmpeg or ffprobe exited non-zero; the message carries the stderr tail."""


def run(argv: list[str], *, timeout_s: float = 120.0) -> subprocess.CompletedProcess[bytes]:
    """Runs through `subproc.run`, so a job's watchdog can kill it (11.2)."""
    proc = subproc.run(argv, timeout_s=timeout_s)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace")[-4000:]
        raise FFmpegError(f"{argv[0]} exited {proc.returncode}:\n{tail}")
    return proc


def probe(path: Path) -> dict[str, Any]:
    """ffprobe -show_streams -show_format as a dict."""
    proc = run(
        [
            FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
    return json.loads(proc.stdout.decode("utf-8"))


_MEAN_VOLUME = re.compile(r"mean_volume:\s*(-?[\d.]+|-inf)\s*dB")


def mean_volume_db(path: Path) -> float | None:
    """Mean volume of the first audio stream via `volumedetect`; None when silent or absent."""
    proc = subprocess.run(
        [
            FFMPEG,
            "-v",
            "info",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-vn",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        timeout=600,
    )
    if proc.returncode != 0:
        return None
    match = _MEAN_VOLUME.search(proc.stderr.decode("utf-8", errors="replace"))
    if match is None or match.group(1) == "-inf":
        return None
    return float(match.group(1))


def frame_rgb(path: Path, *, at_s: float) -> tuple[int, int, bytes]:
    """Decode one frame at `at_s` as packed RGB24. Returns (width, height, pixels)."""
    proc = run(
        [
            FFMPEG,
            "-v",
            "error",
            "-ss",
            f"{at_s:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "ppm",
            "-",
        ]
    )
    return _parse_ppm(proc.stdout)


def _parse_ppm(data: bytes) -> tuple[int, int, bytes]:
    # Binary PPM: "P6\n<w> <h>\n255\n<pixels>" ; ffmpeg writes no comments.
    fields: list[bytes] = []
    pos = 0
    while len(fields) < 4:
        while data[pos : pos + 1].isspace():
            pos += 1
        start = pos
        while not data[pos : pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    pos += 1  # the single whitespace byte after maxval
    if fields[0] != b"P6" or fields[3] != b"255":
        raise FFmpegError(f"unexpected PPM header {fields!r}")
    width, height = int(fields[1]), int(fields[2])
    pixels = data[pos : pos + width * height * 3]
    if len(pixels) != width * height * 3:
        raise FFmpegError("short PPM payload")
    return width, height, pixels
