"""Banners and the light-flare transition (ticket 107; 083 part 2).

A `banner` is a top or lower bar of the recording's own words sliding in on its spoken
word (`Beat.banner`), and `light_flare` is a warm light burst peaking on the cut (a
`Transition`). Both are built from the v2 reference cards: every number lives in the
style front matter (`broll.banner`, `broll.transitions.light_flare`) and each is offered
only where the style's references use it. The grammar accepts them where the style
allows; the renderer places the banner inside the safe band, off the PIP circle and the
captions; Remotion draws both. No network, no key."""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from shortsmith import captions, ffmpeg, fixture, grammar, jobs, render, styles
from shortsmith.contracts import (
    Banner,
    BannerPosition,
    Constraints,
    Mode,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Violation,
)
from shortsmith.planner import FakePlanner
from shortsmith.reference.examples import load_effect_map
from shortsmith.safe_area import BAND_LEFT, BAND_WIDTH, SAFE_TOP_PX
from shortsmith.transcriber import FakeTranscriber

TRANSCRIPT = FakeTranscriber().transcribe(Path("unused.mp4"))
WORDS = TRANSCRIPT.words
REGISTRY = render.registry()
SPECS = styles.load_all(REGISTRY)
EXPLAINER = SPECS["explainer"]
OFFER_BANNER = ("explainer", "vishva")
OFFER_FLARE = ("explainer",)


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
    plan = FakePlanner().plan_picture(request)
    # the fake's wall (b10) flares where the style offers it; these tests place their own
    # (a spring, not a cut: 110b's non_cut_min_share)
    return _with(plan, "b10", enter="spring")


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


HELLO = Banner(text="HELLO THERE", word=1, position="top")


# --- the styles: numbers in front matter, offered where the references use it ------------


def test_the_banner_row_carries_the_reference_numbers_where_offered() -> None:
    for name in OFFER_BANNER:
        row = SPECS[name].broll.banner
        assert row is not None, name
        # M78CO3Ybr7U date_stamp and ePTZVwipoAM indus_war_tag slide in over 0.3 s; the
        # longest reference banner holds 2.0 s (bL3rUtUPYsc barabar_banner)
        assert (row.slide_s, row.hold_max_s, row.words_max) == (0.3, 2.0, 5), name
        assert "banner" in SPECS[name].requires_components, name
    assert SPECS["explainer"].broll.banner.max_per_60s == 1  # type: ignore[union-attr]
    assert SPECS["vishva"].broll.banner.max_per_60s == 2  # type: ignore[union-attr]
    for name, spec in SPECS.items():
        if name not in OFFER_BANNER:
            assert spec.broll.banner is None, name


def test_the_light_flare_is_offered_only_where_the_references_flare() -> None:
    row = EXPLAINER.broll.transitions.light_flare
    assert row is not None
    # QjwDTLPLJ6c: 13 flare cuts of 0.3 s in 176 s (4.4 a minute)
    assert (row.duration_s, row.max_per_60s) == (0.3, 4)
    assert "light_flare" in EXPLAINER.broll.enter_transitions
    assert "light_flare" in EXPLAINER.requires_components
    for name, spec in SPECS.items():
        if name not in OFFER_FLARE:
            assert "light_flare" not in spec.broll.enter_transitions, name


