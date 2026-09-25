"""render (ticket 004): the pure RenderSpec builder (frames, beats, fixed-advance
caption boxes anchored at y 1460, the PIP geometry - measured by 013, the 004 fixed
fallback otherwise - palette), the component
registry the Node project exports, the driver's progress lines, and one real render
of the fixture through the Remotion composition checked with ffprobe.

Ticket 005 adds the ffmpeg half: the CFR no-B-frame presenter cut with the 1.5x crop
rule, the voice stem through the 7.3 chain, and the mux with `-c:v copy`."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import (
    assets,
    captions,
    ffmpeg,
    fixture,
    geo,
    infographics,
    jobs,
    presenter,
    render,
    rights,
    sound,
    styles,
)
from shortsmith.contracts import (
    AssetManifest,
    Beat,
    BedQuery,
    CaptionPage,
    Captions,
    Constraints,
    CounterPlan,
    Crop,
    CutPlan,
    Event,
    FaceBox,
    MapMarker,
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


def _plan_request() -> PlanRequest:
    return PlanRequest(
        brief="Topic: a six-second synthetic clip.",
        style=PlanStyle(name="explainer"),
        style_note="explainer",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def _plan() -> PicturePlan:
    return FakePlanner().plan_picture(_plan_request())


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


def test_only_the_kinds_with_a_base_still_carry_their_asset(tmp_path: Path) -> None:
    """A photo and a card beat draw their asset as the beat (016); after 027 a `list`
    and a `wall` draw theirs as the dimmed base under the set piece. Every other kind -
    the presenter, the hook, the `split` (its asset is the badge) and the finale - has
    no visual of its own."""
    spec = _visual_spec(tmp_path)
    visual = {b.id: b.visual for b in spec.beats}
    photo, card = visual["b03"], visual["b04"]
    assert photo is not None and photo.treatment == "photo" and photo.card is None
    assert card is not None and card.treatment == "card" and card.card is not None
    assert Path(photo.src).is_absolute() and Path(photo.src).is_file()
    assert (photo.width, photo.height) == (1080, 1920)
    assert (photo.dim, card.dim) == (0.0, 0.0)
    base = {b: visual[b] for b in ("b08", "b10")}  # the list and the wall
    assert all(v is not None and v.treatment == "photo" and v.dim > 0 for v in base.values())
    carriers = ("b03", "b04", "b08", "b10")
    assert all(visual[b] is None for b in visual if b not in carriers)


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


# --- set pieces and overlays (ticket 026; decisions 3.2, 3.4, 4.1, 4.2, 6.3) -----------


def _only(manifest: AssetManifest, *keep: str) -> AssetManifest:
    """The manifest with every hook-card alias but `keep` resolved to nothing."""
    aliases = {k: (v if k in keep else None) for k, v in manifest.aliases.items()}
    return manifest.model_copy(update={"aliases": aliases})


def test_the_hook_beat_carries_its_title_and_three_cards_in_plan_order(tmp_path: Path) -> None:
    plan = _plan()
    spec = _visual_spec(tmp_path, plan)
    hook = next(b for b in spec.beats if b.id == "b02").hook
    assert hook is not None
    assert " ".join(hook.title_lines) == plan.hook.title
    assert len(hook.cards) == EXPLAINER.broll.hook_cards == 3
    manifest = _sourced(tmp_path, plan)
    wanted = [manifest.aliases[i] for i in plan.hook.card_asset_ids]
    assert all(Path(c.src).is_absolute() and Path(c.src).is_file() for c in hook.cards)
    assert len({c.src for c in hook.cards}) == 3 and len(set(wanted)) == 3
    assert hook.cards[0].left < hook.cards[1].left  # left slot, then the right one


def test_fewer_than_three_hook_assets_give_one_centred_card(tmp_path: Path) -> None:
    plan = _plan()
    manifest = _only(_sourced(tmp_path, plan), "a1")
    hook = next(b for b in _visual_spec(tmp_path, plan, manifest).beats if b.id == "b02").hook
    assert hook is not None and len(hook.cards) == 1
    card = hook.cards[0]
    assert card.left + card.box_width / 2 == pytest.approx(render.WIDTH / 2)


def test_a_hook_with_no_resolved_asset_still_draws_its_title(tmp_path: Path) -> None:
    plan = _plan()
    manifest = _only(_sourced(tmp_path, plan))
    hook = next(b for b in _visual_spec(tmp_path, plan, manifest).beats if b.id == "b02").hook
    assert hook is not None and hook.cards == [] and hook.title_lines


def test_hook_cards_end_above_the_caption_block(tmp_path: Path) -> None:
    plan = _plan()
    hook = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == "b02").hook
    assert hook is not None
    block_top = styles.caption_block_top(EXPLAINER.captions)
    assert max(c.top + c.box_height for c in hook.cards) <= block_top
    assert min(c.left for c in hook.cards) >= render.SAFE_LEFT
    assert max(c.left + c.box_width for c in hook.cards) <= render.WIDTH - render.SAFE_LEFT


def test_the_hook_title_wraps_to_at_most_two_lines_inside_the_caption_width() -> None:
    long_title = "Why this one small change made everything suddenly cheaper"
    plan = _plan()
    plan = plan.model_copy(update={"hook": plan.hook.model_copy(update={"title": long_title})})
    spec = render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
    )  # fmt: skip
    hook = next(b for b in spec.beats if b.id == "b02").hook
    assert hook is not None and 1 <= len(hook.title_lines) <= render.HOOK_TITLE_MAX_LINES
    assert " ".join(hook.title_lines) == long_title
    style = EXPLAINER.captions
    for line in hook.title_lines:
        width = captions.measure(line, family=style.font_family, weight=style.font_weight,
                                 size_px=hook.title_font_px,
                                 letter_spacing_px=style.letter_spacing_px)  # fmt: skip
        assert width <= style.max_width_px + 1e-6


def test_the_cold_open_beat_is_full_frame_with_the_research_punch_in() -> None:
    cold_open = _spec().beats[0]
    assert cold_open.mode == "full"
    punch = cold_open.punch_in
    assert punch is not None
    assert (punch.scale_from, punch.settle_to, punch.settle_s) == (1.22, 1.03, 0.9)
    assert (punch.contrast, punch.saturate, punch.origin_y) == (1.06, 1.08, 0.30)
    assert all(b.punch_in is None for b in _spec().beats if b.mode != "full")


def test_the_finale_carries_the_presenter_circle_the_payoff_word_and_the_hook_cards(
    tmp_path: Path,
) -> None:
    plan = _plan()
    spec = _visual_spec(tmp_path, plan)
    beat = next(b for b in spec.beats if b.id == plan.finale.beat_id)
    finale = beat.finale
    assert beat.mode == "off" and finale is not None
    assert finale.text == plan.finale.text
    assert finale.circle_diameter == render.FINALE_DIAMETER
    assert finale.circle_left + finale.circle_diameter / 2 == pytest.approx(render.WIDTH / 2)
    assert finale.ring_color == EXPLAINER.palette.accent
    assert finale.fade_s == 0.35  # explainer broll.motion.finale.duration_s
    assert len(finale.cards) == 3
    assert all(b.finale is None for b in spec.beats if b.id != plan.finale.beat_id)


def test_a_finale_outside_the_style_length_fails_the_build() -> None:
    plan = _plan()
    beats = list(plan.beats)
    beats[-1] = beats[-1].model_copy(update={"start": 3.0})  # 3.0 s, over finale.max_s
    beats[-2] = beats[-2].model_copy(update={"end": 3.0})
    plan = plan.model_copy(update={"beats": beats})
    with pytest.raises(render.RenderError, match="finale"):
        render.build_spec(
            plan, Captions(pages=[]), presenter=Path("work/cut.mp4"),
            source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        )  # fmt: skip


def test_a_caption_page_that_runs_into_the_finale_fails_the_build() -> None:
    plan = _plan()
    late = CaptionPage(index=0, word_indices=[0], texts=["x"], start=4.9, end=5.4)
    with pytest.raises(render.RenderError, match="finale"):
        render.build_spec(
            plan, Captions(pages=[late]), presenter=Path("work/cut.mp4"),
            source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        )  # fmt: skip


def test_the_stamp_look_comes_from_the_style_front_matter() -> None:
    stamp = _spec().beats[2].stamp
    assert stamp is not None and stamp.text == "NOTHING"
    assert (stamp.land_s, stamp.shake_s) == (0.16, render.STAMP_SHAKE_S)  # motion.stamp
    assert stamp.color == "#FFD60A"  # broll.motion.stamp.palette yellow_green_red
    assert stamp.rotate_deg != 0.0 and stamp.scale_from == render.STAMP_SCALE_FROM
    assert all(b.stamp is None for b in _spec().beats if b.id != "b03")


@pytest.mark.parametrize(
    "text",
    ["12", "NOTHING", "SIX SECONDS", "A VERY LONG STAMP WORD THAT WILL NOT FIT AT ALL"],
)
def test_stamps_stay_in_the_top_60_percent_and_clear_of_the_right_rail(text: str) -> None:
    stamp = render.stamp_spec(text, numbers=EXPLAINER)
    limit = EXPLAINER.broll.stamp_max_y_fraction * render.HEIGHT
    assert stamp.top >= 0.0 and stamp.top + stamp.height <= limit + 1e-6
    assert stamp.left >= render.SAFE_LEFT - 1e-6
    assert stamp.left + stamp.width <= render.WIDTH - render.SAFE_RIGHT_PX + 1e-6
    assert stamp.font_px <= render.STAMP_FONT_PX


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("India Gate · Delhi", ("India Gate", "Delhi")),
        ("Steve Jobs — Apple co-founder", ("Steve Jobs", "Apple co-founder")),
        ("Virat Kohli", ("Virat Kohli", "")),
    ],
)
def test_the_lower_third_sits_in_the_style_band_and_splits_name_from_role(
    text: str, expected: tuple[str, str]
) -> None:
    label = render.lower_third_spec(text, numbers=EXPLAINER)
    assert (label.name, label.role) == expected
    assert label.top == EXPLAINER.broll.lower_third_top_y == 1150
    assert label.top + label.height == EXPLAINER.broll.lower_third_bottom_y == 1240
    assert label.fade_s == 0.35 and label.left == render.SAFE_LEFT
    assert label.left + label.width <= render.WIDTH - render.SAFE_RIGHT_PX + 1e-6


def _label_beat(i: int) -> Beat:
    """A portrait entity beat: drawn as a full-bleed photo, so nothing but the
    lower-third carries its label."""
    return Beat.model_validate({
        "id": f"b{i}", "start": float(i - 1), "end": float(i), "mode": "pip", "kind": "photo",
        "motion": "ken_burns_in", "subject_kind": "entity", "query": PORTRAIT_SKY,
        "query_fallback": "sky", "source_intent": "search", "asset_id": f"a{i}",
        "event": {"kind": "lower_third", "text": "India Gate · Delhi"},
    })  # fmt: skip


def test_an_entity_beat_with_a_lower_third_event_renders_it(tmp_path: Path) -> None:
    plan = _plan().model_copy(update={"beats": [_label_beat(1)]})
    beat = _visual_spec(tmp_path, plan).beats[0]
    assert beat.visual is not None and beat.visual.treatment == "photo"
    assert beat.lower_third is not None and beat.lower_third.name == "India Gate"


def test_the_lower_third_is_suppressed_under_a_two_line_caption_page(tmp_path: Path) -> None:
    plan = _plan().model_copy(update={"beats": [_label_beat(1)]})
    manifest = _sourced(tmp_path, plan)
    spec = render.build_spec(
        plan, Captions(pages=[], beats_with_two_lines=["b1"]),
        presenter=Path("work/cut.mp4"), source_size=(fixture.WIDTH, fixture.HEIGHT),
        duration_s=fixture.DURATION_S, manifest=manifest, job_dir=tmp_path / "job",
    )  # fmt: skip
    assert spec.beats[0].lower_third is None


def test_the_lower_third_is_suppressed_where_the_card_strip_already_shows_it(
    tmp_path: Path,
) -> None:
    spec = _visual_spec(tmp_path)
    beat = next(b for b in spec.beats if b.id == "b04")
    assert beat.visual is not None and beat.visual.card is not None
    assert beat.visual.card.strip_text == "India Gate · Delhi" and beat.lower_third is None


def _number_beat(i: int, asset_id: str) -> Beat:
    return Beat.model_validate({
        "id": f"b{i}", "start": float(i - 1), "end": float(i), "mode": "pip", "kind": "photo",
        "motion": "ken_burns_in", "subject_kind": "number", "query": "the number",
        "query_fallback": "a number", "asset_id": asset_id,
        "event": {"kind": "stamp", "text": "12"},
    })  # fmt: skip


def test_a_number_beat_stamps_over_the_previous_asset_with_its_ken_burns_continued(
    tmp_path: Path,
) -> None:
    plan = _plan().model_copy(update={"beats": [_photo_beat(1), _number_beat(2, "a1")]})
    manifest = _sourced(tmp_path, plan)
    assert len(manifest.assets) == 1  # 4.2: a number beat adds no asset
    first, second = (b.visual for b in _visual_spec(tmp_path, plan, manifest).beats)
    assert first is not None and second is not None and first.src == second.src
    assert second.scale_from == first.scale_to  # the Ken Burns carries on, never restarts
    assert second.scale_to > second.scale_from and second.zoom == first.zoom


# --- list, split and wall (ticket 027; decisions 4.1, 5.2, 5.3, 9.2) -------------------


def _piece_beat(plan: PicturePlan, kind: str) -> Beat:
    return next(b for b in plan.beats if b.kind == kind)


def test_the_list_beat_draws_its_header_and_one_row_per_item(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "list")
    piece = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id).list
    assert piece is not None
    assert piece.header == beat.set_piece_title
    assert [r.text for r in piece.rows] == [i.text for i in beat.items]
    delays = [r.delay_s for r in piece.rows]
    assert delays == sorted(delays) and len(set(delays)) == len(delays)  # sequential entry
    assert all(r.from_x != 0 for r in piece.rows)  # each row springs in
    icons = [r.icon_src for r in piece.rows]
    assert [bool(i) for i in icons] == [i.asset_id is not None for i in beat.items]


def test_list_rows_stay_inside_the_safe_box_and_above_the_card_limit(tmp_path: Path) -> None:
    plan = _plan()
    piece = next(
        b for b in _visual_spec(tmp_path, plan).beats if b.id == _piece_beat(plan, "list").id
    ).list
    assert piece is not None and piece.rows
    assert min(r.left for r in piece.rows) >= render.SAFE_LEFT
    assert max(r.left + r.width for r in piece.rows) <= render.WIDTH - render.SAFE_LEFT
    assert max(r.top + r.height for r in piece.rows) <= EXPLAINER.broll.card_max_bottom_y
    assert piece.header_top + piece.header_font_px <= min(r.top for r in piece.rows)


def test_the_list_base_still_is_the_dimmed_ken_burns_of_the_style(tmp_path: Path) -> None:
    plan = _plan()
    beat = next(
        b for b in _visual_spec(tmp_path, plan).beats if b.id == _piece_beat(plan, "list").id
    )
    visual = beat.visual
    assert visual is not None and visual.treatment == "photo"
    b = EXPLAINER.broll
    assert (visual.scale_from, visual.scale_to) == (b.list_scale_from, b.list_scale_to)
    assert visual.dim == b.list_dim == 0.45


def test_more_items_than_the_style_allows_are_cut_to_its_maximum() -> None:
    items = [render.ItemSource(text=f"row {i}") for i in range(9)]
    piece = render.list_spec("Header", items, numbers=EXPLAINER)
    assert len(piece.rows) == EXPLAINER.broll.list_items_max == 6


def test_the_split_beat_draws_two_labelled_panes_a_badge_and_a_title_strip(
    tmp_path: Path,
) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "split")
    piece = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id).split
    assert piece is not None
    left, right = piece.panes
    assert [p.label for p in piece.panes] == [i.text for i in beat.items]
    assert left.left < right.left and left.pane_width == right.pane_width
    assert right.left - (left.left + left.pane_width) == piece.seam_px
    assert right.from_x > 0 and left.from_x == 0  # the right half slides in (nkb_08)
    assert " ".join(w.text for w in piece.title_words) == beat.set_piece_title
    highlighted = {w.text for w in piece.title_words if w.highlight}
    assert highlighted == {i.text for i in beat.items}  # the panes are the key words


def test_the_split_card_sits_above_the_pip_with_its_badge_on_a_corner(tmp_path: Path) -> None:
    plan = _plan()
    piece = next(
        b for b in _visual_spec(tmp_path, plan).beats if b.id == _piece_beat(plan, "split").id
    ).split
    assert piece is not None
    assert piece.left >= render.SAFE_LEFT
    assert piece.left + piece.width <= render.WIDTH - render.SAFE_LEFT
    assert piece.top + piece.height <= EXPLAINER.broll.card_max_bottom_y
    badge = piece.badge
    assert badge is not None
    assert badge.left >= render.SAFE_LEFT
    assert badge.left + badge.diameter <= render.WIDTH - render.SAFE_RIGHT_PX
    # it overlaps the card's top-left corner rather than floating beside it
    assert badge.left < piece.left + piece.width and badge.top < piece.top
    assert badge.top + badge.diameter > piece.top


def test_the_wall_draws_a_grid_with_staggered_entry_and_ken_burns_per_cell(
    tmp_path: Path,
) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "wall")
    piece = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id).wall
    assert piece is not None
    assert len(piece.cells) == len(beat.items) == 4
    assert piece.columns == 2  # 2x2 for four cells
    delays = [c.delay_s for c in piece.cells]
    assert delays == sorted(delays) and len(set(delays)) > 1
    assert all(c.scale_from != c.scale_to for c in piece.cells)  # Ken Burns on every cell
    signs = [c.from_x > 0 for c in piece.cells]
    assert signs == [i % 2 == 1 for i in range(len(signs))]  # alternating sides (nkb_09)


def test_wall_cells_tile_the_band_inside_the_safe_box(tmp_path: Path) -> None:
    plan = _plan()
    piece = next(
        b for b in _visual_spec(tmp_path, plan).beats if b.id == _piece_beat(plan, "wall").id
    ).wall
    assert piece is not None
    assert min(c.left for c in piece.cells) >= render.SAFE_LEFT
    assert max(c.left + c.box_width for c in piece.cells) <= render.WIDTH - render.SAFE_LEFT
    assert max(c.top + c.box_height for c in piece.cells) <= EXPLAINER.broll.card_max_bottom_y
    assert len({c.left for c in piece.cells}) == piece.columns


@pytest.mark.parametrize(
    ("cells", "columns"), [(4, 2), (5, 3), (6, 3), (7, 3), (9, 3)]
)
def test_the_wall_grid_runs_from_two_by_two_to_three_by_three(cells: int, columns: int) -> None:
    sources = [render.ItemSource(text=f"c{i}", card=_fake_card(i)) for i in range(cells)]
    piece = render.wall_spec(sources, numbers=EXPLAINER)
    assert piece.columns == columns and len(piece.cells) == cells


def _fake_card(i: int) -> render.CardSource:
    return render.CardSource(src=f"/tmp/a{i}.png", width=1200, height=800)


def test_an_item_naming_an_asset_the_manifest_never_sourced_fails_the_build(
    tmp_path: Path,
) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "wall")
    items = [i.model_copy(update={"asset_id": "nope"}) for i in beat.items]
    plan = plan.model_copy(
        update={
            "beats": [
                b.model_copy(update={"items": items}) if b.id == beat.id else b for b in plan.beats
            ]
        }
    )
    with pytest.raises(render.RenderError, match="nope"):
        _visual_spec(tmp_path, plan)


def test_registry_exports_list_split_and_wall_after_027() -> None:
    assert {"list", "split", "wall"} <= set(render.registry())


# --- charts and labelled diagrams (ticket 021; decisions 9.2, 9.3, 5.5) ----------------


def test_the_chart_beat_draws_the_planners_series_in_the_style_format(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "chart")
    drawn = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id)
    chart = drawn.chart
    assert chart is not None
    assert chart.form == beat.chart_form
    assert chart.title == beat.set_piece_title
    assert [m.label for m in chart.marks] == [p.label for p in beat.series]
    assert [m.value for m in chart.marks] == [p.value for p in beat.series]
    assert chart.marks[0].value_text == "12 words"  # explainer decimals 0, the beat's unit
    # the chart is drawn, never sourced: its beat shows no picture of its own
    assert drawn.visual is None


def test_the_infographic_beat_draws_its_base_and_its_labels(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "infographic")
    drawn = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id)
    diagram = drawn.infographic
    assert diagram is not None
    assert [label.text for label in diagram.labels] == [label.text for label in beat.labels]
    assert Path(diagram.src).is_file()
    manifest_beat = _sourced(tmp_path, plan).beat(beat.id)
    assert manifest_beat is not None and manifest_beat.asset_id is not None
    record = _sourced(tmp_path, plan).asset(manifest_beat.asset_id)
    assert record is not None and (diagram.width, diagram.height) == (record.width, record.height)
    # a landscape base is boxed like a card, inside the safe box and above the limit
    assert diagram.left >= render.SAFE_LEFT
    assert diagram.top + diagram.box_height <= EXPLAINER.broll.card_max_bottom_y
    # 5.5: the base is the diagram's own layer, never a bare photo beat
    assert drawn.visual is None


def test_the_asset_step_marks_the_diagram_base(tmp_path: Path) -> None:
    plan = _plan()
    manifest = _sourced(tmp_path, plan)
    beat = _piece_beat(plan, "infographic")
    decided = manifest.beat(beat.id)
    assert decided is not None and decided.diagram_base
    others = [b.beat_id for b in manifest.beats if b.diagram_base]
    assert others == [beat.id]


def test_a_label_outside_the_safe_area_fails_the_build(tmp_path: Path) -> None:
    """9.3: on a full-bleed base the percentages are the frame's, so a label at 95 % of
    the height lands under the platform's chrome - a build failure, not a silent clamp."""
    plan = _plan()
    beat = _piece_beat(plan, "infographic")
    low = [label.model_copy(update={"y": 95.0}) for label in beat.labels]
    plan = plan.model_copy(update={"beats": [
        b.model_copy(update={"labels": low}) if b.id == beat.id else b for b in plan.beats
    ]})  # fmt: skip
    portrait = {PORTRAIT_SKY: (1080, 1920), beat.query: (1080, 1920)}
    manifest = _sourced(
        tmp_path, plan,
        web=assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY, beat.query}),
        commons=assets.FakeImageSource("commons", sizes=portrait),
    )  # fmt: skip
    with pytest.raises(render.RenderError, match="safe area"):
        _visual_spec(tmp_path, plan, manifest)


