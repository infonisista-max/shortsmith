"""styles: the loader (decisions 1.2, 1.4, 6.3, 9.2) and the resolver (1.1).

Boundary tests per 12.2: missing key group, draft never resolves as shipped, the
PIP/caption collision assert, `requires_components` against the renderer registry;
resolver: alias hit, tie, zero hits, draft redirect notice. Variants of a real spec
are written to a temp directory by editing its front matter, so every failure test
starts from a spec that loads."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from shortsmith import fixture, render, styles
from shortsmith.styles import KEY_GROUPS, PROSE_SECTIONS, Resolution, StyleError, StyleSpec
from tests.conftest import flash_whoosh_style

REGISTRY = render.registry()  # ["captions", "pip"] today
NAMES = ("explainer", "educational", "animated", "hitech")
# 059: the three recipe styles built from the references; tests/test_recipe_styles.py
# judges their numbers. The facts below that pin the four styles above stay on those four.
RECIPES = ("fastfacts", "footage", "vishva")
# 059 changed the explainer's aliases (1.1 as amended): its front matter was v11; 064's
# 12 dB speech-band margin bumped every style once more.
VERSIONS = {"explainer": "24", "educational": "19", "animated": "19", "hitech": "23"}  # 103
FORBIDDEN = ["sweep", "riser", "rumble_crescendo"]  # 7.1, operator rider; 070 lifts whoosh


@pytest.fixture(scope="module")
def specs() -> dict[str, StyleSpec]:
    return styles.load_all(REGISTRY)


@pytest.fixture(scope="module")
def existing(specs: dict[str, StyleSpec]) -> dict[str, StyleSpec]:
    """The four styles before 059, whose overlay caps, flash and whoosh rules are pinned."""
    return {name: specs[name] for name in NAMES}


def _variant_dir(tmp_path: Path, name: str, mutate: Callable[[dict[str, Any]], None]) -> Path:
    """A copy of `styles/` with one spec's front matter changed by `mutate`."""
    target = tmp_path / "styles"
    shutil.copytree(styles.STYLES_DIR, target)
    path = target / f"{name}.md"
    front, body = styles.split_front_matter(path.read_text(encoding="utf-8"))
    mutate(front)
    path.write_text(f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n{body}", encoding="utf-8")
    return target


# --- the real specs -------------------------------------------------------------


def test_load_all_loads_the_seven_specs_and_the_drafts_stay_drafts(
    specs: dict[str, StyleSpec],
) -> None:
    assert set(specs) == set(NAMES) | set(RECIPES)
    assert styles.shipped(specs) == ["explainer", *RECIPES]
    assert [n for n in NAMES if specs[n].status == "draft"] == ["educational", "animated", "hitech"]
    for name, spec in specs.items():
        assert spec.name == name
        assert spec.aliases and name in spec.aliases


def test_every_spec_carries_the_eight_key_groups_and_the_five_prose_sections(
    specs: dict[str, StyleSpec],
) -> None:
    assert KEY_GROUPS == (
        "aliases", "beats", "presenter", "broll", "captions", "sound", "finale", "cut",
    )  # fmt: skip
    assert PROSE_SECTIONS == ("Beat grammar", "B-roll", "Captions", "Sound", "Finale")
    for spec in specs.values():
        numbers = spec.numbers()
        for group in KEY_GROUPS:
            assert group in numbers, (spec.name, group)
        for extra in ("status", "requires_components", "budget", "pip", "palette"):
            assert extra in numbers, (spec.name, extra)
        assert list(spec.sections) == list(PROSE_SECTIONS)
        assert all(text.strip() for text in spec.sections.values()), spec.name
        for heading in PROSE_SECTIONS:
            assert f"## {heading}" in spec.prose


def test_every_spec_names_a_default_bed_query_of_at_most_six_words(
    specs: dict[str, StyleSpec],
) -> None:
    """054: the last rung of the bed search ladder is the style's own plain words, so a
    short is never silent because the planner's theme sentence matched nothing."""
    for spec in specs.values():
        words = spec.sound.default_bed_query.split()
        assert 1 <= len(words) <= 6, (spec.name, spec.sound.default_bed_query)
        assert spec.version == VERSIONS.get(spec.name, "14"), spec.name
    assert specs["explainer"].sound.default_bed_query == "cinematic ambient documentary"


def test_every_style_lets_a_portrait_fill_the_frame_at_two_x(specs: dict[str, StyleSpec]) -> None:
    """057 (amending 5.1 and 5.3): the full-bleed limit is a style number, 2.0 in every
    shipped and draft style, and no spec's prose says web images are always cards."""
    for spec in specs.values():
        assert spec.broll.full_bleed_max_upscale == 2.0, spec.name
        assert "always re-dressed as cards" not in spec.sections["B-roll"], spec.name
        assert "always cards" not in spec.sections["B-roll"], spec.name
    assert "full_bleed_max_upscale" in specs["explainer"].sections["B-roll"]


def test_a_spec_without_the_full_bleed_limit_fails_to_load(tmp_path: Path) -> None:
    def drop(front: dict[str, Any]) -> None:
        del front["broll"]["full_bleed_max_upscale"]

    with pytest.raises(StyleError, match="full_bleed_max_upscale"):
        styles.load_all(REGISTRY, styles_dir=_variant_dir(tmp_path, "explainer", drop))


def test_every_style_puts_the_bed_14_db_under_the_voice_and_reuses_an_image_twice(
    specs: dict[str, StyleSpec],
) -> None:
    """056 (3, 5): the operator's run03 verdicts, in every style's front matter."""
    for spec in specs.values():
        assert spec.sound.bed_db_under_voice == -14, spec.name
        assert spec.sound.bed_accept_db == (-15, -12), spec.name
        assert spec.broll.reuse_max == 2, spec.name


def test_every_style_opens_in_pip_over_images_and_no_style_has_hook_cards(
    specs: dict[str, StyleSpec],
) -> None:
    """055 (3.4 as amended): every style opens with the speaker's first words as two or
    three quick pip beats over full-screen images; the hook fields, the hook-cards kind
    and the `cold_open` reason are gone from every front matter; each style names the
    pause it tightens to."""
    for spec in specs.values():
        assert (spec.beats.opening_beats_min, spec.beats.opening_beats_max) == (2, 3), spec.name
        assert spec.beats.opening_max_s >= 5.0, spec.name
        assert spec.presenter.opening_mode == "pip", spec.name
        assert "cold_open" not in spec.presenter.full_reasons, spec.name
        assert "hook_cards" not in spec.broll.kinds, spec.name
        assert "hook_cards" not in spec.requires_components, spec.name
        assert "hook_cards" not in spec.broll.motion, spec.name
        assert spec.broll.motion["finale"]["cards"] == 3, spec.name
        assert spec.cut.max_pause_s > spec.beats.snap_window_s, spec.name
        numbers = spec.numbers()
        for gone in ("cold_open_min_s", "hook_cards_min_s", "hook_title_max_words"):
            assert gone not in numbers["beats"], (spec.name, gone)
        assert "hook_modes" not in numbers["presenter"], spec.name
    assert specs["explainer"].cut.max_pause_s == 0.6
    assert specs["educational"].cut.max_pause_s == 0.8


def test_a_spec_without_the_cut_group_or_the_opening_numbers_fails_to_load() -> None:
    text = (styles.STYLES_DIR / "explainer.md").read_text(encoding="utf-8")
    without_cut = text.replace("cut:\n  max_pause_s: 0.6", "")
    with pytest.raises(StyleError, match="missing key group 'cut'"):
        styles.parse(without_cut, name="explainer")
    without_opening = text.replace("  opening_max_s: 5.0\n", "")
    with pytest.raises(StyleError, match="opening_max_s"):
        styles.parse(without_opening, name="explainer")


def test_forbidden_lists_ban_sweeps_and_risers_and_no_longer_chimes_or_ticks(
    specs: dict[str, StyleSpec],
) -> None:
    for spec in specs.values():
        # 070: every style allows a short whoosh on a transition, so none lists it
        assert spec.sound.forbidden == FORBIDDEN, spec.name
    assert "7.1" in specs["explainer"].sections["Sound"]


def test_explainer_numbers_are_the_grill_decisions(specs: dict[str, StyleSpec]) -> None:
    ex = specs["explainer"]
    assert (ex.beats.min_s, ex.beats.max_s, ex.beats.set_piece_max_s) == (0.7, 6.0, 8.0)  # 3.1
    assert (ex.beats.target_mean_s, ex.beats.mean_min_s, ex.beats.mean_max_s) == (2.5, 2.0, 3.2)
    assert ex.beats.density_gap_max_s == 1.5
    assert ex.presenter.modes == ["full", "pip", "off"]  # 3.2
    assert ex.presenter.full_max_fraction == 0.25 and ex.presenter.full_never_consecutive
    assert (ex.presenter.pip_max_run, ex.presenter.off_max_run) == (6, 3)
    assert ex.presenter.full_reasons == ["emotional_line", "argument_turn"]  # 055: no cold open
    assert (ex.pip.diameter, ex.pip.large_face_diameter, ex.pip.chin_anchor) == (300, 340, 0.82)
    assert ex.pip.large_face_ratio == 0.45  # 3.3
    assert ex.broll.enter_transitions == ["cut", "fade", "whip", "zoom", "spring"]  # 9.4
    assert ex.broll.whip_max_per_3_beats == 1
    assert (ex.broll.unique_assets_min_per_60s, ex.broll.unique_assets_max_per_60s) == (12, 24)
    assert ex.broll.reuse_max == 2  # 4.3 as amended by 056 (3): counted per image
    assert "photo" in ex.broll.kinds and "parallax" not in ex.broll.kinds  # 4.1 / 9.2
    assert ex.broll.tier2_kinds == []
    assert (ex.captions.font_family, ex.captions.size_px, ex.captions.font_weight) == (
        "Poppins", 74, 800,
    )  # fmt: skip
    assert (ex.captions.anchor_y, ex.captions.max_lines, ex.captions.line_height) == (1460, 2, 1.35)
    assert (ex.captions.words_per_page, ex.captions.prefer) == ((2, 4), 3)  # 6.1
    assert (ex.captions.emphasis_max_ratio, ex.captions.gap_break_s) == (0.25, 0.35)
    # 7.3 as amended by 056 (5): the operator's "30 % quieter" bed, -14 dB in every style.
    assert ex.sound.bed_db_under_voice == -14 and ex.sound.duck_max_db == 4
    assert ex.sound.bed_accept_db == (-15, -12)
    assert (ex.sound.cues_max_per_60s, ex.sound.cues_per_beat_max) == (20, 1)
    assert (ex.sound.swell_max_db, ex.sound.drop_min_db, ex.sound.ramp_min_s) == (4, -8, 1.5)
    assert (ex.finale.mode, ex.finale.min_s, ex.finale.max_s) == ("off", 0.8, 1.2)
    assert (ex.budget.judge_max_calls, ex.budget.search_max_queries) == (40, 60)  # 5.6
    assert ex.budget.gen_max_per_short == 8  # 5.5
    # 030: the full tier-1 list, the two B-roll treatments and the six transitions (9.2, 9.4);
    # 055 removed `hook_cards`.
    # 058 adds `clip`, the moving footage kind.
    # 103 adds the three picture treatments beside `photo` and `card`.
    assert ex.requires_components == [
        "captions", "pip", "photo", "card", "clip", "stamp", "lower_third", "finale",
        "list", "chart", "split", "wall", "infographic", "label_flyin", "counter", "map",
        "pin_drop", "route_arrow", "object_path", "crop_fill", "backdrop", "polaroid",
        "cut", "fade", "whip", "zoom", "spring", "wipe",
    ]  # fmt: skip
    # 029: the counter writes its digits in the audience's grouping.
    assert ex.broll.motion["counter"] == {"kind": "count_up", "grouping": "indian"}
    # 027: the three tier-1 set pieces carry their own counts and base motion (4.1, 5.2).
    assert ex.broll.motion["list"]["items_max"] == 6
    assert ex.broll.motion["split"]["panes"] == 2
    assert (ex.broll.motion["wall"]["cells_min"], ex.broll.motion["wall"]["cells_max"]) == (4, 9)
    # 021: the two infographic kinds are drawn in code from these numbers (9.2, 9.3).
    assert ex.broll.motion["chart"]["marks_max"] == 6
    assert ex.broll.motion["chart"]["grouping"] == "indian"
    assert ex.broll.motion["infographic"]["labels_max"] == 5
    assert ex.palette.accent == "#FFD60A"


# 055: `hook_cards` stays exported by the Node project (its component is still built) but
# no style requires it, so it is not in the list a shipped spec must cover.
TIER1_REGISTRY = [
    "captions", "pip", "photo", "card", "clip", "stamp", "lower_third", "finale",
    "list", "chart", "split", "wall", "infographic", "label_flyin", "counter", "map",
    "pin_drop", "route_arrow", "object_path",
    "cut", "fade", "whip", "zoom", "spring", "wipe",
]  # fmt: skip


def test_the_registry_holds_every_tier_1_component_and_the_six_transitions() -> None:
    """030: the renderer exports the whole tier-1 set (9.2) and the 9.4 vocabulary; the
    map (020) and its three animations (028) included."""
    assert set(TIER1_REGISTRY) <= set(REGISTRY), sorted(set(TIER1_REGISTRY) - set(REGISTRY))


def test_the_explainer_requires_the_whole_registry_list_and_loads_shipped(
    specs: dict[str, StyleSpec],
) -> None:
    ex = specs["explainer"]
    assert ex.status == "shipped"
    assert set(TIER1_REGISTRY) <= set(ex.requires_components)
    assert set(ex.requires_components) <= set(REGISTRY)


@pytest.mark.parametrize("component", TIER1_REGISTRY)
def test_removing_a_component_from_the_registry_fails_the_explainer(component: str) -> None:
    """030: a copy of the registry without one component, and the shipped spec that
    requires it does not load (9.2)."""
    without = [c for c in REGISTRY if c != component]
    with pytest.raises(StyleError, match=rf"explainer.*\b{component}\b.*registry"):
        styles.load_all(without)


def test_each_style_enables_its_9_4_transition_subset(specs: dict[str, StyleSpec]) -> None:
    assert specs["explainer"].broll.enter_transitions == ["cut", "fade", "whip", "zoom", "spring"]
    assert specs["hitech"].broll.enter_transitions == ["cut", "fade", "wipe", "zoom"]
    assert specs["educational"].broll.enter_transitions == ["cut", "fade"]
    assert specs["animated"].broll.enter_transitions == [
        "cut", "fade", "whip", "zoom", "spring", "wipe",
    ]  # fmt: skip
    for spec in specs.values():
        assert spec.broll.enter_transitions[0] == "cut", spec.name


def test_the_transition_numbers_are_the_9_4_decisions_in_every_spec(
    specs: dict[str, StyleSpec],
) -> None:
    """9.4: fade 0.35 s, whip 0.22 s with a 14 px directional blur, zoom 0.3 s from 1.6,
    spring damping 14 / stiffness 160 / mass 0.7, wipe 0.25 s; `cut` has no numbers."""
    for spec in specs.values():
        t = spec.broll.transitions
        assert t.fade.duration_s == 0.35, spec.name
        assert (t.whip.duration_s, t.whip.blur_px) == (0.22, 14), spec.name
        assert (t.zoom.duration_s, t.zoom.scale_from) == (0.3, 1.6), spec.name
        assert (t.spring.damping, t.spring.stiffness, t.spring.mass) == (14, 160, 0.7), spec.name
        assert t.wipe.duration_s == 0.25, spec.name


def test_a_transition_row_missing_from_the_front_matter_fails_the_loader(
    tmp_path: Path,
) -> None:
    """The vocabulary is global (9.4): every spec carries all five numbered rows, whether
    or not it enables the transition, so the renderer reads one shape."""

    def drop_whip(fm: dict[str, Any]) -> None:
        del fm["broll"]["transitions"]["whip"]

    where = _variant_dir(tmp_path, "educational", drop_whip)
    with pytest.raises(StyleError, match=r"educational.*broll\.transitions\.whip"):
        styles.load_all(REGISTRY, where)


# --- flash and the whoosh allowance (ticket 060; 9.4 and 7.3 as amended) ------------------

WHOOSH = {"max_per_60s": 6, "min_gap_s": 3.0, "max_len_s": 0.8, "on": ["flash", "pop"]}


def _allow_whoosh(fm: dict[str, Any]) -> None:
    """060's test style: `flash` enabled and the whoosh row on it and on pop-ins."""
    fm["broll"]["enter_transitions"].append("flash")
    fm["requires_components"].append("flash")
    fm["sound"]["forbidden"] = [f for f in fm["sound"]["forbidden"] if f != "whoosh"]
    fm["sound"]["whoosh"] = dict(WHOOSH)


def _forbid_whoosh(fm: dict[str, Any]) -> None:
    fm["sound"]["forbidden"] = [*fm["sound"]["forbidden"], "whoosh"]


def test_every_spec_carries_the_flash_row_and_cap_and_none_enables_it(
    existing: dict[str, StyleSpec],
) -> None:
    """060 (1, 2, 4): the flash is the sixth numbered row of the global vocabulary
    (0.3 s in the style's colour: explainer's accent, white elsewhere) and
    `broll.flash_max_per_60s` is 5 in every spec; none of the four existing styles
    enables `flash`."""
    for spec in existing.values():
        assert spec.broll.transitions.flash.duration_s == 0.3, spec.name
        assert spec.broll.flash_max_per_60s == 5, spec.name
        assert "flash" not in spec.broll.enter_transitions, spec.name
    explainer = existing["explainer"]
    assert explainer.broll.transitions.flash.color == explainer.palette.accent == "#FFD60A"
    for name in ("educational", "animated", "hitech"):
        assert existing[name].broll.transitions.flash.color == "#FFFFFF", name


def test_the_flash_row_missing_fails_the_loader_naming_the_spec(tmp_path: Path) -> None:
    """060: a style listing `flash` without a `transitions.flash` row cannot load; the
    row is required of every spec, enabled or not, like the other five (030)."""

    def drop_flash(fm: dict[str, Any]) -> None:
        fm["broll"]["enter_transitions"].append("flash")
        del fm["broll"]["transitions"]["flash"]

    where = _variant_dir(tmp_path, "explainer", drop_flash)
    with pytest.raises(StyleError, match=r"explainer.*broll\.transitions\.flash"):
        styles.load_all(REGISTRY, where)


def test_a_shipped_style_may_enable_flash_when_the_registry_exports_it(tmp_path: Path) -> None:
    def enable(fm: dict[str, Any]) -> None:
        fm["broll"]["enter_transitions"].append("flash")
        fm["requires_components"].append("flash")

    loaded = styles.load_all(REGISTRY, _variant_dir(tmp_path, "explainer", enable))["explainer"]
    assert loaded.broll.enter_transitions[-1] == "flash"
    assert "flash" in REGISTRY


def test_every_existing_style_now_allows_whooshes(existing: dict[str, StyleSpec]) -> None:
    """070 (operator, run04 QA: all styles) overrides 060 (4): explainer, educational,
    animated and hitech leave `whoosh` out of `forbidden` and carry the row, on their own
    non-cut enters and `pop`."""
    for spec in existing.values():
        assert "whoosh" not in spec.sound.forbidden and spec.sound.whoosh is not None, spec.name
        assert styles.allows_whoosh(spec.sound), spec.name
        moving = [t for t in spec.broll.enter_transitions if t != "cut"]
        assert spec.sound.whoosh.on == [*moving, "pop"], spec.name


def test_a_style_allows_whooshes_by_the_row_and_the_forbidden_list_together(
    tmp_path: Path,
) -> None:
    """060 (3): whooshes are allowed by leaving `whoosh` out of `sound.forbidden` AND
    carrying `sound.whoosh`; one without the other fails the loader naming the spec, and
    a trigger outside `flash` / `pop` fails too."""
    loaded = styles.load_all(REGISTRY, _variant_dir(tmp_path, "explainer", _allow_whoosh))
    allowance = loaded["explainer"].sound.whoosh
    assert styles.allows_whoosh(loaded["explainer"].sound)
    assert allowance is not None
    assert (allowance.max_per_60s, allowance.min_gap_s, allowance.max_len_s) == (6, 3.0, 0.8)
    assert allowance.on == ["flash", "pop"]

    def only_unforbidden(fm: dict[str, Any]) -> None:
        del fm["sound"]["whoosh"]

    with pytest.raises(StyleError, match=r"hitech.*sound\.whoosh"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "a", "hitech", only_unforbidden))

    with pytest.raises(StyleError, match=r"hitech.*whoosh.*forbidden"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "b", "hitech", _forbid_whoosh))

    def bad_trigger(fm: dict[str, Any]) -> None:
        _allow_whoosh(fm)
        fm["sound"]["whoosh"]["on"] = ["cut"]

    with pytest.raises(StyleError, match=r"explainer.*whoosh.*on"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "c", "explainer", bad_trigger))


