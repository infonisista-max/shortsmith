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
    stickers,
    styles,
)
from shortsmith.contracts import (
    AssetManifest,
    Beat,
    BedQuery,
    Bubble,
    BubbleSpec,
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
    PipGeometry,
    PlanRequest,
    PlanStyle,
    RenderSpec,
    SetPieceItem,
    SoundStory,
    Span,
    Sticker,
    StickerSpec,
    TextPop,
    TextPopSpec,
    TransitionStyle,
    ValidatedPlan,
    WordBox,
)
from shortsmith.planner import FakePlanner
from shortsmith.qa import technical
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media, bubble_style, text_pop_style

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
    the presenter, the `split` (its asset is the badge) and the finale - has no visual
    of its own. 055: the opening beats b01 (photo) and b02 (card) are the first two."""
    spec = _visual_spec(tmp_path)
    visual = {b.id: b.visual for b in spec.beats}
    photo, card = visual["b01"], visual["b02"]
    assert photo is not None and photo.treatment == "photo" and photo.card is None
    assert card is not None and card.treatment == "card" and card.card is not None
    assert Path(photo.src).is_absolute() and Path(photo.src).is_file()
    assert (photo.width, photo.height) == (1080, 1920)
    assert (photo.dim, card.dim) == (0.0, 0.0)
    base = {b: visual[b] for b in ("b08", "b10")}  # the list and the wall
    assert all(v is not None and v.treatment == "photo" and v.dim > 0 for v in base.values())
    carriers = ("b01", "b02", "b04", "b08", "b10")
    assert all(visual[b] is None for b in visual if b not in carriers)


def test_photo_ken_burns_numbers_come_from_the_style(tmp_path: Path) -> None:
    photo = _visual_spec(tmp_path).beats[0].visual
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


DIAGRAM_QUERIES = {"labelled diagram of a tone burst", "sound wave diagram"}  # b07's
LIST_QUERIES = {"three things about nothing", "empty list"}  # b08's


def _entity_opening(plan: PicturePlan) -> PicturePlan:
    """The fake plan with its opening (b01, b02) and b04 as entity beats: 055 always
    finds the opening an image, so a concept beat nothing is found for later has no
    earlier concept asset to re-dress and falls to rung 4."""
    return plan.model_copy(update={"beats": [
        b.model_copy(update={"subject_kind": "entity", "depicts": None})
        if b.id in ("b01", "b02", "b04") else b
        for b in plan.beats
    ]})  # fmt: skip


def _nothing_for_the_set_pieces(tmp_path: Path, plan: PicturePlan) -> AssetManifest:
    missing = DIAGRAM_QUERIES | LIST_QUERIES
    return _sourced(
        tmp_path, plan,
        web=assets.FakeImageSource("web", nothing_for=missing | {PORTRAIT_SKY}),
        commons=assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)},
                                       nothing_for=missing),
    )  # fmt: skip


def test_a_rung_4_beat_swaps_to_pip_over_the_gradient(tmp_path: Path) -> None:
    plan = _entity_opening(_plan())
    spec = _visual_spec(tmp_path, plan, _nothing_for_the_set_pieces(tmp_path, plan))
    b07 = next(b for b in spec.beats if b.id == "b07")
    assert (b07.mode, b07.visual) == ("pip", None)
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


# --- 051: cards and the split clear the measured PIP circle (decisions 3.3, 6.3) --------

# A face over 45 % of the 1080 px cut (3.3): the circle grows to 340 and its top to 920.
LARGE_FACE = FaceBox(left=280, top=600, width=520, height=520)


def _large_pip() -> PipGeometry:
    pip = presenter.pip_geometry(LARGE_FACE, (1080, 1920), EXPLAINER_SPEC)
    assert (pip.diameter, pip.top) == (340, 920)
    return pip


@pytest.mark.parametrize("size", [(1600, 900), (1000, 1000), (900, 1600)])
@pytest.mark.parametrize("pip_top", [920, 960])
def test_a_card_ends_the_gap_above_the_circle_top_it_is_given(
    size: tuple[int, int], pip_top: int
) -> None:
    """The card reads the circle the render will draw, not the style's fixed `pip.top`:
    on a large-face job (top 920) it ends 32 px above 920, on the normal circle above
    960 as before."""
    visual = render.card_visual("x.png", *size, strip_text="label", ring=False, index=0,
                                crop=Crop(), numbers=EXPLAINER, pip_top=pip_top)  # fmt: skip
    assert render.card_bottom(visual) == pytest.approx(pip_top - render.PIP_GAP_PX)


def _two_panes() -> list[render.ItemSource]:
    return [
        render.ItemSource(text=t, card=render.CardSource(src=f"{t}.png", width=800, height=800))
        for t in ("Alpha", "Beta")
    ]


@pytest.mark.parametrize("pip_top", [920, 960])
def test_the_split_ends_the_gap_above_the_circle_top_it_is_given(pip_top: int) -> None:
    piece = render.split_spec("Alpha versus Beta", _two_panes(), None, numbers=EXPLAINER,
                              pip_top=pip_top)  # fmt: skip
    assert render.split_bottom(piece) == pytest.approx(pip_top - render.PIP_GAP_PX)


def test_split_bottom_is_the_tilted_card_edge() -> None:
    piece = render.split_spec("Alpha versus Beta", _two_panes(), None, numbers=EXPLAINER,
                              pip_top=960)  # fmt: skip
    tilt = render._tilt_extent(piece.width, piece.height, piece.rotate_deg)  # pyright: ignore[reportPrivateUsage]
    assert render.split_bottom(piece) == pytest.approx(piece.top + piece.height / 2 + tilt)
    assert render.split_bottom(piece) > piece.top + piece.height  # the tilt adds to it


def test_build_spec_places_cards_and_the_split_under_the_measured_circle(
    tmp_path: Path,
) -> None:
    """`build_spec` derives the geometry it draws before placing the visuals and hands
    its top down: with a large-face measurement every card and the split composite end
    `PIP_GAP_PX` above 920; unmeasured (`pip=None`) they sit where 004/008 put them."""
    plan = _plan()
    manifest = _sourced(tmp_path, plan)
    measured = render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=manifest, job_dir=tmp_path / "job", pip=_large_pip(),
    )  # fmt: skip
    cards = [b.visual for b in measured.beats if b.visual is not None and b.visual.card]
    splits = [b.split for b in measured.beats if b.split is not None]
    assert cards and splits
    limit = measured.pip.top - render.PIP_GAP_PX
    assert limit == 920 - render.PIP_GAP_PX
    assert all(render.card_bottom(v) <= limit + 1e-6 for v in cards)
    assert all(render.split_bottom(s) <= limit + 1e-6 for s in splits)
    assert all(render.card_bottom(v) <= EXPLAINER.broll.card_max_bottom_y + 1e-6 for v in cards)
    fixed = _visual_spec(tmp_path, plan, manifest)
    fixed_limit = EXPLAINER.broll.pip_top - render.PIP_GAP_PX
    for beat in fixed.beats:
        if beat.visual is not None and beat.visual.card is not None:
            assert render.card_bottom(beat.visual) == pytest.approx(fixed_limit)
        if beat.split is not None:
            assert render.split_bottom(beat.split) == pytest.approx(fixed_limit)


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
    card = _visual_spec(tmp_path).beats[1].visual
    assert card is not None and card.card is not None
    assert card.card.strip_text == "India Gate · Delhi"


# --- set pieces and overlays (ticket 026; decisions 3.2, 3.4, 4.1, 4.2, 6.3) -----------


def test_the_opening_beats_are_pip_over_full_screen_images_with_no_hook(tmp_path: Path) -> None:
    """055: the first two beats draw the speaker in the circle over a photo and a card;
    no beat carries a hook, no beat is `hook_cards`, and only `full` beats punch in."""
    spec = _visual_spec(tmp_path)
    first, second = spec.beats[:2]
    assert (first.mode, second.mode) == ("pip", "pip")
    assert first.visual is not None and first.visual.treatment == "photo"
    assert second.visual is not None and second.visual.treatment == "card"
    assert first.punch_in is None and second.punch_in is None
    assert not any(hasattr(b, "hook") for b in spec.beats)
    assert "hook_cards" not in {b.kind for b in spec.beats}


def test_the_full_beat_is_the_only_one_with_the_research_punch_in() -> None:
    spec = _spec()
    full = [b for b in spec.beats if b.mode == "full"]
    assert [b.id for b in full] == ["b03"]
    punch = full[0].punch_in
    assert punch is not None
    assert (punch.scale_from, punch.settle_to, punch.settle_s) == (1.22, 1.03, 0.9)
    assert (punch.contrast, punch.saturate, punch.origin_y) == (1.06, 1.08, 0.30)
    assert all(b.punch_in is None for b in spec.beats if b.mode != "full")


def test_the_finale_cards_are_the_shorts_first_distinct_images_in_beat_order(
    tmp_path: Path,
) -> None:
    """055: the opening's images first, then the next distinct assets, up to the
    style's `broll.motion.finale.cards`; each labelled with its beat's lower-third."""
    plan = _plan()
    manifest = _sourced(tmp_path, plan)
    spec = _visual_spec(tmp_path, plan, manifest)
    finale = next(b for b in spec.beats if b.id == plan.finale.beat_id).finale
    assert finale is not None
    assert len(finale.cards) == EXPLAINER.broll.finale_cards == 3
    ids = render.opening_asset_ids(plan, manifest, 3)
    first_two = [manifest.beat("b01"), manifest.beat("b02")]
    assert [d.asset_id for d in first_two if d is not None] == ids[:2]
    files = [str((tmp_path / "job" / record.file).resolve())
             for record in (manifest.asset(i) for i in ids) if record is not None]  # fmt: skip
    assert [c.src for c in finale.cards] == files
    opening = next(b for b in spec.beats if b.id == "b01").visual
    assert opening is not None and finale.cards[0].src == opening.src
    assert finale.cards[1].label == "India Gate · Delhi"  # b02's lower-third
    assert all(Path(c.src).is_absolute() and Path(c.src).is_file() for c in finale.cards)
    assert finale.cards[1].left < finale.cards[2].left  # left shoulder, then the right one


def test_fewer_resolved_assets_give_fewer_finale_cards_never_a_failure(tmp_path: Path) -> None:
    plan = _plan()
    manifest = _sourced(tmp_path, plan)
    first = manifest.beat("b01")
    assert first is not None and first.asset_id is not None
    one = manifest.model_copy(update={"assets": [a for a in manifest.assets
                                                 if a.id == first.asset_id]})  # fmt: skip
    finale = next(b for b in _visual_spec(tmp_path, plan, one).beats if b.finale).finale
    assert finale is not None and len(finale.cards) == 1
    none = manifest.model_copy(update={"assets": []})
    finale = next(b for b in _visual_spec(tmp_path, plan, none).beats if b.finale).finale
    assert finale is not None and finale.cards == [] and finale.text == plan.finale.text


def test_finale_cards_stay_inside_the_side_margins(tmp_path: Path) -> None:
    finale = next(b for b in _visual_spec(tmp_path).beats if b.finale).finale
    assert finale is not None
    assert min(c.left for c in finale.cards) >= render.SAFE_LEFT
    assert max(c.left + c.box_width for c in finale.cards) <= render.WIDTH - render.SAFE_LEFT


def test_the_finale_carries_the_presenter_circle_the_payoff_word_and_the_cards(
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
    stamp = _spec().beats[3].stamp  # b04, the fake plan's stamp beat (055)
    assert stamp is not None and stamp.text == "NOTHING"
    assert (stamp.land_s, stamp.shake_s) == (0.16, render.STAMP_SHAKE_S)  # motion.stamp
    assert stamp.color == "#FFD60A"  # broll.motion.stamp.palette yellow_green_red
    assert stamp.rotate_deg != 0.0 and stamp.scale_from == render.STAMP_SCALE_FROM
    assert all(b.stamp is None for b in _spec().beats if b.id != "b04")


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
    beat = next(b for b in spec.beats if b.id == "b02")
    assert beat.visual is not None and beat.visual.card is not None
    assert beat.visual.card.strip_text == "India Gate · Delhi" and beat.lower_third is None


# --- 056 (4): stamps never cover a face ---------------------------------------------------
#
# run03: every stamp over the portrait card (b05, b08, b15, b16, b17, b23, b25) covered
# the king's face. The 3.3 detector runs on the image; the stamp moves to the largest
# face-free band of the card (upper or lower third, or below it). No face: today's place.


def _stamped(i: int, *, kind: str, query: str = "an archival group photo") -> Beat:
    return Beat.model_validate({
        "id": f"b{i}", "start": float(i - 1), "end": float(i), "mode": "pip", "kind": kind,
        "motion": "ken_burns_in" if kind == "photo" else "push_in", "subject_kind": "entity",
        "query": query, "query_fallback": "photo", "source_intent": "search",
        "asset_id": f"a{i}", "event": {"kind": "stamp", "text": "1953"},
    })  # fmt: skip


def _faced_spec(
    tmp_path: Path, plan: PicturePlan, face: FaceBox | None, log: list[str] | None = None
) -> RenderSpec:
    manifest = _sourced(tmp_path, plan)
    detector = presenter.FakeFaceDetector(face) if face is not None else None
    return render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=manifest, job_dir=tmp_path / "job", detector=detector,
        log=log.append if log is not None else None,
    )  # fmt: skip


def _overlaps(a: render.Box, b: render.Box) -> bool:
    return a.left < b.right and b.left < a.right and a.top < b.bottom and b.top < a.bottom


def test_a_stamp_over_a_card_with_a_face_moves_to_a_face_free_band(tmp_path: Path) -> None:
    """The fake web image is 1600x1000 (a card); a face across the middle of it sits
    under today's stamp, so the stamp moves off it, still inside the style band and the
    6.3 zones, and the move is one log line naming the beat."""
    plan = _plan().model_copy(update={"beats": [_stamped(1, kind="card")]})
    face = FaceBox(left=600, top=250, width=400, height=500)  # image pixels, 1600x1000
    log: list[str] = []
    beat = _faced_spec(tmp_path, plan, face, log).beats[0]
    plain = _faced_spec(tmp_path, plan, None).beats[0]
    assert beat.visual is not None and beat.visual.card is not None
    assert beat.stamp is not None and plain.stamp is not None
    face_box = render.face_box_on(beat.visual, face)
    assert _overlaps(render.stamp_box(plain.stamp), face_box), "today's stamp sat on the face"
    assert not _overlaps(render.stamp_box(beat.stamp), face_box)
    assert beat.stamp.top != plain.stamp.top and beat.stamp.left == plain.stamp.left
    assert (beat.stamp.text, beat.stamp.font_px, beat.stamp.width) == (
        plain.stamp.text, plain.stamp.font_px, plain.stamp.width,
    )  # fmt: skip
    limit = EXPLAINER.broll.stamp_max_y_fraction * render.HEIGHT
    assert render.stamp_box(beat.stamp).top >= render.SAFE_TOP_PX - 1e-6
    assert render.stamp_box(beat.stamp).bottom <= limit + 1e-6
    assert any("b1" in line and "stamp" in line and "face" in line for line in log), log


def test_a_stamp_over_a_photo_with_a_face_moves_too(tmp_path: Path) -> None:
    plan = _plan().model_copy(update={"beats": [_stamped(1, kind="photo", query=PORTRAIT_SKY)]})
    face = FaceBox(left=340, top=400, width=400, height=500)  # image pixels, 1080x1920
    beat = _faced_spec(tmp_path, plan, face).beats[0]
    plain = _faced_spec(tmp_path, plan, None).beats[0]
    assert beat.visual is not None and beat.visual.treatment == "photo"
    assert beat.stamp is not None and plain.stamp is not None
    face_box = render.face_box_on(beat.visual, face)
    assert _overlaps(render.stamp_box(plain.stamp), face_box)
    assert not _overlaps(render.stamp_box(beat.stamp), face_box)


def test_an_image_with_no_face_keeps_todays_stamp_placement(tmp_path: Path) -> None:
    plan = _plan().model_copy(update={"beats": [_stamped(1, kind="card")]})
    with_detector = _faced_spec(tmp_path, plan, None).beats[0]
    manifest = _sourced(tmp_path, plan)
    none_found = render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=manifest, job_dir=tmp_path / "job",
        detector=presenter.FakeFaceDetector(found=0),
    ).beats[0]  # fmt: skip
    assert with_detector.stamp is not None and none_found.stamp == with_detector.stamp
    assert none_found.stamp == render.stamp_spec("1953", numbers=EXPLAINER)


def test_a_face_that_fills_the_card_sends_the_stamp_below_the_card(tmp_path: Path) -> None:
    plan = _plan().model_copy(update={"beats": [_stamped(1, kind="card")]})
    face = FaceBox(left=0, top=0, width=1600, height=1000)
    log: list[str] = []
    beat = _faced_spec(tmp_path, plan, face, log).beats[0]
    assert beat.stamp is not None and beat.visual is not None
    assert render.stamp_box(beat.stamp).top >= render.image_box_on(beat.visual).bottom
    assert any("below the image" in line for line in log), log


def test_a_face_that_fills_the_photo_leaves_the_stamp_where_it_was(tmp_path: Path) -> None:
    """No face-free band on a full-bleed photo: today's placement, and the log says why."""
    plan = _plan().model_copy(update={"beats": [_stamped(1, kind="photo", query=PORTRAIT_SKY)]})
    face = FaceBox(left=0, top=0, width=1080, height=1920)
    log: list[str] = []
    beat = _faced_spec(tmp_path, plan, face, log).beats[0]
    assert beat.stamp == render.stamp_spec("1953", numbers=EXPLAINER)
    assert any("no face-free band" in line for line in log), log