def test_a_rescued_infographic_beat_draws_no_diagram(tmp_path: Path) -> None:
    plan = _plan()
    empty = assets.FakeImageSource("web", nothing_found=True)
    spec = _visual_spec(tmp_path, plan, _sourced(tmp_path, plan, web=empty, commons=empty))
    beat = next(b for b in spec.beats if b.id == _piece_beat(plan, "infographic").id)
    assert beat.infographic is None and beat.mode == "pip"


def test_registry_exports_chart_and_infographic_after_021() -> None:
    assert {"chart", "infographic"} <= set(render.registry())


# --- label fly-ins and the counter (ticket 029; decisions 4.2, 7.1, 9.2, 9.3) ----------


def test_the_diagram_labels_fly_in_on_a_stagger_from_the_beats_length(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "infographic")
    drawn = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id)
    diagram = drawn.infographic
    assert diagram is not None
    stagger, fly_s = infographics.label_stagger(
        len(beat.labels), length_s=beat.end - beat.start, fly_s=EXPLAINER.info.diagram.fly_s
    )
    assert [label.delay_s for label in diagram.labels] == pytest.approx(
        [i * stagger for i in range(len(beat.labels))]
    )
    assert diagram.fly_s == pytest.approx(fly_s)
    assert all((label.from_x, label.from_y) != (0.0, 0.0) for label in diagram.labels)


