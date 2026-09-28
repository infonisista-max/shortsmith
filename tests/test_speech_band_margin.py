"""Ticket 064: the speech-band margin is 12 dB in every style (7.3 as amended, paired
review 28 Sep 2026, option A). Only the number moves: the margin is measured the same
way and a bed that misses the line enters the 056 repair ladder in the same order."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shortsmith import render, sound, styles
from shortsmith.contracts import BalanceReport
from shortsmith.sound import (
    _BedMix,  # pyright: ignore[reportPrivateUsage]
    _repaired_bed,  # pyright: ignore[reportPrivateUsage]
)

ALL = ("explainer", "educational", "animated", "hitech", "footage", "vishva", "fastfacts")
VERSIONS = {
    "explainer": "13", "educational": "12", "animated": "12", "hitech": "12",
    "footage": "3", "vishva": "3", "fastfacts": "3",
}  # fmt: skip  (067 bumped each once more)


@pytest.fixture(scope="module")
def specs() -> dict[str, styles.StyleSpec]:
    return styles.load_all(render.registry())


def test_every_style_carries_a_12_db_margin_and_a_bumped_version(
    specs: dict[str, styles.StyleSpec],
) -> None:
    assert sorted(specs) == sorted(ALL)
    for name in ALL:
        assert specs[name].sound.speech_band_margin_db == 12, name
        assert specs[name].version == VERSIONS[name], name


def test_a_margin_over_the_line_is_no_problem_and_one_under_is(
    specs: dict[str, styles.StyleSpec],
) -> None:
    for name in ALL:
        nums = specs[name].sound
        assert sound.margin_problem(12.5, nums) is None, name
        assert sound.margin_problem(12.0, nums) is None, name
        problem = sound.margin_problem(11.0, nums)
        assert problem is not None, name
        assert "11.0 dB, under sound.speech_band_margin_db 12 dB" in problem, name


def _report(nums: styles.Sound, margin: float) -> BalanceReport:
    problem = sound.margin_problem(margin, nums)
    return BalanceReport(
        voice_db=-20.0, bed_under_voice_db=-14.0, speech_band_margin_db=margin,
        bed_accept_db=nums.bed_accept_db, speech_band_margin_min_db=nums.speech_band_margin_db,
        duck_max_db=nums.duck_max_db, problems=[] if problem is None else [problem],
    )  # fmt: skip


def _ladder(
    monkeypatch: pytest.MonkeyPatch, nums: styles.Sound, plain: float, dipped: float
) -> tuple[_BedMix, list[str], list[tuple[float, float | None]]]:
    """`_repaired_bed` with the mix stubbed: the plain mix measures `plain`, any dip or
    lowering measures `dipped`. Returns the result, the log and each mix's (dip, under)."""
    calls: list[tuple[float, float | None]] = []

    def fake_mix(stems: Path, **kw: object) -> _BedMix:
        dip, under = kw["dip_db"], kw["under_db"]
        assert isinstance(dip, float) and (under is None or isinstance(under, float))
        calls.append((dip, under))
        margin = plain if (dip, under) == (0.0, None) else dipped
        return _BedMix(None, None, _report(nums, margin), dip_db=dip)

    monkeypatch.setattr(sound, "_mix_bed", fake_mix)
    lines: list[str] = []
    result = _repaired_bed(
        Path("stems"), bed=SimpleNamespace(id="bed_x"), library=None,  # type: ignore[arg-type]
        story=None, nums=nums,  # type: ignore[arg-type]
        voice=Path("voice.wav"), voice_db=-20.0, runtime_s=6.0, cues=0,
        note=lambda ls: lines.extend(ls),
    )  # fmt: skip
    return result, lines, calls


def test_a_bed_clearing_the_band_by_12_5_db_is_kept_with_no_repair(
    monkeypatch: pytest.MonkeyPatch, specs: dict[str, styles.StyleSpec]
) -> None:
    for name in ALL:
        result, lines, calls = _ladder(monkeypatch, specs[name].sound, 12.5, 12.5)
        assert result.repairs == () and result.balance.problems == [], name
        assert lines == [] and calls == [(0.0, None)], name


def test_a_bed_at_11_db_enters_the_056_ladder_dip_first(
    monkeypatch: pytest.MonkeyPatch, specs: dict[str, styles.StyleSpec]
) -> None:
    """Same order as before: the miss logged, then the dip at the shortfall plus a
    decibel (2 dB for 1 dB short); the dip that clears the line ends the ladder."""
    nums = specs["explainer"].sound
    result, lines, calls = _ladder(monkeypatch, nums, 11.0, 12.5)
    assert "misses the 7.3 band" in lines[0] and "under sound.speech_band_margin_db 12" in lines[0]
    assert calls == [(0.0, None), (sound.dip_depths(1.0)[0], None)]
    assert sound.dip_depths(1.0)[0] == 2.0
    assert len(result.repairs) == 1 and "dipped by 2 dB" in result.repairs[0]
    assert "line 12)" in result.repairs[0]


def test_a_bed_no_dip_saves_is_lowered_after_every_dip(
    monkeypatch: pytest.MonkeyPatch, specs: dict[str, styles.StyleSpec]
) -> None:
    nums = specs["explainer"].sound
    result, _, calls = _ladder(monkeypatch, nums, 11.0, 11.0)
    depths = sound.dip_depths(1.0)
    assert [c for c in calls[1:-1]] == [(d, None) for d in depths]
    assert calls[-1][1] is not None  # the lowered bed comes last
    assert "lowered to" in result.repairs[-1]
    assert all("dipped" in r for r in result.repairs[:-1])
