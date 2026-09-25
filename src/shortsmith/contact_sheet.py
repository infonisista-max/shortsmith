"""The contact sheet `out/contact.jpg` (decision 10.4).

Row 1 is the hook strip: the first 2 s at 4 fps. Row 2 is the PIP strip (013, 3.3):
the eight `work/frames/strip_<n>.jpg` stills cropped through the measured window, as
the circle shows them, with the circle's edge and the face box the detector found
drawn on each (a still with no face says so), labelled with the still's time on the
recording; a job with no measurement or swept stills has no such row. Then one frame
per second at 270 px wide, six per row, a time label under each frame and the strip
line beneath it (016):
the beat at that time, its mode letter as drawn (F/P/O; a rung-4 rescue is P), its
kind (the treatment actually drawn for photo and card beats), and the asset-origin
letter (U user, W web, C Commons, O Openverse, P Pexels, X Pixabay, G generated, L
library, - none), with a red corner mark on a rescued (4.4) or downgraded (5.3) beat.
The 6.3 platform safe-area zones are drawn as thin outlines on the
first frame of every row. The last row is the summary panel: one dot per technical
check T1-T13 (green pass, red fail, grey not run or `not_implemented`: the 032
placeholders, 031), the critic scores as a placeholder until
033, the relevance judge's spent calls against the style's ceiling (5.2), and the
ledger line (cash total, subscription tokens with their api-equivalent value, the
soft-cap flag; 11.3). The file stays under 2 MB: `encode` steps the JPEG
quality down and, as a last resort, scales the whole sheet.

`layout` is pure geometry so the tests pin every position; `compose_image` draws from
in-memory frames; `compose(job)` pulls the frames from `out/short.mp4` in two ffmpeg
passes (`ffmpeg.frames_rgb`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from shortsmith import assets, ffmpeg, jobs, ledger, presenter
from shortsmith.contracts import AssetManifest, FaceBox, PicturePlan, PresenterMeasurement
from shortsmith.jobs import Job, JobRecord
from shortsmith.qa import technical
from shortsmith.qa.technical import QaReport

SOURCE_W, SOURCE_H = 1080, 1920
# Decision 6.3: the platform safe area, global for every style.
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT = 250, 320, 140

FRAME_W = 270
PER_ROW = 6
GUTTER = 12
SHEET_W = PER_ROW * FRAME_W + (PER_ROW + 1) * GUTTER
HOOK_FPS = 4
HOOK_SECONDS = 2.0
HOOK_FRAMES = int(HOOK_SECONDS * HOOK_FPS)
HOOK_W = (SHEET_W - (HOOK_FRAMES + 1) * GUTTER) // HOOK_FRAMES
# 013: the PIP strip row, eight square window crops on the hook row's grid.
PIP_FRAMES = presenter.STRIP_COUNT
PIP_W = (SHEET_W - (PIP_FRAMES + 1) * GUTTER) // PIP_FRAMES
PIP_H = PIP_W
HEADER_H = 36
LABEL_H = 20
STRIP_H = 20
SUMMARY_H = 72
MAX_BYTES = 2_000_000
TECHNICAL_CHECKS = technical.CHECK_ORDER  # T1-T13; T8 partial and T11-T13 grey until 032

BG_COLOUR = (24, 24, 24)
PANEL_COLOUR = (40, 40, 40)
TEXT_COLOUR = (230, 230, 230)
MUTED_COLOUR = (150, 150, 150)
SAFE_COLOUR = (255, 80, 80)
PASS_COLOUR = (46, 204, 113)
FAIL_COLOUR = (231, 76, 60)
PENDING_COLOUR = (120, 120, 120)
MARK_COLOUR = (231, 76, 60)
MARK_PX = 22
CIRCLE_COLOUR = (255, 255, 255)  # the PIP circle's edge on the strip row
FACE_COLOUR = (255, 214, 10)  # the detector's box on the strip row
FACE_PX = 2

QUALITIES = (85, 75, 65, 55, 45)
SCALES = (1.0, 0.75, 0.5)


class ContactSheetError(RuntimeError):
    """The sheet could not be brought under the size cap."""


def scaled_height(width: int) -> int:
    """The height ffmpeg's `scale=<width>:-2` gives a 9:16 source: nearest even."""
    return 2 * round(width * SOURCE_H / SOURCE_W / 2)


FRAME_H = scaled_height(FRAME_W)
HOOK_H = scaled_height(HOOK_W)


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """Inclusive PIL rectangle corners."""
        return (self.x, self.y, self.x + self.w - 1, self.y + self.h - 1)


