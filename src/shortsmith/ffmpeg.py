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
SAMPLE_RATE = 48000  # 7.3: every stem and the master are 48 kHz


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


def duration_s(path: Path) -> float:
    """The container duration in seconds."""
    return float(probe(path)["format"]["duration"])


def video_size(path: Path) -> tuple[int, int]:
    """(width, height) of the first video stream."""
    for stream in probe(path)["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise FFmpegError(f"{path.name} has no video stream")


def still(src: Path, dst: Path, *, at_s: float, vf: str = "") -> Path:
    """One frame of `src` at `at_s` through the filter `vf`, written as the image
    `dst`'s suffix names (the 013 strip stills). The seek sits before the input, so a
    still deep into an eight-minute recording costs a keyframe seek, not a decode."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    argv = [FFMPEG, "-v", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(src)]
    if vf:
        argv += ["-vf", vf]
    run([*argv, "-frames:v", "1", "-q:v", "2", str(dst)], timeout_s=MEASURE_TIMEOUT_S)
    return dst


# Research §6: both approved jobs fed Groq Whisper 16 kHz mono MP3 at 64 kbps.
SPEECH_RATE_HZ = 16000
SPEECH_BITRATE = "64k"


def extract_speech(src: Path, dst: Path, *, start_s: float = 0.0) -> Path:
    """The first audio stream of `src` from `start_s` to the end as the ASR's MP3."""
    seek = ["-ss", f"{start_s:.3f}"] if start_s > 0 else []
    run(
        [
            FFMPEG, "-y", "-v", "error", *seek, "-i", str(src),
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SPEECH_RATE_HZ),
            "-c:a", "libmp3lame", "-b:a", SPEECH_BITRATE, str(dst),
        ],
        timeout_s=MEASURE_TIMEOUT_S,
    )  # fmt: skip
    return dst


# Speech onset for the head-smear check: the end of a silence that starts the file.
ONSET_NOISE_DB = -35
ONSET_MIN_SILENCE_S = 0.3
_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def speech_onset_s(path: Path) -> float:
    """Seconds of silence (below -35 dB for at least 0.3 s) the audio opens with; 0.0
    when it opens with sound, or is silent throughout."""
    proc = run(
        [
            FFMPEG, "-v", "info", "-nostats", "-i", str(path), "-map", "0:a:0",
            "-af", f"silencedetect=noise={ONSET_NOISE_DB}dB:d={ONSET_MIN_SILENCE_S}",
            "-vn", "-f", "null", "-",
        ],
        timeout_s=MEASURE_TIMEOUT_S,
    )  # fmt: skip
    text = proc.stderr.decode("utf-8", errors="replace")
    start, end = _SILENCE_START.search(text), _SILENCE_END.search(text)
    if start is None or end is None or float(start.group(1)) > 0.01:
        return 0.0
    return round(float(end.group(1)), 3)


_MEAN_VOLUME = re.compile(r"mean_volume:\s*(-?[\d.]+|-inf)\s*dB")
_MAX_VOLUME = re.compile(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB")


def _volumedetect(path: Path, prefilter: str) -> str | None:
    chain = f"{prefilter},volumedetect" if prefilter else "volumedetect"
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
            chain,
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
    return proc.stderr.decode("utf-8", errors="replace")


def mean_volume_db(path: Path, *, prefilter: str = "") -> float | None:
    """RMS level of the first audio stream (after `prefilter`) via `volumedetect`; None
    when silent or absent."""
    text = _volumedetect(path, prefilter)
    if text is None:
        return None
    match = _MEAN_VOLUME.search(text)
    if match is None or match.group(1) == "-inf":
        return None
    return float(match.group(1))


def max_volume_db(path: Path, *, prefilter: str = "") -> float | None:
    """Peak level of the first audio stream (after `prefilter`); None when silent."""
    text = _volumedetect(path, prefilter)
    if text is None:
        return None
    match = _MAX_VOLUME.search(text)
    if match is None or match.group(1) == "-inf":
        return None
    return float(match.group(1))


_RMS_LEVEL = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-?inf|nan)")


