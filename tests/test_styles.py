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

from shortsmith import render, styles
from shortsmith.styles import KEY_GROUPS, PROSE_SECTIONS, Resolution, StyleError, StyleSpec

REGISTRY = render.registry()  # ["captions", "pip"] today
NAMES = ("explainer", "educational", "animated", "hitech")
FORBIDDEN = ["sweep", "riser", "rumble_crescendo", "whoosh"]  # 7.1, operator rider


@pytest.fixture(scope="module")
def specs() -> dict[str, StyleSpec]:
    return styles.load_all(REGISTRY)


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


def test_load_all_loads_the_four_specs_and_only_explainer_is_shipped(
    specs: dict[str, StyleSpec],
) -> None:
    assert set(specs) == set(NAMES)
    assert specs["explainer"].status == "shipped"
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
        assert spec.version == "5", spec.name  # the front matter changed again (057)
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
    assert ex.requires_components == [
        "captions", "pip", "photo", "card", "stamp", "lower_third", "finale",
        "list", "chart", "split", "wall", "infographic", "label_flyin", "counter", "map",
        "pin_drop", "route_arrow", "object_path",
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
    "captions", "pip", "photo", "card", "stamp", "lower_third", "finale",
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
    "captions", "pip", "photo", "card", "stamp", "lower_third", "finale",
    "list", "chart", "split", "wall", "infographic", "label_flyin", "counter", "map",
    "pin_drop", "route_arrow", "object_path",
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
