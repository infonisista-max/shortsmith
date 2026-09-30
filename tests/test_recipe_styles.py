"""The three recipe styles of ticket 059 (`footage`, `vishva`, `fastfacts`): each a shipped
spec built from the reference inventory's measured numbers, with the explainer's captions,
PIP, opening, finale, bed level and loudness, `flash` enabled and whooshes allowed under
060's rule; the resolver's new aliases (1.1 as amended); the style README's trace table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shortsmith import render, styles
from shortsmith.styles import StyleSpec

REGISTRY = render.registry()
RECIPES = ("footage", "vishva", "fastfacts")
WHOOSH = {
    "max_per_60s": 6, "min_gap_s": 3.0, "max_len_s": 0.8,
    "on": ["fade", "whip", "zoom", "spring", "flash", "pop"],  # 070: every non-cut enter
}  # fmt: skip
README = styles.STYLES_DIR / "README.md"
# The reference ids each recipe was measured from (the ticket's table).
REFERENCES = {
    "footage": ("S5j-2CWYYwM", "ATkSnL_CdLg", "VSJzviqMO7k", "cKxkAjYHXbk"),
    "vishva": ("FbaBcWgMIEY", "ePTZVwipoAM", "nBihHUlYOQk"),
    "fastfacts": ("Q2pquJ2FlzA", "zXK42RMPKUY"),
}


@pytest.fixture(scope="module")
def specs() -> dict[str, StyleSpec]:
    return styles.load_all(REGISTRY)


def test_the_three_recipes_load_shipped_at_version_3_with_every_component_registered(
    specs: dict[str, StyleSpec],
) -> None:
    for name in RECIPES:
        spec = specs[name]
        assert spec.status == "shipped" and spec.version == "13", name  # 064 v1 ... 105 v13
        missing = [c for c in spec.requires_components if c not in REGISTRY]
        assert not missing, (name, missing)
        for component in ("clip", "flash", "text_pop"):
            assert component in spec.requires_components, (name, component)
        assert list(spec.sections) == list(styles.PROSE_SECTIONS), name
    for component in ("bubble", "sticker"):
        assert component in specs["vishva"].requires_components, component
    assert "sticker" in specs["footage"].requires_components
    assert "title_strip" in specs["fastfacts"].requires_components
    assert "title_strip" in REGISTRY
    assert styles.shipped(specs) == ["explainer", "fastfacts", "footage", "vishva"]


@pytest.mark.parametrize("name", RECIPES)
def test_each_recipe_keeps_the_explainer_captions_pip_opening_finale_and_bed(
    specs: dict[str, StyleSpec], name: str
) -> None:
    """In all three (run03: "subtitles perfect"): captions number for number, the PIP
    geometry, the 055 opening, the finale and the bed at -14 dB are the explainer's."""
    ex, spec = specs["explainer"], specs[name]
    assert spec.captions == ex.captions
    assert spec.pip == ex.pip
    opening = ("opening_beats_min", "opening_beats_max", "opening_max_s", "snap_window_s")
    assert [getattr(spec.beats, k) for k in opening] == [getattr(ex.beats, k) for k in opening]
    assert spec.presenter.opening_mode == ex.presenter.opening_mode == "pip"
    assert spec.finale == ex.finale
    assert spec.cut == ex.cut
    level = ("bed_db_under_voice", "bed_accept_db", "speech_band_hz", "speech_band_margin_db")
    assert [getattr(spec.sound, k) for k in level] == [getattr(ex.sound, k) for k in level]
    assert spec.sound.bed_db_under_voice == -14


@pytest.mark.parametrize("name", RECIPES)
def test_each_recipe_flashes_and_allows_whooshes_under_the_060_rule(
    specs: dict[str, StyleSpec], name: str
) -> None:
    spec = specs[name]
    assert "flash" in spec.broll.enter_transitions
    assert styles.allows_whoosh(spec.sound)
    assert spec.sound.whoosh is not None
    assert spec.sound.whoosh.model_dump() == WHOOSH
    for banned in ("sweep", "riser", "rumble_crescendo"):
        assert banned in spec.sound.forbidden, banned


def test_footage_is_moving_clips_under_the_pip_with_the_dhruv_flash(
    specs: dict[str, StyleSpec],
) -> None:
    """A shot every ~2.2 s; clips up to 0.75 of the runtime; the presenter full-frame at
    argument turns up to 0.25; pops about 1 per 10 s, a sticker at most every ~20 s."""
    spec = specs["footage"]
    assert spec.beats.target_mean_s == 2.2
    assert spec.beats.mean_min_s <= 2.2 <= spec.beats.mean_max_s
    assert spec.broll.clip_max_fraction == 0.75
    assert spec.presenter.full_max_fraction == 0.25
    assert "argument_turn" in spec.presenter.full_reasons
    assert spec.broll.text_pops_max_per_60s == 6
    assert spec.broll.stickers_max_per_60s == 3
    assert spec.broll.bubbles_max_per_60s == 0


