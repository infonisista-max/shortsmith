"""Server-side input validation (decision 2.1) and the `input/` layout (decision 2.2).

The checks are pure functions over plain data so every threshold is boundary-tested
without HTTP or ffmpeg: `check_video`, `check_brief`, `check_references`. The probes
(`probe_video`, `probe_reference`) read that data with ffprobe/ffmpeg. `accept` runs
probes and checks first and only then creates the job, so a rejection never leaves a
job directory behind. A rejection is one plain sentence (`Rejected`).

`Limits` carries the 2.1 numbers as defaults. Smoke lowers only `min_duration_s`
because the 12.1 fixture is six seconds long; nothing else ever overrides a limit.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shortsmith import ffmpeg, jobs
from shortsmith.contracts import ReferenceRecord
from shortsmith.jobs import InputSummary, Job

TARGET_WIDTH, TARGET_HEIGHT = 1080, 1920
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
MIB = 1024 * 1024

ReferenceKind = Literal["image", "clip", "unknown"]


class Rejected(Exception):
    """The upload was refused; `str(exc)` is the one plain sentence for the page."""


@dataclass(frozen=True)
class Limits:
    min_duration_s: float = 20.0
    max_duration_s: float = 480.0
    min_mean_volume_db: float = -50.0
    max_upscale: float = 1.5
    brief_min_chars: int = 40
    brief_max_chars: int = 1500
    max_references: int = 8
    max_reference_bytes: int = 20 * MIB
    min_image_short_side: int = 600
    max_upload_bytes: int = 500 * MIB


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class VideoInfo:
    duration_s: float
    width: int
    height: int
    video_streams: int
    audio_streams: int
    mean_volume_db: float | None
    size_bytes: int
    extension: str


@dataclass(frozen=True)
class ReferenceInfo:
    original_name: str
    caption: str
    size_bytes: int
    width: int
    height: int
    kind: ReferenceKind


@dataclass(frozen=True)
class VideoUpload:
    path: Path
    original_name: str


@dataclass(frozen=True)
class ReferenceUpload:
    path: Path
    original_name: str
    caption: str = ""


# --- pure checks ----------------------------------------------------------------


def upscale_factor(width: int, height: int) -> float:
    """Scale needed to fill 1080x1920 from the largest 9:16 centre crop of the source."""
    crop_height = min(height, width * TARGET_HEIGHT / TARGET_WIDTH)
    return TARGET_HEIGHT / crop_height


def _duration_words(limits: Limits) -> str:
    lo = f"{limits.min_duration_s:g} seconds"
    hi_s = limits.max_duration_s
    hi = f"{hi_s / 60:g} minutes" if hi_s % 60 == 0 else f"{hi_s:g} seconds"
    return f"between {lo} and {hi}"


def check_video(info: VideoInfo, limits: Limits) -> str | None:
    """The 2.1 video rules in order; the first failure's sentence, else None."""
    if info.extension.lower() not in VIDEO_EXTENSIONS:
        return "The recording must be an mp4 or mov file."
    if info.size_bytes > limits.max_upload_bytes:
        return f"The recording must be {limits.max_upload_bytes // MIB} MB or smaller."
    if info.video_streams != 1 or info.audio_streams != 1:
        return "The recording needs exactly one video stream and one audio track."
    if not limits.min_duration_s <= info.duration_s <= limits.max_duration_s:
        return f"The recording must be {_duration_words(limits)} long."
    if info.mean_volume_db is None or info.mean_volume_db < limits.min_mean_volume_db:
        return "No speech found in the recording."
    if upscale_factor(info.width, info.height) > limits.max_upscale:
        return (
            f"Filling 9:16 from this recording would need more than a {limits.max_upscale:g}x "
            "upscale, so record vertical or in 4K."
        )
    return None


def video_warnings(info: VideoInfo) -> list[str]:
    """Non-blocking notes shown on the job page (2.1: any orientation is accepted)."""
    if info.width * TARGET_HEIGHT > info.height * TARGET_WIDTH:  # wider than 9:16
        shape = "landscape" if info.width > info.height else "not 9:16"
        return [
            f"Vertical works best for PIP; this recording is {shape}, "
            "so it will be centre-cropped."
        ]
    return []


def check_brief(brief: str, limits: Limits) -> str | None:
    if not limits.brief_min_chars <= len(brief.strip()) <= limits.brief_max_chars:
        return (
            f"The brief must be between {limits.brief_min_chars} and "
            f"{limits.brief_max_chars} characters."
        )
    return None