# --- text pops (ticket 061; 4.1 and 9.2 as amended) ---------------------------------------


def test_every_spec_carries_the_text_pop_row_and_a_cap_of_zero(
    existing: dict[str, StyleSpec],
) -> None:
    """061 (1, 4): the pop's numbers are a `broll.motion.text_pop` row in every spec
    (a 0.15-0.25 s overshoot, at most 2.5 s on screen, at most 2 per beat, a tilt of
    up to 8 degrees, Poppins 900) and `broll.text_pops_max_per_60s` is 0 in the four
    existing styles: off until the recipe styles of 059 turn it on."""
    for spec in existing.values():
        row = spec.broll.motion["text_pop"]
        assert row["kind"] == "pop", spec.name
        assert 0.15 <= float(row["duration_s"]) <= 0.25, spec.name
        assert float(row["hold_max_s"]) == 2.5, spec.name
        assert int(row["max_per_beat"]) == 2, spec.name
        assert 0 < float(row["tilt_deg"]) <= 8.0, spec.name
        assert int(row["size_px"]) > 0 and str(row["fill"]).startswith("#"), spec.name
        assert spec.broll.text_pops_max_per_60s == 0, spec.name
        assert "text_pop" not in spec.requires_components, spec.name
    assert "text_pop" in REGISTRY