def rms_windows_db(path: Path, *, window_s: float = 1.0) -> list[float]:
    """The RMS level of each `window_s` window of the first audio stream, in dB.

    `asetnsamples` makes one filter frame per window so `astats` resets on exactly that
    span; silent windows come back as -inf and are left out, so the median of the result
    is the median level of the audible signal (7.3)."""
    samples = max(1, round(window_s * SAMPLE_RATE))
    proc = run(
        [
            FFMPEG, "-v", "info", "-nostats", "-i", str(path), "-map", "0:a:0",
            "-af",
            f"asetnsamples=n={samples}:p=0,astats=metadata=1:reset=1,"
            "ametadata=print:key=lavfi.astats.Overall.RMS_level",
            "-vn", "-f", "null", "-",
        ],  # fmt: skip
        timeout_s=MEASURE_TIMEOUT_S,
    )
    text = proc.stderr.decode("utf-8", errors="replace")
    out: list[float] = []
    for match in _RMS_LEVEL.finditer(text):
        raw = match.group(1)
        if raw in ("-inf", "inf", "nan"):
            continue
        out.append(float(raw))
    return out


def pcm_f32(path: Path, *, rate: int = SAMPLE_RATE) -> bytes:
    """The first audio stream folded to mono and resampled to `rate`, as raw
    little-endian float32 samples: what the 023 detector and the catalogue measure read
    (ffmpeg decodes every format, numpy only measures)."""
    proc = run(
        [
            FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a:0",
            "-ac", "1", "-ar", str(rate), "-f", "f32le", "-c:a", "pcm_f32le", "-",
        ],  # fmt: skip
        timeout_s=MEASURE_TIMEOUT_S,
    )
    return proc.stdout


@dataclass(frozen=True)
class FrameStat:
    """One decoded frame of the first video stream (gate T7, 031): its index, its mean
    luma on the full 0-255 range and the MD5 of its pixels."""

    index: int
    luma: float
    hash: str


LIMITED_BLACK, LIMITED_WHITE = 16.0, 235.0


def luma_full(yavg: float, *, full_range: bool = False) -> float:
    """A `signalstats` YAVG on the full 0-255 range: limited-range video (the default
    for H.264 4:2:0, and what `color_range=unknown` decodes as) puts black at Y=16 and
    white at Y=235, so 12/255 in 10.1 is read after that mapping, never on raw Y."""
    if full_range:
        return yavg
    scaled = (yavg - LIMITED_BLACK) * 255.0 / (LIMITED_WHITE - LIMITED_BLACK)
    return min(255.0, max(0.0, scaled))


_YAVG = re.compile(r"lavfi\.signalstats\.YAVG=(-?[\d.]+)")


def frame_stats(path: Path, *, full_range: bool = False) -> list[FrameStat]:
    """Every frame's mean luma and pixel hash in one decode: `signalstats` prints YAVG
    per frame to the log, the `framehash` muxer writes one MD5 line per frame to
    stdout. The video stream alone is mapped, so no audio frame is hashed."""
    proc = run(
        [
            FFMPEG, "-v", "info", "-nostats", "-i", str(path), "-map", "0:v:0", "-an",
            "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
            "-f", "framehash", "-hash", "md5", "-",
        ],  # fmt: skip
        timeout_s=MEASURE_TIMEOUT_S,
    )
    lumas = [float(m.group(1)) for m in _YAVG.finditer(proc.stderr.decode("utf-8", "replace"))]
    hashes = [
        line.rsplit(",", 1)[1].strip()
        for line in proc.stdout.decode("utf-8", errors="replace").splitlines()
        if line and not line.startswith("#")
    ]
    if len(lumas) != len(hashes):
        raise FFmpegError(f"{len(lumas)} luma readings for {len(hashes)} frame hashes")
    return [
        FrameStat(index=i, luma=luma_full(y, full_range=full_range), hash=h)
        for i, (y, h) in enumerate(zip(lumas, hashes, strict=True))
    ]


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