def check_references(refs: list[ReferenceInfo], limits: Limits) -> str | None:
    if len(refs) > limits.max_references:
        return f"At most {limits.max_references} reference files are allowed."
    for ref in refs:
        name = ref.original_name
        if ref.kind == "unknown":
            return f"Reference {name} must be a jpg, png, webp, mp4 or mov file."
        if ref.size_bytes > limits.max_reference_bytes:
            return f"Reference {name} must be {limits.max_reference_bytes // MIB} MB or smaller."
        if ref.kind == "image" and min(ref.width, ref.height) < limits.min_image_short_side:
            return (
                f"Reference {name} must be at least {limits.min_image_short_side} px "
                "on its short side."
            )
    return None


def reference_kind(name: str) -> ReferenceKind:
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "clip"
    return "unknown"


_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    stem = Path(name).stem.lower()
    cleaned = _NON_SLUG.sub("-", stem).strip("-")
    return cleaned[:60] or "ref"


# --- probes ---------------------------------------------------------------------


def probe_video(path: Path, *, original_name: str | None = None) -> VideoInfo:
    data = ffmpeg.probe(path)
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or (video[0].get("duration") if video else 0) or 0)
    width = int(video[0].get("width", 0)) if video else 0
    height = int(video[0].get("height", 0)) if video else 0
    volume = ffmpeg.mean_volume_db(path) if audio else None
    return VideoInfo(
        duration_s=duration,
        width=width,
        height=height,
        video_streams=len(video),
        audio_streams=len(audio),
        mean_volume_db=volume,
        size_bytes=path.stat().st_size,
        extension=Path(original_name or path.name).suffix,
    )


def probe_reference(path: Path, *, original_name: str, caption: str) -> ReferenceInfo:
    kind = reference_kind(original_name)
    width = height = 0
    if kind != "unknown":
        try:
            data = ffmpeg.probe(path)
        except ffmpeg.FFmpegError:
            kind = "unknown"
        else:
            video = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
            if video:
                width = int(video[0].get("width", 0))
                height = int(video[0].get("height", 0))
            else:
                kind = "unknown"
    return ReferenceInfo(
        original_name=original_name,
        caption=caption,
        size_bytes=path.stat().st_size,
        width=width,
        height=height,
        kind=kind,
    )


# --- accept ---------------------------------------------------------------------


def accept(
    data_dir: Path,
    *,
    video: VideoUpload,
    brief: str,
    style_line: str,
    references: list[ReferenceUpload],
    limits: Limits | None = None,
    now: jobs.Clock | None = None,
) -> Job:
    """Validate everything, then create the job and lay out `input/` per 2.2.

    Raises `Rejected` with the one plain sentence; no job directory exists then.
    """
    limits = limits or DEFAULT_LIMITS
    brief_problem = check_brief(brief, limits)
    if brief_problem:
        raise Rejected(brief_problem)
    if not video.path.is_file() or video.path.stat().st_size == 0:
        raise Rejected("Please choose a video file to upload.")
    info = probe_video(video.path, original_name=video.original_name)
    video_problem = check_video(info, limits)
    if video_problem:
        raise Rejected(video_problem)
    ref_infos = [
        probe_reference(r.path, original_name=r.original_name, caption=r.caption)
        for r in references
    ]
    ref_problem = check_references(ref_infos, limits)
    if ref_problem:
        raise Rejected(ref_problem)

    raw_name = "raw" + info.extension.lower()
    summary = InputSummary(
        file=raw_name,
        original_name=video.original_name,
        duration_s=info.duration_s,
        width=info.width,
        height=info.height,
        size_bytes=info.size_bytes,
        references=len(references),
    )
    kwargs = {"now": now} if now is not None else {}
    job = jobs.create(
        data_dir,
        style_line=style_line,
        input=summary,
        warnings=video_warnings(info),
        **kwargs,
    )
    shutil.copyfile(video.path, job.input_dir / raw_name)
    (job.input_dir / "brief.md").write_text(brief, encoding="utf-8")
    refs_dir = job.input_dir / "refs"
    refs_dir.mkdir(exist_ok=True)
    records: list[ReferenceRecord] = []
    for n, (upload, ref) in enumerate(zip(references, ref_infos, strict=True), start=1):
        ext = Path(upload.original_name).suffix.lower()
        rel = f"refs/{n}_{slug(upload.original_name)}{ext}"
        shutil.copyfile(upload.path, job.input_dir / rel)
        records.append(
            ReferenceRecord(
                id=f"ref{n}",
                file=rel,
                kind="clip" if ref.kind == "clip" else "image",
                caption=upload.caption,
                original_name=upload.original_name,
                width=ref.width,
                height=ref.height,
                size_bytes=ref.size_bytes,
            )
        )
    (job.input_dir / "refs.json").write_text(
        json.dumps([r.model_dump() for r in records], indent=2), encoding="utf-8"
    )
    return job
