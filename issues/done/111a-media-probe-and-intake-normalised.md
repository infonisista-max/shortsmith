# 111a — One media probe; every uploaded photo is a real JPG/PNG at intake

## Type

AFK. Part of 111 (read it for the causes).

## What to build

- **New `src/shortsmith/media.py`**, pure and small:
  - `probe(path) -> "image" | "video" | None`. It decides by **content**, never by
    extension: Pillow opens it as an image, or ffprobe finds a video stream; otherwise
    `None` (missing, empty, or undecodable).
  - `as_still(path, dest) -> Path`. It writes a real JPG (or a PNG when there is alpha)
    from any image Pillow reads (WebP, AVIF, GIF first frame, BMP, TIFF, HEIC if Pillow
    has it), with EXIF rotation applied. Given a video, it grabs one frame at 1/3 of its
    length with ffmpeg.
  - `as_clip(path, dest) -> Path`. It re-encodes a video that is not H.264 mp4 (.webm,
    .mov, other codecs) to H.264 mp4. Browser-safe means jpg/png/webp for images and
    H.264 mp4 for video (probe the codec).
- **Intake (`ingest.py:285-306`).** Every image ref is checked by content and saved as a
  real `.jpg`/`.png`. Its name keeps the slug, and `refs.json` points at the new file. A
  file that is not an image at all is refused with a plain message, as now. The
  extension allow-list stays only as a first filter, and `.avif`/`.heic` are added to it.
- **Old jobs.** An idempotent `normalise_refs(job_dir)` runs whenever a job enters
  sourcing or rendering, so a Retry on a job uploaded before this ticket is fixed too
  (today's job re-renders through it). Each conversion gets one job.log line.
- **Faces (`presenter.py:173`).** Faces are read through the normalised file. An
  unreadable ref logs and is skipped (as now) but never raises.

## Acceptance

- A WebP and an AVIF saved as `x.jpg` are converted at intake, and the face detector reads them.
- A fake `.jpg` that is a text file is refused at intake.
- `normalise_refs` on a job dir with a mislabelled ref fixes it once; a second run changes nothing.
- Tests: new `tests/test_media.py`, plus the matching cases in `test_ingest.py`.

## Files

`media.py` (new), `ingest.py`, `presenter.py`, the step entry in `pipeline.py` (one call only).
