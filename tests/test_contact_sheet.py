"""contact_sheet: the frames-only sheet per decision 10.4 (ticket 006): hook strip
row, one frame per second at 270 px six per row with a time label and the strip line
(beat, mode letter, kind, asset-origin letter; 016) with a red corner on rescued or
downgraded beats, the 6.3 safe-area outlines on the first frame of each row, a summary
row with the technical-check dots, under 2 MB. Layout and size are unit-tested on synthetic frames;
`compose(job)` runs on a small synthetic short (12.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from shortsmith import contact_sheet, ffmpeg, jobs, presenter
from shortsmith.contact_sheet import (
    FRAME_H,
    FRAME_W,
    GUTTER,
    HOOK_FRAMES,
    HOOK_H,
    HOOK_W,
    PER_ROW,
    PIP_H,
    PIP_W,
    SHEET_W,
    Box,
)
from shortsmith.contracts import (
    AssetManifest,
    AssetRecord,
    Beat,
    BeatAsset,
    CutPlan,
    FaceBox,
    Finale,
    Hook,
    PicturePlan,
    PipGeometry,
    PresenterMeasurement,
    Span,
)
from shortsmith.qa import technical
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


def test_summary_panel_lists_t1_to_t13_and_draws_a_check_that_did_not_run_grey() -> None:
    """031 / 032: thirteen dots in gate order; a check the report does not carry (or a
    pre-032 `not_implemented` row) is grey, not red and not green."""
    assert contact_sheet.TECHNICAL_CHECKS == technical.CHECK_ORDER
    hook = [_solid((HOOK_W, HOOK_H), (0, 0, 0))] * HOOK_FRAMES
    frames = [_solid((FRAME_W, FRAME_H), (0, 0, 0))]
    lay = contact_sheet.layout(HOOK_FRAMES, 1)
    checks = [QaCheck(name=n, passed=True, detail="x") for n in technical.CHECK_ORDER[:10]]
    checks += [QaCheck(name="T11", passed=False, status="not_implemented", detail="held")]
    image = contact_sheet.compose_image(hook, frames, technical.report(checks), "job p")
    summary = image.crop(
        (lay.summary.x, lay.summary.y, lay.summary.x + lay.summary.w, lay.summary.y + lay.summary.h)
    )
    colours = {c for _, c in (summary.getcolors(maxcolors=1 << 16) or [])}
    assert contact_sheet.PASS_COLOUR in colours and contact_sheet.PENDING_COLOUR in colours
    assert contact_sheet.FAIL_COLOUR not in colours


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


# --- the strip line and the rescue / downgrade mark (016) ----------------------------------


def _strip_plan() -> PicturePlan:
    beats = [
        Beat.model_validate({"id": bid, "start": float(i), "end": float(i + 1), "mode": mode,
                             "kind": kind, "asset_id": asset})  # fmt: skip
        for i, (bid, mode, kind, asset) in enumerate([
            ("b01", "full", "presenter_full", None),
            ("b02", "pip", "photo", "a1"),
            ("b03", "off", "photo", "a2"),
            ("b04", "pip", "card", "a3"),
            ("b05", "off", "finale", "a1"),
        ])
    ]  # fmt: skip
    return PicturePlan(
        prompt_version="t", cut=CutPlan(keep=[Span(start=0.0, end=5.0)]), beats=beats,
        hook=Hook(title="t", cold_open_span=Span(start=0.0, end=1.0), original_position="drop",
                  card_asset_ids=["a1"]),
        finale=Finale(beat_id="b05", text="t"), title="t", description="t",
    )  # fmt: skip


def _strip_manifest() -> AssetManifest:
    def record(asset_id: str, origin: str) -> AssetRecord:
        return AssetRecord.model_validate({
            "id": asset_id, "origin": origin, "source_url": "https://x.invalid/a.png",
            "file": "work/assets/a.png", "sha256": "0" * 64, "width": 1600, "height": 900,
            "fetched_at": "2026-09-22T12:00:00+00:00",
        })  # fmt: skip

    return AssetManifest(
        assets=[record("a1", "commons"), record("a2", "web")],
        beats=[
            BeatAsset(beat_id="b02", asset_id="a1", treatment="photo", fallback_rung=0),
            BeatAsset(beat_id="b03", asset_id="a2", treatment="card", fallback_rung=0,
                      treatment_downgraded=True),
            BeatAsset(beat_id="b04", asset_id=None, treatment="gradient", fallback_rung=4,
                      stamp="WHY"),
        ],
        aliases={"a1": "a1", "a2": "a2", "a3": None}, runtime_s=5.0, rescued_max=1,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("t", "text", "marked"),
    [
        (0.0, "b01 F presenter_full -", False),
        (1.25, "b02 P photo C", False),
        (2.0, "b03 O card W", True),  # a planned photo downgraded to a card (5.3)
        (3.5, "b04 P card -", True),  # rung 4: PIP over the gradient (4.4)
        (4.9, "b05 O finale C", False),  # the finale points at a1 through the aliases
        (5.0, "b05 O finale C", False),  # the last frame belongs to the last beat
    ],
)
def test_strip_line_names_beat_mode_kind_and_origin(t: float, text: str, marked: bool) -> None:
    strip = contact_sheet.strip_line(t, _strip_plan(), _strip_manifest())
    assert (strip.text, strip.marked) == (text, marked)


def test_strip_line_without_a_plan_is_a_placeholder() -> None:
    assert contact_sheet.strip_line(1.0, None, None) == contact_sheet.Strip("-", False)


def test_marked_cells_get_a_red_corner_and_the_others_do_not() -> None:
    hook = [_solid((HOOK_W, HOOK_H), (0, 0, 0))] * HOOK_FRAMES
    frames = [_solid((FRAME_W, FRAME_H), (0, 0, 0)) for _ in range(2)]
    strips = [
        contact_sheet.Strip("b01 P photo C", False),
        contact_sheet.Strip("b02 P card -", True),
    ]
    image = contact_sheet.compose_image(hook, frames, None, "marks", frame_strips=strips)
    lay = contact_sheet.layout(HOOK_FRAMES, 2)
    plain, marked = lay.frames
    corner = (marked.frame.x + marked.frame.w - 3, marked.frame.y + 2)
    assert image.getpixel(corner) == contact_sheet.MARK_COLOUR
    assert image.getpixel((plain.frame.x + plain.frame.w - 3, plain.frame.y + 2)) == (0, 0, 0)


# --- the PIP strip row (013; decision 3.3) --------------------------------------------------


def _measured(*, faces: list[FaceBox | None] | None = None) -> PresenterMeasurement:
    face = FaceBox(left=286, top=114, width=520, height=520)
    return PresenterMeasurement(
        source_width=1080, source_height=1920, times_s=list(presenter.strip_times(6.0)),
        faces=faces if faces is not None else [face] * 8, face=face,
        pip=PipGeometry(left=60, top=920, diameter=340, ring_px=6, ring_color="#FFFFFF",
                        window_left=0, window_top=100, window_size=1080),
    )  # fmt: skip


def test_layout_puts_the_pip_row_between_the_hook_and_the_frames() -> None:
    times = presenter.strip_times(6.0)
    lay = contact_sheet.layout(HOOK_FRAMES, 6, times)
    assert len(lay.pip) == 8 and PIP_W == HOOK_W and PIP_H == PIP_W
    assert [c.frame.x for c in lay.pip] == [GUTTER + i * (PIP_W + GUTTER) for i in range(8)]
    assert len({c.frame.y for c in lay.pip}) == 1
    assert lay.pip[0].frame.y > lay.hook[0].frame.y + HOOK_H
    assert lay.frames[0].frame.y > lay.pip[0].frame.y + PIP_H
    assert [c.time_s for c in lay.pip] == list(times)
    assert not any(c.first_in_row for c in lay.pip)
    without = contact_sheet.layout(HOOK_FRAMES, 6)
    assert without.pip == [] and without.frames[0].frame.y == lay.hook[0].frame.y + (
        HOOK_H + contact_sheet.LABEL_H + contact_sheet.STRIP_H + GUTTER
    )
    row = PIP_H + contact_sheet.LABEL_H + contact_sheet.STRIP_H + GUTTER
    assert lay.height == without.height + row


def test_pip_cell_crops_the_window_and_draws_the_circle_and_the_face_box() -> None:
    still = Image.new("RGB", (1080, 1920), (0, 0, 0))
    ImageDraw.Draw(still).rectangle((0, 100, 1079, 1179), fill=(30, 60, 90))  # the window
    measured = _measured()
    cell = contact_sheet.pip_cell(still, measured, measured.face)
    assert cell.size == (PIP_W, PIP_H)
    assert cell.getpixel((PIP_W // 2, PIP_H // 2)) == (30, 60, 90)  # window content, scaled
    assert cell.getpixel((PIP_W // 2, 0)) == contact_sheet.CIRCLE_COLOUR  # the circle's top
    scale = PIP_W / 1080
    x, y = round((286 + 260) * scale), round((114 - 100) * scale)  # top edge of the face box
    assert cell.getpixel((x, y)) == contact_sheet.FACE_COLOUR
    plain = contact_sheet.pip_cell(still, measured, None)
    assert plain.getpixel((x, y)) == (30, 60, 90)
    assert contact_sheet.pip_strip(measured.face) == contact_sheet.Strip("face 520x520", False)
    assert contact_sheet.pip_strip(None) == contact_sheet.Strip("no face", True)


def test_compose_image_draws_the_pip_row_when_given() -> None:
    hook = [_solid((HOOK_W, HOOK_H), (0, 0, 0))] * HOOK_FRAMES
    frames = [_solid((FRAME_W, FRAME_H), (0, 0, 0))]
    times = presenter.strip_times(6.0)
    pip = [_solid((PIP_W, PIP_H), (70 + i, 80, 90)) for i in range(8)]
    strips = [contact_sheet.Strip("face 1x1", False)] * 7 + [contact_sheet.Strip("no face", True)]
    image = contact_sheet.compose_image(hook, frames, None, "pip", pip=pip, pip_times=times,
                                        pip_strips=strips)  # fmt: skip
    lay = contact_sheet.layout(HOOK_FRAMES, 1, times)
    assert image.size == (lay.width, lay.height)
    for i, cell in enumerate(lay.pip):
        assert image.getpixel((cell.frame.x + 20, cell.frame.y + 20)) == (70 + i, 80, 90)
    last = lay.pip[-1]
    corner = (last.frame.x + last.frame.w - 3, last.frame.y + 2)
    assert image.getpixel(corner) == contact_sheet.MARK_COLOUR


def test_compose_draws_the_strip_stills_of_a_measured_job(media: Media, tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    (job.out_dir / "short.mp4").write_bytes(media.clip(duration_s=6.0, ext=".mp4").read_bytes())
    measured = _measured(faces=[_measured().face] * 7 + [None])
    presenter.still_path(job, 1).parent.mkdir(parents=True)
    for n in range(1, 9):
        Image.new("RGB", (1080, 1920), (n, 0, 0)).save(presenter.still_path(job, n))
    jobs.amend(job, presenter=measured)
    out = contact_sheet.compose(job)
    lay = contact_sheet.layout(HOOK_FRAMES, 6, measured.times_s)
    with Image.open(out) as saved:
        assert saved.size == (lay.width, lay.height)
    # A swept still leaves the row out rather than drawing it short.
    presenter.still_path(job, 3).unlink()
    out = contact_sheet.compose(job)
    with Image.open(out) as saved:
        assert saved.size == (lay.width, contact_sheet.layout(HOOK_FRAMES, 6).height)
