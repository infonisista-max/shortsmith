"""Cash and particle overlays (ticket 109; 083 part 4).

A money line (oil wealth, budgets) may carry falling banknotes (`cash`: currency_shower,
cash_cascade - QjwDTLPLJ6c) and a thinking line drifting glowing particles (`brain`:
brain_particles_overlay - zXK42RMPKUY): `Beat.particles`, drawn in code with no stock
asset, landing on the spoken word, capped per 60 s in front matter (`broll.particles`),
offered where the references use them, and never over a face, the PIP circle or the
captions. No network, no key."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shortsmith import captions, ffmpeg, fixture, grammar, render, styles
from shortsmith.contracts import (
    BeatSpec,
    Captions,
    Constraints,
    ParticlesPlan,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Violation,
)
from shortsmith.planner import FakePlanner
from shortsmith.reference.examples import load_effect_map
from shortsmith.safe_area import SAFE_LEFT, SAFE_RIGHT_PX, SAFE_TOP_PX, WIDTH
from shortsmith.transcriber import FakeTranscriber

TRANSCRIPT = FakeTranscriber().transcribe(Path("unused.mp4"))
WORDS = TRANSCRIPT.words
REGISTRY = render.registry()
SPECS = styles.load_all(REGISTRY)
EXPLAINER = SPECS["explainer"]
NUMBERS = render.numbers_for(EXPLAINER)
PIP = render.fixed_pip((1080, 1920), NUMBERS)
CASH = ParticlesPlan(kind="cash", word=1)


def _smoke(name: str = "explainer") -> styles.StyleSpec:
    return fixture.smoke_specs(SPECS, name)[name]


def _plan(spec: styles.StyleSpec | None = None) -> PicturePlan:
    spec = spec or _smoke()
    request = PlanRequest(
        brief="Topic: a six-second synthetic clip.",
        style=PlanStyle(name=spec.name, numbers=spec.numbers(), prose=spec.prose),
        style_note=spec.name, transcript=TRANSCRIPT, references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )  # fmt: skip
    return FakePlanner().plan_picture(request)


def _with(plan: PicturePlan, beat_id: str, **update: Any) -> PicturePlan:
    return plan.model_copy(update={"beats": [
        b.model_copy(update=update) if b.id == beat_id else b for b in plan.beats
    ]})  # fmt: skip


Checked = grammar.PictureCheck | grammar.Violations


def _check(plan: PicturePlan, spec: styles.StyleSpec | None = None) -> Checked:
    return grammar.validate_picture(plan, TRANSCRIPT, spec or _smoke())


def _problems(result: Checked, needle: str) -> list[Violation]:
    assert isinstance(result, grammar.Violations), "the plan passed"
    return [v for v in result.items if needle in v.message]


# --- the styles -------------------------------------------------------------------------


def test_the_explainer_rains_cash_and_fastfacts_drifts_brain_particles() -> None:
    cash = EXPLAINER.broll.particles
    assert cash is not None and list(cash.kinds) == ["cash"]
    # QjwDTLPLJ6c: currency_shower on screen 3.8 s, two money overlays in 179 s
    assert (cash.max_per_60s, cash.kinds["cash"].hold_max_s) == (1, 3.8)
    brain = SPECS["fastfacts"].broll.particles
    assert brain is not None and list(brain.kinds) == ["brain"]
    # zXK42RMPKUY: brain_particles_overlay 1.7 s, one in 58 s
    assert (brain.max_per_60s, brain.kinds["brain"].hold_max_s) == (1, 1.7)
    for name in ("explainer", "fastfacts"):
        assert "particles" in SPECS[name].requires_components, name
    for name, spec in SPECS.items():
        if name not in ("explainer", "fastfacts"):
            assert spec.broll.particles is None, name


def test_particles_are_registered_and_the_effect_map_points_the_three_names_at_them() -> None:
    assert "particles" in REGISTRY
    mapped = load_effect_map()
    for name in ("currency_shower", "cash_cascade", "brain_particles_overlay"):
        assert mapped[name] == "particles", name


# --- the grammar ------------------------------------------------------------------------


def test_cash_on_a_money_beat_passes_and_lands_on_its_word() -> None:
    result = _check(_with(_plan(), "b01", particles=CASH))
    assert isinstance(result, grammar.PictureCheck), result
    landed = result.picture.beats[0].particles
    assert landed is not None and landed.at_s == pytest.approx(WORDS[1].start)
    assert WORDS[1].start in grammar.change_times(result.picture.beats[0])


def test_a_kind_the_style_does_not_offer_fails() -> None:
    brain = _with(_plan(), "b01", particles=CASH.model_copy(update={"kind": "brain"}))
    assert _problems(_check(brain), "offers no brain particles")
    footage = _smoke("footage")
    assert _problems(_check(_with(_plan(footage), "b01", particles=CASH), footage),
                     "offers no cash particles")  # fmt: skip


def test_particles_over_the_cap_off_their_beat_or_on_a_set_piece_fail() -> None:
    plan = _with(_with(_plan(), "b01", particles=CASH), "b03",
                 particles=CASH.model_copy(update={"word": 2}))  # fmt: skip
    assert [v.beat_id for v in _problems(_check(plan), "broll.particles.max_per_60s")] == ["b03"]
    assert _problems(_check(_with(_plan(), "b01", particles=CASH.model_copy(update={"word": 5}))),
                     "does not cover")  # fmt: skip
    assert _problems(_check(_with(_plan(), "b08", particles=CASH.model_copy(
        update={"word": 7}))), "sits on a picture beat")  # fmt: skip


# --- the render spec: never over a face, the circle or the captions ------------------------


def _spec(mode: Any = "pip", face: render.Box | None = None, at_s: float = 1.0) -> Any:
    return render.particles_spec(CASH.model_copy(update={"at_s": at_s}), mode=mode,
                                 beat_start_s=0.0, beat_end_s=6.0, numbers=NUMBERS, pip=PIP,
                                 face=face)  # fmt: skip


def _box(spec: Any) -> tuple[float, float, float, float]:
    return (spec.left, spec.top, spec.left + spec.width, spec.top + spec.height)


def test_the_cash_falls_in_the_safe_band_above_the_circle_and_the_captions() -> None:
    row = EXPLAINER.broll.particles
    assert row is not None
    spec = _spec()
    left, top, right, bottom = _box(spec)
    assert left >= SAFE_LEFT and right <= WIDTH - SAFE_RIGHT_PX and top >= SAFE_TOP_PX
    assert bottom <= PIP.top  # a pip beat: the circle
    full = _box(_spec(mode="full"))
    assert full[3] <= styles.caption_block_top(EXPLAINER.captions)  # else the captions
    kind = row.kinds["cash"]
    assert (spec.count, spec.size_px, spec.fall_s, spec.colors) == (
        kind.count, kind.size_px, kind.fall_s, kind.colors,
    )  # fmt: skip
    assert (spec.at_s, spec.until_s) == (1.0, pytest.approx(1.0 + kind.hold_max_s))


def test_the_particles_keep_off_a_face_taking_the_larger_free_band() -> None:
    face = render.Box(300.0, 700.0, 300.0, 300.0)
    spec = _spec(face=face)
    _, top, _, bottom = _box(spec)
    assert bottom <= face.top or top >= face.bottom
    assert top == SAFE_TOP_PX and bottom <= face.top  # above it: the larger band


def test_with_no_room_beside_the_face_the_particles_are_dropped() -> None:
    face = render.Box(100.0, 260.0, 700.0, 680.0)  # the whole band above the circle
    assert _spec(face=face) is None


def test_the_build_places_the_beats_particles_timed_on_its_word() -> None:
    plan = _with(_plan(), "b01", particles=CASH.model_copy(update={"at_s": 0.36}))
    spec = render.build_spec(
        plan, captions.build(TRANSCRIPT, plan, EXPLAINER), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        numbers=NUMBERS,
    )  # fmt: skip
    placed = spec.beats[0].particles
    assert placed is not None and placed.kind == "cash"
    assert placed.at_s == pytest.approx(0.36) and placed.until_s == pytest.approx(0.5)


# --- one real render (Remotion) ------------------------------------------------------------


Frame = tuple[int, int, bytes]


def _differs(a: Frame, b: Frame, box: tuple[float, float, float, float]) -> float:
    width, _, da = a
    _, _, db = b
    left, top, right, bottom = (round(v) for v in box)
    worst = 0
    for y in range(top, bottom, 6):
        for x in range(left, right, 6):
            i = 3 * (y * width + x)
            worst = max(worst, sum(abs(da[i + k] - db[i + k]) for k in range(3)))
    return worst


def test_the_notes_fall_inside_their_area_and_nowhere_else(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """109 through Remotion: one 1.5 s `off` beat with cash landing at 0.3 s. Nothing is
    drawn before the word; after it the area changes frame to frame (the notes fall);
    below the area - the circle's and the captions' place - the frame never changes."""
    base = render.build_spec(
        PicturePlan.model_validate({
            "prompt_version": "t", "cut": {"keep": [{"start": 0.0, "end": 1.5}]},
            "beats": [{"id": "b01", "start": 0.0, "end": 1.5, "mode": "off", "kind": "photo"}],
            "finale": {"beat_id": "none", "text": ""}, "title": "t", "description": "t",
        }),
        Captions(pages=[]), presenter=fixture_clip,
        source_size=ffmpeg.video_size(fixture_clip), duration_s=1.5, numbers=NUMBERS,
    )  # fmt: skip
    cash = render.particles_spec(CASH.model_copy(update={"at_s": 0.3}), mode="pip",
                                 beat_start_s=0.0, beat_end_s=1.5, numbers=NUMBERS, pip=PIP,
                                 face=None)  # fmt: skip
    assert cash is not None
    beat = BeatSpec(id="b01", start_frame=0, end_frame=45, mode="off", kind="photo",
                    particles=cash)  # fmt: skip
    spec = base.model_copy(update={"beats": [beat], "frames": 45})
    work = tmp_path / "p"
    work.mkdir()
    render.run_driver(spec, spec_path=work / "spec.json", out_path=work / "p.mp4",
                      log_path=work / "r.log")  # fmt: skip
    frames = ffmpeg.frames_rgb(work / "p.mp4", fps=30, width=1080, duration_s=1.5)
    area = _box(cash)
    assert _differs(frames[0], frames[7], area) < 12  # before the word: nothing
    assert _differs(frames[20], frames[26], area) > 60  # notes falling
    below = (0.0, area[3] + 4, 1080.0, 1900.0)
    assert _differs(frames[0], frames[26], below) < 12


# --- the prompt and the editor ------------------------------------------------------------


def test_the_picture_prompt_names_the_particles() -> None:
    text = (Path(__file__).parents[1] / "src" / "shortsmith" / "planner" / "prompts"
            / "picture_v20.md").read_text(encoding="utf-8")  # fmt: skip
    assert "`particles`" in text and "broll.particles.max_per_60s" in text
    assert "`cash`" in text and "`brain`" in text


def test_the_editor_can_drop_the_particles() -> None:
    from shortsmith.editor import repairs

    plan = _with(_plan(), "b01", particles=CASH)
    assert "particles" in repairs.layers_of(plan.beats[0])
    assert repairs.drop_layer(plan, "b01", "particles").beats[0].particles is None
    assert repairs.strip_overlays(plan).beats[0].particles is None
