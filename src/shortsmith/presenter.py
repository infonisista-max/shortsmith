"""The presenter cut list (PRD `presenter`, ticket 005; decisions 3.4, 8.1, 9.1).

`cut_list(plan)` turns the plan's kept and dropped spans plus the cold-open lift into
the ordered list of source spans that make up the output timeline: the cold-open span
first (the only editorial reordering in v1), then the kept spans minus the dropped
ones, minus the cold-open span itself at its original place when the planner said
`original_position: drop`. With `keep` the lifted line stays where it was and plays
twice; the validator (009) is what rejects an accidental repeat.

`output_time` maps a source time onto that timeline; `words_on_cut` applies the same
spans to the word list, so the pager (010) pages exactly the words the audio keeps,
at their times on the cut.

`crop_window` is the 2.1 geometry: the largest centred 9:16 window of the source,
refused when filling 1080x1920 from it would upscale past `MAX_UPSCALE` (ingest
rejects such uploads first; the cut checks again so a job never renders a soft
presenter). `scale_filter` is that window scaled to the composition: the cut and the
013 stills go through the same filter, so a face box measured on a still is already
in the cut's pixels.

Face measurement (ticket 013; decisions 3.3, 14.1(b)). `measure(job, spec)` takes
eight stills of the recording at the research strip times (`strip_times`), runs a
`FaceDetector` on each (`HaarDetector`, OpenCV's bundled frontal-face cascade; the
`FakeFaceDetector` answers a fixed box for the pipeline and app tests), takes the
per-edge median of the boxes it found (`median_box`), and derives the PIP geometry
(`pip_geometry`): the crop window is the full source width, square, placed so the chin
sits at `pip.chin_anchor` of its height (hair clips before chin) and clamped inside the
source; a face-box height over `pip.large_face_ratio` of the source width grows the
circle from `pip.diameter` to `pip.large_face_diameter`, upward from the same bottom
edge. Fewer than `MIN_FACES` stills with a face raise `NoFace` with the user-facing
sentence and the job fails at `transcribing`, before any paid call. The stills stay
under `work/frames/strip_<n>.jpg` for the contact sheet's PIP row (10.4), and the
measurement is written to `job.json.presenter`. Measured once; the PIP never follows
movement.
"""

from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

import cv2
from cv2 import data as cv2_data  # the bundled cascades' directory (`haarcascades`)

from shortsmith import ffmpeg, jobs
from shortsmith.contracts import (
    CutList,
    FaceBox,
    PicturePlan,
    PipGeometry,
    PresenterMeasurement,
    Span,
    Word,
)
from shortsmith.jobs import Job
from shortsmith.styles import StyleSpec

TARGET_WIDTH, TARGET_HEIGHT = 1080, 1920
MAX_UPSCALE = 1.5  # decision 2.1; the same number as `ingest.Limits.max_upscale`

# Decision 3.3: "8 stills at the research strip times". research.md section 2 records
# the old engine's PIP check verbatim: "a strip of 8 frames at 3.8, 6.5, 9.5, 17, 25,
# 36, 44, 53 s eyeballed at 3 to 4 candidate face centres", set before the Dyson v1
# delivery, whose master runs 57.5 s (docs/reference/README.md,
# DysonToothbrush_Short_v1.mp4). Uploads run 20 s to 8 min (2.1), so the eight times
# are kept as fractions of that 57.5 s runtime and applied to the recording's length.
STRIP_TIMES_S: tuple[float, ...] = (3.8, 6.5, 9.5, 17.0, 25.0, 36.0, 44.0, 53.0)
STRIP_RUNTIME_S = 57.5
STRIP_COUNT = len(STRIP_TIMES_S)
MIN_FACES = 6  # 3.3: "no face in >= 6 of 8 -> job fails early"
FRAMES_DIR = "frames"
NO_FACE_TEXT = "We could not find your face, please record facing the camera."

