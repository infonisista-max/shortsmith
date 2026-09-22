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
from PIL import Image

from shortsmith import assets, captions, ffmpeg, fixture, jobs, presenter, render, styles
from shortsmith.contracts import (
    AssetManifest,
    Beat,
    BedQuery,
    Captions,
    Constraints,
    Crop,
    CutPlan,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    RenderSpec,
    SoundStory,
    Span,
    ValidatedPlan,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media

WORDS = FakeTranscriber().transcribe(Path("unused.mp4")).words
EXPLAINER = render.style_numbers("explainer")  # from styles/explainer.md front matter (008)
EXPLAINER_SPEC = render.loaded_styles()["explainer"]


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


def _captions(plan: PicturePlan) -> Captions:
    return captions.build(FakeTranscriber().transcribe(Path("unused.mp4")), plan, EXPLAINER_SPEC)


def _spec() -> RenderSpec:
    plan = _plan()
    return render.build_spec(
        plan,
        _captions(plan),
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
        _captions(plan).model_dump_json(), encoding="utf-8"
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


def test_registry_exports_photo_and_card_after_016() -> None:
    assert {"photo", "card"} <= set(render.registry())


# --- photo and card (ticket 016; decisions 4.1, 4.4, 5.3) -------------------------------

SPECS = styles.load_all(render.registry())
PORTRAIT_SKY = "slow colour gradient sky"


def _sourced(tmp_path: Path, plan: PicturePlan, **sources: assets.ImageSource) -> AssetManifest:
    """The fake plan sourced through fakes: web finds landscapes (cards), commons the
    one portrait the photo beat asks for."""
    job_dir = tmp_path / "job"
    (job_dir / "work").mkdir(parents=True, exist_ok=True)
    validated = ValidatedPlan(picture=plan, sound=SoundStory(
        prompt_version="t", theme="t", mood_curve=[], bed_query=BedQuery(theme="t", mood="t",
        energy=3), cues=[]))  # fmt: skip
    return assets.source_assets(
        validated, [], "any", spec=SPECS["explainer"], job_dir=job_dir,
        sources=sources or {
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
    )  # fmt: skip


def _visual_spec(tmp_path: Path, plan: PicturePlan | None = None,
                 manifest: AssetManifest | None = None) -> RenderSpec:  # fmt: skip
    plan = plan or _plan()
    manifest = manifest or _sourced(tmp_path, plan)
    return render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=manifest, job_dir=tmp_path / "job",
    )  # fmt: skip


def test_photo_and_card_beats_carry_their_asset_and_other_kinds_do_not(tmp_path: Path) -> None:
    spec = _visual_spec(tmp_path)
    visual = {b.id: b.visual for b in spec.beats}
    photo, card = visual["b03"], visual["b04"]
    assert photo is not None and photo.treatment == "photo" and photo.card is None
    assert card is not None and card.treatment == "card" and card.card is not None
    assert Path(photo.src).is_absolute() and Path(photo.src).is_file()
    assert (photo.width, photo.height) == (1080, 1920)
    assert all(visual[b] is None for b in visual if b not in ("b03", "b04"))


def test_photo_ken_burns_numbers_come_from_the_style(tmp_path: Path) -> None:
    photo = _visual_spec(tmp_path).beats[2].visual
    assert photo is not None
    assert (photo.scale_from, photo.scale_to) == (1.10, 1.16)  # explainer broll.motion.photo


def _photo_beat(i: int) -> Beat:
    return Beat.model_validate({
        "id": f"b{i}", "start": float(i - 1), "end": float(i), "mode": "pip", "kind": "photo",
        "motion": "ken_burns_in", "subject_kind": "concept", "query": PORTRAIT_SKY,
        "query_fallback": "sky", "source_intent": "search", "asset_id": f"a{i}",
    })  # fmt: skip


def test_ken_burns_alternates_in_out_and_pan_direction_per_consecutive_beat(
    tmp_path: Path,
) -> None:
    plan = _plan().model_copy(update={"beats": [_photo_beat(i) for i in range(1, 4)]})
    beats = _visual_spec(tmp_path, plan).beats
    scales = [(b.visual.scale_from, b.visual.scale_to) for b in beats if b.visual]
    assert scales == [(1.10, 1.16), (1.16, 1.10), (1.10, 1.16)]
    pans = [b.visual.pan_px for b in beats if b.visual]
    assert pans[0] > 0 > pans[1] and pans[2] > 0


def test_a_redressed_beat_carries_the_new_crop(tmp_path: Path) -> None:
    plan = _plan().model_copy(update={"beats": [_photo_beat(1), _photo_beat(2)]})
    commons = assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)})
    manifest = _sourced(tmp_path, plan, commons=commons)
    rescued = manifest.beats[1].model_copy(
        update={"fallback_rung": 3, "redressed_from": "a1", "asset_id": "a1",
                "crop": assets.redress_crop(1)})  # fmt: skip
    manifest = manifest.model_copy(update={"beats": [manifest.beats[0], rescued]})
    first, second = (b.visual for b in _visual_spec(tmp_path, plan, manifest).beats)
    assert first is not None and second is not None and first.src == second.src
    assert (second.zoom, second.focus_x) == (1.15, 0.35) != (first.zoom, first.focus_x)