def test_the_render_safe_top_is_the_gates() -> None:
    from shortsmith.qa import technical

    assert render.SAFE_TOP_PX == technical.SAFE_TOP_PX


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
    plan = _entity_opening(_plan())
    spec = _visual_spec(tmp_path, plan, _nothing_for_the_set_pieces(tmp_path, plan))
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
    assert modes[:2] == ["pip", "pip"] and "full" in modes and "off" in modes  # 055
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


# --- transitions (ticket 030; decision 9.4) ---------------------------------------------


def test_the_spec_carries_the_styles_transition_list_and_the_9_4_numbers() -> None:
    """The composition reads the enabled list and every number from the spec, never
    from code: the front matter's `broll.transitions` rows ride along verbatim."""
    spec = _spec()
    t = spec.transitions
    assert t.enabled == ["cut", "fade", "whip", "zoom", "spring"]
    assert t.fade.duration_s == 0.35
    assert (t.whip.duration_s, t.whip.blur_px) == (0.22, 14)
    assert (t.zoom.duration_s, t.zoom.scale_from) == (0.3, 1.6)
    assert (t.spring.damping, t.spring.stiffness, t.spring.mass) == (14, 160, 0.7)
    assert t.wipe.duration_s == 0.25
    assert t == EXPLAINER.transitions


