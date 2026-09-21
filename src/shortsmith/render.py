"""The Python half of the picture engine (decision 9.1, ticket 004).

`build_spec` is pure: from the PicturePlan, the caption pages and the transcript
words it resolves everything the Remotion composition needs into a `RenderSpec`
(frames not seconds, a pixel box per word, the PIP circle and crop window, the
palette, the 6.2 typography numbers). The composition under `src/remotion/` draws
what it is given and measures nothing.

`render(job)` writes `work/render_spec.json`, runs `src/remotion/driver.mjs` (which
bundles once into `build/remotion/` and renders through `@remotion/renderer` with
concurrency 2 and bt709), streams the driver's `progress N/M` lines to the caller,
keeps the full driver output in `work/render.log` and leaves `work/picture.mp4`,
silent H.264. The presenter source is `input/raw.mp4` until ticket 005 supplies the
CFR cut.

Style numbers: the loader (008) does not exist yet, so `EXPLAINER` holds the 6.2, 6.3
and 3.3 numbers as one typed constant, the way `pipeline` holds the pager numbers.
Word widths are estimated from a per-glyph advance table for Poppins 800; ticket 010
replaces the estimate with a Pillow measurement and adds the pager's own wrapping.
The gradient palette, PIP left edge and ring look are placeholders that 008 moves
into front matter (no reference value exists on record for them).

Component registry (9.2): `src/remotion/registry.json` is the checked-in list the
Node test asserts against the component files; `registry()` reads the same file.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from shortsmith import ffmpeg, subproc
from shortsmith.contracts import (
    BeatSpec,
    CaptionPage,
    CaptionPageSpec,
    CaptionStyle,
    Palette,
    PicturePlan,
    PipGeometry,
    RenderSpec,
    Transcript,
    Word,
    WordBox,
)
from shortsmith.jobs import Job

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTION_DIR = REPO_ROOT / "src" / "remotion"
DRIVER = REMOTION_DIR / "driver.mjs"
REGISTRY_PATH = REMOTION_DIR / "registry.json"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
CONCURRENCY = 2  # decision 9.1
DRIVER_TIMEOUT_S = 3600.0

_PAGES = TypeAdapter(list[CaptionPage])


class RenderError(RuntimeError):
    """The driver failed; the message carries the tail of its output."""


class LayoutError(ValueError):
    """A caption page cannot be laid out within the style's line limit (6.2)."""


# --- style numbers (until 008) ---------------------------------------------------------


@dataclass(frozen=True)
class PipNumbers:
    diameter: int
    large_face_diameter: int
    chin_anchor: float
    left: int
    ring_px: int
    ring_color: str


@dataclass(frozen=True)
class StyleNumbers:
    captions: CaptionStyle
    pip: PipNumbers
    palette: Palette


EXPLAINER = StyleNumbers(
    captions=CaptionStyle(
        font_family="Poppins",
        font_weight=800,
        size_px=74,
        line_height=1.35,
        letter_spacing_px=0.5,
        anchor_y=1460,
        max_lines=2,
        max_width_px=960,
        word_gap_px=22,
        unspoken_alpha=0.86,
        active_color="#FFD60A",
        active_scale=1.08,
        active_scale_s=0.10,
        keyword_fg="#111",
        keyword_bg="#FFD60A",
        keyword_pad_px=14,
        keyword_radius_px=14,
        enter_scale_from=0.94,
        enter_s=0.12,
        enter_opacity_s=0.06,
        stroke_px=2,
        drop_px=3,
        glow_px=18,
    ),
    pip=PipNumbers(
        diameter=300,
        large_face_diameter=340,
        chin_anchor=0.82,
        left=60,  # placeholder until 008: "bottom-left" is all the reference records
        ring_px=6,
        ring_color="#FFFFFF",
    ),
    palette=Palette(gradient=["#0B1D3A", "#1F3B73"], angle_deg=160, accent="#FFD60A"),
)


# --- text width estimate (until 010 measures with Pillow) -----------------------------

# Advance widths in em for Poppins 800, by glyph class; a guess good to about 10 %.
_NARROW = set("iljtfr.,'!|:;")
_WIDE = set("mw")
_WIDE_UPPER = set("MW")
_ADVANCE_EM = {"narrow": 0.34, "lower": 0.58, "wide": 0.90, "upper": 0.72, "wide_upper": 1.0,
               "digit": 0.62, "space": 0.30, "other": 0.60}  # fmt: skip


def _glyph_em(ch: str) -> float:
    if ch in _NARROW:
        return _ADVANCE_EM["narrow"]
    if ch in _WIDE:
        return _ADVANCE_EM["wide"]
    if ch in _WIDE_UPPER:
        return _ADVANCE_EM["wide_upper"]
    if ch.isspace():
        return _ADVANCE_EM["space"]
    if ch.isdigit():
        return _ADVANCE_EM["digit"]
    if ch.isupper():
        return _ADVANCE_EM["upper"]
    if ch.islower():
        return _ADVANCE_EM["lower"]
    return _ADVANCE_EM["other"]