def test_the_counter_beat_counts_to_its_target_and_lands_in_the_stamp_time() -> None:
    plan = _plan()
    beat = next(b for b in plan.beats if b.counter is not None)
    drawn = next(b for b in _spec().beats if b.id == beat.id)
    counter = drawn.counter
    assert counter is not None and drawn.stamp is None  # the counter is its landed event
    frames = drawn.end_frame - drawn.start_frame
    assert len(counter.texts) == frames
    assert counter.texts[0] == "0 words" and counter.texts[-1] == counter.text == "12 words"
    assert counter.land_s == EXPLAINER.broll.stamp_land_s == 0.16  # motion.stamp.duration_s
    assert counter.land_frame == frames - round(counter.land_s * 30)
    assert counter.shake_s > 0 and counter.color == render.stamp_colors(EXPLAINER)[0]


@pytest.mark.parametrize(("target", "grouping", "last"), [
    (12500000, "indian", "1,25,00,000 crore"),
    (12500000, "western", "12,500,000 crore"),
])  # fmt: skip
def test_the_counter_writes_the_styles_grouping_and_stays_in_the_top_60_percent(
    target: float, grouping: str, last: str
) -> None:
    numbers = dataclasses.replace(
        EXPLAINER, broll=dataclasses.replace(EXPLAINER.broll, counter_grouping=grouping)
    )
    counter = render.counter_spec(
        CounterPlan(start=0, target=target, unit="crore"), frames=90, fps=30, numbers=numbers
    )
    assert counter.texts[-1] == last
    limit = EXPLAINER.broll.stamp_max_y_fraction * render.HEIGHT
    tilt = render._tilt_extent(counter.width, counter.height, counter.rotate_deg)  # pyright: ignore[reportPrivateUsage]
    assert counter.top + counter.height / 2 + tilt <= limit + 1e-6
    assert counter.left + counter.width <= render.WIDTH - render.SAFE_RIGHT_PX + 1e-6
    # one size for every frame, the box measured on the widest text it will show, so no
    # frame's digits spill out
    pads = 2 * render.STAMP_PAD_X + 2 * render.STAMP_BORDER_PX
    widths = [
        render._measured(t, font_px=counter.font_px, style=EXPLAINER.captions) + pads  # pyright: ignore[reportPrivateUsage]
        for t in set(counter.texts)
    ]
    assert max(widths) == pytest.approx(counter.width)