def test_every_beat_carries_its_plan_enter_and_the_fake_uses_all_five() -> None:
    plan = _plan()
    spec = _spec()
    assert [b.enter for b in spec.beats] == [b.enter for b in plan.beats]
    assert {b.enter for b in spec.beats} == {"cut", "fade", "whip", "zoom", "spring"}


def test_a_beat_entering_outside_the_style_list_fails_the_build() -> None:
    """Defence in depth behind the grammar (9.4): the renderer refuses an enter the
    style never enabled, naming the beat and the list."""
    plan = _plan()
    wiped = plan.model_copy(
        update={
            "beats": [
                b.model_copy(update={"enter": "wipe"}) if b.id == "b05" else b for b in plan.beats
            ]
        }
    )
    with pytest.raises(render.RenderError, match=r"b05.*'wipe'.*enter_transitions.*9\.4"):
        render.build_spec(
            wiped,
            _captions(plan),
            presenter=Path("work/cut.mp4"),
            source_size=(fixture.WIDTH, fixture.HEIGHT),
            duration_s=fixture.DURATION_S,
        )


def test_registry_exports_the_six_transitions_after_030() -> None:
    assert {"cut", "fade", "whip", "zoom", "spring", "wipe"} <= set(render.registry())


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
    022, never a failure. 054 (5): with a story and no search, the job log and the job
    page both say "no audio search configured"."""
    job = _job_with(tmp_path, fixture_clip)
    _synthetic_picture(job, media)
    render.voice_stem(job)
    assert render.sound_mix(job, library=sound.Library(root=tmp_path)) is None
    assert "no audio search" not in job.log_path.read_text(encoding="utf-8"), "no story: no note"
    story = FakePlanner().plan_sound(_plan_request(), _plan())
    (job.work_dir / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    assert render.sound_mix(job, library=sound.Library(root=tmp_path)) is None
    render.mux(job, library=sound.Library(root=tmp_path))
    stems = job.work_dir / "stems"
    assert not (stems / "music.wav").exists() and not (stems / "sfx.wav").exists()
    assert (stems / "mix.wav").is_file()
    log = job.log_path.read_text(encoding="utf-8")
    assert "sound: voice only" in log and "no audio search configured" in log
    reloaded = jobs.load(job.path)
    notices = [w for w in reloaded.record.warnings if "no audio search configured" in w]
    assert len(notices) == 1, "one line on the page, not one per run"
    from shortsmith import app

    assert "no audio search configured" in app.render_job_page(reloaded)


def test_an_empty_catalogue_with_a_search_still_mixes_a_bed_and_cues(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    """054: F1 went out silent because the empty shipped catalogue returned before the
    search was asked. With a search the director runs, adopts a bed and the SFX, and
    every search and decision is a line in job.log."""
    job = _job_with(tmp_path, fixture_clip)
    _synthetic_picture(job, media)
    story = FakePlanner().plan_sound(_plan_request(), _plan())
    (job.work_dir / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    render.voice_stem(job)
    search = sound.FakeAudioSearch(shelf=library)
    empty = sound.Library(root=library.root)  # the shelf's files land under this root
    render.mux(job, library=empty, search=search)
    stems = job.work_dir / "stems"
    for name in ("voice.wav", "music.wav", "sfx.wav", "mix.wav"):
        assert (stems / name).is_file(), name
    assert search.calls and search.sfx_calls
    log = job.log_path.read_text(encoding="utf-8")
    assert "sound: audio search fake bed " in log and "sound: audio search fake sfx " in log
    assert "from the audio search" in log and "placed at" in log
    rows = rights.audio_rows(job.path)
    assert {r.kind for r in rows} == {"music", "sfx"}, "the fetched files have rights rows"
    assert not [w for w in jobs.load(job.path).record.warnings if "voice only" in w]


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
    """016 end to end through Remotion: at 0.25 s (b01) the frame shows the portrait
    photo's colour full-bleed; at 0.75 s (b02) the card centre shows the card image and
    the cover behind it is the same image darkened (055: the opening beats)."""
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

    assert _near(_pixel(frames[1], 900, 700), colour("b01"))
    card = next(b for b in spec.beats if b.id == "b02").visual
    assert card is not None and card.card is not None
    cx = round(card.card.left + card.card.width / 2)
    cy = round(card.card.top + card.card.border_px + card.card.image_height / 2)
    centre = _pixel(frames[3], cx, cy)
    assert _near(centre, colour("b02"))
    cover = _pixel(frames[3], 1000, 1800)
    assert sum(cover) < sum(centre)


FLASH = (255, 214, 10)  # explainer's accent, its transitions.flash.color


def _flashy_numbers() -> render.StyleNumbers:
    """The explainer numbers with `flash` enabled: the renderer's own guard reads the
    enabled list, so the test style is a copy, never the shipped spec."""
    numbers = EXPLAINER_SPEC.broll.transitions.model_dump()
    return dataclasses.replace(
        EXPLAINER,
        transitions=TransitionStyle(enabled=[*EXPLAINER.transitions.enabled, "flash"], **numbers),
    )


def _bright_text_pixels(frame: tuple[int, int, bytes], box: WordBox) -> int:
    """Pixels inside a caption word's box that read as text: bright on every channel,
    which the flash colour (blue 10) never is."""
    width, _, data = frame
    count = 0
    for y in range(int(box.y), int(box.y + box.height)):
        for x in range(int(box.x), int(box.x + box.width)):
            i = 3 * (y * width + x)
            if min(data[i], data[i + 1], data[i + 2]) >= 150:
                count += 1
    return count


def test_a_flash_peaks_on_the_boundary_and_leaves_the_pip_and_captions_on_top(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """060 (9.4 as amended), end to end through Remotion: b02 enters on a `flash` at
    0.5 s (frame 15). The boundary frame's picture is the flash colour; 0.3 s either
    side (frames 6 and 24) the picture is the plain shot - b01's photo, b02's darkened
    cover; the PIP circle's centre is the presenter on every one of those frames, never
    the flash; and the caption text is still drawn on the boundary frame."""
    plan = _plan()
    plan = plan.model_copy(update={"beats": [
        b.model_copy(update={"enter": "flash"}) if b.id == "b02" else b for b in plan.beats
    ]})  # fmt: skip
    job = _job_with(tmp_path, fixture_clip, plan)
    manifest = assets.source_assets(
        ValidatedPlan(picture=plan, sound=SoundStory(
            prompt_version="t", theme="t", mood_curve=[],
            bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[])),
        [], "any", spec=SPECS["explainer"], job_dir=job.path,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
    )  # fmt: skip
    assets.write_manifest(job.path, manifest)
    render.cut_presenter(job)
    spec = render.spec_for_job(job, numbers=_flashy_numbers())
    assert [b.enter for b in spec.beats if b.id == "b02"] == ["flash"]
    assert spec.transitions.flash.color == "#FFD60A" and spec.transitions.flash.duration_s == 0.3
    picture = job.work_dir / "picture.mp4"
    render.run_driver(
        spec, spec_path=job.work_dir / "render_spec.json", out_path=picture,
        log_path=job.work_dir / "render.log",
    )  # fmt: skip
    frames = ffmpeg.frames_rgb(picture, fps=30, width=1080, duration_s=1.0)
    assert len(frames) == 30
    boundary, before, after = frames[15], frames[6], frames[24]
    # the picture: flash colour on the boundary, the plain shots 0.3 s either side
    assert _near(_pixel(boundary, 900, 300), FLASH)
    assert not _near(_pixel(before, 900, 300), FLASH)
    assert not _near(_pixel(after, 900, 300), FLASH)
    assert sum(_pixel(after, 1000, 1800)) < sum(FLASH) / 2, "b02's darkened cover, not the flash"
    # the PIP circle never blinks: its centre is the presenter on every frame
    cx = spec.pip.left + spec.pip.diameter // 2
    cy = spec.pip.top + spec.pip.diameter // 2
    for frame in (before, boundary, after):
        assert not _near(_pixel(frame, cx, cy), FLASH)
    assert _near(_pixel(boundary, cx, cy), _pixel(before, cx, cy))
    # the captions stay on top: the page's first word ("hello", spoken by 0.34 s and past
    # the component's 0.06 s active hold by frame 13, so drawn white, not the active
    # yellow; not a keyword, so not a yellow box) shows its text pixels on the boundary
    # frame as it does two frames before it
    page = next(p for p in spec.captions if p.start <= 0.5 < p.end)
    word = page.words[0]
    assert word.text == "hello" and not word.keyword and word.end + 0.06 <= 13 / 30
    area = int(word.width) * int(word.height)
    for frame in (frames[13], boundary):
        assert _bright_text_pixels(frame, word) > area * 0.02


# --- text pops (ticket 061; 4.1 as amended) -----------------------------------------------------
#
# The fake plan's b01 (0-0.5 s, a `photo` in `pip`) speaks "hello" (word 0, 0.2 s) and
# "there" (word 1, 0.36 s); b03 (1.0-1.5 s) is the presenter full frame speaking "this".

POP_YELLOW = (255, 214, 10)  # explainer's broll.motion.text_pop.fill


def _popped(plan: PicturePlan, beat_id: str, *pops: TextPop) -> PicturePlan:
    return plan.model_copy(update={"beats": [
        b.model_copy(update={"text_pops": list(pops)}) if b.id == beat_id else b
        for b in plan.beats
    ]})  # fmt: skip


def _pop_beat(plan: PicturePlan, beat_id: str, log: list[str] | None = None, **kwargs: object):  # noqa: ANN202
    spec = render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        log=log.append if log is not None else None, **kwargs,  # pyright: ignore[reportArgumentType]
    )  # fmt: skip
    return next(b for b in spec.beats if b.id == beat_id), spec


def _box(pop: TextPopSpec) -> render.Box:
    return render.Box(pop.left, pop.top, pop.width, pop.height)


def test_text_pops_are_placed_at_the_planners_point_and_timed_on_their_word() -> None:
    """061 (1-3): two pops on b01 sit at their `{x, y, anchor}` in percent of the frame,
    in the explainer's pop look (Poppins 900 at `size_px`, the row's fill for `yellow`,
    white for `white`, tilted by `tilt_deg` alternating), popping in over `duration_s`
    at their word's time (`at_s`, seconds into the beat) and leaving at the beat's end
    (0.5 s, under `hold_max_s`); every other beat carries none."""
    plan = _popped(
        _plan(), "b01",
        TextPop(text="HELLO", word=0, x=70.0, y=30.0, at_s=0.2),
        TextPop(text="THERE", word=1, x=50.0, y=45.0, anchor="left", fill="white", at_s=0.36),
    )  # fmt: skip
    beat, spec = _pop_beat(plan, "b01")
    hello, there = beat.text_pops
    row = EXPLAINER_SPEC.broll.motion["text_pop"]
    assert (hello.text, hello.font_weight, hello.font_px) == ("HELLO", 900, int(row["size_px"]))
    assert hello.color == row["fill"] == "#FFD60A" and there.color == "#FFFFFF"
    assert hello.left + hello.width / 2 == pytest.approx(0.70 * render.WIDTH)
    assert hello.top + hello.height / 2 == pytest.approx(0.30 * render.HEIGHT)
    assert there.left == pytest.approx(0.50 * render.WIDTH)
    assert there.top + there.height / 2 == pytest.approx(0.45 * render.HEIGHT)
    assert (hello.rotate_deg, there.rotate_deg) == (-float(row["tilt_deg"]), float(row["tilt_deg"]))
    assert (hello.at_s, hello.pop_s, hello.until_s) == (0.2, float(row["duration_s"]), 0.5)
    assert (there.at_s, there.until_s) == (0.36, 0.5)
    assert hello.scale_from < 1.0 and hello.stroke_px > 0 and hello.drop_px > 0
    assert all(not b.text_pops for b in spec.beats if b.id != "b01")
    for pop in (hello, there):
        assert technical.zone_hits(pop.left, pop.top, pop.width, pop.height) == []


def test_a_text_pop_stays_on_screen_at_most_hold_max_s() -> None:
    """A pop on a long beat leaves `hold_max_s` after it lands, not at the beat's end."""
    plan = _plan()
    long_beat = plan.model_copy(update={"beats": [
        plan.beats[0].model_copy(update={"end": 4.0}),
        *[b.model_copy(update={"start": max(b.start, 4.0)}) for b in plan.beats[1:] if b.end > 4.0],
    ]})  # fmt: skip
    popped = _popped(long_beat, "b01", TextPop(text="HELLO", word=0, x=70.0, y=30.0, at_s=0.2))
    beat, _ = _pop_beat(popped, "b01")
    assert beat.text_pops[0].until_s == pytest.approx(0.2 + 2.5)


