"""render (ticket 004): the pure RenderSpec builder (frames, beats, fixed-advance
caption boxes anchored at y 1460, fixed PIP geometry, palette), the component
registry the Node project exports, the driver's progress lines, and one real render
of the fixture through the Remotion composition checked with ffprobe."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from shortsmith import captions, ffmpeg, fixture, jobs, render
from shortsmith.contracts import (
    CaptionPage,
    Constraints,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    RenderSpec,
    Word,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber

WORDS = FakeTranscriber().transcribe(Path("unused.mp4")).words


def _plan() -> PicturePlan:
    request = PlanRequest(
        brief="Topic: a six-second synthetic clip.",
        style=PlanStyle(name="explainer"),
        style_note="explainer",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )
    return FakePlanner().plan_picture(request)


def _pages(plan: PicturePlan) -> list[CaptionPage]:
    return captions.page(WORDS, plan.keywords, captions.PagerNumbers(), duration_s=6.0)


def _spec() -> RenderSpec:
    plan = _plan()
    return render.build_spec(
        plan,
        _pages(plan),
        WORDS,
        presenter=Path("input/raw.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT),
        duration_s=fixture.DURATION_S,
    )


# --- registry (decision 9.2) ----------------------------------------------------------


def test_registry_lists_captions_and_pip_from_the_node_project() -> None:
    names = render.registry()
    assert "captions" in names and "pip" in names
    assert names == sorted(set(names))
    on_disk = json.loads(render.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert on_disk["components"] == names


# --- frames and beats -----------------------------------------------------------------


def test_spec_has_round_duration_times_fps_frames_and_beats_tile_them() -> None:
    spec = _spec()
    assert (spec.width, spec.height, spec.fps) == (1080, 1920, 30)
    assert spec.frames == round(fixture.DURATION_S * 30) == 180
    assert spec.beats[0].start_frame == 0 and spec.beats[-1].end_frame == 180
    for a, b in zip(spec.beats, spec.beats[1:], strict=False):
        assert a.end_frame == b.start_frame
    modes = [b.mode for b in spec.beats]
    assert modes[0] == "full" and "pip" in modes and "off" in modes
    assert spec.presenter.endswith("raw.mp4")


def test_beat_frames_round_to_the_nearest_frame() -> None:
    spec = _spec()
    by_id = {b.id: b for b in spec.beats}
    assert (by_id["b03"].start_frame, by_id["b03"].end_frame) == (30, 45)


# --- caption boxes (decision 6.2 / 6.3) ----------------------------------------------


def test_every_word_has_a_box_and_timing_from_the_transcript() -> None:
    spec = _spec()
    assert len(spec.captions) == 4
    first = spec.captions[0]
    assert [w.text for w in first.words] == ["hello", "there", "this"]
    assert first.words[0].start == WORDS[0].start and first.words[0].end == WORDS[0].end
    assert (first.start, first.end) == (0.16, 1.32)


def test_boxes_advance_by_the_fixed_gap_so_activation_never_moves_a_neighbour() -> None:
    numbers = render.EXPLAINER
    spec = _spec()
    line = spec.captions[0].words
    for left, right in zip(line, line[1:], strict=False):
        assert right.x == pytest.approx(left.x + left.width + numbers.captions.word_gap_px)
    # Each box is sized at the 1.08-scaled width (6.2), not the resting width.
    resting = render.text_width("hello", numbers.captions)
    assert line[0].width == pytest.approx(resting * numbers.captions.active_scale)


def test_one_line_block_bottom_sits_at_the_explainer_anchor_and_is_centred() -> None:
    numbers = render.EXPLAINER
    page = _spec().captions[0]
    assert page.lines == 1
    line_h = numbers.captions.size_px * numbers.captions.line_height
    assert page.words[0].y == pytest.approx(numbers.captions.anchor_y - line_h)
    assert all(w.height == pytest.approx(line_h) for w in page.words)
    left, right = page.words[0].x, page.words[-1].x + page.words[-1].width
    assert left == pytest.approx(1080 - right)
    assert right - left <= numbers.captions.max_width_px


def test_keyword_word_is_flagged_once_per_page_and_padded_for_its_box() -> None:
    numbers = render.EXPLAINER
    page = _spec().captions[0]  # keyword 1 -> "there"
    flagged = [w for w in page.words if w.keyword]
    assert [w.text for w in flagged] == ["there"]
    plain = render.text_width("there", numbers.captions) * numbers.captions.active_scale
    assert flagged[0].width == pytest.approx(plain + 2 * numbers.captions.keyword_pad_px)


def _page_of(texts: list[str], keyword: int | None = None) -> tuple[CaptionPage, list[Word]]:
    words = [
        Word(text=t, start=0.5 * i, end=0.5 * i + 0.4, segment=0) for i, t in enumerate(texts)
    ]
    page = CaptionPage(
        index=0,
        word_indices=list(range(len(texts))),
        texts=texts,
        start=0.0,
        end=1.0,
        keyword=keyword,
    )
    return page, words


def test_a_wide_page_wraps_to_two_lines_above_the_anchor() -> None:
    numbers = render.EXPLAINER
    page, words = _page_of(["remarkable", "discoveries", "await"])
    laid = render.layout_page(page, words, numbers.captions)
    assert laid.lines == 2
    line_h = numbers.captions.size_px * numbers.captions.line_height
    tops = sorted({w.y for w in laid.words})
    assert tops == pytest.approx([numbers.captions.anchor_y - 2 * line_h,
                                  numbers.captions.anchor_y - line_h])  # fmt: skip
    for y in tops:
        row = [w for w in laid.words if w.y == y]
        assert row[-1].x + row[-1].width - row[0].x <= numbers.captions.max_width_px


def test_a_page_needing_three_lines_is_a_pager_bug_and_raises() -> None:
    page, words = _page_of(
        ["incomprehensibilities", "counterrevolutionaries", "electroencephalographically"]
    )
    with pytest.raises(render.LayoutError, match="three lines"):
        render.layout_page(page, words, render.EXPLAINER.captions)


# --- PIP geometry and palette (decisions 3.3, 6.3) -----------------------------------


def test_fixed_pip_is_a_300_px_circle_touching_the_caption_block_from_above() -> None:
    numbers = render.EXPLAINER
    pip = render.fixed_pip((1080, 1920), numbers)
    assert pip.diameter == 300 and pip.left == 60
    line_h = numbers.captions.size_px * numbers.captions.line_height
    assert pip.top + pip.diameter <= numbers.captions.anchor_y - numbers.captions.max_lines * line_h
    assert pip.top + pip.diameter == 1260
    # The crop window is the full source width, square, from the top (013 measures it).
    assert (pip.window_left, pip.window_top, pip.window_size) == (0, 0, 1080)


def test_landscape_source_window_is_still_a_square_inside_the_source() -> None:
    pip = render.fixed_pip((1920, 1080), render.EXPLAINER)
    assert pip.window_size == 1080 and pip.window_left == 420 and pip.window_top == 0


def test_spec_carries_the_palette_gradient_and_caption_style() -> None:
    spec = _spec()
    assert len(spec.palette.gradient) == 2 and spec.palette.accent == "#FFD60A"
    assert spec.caption_style.font_family == "Poppins" and spec.caption_style.size_px == 74
    assert spec.caption_style.active_color == "#FFD60A"
    assert spec.caption_style.keyword_fg == "#111" and spec.caption_style.keyword_bg == "#FFD60A"


# --- driver protocol ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("progress 0/180", (0, 180)),
        ("progress 179/180\n", (179, 180)),
        ("Rendering frames", None),
        ("", None),
    ],
)
def test_parse_progress(line: str, expected: tuple[int, int] | None) -> None:
    assert render.parse_progress(line) == expected


# --- the real thing -------------------------------------------------------------------


def test_render_writes_a_silent_h264_picture_with_progress(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = jobs.create(tmp_path)
    shutil.copyfile(fixture_clip, job.input_dir / "raw.mp4")
    plan = _plan()
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job.work_dir / "asr.json").write_text(
        FakeTranscriber().transcribe(fixture_clip).model_dump_json(indent=2), encoding="utf-8"
    )
    (job.work_dir / "captions.json").write_text(
        json.dumps([p.model_dump() for p in _pages(plan)]), encoding="utf-8"
    )
    seen: list[int] = []
    out = render.render(job, on_progress=seen.append)
    assert out == job.work_dir / "picture.mp4" and out.is_file()
    assert (job.work_dir / "render_spec.json").is_file()
    assert (job.work_dir / "render.log").is_file()
    assert seen and seen[-1] == 100 and seen == sorted(seen)
    info = ffmpeg.probe(out)
    streams = info["streams"]
    assert [s["codec_type"] for s in streams] == ["video"]  # silent: no audio stream
    video = streams[0]
    assert video["codec_name"] == "h264"
    assert (video["width"], video["height"]) == (1080, 1920)
    assert int(video["nb_frames"]) == 180
    assert video["r_frame_rate"] == "30/1"
