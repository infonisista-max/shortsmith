"""contact_sheet: the frames-only sheet per decision 10.4 (ticket 006): hook strip
row, one frame per second at 270 px six per row with a time label and a strip-line
placeholder, the 6.3 safe-area outlines on the first frame of each row, a summary row
with the T1-T4 dots, under 2 MB. Layout and size are unit-tested on synthetic frames;
`compose(job)` runs on a small synthetic short (12.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from shortsmith import contact_sheet, ffmpeg, jobs
from shortsmith.contact_sheet import (
    FRAME_H,
    FRAME_W,
    GUTTER,
    HOOK_FRAMES,
    HOOK_H,
    HOOK_W,
    PER_ROW,
    SHEET_W,
    Box,
)
from shortsmith.qa.technical import QaCheck, QaReport
from tests.conftest import Media


def _solid(size: tuple[int, int], colour: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", size, colour)


def _textured(size: tuple[int, int], seed: int) -> Image.Image:
    """A frame with the texture of a real short: gradient, shapes and text."""
    w, h = size
    image = Image.new("RGB", size)
    px = image.load()
    assert px is not None
    for y in range(h):
        for x in range(0, w, 1):
            px[x, y] = ((x * 255) // w, (y * 255) // h, (seed * 37) % 255)
    draw = ImageDraw.Draw(image)
    for i in range(12):
        draw.ellipse(
            [(i * 20 + seed) % w, (i * 33) % h, (i * 20 + seed) % w + 40, (i * 33) % h + 40],
            outline=(255, 255, 255),
            width=3,
        )
    draw.text((10, h // 2), f"FRAME {seed}", fill=(255, 214, 10))
    return image


def _report(*passed: bool) -> QaReport:
    checks = [
        QaCheck(name=f"T{i + 1}", passed=ok, detail="x") for i, ok in enumerate(passed)
    ]
    return QaReport(checks=checks, passed=all(passed))


# --- ffmpeg.frames_rgb ---------------------------------------------------------------------


def test_frames_rgb_extracts_one_frame_per_second_scaled(media: Media) -> None:
    clip = media.clip(duration_s=2.0, ext=".mp4")
    frames = ffmpeg.frames_rgb(clip, fps=1, width=FRAME_W)
    assert [(w, h) for w, h, _ in frames] == [(FRAME_W, FRAME_H)] * 2
    assert all(len(px) == FRAME_W * FRAME_H * 3 for _, _, px in frames)


def test_frames_rgb_hook_strip_is_two_seconds_at_four_fps(media: Media) -> None:
    clip = media.clip(duration_s=6.0, width=540, height=960, ext=".mp4")
    frames = ffmpeg.frames_rgb(clip, fps=4, width=HOOK_W, duration_s=2.0)
    assert len(frames) == HOOK_FRAMES
    assert {(w, h) for w, h, _ in frames} == {(HOOK_W, HOOK_H)}


# --- layout -----------------------------------------------------------------------------


def test_sheet_geometry_constants() -> None:
    assert FRAME_W == 270 and FRAME_H == 480 and PER_ROW == 6
    assert SHEET_W == PER_ROW * FRAME_W + (PER_ROW + 1) * GUTTER
    assert HOOK_FRAMES == 8  # first 2 s at 4 fps
    assert HOOK_W * HOOK_FRAMES + (HOOK_FRAMES + 1) * GUTTER <= SHEET_W
    assert contact_sheet.scaled_height(HOOK_W) == HOOK_H


def test_layout_places_hook_row_then_six_frames_per_row() -> None:
    lay = contact_sheet.layout(HOOK_FRAMES, 6)
    assert lay.width == SHEET_W
    assert [c.frame.x for c in lay.hook] == [GUTTER + i * (HOOK_W + GUTTER) for i in range(8)]
    assert len({c.frame.y for c in lay.hook}) == 1
    assert [c.frame.x for c in lay.frames] == [GUTTER + i * (FRAME_W + GUTTER) for i in range(6)]
    assert len({c.frame.y for c in lay.frames}) == 1
    assert lay.frames[0].frame.y > lay.hook[0].frame.y + HOOK_H
    assert [c.time_s for c in lay.frames] == [0, 1, 2, 3, 4, 5]
    assert [c.first_in_row for c in lay.frames] == [True] + [False] * 5
    assert lay.hook[0].first_in_row and not lay.hook[1].first_in_row
    for cell in lay.frames:
        assert cell.label.y >= cell.frame.y + FRAME_H
        assert cell.strip.y >= cell.label.y + cell.label.h
    assert lay.summary.y >= lay.frames[0].strip.y + lay.frames[0].strip.h
    assert lay.height == lay.summary.y + lay.summary.h + GUTTER


def test_layout_wraps_sixty_frames_into_ten_rows() -> None:
    lay = contact_sheet.layout(HOOK_FRAMES, 60)
    rows = sorted({c.frame.y for c in lay.frames})
    assert len(rows) == 10
    assert [c.first_in_row for c in lay.frames].count(True) == 10
    assert lay.frames[6].first_in_row and lay.frames[6].frame.x == GUTTER
    assert lay.frames[59].time_s == 59
    assert lay.frames[7].frame.y == lay.frames[6].frame.y


def test_layout_seven_frames_start_a_second_row() -> None:
    lay = contact_sheet.layout(HOOK_FRAMES, 7)
    assert lay.frames[6].frame.x == GUTTER
    assert lay.frames[6].frame.y > lay.frames[5].frame.y


def test_safe_area_outlines_scale_the_6_3_zones_into_the_frame() -> None:
    top, bottom, right = contact_sheet.safe_area_rects(Box(100, 200, FRAME_W, FRAME_H))
    assert (top.x, top.y, top.w, top.h) == (100, 200, FRAME_W, round(250 / 4))
    assert (bottom.x, bottom.w, bottom.h) == (100, FRAME_W, round(320 / 4))
    assert bottom.y + bottom.h == 200 + FRAME_H
    assert (right.y, right.h, right.w) == (200, FRAME_H, round(140 / 4))
    assert right.x + right.w == 100 + FRAME_W


# --- compose_image ----------------------------------------------------------------------


def test_compose_image_pastes_frames_labels_and_outlines() -> None:
    hook = [_solid((HOOK_W, HOOK_H), (10, 20, 30))] * HOOK_FRAMES
    frames = [_solid((FRAME_W, FRAME_H), (40 + i, 50, 60)) for i in range(6)]
    image = contact_sheet.compose_image(hook, frames, _report(True, True, True, True), "job x")
    lay = contact_sheet.layout(HOOK_FRAMES, 6)
    assert image.size == (lay.width, lay.height)
    # Frame pixels land where the layout says (sampled away from the outline strokes).
    for i, cell in enumerate(lay.frames):
        assert image.getpixel((cell.frame.x + 100, cell.frame.y + 200)) == (40 + i, 50, 60)
    # The 6.3 outlines sit on the first frame of the row and not on the second.
    first, second = lay.frames[0], lay.frames[1]
    top = contact_sheet.safe_area_rects(first.frame)[0]
    assert image.getpixel((first.frame.x + 100, top.y + top.h - 1)) == contact_sheet.SAFE_COLOUR
    assert image.getpixel((second.frame.x + 100, top.y + top.h - 1)) == (41, 50, 60)
    # Something is drawn in every label and strip slot and in the summary row.
    for cell in lay.frames:
        for box in (cell.label, cell.strip):
            region = image.crop((box.x, box.y, box.x + box.w, box.y + box.h))
            assert len(region.getcolors(maxcolors=4096) or []) > 1
    summary = image.crop(
        (lay.summary.x, lay.summary.y, lay.summary.x + lay.summary.w, lay.summary.y + lay.summary.h)
    )
    colours = {c for _, c in (summary.getcolors(maxcolors=1 << 16) or [])}
    assert contact_sheet.PASS_COLOUR in colours
    assert contact_sheet.FAIL_COLOUR not in colours


def test_compose_image_marks_a_failed_check_red_and_pending_checks_grey() -> None:
    hook = [_solid((HOOK_W, HOOK_H), (0, 0, 0))] * HOOK_FRAMES
    frames = [_solid((FRAME_W, FRAME_H), (0, 0, 0))]
    lay = contact_sheet.layout(HOOK_FRAMES, 1)
    image = contact_sheet.compose_image(hook, frames, _report(True, False), "job y")
    summary = image.crop(
        (lay.summary.x, lay.summary.y, lay.summary.x + lay.summary.w, lay.summary.y + lay.summary.h)
    )
    colours = {c for _, c in (summary.getcolors(maxcolors=1 << 16) or [])}
    expected = {contact_sheet.PASS_COLOUR, contact_sheet.FAIL_COLOUR, contact_sheet.PENDING_COLOUR}
    assert expected <= colours
    without = contact_sheet.compose_image(hook, frames, None, "job z")
    assert without.size == image.size


# --- encode: under 2 MB --------------------------------------------------------------------


def test_encode_keeps_a_sixty_second_sheet_under_two_megabytes(tmp_path: Path) -> None:
    hook = [_textured((HOOK_W, HOOK_H), i) for i in range(HOOK_FRAMES)]
    frames = [_textured((FRAME_W, FRAME_H), i) for i in range(60)]
    image = contact_sheet.compose_image(hook, frames, _report(True, True, True, True), "sixty")
    out = contact_sheet.encode(image, tmp_path / "contact.jpg")
    assert out.stat().st_size < contact_sheet.MAX_BYTES
    with Image.open(out) as saved:
        assert saved.format == "JPEG"
        assert saved.size == image.size


def test_encode_steps_quality_down_to_meet_a_cap(tmp_path: Path) -> None:
    hook = [_textured((HOOK_W, HOOK_H), i) for i in range(HOOK_FRAMES)]
    frames = [_textured((FRAME_W, FRAME_H), i) for i in range(6)]
    image = contact_sheet.compose_image(hook, frames, None, "cap")
    loose = contact_sheet.encode(image, tmp_path / "loose.jpg")
    tight = contact_sheet.encode(image, tmp_path / "tight.jpg", max_bytes=loose.stat().st_size // 2)
    assert tight.stat().st_size < loose.stat().st_size // 2


def test_encode_refuses_when_nothing_fits(tmp_path: Path) -> None:
    image = _textured((SHEET_W, 600), 3)
    with pytest.raises(contact_sheet.ContactSheetError):
        contact_sheet.encode(image, tmp_path / "never.jpg", max_bytes=500)


# --- compose(job) --------------------------------------------------------------------------


def test_compose_writes_out_contact_jpg_from_the_short(media: Media, tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    (job.out_dir / "short.mp4").write_bytes(media.clip(duration_s=6.0, ext=".mp4").read_bytes())
    (job.out_dir / "qa.json").write_text(
        _report(True, True, True, True).model_dump_json(), encoding="utf-8"
    )
    out = contact_sheet.compose(job)
    assert out == job.out_dir / "contact.jpg"
    lay = contact_sheet.layout(HOOK_FRAMES, 6)
    with Image.open(out) as saved:
        assert saved.format == "JPEG"
        assert saved.size == (lay.width, lay.height)
    assert out.stat().st_size < contact_sheet.MAX_BYTES