def test_a_rung_4_beat_swaps_to_pip_over_the_gradient(tmp_path: Path) -> None:
    plan = _plan()
    empty = assets.FakeImageSource("web", nothing_found=True)
    spec = _visual_spec(tmp_path, plan, _sourced(tmp_path, plan, web=empty))
    b04 = next(b for b in spec.beats if b.id == "b04")
    assert (b04.mode, b04.visual) == ("pip", None)
    b08 = next(b for b in spec.beats if b.id == "b08")  # an `off` list beat, rescued too
    assert b08.mode == "pip"


def test_card_width_is_min_980_and_650_times_aspect_never_over_1_5x() -> None:
    """5.3's width is the card's own (border included): the reference card measures
    ~982 px across on a 1080 frame (dyson_05)."""
    border = EXPLAINER.broll.card_border_px
    assert render.card_image_size(1600, 900, border)[0] == 980 - 2 * border
    assert render.card_image_size(900, 1600, border)[0] == pytest.approx(
        650 * 900 / 1600 - 2 * border
    )
    assert render.card_image_size(1000, 1000, border) == (650 - 2 * border, 650 - 2 * border)
    assert render.card_image_size(400, 300, border) == (600, 450)  # 1.5x of 400
    card = render.card_visual("x.png", 1600, 900, strip_text="", ring=False, index=0,
                              crop=Crop(), numbers=EXPLAINER).card  # fmt: skip
    assert card is not None and card.width == 980


@pytest.mark.parametrize("size", [(1600, 900), (1000, 1000), (900, 1600), (500, 2000),
                                  (4000, 1000)])  # fmt: skip
@pytest.mark.parametrize("strip", ["", "India Gate · Delhi"])
def test_cards_end_above_y_1240_at_full_push_and_tilt(size: tuple[int, int], strip: str) -> None:
    visual = render.card_visual("x.png", *size, strip_text=strip, ring=False, index=0,
                                crop=Crop(), numbers=EXPLAINER)  # fmt: skip
    assert render.card_bottom(visual) <= EXPLAINER.broll.card_max_bottom_y + 1e-6
    assert visual.card is not None and visual.card.top >= 0


@pytest.mark.parametrize("size", [(1600, 900), (1000, 1000), (900, 1600)])
def test_cards_sit_above_the_pip_like_the_reference_frames(size: tuple[int, int]) -> None:
    """The reference cards (dyson_05, nkb_06) end about 35 px above the PIP circle."""
    visual = render.card_visual("x.png", *size, strip_text="label", ring=False, index=0,
                                crop=Crop(), numbers=EXPLAINER)  # fmt: skip
    pip_top = EXPLAINER.broll.pip_top
    assert render.card_bottom(visual) == pytest.approx(pip_top - render.PIP_GAP_PX)