@dataclass(frozen=True)
class Cell:
    frame: Box
    label: Box
    strip: Box
    time_s: float
    first_in_row: bool


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    hook: list[Cell]
    pip: list[Cell]
    frames: list[Cell]
    summary: Box


def _cell(x: int, y: int, w: int, h: int, time_s: float, first: bool) -> Cell:
    return Cell(
        frame=Box(x, y, w, h),
        label=Box(x, y + h, w, LABEL_H),
        strip=Box(x, y + h + LABEL_H, w, STRIP_H),
        time_s=time_s,
        first_in_row=first,
    )


def layout(n_hook: int, n_frames: int, pip_times: Sequence[float] = ()) -> Layout:
    """Where everything goes for `n_hook` hook frames, one PIP strip cell per time in
    `pip_times` (013; none when the job was not measured) and `n_frames` per-second
    frames."""
    y = HEADER_H
    hook = [
        _cell(GUTTER + i * (HOOK_W + GUTTER), y, HOOK_W, HOOK_H, i / HOOK_FPS, i == 0)
        for i in range(n_hook)
    ]
    if n_hook:
        y += HOOK_H + LABEL_H + STRIP_H + GUTTER
    # The safe-area outlines mean nothing on a window crop, so no PIP cell is `first`.
    pip = [
        _cell(GUTTER + i * (PIP_W + GUTTER), y, PIP_W, PIP_H, t, False)
        for i, t in enumerate(pip_times)
    ]
    if pip:
        y += PIP_H + LABEL_H + STRIP_H + GUTTER
    row_h = FRAME_H + LABEL_H + STRIP_H + GUTTER
    frames = [
        _cell(
            GUTTER + (i % PER_ROW) * (FRAME_W + GUTTER),
            y + (i // PER_ROW) * row_h,
            FRAME_W,
            FRAME_H,
            float(i),
            i % PER_ROW == 0,
        )
        for i in range(n_frames)
    ]
    y += ceil(n_frames / PER_ROW) * row_h
    summary = Box(GUTTER, y, SHEET_W - 2 * GUTTER, SUMMARY_H)
    return Layout(
        width=SHEET_W, height=y + SUMMARY_H + GUTTER, hook=hook, pip=pip, frames=frames,
        summary=summary,
    )  # fmt: skip


def safe_area_rects(frame: Box) -> tuple[Box, Box, Box]:
    """The 6.3 top, bottom and right reserved zones scaled into a frame box."""
    scale = frame.w / SOURCE_W
    top_h, bottom_h, right_w = (round(v * scale) for v in (SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT))
    return (
        Box(frame.x, frame.y, frame.w, top_h),
        Box(frame.x, frame.y + frame.h - bottom_h, frame.w, bottom_h),
        Box(frame.x + frame.w - right_w, frame.y, right_w, frame.h),
    )


def time_label(seconds: float) -> str:
    if seconds != int(seconds):
        return f"{seconds:.2f} s"
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _paste(image: Image.Image, frame: Image.Image, box: Box) -> None:
    if frame.size != (box.w, box.h):
        frame = frame.resize((box.w, box.h))  # pyright: ignore[reportUnknownMemberType]
    image.paste(frame, (box.x, box.y))


# --- the strip line (016) ------------------------------------------------------------------

MODE_LETTERS = {"full": "F", "pip": "P", "off": "O"}
ORIGIN_LETTERS = {
    "owner_supplied": "U", "web": "W", "commons": "C", "openverse": "O", "pexels": "P",
    "pixabay": "X", "generated": "G", "library": "L",
}  # fmt: skip


@dataclass(frozen=True)
class Strip:
    text: str
    marked: bool


def strip_line(t: float, plan: PicturePlan | None, manifest: AssetManifest | None) -> Strip:
    """The strip under the frame at output time `t` (10.4)."""
    if plan is None or not plan.beats:
        return Strip("-", False)
    beat = next((b for b in plan.beats if b.start <= t < b.end), plan.beats[-1])
    decided = manifest.beat(beat.id) if manifest is not None else None
    mode, kind, asset_id = beat.mode, str(beat.kind), beat.asset_id
    marked = False
    if decided is not None:
        asset_id = decided.asset_id
        marked = decided.rescued or decided.treatment_downgraded
        if decided.fallback_rung == 4:
            mode = "pip"
        elif beat.kind in ("photo", "card"):
            kind = decided.treatment
    elif asset_id is not None and manifest is not None:
        asset_id = manifest.aliases.get(asset_id, asset_id)
    record = manifest.asset(asset_id) if manifest is not None and asset_id else None
    origin = ORIGIN_LETTERS.get(record.origin, "-") if record is not None else "-"
    return Strip(f"{beat.id} {MODE_LETTERS[mode]} {kind} {origin}", marked)


def _draw_cell(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    cell: Cell,
    frame: Image.Image,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    strip: Strip | None = None,
) -> None:
    _paste(image, frame, cell.frame)
    if cell.first_in_row:
        for zone in safe_area_rects(cell.frame):
            draw.rectangle(zone.rect, outline=SAFE_COLOUR, width=1)
    strip = strip or Strip("-", False)
    if strip.marked:
        right, top = cell.frame.x + cell.frame.w - 1, cell.frame.y
        draw.polygon([(right - MARK_PX, top), (right, top), (right, top + MARK_PX)],
                     fill=MARK_COLOUR)  # fmt: skip
    label = time_label(cell.time_s)
    draw.text((cell.label.x + 4, cell.label.y + 2), label, fill=TEXT_COLOUR, font=font)
    colour = TEXT_COLOUR if strip.text != "-" else MUTED_COLOUR
    draw.text((cell.strip.x + 4, cell.strip.y + 2), strip.text, fill=colour, font=font)


# --- the PIP strip row (013) ---------------------------------------------------------------


def pip_cell(
    still: Image.Image, measured: PresenterMeasurement, face: FaceBox | None
) -> Image.Image:
    """One strip still as the circle shows it (3.3): cropped through the measured
    window and scaled to the cell, the circle's edge inscribed, and the box the detector
    found on this still outlined where it lands inside the window."""
    pip = measured.pip
    window = (pip.window_left, pip.window_top,
              pip.window_left + pip.window_size, pip.window_top + pip.window_size)  # fmt: skip
    cell = still.convert("RGB").crop(window).resize((PIP_W, PIP_H))  # pyright: ignore[reportUnknownMemberType]
    draw = ImageDraw.Draw(cell)
    draw.ellipse((0, 0, PIP_W - 1, PIP_H - 1), outline=CIRCLE_COLOUR, width=FACE_PX)
    if face is not None:
        scale = PIP_W / pip.window_size
        box = (
            (face.left - pip.window_left) * scale,
            (face.top - pip.window_top) * scale,
            (face.left + face.width - pip.window_left) * scale,
            (face.top + face.height - pip.window_top) * scale,
        )
        draw.rectangle(box, outline=FACE_COLOUR, width=FACE_PX)
    return cell


def pip_strip(face: FaceBox | None) -> Strip:
    """The line under a strip cell: the box the detector found, or that it found none."""
    if face is None:
        return Strip("no face", True)
    return Strip(f"face {face.width}x{face.height}", False)


def pip_row(job: Job, measured: PresenterMeasurement) -> tuple[list[Image.Image], list[Strip]]:
    """The row's cells and their lines from `work/frames/strip_<n>.jpg`; empty when a
    still is gone (the sweeper took `work/`), never a partial row."""
    cells: list[Image.Image] = []
    strips: list[Strip] = []
    for n, face in enumerate(measured.faces, start=1):
        path = presenter.still_path(job, n)
        if not path.is_file():
            return [], []
        with Image.open(path) as still:
            cells.append(pip_cell(still, measured, face))
        strips.append(pip_strip(face))
    return cells, strips


def ledger_line(record: JobRecord) -> str:
    """The 11.3 cost line: cash, subscription tokens beside it, the soft-cap flag."""
    line = f"ledger: INR {ledger.cash_total(record):.2f} cash"
    tokens = ledger.tokens_total(record)
    if tokens:
        line += f" + {tokens} tokens (INR {ledger.equivalent_total(record):.2f} equiv.)"
    if record.over_soft_cap:
        line += " OVER SOFT CAP"
    return line


def judge_line(manifest: AssetManifest | None) -> str:
    """The 5.2 judge line: calls spent against the style's ceiling, and whether the
    ceiling stopped it (the beats after it were sourced unjudged)."""
    if manifest is None or manifest.judge_max == 0:
        return "judge: off"
    line = f"judge: {manifest.judge_calls}/{manifest.judge_max} calls"
    if manifest.judge_calls >= manifest.judge_max:
        line += " CAP REACHED"
    return line


def _draw_summary(
    draw: ImageDraw.ImageDraw,
    box: Box,
    report: QaReport | None,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    cost: str = "ledger: -",
) -> None:
    draw.rectangle(box.rect, fill=PANEL_COLOUR)
    results = {c.name: c.status for c in report.checks} if report is not None else {}
    x = box.x + 12
    cy = box.y + 22
    for name in TECHNICAL_CHECKS:
        # A check that did not run, or a 032 placeholder, is grey: never green (031).
        status = results.get(name)
        colour = (
            PASS_COLOUR if status == "pass" else FAIL_COLOUR if status == "fail" else PENDING_COLOUR
        )
        draw.ellipse((x, cy - 8, x + 16, cy + 8), fill=colour)
        draw.text((x + 22, cy - 9), name, fill=TEXT_COLOUR, font=font)
        x += 70
    draw.text(
        (box.x + 12, box.y + 44),
        f"critic E1-E10: pending (033) · {cost}",
        fill=MUTED_COLOUR,
        font=font,
    )


def compose_image(
    hook: list[Image.Image],
    frames: list[Image.Image],
    report: QaReport | None,
    title: str,
    cost: str = "ledger: -",
    *,
    hook_strips: list[Strip] | None = None,
    frame_strips: list[Strip] | None = None,
    pip: list[Image.Image] | None = None,
    pip_times: Sequence[float] = (),
    pip_strips: list[Strip] | None = None,
) -> Image.Image:
    """Draw the sheet from in-memory frames (hook strip first, then the PIP strip row
    when `pip` cells are given, one per time in `pip_times`, then per-second)."""
    pip = pip or []
    lay = layout(len(hook), len(frames), pip_times[: len(pip)])
    image = Image.new("RGB", (lay.width, lay.height), BG_COLOUR)
    draw = ImageDraw.Draw(image)
    font = _font(14)
    draw.text((GUTTER, 10), title, fill=TEXT_COLOUR, font=_font(16))
    for i, (cell, frame) in enumerate(zip(lay.hook, hook, strict=True)):
        _draw_cell(image, draw, cell, frame, font, hook_strips[i] if hook_strips else None)
    for i, (cell, frame) in enumerate(zip(lay.pip, pip, strict=True)):
        _draw_cell(image, draw, cell, frame, font, pip_strips[i] if pip_strips else None)
    for i, (cell, frame) in enumerate(zip(lay.frames, frames, strict=True)):
        _draw_cell(image, draw, cell, frame, font, frame_strips[i] if frame_strips else None)
    _draw_summary(draw, lay.summary, report, font, cost)
    return image


def encode(image: Image.Image, path: Path, *, max_bytes: int = MAX_BYTES) -> Path:
    """Save as JPEG under `max_bytes`: quality steps down first, then the sheet scales."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for scale in SCALES:
        candidate = image
        if scale != 1.0:
            size = (round(image.width * scale), round(image.height * scale))
            candidate = image.resize(size)  # pyright: ignore[reportUnknownMemberType]
        for quality in QUALITIES:
            candidate.save(path, format="JPEG", quality=quality, optimize=True)
            if path.stat().st_size < max_bytes:
                return path
    path.unlink(missing_ok=True)
    raise ContactSheetError(f"contact sheet cannot be brought under {max_bytes} bytes")


def _to_images(frames: list[tuple[int, int, bytes]]) -> list[Image.Image]:
    return [Image.frombytes("RGB", (w, h), px) for w, h, px in frames]


def compose(job: Job) -> Path:
    """`out/contact.jpg` from `out/short.mp4` and `out/qa.json` (when present)."""
    short = job.out_dir / "short.mp4"
    hook = _to_images(
        ffmpeg.frames_rgb(short, fps=HOOK_FPS, width=HOOK_W, duration_s=HOOK_SECONDS)
    )
    frames = _to_images(ffmpeg.frames_rgb(short, fps=1, width=FRAME_W))
    report = technical.load_report(job)
    title = (
        f"job {job.id} · {len(frames)} frames at 1 fps · hook {HOOK_SECONDS:g} s at {HOOK_FPS} fps"
    )
    plan_path = job.work_dir / "plan.json"
    plan = (
        PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        if plan_path.is_file()
        else None
    )
    manifest = assets.load_manifest(job.path)
    lay = layout(len(hook), len(frames))
    hook_strips = [strip_line(c.time_s, plan, manifest) for c in lay.hook]
    frame_strips = [strip_line(c.time_s, plan, manifest) for c in lay.frames]
    # Re-read: the ledger appends rows to job.json behind the worker's Job value, and
    # the measurement (013) landed there at `transcribing`.
    record = jobs.load(job.path).record
    cost = f"{judge_line(manifest)} · {ledger_line(record)}"
    pip, pip_strips, pip_times = [], [], []
    if record.presenter is not None:
        pip, pip_strips = pip_row(job, record.presenter)
        pip_times = record.presenter.times_s
    image = compose_image(hook, frames, report, title, cost, hook_strips=hook_strips,
                          frame_strips=frame_strips, pip=pip, pip_times=pip_times,
                          pip_strips=pip_strips)  # fmt: skip
    return encode(image, job.out_dir / "contact.jpg")