# The Haar cascade OpenCV bundles and its documented defaults; a face under
# `MIN_FACE_PX` on a 1080-wide cut is not a presenter.
CASCADE = "haarcascade_frontalface_default.xml"
SCALE_FACTOR, MIN_NEIGHBOURS, MIN_FACE_PX = 1.1, 5, 80


class UpscaleExceeded(ValueError):
    """The source is too small to fill 9:16 within the 1.5x rule."""


class NoFace(RuntimeError):
    """Fewer than `MIN_FACES` strip stills showed a face (3.3): the user-facing sentence."""

    def __init__(self, found: int) -> None:
        super().__init__(NO_FACE_TEXT)
        self.found = found


def upscale_factor(width: int, height: int) -> float:
    """Scale needed to fill 1080x1920 from the largest 9:16 centre crop of the source."""
    crop_height = min(height, width * TARGET_HEIGHT / TARGET_WIDTH)
    return TARGET_HEIGHT / crop_height


def _even(n: float) -> int:
    return int(round(n / 2)) * 2


def crop_window(source_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """(width, height, x, y) of the largest centred 9:16 window with even edges, or
    `UpscaleExceeded` when scaling it to 1080x1920 would pass the 1.5x rule."""
    width, height = source_size
    factor = upscale_factor(width, height)
    if factor > MAX_UPSCALE + 1e-9:
        raise UpscaleExceeded(
            f"filling 1080x1920 from {width}x{height} needs a {factor:.2f}x upscale, "
            f"more than the {MAX_UPSCALE:g}x rule allows"
        )
    if width * TARGET_HEIGHT >= height * TARGET_WIDTH:  # wider than 9:16: keep the height
        crop_w, crop_h = min(width, _even(height * TARGET_WIDTH / TARGET_HEIGHT)), height
    else:  # taller than 9:16: keep the width
        crop_w, crop_h = width, min(height, _even(width * TARGET_HEIGHT / TARGET_WIDTH))
    return crop_w, crop_h, (width - crop_w) // 2, (height - crop_h) // 2


def scale_filter(source_size: tuple[int, int]) -> str:
    """The 2.1 window cropped and scaled to the composition: what the presenter cut and
    the 013 stills both go through, so their pixels agree."""
    crop_w, crop_h, x, y = crop_window(source_size)
    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos"


# --- face measurement (ticket 013; decision 3.3) ------------------------------------------


def strip_times(duration_s: float) -> tuple[float, ...]:
    """The eight research strip times as fractions of the research runtime, on a
    recording `duration_s` long; see `STRIP_TIMES_S` for the source."""
    return tuple(round(t * duration_s / STRIP_RUNTIME_S, 3) for t in STRIP_TIMES_S)


class FaceDetector(ABC):
    @abstractmethod
    def detect(self, still: Path) -> FaceBox | None:
        """The largest face on the still, in its pixels, or None."""


class HaarDetector(FaceDetector):
    """OpenCV's bundled frontal-face Haar cascade at its documented defaults."""

    def __init__(self) -> None:
        self._cascade = cv2.CascadeClassifier(str(Path(cv2_data.haarcascades) / CASCADE))
        if self._cascade.empty():
            raise RuntimeError(f"OpenCV did not load {CASCADE} from cv2.data.haarcascades")

    def detect(self, still: Path) -> FaceBox | None:
        image = cv2.imread(str(still))
        if image is None:
            raise RuntimeError(f"OpenCV could not read {still}")
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found = self._cascade.detectMultiScale(
            grey,
            scaleFactor=SCALE_FACTOR,
            minNeighbors=MIN_NEIGHBOURS,
            minSize=(MIN_FACE_PX, MIN_FACE_PX),
        )
        boxes = [
            FaceBox(left=int(x), top=int(y), width=int(w), height=int(h)) for x, y, w, h in found
        ]
        if not boxes:
            return None
        return max(boxes, key=lambda b: b.width * b.height)


class FakeFaceDetector(FaceDetector):
    """Answers `box` on the first `found` stills of every eight and None on the rest:
    the pipeline and app tests upload flat clips with no face, and the 3.3 floor is
    tested by count. One instance serves every job a worker runs."""

    def __init__(self, box: FaceBox | None = None, *, found: int = STRIP_COUNT) -> None:
        self.box = box or FaceBox(left=286, top=114, width=520, height=520)
        self.found = found
        self.seen: list[Path] = []

    def detect(self, still: Path) -> FaceBox | None:
        self.seen.append(still)
        return self.box if (len(self.seen) - 1) % STRIP_COUNT < self.found else None


def median_box(boxes: Sequence[FaceBox | None]) -> FaceBox:
    """The per-edge median over the stills that showed a face (3.3)."""
    found = [b for b in boxes if b is not None]
    if not found:
        raise NoFace(0)

    def med(values: list[int]) -> int:
        return round(statistics.median(values))

    return FaceBox(
        left=med([b.left for b in found]),
        top=med([b.top for b in found]),
        width=med([b.width for b in found]),
        height=med([b.height for b in found]),
    )


def pip_geometry(face: FaceBox, source_size: tuple[int, int], spec: StyleSpec) -> PipGeometry:
    """The 3.3 geometry from the median face box, in the cut's pixels.

    Window: the full source width, square; its top placed so the chin (the box's
    bottom) sits at `pip.chin_anchor` of the window height, clamped so the window never
    leaves the source; centred horizontally when the source is wider than tall.
    Circle: `pip.large_face_diameter` when the box height passes `pip.large_face_ratio`
    of the source width, else `pip.diameter`; its bottom edge stays on the caption
    block's top (6.3), so the larger circle grows upward."""
    src_w, src_h = source_size
    size = min(src_w, src_h)
    top = round(face.chin_y - spec.pip.chin_anchor * size)
    window_top = max(0, min(src_h - size, top))
    large = face.height > spec.pip.large_face_ratio * src_w
    diameter = spec.pip.large_face_diameter if large else spec.pip.diameter
    bottom = spec.pip.top + spec.pip.diameter
    return PipGeometry(
        left=spec.pip.left,
        top=bottom - diameter,
        diameter=diameter,
        ring_px=spec.pip.ring_px,
        ring_color=spec.pip.ring_color,
        window_left=(src_w - size) // 2,
        window_top=window_top,
        window_size=size,
    )


def still_path(job: Job, n: int) -> Path:
    """`work/frames/strip_<n>.jpg`, `n` from 1."""
    return job.work_dir / FRAMES_DIR / f"strip_{n}.jpg"


def measure(job: Job, spec: StyleSpec, *, detector: FaceDetector | None = None) -> PipGeometry:
    """Measure the face once for `job` (3.3): eight stills of the recording through the
    cut's crop, the detector on each, the median box and the PIP geometry, written to
    `job.json.presenter`. Raises `NoFace` under `MIN_FACES` hits; the stills stay on
    disk either way."""
    detector = detector or HaarDetector()
    raw = job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")
    summary = job.record.input
    if summary is not None:
        source, duration = (summary.width, summary.height), summary.duration_s
    else:
        source, duration = ffmpeg.video_size(raw), ffmpeg.duration_s(raw)
    vf = scale_filter(source)
    times = strip_times(duration)
    faces: list[FaceBox | None] = []
    for n, t in enumerate(times, start=1):
        faces.append(detector.detect(ffmpeg.still(raw, still_path(job, n), at_s=t, vf=vf)))
    found = sum(1 for f in faces if f is not None)
    if found < MIN_FACES:
        raise NoFace(found)
    cut_size = (TARGET_WIDTH, TARGET_HEIGHT)
    face = median_box(faces)
    geometry = pip_geometry(face, cut_size, spec)
    measured = PresenterMeasurement(
        source_width=cut_size[0], source_height=cut_size[1], times_s=list(times),
        faces=faces, face=face, pip=geometry,
    )  # fmt: skip
    jobs.amend(job, presenter=measured)
    return geometry


def _subtract(spans: Sequence[Span], holes: Sequence[Span]) -> list[Span]:
    out: list[Span] = []
    for span in spans:
        pieces = [span]
        for hole in holes:
            next_pieces: list[Span] = []
            for piece in pieces:
                if hole.end <= piece.start or hole.start >= piece.end:
                    next_pieces.append(piece)
                    continue
                if hole.start > piece.start:
                    next_pieces.append(Span(start=piece.start, end=hole.start))
                if hole.end < piece.end:
                    next_pieces.append(Span(start=hole.end, end=piece.end))
            pieces = next_pieces
        out.extend(p for p in pieces if p.end > p.start)
    return out


def cut_list(plan: PicturePlan) -> list[Span]:
    """Source spans in output order: cold open, then the kept spans with the dropped
    spans (and, under `drop`, the cold open's original place) removed."""
    cold_open = plan.hook.cold_open_span
    holes = list(plan.cut.drop)
    if plan.hook.original_position == "drop":
        holes.append(cold_open)
    kept = sorted(plan.cut.keep, key=lambda s: s.start)
    body = _subtract(kept, holes)
    return [Span(start=cold_open.start, end=cold_open.end), *body]


def total_duration(spans: Sequence[Span]) -> float:
    return sum(s.end - s.start for s in spans)


CUT_LIST_NAME = "cut.json"


def write_cut_list(job: Job, spans: Sequence[Span]) -> Path:
    """`work/cut.json` (031): the spans the renderer cut, for gate T10."""
    path = job.work_dir / CUT_LIST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CutList(spans=list(spans)).model_dump_json(indent=2), encoding="utf-8")
    return path