def test_a_counter_on_a_number_beat_rides_the_previous_asset(tmp_path: Path) -> None:
    """4.2: a counter beat is a number beat - it adds no asset and its picture is the
    previous beat's with the Ken Burns carried on."""
    counted = _number_beat(2, "a1").model_copy(update={
        "event": Event(), "overlays": ["counter"], "counter": CounterPlan(target=40, unit="%"),
    })  # fmt: skip
    plan = _plan().model_copy(update={"beats": [_photo_beat(1), counted]})
    manifest = _sourced(tmp_path, plan)
    assert len(manifest.assets) == 1
    first, second = _visual_spec(tmp_path, plan, manifest).beats
    assert first.visual is not None and second.visual is not None
    assert second.visual.scale_from == first.visual.scale_to
    assert second.counter is not None and second.counter.text == "40%"


def test_registry_exports_label_flyin_and_counter_after_029() -> None:
    assert {"label_flyin", "counter"} <= set(render.registry())
    required = render.loaded_styles()["explainer"].requires_components
    assert {"label_flyin", "counter"} <= set(required)


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
    # The fallback crop window is the full source width, square, from the top; a job's
    # own window comes from `presenter.measure` (013).
    assert (pip.window_left, pip.window_top, pip.window_size) == (0, 0, 1080)