def test_the_text_pop_row_or_cap_missing_fails_the_loader_naming_the_spec(tmp_path: Path) -> None:
    def drop_row(fm: dict[str, Any]) -> None:
        del fm["broll"]["motion"]["text_pop"]

    with pytest.raises(StyleError, match=r"explainer.*text_pop"):
        render.numbers_for(
            styles.load_all(REGISTRY, _variant_dir(tmp_path / "a", "explainer", drop_row))[
                "explainer"
            ]
        )

    def drop_cap(fm: dict[str, Any]) -> None:
        del fm["broll"]["text_pops_max_per_60s"]

    with pytest.raises(StyleError, match=r"hitech.*text_pops_max_per_60s"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "b", "hitech", drop_cap))


def test_the_test_style_helper_turns_text_pops_on(specs: dict[str, StyleSpec]) -> None:
    """The copy the grammar, the fake planner, the render and the smoke exercise 061
    under: the explainer with `text_pops_max_per_60s` raised to 10, so a six-second
    fixture allows one pop; nothing else changes and the original is untouched."""
    from tests.conftest import TEXT_POPS_PER_60S, text_pop_style

    styled = text_pop_style(specs["explainer"])
    assert styled.broll.text_pops_max_per_60s == TEXT_POPS_PER_60S == 10
    assert styled.broll.motion["text_pop"] == specs["explainer"].broll.motion["text_pop"]
    assert specs["explainer"].broll.text_pops_max_per_60s == 0, "the original is untouched"
    assert styled.model_dump(exclude={"broll"}) == specs["explainer"].model_dump(exclude={"broll"})


