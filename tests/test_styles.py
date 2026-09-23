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


def test_every_spec_carries_the_seven_key_groups_and_the_five_prose_sections(
    specs: dict[str, StyleSpec],
) -> None:
    assert KEY_GROUPS == ("aliases", "beats", "presenter", "broll", "captions", "sound", "finale")
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
    assert ex.presenter.full_reasons == ["cold_open", "emotional_line", "argument_turn"]
    assert (ex.pip.diameter, ex.pip.large_face_diameter, ex.pip.chin_anchor) == (300, 340, 0.82)
    assert ex.pip.large_face_ratio == 0.45  # 3.3
    assert ex.broll.enter_transitions == ["cut", "fade", "whip", "zoom", "spring"]  # 9.4
    assert ex.broll.whip_max_per_3_beats == 1
    assert (ex.broll.unique_assets_min_per_60s, ex.broll.unique_assets_max_per_60s) == (12, 24)
    assert ex.broll.reuse_max == 4  # 4.3
    assert "photo" in ex.broll.kinds and "parallax" not in ex.broll.kinds  # 4.1 / 9.2
    assert ex.broll.tier2_kinds == []
    assert (ex.captions.font_family, ex.captions.size_px, ex.captions.font_weight) == (
        "Poppins", 74, 800,
    )  # fmt: skip
    assert (ex.captions.anchor_y, ex.captions.max_lines, ex.captions.line_height) == (1460, 2, 1.35)
    assert (ex.captions.words_per_page, ex.captions.prefer) == ((2, 4), 3)  # 6.1
    assert (ex.captions.emphasis_max_ratio, ex.captions.gap_break_s) == (0.25, 0.35)
    assert ex.sound.bed_db_under_voice == -11 and ex.sound.duck_max_db == 4  # 7.3
    assert (ex.sound.cues_max_per_60s, ex.sound.cues_per_beat_max) == (20, 1)
    assert (ex.sound.swell_max_db, ex.sound.drop_min_db, ex.sound.ramp_min_s) == (4, -8, 1.5)
    assert (ex.finale.mode, ex.finale.min_s, ex.finale.max_s) == ("off", 0.8, 1.2)
    assert (ex.budget.judge_max_calls, ex.budget.search_max_queries) == (40, 60)  # 5.6
    assert ex.budget.gen_max_per_short == 8  # 5.5
    assert ex.requires_components == [
        "captions", "pip", "hook_cards", "finale", "stamp", "lower_third",
        "list", "split", "wall", "chart", "infographic",
    ]  # fmt: skip
    # 027: the three tier-1 set pieces carry their own counts and base motion (4.1, 5.2).
    assert ex.broll.motion["list"]["items_max"] == 6
    assert ex.broll.motion["split"]["panes"] == 2
    assert (ex.broll.motion["wall"]["cells_min"], ex.broll.motion["wall"]["cells_max"]) == (4, 9)
    # 021: the two infographic kinds are drawn in code from these numbers (9.2, 9.3).
    assert ex.broll.motion["chart"]["marks_max"] == 6
    assert ex.broll.motion["chart"]["grouping"] == "indian"
    assert ex.broll.motion["infographic"]["labels_max"] == 5
    assert ex.palette.accent == "#FFD60A"


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
        c for n in ("educational", "animated", "hitech") for c in specs[n].requires_components
    } - set(REGISTRY)
    assert unbuilt, "a draft should name at least one component still to build"


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