def test_a_text_pop_on_the_pip_circle_or_the_caption_band_is_moved_into_the_allowed_area() -> None:
    """061 (2): a pop asked for on the PIP circle (b01 is `pip`) moves off it, one asked
    for in the caption band moves above it, one asked for under the platform chrome
    moves into the safe area; each move is one `text pop:` line in job.log naming the
    beat and what it cleared."""
    on_circle = TextPop(text="HELLO", word=0, x=15.0, y=58.0, at_s=0.2)
    in_band = TextPop(text="THERE", word=1, x=50.0, y=72.0, at_s=0.36)
    log: list[str] = []
    beat, spec = _pop_beat(_popped(_plan(), "b01", on_circle, in_band), "b01", log)
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    band_top = styles.caption_block_top(spec.caption_style)
    hello, there = beat.text_pops
    assert not _box(hello).overlaps(circle) and _box(hello).bottom <= band_top + 1e-6
    assert not _box(there).overlaps(circle) and _box(there).bottom <= band_top + 1e-6
    assert any("b01" in line and "HELLO" in line and "circle" in line for line in log), log
    assert any("b01" in line and "THERE" in line and "caption" in line for line in log), log
    too_high = TextPop(text="HELLO", word=0, x=50.0, y=3.0, at_s=0.2)
    beat, _ = _pop_beat(_popped(_plan(), "b01", too_high), "b01")
    assert beat.text_pops[0].top >= render.SAFE_TOP_PX - 1e-6
    for pop in beat.text_pops:
        assert technical.zone_hits(pop.left, pop.top, pop.width, pop.height) == []


def test_a_text_pop_over_a_face_is_moved_and_one_with_no_free_spot_is_dropped(
    tmp_path: Path,
) -> None:
    """061 (2) reusing 056 (4): on a photo with a detected face under the pop's box the
    pop moves to a face-free spot (still off the circle and the captions) and job.log
    says so; a face filling the whole photo leaves no spot, so the pop is dropped and
    job.log says that too. No detector: the pop stays where it was asked."""
    pop = TextPop(text="1953", word=0, x=50.0, y=30.0, at_s=0.2)
    plan = _popped(_plan().model_copy(update={"beats": [
        _stamped(1, kind="photo", query=PORTRAIT_SKY).model_copy(update={"event": Event()}),
    ]}), "b1", pop)  # fmt: skip
    face = FaceBox(left=240, top=280, width=600, height=640)  # image pixels, 1080x1920
    log: list[str] = []
    beat = _faced_spec(tmp_path, plan, face, log).beats[0]
    plain = _faced_spec(tmp_path, plan, None).beats[0]
    assert beat.visual is not None and plain.text_pops and beat.text_pops
    face_box = render.face_box_on(beat.visual, face)
    assert _box(plain.text_pops[0]).overlaps(face_box), "the asked-for spot sat on the face"
    assert not _box(beat.text_pops[0]).overlaps(face_box)
    assert any("b1" in line and "text pop" in line and "face" in line for line in log), log
    whole = FaceBox(left=0, top=0, width=1080, height=1920)
    dropped_log: list[str] = []
    dropped = _faced_spec(tmp_path, plan, whole, dropped_log).beats[0]
    assert dropped.text_pops == ()
    assert any("b1" in line and "dropped" in line and "face" in line for line in dropped_log)


def test_a_text_pop_on_the_presenter_full_frame_clears_the_measured_face() -> None:
    """061 (2): on a `full` beat the face is the presenter's own (`job.json.presenter`),
    punched in; a pop asked for over it moves off it."""
    face = FaceBox(left=320, top=150, width=440, height=460)  # the fixture's drawn face
    pop = TextPop(text="THIS", word=2, x=50.0, y=20.0, at_s=1.2)
    log: list[str] = []
    beat, _ = _pop_beat(_popped(_plan(), "b03", pop), "b03", log, presenter_face=face)
    assert beat.mode == "full" and len(beat.text_pops) == 1
    punched = render.presenter_face_box(face)
    assert not _box(beat.text_pops[0]).overlaps(punched)
    assert any("b03" in line and "face" in line for line in log), log
    plain, _ = _pop_beat(_popped(_plan(), "b03", pop), "b03")
    assert _box(plain.text_pops[0]).overlaps(punched), "the asked-for spot sat on the face"


def test_text_pops_land_within_a_frame_of_the_spoken_word_through_the_grammar() -> None:
    """061 (3): the fake plan's pop (b03, word 2 "this" at 1.2 s) validated under the
    pops style lands 0.2 s into b03 - within 0.15 s of the transcript word's time."""
    from shortsmith import grammar

    request = _plan_request()
    popped = text_pop_style(EXPLAINER_SPEC)
    styled = request.model_copy(update={"style": PlanStyle(
        name="explainer", status="shipped", numbers=popped.numbers(), prose=popped.prose,
    )})  # fmt: skip
    plan = FakePlanner().plan_picture(styled)
    story = FakePlanner().plan_sound(styled, plan)
    judged = fixture.smoke_specs({"explainer": popped})["explainer"]
    validated = grammar.validate(plan, story, request.transcript, judged)
    assert isinstance(validated, ValidatedPlan), getattr(validated, "items", validated)
    beat, spec = _pop_beat(validated.picture, "b03")
    (pop,) = beat.text_pops
    landing = beat.start_frame / spec.fps + pop.at_s
    assert abs(landing - request.transcript.words[2].start) <= 0.15
    assert pop.at_s == pytest.approx(0.2)