# --- moving footage (ticket 058; 4.1 and 5.1 as amended) ----------------------------------


def test_every_spec_carries_the_clip_row_and_the_clip_share(existing: dict[str, StyleSpec]) -> None:
    """058 (6): the clip's numbers are a `broll.motion.clip` row in every spec (no push:
    the clip's own movement is the motion, so 1.0 -> 1.0; speed 1.0) and
    `broll.clip_max_fraction` is 0.35 in the four existing styles (the reference median
    moving-footage share is 31 %); `clip` is a kind every style may plan, and the
    renderer exports it."""
    for spec in existing.values():
        row = spec.broll.motion["clip"]
        assert row["kind"] == "push", spec.name
        assert (float(row["scale_from"]), float(row["scale_to"])) == (1.0, 1.0), spec.name
        assert float(row["speed"]) == 1.0, spec.name
        assert spec.broll.clip_max_fraction == 0.35, spec.name
        assert "clip" in spec.broll.kinds, spec.name
        assert spec.version == VERSIONS[spec.name], spec.name
    assert "clip" in REGISTRY
    assert "clip" in existing["explainer"].requires_components
    assert "clip" in existing["hitech"].requires_components


def test_the_clip_row_or_share_missing_fails_the_loader_naming_the_spec(tmp_path: Path) -> None:
    def drop_row(fm: dict[str, Any]) -> None:
        del fm["broll"]["motion"]["clip"]

    with pytest.raises(StyleError, match=r"explainer.*clip"):
        render.numbers_for(
            styles.load_all(REGISTRY, _variant_dir(tmp_path / "a", "explainer", drop_row))[
                "explainer"
            ]
        )

    def drop_share(fm: dict[str, Any]) -> None:
        del fm["broll"]["clip_max_fraction"]

    with pytest.raises(StyleError, match=r"hitech.*clip_max_fraction"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "b", "hitech", drop_share))

    def over_one(fm: dict[str, Any]) -> None:
        fm["broll"]["clip_max_fraction"] = 1.5

    with pytest.raises(StyleError, match=r"hitech.*clip_max_fraction"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "c", "hitech", over_one))


