"""More ways to show a picture (ticket 103; run05: 9 of 17 photos became the red card).

`assets.classify` no longer decides the look: `assets.allowed_treatments` says what an
image allows (fits full screen, has a face, its resolution), the planner picks a
`treatment` per still beat, and `render.pick_treatment` draws the pick or falls back to an
allowed one - never the same framed treatment twice in a row, never more cards than the
style's `broll.card_max_per_60s`. The grammar flags a repeat as a soft violation and the
editor's repair swaps the treatment. Every number is style front matter.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from shortsmith import assets, grammar, render, styles
from shortsmith.contracts import (
    PICTURE_TREATMENTS,
    AssetManifest,
    AssetRecord,
    Beat,
    BeatAsset,
    CutPlan,
    FaceBox,
    Finale,
    PicturePlan,
    Span,
    VisualSpec,
)
from shortsmith.editor import beat_options, fallback_for, repairs

EXPLAINER = render.style_numbers("explainer")
LANDSCAPE_LOW = (870, 614)  # run05 b05: an owner photo that cannot fill the frame
FACE_LANDSCAPE = (1500, 1358)  # run05 b03: covers 1080x1920 within crop_fill's upscale
PORTRAIT = (1000, 1406)  # run05 b02: fills the frame
FACE = FaceBox(left=900, top=300, width=240, height=260)
SHIPPED = ("explainer", "fastfacts", "footage", "vishva", "hitech")


def _spec(name: str = "explainer") -> styles.StyleSpec:
    return render.loaded_styles()[name]


# --- what an image allows (classify says, it no longer decides) --------------------------


def _allowed(size: tuple[int, int], *, fits: bool, face: bool) -> tuple[str, ...]:
    b = EXPLAINER.broll
    return assets.allowed_treatments(
        size[0], size[1], fits=fits, has_face=face, offered=b.treatments,
        crop_fill_max_upscale=b.crop_fill.max_upscale if b.crop_fill else 0.0,
    )  # fmt: skip


def test_a_low_res_landscape_may_take_backdrop_polaroid_or_card() -> None:
    allowed = _allowed(LANDSCAPE_LOW, fits=False, face=False)
    assert {"backdrop", "polaroid", "card"} <= set(allowed)
    assert "photo" not in allowed and "crop_fill" not in allowed


def test_a_face_image_may_take_crop_to_fill() -> None:
    assert "crop_fill" in _allowed(FACE_LANDSCAPE, fits=False, face=True)
    assert "crop_fill" not in _allowed(FACE_LANDSCAPE, fits=False, face=False)


def test_crop_to_fill_never_upscales_past_the_style_limit() -> None:
    tiny = (300, 422)  # run05 b23: 4.5x to cover the frame
    assert "crop_fill" not in _allowed(tiny, fits=False, face=True)


def test_an_image_that_fills_the_frame_may_be_a_photo() -> None:
    assert _allowed(PORTRAIT, fits=True, face=False)[0] == "photo"


def test_the_allowed_list_is_never_empty() -> None:
    allowed = assets.allowed_treatments(10, 10, fits=False, has_face=False, offered=("photo",),
                                        crop_fill_max_upscale=2.0)  # fmt: skip
    assert allowed == ("card",)


# --- the renderer's pick and its fallback ----------------------------------------------------

NO_REPEAT = frozenset({"backdrop", "polaroid", "card"})
ORDER = ("photo", "crop_fill", "backdrop", "polaroid", "card")


def _pick(planned: str | None, allowed: tuple[str, ...], previous: str | None = None,
          cards_left: float = math.inf) -> str:  # fmt: skip
    return render.pick_treatment(planned, allowed, previous=previous, no_repeat=NO_REPEAT,
                                 order=ORDER, cards_left=cards_left)  # fmt: skip


def test_the_planners_pick_is_drawn_when_the_image_allows_it() -> None:
    assert _pick("polaroid", ("backdrop", "polaroid", "card")) == "polaroid"


def test_a_pick_the_image_does_not_allow_falls_back_to_an_allowed_one() -> None:
    assert _pick("photo", ("backdrop", "polaroid", "card")) == "backdrop"
    assert _pick("crop_fill", ("backdrop", "polaroid", "card")) == "backdrop"


def test_the_same_framed_treatment_never_runs_back_to_back() -> None:
    assert _pick("card", ("backdrop", "polaroid", "card"), previous="card") == "backdrop"
    assert _pick("backdrop", ("backdrop", "polaroid", "card"), previous="backdrop") == "polaroid"


def test_full_screen_photos_may_follow_each_other() -> None:
    assert _pick("photo", ("photo", "backdrop"), previous="photo") == "photo"


def test_the_card_is_capped() -> None:
    assert _pick("card", ("backdrop", "polaroid", "card"), cards_left=0) == "backdrop"


def test_the_pick_never_fails() -> None:
    assert _pick("card", ("card",), previous="card", cards_left=0) == "card"
    assert _pick(None, ("card",)) == "card"


def test_the_card_cap_and_the_order_are_front_matter() -> None:
    for name in SHIPPED:
        spec = _spec(name)
        b = render.style_numbers(name).broll
        assert spec.broll.card_max_per_60s == b.card_max_per_60s == 3, name  # NKB 2, Dyson 3
        assert tuple(spec.broll.treatments) == b.treatments, name
        assert set(b.treatments) == set(PICTURE_TREATMENTS), name
        assert b.no_repeat == frozenset(spec.broll.no_repeat_treatments), name
        assert b.backdrop and b.polaroid and b.crop_fill, name


# --- the visuals as drawn -----------------------------------------------------------------


def _beat(i: int, *, treatment: str | None = None, kind: str = "photo",
          event: dict[str, str] | None = None) -> Beat:  # fmt: skip
    return Beat.model_validate({
        "id": f"b{i:02d}", "start": 2.0 * i, "end": 2.0 * i + 2.0, "mode": "pip", "kind": kind,
        "motion": "ken_burns_in", "subject_kind": "entity", "query": f"archival photo {i}",
        "treatment": treatment, **({"event": event} if event else {}),
    })  # fmt: skip


def _plan(beats: list[Beat]) -> PicturePlan:
    return PicturePlan(prompt_version="t", cut=CutPlan(keep=[Span(start=0, end=beats[-1].end)]),
                       beats=beats, finale=Finale(beat_id="none", text="?"), title="t",
                       description="d")  # fmt: skip


def _manifest(beats: list[Beat], size: tuple[int, int], *, fits: bool) -> AssetManifest:
    records = [
        AssetRecord(id=f"a{i}", origin="web", file=f"assets/a{i}.jpg", sha256=str(i),
                    width=size[0], height=size[1], fetched_at="2026-09-30T00:00:00Z")
        for i in range(len(beats))
    ]  # fmt: skip
    decided = [
        BeatAsset(beat_id=b.id, asset_id=f"a{i}", treatment="photo" if fits else "card",
                  fallback_rung=0)
        for i, b in enumerate(beats)
    ]  # fmt: skip
    return AssetManifest(assets=records, beats=decided, runtime_s=beats[-1].end, rescued_max=4)


def _drawn(tmp_path: Path, beats: list[Beat], size: tuple[int, int], *, fits: bool = False,
           face: FaceBox | None = None) -> dict[str, VisualSpec]:  # fmt: skip
    out = render._visuals(  # pyright: ignore[reportPrivateUsage]
        _plan(beats), _manifest(beats, size, fits=fits), tmp_path, EXPLAINER, pip_top=960,
        face_of=lambda _src: face,
    )  # fmt: skip
    return {k: v for k, (_mode, v) in out.items() if v is not None}


def test_run05_nine_cards_in_a_row_become_varied_treatments(tmp_path: Path) -> None:
    # nine photo beats whose images cannot fill the frame, the planner naming nothing
    beats = [_beat(i) for i in range(9)]
    drawn = [v.treatment for v in _drawn(tmp_path, beats, LANDSCAPE_LOW).values()]
    assert drawn.count("card") <= math.ceil(3 * 18 / 60)
    assert all(a != b for a, b in zip(drawn, drawn[1:], strict=False) if a in NO_REPEAT)
    assert {"backdrop", "polaroid"} <= set(drawn)


def test_the_planners_treatments_are_drawn(tmp_path: Path) -> None:
    beats = [_beat(0, treatment="polaroid"), _beat(1, treatment="backdrop"),
             _beat(2, treatment="card"), _beat(3, treatment="crop_fill")]  # fmt: skip
    drawn = _drawn(tmp_path, beats, FACE_LANDSCAPE, face=FACE)
    assert [v.treatment for v in drawn.values()] == ["polaroid", "backdrop", "card", "crop_fill"]


def test_crop_to_fill_frames_the_face_and_moves_slowly(tmp_path: Path) -> None:
    # 102: a scene beat - no subject known, so the (largest) face found is framed; a named
    # person's beat aims at the ring's point instead (tests/test_motion_alive.py)
    scene = _beat(0, treatment="crop_fill").model_copy(update={"depicts": "scene"})
    visual = _drawn(tmp_path, [scene], FACE_LANDSCAPE, face=FACE)["b00"]
    cf = EXPLAINER.broll.crop_fill
    assert cf is not None and visual.card is None
    # 102: the beat's `ken_burns_in` is the style's move; a motion with no move row keeps
    # crop_fill's own slow push
    move = EXPLAINER.broll.moves["ken_burns_in"]
    assert (visual.scale_from, visual.scale_to) == (move.scale_from, move.scale_to)
    own = render._visuals(  # pyright: ignore[reportPrivateUsage]
        _plan([_beat(0, treatment="crop_fill").model_copy(update={"motion": "reveal"})]),
        _manifest([_beat(0)], FACE_LANDSCAPE, fits=False), tmp_path, EXPLAINER, pip_top=960,
        face_of=lambda _src: FACE,
    )["b00"][1]  # fmt: skip
    assert own is not None and (own.scale_from, own.scale_to) == (cf.scale_from, cf.scale_to)
    face = render.face_box_on(visual, FACE)
    centre = face.left + face.width / 2
    assert abs(centre - render.WIDTH / 2) < render.WIDTH * 0.1  # the face across the middle
    assert face.left >= 0 and face.right <= render.WIDTH


def test_crop_to_fill_without_a_face_falls_back(tmp_path: Path) -> None:
    visual = _drawn(tmp_path, [_beat(0, treatment="crop_fill")], FACE_LANDSCAPE)["b00"]
    assert visual.treatment == "backdrop"


def test_the_backdrop_is_the_sharp_image_over_its_blurred_enlarged_copy(tmp_path: Path) -> None:
    visual = _drawn(tmp_path, [_beat(0, treatment="backdrop")], LANDSCAPE_LOW)["b00"]
    bd, card = EXPLAINER.broll.backdrop, visual.card
    assert bd is not None and card is not None
    assert card.border_px == 0 and card.rotate_deg == 0 and card.strip_px == 0
    assert card.image_width <= min(bd.width_px, bd.max_upscale * LANDSCAPE_LOW[0]) + 1e-6
    assert (card.cover_blur_px, card.cover_brightness) == (bd.blur_px, bd.brightness)
    assert card.cover_scale_from > 1.0  # enlarged, filling 9:16
    assert render.card_bottom(visual) <= 960 - render.PIP_GAP_PX + 1e-6


def test_the_polaroid_drops_and_its_tilt_varies_within_the_range(tmp_path: Path) -> None:
    beats = [_beat(i, treatment="polaroid") for i in range(0, 8, 2)]
    beats = [b.model_copy(update={"id": f"p{i}", "start": 2.0 * i, "end": 2.0 * i + 2.0})
             for i, b in enumerate(beats)]  # fmt: skip
    # never back to back: put a photo between the polaroids
    spaced: list[Beat] = []
    for i, b in enumerate(beats):
        between = {"id": f"q{i}", "start": 4.0 * i + 2.0, "end": 4.0 * i + 4.0}
        spaced += [b.model_copy(update={"start": 4.0 * i, "end": 4.0 * i + 2.0}),
                   _beat(0, treatment="backdrop").model_copy(update=between)]  # fmt: skip
    drawn = _drawn(tmp_path, spaced, LANDSCAPE_LOW)
    pl = EXPLAINER.broll.polaroid
    assert pl is not None
    tilts = [v.card.rotate_deg for k, v in drawn.items() if k.startswith("p") and v.card]
    assert len(tilts) == 4 and len(set(tilts)) == 4
    assert all(pl.tilt_min_deg <= t <= pl.tilt_max_deg for t in tilts)
    card = drawn["p0"].card
    assert card is not None
    assert (card.drop_px, card.drop_s, card.border_px) == (pl.drop_px, pl.drop_s, pl.border_px)
    assert card.strip_px + card.border_px == pl.bottom_px  # the thick bottom of a print
    assert render.card_bottom(drawn["p0"]) <= 960 - render.PIP_GAP_PX + 1e-6


def test_the_polaroids_bottom_carries_the_lower_third_label(tmp_path: Path) -> None:
    beat = _beat(0, treatment="polaroid", event={"kind": "lower_third", "text": "Kainchi Dham"})
    card = _drawn(tmp_path, [beat], LANDSCAPE_LOW)["b00"].card
    assert card is not None and card.strip_text == "Kainchi Dham"


def test_a_number_beat_carrying_a_polaroid_on_does_not_drop_it_again(tmp_path: Path) -> None:
    first = _beat(0, treatment="polaroid")
    number = Beat.model_validate({
        **_beat(1).model_dump(), "subject_kind": "number", "asset_id": "a0",
    })  # fmt: skip
    manifest = _manifest([first, number], LANDSCAPE_LOW, fits=False)
    manifest.beats[1] = manifest.beats[1].model_copy(update={"asset_id": "a0"})
    out = render._visuals(  # pyright: ignore[reportPrivateUsage]
        _plan([first, number]), manifest, tmp_path, EXPLAINER, pip_top=960,
    )  # fmt: skip
    visual = out["b01"][1]
    assert visual is not None and visual.treatment == "polaroid" and visual.card is not None
    assert visual.card.drop_px == 0


# --- the grammar: a repeat is soft, the editor swaps it -----------------------------------


def test_two_consecutive_beats_with_the_same_treatment_are_a_soft_violation() -> None:
    beats = [_beat(0, treatment="card"), _beat(1, treatment="card"), _beat(2, treatment="photo")]
    found = grammar.treatments(beats, runtime=60.0, spec=_spec())
    assert len(found) == 1
    v = found[0]
    assert v.beat_id == "b01" and not v.hard and "treatment" in v.message


def test_different_treatments_and_repeated_photos_pass() -> None:
    beats = [_beat(0, treatment="card"), _beat(1, treatment="polaroid"),
             _beat(2, treatment="photo"), _beat(3, treatment="photo")]  # fmt: skip
    assert grammar.treatments(beats, runtime=8.0, spec=_spec()) == []


def test_more_cards_than_the_cap_is_soft() -> None:
    beats = [_beat(i, treatment="card" if i % 2 == 0 else "photo") for i in range(10)]
    found = grammar.treatments(beats, runtime=20.0, spec=_spec())
    assert found and all(not v.hard for v in found)
    assert any("card_max_per_60s" in v.message for v in found)


def test_a_treatment_the_style_does_not_offer_is_soft() -> None:
    spec = _spec()
    narrow = spec.model_copy(update={"broll": spec.broll.model_copy(
        update={"treatments": ["photo", "card"], "no_repeat_treatments": ["card"]})})  # fmt: skip
    found = grammar.treatments([_beat(0, treatment="polaroid")], runtime=2.0, spec=narrow)
    assert len(found) == 1 and not found[0].hard


def test_the_validator_keeps_the_repeat_as_a_warning_with_keep_soft() -> None:
    beats = [_beat(0, treatment="card"), _beat(1, treatment="card")]
    plan = _plan(beats)
    spec = _spec()
    strict = grammar.treatments(plan.beats, runtime=4.0, spec=spec)
    assert strict
    kept = [grammar.kept_note(v) for v in strict]
    assert all(k.startswith("kept by the editor:") for k in kept)


def test_the_editor_swaps_the_repeated_treatment() -> None:
    beats = [_beat(0, treatment="card"), _beat(1, treatment="card"), _beat(2, treatment="backdrop")]
    plan = _plan(beats)
    found = grammar.treatments(plan.beats, runtime=6.0, spec=_spec())
    problem = "; ".join(v.message for v in found)
    options = beat_options(plan, "b01", hard=False, treatments=ORDER)
    ids = [o.id for o in options]
    # never the neighbours' treatments, never its own
    assert "treatment:card" not in ids and "treatment:backdrop" not in ids
    assert "treatment:polaroid" in ids
    chosen = fallback_for(problem, options, hard=False)
    assert chosen.startswith("treatment:")
    option = next(o for o in options if o.id == chosen)
    assert option.apply is not None
    fixed = option.apply(plan)
    assert grammar.treatments(fixed.beats, runtime=6.0, spec=_spec()) == []


def test_the_swap_repair_sets_only_the_treatment() -> None:
    plan = _plan([_beat(0, treatment="card")])
    fixed = repairs.set_treatment(plan, "b00", "polaroid")
    assert fixed.beats[0].treatment == "polaroid"
    assert fixed.beats[0].model_dump(exclude={"treatment"}) == plan.beats[0].model_dump(
        exclude={"treatment"})  # fmt: skip
    with pytest.raises(repairs.RepairError):
        repairs.set_treatment(plan, "b00", "sparkles")


def test_no_swap_is_offered_on_a_beat_without_a_treatment() -> None:
    plan = _plan([_beat(0)])
    assert not [o for o in beat_options(plan, "b00", hard=False) if o.id.startswith("treatment:")]


# --- the style specs -----------------------------------------------------------------------


def test_every_shipped_style_lists_its_treatments_in_requires_components() -> None:
    specs = render.loaded_styles()
    for name in SHIPPED:
        spec = specs[name]
        assert set(spec.broll.treatments) <= set(spec.requires_components), name


def test_a_shipped_style_offering_a_treatment_it_does_not_require_is_refused() -> None:
    spec = _spec()
    bad = spec.model_copy(update={"requires_components": [
        c for c in spec.requires_components if c != "polaroid"]})  # fmt: skip
    with pytest.raises(styles.StyleError, match="polaroid"):
        styles.check(bad, render.registry())