RGB = tuple[int, int, int]


def _colour_pixels(frame: tuple[int, int, bytes], box: render.Box, colour: RGB) -> int:
    width, _, data = frame
    count = 0
    for y in range(max(0, int(box.top)), min(render.HEIGHT, int(box.bottom))):
        for x in range(max(0, int(box.left)), min(render.WIDTH, int(box.right))):
            i = 3 * (y * width + x)
            if _near((data[i], data[i + 1], data[i + 2]), colour, 40):
                count += 1
    return count


def test_text_pops_render_their_fill_in_their_box_after_landing(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """061 end to end through Remotion: b01 carries two pops on its full-bleed photo (the
    sky, no yellow or white in it). Before the first landing (0.1 s) neither box holds
    the pop's colour; after each landing its box shows the fill: yellow for "HELLO" at
    0.43 s, white for "THERE" at 0.47 s."""
    plan = _popped(
        _plan(), "b01",
        TextPop(text="HELLO", word=0, x=70.0, y=30.0, at_s=0.2),
        TextPop(text="THERE", word=1, x=62.0, y=45.0, anchor="left", fill="white", at_s=0.36),
    )  # fmt: skip
    job = _job_with(tmp_path, fixture_clip, plan)
    manifest = assets.source_assets(
        ValidatedPlan(picture=plan, sound=SoundStory(
            prompt_version="t", theme="t", mood_curve=[],
            bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[])),
        [], "any", spec=SPECS["explainer"], job_dir=job.path,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
    )  # fmt: skip
    assets.write_manifest(job.path, manifest)
    render.cut_presenter(job)
    spec = render.spec_for_job(job)
    beat = next(b for b in spec.beats if b.id == "b01")
    assert beat.visual is not None and beat.visual.treatment == "photo"
    hello, there = beat.text_pops
    picture = job.work_dir / "picture.mp4"
    render.run_driver(
        spec, spec_path=job.work_dir / "render_spec.json", out_path=picture,
        log_path=job.work_dir / "render.log",
    )  # fmt: skip
    frames = ffmpeg.frames_rgb(picture, fps=30, width=1080, duration_s=0.5)
    before, hello_landed, there_landed = frames[3], frames[13], frames[14]
    hello_box, there_box = _box(hello), _box(there)
    white = (255, 255, 255)
    assert _colour_pixels(before, hello_box, POP_YELLOW) == 0
    assert _colour_pixels(before, there_box, white) == 0
    hello_area = hello_box.width * hello_box.height
    there_area = there_box.width * there_box.height
    assert _colour_pixels(hello_landed, hello_box, POP_YELLOW) > hello_area * 0.02
    assert _colour_pixels(there_landed, there_box, white) > there_area * 0.01


# --- bubbles (ticket 063; 4.1 as amended) -------------------------------------------------------
#
# The fake plan's b01 (0-0.5 s, a `photo` in `pip`) speaks "hello" (word 0, 0.2 s) and
# "there" (word 1, 0.36 s); b04 (1.5-2.0 s) is the card beat with the stamp.

BUBBLE_ROW = EXPLAINER_SPEC.broll.motion["bubble"]


def _bubbled(plan: PicturePlan, beat_id: str, *bubbles: Bubble) -> PicturePlan:
    return plan.model_copy(update={"beats": [
        b.model_copy(update={"bubbles": list(bubbles)}) if b.id == beat_id else b
        for b in plan.beats
    ]})  # fmt: skip


def _body(bubble: BubbleSpec) -> render.Box:
    return render.Box(bubble.left, bubble.top, bubble.width, bubble.height)


def _anchor_px(x: float, y: float) -> tuple[float, float]:
    return x / 100 * render.WIDTH, y / 100 * render.HEIGHT


def test_a_speech_bubble_sits_above_its_anchor_with_the_tail_tip_on_it() -> None:
    """063 (1, 4): a speech bubble on b01 is a white rounded body in the explainer's
    bubble look (Poppins 800 at `size_px`, `fill`, `ink`), centred over the planner's
    `{x, y}` with its tail tip exactly on that point (the AC's 40 px), popping in over
    `duration_s` at `at_s` and leaving at the beat's end; the body stays out of the 6.3
    zones; every other beat carries none."""
    asked = Bubble(text="Who asked?", first=0, last=1, x=62.0, y=30.0, at_s=0.2)
    beat, spec = _pop_beat(_bubbled(_plan(), "b01", asked), "b01")
    (bubble,) = beat.bubbles
    ax, ay = _anchor_px(62.0, 30.0)
    assert (bubble.shape, bubble.text, bubble.lines) == ("speech", "Who asked?", ["Who asked?"])
    assert (bubble.font_px, bubble.font_weight) == (int(BUBBLE_ROW["size_px"]), 800)
    assert (bubble.fill, bubble.ink) == (BUBBLE_ROW["fill"], BUBBLE_ROW["ink"])
    assert (bubble.fill, bubble.ink) == ("#FFFFFF", "#111111")
    assert (bubble.tip_x, bubble.tip_y) == (ax, ay)
    assert bubble.left + bubble.width / 2 == pytest.approx(ax)
    assert bubble.top + bubble.height == pytest.approx(ay - render.BUBBLE_TAIL_LEN_PX)
    assert bubble.width <= int(BUBBLE_ROW["width_px"]) and bubble.radius_px > 0
    tail = render.bubble_tail(_body(bubble), (ax, ay))
    assert bubble.path == render.bubble_path(_body(bubble), bubble.radius_px, tail)
    assert bubble.dots == [] and bubble.stroke_px > 0 and bubble.scale_from < 1.0
    assert (bubble.at_s, bubble.pop_s) == (0.2, float(BUBBLE_ROW["duration_s"]))
    assert bubble.until_s == 0.5
    assert technical.zone_hits(bubble.left, bubble.top, bubble.width, bubble.height) == []
    assert all(not b.bubbles for b in spec.beats if b.id != "b01")


def test_a_thought_bubble_trails_dots_to_its_anchor_and_has_no_tail() -> None:
    """063 (1): a thought bubble is the rounded body without a tail, with a trail of
    dots shrinking from the body's edge to the anchor."""
    asked = Bubble(shape="thought", text="Nobody", first=0, last=0, x=40.0, y=35.0, at_s=0.2)
    beat, _ = _pop_beat(_bubbled(_plan(), "b01", asked), "b01")
    (bubble,) = beat.bubbles
    ax, ay = _anchor_px(40.0, 35.0)
    assert bubble.shape == "thought" and (bubble.tip_x, bubble.tip_y) == (ax, ay)
    assert bubble.path == render.bubble_path(_body(bubble), bubble.radius_px, None)
    radii = [d.r for d in bubble.dots]
    assert len(radii) == 3 and radii == sorted(radii, reverse=True)
    body = _body(bubble)
    for dot in bubble.dots:
        assert body.bottom < dot.cy < ay and abs(dot.cx - ax) < 1e-6


def test_the_tail_leaves_the_side_of_the_body_that_faces_the_anchor() -> None:
    """The tail's base sits on the body edge nearest the tip, clear of the corners."""
    body = render.Box(300.0, 500.0, 400.0, 120.0)
    below = render.bubble_tail(body, (520.0, 800.0))
    assert below is not None and below.side == "bottom"
    assert below.a[1] == below.b[1] == body.bottom and below.a[0] < 520.0 < below.b[0]
    above = render.bubble_tail(body, (320.0, 300.0))
    assert above is not None and above.side == "top" and above.a[1] == body.top
    assert above.a[0] >= body.left + render.BUBBLE_RADIUS_PX
    right = render.bubble_tail(body, (900.0, 560.0))
    assert right is not None and right.side == "right" and right.a[0] == body.right
    left = render.bubble_tail(body, (100.0, 560.0))
    assert left is not None and left.side == "left" and left.a[0] == body.left
    assert render.bubble_tail(body, (500.0, 560.0)) is None  # inside: nothing to point at
    path = render.bubble_path(body, 28.0, below)
    assert path.startswith("M") and path.endswith("Z") and "L 520 800" in path
    assert "L" not in render.bubble_path(body, 28.0, None)


def test_a_dialogue_pair_keeps_apart_and_the_second_lands_after_the_first() -> None:
    """063 (3): two bubbles on one beat never overlap - the second asked for the same
    spot is moved off the first, logged - and each keeps its own landing: here 0.6 s
    apart, the real dialogue gap, on b01 stretched to 4 s."""
    plan = _plan()
    long_beat = plan.model_copy(update={"beats": [
        plan.beats[0].model_copy(update={"end": 4.0}),
        *[b.model_copy(update={"start": max(b.start, 4.0)}) for b in plan.beats[1:] if b.end > 4.0],
    ]})  # fmt: skip
    question = Bubble(text="Who asked?", first=0, last=1, x=62.0, y=30.0, at_s=0.25)
    answer = Bubble(shape="thought", text="Nobody did", first=2, last=3, x=62.0, y=30.0, at_s=0.85)
    log: list[str] = []
    beat, _ = _pop_beat(_bubbled(long_beat, "b01", question, answer), "b01", log)
    first, second = beat.bubbles
    assert not _body(first).overlaps(_body(second))
    assert (first.at_s, second.at_s) == (0.25, 0.85)
    assert second.at_s - first.at_s == pytest.approx(0.6)
    assert first.until_s == pytest.approx(0.25 + float(BUBBLE_ROW["hold_max_s"]))
    moved = [line for line in log if "bubble:" in line and "Nobody did" in line]
    assert moved and "the first bubble" in moved[0], log


def test_bubble_text_wraps_and_shrinks_to_fit_and_fails_below_the_minimum() -> None:
    """063 (4): seven long words wrap onto lines inside `width_px`, the type shrinking
    from `size_px` towards `min_size_px` until they fit; text that cannot fit at the
    minimum fails the build naming the beat."""
    seven = "Remarkable discoveries throughout centuries transformed humanity completely"
    plan = _bubbled(_plan(), "b01", Bubble(text=seven, first=0, last=1, x=50.0, y=30.0, at_s=0.2))
    beat, _ = _pop_beat(plan, "b01")
    (bubble,) = beat.bubbles
    assert int(BUBBLE_ROW["min_size_px"]) <= bubble.font_px < int(BUBBLE_ROW["size_px"])
    assert 2 <= len(bubble.lines) <= render.BUBBLE_LINES_MAX
    assert " ".join(bubble.lines) == seven
    assert bubble.width <= int(BUBBLE_ROW["width_px"])
    one_word = "Supercalifragilisticexpialidocious" * 3
    asked = Bubble(text=one_word, first=0, last=1, x=50.0, y=30.0, at_s=0.2)
    too_long = _bubbled(_plan(), "b01", asked)
    with pytest.raises(render.RenderError, match=r"b01.*bubble.*min_size_px|b01.*does not fit"):
        _pop_beat(too_long, "b01")


def test_a_bubble_in_the_caption_band_or_on_the_pip_circle_is_moved_into_the_allowed_area() -> None:
    """063 (4): a bubble whose body would sit in the caption band moves above it; one
    whose body would cover the PIP circle (b01 is `pip`) moves off it; the tail still
    points at the anchor; each move is one `bubble:` line in job.log."""
    in_band = Bubble(text="Down here", first=0, last=1, x=50.0, y=80.0, at_s=0.2)
    log: list[str] = []
    beat, spec = _pop_beat(_bubbled(_plan(), "b01", in_band), "b01", log)
    (bubble,) = beat.bubbles
    band_top = styles.caption_block_top(spec.caption_style)
    assert _body(bubble).bottom <= band_top + 1e-6
    assert (bubble.tip_x, bubble.tip_y) == _anchor_px(50.0, 80.0)
    assert any("b01" in line and "bubble:" in line and "caption" in line for line in log), log
    on_circle = Bubble(text="Me", first=0, last=0, x=19.4, y=62.0, at_s=0.2)
    log.clear()
    beat, spec = _pop_beat(_bubbled(_plan(), "b01", on_circle), "b01", log)
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    (bubble,) = beat.bubbles
    assert not _body(bubble).overlaps(circle)
    assert any("b01" in line and "bubble:" in line and "circle" in line for line in log), log
    for placed in beat.bubbles:
        assert technical.zone_hits(placed.left, placed.top, placed.width, placed.height) == []


def test_a_bubble_over_a_face_is_moved_and_its_tail_still_points_at_the_face(
    tmp_path: Path,
) -> None:
    """063 (4) reusing 056 (4): on a photo with a detected face under the body the
    bubble moves to a face-free spot (the tail still on its anchor, the face) and
    job.log says so; a face filling the whole photo leaves no spot, so the bubble is
    dropped and job.log says that too."""
    bubble = Bubble(text="Who, me?", first=0, last=0, x=50.0, y=31.0, at_s=0.2)
    plan = _bubbled(_plan().model_copy(update={"beats": [
        _stamped(1, kind="photo", query=PORTRAIT_SKY).model_copy(update={"event": Event()}),
    ]}), "b1", bubble)  # fmt: skip
    face = FaceBox(left=240, top=280, width=600, height=640)  # image pixels, 1080x1920
    log: list[str] = []
    beat = _faced_spec(tmp_path, plan, face, log).beats[0]
    plain = _faced_spec(tmp_path, plan, None).beats[0]
    assert beat.visual is not None and plain.bubbles and beat.bubbles
    face_box = render.face_box_on(beat.visual, face)
    assert _body(plain.bubbles[0]).overlaps(face_box), "the asked-for spot sat on the face"
    assert not _body(beat.bubbles[0]).overlaps(face_box)
    assert (beat.bubbles[0].tip_x, beat.bubbles[0].tip_y) == _anchor_px(50.0, 31.0)
    assert any("b1" in line and "bubble:" in line and "face" in line for line in log), log
    whole = FaceBox(left=0, top=0, width=1080, height=1920)
    dropped_log: list[str] = []
    dropped = _faced_spec(tmp_path, plan, whole, dropped_log).beats[0]
    assert dropped.bubbles == ()
    assert any("b1" in line and "dropped" in line and "face" in line for line in dropped_log)


def test_the_fake_dialogue_pair_lands_through_the_grammar_on_the_card_beat() -> None:
    """063: the fake plan's pair (b04, the card beat) validated under the bubbles style
    lands at the beat's start (its words came earlier) and the fixture-scaled gap
    later; the render keeps both off the stamp, the circle and each other."""
    from shortsmith import grammar

    request = _plan_request()
    bubbled = bubble_style(EXPLAINER_SPEC)
    styled = request.model_copy(update={"style": PlanStyle(
        name="explainer", status="shipped", numbers=bubbled.numbers(), prose=bubbled.prose,
    )})  # fmt: skip
    plan = FakePlanner().plan_picture(styled)
    story = FakePlanner().plan_sound(styled, plan)
    judged = fixture.smoke_specs({"explainer": bubbled})["explainer"]
    validated = grammar.validate(plan, story, request.transcript, judged)
    assert isinstance(validated, ValidatedPlan), getattr(validated, "items", validated)
    beat, spec = _pop_beat(validated.picture, "b04")
    first, second = beat.bubbles
    assert (first.shape, second.shape) == ("speech", "thought")
    assert (first.at_s, second.at_s) == (0.0, fixture.SMOKE_BUBBLE["dialogue_gap_min_s"])
    assert beat.stamp is not None
    stamp = render.stamp_box(beat.stamp)
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    for bubble in beat.bubbles:
        assert not _body(bubble).overlaps(stamp) and not _body(bubble).overlaps(circle)
        assert technical.zone_hits(bubble.left, bubble.top, bubble.width, bubble.height) == []
    assert not _body(first).overlaps(_body(second))


def test_bubbles_render_their_white_bodies_after_landing(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """063 end to end through Remotion: b01 carries a dialogue pair on its full-bleed
    photo (the sky, no white in it). At 0 s neither body is drawn; at 0.47 s both
    bodies are mostly the bubble's white fill."""
    plan = _bubbled(
        _plan(), "b01",
        Bubble(text="Who asked?", first=0, last=1, x=62.0, y=30.0, at_s=0.05),
        Bubble(shape="thought", text="Nobody", first=2, last=3, x=30.0, y=42.0, at_s=0.3),
    )  # fmt: skip
    job = _job_with(tmp_path, fixture_clip, plan)
    manifest = assets.source_assets(
        ValidatedPlan(picture=plan, sound=SoundStory(
            prompt_version="t", theme="t", mood_curve=[],
            bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[])),
        [], "any", spec=SPECS["explainer"], job_dir=job.path,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
    )  # fmt: skip
    assets.write_manifest(job.path, manifest)
    render.cut_presenter(job)
    spec = render.spec_for_job(job)
    beat = next(b for b in spec.beats if b.id == "b01")
    assert beat.visual is not None and beat.visual.treatment == "photo"
    speech, thought = beat.bubbles
    picture = job.work_dir / "picture.mp4"
    render.run_driver(
        spec, spec_path=job.work_dir / "render_spec.json", out_path=picture,
        log_path=job.work_dir / "render.log",
    )  # fmt: skip
    frames = ffmpeg.frames_rgb(picture, fps=30, width=1080, duration_s=0.5)
    before, landed = frames[0], frames[14]
    white = (255, 255, 255)
    for bubble in (speech, thought):
        box = _body(bubble)
        assert _colour_pixels(before, box, white) == 0
        assert _colour_pixels(landed, box, white) > box.width * box.height * 0.3


# --- stickers (ticket 062; 4.1 as amended) -----------------------------------------------------

STICKER_ROW = EXPLAINER_SPEC.broll.motion["sticker"]
BULB = Sticker(intent="idea", name="Light bulb", word=1, at_s=0.36)


def _stuck(plan: PicturePlan, beat_id: str, *on: Sticker) -> PicturePlan:
    return plan.model_copy(update={"beats": [
        b.model_copy(update={"stickers": list(on)}) if b.id == beat_id else b for b in plan.beats
    ]})  # fmt: skip


def _with_stickers(tmp_path: Path, plan: PicturePlan) -> AssetManifest:
    """The fake plan sourced through fakes, its stickers fetched by the fake fetcher into
    the job folder `_sourced` uses."""
    manifest = _sourced(tmp_path, plan)
    shelf = stickers.StickerShelf(catalogue=stickers.shipped(),
                                  fetcher=stickers.FakeStickerFetcher(),
                                  cache_dir=tmp_path / "cache")  # fmt: skip
    manifest.stickers = shelf.source(plan, job_dir=tmp_path / "job", log=print, fetched_at="t")
    return manifest


def _sticker_spec(
    tmp_path: Path, plan: PicturePlan, *, manifest: AssetManifest | None = None,
    face: FaceBox | None = None, log: list[str] | None = None,
) -> RenderSpec:  # fmt: skip
    return render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=manifest if manifest is not None else _with_stickers(tmp_path, plan),
        job_dir=tmp_path / "job",
        detector=presenter.FakeFaceDetector(face) if face is not None else None,
        log=log.append if log is not None else None,
    )  # fmt: skip


def _square(sticker: StickerSpec) -> render.Box:
    return render.Box(sticker.left, sticker.top, sticker.size, sticker.size)


def test_a_sticker_sits_above_the_pip_circle_and_pops_in_on_its_word(tmp_path: Path) -> None:
    """062 (3): with no `{x, y}` on a `pip` beat the sticker is a `size_px` square
    centred over the circle, `STICKER_GAP_PX` above it (the "over his head" spot); it
    never touches the circle, the caption band or a 6.3 zone (float included); it lands
    at its word's time and floats in the style's row; its src is the job's own copy."""
    log: list[str] = []
    spec = _sticker_spec(tmp_path, _stuck(_plan(), "b01", BULB), log=log)
    beat = next(b for b in spec.beats if b.id == "b01")
    (sticker,) = beat.stickers
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    size = float(STICKER_ROW["size_px"])
    assert sticker.size == size == 240
    assert sticker.left + size / 2 == pytest.approx(circle.left + circle.width / 2)
    assert sticker.top + size == pytest.approx(circle.top - render.STICKER_GAP_PX)
    assert not _square(sticker).overlaps(circle)
    assert _square(sticker).bottom <= styles.caption_block_top(spec.caption_style)
    assert technical.zone_hits(sticker.left, sticker.top - sticker.float_px, size,
                               size + 2 * sticker.float_px) == []  # fmt: skip
    assert (sticker.at_s, sticker.pop_s, sticker.until_s) == (
        0.36, float(STICKER_ROW["duration_s"]), 0.5,
    )  # fmt: skip
    assert (sticker.float_px, sticker.float_period_s) == (
        float(STICKER_ROW["float_px"]), float(STICKER_ROW["float_period_s"]),
    )  # fmt: skip
    assert sticker.scale_from < 1.0 and sticker.shadow_px > 0
    assert sticker.src == str((tmp_path / "job" / "assets/stickers/light_bulb_3d.png").resolve())
    assert sticker.name == "Light bulb"
    assert all(not b.stickers for b in spec.beats if b.id != "b01")
    assert log == []


def test_a_sticker_with_a_point_sits_centred_on_it(tmp_path: Path) -> None:
    near = BULB.model_copy(update={"x": 70.0, "y": 30.0})
    spec = _sticker_spec(tmp_path, _stuck(_plan(), "b01", near))
    (sticker,) = next(b for b in spec.beats if b.id == "b01").stickers
    assert sticker.left + sticker.size / 2 == pytest.approx(0.70 * render.WIDTH)
    assert sticker.top + sticker.size / 2 == pytest.approx(0.30 * render.HEIGHT)


def test_a_sticker_keeps_off_the_beats_text_pops_and_bubbles(tmp_path: Path) -> None:
    """062 (3): the beat's other overlays are obstacles too."""
    circle_top = _sticker_spec(tmp_path, _stuck(_plan(), "b01", BULB)).pip.top
    pop = TextPop(text="HELLO", word=0, x=19.4, y=(circle_top - 140) / render.HEIGHT * 100,
                  at_s=0.2)  # fmt: skip
    plan = _stuck(_popped(_plan(), "b01", pop), "b01", BULB)
    log: list[str] = []
    beat = next(b for b in _sticker_spec(tmp_path, plan, log=log).beats if b.id == "b01")
    (sticker,) = beat.stickers
    (placed_pop,) = beat.text_pops
    assert not _square(sticker).overlaps(_box(placed_pop))
    assert any("sticker: b01" in line and "moved" in line for line in log), log


def test_a_sticker_over_a_face_is_moved_and_with_no_free_spot_dropped(tmp_path: Path) -> None:
    """062 (3) reusing 056 (4): a detected face under the asked-for spot moves the
    sticker off it (logged); a face filling the photo leaves no spot, so the sticker
    is dropped (logged) and the job goes on."""
    plan = _stuck(_plan().model_copy(update={"beats": [
        _stamped(1, kind="photo", query=PORTRAIT_SKY).model_copy(update={"event": Event()}),
    ]}), "b1", BULB.model_copy(update={"at_s": 0.2}))  # fmt: skip
    face = FaceBox(left=0, top=640, width=460, height=360)  # over the spot above the circle
    log: list[str] = []
    beat = _sticker_spec(tmp_path, plan, face=face, log=log).beats[0]
    assert beat.visual is not None and len(beat.stickers) == 1
    assert not _square(beat.stickers[0]).overlaps(render.face_box_on(beat.visual, face))
    assert any("sticker: b1" in line and "face" in line for line in log), log
    whole = FaceBox(left=0, top=0, width=1080, height=1920)
    dropped_log: list[str] = []
    dropped = _sticker_spec(tmp_path, plan, face=whole, log=dropped_log).beats[0]
    assert dropped.stickers == ()
    assert any("sticker: b1" in line and "dropped" in line for line in dropped_log), dropped_log


def test_a_sticker_the_fetch_dropped_is_left_out_of_the_picture(tmp_path: Path) -> None:
    """062 (2): no fetched file (no manifest record) leaves the beat without it."""
    plan = _stuck(_plan(), "b01", BULB)
    log: list[str] = []
    spec = _sticker_spec(tmp_path, plan, manifest=_sourced(tmp_path, plan), log=log)
    assert next(b for b in spec.beats if b.id == "b01").stickers == ()
    assert any("sticker: b01" in line and "no fetched file" in line for line in log), log


def test_a_sticker_renders_above_the_pip_circle_after_landing(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """062 end to end through Remotion: the fake sticker (a yellow disc) on b01 above the
    circle is absent at 0 s and drawn once it lands (0.1 s + the 0.2 s pop)."""
    plan = _stuck(_plan(), "b01", BULB.model_copy(update={"at_s": 0.1}))
    job = _job_with(tmp_path, fixture_clip, plan)
    manifest = _sourced(tmp_path, plan)
    manifest = assets.source_assets(
        ValidatedPlan(picture=plan, sound=SoundStory(
            prompt_version="t", theme="t", mood_curve=[],
            bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[])),
        [], "any", spec=SPECS["explainer"], job_dir=job.path,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
    )  # fmt: skip
    shelf = stickers.StickerShelf(catalogue=stickers.shipped(),
                                  fetcher=stickers.FakeStickerFetcher(),
                                  cache_dir=tmp_path / "cache")  # fmt: skip
    manifest.stickers = shelf.source(plan, job_dir=job.path, log=print, fetched_at="t")
    assets.write_manifest(job.path, manifest)
    render.cut_presenter(job)
    spec = render.spec_for_job(job)
    (sticker,) = next(b for b in spec.beats if b.id == "b01").stickers
    picture = job.work_dir / "picture.mp4"
    render.run_driver(
        spec, spec_path=job.work_dir / "render_spec.json", out_path=picture,
        log_path=job.work_dir / "render.log",
    )  # fmt: skip
    frames = ffmpeg.frames_rgb(picture, fps=30, width=1080, duration_s=0.5)
    before, landed = frames[0], frames[14]
    inner = render.Box(sticker.left + sticker.size * 0.3, sticker.top + sticker.size * 0.3,
                       sticker.size * 0.4, sticker.size * 0.4)  # fmt: skip
    yellow = (255, 214, 10)
    assert _colour_pixels(before, inner, yellow) == 0
    assert _colour_pixels(landed, inner, yellow) > inner.width * inner.height * 0.5


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


# --- map animations (ticket 028; decisions 9.2, 9.3) --------------------------------------------


def test_the_map_beat_carries_its_three_animations_timed_from_the_beat(tmp_path: Path) -> None:
    plan = _plan()
    beat = _piece_beat(plan, "map")
    assert set(beat.overlays) == {"pin_drop", "route_arrow", "object_path"}
    drawn = next(b for b in _visual_spec(tmp_path, plan).beats if b.id == beat.id)
    layout = drawn.map
    assert layout is not None
    assert layout.pin_drop and layout.route_arrow and layout.object_path
    assert layout.route_path.startswith("M ") and len(layout.segments) == 1
    assert layout.route_length_px > 0 and layout.object == "plane"
    # timed from the beat's length, in order, landing inside the beat
    length = beat.end - beat.start
    assert 0 < layout.landed_s <= length * infographics.MOTIONS_IN_FRACTION + 1e-9
    assert layout.markers[0].delay_s == 0.0 and layout.markers[1].delay_s > 0
    assert layout.route_start_s >= layout.markers[1].delay_s + layout.pin_drop_s
    assert layout.object_start_s >= layout.route_start_s + layout.route_draw_s
    # every pixel is the layout's: the plan named places only
    assert beat.map is not None and all(m.lat is None for m in beat.map.markers)


def test_registry_exports_the_map_animations_after_028() -> None:
    animations = {"pin_drop", "route_arrow", "object_path"}
    assert animations <= set(render.registry())
    required = render.loaded_styles()["explainer"].requires_components
    assert animations <= set(required)


# --- moving footage (ticket 058; 4.1 and 5.1 as amended) --------------------------------

CLOUDS = "clouds drifting over hills"


def _clip_beat(i: int, *, asset_id: str | None = None, length: float = 1.0) -> Beat:
    return Beat.model_validate({
        "id": f"b{i}", "start": (i - 1) * length, "end": i * length, "mode": "pip",
        "kind": "clip", "motion": "push_in", "subject_kind": "concept", "depicts": "scene",
        "query": CLOUDS, "query_fallback": "sky", "source_intent": "search",
        "asset_id": asset_id or f"a{i}", "event": {"kind": "stamp", "text": "CLOUDS"},
    })  # fmt: skip


def _clip_sourced(
    tmp_path: Path, plan: PicturePlan, clip_source: assets.ClipSource | None = None
) -> AssetManifest:
    job_dir = tmp_path / "job"
    (job_dir / "work").mkdir(parents=True, exist_ok=True)
    validated = ValidatedPlan(picture=plan, sound=SoundStory(
        prompt_version="t", theme="t", mood_curve=[], bed_query=BedQuery(theme="t", mood="t",
        energy=3), cues=[]))  # fmt: skip
    return assets.source_assets(
        validated, [], "any", spec=SPECS["explainer"], job_dir=job_dir,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
        clips={"pexels": clip_source or assets.FakeClipSource("pexels")},
    )  # fmt: skip


def test_a_clip_beat_draws_the_video_full_screen_at_the_styles_speed(tmp_path: Path) -> None:
    """058 (1, 6): the clip is the beat's visual - the `clip` treatment covering the
    frame under the circle, muted, from the file's start at `broll.motion.clip.speed`
    with the row's push (1.0 -> 1.0: the clip's own movement is the motion), no drift,
    no scrim, no card."""
    plan = _plan().model_copy(update={"beats": [_clip_beat(1)]})
    manifest = _clip_sourced(tmp_path, plan)
    beat = _visual_spec(tmp_path, plan, manifest).beats[0]
    visual = beat.visual
    assert visual is not None and visual.treatment == "clip" and beat.mode == "pip"
    assert Path(visual.src).is_absolute() and Path(visual.src).is_file()
    assert visual.src.endswith(".mp4") and (visual.width, visual.height) == (1080, 1920)
    row = EXPLAINER.broll
    assert (visual.speed, visual.start_s) == (row.clip_speed, 0.0) == (1.0, 0.0)
    assert (visual.scale_from, visual.scale_to) == (row.clip_scale_from, row.clip_scale_to)
    assert (visual.pan_px, visual.dim, visual.card, visual.zoom) == (0.0, 0.0, None, 1.0)
    assert beat.stamp is not None  # the stamp still lands over the clip


def test_a_number_beat_carries_the_clip_on_from_where_it_stopped(tmp_path: Path) -> None:
    """4.2 / 058: a number beat over the clip keeps playing it: same file, `start_s` the
    seconds the first beat already played at the style's speed."""
    beats = [_clip_beat(1), _number_beat(2, "a1")]
    plan = _plan().model_copy(update={"beats": beats})
    manifest = _clip_sourced(tmp_path, plan)
    assert len(manifest.assets) == 1
    first, second = (b.visual for b in _visual_spec(tmp_path, plan, manifest).beats)
    assert first is not None and second is not None and first.src == second.src
    assert (first.treatment, second.treatment) == ("clip", "clip")
    assert second.start_s == pytest.approx(1.0 * first.speed) and second.speed == first.speed


def test_the_finale_cards_and_set_pieces_never_show_a_clip(tmp_path: Path) -> None:
    """058 (7): the finale's cards are the short's first stills, so a clip record is
    passed over; a set-piece item resolving to a clip fails the build naming it."""
    plan = _plan()
    beats = [_clip_beat(1, length=0.5), *plan.beats[1:]]
    plan = plan.model_copy(update={"beats": beats})
    manifest = _clip_sourced(tmp_path, plan)
    first = manifest.asset("a1")
    assert first is not None and first.kind == "clip"
    ids = render.opening_asset_ids(plan, manifest, 3)
    assert "a1" not in ids and len(ids) == 3
    with pytest.raises(render.RenderError, match="clip"):
        render.item_sources(
            plan.beats[-2].model_copy(update={"items": [SetPieceItem(text="x", asset_id="a1")]}),
            manifest, tmp_path / "job",
        )  # fmt: skip


def test_no_face_detection_runs_on_a_clip_and_its_overlays_stay_placed(tmp_path: Path) -> None:
    """056 (4) / 058: the detector reads stills; a clip has no still to read, so the
    stamp (and a pop or bubble) over a clip keeps today's placement and the detector is
    never asked."""
    plan = _plan().model_copy(update={"beats": [_clip_beat(1)]})
    manifest = _clip_sourced(tmp_path, plan)
    detector = presenter.FakeFaceDetector(FaceBox(left=300, top=300, width=400, height=500))
    log: list[str] = []
    spec = render.build_spec(
        plan, _captions(plan), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        manifest=manifest, job_dir=tmp_path / "job", detector=detector, log=log.append,
    )  # fmt: skip
    plain = _visual_spec(tmp_path, plan, manifest)
    assert detector.seen == []
    assert spec.beats[0].stamp == plain.beats[0].stamp and spec.beats[0].stamp is not None
    assert not any("face" in line for line in log)


def _region_motion(a: tuple[int, int, bytes], b: tuple[int, int, bytes],
                   box: tuple[int, int, int, int]) -> float:  # fmt: skip
    """The share of the pixels inside `box` that differ by more than 30 levels."""
    left, top, right, bottom = box
    changed = total = 0
    for y in range(top, bottom, 2):
        for x in range(left, right, 2):
            total += 1
            if not _near(_pixel(a, x, y), _pixel(b, x, y)):
                changed += 1
    return changed / max(1, total)


# Below the stamp, right of the PIP circle, above the caption band: the clip alone moves here.
CLIP_REGION = (400, 720, 940, 940)


def test_a_clip_beat_renders_moving_muted_footage(tmp_path: Path, fixture_clip: Path) -> None:
    """058 end to end through Remotion: the fake plan's clip beat (b04, 1.5-2.0 s) draws
    the synthetic clip full-screen under the circle and the captions - a frame at the
    beat's middle differs from its first - while the picture stays silent although the
    clip file carries a tone (the master carries no clip audio)."""
    plan = _plan()
    job = _job_with(tmp_path, fixture_clip, plan)
    validated = ValidatedPlan(picture=plan, sound=SoundStory(
        prompt_version="t", theme="t", mood_curve=[],
        bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[]))  # fmt: skip
    manifest = assets.source_assets(
        validated, [], "any", spec=SPECS["explainer"], job_dir=job.path,
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PORTRAIT_SKY}),
            "commons": assets.FakeImageSource("commons", sizes={PORTRAIT_SKY: (1080, 1920)}),
        },
        clips={"pexels": assets.FakeClipSource("pexels")},
    )  # fmt: skip
    assets.write_manifest(job.path, manifest)
    decided = manifest.beat("b04")
    assert decided is not None and decided.treatment == "clip" and decided.asset_id is not None
    record = manifest.asset(decided.asset_id)
    assert record is not None and record.kind == "clip"
    clip_streams = {s["codec_type"] for s in ffmpeg.probe(job.path / record.file)["streams"]}
    assert clip_streams == {"video", "audio"}  # the source clip carries a tone
    render.RemotionRenderer().render(job)
    picture = job.work_dir / "picture.mp4"
    assert [s["codec_type"] for s in ffmpeg.probe(picture)["streams"]] == ["video"]
    short = job.out_dir / "short.mp4"
    assert ffmpeg.video_md5(short) == ffmpeg.video_md5(picture)
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    b04 = next(b for b in spec.beats if b.id == "b04")
    assert b04.visual is not None and b04.visual.treatment == "clip"
    start_s = b04.start_frame / spec.fps
    middle_s = (b04.start_frame + b04.end_frame) / 2 / spec.fps
    first = ffmpeg.frame_rgb(picture, at_s=start_s + 1 / spec.fps)
    middle = ffmpeg.frame_rgb(picture, at_s=middle_s)
    assert _region_motion(first, middle, CLIP_REGION) > 0.01
    # the stems are the voice, the bed and the cues; no clip audio reaches the mix
    stems = sorted(p.name for p in (job.work_dir / "stems").glob("*.wav"))
    assert "voice.wav" in stems and "mix.wav" in stems and not any("clip" in s for s in stems)


def test_registry_exports_clip_after_058() -> None:
    assert "clip" in render.registry()
    assert "clip" in render.loaded_styles()["explainer"].requires_components