# --- bubbles (ticket 063; 4.1 and 9.2 as amended) -----------------------------------------


def test_every_spec_carries_the_bubble_row_and_a_cap_of_zero(
    existing: dict[str, StyleSpec],
) -> None:
    """063 (1, 3, 5): the bubble's numbers are a `broll.motion.bubble` row in every spec
    (a 0.15-0.25 s overshoot, a hold, at most 2 per beat, 1-7 words, the dialogue gap
    inside 0.6-1.2 s, the type size with its minimum, the body width, white fill and dark
    ink) and `broll.bubbles_max_per_60s` is 0 in the four existing styles: off until the
    recipe styles of 059 turn it on."""
    for spec in existing.values():
        row = spec.broll.motion["bubble"]
        assert row["kind"] == "pop", spec.name
        assert 0.15 <= float(row["duration_s"]) <= 0.25, spec.name
        assert float(row["hold_max_s"]) > 0, spec.name
        assert int(row["max_per_beat"]) == 2, spec.name
        assert int(row["words_max"]) == 7, spec.name
        lo, hi = float(row["dialogue_gap_min_s"]), float(row["dialogue_gap_max_s"])
        assert 0.6 <= lo < hi <= 1.2, spec.name
        assert 0 < int(row["min_size_px"]) < int(row["size_px"]), spec.name
        assert int(row["width_px"]) > 0, spec.name
        assert str(row["fill"]).startswith("#") and str(row["ink"]).startswith("#"), spec.name
        assert spec.broll.bubbles_max_per_60s == 0, spec.name
        assert "bubble" not in spec.requires_components, spec.name
    assert "bubble" in REGISTRY