def text_width(text: str, style: CaptionStyle) -> float:
    """Resting width of `text` at the style size: glyph advances plus letter spacing."""
    return sum(_glyph_em(ch) for ch in text) * style.size_px + style.letter_spacing_px * len(text)


def box_width(text: str, *, keyword: bool, style: CaptionStyle) -> float:
    """The fixed box: the 1.08-scaled width, plus the keyword padding when boxed (6.2)."""
    width = text_width(text, style) * style.active_scale
    if keyword:
        width += 2 * style.keyword_pad_px
    return width


# --- caption layout --------------------------------------------------------------------


def layout_page(page: CaptionPage, words: Sequence[Word], style: CaptionStyle) -> CaptionPageSpec:
    """Boxes for one page: greedy fill into lines no wider than `max_width_px`, each
    line centred, the block's bottom edge on `anchor_y`. More than `max_lines` raises."""
    items = [
        (words[i], box_width(words[i].text, keyword=(i == page.keyword), style=style), i)
        for i in page.word_indices
    ]
    lines: list[list[tuple[Word, float, int]]] = [[]]
    used = 0.0
    for item in items:
        width = item[1]
        extra = width if not lines[-1] else style.word_gap_px + width
        if lines[-1] and used + extra > style.max_width_px:
            lines.append([item])
            used = width
        else:
            lines[-1].append(item)
            used += extra
    if len(lines) > style.max_lines:
        raise LayoutError(
            f"caption page {page.index} needs {_count(len(lines))} lines "
            f"(max {style.max_lines}): {' '.join(page.texts)!r}"
        )
    line_h = style.size_px * style.line_height
    top = style.anchor_y - len(lines) * line_h
    boxes: list[WordBox] = []
    for n, line in enumerate(lines):
        line_w = sum(w for _, w, _ in line) + style.word_gap_px * (len(line) - 1)
        x = (WIDTH - line_w) / 2
        for word, width, index in line:
            boxes.append(
                WordBox(
                    text=word.text,
                    start=word.start,
                    end=word.end,
                    x=x,
                    y=top + n * line_h,
                    width=width,
                    height=line_h,
                    keyword=index == page.keyword,
                )
            )
            x += width + style.word_gap_px
    return CaptionPageSpec(
        index=page.index, start=page.start, end=page.end, lines=len(lines), words=boxes
    )


def _count(n: int) -> str:
    return {3: "three", 4: "four"}.get(n, str(n))


# --- PIP geometry ----------------------------------------------------------------------


def fixed_pip(source_size: tuple[int, int], numbers: StyleNumbers) -> PipGeometry:
    """The 004 geometry: the style diameter, left at the style edge, bottom touching the
    caption block's top (6.3); the crop window is the largest square of full source
    width anchored at the top, centred horizontally on a landscape source."""
    style = numbers.captions
    block_top = style.anchor_y - style.max_lines * style.size_px * style.line_height
    top = int(block_top) - numbers.pip.diameter
    src_w, src_h = source_size
    size = min(src_w, src_h)
    return PipGeometry(
        left=numbers.pip.left,
        top=top,
        diameter=numbers.pip.diameter,
        ring_px=numbers.pip.ring_px,
        ring_color=numbers.pip.ring_color,
        window_left=(src_w - size) // 2,
        window_top=0,
        window_size=size,
    )


# --- the spec --------------------------------------------------------------------------


def build_spec(
    plan: PicturePlan,
    pages: Sequence[CaptionPage],
    words: Sequence[Word],
    *,
    presenter: Path,
    source_size: tuple[int, int],
    duration_s: float,
    numbers: StyleNumbers = EXPLAINER,
    fps: int = FPS,
) -> RenderSpec:
    frames = round(duration_s * fps)
    beats = [
        BeatSpec(
            id=b.id,
            start_frame=round(b.start * fps),
            end_frame=round(b.end * fps),
            mode=b.mode,
            kind=b.kind,
            enter=b.enter,
        )
        for b in plan.beats
    ]
    return RenderSpec(
        width=WIDTH,
        height=HEIGHT,
        fps=fps,
        frames=frames,
        presenter=str(presenter),
        source_width=source_size[0],
        source_height=source_size[1],
        beats=beats,
        captions=[layout_page(p, words, numbers.captions) for p in pages],
        pip=fixed_pip(source_size, numbers),
        palette=numbers.palette,
        caption_style=numbers.captions,
    )


# --- the driver ------------------------------------------------------------------------

_PROGRESS = re.compile(r"^progress (\d+)/(\d+)\s*$")
_DONE = re.compile(r"^done frames=(\d+) render_s=([\d.]+) bundle_s=([\d.]+)\s*$")