def test_card_look_numbers_come_from_the_style() -> None:
    visual = render.card_visual("x.png", 1600, 900, strip_text="t", ring=True, index=0,
                                crop=Crop(), numbers=EXPLAINER)  # fmt: skip
    card = visual.card
    assert card is not None
    assert (card.border_px, card.rotate_deg, card.ring_color) == (14, -1.5, "#E53935")
    assert (card.cover_scale_from, card.cover_scale_to) == (1.45, 2.1)
    assert card.ring and card.strip_text == "t" and card.strip_px > 0
    assert card.left + card.width / 2 == pytest.approx(render.WIDTH / 2)
    no_strip = render.card_visual("x.png", 1600, 900, strip_text="", ring=False, index=0,
                                  crop=Crop(), numbers=EXPLAINER)  # fmt: skip
    assert no_strip.card is not None and no_strip.card.strip_px == 0


def test_the_card_strip_shows_the_lower_third_label(tmp_path: Path) -> None:
    card = _visual_spec(tmp_path).beats[3].visual
    assert card is not None and card.card is not None
    assert card.card.strip_text == "India Gate · Delhi"


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


# --- caption boxes (decisions 6.2, 6.3; laid out by the pager, ticket 010) ----------


def test_the_spec_carries_the_pagers_boxes_as_given() -> None:
    plan = _plan()
    paged = _captions(plan)
    spec = _spec()
    assert len(spec.captions) == len(paged.pages) == 5  # the finale hides the last burst
    for drawn, page in zip(spec.captions, paged.pages, strict=True):
        assert (drawn.index, drawn.start, drawn.end, drawn.lines) == (
            page.index, page.start, page.end, page.lines
        )
        assert drawn.words == page.words
    first = spec.captions[0]
    assert [w.text for w in first.words] == ["hello", "there"]
    assert first.words[0].start == WORDS[0].start and first.words[0].end == WORDS[0].end
    assert (first.start, first.end) == (0.16, 1.16)


def test_the_spec_carries_the_beats_with_two_line_pages() -> None:
    paged = Captions(pages=[], beats_with_two_lines=["b03", "b04"])
    spec = render.build_spec(
        _plan(), paged, presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
    )  # fmt: skip
    assert spec.beats_with_two_lines == ["b03", "b04"]
    assert _spec().beats_with_two_lines == []  # the fixture's pages are one line each


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


def _pixel(frame: tuple[int, int, bytes], x: int, y: int) -> tuple[int, int, int]:
    width, _, data = frame
    i = 3 * (y * width + x)
    return data[i], data[i + 1], data[i + 2]


def _near(a: tuple[int, ...], b: tuple[int, ...], tolerance: int = 30) -> bool:
    return all(abs(p - q) <= tolerance for p, q in zip(a, b, strict=True))


def test_the_photo_and_the_card_are_drawn_from_their_asset_files(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """016 end to end through Remotion: at 1.25 s (b03) the frame shows the portrait
    photo's colour full-bleed; at 1.75 s (b04) the card centre shows the card image and
    the cover behind it is the same image darkened."""
    plan = _plan()
    job = _job_with(tmp_path, fixture_clip, plan)
    manifest_in_job = assets.source_assets(
        ValidatedPlan(picture=plan, sound=SoundStory(
            prompt_version="t", theme="t", mood_curve=[],
            bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[])),
        [], "any", spec=SPECS["explainer"], job_dir=job.path,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
    )  # fmt: skip
    assets.write_manifest(job.path, manifest_in_job)
    render.RemotionRenderer().render(job)
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    frames = ffmpeg.frames_rgb(job.work_dir / "picture.mp4", fps=4, width=1080, duration_s=2.0)

    def colour(beat_id: str) -> tuple[int, int, int]:
        decided = manifest_in_job.beat(beat_id)
        assert decided is not None and decided.asset_id is not None
        record = manifest_in_job.asset(decided.asset_id)
        assert record is not None
        with Image.open(job.path / record.file) as image:
            data = image.convert("RGB").tobytes()
            i = 3 * ((image.height // 2) * image.width + image.width // 2)
        return data[i], data[i + 1], data[i + 2]

    assert _near(_pixel(frames[5], 900, 700), colour("b03"))
    card = next(b for b in spec.beats if b.id == "b04").visual
    assert card is not None and card.card is not None
    cx = round(card.card.left + card.card.width / 2)
    cy = round(card.card.top + card.card.border_px + card.card.image_height / 2)
    centre = _pixel(frames[7], cx, cy)
    assert _near(centre, colour("b04"))
    cover = _pixel(frames[7], 1000, 1800)
    assert sum(cover) < sum(centre)