def test_the_bubble_row_or_cap_missing_fails_the_loader_naming_the_spec(tmp_path: Path) -> None:
    def drop_row(fm: dict[str, Any]) -> None:
        del fm["broll"]["motion"]["bubble"]

    with pytest.raises(StyleError, match=r"explainer.*bubble"):
        render.numbers_for(
            styles.load_all(REGISTRY, _variant_dir(tmp_path / "a", "explainer", drop_row))[
                "explainer"
            ]
        )

    def drop_cap(fm: dict[str, Any]) -> None:
        del fm["broll"]["bubbles_max_per_60s"]

    with pytest.raises(StyleError, match=r"hitech.*bubbles_max_per_60s"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "b", "hitech", drop_cap))


def test_the_test_style_helper_turns_bubbles_on(specs: dict[str, StyleSpec]) -> None:
    """The copy the grammar, the fake planner, the render and the smoke exercise 063
    under: the explainer with `bubbles_max_per_60s` raised to 20, so a six-second fixture
    allows the one dialogue pair; nothing else changes and the original is untouched."""
    from tests.conftest import BUBBLES_PER_60S, bubble_style

    styled = bubble_style(specs["explainer"])
    assert styled.broll.bubbles_max_per_60s == BUBBLES_PER_60S == 20
    assert styled.broll.motion["bubble"] == specs["explainer"].broll.motion["bubble"]
    assert specs["explainer"].broll.bubbles_max_per_60s == 0, "the original is untouched"
    assert styled.model_dump(exclude={"broll"}) == specs["explainer"].model_dump(exclude={"broll"})


def test_the_fixture_shaped_copy_scales_the_dialogue_gap_to_the_clip(
    specs: dict[str, StyleSpec],
) -> None:
    """063: no 0.5 s fake beat can hold a real 0.6 s dialogue gap, so the fixture-shaped
    copy scales `motion.bubble.dialogue_gap_*` as it scales the beat lengths; the
    shipped row is untouched."""
    scaled = fixture.smoke_specs(specs)["explainer"].broll.motion["bubble"]
    real = specs["explainer"].broll.motion["bubble"]
    assert scaled["dialogue_gap_min_s"] == fixture.SMOKE_BUBBLE["dialogue_gap_min_s"] == 0.2
    assert scaled["dialogue_gap_max_s"] == fixture.SMOKE_BUBBLE["dialogue_gap_max_s"] == 0.4
    assert float(real["dialogue_gap_min_s"]) == 0.6
    assert {k: v for k, v in scaled.items() if not k.startswith("dialogue_gap")} == {
        k: v for k, v in real.items() if not k.startswith("dialogue_gap")
    }


# --- stickers (ticket 062; 4.1 and 9.2 as amended) ----------------------------------------


def test_every_spec_carries_the_sticker_row_and_a_cap_of_zero(
    existing: dict[str, StyleSpec],
) -> None:
    """062 (3, 4): the sticker's numbers are a `broll.motion.sticker` row in every spec (a
    0.15-0.25 s overshoot, a hold, one per beat, a 180-320 px square, a gentle float)
    and `broll.stickers_max_per_60s` is 0 in the four existing styles: off until the
    recipe styles of 059 set theirs."""
    for spec in existing.values():
        row = spec.broll.motion["sticker"]
        assert row["kind"] == "pop", spec.name
        assert 0.15 <= float(row["duration_s"]) <= 0.25, spec.name
        assert float(row["hold_max_s"]) > 0, spec.name
        assert int(row["max_per_beat"]) == 1, spec.name
        assert 180 <= int(row["size_px"]) <= 320, spec.name
        assert 0 < float(row["float_px"]) <= 20 and float(row["float_period_s"]) > 0, spec.name
        assert spec.broll.stickers_max_per_60s == 0, spec.name
        assert "sticker" not in spec.requires_components, spec.name
        assert spec.version == VERSIONS[spec.name], spec.name
    assert "sticker" in REGISTRY