def load_cut_list(job: Job) -> list[Span] | None:
    """The spans `write_cut_list` recorded; None before the renderer ran."""
    path = job.work_dir / CUT_LIST_NAME
    if not path.is_file():
        return None
    return CutList.model_validate_json(path.read_text(encoding="utf-8")).spans


def source_time(spans: Sequence[Span], output_t: float) -> float:
    """Where output time `output_t` comes from in the recording: the inverse of
    `output_time`. The end of the last span maps to that span's end; a time past the
    runtime is clamped there."""
    if not spans:
        return output_t
    offset = 0.0
    for i, span in enumerate(spans):
        length = span.end - span.start
        if output_t < offset + length or i == len(spans) - 1:
            return span.start + min(max(output_t - offset, 0.0), length)
        offset += length
    return spans[-1].end


def words_on_cut(spans: Sequence[Span], words: Sequence[Word]) -> list[tuple[int, Word]]:
    """The words the cut keeps, in output order, each with its index in `words` and its
    times moved onto the cut timeline (6.1): a word is kept by the span holding its
    midpoint, so a dropped span loses its words and the cold-open lift moves them to
    the front. Inside one span this is `output_time`; a lifted line kept at its
    original place (`keep`) is placed in both spans, as it plays twice."""
    placed: list[tuple[int, Word]] = []
    offset = 0.0
    for span in spans:
        for i, word in enumerate(words):
            mid = (word.start + word.end) / 2
            if span.start <= mid < span.end:
                start = offset + max(word.start, span.start) - span.start
                end = offset + min(word.end, span.end) - span.start
                placed.append(
                    (i, word.model_copy(update={"start": round(start, 3), "end": round(end, 3)}))
                )
        offset += span.end - span.start
    return placed


def output_time(spans: Sequence[Span], source_t: float) -> float:
    """Where `source_t` lands on the cut timeline. A time on a boundary belongs to the
    later span; a time inside no span maps to the end of the last span before it."""
    offset = 0.0
    hit: float | None = None
    for span in spans:
        if span.start <= source_t < span.end:
            hit = offset + (source_t - span.start)
        offset += span.end - span.start
    if hit is not None:
        return hit
    # Not inside any span: the end of the nearest earlier span, else 0.
    offset = 0.0
    best = 0.0
    for span in spans:
        offset += span.end - span.start
        if span.end <= source_t:
            best = offset
    return best