def parse_progress(line: str) -> tuple[int, int] | None:
    match = _PROGRESS.match(line)
    return (int(match.group(1)), int(match.group(2))) if match else None


@dataclass(frozen=True)
class DriverResult:
    frames: int
    render_s: float
    bundle_s: float
    wall_s: float


def registry() -> list[str]:
    """The component names the Node project exports (9.2)."""
    return list(json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["components"])


def node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        raise RenderError("node is not on PATH; the picture engine needs Node (ticket 004)")
    return node


def run_driver(
    spec: RenderSpec,
    *,
    spec_path: Path,
    out_path: Path,
    log_path: Path,
    on_progress: Callable[[int], None] | None = None,
    concurrency: int = CONCURRENCY,
) -> DriverResult:
    """Render `spec` to `out_path` through the driver; every driver line lands in
    `log_path`, `progress` lines reach `on_progress` as a percentage when it changes."""
    spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    argv = [
        node_binary(),
        str(DRIVER),
        "render",
        "--spec",
        str(spec_path),
        "--out",
        str(out_path),
        "--concurrency",
        str(concurrency),
    ]
    done: DriverResult | None = None
    last_pct = -1
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(argv) + "\n")

        def on_line(stream: str, line: str) -> None:
            nonlocal done, last_pct
            log.write(f"[{stream}] {line}\n")
            if stream != "out":
                return
            progress = parse_progress(line)
            if progress is not None and on_progress is not None:
                rendered, total = progress
                pct = min(100, math.floor(100 * rendered / max(1, total)))
                if pct != last_pct:
                    last_pct = pct
                    on_progress(pct)
                return
            match = _DONE.match(line)
            if match:
                done = DriverResult(
                    frames=int(match.group(1)),
                    render_s=float(match.group(2)),
                    bundle_s=float(match.group(3)),
                    wall_s=0.0,
                )

        proc = subproc.stream(argv, on_line, timeout_s=DRIVER_TIMEOUT_S, cwd=REPO_ROOT)
    if proc.returncode != 0 or done is None or not out_path.is_file():
        tail = log_path.read_text(encoding="utf-8")[-4000:]
        raise RenderError(f"remotion driver exited {proc.returncode}:\n{tail}")
    if on_progress is not None and last_pct != 100:
        on_progress(100)
    return DriverResult(
        frames=done.frames,
        render_s=done.render_s,
        bundle_s=done.bundle_s,
        wall_s=time.perf_counter() - started,
    )


def spec_for_job(job: Job, *, numbers: StyleNumbers = EXPLAINER) -> RenderSpec:
    """The RenderSpec from the job's files: plan.json, asr.json, captions.json and the
    presenter source (input/raw.mp4 until 005)."""
    work = job.work_dir
    plan = PicturePlan.model_validate_json((work / "plan.json").read_text(encoding="utf-8"))
    transcript = Transcript.model_validate_json((work / "asr.json").read_text(encoding="utf-8"))
    pages = _PAGES.validate_json((work / "captions.json").read_text(encoding="utf-8"))
    presenter = job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")
    if job.record.input is not None:
        source_size = (job.record.input.width, job.record.input.height)
    else:
        source_size = _probe_size(presenter)
    return build_spec(
        plan,
        pages,
        transcript.words,
        presenter=presenter,
        source_size=source_size,
        duration_s=transcript.duration_s,
        numbers=numbers,
    )


def _probe_size(path: Path) -> tuple[int, int]:
    for stream in ffmpeg.probe(path)["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise RenderError(f"{path.name} has no video stream")


def render(job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
    """The `rendering` step's picture half: `work/picture.mp4`, silent H.264."""
    spec = spec_for_job(job)
    out = job.work_dir / "picture.mp4"
    run_driver(
        spec,
        spec_path=job.work_dir / "render_spec.json",
        out_path=out,
        log_path=job.work_dir / "render.log",
        on_progress=on_progress,
    )
    return out


# --- the interface the pipeline uses ---------------------------------------------------


class Renderer(ABC):
    """The picture engine as the pipeline sees it. Remotion is local, not a paid
    service, but a render costs seconds, so the fake keeps the pipeline and app tests
    fast; the real path is covered by test_render and smoke (12.1)."""

    @abstractmethod
    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        """Write `work/picture.mp4` and return it; `on_progress` gets 0-100."""


class RemotionRenderer(Renderer):
    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        return render(job, on_progress=on_progress)


class FakeRenderer(Renderer):
    """Builds the same RenderSpec (so a bad plan still fails here), reports 0, 50 and
    100, and writes a placeholder `picture.mp4` that is not a video."""

    def __init__(self) -> None:
        self.jobs: list[Path] = []

    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        self.jobs.append(job.path)
        spec = spec_for_job(job)
        (job.work_dir / "render_spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
        for pct in (0, 50, 100):
            if on_progress is not None:
                on_progress(pct)
        out = job.work_dir / "picture.mp4"
        out.write_bytes(b"")
        return out
