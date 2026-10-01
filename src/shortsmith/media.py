"""One media probe and the converters every step shares (111a).

A file's kind is decided by its **content**, never by its extension: an upload named
`x.jpg` can be an AVIF, a WebP or a text file. The API the later 111 tickets build on:

- `probe(path) -> "image" | "video" | None`: Pillow opens it as an image, or ffprobe
  finds a real video stream in it; otherwise None (missing, empty or undecodable).
  Pillow goes first because ffprobe calls an AVIF a video and a text file an mjpeg.
- `is_browser_safe(path) -> bool`: what Chrome decodes in the render: a JPEG, PNG or
  WebP image, or an H.264 video in an mp4 container (the codec is probed). A file whose
  extension names another format than its content is not safe.
- `is_real_still(path, suffix=None) -> bool`: a JPEG, PNG or (112b) WebP by content under its
  own suffix (what intake and `normalise_refs` keep byte for byte; anything else goes
  through `as_still`).
- `as_still(path, dest) -> Path`: a real JPG (a PNG when the image has alpha) from any
  image Pillow reads (WebP, AVIF, GIF first frame, BMP, TIFF; HEIC only if Pillow has
  it), EXIF rotation applied, written at `dest` with its suffix set to `.jpg`/`.png`.
  Given a video, one frame at 1/3 of its length. `dest` may be the source itself.
- `as_clip(path, dest) -> Path`: an H.264 mp4 of any video, at `dest` with the suffix
  `.mp4`; an H.264 mp4 already is returned unchanged and nothing is written.
- `normalise_refs(job_dir) -> list[str]`: every image row of `input/refs.json` that is
  not a real `.jpg`/`.png`/`.webp` (content and suffix agreeing) becomes one, keeping the slug;
  `refs.json` then points at it with its new size. Idempotent. It returns one job.log
  line per conversion, and per unreadable ref (left as it is: the render skips it);
  a missing ref is skipped silently (sourcing logs it). Clips are left to 111c.

`MediaError` is the one exception `as_still`/`as_clip` raise on a file they cannot use.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from shortsmith import ffmpeg

MediaKind = Literal["image", "video"]

# Pillow format -> the suffixes that may carry it in the render.
_BROWSER_IMAGES: dict[str, frozenset[str]] = {
    "JPEG": frozenset({".jpg", ".jpeg"}),
    "PNG": frozenset({".png"}),
    "WEBP": frozenset({".webp"}),
}
# What a normalised ref is: an image the browser draws under its own suffix (112b: a
# real WebP is kept byte for byte, never re-encoded to a lossy JPEG).
_REF_IMAGES = _BROWSER_IMAGES
# ffprobe demuxers that read stills or text, never a moving picture.
_STILL_DEMUXERS = ("image2", "tty", "_pipe")
STILL_QUALITY = 92
CLIP_TIMEOUT_S = 900.0
FRAME_AT = 1 / 3


class MediaError(Exception):
    """The file is no image or video this module can read."""


def _image_format(path: Path) -> str | None:
    """The Pillow format of `path`, or None when Pillow cannot decode it."""
    try:
        with Image.open(path) as im:
            im.load()
            return im.format
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError):
        return None


def _video_stream(path: Path) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(format, first video stream) when ffprobe finds a moving picture in `path`."""
    try:
        data = ffmpeg.probe(path)
    except (ffmpeg.FFmpegError, OSError, ValueError):
        return None
    fmt = data.get("format", {})
    name = str(fmt.get("format_name", ""))
    if any(still in name for still in _STILL_DEMUXERS):
        return None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return fmt, stream
    return None


def probe(path: Path) -> MediaKind | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    if _image_format(path) is not None:
        return "image"
    if _video_stream(path) is not None:
        return "video"
    return None


def is_browser_safe(path: Path) -> bool:
    suffix = path.suffix.lower()
    fmt = _image_format(path) if path.is_file() else None
    if fmt is not None:
        return suffix in _BROWSER_IMAGES.get(fmt, frozenset())
    found = _video_stream(path) if path.is_file() else None
    if found is None:
        return False
    fmt_info, stream = found
    return (
        suffix == ".mp4"
        and "mp4" in str(fmt_info.get("format_name", ""))
        and stream.get("codec_name") == "h264"
    )


def _replace(tmp: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, dest)
    return dest


def _temp_beside(dest: Path, suffix: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=suffix, dir=dest.parent)
    os.close(fd)
    return Path(name)


def as_still(path: Path, dest: Path) -> Path:
    kind = probe(path)
    if kind is None:
        raise MediaError(f"{path.name} is no image or video")
    if kind == "video":
        out = dest.with_suffix(".jpg")
        duration = ffmpeg.duration_s(path)
        tmp = _temp_beside(out, ".jpg")
        try:
            ffmpeg.still(path, tmp, at_s=duration * FRAME_AT)
            return _replace(tmp, out)
        finally:
            tmp.unlink(missing_ok=True)
    with Image.open(path) as im:
        im.seek(0)
        upright = ImageOps.exif_transpose(im)
        alpha = upright.mode in ("RGBA", "LA", "PA") or (
            upright.mode == "P" and "transparency" in upright.info
        )
        out = dest.with_suffix(".png" if alpha else ".jpg")
        tmp = _temp_beside(out, out.suffix)
        try:
            if alpha:
                upright.convert("RGBA").save(tmp, format="PNG")
            else:
                upright.convert("RGB").save(tmp, format="JPEG", quality=STILL_QUALITY)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    try:
        return _replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def as_clip(path: Path, dest: Path) -> Path:
    if probe(path) != "video":
        raise MediaError(f"{path.name} is no video")
    if is_browser_safe(path):
        return path
    out = dest.with_suffix(".mp4")
    tmp = _temp_beside(out, ".mp4")
    try:
        ffmpeg.run(
            [
                ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(path),
                "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:a", "aac", "-movflags", "+faststart", str(tmp),
            ],  # fmt: skip
            timeout_s=CLIP_TIMEOUT_S,
        )
        return _replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def is_real_still(path: Path, *, suffix: str | None = None) -> bool:
    """A JPG, PNG or WebP by content, under its own suffix (`suffix` stands in for the
    path's own, e.g. an upload's original name): what a ref is saved as."""
    fmt = _image_format(path)
    named = (suffix if suffix is not None else path.suffix).lower()
    return fmt is not None and named in _REF_IMAGES.get(fmt, frozenset())


def normalise_refs(job_dir: Path) -> list[str]:
    input_dir = job_dir / "input"
    refs_path = input_dir / "refs.json"
    if not refs_path.is_file():
        return []
    rows: list[dict[str, Any]] = json.loads(refs_path.read_text(encoding="utf-8"))
    lines: list[str] = []
    changed = False
    for row in rows:
        if row.get("kind") != "image":
            continue
        src = input_dir / str(row["file"])
        if not src.exists() or is_real_still(src):  # a missing ref is sourcing's to log
            continue
        if probe(src) != "image":
            lines.append(f"refs: {src.name} is not a readable image; left as it is")
            continue
        out = as_still(src, src)
        if out != src:
            src.unlink(missing_ok=True)
        row["file"] = out.relative_to(input_dir).as_posix()
        row["size_bytes"] = out.stat().st_size
        with Image.open(out) as im:
            row["width"], row["height"] = im.size
        changed = True
        lines.append(f"refs: {src.name} converted to a real {out.suffix[1:]} ({out.name})")
    if changed:
        refs_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return lines
