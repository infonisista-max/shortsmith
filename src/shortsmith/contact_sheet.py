"""The contact sheet `out/contact.jpg` (decision 10.4), frames only in this ticket.

Row 1 is the hook strip: the first 2 s at 4 fps. Then one frame per second at 270 px
wide, six per row, a time label under each frame and a one-line strip slot beneath it
that later tickets fill (beat id, mode letter, kind, asset-origin letter, red corner
mark: 016 and 035). The 6.3 platform safe-area zones are drawn as thin outlines on the
first frame of every row. The last row is the summary panel: one dot per technical
check (green pass, red fail, grey not run), with the critic scores and ledger total as
placeholders until 033 and 011. The file stays under 2 MB: `encode` steps the JPEG
quality down and, as a last resort, scales the whole sheet.

`layout` is pure geometry so the tests pin every position; `compose_image` draws from
in-memory frames; `compose(job)` pulls the frames from `out/short.mp4` in two ffmpeg
passes (`ffmpeg.frames_rgb`).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from shortsmith import ffmpeg
from shortsmith.jobs import Job
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
HEADER_H = 36
LABEL_H = 20
STRIP_H = 20
SUMMARY_H = 72
MAX_BYTES = 2_000_000
TECHNICAL_CHECKS = ("T1", "T2", "T3", "T4")  # grows to T13 with the later gate tickets

BG_COLOUR = (24, 24, 24)
PANEL_COLOUR = (40, 40, 40)
TEXT_COLOUR = (230, 230, 230)
MUTED_COLOUR = (150, 150, 150)
SAFE_COLOUR = (255, 80, 80)
PASS_COLOUR = (46, 204, 113)
FAIL_COLOUR = (231, 76, 60)
PENDING_COLOUR = (120, 120, 120)

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


def layout(n_hook: int, n_frames: int) -> Layout:
    """Where everything goes for `n_hook` hook frames and `n_frames` per-second frames."""
    y = HEADER_H
    hook = [
        _cell(GUTTER + i * (HOOK_W + GUTTER), y, HOOK_W, HOOK_H, i / HOOK_FPS, i == 0)
        for i in range(n_hook)
    ]
    if n_hook:
        y += HOOK_H + LABEL_H + STRIP_H + GUTTER
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
        width=SHEET_W, height=y + SUMMARY_H + GUTTER, hook=hook, frames=frames, summary=summary
    )


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


def _draw_cell(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    cell: Cell,
    frame: Image.Image,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    _paste(image, frame, cell.frame)
    if cell.first_in_row:
        for zone in safe_area_rects(cell.frame):
            draw.rectangle(zone.rect, outline=SAFE_COLOUR, width=1)
    label = time_label(cell.time_s)
    draw.text((cell.label.x + 4, cell.label.y + 2), label, fill=TEXT_COLOUR, font=font)
    # The strip line (beat · mode · kind · origin) is filled by 016/035; a placeholder for now.
    draw.text((cell.strip.x + 4, cell.strip.y + 2), "- · - · - · -", fill=MUTED_COLOUR, font=font)


def _draw_summary(
    draw: ImageDraw.ImageDraw,
    box: Box,
    report: QaReport | None,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    draw.rectangle(box.rect, fill=PANEL_COLOUR)
    results = {c.name: c.passed for c in report.checks} if report is not None else {}
    x = box.x + 12
    cy = box.y + 22
    for name in TECHNICAL_CHECKS:
        passed = results.get(name)
        colour = (
            PENDING_COLOUR if passed is None else PASS_COLOUR if passed else FAIL_COLOUR
        )
        draw.ellipse((x, cy - 8, x + 16, cy + 8), fill=colour)
        draw.text((x + 22, cy - 9), name, fill=TEXT_COLOUR, font=font)
        x += 70
    draw.text(
        (box.x + 12, box.y + 44),
        "critic E1-E10: pending (033) · ledger total: pending (011)",
        fill=MUTED_COLOUR,
        font=font,
    )


def compose_image(
    hook: list[Image.Image],
    frames: list[Image.Image],
    report: QaReport | None,
    title: str,
) -> Image.Image:
    """Draw the sheet from in-memory frames (hook strip first, then per-second)."""
    lay = layout(len(hook), len(frames))
    image = Image.new("RGB", (lay.width, lay.height), BG_COLOUR)
    draw = ImageDraw.Draw(image)
    font = _font(14)
    draw.text((GUTTER, 10), title, fill=TEXT_COLOUR, font=_font(16))
    for cell, frame in zip(lay.hook, hook, strict=True):
        _draw_cell(image, draw, cell, frame, font)
    for cell, frame in zip(lay.frames, frames, strict=True):
        _draw_cell(image, draw, cell, frame, font)
    _draw_summary(draw, lay.summary, report, font)
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
    image = compose_image(hook, frames, report, title)
    return encode(image, job.out_dir / "contact.jpg")