def test_landscape_source_window_is_still_a_square_inside_the_source() -> None:
    pip = render.fixed_pip((1920, 1080), EXPLAINER)
    assert pip.window_size == 1080 and pip.window_left == 420 and pip.window_top == 0


def test_the_spec_carries_the_measured_pip_geometry_over_the_fixed_one() -> None:
    """013: `spec_for_job` passes `job.json.presenter.pip`; `build_spec` draws it as
    given and only falls back to `fixed_pip` when a job was never measured."""
    measured = presenter.pip_geometry(
        FaceBox(left=300, top=700, width=400, height=500), (1080, 1920), EXPLAINER_SPEC
    )
    spec = render.build_spec(
        _plan(), _captions(_plan()), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        pip=measured,
    )  # fmt: skip
    assert spec.pip == measured
    assert (spec.pip.window_top, spec.pip.diameter) == (314, 340)
    assert _spec().pip == render.fixed_pip((1080, 1920), EXPLAINER)


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
    # 031: the spans that were cut are on disk for gate T10.
    assert presenter.load_cut_list(job) == presenter.cut_list(plan)


def test_fake_renderer_writes_the_cut_list_too(tmp_path: Path, fixture_clip: Path) -> None:
    job = _job_with(tmp_path, fixture_clip)
    render.FakeRenderer().render(job)
    assert presenter.load_cut_list(job) == presenter.cut_list(_plan())


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