def _variant(tmp_path: Path, name: str, mutate: Any) -> Path:
    target = tmp_path / "styles"
    shutil.copytree(styles.STYLES_DIR, target)
    path = target / f"{name}.md"
    front, body = styles.split_front_matter(path.read_text(encoding="utf-8"))
    mutate(front)
    path.write_text(f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n{body}", encoding="utf-8")
    return target


def test_a_style_enabling_the_flare_without_its_row_fails_to_load(tmp_path: Path) -> None:
    def enable(fm: dict[str, Any]) -> None:
        fm["broll"]["enter_transitions"].append("light_flare")

    with pytest.raises(styles.StyleError, match=r"footage.*light_flare"):
        styles.load_all(REGISTRY, _variant(tmp_path, "footage", enable))


def test_a_shipped_style_offering_a_banner_must_require_it(tmp_path: Path) -> None:
    def unrequire(fm: dict[str, Any]) -> None:
        fm["requires_components"].remove("banner")

    with pytest.raises(styles.StyleError, match=r"vishva.*banner.*requires_components"):
        styles.load_all(REGISTRY, _variant(tmp_path, "vishva", unrequire))


def test_both_are_registered_and_the_effect_map_points_the_names_at_them() -> None:
    assert {"banner", "light_flare"} <= set(REGISTRY)
    mapped = load_effect_map()
    for name in ("banner_slide_down", "date_banner_slide", "text_banner_pop", "text_banner"):
        assert mapped[name] == "banner", name
    for name in ("light_flare", "light_burst"):
        assert mapped[name] == "light_flare", name


# --- the grammar ------------------------------------------------------------------------


def test_a_banner_on_a_picture_beat_passes_and_lands_on_its_word() -> None:
    result = _check(_with(_plan(), "b01", banner=HELLO))
    assert isinstance(result, grammar.PictureCheck), result
    banner = result.picture.beats[0].banner
    assert banner is not None and banner.at_s == pytest.approx(WORDS[1].start)


def test_a_banner_counts_as_a_change_on_screen_at_its_landing() -> None:
    beat = _with(_plan(), "b01", banner=HELLO.model_copy(update={"at_s": 0.36})).beats[0]
    assert 0.36 in grammar.change_times(beat)


def test_a_banner_under_a_style_that_offers_none_fails_naming_the_beat() -> None:
    result = _check(_with(_plan(_smoke("footage")), "b01", banner=HELLO), _smoke("footage"))
    found = _problems(result, "banner")
    assert found and found[0].beat_id == "b01" and "offers no banner" in found[0].message


def test_a_banner_over_the_cap_fails() -> None:
    plan = _with(_plan(), "b01", banner=HELLO)
    plan = _with(plan, "b03", banner=Banner(text="THIS", word=2, position="bottom"))
    found = _problems(_check(plan), "broll.banner.max_per_60s")
    assert [v.beat_id for v in found] == ["b03"]


def test_a_banner_of_too_many_words_or_off_its_beat_fails() -> None:
    long = HELLO.model_copy(update={"text": "one two three four five six"})
    assert _problems(_check(_with(_plan(), "b01", banner=long)), "words_max")
    elsewhere = HELLO.model_copy(update={"word": 5})
    assert _problems(_check(_with(_plan(), "b01", banner=elsewhere)), "does not cover")


def test_a_banner_sits_only_on_a_picture_beat() -> None:
    plan = _with(_plan(), "b05", banner=Banner(text="A SHORT", word=5))
    assert _problems(_check(plan), "sits on a picture beat")


def test_the_flare_is_accepted_where_offered_capped_and_never_twice_in_a_row() -> None:
    flared = _with(_plan(), "b03", enter="light_flare")
    assert isinstance(_check(flared), grammar.PictureCheck)
    footage = _smoke("footage")
    refused = _check(_with(_plan(footage), "b03", enter="light_flare"), footage)
    assert _problems(refused, "not in broll.enter_transitions")
    twice = _with(flared, "b04", enter="light_flare")
    assert _problems(_check(twice), "two light flares in a row")


def test_the_flare_cap_scales_with_the_runtime() -> None:
    assert grammar.light_flare_cap(EXPLAINER, runtime=60.0) == 4
    assert grammar.light_flare_cap(EXPLAINER, runtime=6.0) == 1
    plan = _with(_with(_plan(), "b03", enter="light_flare"), "b06", enter="light_flare")
    found = _problems(_check(plan), "max_per_60s")
    assert [v.beat_id for v in found] == ["b06"]


# --- the render spec ----------------------------------------------------------------------


NUMBERS = render.numbers_for(EXPLAINER)


def _banner(position: BannerPosition, mode: Mode) -> Any:
    banner = Banner(text="HELLO THERE", word=1, position=position, at_s=0.36)
    pip = render.fixed_pip((1080, 1920), NUMBERS)
    return render.banner_spec(banner, mode=mode, beat_start_s=0.0, beat_end_s=0.5,
                              numbers=NUMBERS, pip=pip)  # fmt: skip


def test_a_top_banner_spans_the_safe_band_under_the_top_zone() -> None:
    row = EXPLAINER.broll.banner
    assert row is not None
    spec = _banner("top", "pip")
    assert (spec.left, spec.width) == (BAND_LEFT, BAND_WIDTH)
    assert spec.top == row.top_y >= SAFE_TOP_PX
    assert spec.height == row.height_px and spec.from_top
    assert (spec.fill, spec.ink, spec.bar) == (row.fill, row.ink, row.bar)
    assert row.min_size_px <= spec.font_px <= row.size_px


def test_a_lower_banner_sits_above_the_circle_on_a_pip_beat_and_the_captions_else() -> None:
    row = EXPLAINER.broll.banner
    assert row is not None
    pip = render.fixed_pip((1080, 1920), NUMBERS)
    on_pip = _banner("bottom", "pip")
    assert on_pip.top + on_pip.height == pytest.approx(pip.top - row.gap_px)
    assert not on_pip.from_top
    full = _banner("bottom", "full")
    band_top = styles.caption_block_top(EXPLAINER.captions)
    assert full.top + full.height == pytest.approx(band_top - row.gap_px)


def test_the_banner_slides_in_on_its_word_and_holds_to_the_beat_or_its_cap() -> None:
    row = EXPLAINER.broll.banner
    assert row is not None
    spec = _banner("top", "pip")
    assert (spec.at_s, spec.slide_s) == (pytest.approx(0.36), row.slide_s)
    assert spec.until_s == pytest.approx(0.5)  # the beat ends before the 2.0 s hold
    long = render.banner_spec(
        Banner(text="HELLO", word=0, at_s=1.0), mode="pip", beat_start_s=0.0, beat_end_s=6.0,
        numbers=NUMBERS, pip=render.fixed_pip((1080, 1920), NUMBERS),
    )  # fmt: skip
    assert long.until_s == pytest.approx(1.0 + row.hold_max_s)


def test_a_banner_too_long_for_the_band_at_its_smallest_type_fails_naming_it() -> None:
    wide = Banner(text="W" * 60, word=0, at_s=0.2)
    with pytest.raises(render.RenderError, match="banner"):
        render.banner_spec(wide, mode="pip", beat_start_s=0.0, beat_end_s=0.5, numbers=NUMBERS,
                           pip=render.fixed_pip((1080, 1920), NUMBERS))  # fmt: skip


def _spec_of(plan: PicturePlan) -> Any:
    return render.build_spec(
        plan, captions.build(TRANSCRIPT, plan, EXPLAINER), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        numbers=NUMBERS,
    )  # fmt: skip


def _validated(plan: PicturePlan) -> PicturePlan:
    result = _check(plan)
    assert isinstance(result, grammar.PictureCheck), result
    return result.picture


def test_the_render_spec_carries_the_banner_and_the_flare_numbers() -> None:
    plan = _validated(_with(_with(_plan(), "b01", banner=HELLO), "b03", enter="light_flare"))
    spec = _spec_of(plan)
    assert spec.beats[0].banner is not None and spec.beats[0].banner.text == "HELLO THERE"
    assert spec.beats[1].banner is None
    assert spec.beats[2].enter == "light_flare"
    assert spec.transitions.light_flare == EXPLAINER.broll.transitions.light_flare
    assert "light_flare" in spec.transitions.enabled


# --- one real render (Remotion) ------------------------------------------------------------


Frame = tuple[int, int, bytes]


def _pixel(frame: Frame, x: float, y: float) -> tuple[int, int, int]:
    width, _, data = frame
    i = 3 * (round(y) * width + round(x))
    return data[i], data[i + 1], data[i + 2]


def _near(got: tuple[int, int, int], hex_colour: str, tol: int = 40) -> bool:
    want = tuple(int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return max(abs(a - b) for a, b in zip(got, want, strict=True)) <= tol


def test_the_banner_slides_in_and_the_flare_burns_over_the_cut(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """107 end to end through Remotion over b01-b03 (0-1.5 s). The banner's bar colour is
    absent before its word (frame 5, 0.17 s) and fills its box once slid in (frame 14);
    around b03's cut (1.0 s, frame 30) the flare lifts the frame's brightness far over
    the same point two tenths later; the PIP circle is never tinted by the banner."""
    job = jobs.create(tmp_path, style="explainer", style_note="explainer")
    shutil.copyfile(fixture_clip, job.input_dir / "raw.mp4")
    plan = _validated(_with(_with(_plan(), "b01", banner=HELLO), "b03", enter="light_flare"))
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    (job.work_dir / "captions.json").write_text(
        captions.build(TRANSCRIPT, plan, EXPLAINER).model_dump_json(), encoding="utf-8"
    )
    render.cut_presenter(job)
    spec = render.spec_for_job(job).model_copy(update={"frames": 45})
    banner = spec.beats[0].banner
    assert banner is not None
    out = job.work_dir / "picture.mp4"
    render.run_driver(spec, spec_path=job.work_dir / "spec.json", out_path=out,
                      log_path=job.work_dir / "render.log")  # fmt: skip
    frames = ffmpeg.frames_rgb(out, fps=30, width=1080, duration_s=1.5)
    # a point on the bar's body, clear of the words (its left end)
    x, y = banner.left + 12, banner.top + banner.height / 2
    assert not _near(_pixel(frames[5], x, y), banner.fill, tol=20)
    assert _near(_pixel(frames[14], x, y), banner.fill)
    row = EXPLAINER.broll.transitions.light_flare
    assert row is not None

    def lum(frame: Frame, px: float, py: float) -> float:
        r, g, b = _pixel(frame, px, py)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    fx, fy = 540.0, row.y * 1920
    burnt = max(lum(frames[i], fx, fy) for i in (29, 30))
    assert burnt > 225 and burnt > lum(frames[37], fx, fy) + 40
    assert not math.isclose(burnt, lum(frames[37], fx, fy))


# --- the prompt and the editor ------------------------------------------------------------


def test_the_picture_prompt_names_the_banner_and_the_flare() -> None:
    text = (Path(__file__).parents[1] / "src" / "shortsmith" / "planner" / "prompts"
            / "picture_v20.md").read_text(encoding="utf-8")  # fmt: skip
    assert "`light_flare`" in text and "broll.transitions.light_flare.max_per_60s" in text
    assert "`banner`" in text and "broll.banner.words_max" in text
    assert "broll.banner.max_per_60s" in text


def test_the_editor_can_drop_a_banner_it_cannot_keep() -> None:
    from shortsmith.editor import repairs

    beat = _with(_plan(), "b01", banner=HELLO).beats[0]
    assert "banner" in repairs.layers_of(beat)
    plan = repairs.drop_layer(_with(_plan(), "b01", banner=HELLO), "b01", "banner")
    assert plan.beats[0].banner is None
    assert repairs.strip_overlays(_with(_plan(), "b01", banner=HELLO)).beats[0].banner is None