def test_the_sticker_row_or_cap_missing_or_oversized_fails_naming_the_spec(tmp_path: Path) -> None:
    def drop_row(fm: dict[str, Any]) -> None:
        del fm["broll"]["motion"]["sticker"]

    with pytest.raises(StyleError, match=r"explainer.*sticker"):
        render.numbers_for(
            styles.load_all(REGISTRY, _variant_dir(tmp_path / "a", "explainer", drop_row))[
                "explainer"
            ]
        )

    def drop_cap(fm: dict[str, Any]) -> None:
        del fm["broll"]["stickers_max_per_60s"]

    with pytest.raises(StyleError, match=r"hitech.*stickers_max_per_60s"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "b", "hitech", drop_cap))

    def too_big(fm: dict[str, Any]) -> None:
        fm["broll"]["motion"]["sticker"]["size_px"] = 400

    with pytest.raises(StyleError, match=r"explainer.*sticker.*180-320"):
        render.numbers_for(
            styles.load_all(REGISTRY, _variant_dir(tmp_path / "c", "explainer", too_big))[
                "explainer"
            ]
        )


def test_the_test_style_helper_turns_stickers_on(specs: dict[str, StyleSpec]) -> None:
    """The copy the grammar, the fake planner, the render and the smoke exercise 062
    under: the explainer with `stickers_max_per_60s` raised to 10, so a six-second
    fixture allows one; nothing else changes and the original is untouched."""
    from tests.conftest import STICKERS_PER_60S, sticker_style

    styled = sticker_style(specs["explainer"])
    assert styled.broll.stickers_max_per_60s == STICKERS_PER_60S == 10
    assert specs["explainer"].broll.stickers_max_per_60s == 0, "the original is untouched"
    assert styled.model_dump(exclude={"broll"}) == specs["explainer"].model_dump(exclude={"broll"})


def test_the_test_style_helper_enables_flash_and_allows_whooshes(
    specs: dict[str, StyleSpec],
) -> None:
    """The copy the grammar, sound and gate tests judge 060 under."""
    styled = flash_whoosh_style(specs["explainer"])
    assert styled.broll.enter_transitions[-1] == "flash"
    assert styles.allows_whoosh(styled.sound) and styled.sound.whoosh is not None
    assert "whoosh" not in styled.sound.forbidden
    assert specs["explainer"].broll.enter_transitions[-1] != "flash", "the original is untouched"


def test_explainer_pip_touches_the_caption_block_from_above(specs: dict[str, StyleSpec]) -> None:
    ex = specs["explainer"]
    line_h = ex.captions.size_px * ex.captions.line_height
    block_top = ex.captions.anchor_y - ex.captions.max_lines * line_h
    assert ex.pip.top + ex.pip.diameter == 1260 <= block_top  # 6.3


# --- loader failures (12.2) -----------------------------------------------------------


@pytest.mark.parametrize("group", KEY_GROUPS)
def test_a_missing_key_group_fails_naming_the_spec_and_the_group(
    tmp_path: Path, group: str
) -> None:
    where = _variant_dir(tmp_path, "explainer", lambda fm: fm.pop(group))
    with pytest.raises(StyleError, match=rf"explainer.*missing key group '{group}'"):
        styles.load_all(REGISTRY, where)


def test_a_missing_prose_section_fails(tmp_path: Path) -> None:
    where = _variant_dir(tmp_path, "hitech", lambda fm: None)
    path = where / "hitech.md"
    path.write_text(path.read_text(encoding="utf-8").replace("## Finale", "## Ending"), "utf-8")
    with pytest.raises(StyleError, match="hitech.*Finale"):
        styles.load_all(REGISTRY, where)


def test_a_pip_caption_collision_fails_the_loader(tmp_path: Path) -> None:
    """6.3: pip.top + pip.diameter must not pass the caption block's top (y 1260.2)."""

    def collide(fm: dict[str, Any]) -> None:
        fm["pip"]["top"] = 961  # 961 + 300 = 1261 > 1260.2

    where = _variant_dir(tmp_path, "explainer", collide)
    with pytest.raises(StyleError, match=r"explainer.*pip.*1261.*1260"):
        styles.load_all(REGISTRY, where)

    def just_fits(fm: dict[str, Any]) -> None:
        fm["pip"]["top"] = 960

    assert styles.load_all(REGISTRY, _variant_dir(tmp_path / "ok", "explainer", just_fits))


def test_a_shipped_spec_naming_a_component_absent_from_the_registry_fails(
    tmp_path: Path,
) -> None:
    def add(fm: dict[str, Any]) -> None:
        fm["requires_components"].append("hologram")

    where = _variant_dir(tmp_path, "explainer", add)
    with pytest.raises(StyleError, match=r"explainer.*hologram.*registry"):
        styles.load_all(REGISTRY, where)
    # The same component on a draft loads: it is due, not missing (9.2).
    where = _variant_dir(tmp_path / "draft", "hitech", add)
    assert "hologram" in styles.load_all(REGISTRY, where)["hitech"].requires_components


def test_drafts_may_require_components_the_registry_lacks(specs: dict[str, StyleSpec]) -> None:
    unbuilt = {
        c for n in ("educational", "animated") for c in specs[n].requires_components
    } - set(REGISTRY)
    assert unbuilt, "a draft should name at least one component still to build"


HITECH_COMPONENTS = [
    "captions", "pip", "photo", "card", "clip", "stamp", "lower_third", "finale",
    "list", "chart", "split", "wall", "infographic", "label_flyin", "counter", "map",
    "pin_drop", "route_arrow", "object_path", "crop_fill", "backdrop", "polaroid",
    "cut", "fade", "wipe", "zoom",
]  # fmt: skip