def test_vishva_is_full_screen_stills_dense_overlays_and_stacked_panels(
    specs: dict[str, StyleSpec],
) -> None:
    """A shot every ~2.6 s over stills; clips at most 0.15; about 2.5 overlays per 10 s
    across pops, bubbles and stickers; the split drawn as two stacked panels."""
    spec = specs["vishva"]
    assert spec.beats.target_mean_s == 2.6
    assert spec.broll.clip_max_fraction == 0.15
    b = spec.broll
    assert b.text_pops_max_per_60s > 0 and b.bubbles_max_per_60s > 0 and b.stickers_max_per_60s > 0
    assert b.text_pops_max_per_60s + b.bubbles_max_per_60s + b.stickers_max_per_60s == 15
    assert b.motion["split"]["layout"] == "stacked"
    assert render.numbers_for(spec).broll.split_layout == "stacked"


def test_fastfacts_is_fast_cuts_under_a_fixed_title_strip(specs: dict[str, StyleSpec]) -> None:
    """A shot every ~1.2 s (`beats.min_s` 0.5); clips up to 0.7; the title strip of at
    most five words; a text pop on every number; asset bounds scaled to the pace."""
    spec, ex = specs["fastfacts"], specs["explainer"]
    assert spec.beats.min_s == 0.5
    assert spec.beats.target_mean_s == 1.2
    assert spec.beats.mean_max_s <= 1.5
    assert spec.broll.clip_max_fraction == 0.7
    strip = spec.broll.title_strip
    assert strip is not None and strip.words_max == 5
    assert strip.top_y >= render.SAFE_TOP_PX
    assert spec.broll.text_pops_max_per_60s > 0
    scale = ex.beats.target_mean_s / spec.beats.target_mean_s
    assert spec.broll.unique_assets_min_per_60s == round(ex.broll.unique_assets_min_per_60s * scale)
    assert spec.broll.unique_assets_max_per_60s == round(ex.broll.unique_assets_max_per_60s * scale)
    assert spec.broll.reuse_max == 2


def test_the_split_is_side_by_side_unless_a_style_stacks_it(specs: dict[str, StyleSpec]) -> None:
    for name in ("explainer", "hitech", "footage", "fastfacts"):
        assert render.numbers_for(specs[name]).broll.split_layout == "side", name


def test_only_fastfacts_carries_a_title_strip(specs: dict[str, StyleSpec]) -> None:
    assert [n for n, s in specs.items() if s.broll.title_strip is not None] == ["fastfacts"]


def test_a_bad_split_layout_fails_naming_the_spec(tmp_path: Path) -> None:
    from tests.test_styles import _variant_dir  # pyright: ignore[reportPrivateUsage]

    def sideways(fm: dict[str, Any]) -> None:
        fm["broll"]["motion"]["split"]["layout"] = "diagonal"

    where = _variant_dir(tmp_path, "vishva", sideways)
    with pytest.raises(styles.StyleError, match=r"vishva.*split.*layout"):
        render.numbers_for(styles.load_all(REGISTRY, where)["vishva"])


# --- the resolver (1.1 as amended by 059) ---------------------------------------------------


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("facts", "fastfacts"),
        ("fast facts please", "fastfacts"),
        ("dhruv", "footage"),
        ("documentary, cinematic", "footage"),
        ("vishva gyan", "vishva"),
        ("desi history", "vishva"),
        ("explainer", "explainer"),
    ],
)
def test_the_recipe_aliases_resolve(specs: dict[str, StyleSpec], line: str, name: str) -> None:
    assert styles.resolve(line, specs) == styles.Resolution(name=name, note=line, notice="")


def test_explainer_gives_up_fact_facts_and_dhruv(specs: dict[str, StyleSpec]) -> None:
    aliases = set(specs["explainer"].aliases)
    assert not aliases & {"fact", "facts", "dhruv"}
    assert specs["explainer"].version == "23"  # v11 aliases ... v21 099, v22 104, v23 105


def test_a_multi_word_alias_counts_as_a_phrase(specs: dict[str, StyleSpec]) -> None:
    assert "vishva gyan" in specs["vishva"].aliases
    assert "fast facts" in specs["fastfacts"].aliases
    # "gyan" alone is not an alias; the phrase is what matches it.
    assert styles.resolve("gyan", specs).name == "explainer"


# --- the README's trace table ---------------------------------------------------------------


def test_the_readme_traces_each_recipe_to_its_references() -> None:
    text = README.read_text(encoding="utf-8")
    for name, ids in REFERENCES.items():
        row = next((line for line in text.splitlines() if line.startswith(f"| `{name}`")), "")
        assert row, f"no README row for {name}"
        for ref in ids:
            assert ref in text, (name, ref)
