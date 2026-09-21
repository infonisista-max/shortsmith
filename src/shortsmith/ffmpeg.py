"""Thin subprocess wrappers around the local ffmpeg/ffprobe binaries.

Argv lists only, never a shell. FFmpeg is a local dependency (CLAUDE.md); the
binaries are resolved from PATH at call time so tests and smoke share one path.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shortsmith import subproc

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
MEASURE_TIMEOUT_S = 600.0


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


def video_md5(path: Path) -> str:
    """MD5 of the first video stream's packets, bit-exact (`-c copy`): equal for two
    files whose video was muxed without re-encoding (revision proof (a), 10.1)."""
    proc = run(
        [FFMPEG, "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"],
        timeout_s=MEASURE_TIMEOUT_S,
    )
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    if not text.startswith("MD5="):
        raise FFmpegError(f"unexpected md5 output {text!r}")
    return text[len("MD5=") :]


@dataclass(frozen=True)
class Loudness:
    """What `loudnorm` measures in its first pass (EBU R128): integrated loudness in
    LUFS, true peak in dBTP, loudness range in LU, the gate threshold and the offset
    `loudnorm` would apply to reach the target."""

    integrated: float
    true_peak: float
    lra: float
    threshold: float
    offset: float


def loudnorm_filter(*, target_lufs: float, target_tp: float, lra: float = 11.0) -> str:
    return f"loudnorm=I={target_lufs:g}:TP={target_tp:g}:LRA={lra:g}"


_LOUDNORM_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.DOTALL)


def parse_loudnorm(stderr: str) -> Loudness:
    """The JSON block `loudnorm=print_format=json` prints on stderr."""
    match = _LOUDNORM_JSON.search(stderr)
    if match is None:
        raise FFmpegError(f"no loudnorm measurement in ffmpeg output:\n{stderr[-2000:]}")
    data = json.loads(match.group(0))
    return Loudness(
        integrated=float(data["input_i"]),
        true_peak=float(data["input_tp"]),
        lra=float(data["input_lra"]),
        threshold=float(data["input_thresh"]),
        offset=float(data["target_offset"]),
    )


def measure_loudness(
    path: Path,
    *,
    prefilter: str = "",
    target_lufs: float = -14.0,
    target_tp: float = -1.5,
    filter_complex: str | None = None,
    label: str = "0:a",
) -> Loudness:
    """Measure the audio of `path` (after `prefilter`, or the `filter_complex` output
    labelled `label`) with a `loudnorm` analysis pass toward the given target."""
    measure = loudnorm_filter(target_lufs=target_lufs, target_tp=target_tp)
    measure += ":print_format=json"
    argv = [FFMPEG, "-v", "info", "-nostats", "-i", str(path)]
    if filter_complex is not None:
        chain = f"{prefilter}," if prefilter else ""
        argv += ["-filter_complex", f"{filter_complex};[{label}]{chain}{measure}[m]", "-map", "[m]"]
    else:
        chain = f"{prefilter}," if prefilter else ""
        argv += ["-map", "0:a:0", "-af", f"{chain}{measure}"]
    argv += ["-vn", "-f", "null", "-"]
    proc = run(argv, timeout_s=MEASURE_TIMEOUT_S)
    return parse_loudnorm(proc.stderr.decode("utf-8", errors="replace"))


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


def frames_rgb(
    path: Path, *, fps: float, width: int, duration_s: float | None = None
) -> list[tuple[int, int, bytes]]:
    """Decode frames at `fps` (the `fps` filter: t = 0, 1/fps, 2/fps, ...) scaled to
    `width` with an even height, the first `duration_s` seconds only when given, in one
    ffmpeg pass. Each frame is (width, height, packed RGB24)."""
    argv = [FFMPEG, "-v", "error", "-i", str(path)]
    if duration_s is not None:
        argv += ["-t", f"{duration_s:.3f}"]
    argv += ["-vf", f"fps={fps:g},scale={width}:-2", "-f", "image2pipe", "-c:v", "ppm", "-"]
    proc = run(argv, timeout_s=MEASURE_TIMEOUT_S)
    frames: list[tuple[int, int, bytes]] = []
    data, pos = proc.stdout, 0
    while pos < len(data):
        w, h, pixels, pos = _parse_ppm_at(data, pos)
        frames.append((w, h, pixels))
    return frames


def _parse_ppm(data: bytes) -> tuple[int, int, bytes]:
    width, height, pixels, _ = _parse_ppm_at(data, 0)
    return width, height, pixels


def _parse_ppm_at(data: bytes, pos: int) -> tuple[int, int, bytes, int]:
    # Binary PPM: "P6\n<w> <h>\n255\n<pixels>" ; ffmpeg writes no comments. Returns the
    # frame and the offset just past it, so concatenated PPMs from image2pipe parse too.
    fields: list[bytes] = []
    while len(fields) < 4:
        while data[pos : pos + 1].isspace():
            pos += 1
        start = pos
        while pos < len(data) and not data[pos : pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    pos += 1  # the single whitespace byte after maxval
    if fields[0] != b"P6" or fields[3] != b"255":
        raise FFmpegError(f"unexpected PPM header {fields!r}")
    width, height = int(fields[1]), int(fields[2])
    end = pos + width * height * 3
    pixels = data[pos:end]
    if len(pixels) != width * height * 3:
        raise FFmpegError("short PPM payload")
    return width, height, pixels, end