def test_hitech_is_a_draft_whose_components_are_all_in_the_registry(
    specs: dict[str, StyleSpec],
) -> None:
    """048: the draft the 1.4 smoke render uses names every component the render
    exercises and nothing the registry lacks; it stays a draft, so its aliases keep
    redirecting to explainer on the page."""
    hitech = specs["hitech"]
    assert hitech.status == "draft"
    assert set(hitech.requires_components) == set(HITECH_COMPONENTS)
    assert set(hitech.requires_components) <= set(REGISTRY)
    assert set(hitech.broll.enter_transitions) <= set(hitech.requires_components)
    assert "whip" not in hitech.requires_components
    assert "spring" not in hitech.requires_components
    # The renderer's readers accept the completed front matter: every motion row it
    # reads is there, with hitech's own palette and stamp colours.
    numbers = render.numbers_for(hitech)
    assert numbers.palette == hitech.palette
    assert numbers.palette.accent == "#22D3EE" and hitech.palette != specs["explainer"].palette
    assert render.stamp_colors(numbers)[0] == "#22D3EE"
    assert numbers.captions.size_px == 70 and numbers.captions.font_weight == 700


def test_components_doc_records_the_hitech_render(specs: dict[str, StyleSpec]) -> None:
    """048: `docs/components.md` lists every component the hitech smoke exercised, one
    table row per registry component (047 reads the same table)."""
    doc = (styles.STYLES_DIR.parent / "docs" / "components.md").read_text(encoding="utf-8")
    rows = [line for line in doc.splitlines() if line.startswith("| `")]
    named = {line.split("`")[1] for line in rows}
    assert set(REGISTRY) <= named, sorted(set(REGISTRY) - named)
    assert set(specs["hitech"].requires_components) <= named
    assert "hitech" in doc


def _make_draft(fm: dict[str, Any]) -> None:
    fm["status"] = "draft"


def test_explainer_must_exist_and_be_shipped(tmp_path: Path) -> None:
    with pytest.raises(StyleError, match="explainer.*shipped"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path, "explainer", _make_draft))
    where = _variant_dir(tmp_path / "gone", "explainer", lambda fm: None)
    (where / "explainer.md").unlink()
    with pytest.raises(StyleError, match="explainer"):
        styles.load_all(REGISTRY, where)


def test_an_unknown_status_or_stray_key_fails(tmp_path: Path) -> None:
    def bad_status(fm: dict[str, Any]) -> None:
        fm["status"] = "beta"

    with pytest.raises(StyleError, match="hitech"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path, "hitech", bad_status))

    def stray(fm: dict[str, Any]) -> None:
        fm["beats"]["mean"] = 2.5

    with pytest.raises(StyleError, match="animated.*mean"):
        styles.load_all(REGISTRY, _variant_dir(tmp_path / "s", "animated", stray))


# --- resolver (1.1, 1.4) --------------------------------------------------------------


def test_alias_hit_resolves_to_the_shipped_spec_with_the_line_as_the_note(
    specs: dict[str, StyleSpec],
) -> None:
    line = "Explainer, energetic, Hindi captions, about 45 seconds"
    assert styles.resolve(line, specs) == Resolution(name="explainer", note=line, notice="")


def test_a_draft_alias_resolves_to_explainer_with_the_notice(specs: dict[str, StyleSpec]) -> None:
    got = styles.resolve("hitech please", specs)
    assert got == Resolution(
        name="explainer", note="hitech please", notice="hitech not available yet, using explainer"
    )
    assert specs["hitech"].status == "draft"
    for line, draft in (("make it educational", "educational"), ("animated!", "animated")):
        got = styles.resolve(line, specs)
        assert got.name == "explainer"
        assert got.notice == f"{draft} not available yet, using explainer"


def test_highest_alias_count_wins(specs: dict[str, StyleSpec]) -> None:
    got = styles.resolve("tech gadget, explainer energy", specs)  # hitech 2, explainer 1
    assert got.notice.startswith("hitech")


def test_a_tie_falls_back_to_explainer_without_a_notice(specs: dict[str, StyleSpec]) -> None:
    got = styles.resolve("animated or hitech, you choose", specs)
    assert got == Resolution(name="explainer", note="animated or hitech, you choose", notice="")


def test_zero_hits_fall_back_to_explainer_without_a_notice(specs: dict[str, StyleSpec]) -> None:
    for line in ("", "   ", "something else entirely", "Hindi, punchy, 40 s"):
        assert styles.resolve(line, specs) == Resolution(name="explainer", note=line, notice="")


def test_resolution_is_case_insensitive_and_ignores_punctuation(
    specs: dict[str, StyleSpec],
) -> None:
    assert styles.resolve("HITECH!!!", specs).notice.startswith("hitech")
    assert styles.resolve("(Explainer)", specs) == Resolution("explainer", "(Explainer)", "")


def test_a_draft_never_resolves_as_shipped(specs: dict[str, StyleSpec]) -> None:
    for name, spec in specs.items():
        for alias in spec.aliases:
            got = styles.resolve(alias, specs)
            assert specs[got.name].status == "shipped", (name, alias)
            assert got.name == name or got.notice == f"{name} not available yet, using explainer"