# --- ticket 022: the sound director inside the render step (decisions 7.1-7.3, 5.4) ---


def test_without_a_catalogue_the_mix_is_the_voice_alone(
    tmp_path: Path, fixture_clip: Path, media: Media
) -> None:
    """The shipped catalogue is empty until the operator seeds it (025), and a job
    planned before the sound call has no story: both leave the short as it was before
    022, never a failure."""
    job = _job_with(tmp_path, fixture_clip)
    _synthetic_picture(job, media)
    render.voice_stem(job)
    assert render.sound_mix(job, library=sound.Library(root=tmp_path)) is None
    render.mux(job, library=sound.Library(root=tmp_path))
    stems = job.work_dir / "stems"
    assert not (stems / "music.wav").exists() and not (stems / "sfx.wav").exists()
    assert (stems / "mix.wav").is_file()


def test_the_mix_carries_the_bed_and_the_cues_and_their_rights_rows(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    """The whole 022 slice through the renderer: the stems beside the mix, the balance
    report inside the 7.3 band, the master still on T4, and the music and SFX rows in
    `out/rights.json` beside the picture rows (5.4)."""
    job = _job_with(tmp_path, fixture_clip)
    _synthetic_picture(job, media)
    story = FakePlanner().plan_sound(_plan_request(), _plan())
    (job.work_dir / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    render.voice_stem(job)
    out = render.mux(job, library=library)
    stems = job.work_dir / "stems"
    for name in ("voice.wav", "music.wav", "sfx.wav", "mix.wav"):
        assert (stems / name).is_file(), name
    balance = sound.balance_report(stems)
    assert balance is not None and balance.problems == []
    assert balance.cues > 0
    delivered = ffmpeg.measure_loudness(out)
    assert delivered.integrated == pytest.approx(render.MASTER_LUFS, abs=0.5)  # T4 holds
    assert delivered.true_peak <= render.MASTER_TP
    rows = rights.audio_rows(job.path)
    assert {r.kind for r in rows} == {"music", "sfx"}
    assert all(r.origin == "library" and r.source_url for r in rows)


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


# --- maps (ticket 020; decisions 9.3, 12.1) ----------------------------------------------------


def test_the_map_beat_draws_the_bundled_base_with_markers_at_geocoded_points(
    tmp_path: Path,
) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "map")
    drawn = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id)
    layout = drawn.map
    assert layout is not None
    assert beat.map is not None
    assert [m.name for m in layout.markers] == [m.name for m in beat.map.markers]
    assert layout.land and layout.coast and layout.borders
    assert layout.region == "India" and layout.object == "plane"
    assert len(layout.route) == 2
    # the default geocoder is the bundled gazetteer: no network, real coordinates
    assert {m.source for m in layout.markers} == {"gazetteer"}
    delhi, mumbai = layout.markers
    assert delhi.y < mumbai.y and delhi.x > mumbai.x
    # the map is drawn, never sourced: its beat shows no picture of its own
    assert drawn.visual is None
    assert drawn.chart is None and drawn.infographic is None


