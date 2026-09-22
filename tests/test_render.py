"""render (ticket 004): the pure RenderSpec builder (frames, beats, fixed-advance
caption boxes anchored at y 1460, fixed PIP geometry, palette), the component
registry the Node project exports, the driver's progress lines, and one real render
of the fixture through the Remotion composition checked with ffprobe.

Ticket 005 adds the ffmpeg half: the CFR no-B-frame presenter cut with the 1.5x crop
rule, the voice stem through the 7.3 chain, and the mux with `-c:v copy`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from shortsmith import captions, ffmpeg, fixture, jobs, presenter, render
from shortsmith.contracts import (
    CaptionPage,
    Constraints,
    CutPlan,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    RenderSpec,
    Span,
    Word,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media

WORDS = FakeTranscriber().transcribe(Path("unused.mp4")).words
EXPLAINER = render.style_numbers("explainer")  # from styles/explainer.md front matter (008)


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
        presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT),
        duration_s=fixture.DURATION_S,
    )


def _job_with(tmp_path: Path, clip: Path, plan: PicturePlan | None = None) -> jobs.Job:
    """A job past `sourcing` on disk: raw.mp4, plan.json, asr.json, captions.json."""
    job = jobs.create(tmp_path)
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    plan = plan or _plan()
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job.work_dir / "asr.json").write_text(
        FakeTranscriber().transcribe(clip).model_dump_json(indent=2), encoding="utf-8"
    )
    (job.work_dir / "captions.json").write_text(
        json.dumps([p.model_dump() for p in _pages(plan)]), encoding="utf-8"
    )
    return job


def _streams(path: Path) -> dict[str, dict[str, object]]:
    return {s["codec_type"]: s for s in ffmpeg.probe(path)["streams"]}


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
    assert spec.presenter.endswith("cut.mp4")


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
    numbers = EXPLAINER
    spec = _spec()
    line = spec.captions[0].words
    for left, right in zip(line, line[1:], strict=False):
        assert right.x == pytest.approx(left.x + left.width + numbers.captions.word_gap_px)
    # Each box is sized at the 1.08-scaled width (6.2), not the resting width.
    resting = render.text_width("hello", numbers.captions)
    assert line[0].width == pytest.approx(resting * numbers.captions.active_scale)


def test_one_line_block_bottom_sits_at_the_explainer_anchor_and_is_centred() -> None:
    numbers = EXPLAINER
    page = _spec().captions[0]
    assert page.lines == 1
    line_h = numbers.captions.size_px * numbers.captions.line_height
    assert page.words[0].y == pytest.approx(numbers.captions.anchor_y - line_h)
    assert all(w.height == pytest.approx(line_h) for w in page.words)
    left, right = page.words[0].x, page.words[-1].x + page.words[-1].width
    assert left == pytest.approx(1080 - right)
    assert right - left <= numbers.captions.max_width_px


def test_keyword_word_is_flagged_once_per_page_and_padded_for_its_box() -> None:
    numbers = EXPLAINER
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
    numbers = EXPLAINER
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
        render.layout_page(page, words, EXPLAINER.captions)


# --- PIP geometry and palette (decisions 3.3, 6.3) -----------------------------------


def test_fixed_pip_is_a_300_px_circle_touching_the_caption_block_from_above() -> None:
    numbers = EXPLAINER
    pip = render.fixed_pip((1080, 1920), numbers)
    assert pip.diameter == 300 and pip.left == 60
    line_h = numbers.captions.size_px * numbers.captions.line_height
    assert pip.top + pip.diameter <= numbers.captions.anchor_y - numbers.captions.max_lines * line_h
    assert pip.top + pip.diameter == 1260
    # The crop window is the full source width, square, from the top (013 measures it).
    assert (pip.window_left, pip.window_top, pip.window_size) == (0, 0, 1080)


def test_landscape_source_window_is_still_a_square_inside_the_source() -> None:
    pip = render.fixed_pip((1920, 1080), EXPLAINER)
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


# --- ticket 005: the presenter cut (decisions 2.1, 9.1) ------------------------------


def _with_cut(
    plan: PicturePlan, *, keep: list[Span], drop: list[Span] | None = None
) -> PicturePlan:
    return plan.model_copy(update={"cut": CutPlan(keep=keep, drop=drop or [])})


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ((1080, 1920), (1080, 1920, 0, 0)),  # already 9:16: no crop
        ((3840, 2160), (1216, 2160, 1312, 0)),  # 4K landscape: full height, centred width
        ((1080, 2400), (1080, 1920, 0, 240)),  # too tall: full width, centred height
        ((720, 1280), (720, 1280, 0, 0)),  # exactly 1.5x: allowed
    ],
)
def test_crop_window_is_the_largest_centred_9_16_with_even_edges(
    source: tuple[int, int], expected: tuple[int, int, int, int]
) -> None:
    assert presenter.crop_window(source) == expected


@pytest.mark.parametrize("source", [(640, 1136), (1920, 1080), (1280, 720), (1000, 1000)])
def test_crop_window_refuses_a_source_needing_more_than_1_5x_upscale(
    source: tuple[int, int],
) -> None:
    with pytest.raises(presenter.UpscaleExceeded, match="1.5x"):
        presenter.crop_window(source)


def test_span_filter_trims_and_concatenates_video_and_audio() -> None:
    spans = [Span(start=3.0, end=3.5), Span(start=0.0, end=3.0)]
    graph = render.span_filter(spans, video=True, audio=True)
    assert "[0:v]trim=start=3.000:end=3.500,setpts=PTS-STARTPTS[v0]" in graph
    assert "[0:a]atrim=start=0.000:end=3.000,asetpts=PTS-STARTPTS[a1]" in graph
    assert graph.endswith("[v0][a0][v1][a1]concat=n=2:v=1:a=1[vc][ac]")
    audio_only = render.span_filter(spans, video=False, audio=True)
    assert "trim=" not in audio_only.replace("atrim=", "")
    assert audio_only.endswith("[a0][a1]concat=n=2:v=0:a=1[ac]")


def test_cut_presenter_writes_a_cfr_h264_cut_with_no_b_frames_and_the_audio(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _job_with(tmp_path, fixture_clip)
    out = render.cut_presenter(job)
    assert out == job.work_dir / "cut.mp4" and out.is_file()
    streams = _streams(out)
    assert set(streams) == {"video", "audio"}
    video = streams["video"]
    assert video["codec_name"] == "h264"
    assert int(video["has_b_frames"]) == 0  # type: ignore[call-overload]
    assert video["r_frame_rate"] == "30/1" and video["avg_frame_rate"] == "30/1"  # CFR
    assert (video["width"], video["height"]) == (1080, 1920)
    assert int(video["nb_frames"]) == 180  # type: ignore[call-overload]


def test_cut_presenter_applies_the_cut_list(tmp_path: Path, fixture_clip: Path) -> None:
    plan = _with_cut(_plan(), keep=[Span(start=0.0, end=6.0)], drop=[Span(start=1.0, end=2.0)])
    job = _job_with(tmp_path, fixture_clip, plan)
    out = render.cut_presenter(job)
    streams = _streams(out)
    assert int(streams["video"]["nb_frames"]) == 150  # type: ignore[call-overload]
    assert float(streams["audio"]["duration"]) == pytest.approx(5.0, abs=0.05)  # type: ignore[arg-type]


def test_cut_presenter_centre_crops_a_landscape_source_to_1080x1920(
    tmp_path: Path, media: Media
) -> None:
    clip = media.clip(duration_s=2.0, width=2560, height=1440)  # crop 810x1440, 1.33x up
    plan = _with_cut(_plan(), keep=[Span(start=0.0, end=2.0)])
    job = _job_with(tmp_path, clip, plan)
    out = render.cut_presenter(job)
    video = _streams(out)["video"]
    assert (video["width"], video["height"]) == (1080, 1920)
    assert int(video["nb_frames"]) == 60  # type: ignore[call-overload]


def test_cut_presenter_refuses_a_source_over_the_1_5x_rule(tmp_path: Path, media: Media) -> None:
    clip = media.clip(duration_s=2.0, width=640, height=1136)  # 1.69x up
    plan = _with_cut(_plan(), keep=[Span(start=0.0, end=2.0)])
    job = _job_with(tmp_path, clip, plan)
    with pytest.raises(presenter.UpscaleExceeded, match="1.5x"):
        render.cut_presenter(job)
    assert not (job.work_dir / "cut.mp4").exists()


# --- ticket 005: voice stem, master and mux (decisions 7.3, 9.1, 10.1) ----------------


def test_voice_stem_is_mono_48k_pcm_at_minus_19_lufs(tmp_path: Path, fixture_clip: Path) -> None:
    job = _job_with(tmp_path, fixture_clip)
    out = render.voice_stem(job)
    assert out == job.work_dir / "stems" / "voice.wav" and out.is_file()
    audio = _streams(out)["audio"]
    assert audio["codec_name"] == "pcm_s16le"
    assert int(audio["channels"]) == 1 and int(audio["sample_rate"]) == 48000  # type: ignore[call-overload]
    assert float(audio["duration"]) == pytest.approx(6.0, abs=0.05)  # type: ignore[arg-type]
    loud = ffmpeg.measure_loudness(out)
    assert loud.integrated == pytest.approx(render.VOICE_LUFS, abs=1.0)
    assert loud.true_peak <= render.VOICE_TP + 0.1


def test_voice_chain_is_the_7_3_graph_verbatim() -> None:
    chain = render.voice_chain()
    assert chain.startswith("aformat=channel_layouts=stereo,pan=mono|c0=0.5*c0+0.5*c1")
    assert ",highpass=f=80," in chain
    assert chain.endswith("acompressor=threshold=-18dB:ratio=2.5")


def _synthetic_picture(job: jobs.Job, media: Media) -> Path:
    """A silent 6 s 1080x1920 H.264 standing in for the Remotion output."""
    picture = job.work_dir / "picture.mp4"
    shutil.copyfile(media.clip(duration_s=6.0, audio=False, ext=".mp4"), picture)
    return picture


def test_mux_copies_the_picture_stream_and_masters_the_voice(
    tmp_path: Path, fixture_clip: Path, media: Media
) -> None:
    job = _job_with(tmp_path, fixture_clip)
    picture = _synthetic_picture(job, media)
    render.voice_stem(job)
    out = render.mux(job)
    assert out == job.out_dir / "short.mp4" and out.is_file()
    streams = _streams(out)
    assert set(streams) == {"video", "audio"}
    assert ffmpeg.video_md5(out) == ffmpeg.video_md5(picture)  # revision proof (a)
    mix = job.work_dir / "stems" / "mix.wav"
    assert mix.is_file() and (job.work_dir / "stems" / "voice.wav").is_file()
    loud = ffmpeg.measure_loudness(mix)
    assert loud.integrated == pytest.approx(render.MASTER_LUFS, abs=0.5)  # T4
    assert loud.true_peak <= render.MASTER_TP
    # T4 is measured on the delivered file (10.1): the AAC encode overshoots the WAV's
    # peaks by a few tenths of a dB, so the master leaves it headroom (006).
    delivered = ffmpeg.measure_loudness(out)
    assert delivered.integrated == pytest.approx(render.MASTER_LUFS, abs=0.5)
    assert delivered.true_peak <= render.MASTER_TP


def test_master_chain_leaves_aac_headroom_under_the_true_peak_ceiling() -> None:
    measured = ffmpeg.Loudness(
        integrated=-19.3, true_peak=-6.1, lra=4.0, threshold=-29.5, offset=5.3
    )
    chain = render.master_chain(measured)
    assert f"TP={render.MASTER_TP - render.AAC_HEADROOM_DB:g}" in chain
    assert f"TP={render.MASTER_TP:g}:" not in chain
    assert render.MASTER_TP == -1.5 and 0 < render.AAC_HEADROOM_DB <= 1.0


def test_spec_for_job_reads_the_cut_as_the_presenter_source(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _job_with(tmp_path, fixture_clip)
    render.cut_presenter(job)
    spec = render.spec_for_job(job)
    assert Path(spec.presenter) == job.work_dir / "cut.mp4"
    assert (spec.source_width, spec.source_height) == (1080, 1920)
    assert spec.frames == 180


def test_spec_for_job_without_a_cut_names_the_missing_file(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _job_with(tmp_path, fixture_clip)
    with pytest.raises(render.RenderError, match="cut.mp4"):
        render.spec_for_job(job)


# --- the real thing -------------------------------------------------------------------


def test_remotion_renderer_runs_the_whole_step_to_out_short_mp4(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _job_with(tmp_path, fixture_clip)
    seen: list[int] = []
    out = render.RemotionRenderer().render(job, on_progress=seen.append)
    assert out == job.out_dir / "short.mp4" and out.is_file()
    picture = job.work_dir / "picture.mp4"
    assert picture.is_file() and (job.work_dir / "cut.mp4").is_file()
    assert (job.work_dir / "render_spec.json").is_file()
    assert (job.work_dir / "render.log").is_file()
    assert seen and seen[-1] == 100 and seen == sorted(seen)
    streams = ffmpeg.probe(picture)["streams"]
    assert [s["codec_type"] for s in streams] == ["video"]  # silent: no audio stream
    video = streams[0]
    assert video["codec_name"] == "h264"
    assert (video["width"], video["height"]) == (1080, 1920)
    assert int(video["nb_frames"]) == 180
    assert video["r_frame_rate"] == "30/1"
    short = _streams(out)
    assert set(short) == {"video", "audio"}
    assert int(short["video"]["nb_frames"]) == 180  # type: ignore[call-overload]
    assert ffmpeg.video_md5(out) == ffmpeg.video_md5(picture)
