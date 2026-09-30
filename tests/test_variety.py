"""Variety numbers in every style, as soft grammar rules the editor repairs (ticket 110b).

run05 had 12 identical yellow stamps, entered on a cut 17 times of 26, and showed
`img_saud_young` on b12/b13/b16 because carry-on beats and set pieces were not counted
toward `reuse_max`. Each style's front matter now carries `clip_share_target`,
`stamps_max_per_60s`, `non_cut_min_share` and `enter_run_max`; `grammar.variety` and
`grammar.reuse` flag a break as a soft violation (094: never a failure), the editor's
fallback repairs it, and a clip share below the target's low end is only logged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shortsmith import grammar, render, styles
from shortsmith.contracts import Beat, CutPlan, Event, Finale, PicturePlan, SetPieceItem, Span
from shortsmith.editor import NEW_PICTURE, REPLACE, beat_options, fallback_for
from shortsmith.planner.prompt import PROMPTS_DIR
from shortsmith.render import registry
from tests.test_grammar import make_plan, picture, replace, transcript_for

KEYS = ("clip_share_target", "stamps_max_per_60s", "non_cut_min_share", "enter_run_max")
PROMPT = PROMPTS_DIR / "picture_v20.md"


def _spec(name: str = "explainer") -> styles.StyleSpec:
    return render.loaded_styles()[name]


def _beat(i: int, *, enter: str = "cut", stamp: bool = False, asset: str | None = None,
          **extra: Any) -> Beat:  # fmt: skip
    return Beat.model_validate({
        "id": f"b{i:02d}", "start": 2.0 * i, "end": 2.0 * i + 2.0, "mode": "pip",
        "kind": "photo", "motion": "ken_burns_in", "subject_kind": "concept",
        "query": f"photo {i}", "enter": enter, "asset_id": asset or f"a{i}",
        **({"event": {"kind": "stamp", "text": f"S{i}"}} if stamp else {}), **extra,
    })  # fmt: skip


def _plan(beats: list[Beat]) -> PicturePlan:
    return PicturePlan(prompt_version="t", cut=CutPlan(keep=[Span(start=0, end=beats[-1].end)]),
                       beats=beats, finale=Finale(beat_id="none", text="?"), title="t",
                       description="d")  # fmt: skip


def _varied(n: int) -> list[str]:
    """Enters that pass every variety rule: fade / zoom / cut / spring, never three alike."""
    return ["cut", *(["fade", "zoom", "cut", "spring"] * n)][:n]


def _repaired(plan: PicturePlan, found: list[grammar.Violation], **kwargs: Any) -> PicturePlan:
    """Each flagged beat takes the editor's fallback option, as `_rescue_picture` does
    when no model answers."""
    for v in found:
        assert v.beat_id is not None and not v.hard
        options = beat_options(plan, v.beat_id, hard=False, **kwargs)
        chosen = next(o for o in options if o.id == fallback_for(v.message, options, hard=False))
        assert chosen.apply is not None, chosen.id
        plan = chosen.apply(plan)
    return plan


# --- the front matter ----------------------------------------------------------------------


def test_every_style_carries_the_variety_numbers() -> None:
    for name, spec in render.loaded_styles().items():
        b = spec.broll
        low, high = b.clip_share_target
        assert 0.0 <= low <= high <= 1.0, name
        assert b.stamps_max_per_60s > 0 and 0.0 <= b.non_cut_min_share <= 1.0, name
        assert b.enter_run_max == 2, name  # never the same enter three beats running


def test_vishva_keeps_the_operators_clip_range_after_the_reference_check() -> None:
    assert _spec("vishva").broll.clip_share_target == (0.20, 0.40)


def test_vishva_is_re_derived_wipe_offered_and_stills_no_longer_the_base() -> None:
    """110c: `wipe` (built, in its `transitions` rows) is one of vishva's enters; its
    prose no longer calls full-screen stills the base, nor leads a number beat to reuse
    the previous asset."""
    spec = _spec("vishva")
    assert spec.version == "18"
    assert "wipe" in spec.broll.enter_transitions
    text = (Path("styles") / "vishva.md").read_text(encoding="utf-8")
    assert "stills are the base" not in text
    assert "beats reuse the previous asset" not in text


def test_clip_max_fraction_is_retired_for_the_target_top() -> None:
    for spec in render.loaded_styles().values():
        assert "clip_max_fraction" not in type(spec.broll).model_fields
        assert spec.broll.clip_share_target[1] > 0


@pytest.mark.parametrize("key", KEYS)
def test_a_style_missing_a_variety_key_is_refused(key: str, tmp_path: Path) -> None:
    text = (Path("styles") / "explainer.md").read_text(encoding="utf-8")
    kept = "\n".join(line for line in text.splitlines() if not line.startswith(f"  {key}:"))
    (tmp_path / "explainer.md").write_text(kept + "\n", encoding="utf-8")
    with pytest.raises(styles.StyleError, match=key):
        styles.load_all(registry(), styles_dir=tmp_path)


@pytest.mark.parametrize("bad", ["[0.5, 0.2]", "[0.1, 1.5]", "[-0.1, 0.3]"])
def test_a_clip_share_target_out_of_order_or_range_is_refused(bad: str, tmp_path: Path) -> None:
    text = (Path("styles") / "explainer.md").read_text(encoding="utf-8")
    lines = [f"  clip_share_target: {bad}" if line.startswith("  clip_share_target:") else line
             for line in text.splitlines()]  # fmt: skip
    (tmp_path / "explainer.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(styles.StyleError, match="clip_share_target"):
        styles.load_all(registry(), styles_dir=tmp_path)


# --- stamps per 60 s -----------------------------------------------------------------------


def test_more_stamps_than_the_cap_is_a_soft_violation_the_editor_drops() -> None:
    spec = _spec()  # 6 a minute: 2 in 20 s
    enters = _varied(10)
    plan = _plan([_beat(i, enter=enters[i], stamp=i % 2 == 0) for i in range(10)])
    found = grammar.variety(plan.beats, runtime=20.0, spec=spec)
    assert [v.beat_id for v in found] == ["b04", "b06", "b08"]
    assert all("stamps_max_per_60s" in v.message and not v.hard for v in found)
    fixed = _repaired(plan, found)
    assert [b.id for b in fixed.beats if b.event.kind == "stamp"] == ["b00", "b02"]
    assert grammar.variety(fixed.beats, runtime=20.0, spec=spec) == []


# --- the non-cut share and the enter runs --------------------------------------------------


def test_too_few_non_cut_enters_is_soft_and_the_editor_varies_them() -> None:
    spec = _spec()  # 0.7 of the beats after the first
    plan = _plan([_beat(i) for i in range(8)])
    found = grammar.variety(plan.beats, runtime=16.0, spec=spec)
    assert found and all(not v.hard and v.beat_id != "b00" for v in found)
    assert any("non_cut_min_share" in v.message for v in found)
    enters = spec.broll.enter_transitions
    fixed = _repaired(plan, found, enters=enters)
    assert all(b.enter in enters for b in fixed.beats)
    assert grammar.variety(fixed.beats, runtime=16.0, spec=spec) == []


def test_the_same_enter_three_times_running_is_soft_and_swapped() -> None:
    spec = _spec("footage")  # non_cut_min_share 0.15: only the run rule speaks
    enters = ["cut", "fade", "fade", "fade", "cut", "zoom"]
    plan = _plan([_beat(i, enter=e) for i, e in enumerate(enters)])
    found = grammar.variety(plan.beats, runtime=12.0, spec=spec)
    assert [(v.beat_id, v.rule) for v in found] == [("b03", "9.4")]
    assert "enter_run_max" in found[0].message
    fixed = _repaired(plan, found, enters=spec.broll.enter_transitions)
    assert fixed.beats[3].enter not in ("fade", "cut")  # never a neighbour's enter
    assert grammar.variety(fixed.beats, runtime=12.0, spec=spec) == []


def test_no_enter_swap_is_offered_unless_the_style_enters_are_passed() -> None:
    plan = _plan([_beat(0), _beat(1)])
    assert not [o for o in beat_options(plan, "b01", hard=False) if o.id.startswith("enter:")]


# --- reuse: set pieces and carry-ons count -------------------------------------------------


def test_carry_ons_and_set_pieces_count_toward_reuse_max() -> None:
    """run05: img_saud_young on b12, the number beat b13 carrying it on, and b16."""
    spec = _spec("vishva")  # reuse_max 2
    beats = [
        _beat(0, enter="cut", asset="saud"),
        _beat(1, enter="fade", asset="saud", subject_kind="number",
              event={"kind": "stamp", "text": "1953"}),
        _beat(2, enter="zoom", asset="other"),
        _beat(3, enter="spring", asset="saud", kind="wall",
              items=[SetPieceItem(asset_id=a) for a in ("other", "saud", "x", "y")]),
    ]
    found = grammar.reuse(beats, spec=spec)
    # the carry-on is flagged, not the wall: a number beat may take a new picture
    assert [(v.beat_id, v.rule, v.hard) for v in found] == [("b01", "4.3", False)]
    assert "reuse_max" in found[0].message
    plan = _plan(beats)
    options = beat_options(plan, "b01", hard=False)
    assert fallback_for(found[0].message, options, hard=False) == NEW_PICTURE
    fixed = _repaired(plan, found)
    assert grammar.reuse(fixed.beats, spec=spec) == []
    assert fixed.beats[3].kind == "wall" and fixed.beats[3].asset_id == "saud"


def test_the_wall_is_flagged_only_when_no_plain_beat_can_give_way() -> None:
    spec = _spec("vishva")
    items = [SetPieceItem(asset_id=a) for a in ("p", "q", "r", "s")]
    beats = [_beat(0, asset="saud"), _beat(1, enter="fade", asset="saud", kind="wall", items=items),
             _beat(2, enter="zoom", asset="saud", kind="wall", items=items)]  # fmt: skip
    found = grammar.reuse(beats, spec=spec)
    assert [v.beat_id for v in found] == ["b02"]
    options = beat_options(_plan(beats), "b02", hard=False)
    assert NEW_PICTURE not in [o.id for o in options]
    assert fallback_for(found[0].message, options, hard=False) == REPLACE


def test_a_number_beat_over_the_cap_takes_a_new_picture() -> None:
    spec = _spec("vishva")
    beats = [
        _beat(0, asset="saud"),
        _beat(1, enter="fade", asset="saud"),
        _beat(2, enter="zoom", asset="saud", subject_kind="number",
              event={"kind": "stamp", "text": "1953"}),
    ]
    plan = _plan(beats)
    found = grammar.reuse(plan.beats, spec=spec)
    assert [v.beat_id for v in found] == ["b02"]
    fixed = _repaired(plan, found)
    assert fixed.beats[2].asset_id is None and fixed.beats[2].kind == "photo"
    assert fixed.beats[2].subject_kind == "concept" and fixed.beats[2].event.text == "1953"
    assert grammar.reuse(fixed.beats, spec=spec) == []


# --- clip share ----------------------------------------------------------------------------


def test_clips_over_the_target_top_are_soft() -> None:
    spec = _spec()  # top 0.35
    plan = make_plan()
    for i in range(3, 13):
        plan = replace(plan, f"b{i:02d}", kind="clip", motion="push_in", subject_kind="concept",
                       asset_id=f"clip{i}", event=Event())  # fmt: skip
    result = picture(plan, spec)
    assert isinstance(result, grammar.Violations)
    lines = [v for v in result.items if "clip_share_target" in v.message]
    assert lines and not any(v.hard for v in lines)


def test_a_plan_under_the_target_low_end_passes_with_a_logged_reason() -> None:
    spec = _spec("vishva")
    plan = make_plan()
    result = grammar.validate_picture(plan, transcript_for(plan), spec, keep_soft=True)
    assert isinstance(result, grammar.PictureCheck)
    assert any("clip_share_target" in w and "below" in w for w in result.warnings)


# --- never a failure -----------------------------------------------------------------------


def test_every_variety_break_is_kept_and_the_plan_passes_with_keep_soft() -> None:
    spec = _spec()
    plan = make_plan()  # every beat enters on a cut and carries a stamp
    strict = picture(plan, spec)
    assert isinstance(strict, grammar.Violations)
    assert all(not v.hard for v in strict.items)
    kept = grammar.validate_picture(plan, transcript_for(plan), spec, keep_soft=True)
    assert isinstance(kept, grammar.PictureCheck)
    assert any("stamps_max_per_60s" in w for w in kept.warnings)
    assert any("non_cut_min_share" in w for w in kept.warnings)


# --- the prompt ----------------------------------------------------------------------------


def test_the_creative_editor_points_at_the_clip_share_target() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "clip_share_target" in text
    assert "clip_max_fraction" not in text



def test_the_styles_readme_says_where_the_creative_editor_rule_lives() -> None:
    """110c: the operator's answer - the prompt section, the style keys and prose, the
    grammar's soft rules and the cross-style worked examples, each named."""
    text = (Path("styles") / "README.md").read_text(encoding="utf-8")
    section = text.split("## Where the creative-editor rule lives", 1)[1]
    for place in ("picture_v20.md:16", "The creative editor", "broll.clip_share_target",
                  "B-roll", "grammar.py:1781", "grammar.variety", "grammar.reuse",
                  "reference/examples.py:109", "reference/variety.py"):  # fmt: skip
        assert place in section, place
    prompt = (PROMPTS_DIR / "picture_v20.md").read_text(encoding="utf-8").splitlines()
    assert prompt[15].startswith("The creative editor")