def test_the_map_beat_is_never_sourced_and_needs_no_rights_row(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "map")
    manifest = _sourced(tmp_path, plan)
    assert manifest.beat(beat.id) is None
    assert beat.id not in {b.beat_id for b in manifest.beats}


def test_a_geocoding_miss_fails_the_build_naming_the_place(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "map")
    assert beat.map is not None
    lost = beat.map.model_copy(update={"markers": [*beat.map.markers, MapMarker(name="Atlantis")]})
    plan = plan.model_copy(update={"beats": [
        b.model_copy(update={"map": lost}) if b.id == beat.id else b for b in plan.beats
    ]})  # fmt: skip
    with pytest.raises(render.RenderError, match=r"b05.*Atlantis"):
        _visual_spec(tmp_path, plan)


def test_build_spec_takes_the_geocoder_and_binds_it_to_the_job(tmp_path: Path) -> None:
    plan = _plan()

    class Recording(geo.FakeGeocoder):
        bound: list[Path] = []

        def for_job(self, job_dir: Path) -> geo.Geocoder:
            self.bound.append(job_dir)
            return self

    coder = Recording()
    spec = render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=_sourced(tmp_path, plan), job_dir=tmp_path / "job", geocoder=coder,
    )  # fmt: skip
    layout = next(b for b in spec.beats if b.kind == "map").map
    assert layout is not None and {m.source for m in layout.markers} == {"fake"}
    assert coder.bound == [tmp_path / "job"]


def test_the_remotion_renderer_carries_a_geocoder_the_gazetteer_by_default() -> None:
    assert isinstance(render.RemotionRenderer().geocoder, geo.GazetteerGeocoder)
    fake = geo.FakeGeocoder()
    assert render.RemotionRenderer(geocoder=fake).geocoder is fake


def test_registry_exports_map_after_020() -> None:
    assert "map" in render.registry()
