"""sound.sweep: the no-sweep rules R1-R4 (decision 7.3), each with a synthesised offender
and its clean twin on the other side of the boundary (12.2). A file may break more than
one rule - a slow attack is also a crescendo - so each test asserts the one rule it is
about, and the clean clicks and the fixture SFX must break none."""

from __future__ import annotations

import pytest

from shortsmith import sound
from shortsmith.sound import sweep
from tests.conftest import Sounds


def _rules(hits: list[sweep.Hit]) -> set[str]:
    return {h.rule for h in hits}


@pytest.mark.parametrize(
    ("name", "rule", "offends"),
    [
        ("noise_500ms", "R1", True),
        ("noise_400ms", "R1", False),
        ("crescendo_250ms_10db", "R2", True),
        ("crescendo_150ms_10db", "R2", False),
        ("crescendo_250ms_6db", "R2", False),
        ("tone_5100ms", "R3", True),
        ("tone_4900ms", "R3", False),
        ("attack_200ms", "R4", True),
        ("attack_100ms", "R4", False),
    ],
)
def test_each_rule_on_both_sides_of_its_boundary(
    sounds: Sounds, name: str, rule: str, offends: bool
) -> None:
    hits = sweep.detect(sounds(name))
    assert (rule in _rules(hits)) is offends, hits


def test_noise_breaks_only_the_flatness_rule(sounds: Sounds) -> None:
    assert _rules(sweep.detect(sounds("noise_500ms"))) == {"R1"}


def test_a_hit_names_its_rule_and_when_it_starts(sounds: Sounds) -> None:
    hits = [h for h in sweep.detect(sounds("tone_5100ms")) if h.rule == "R3"]
    assert len(hits) == 1
    assert hits[0].at_s == pytest.approx(0.0, abs=0.02)
    assert "5.1" in hits[0].detail


def test_clean_clicks_break_no_rule(sounds: Sounds) -> None:
    assert sweep.detect(sounds("clicks")) == []


def test_every_fixture_sfx_is_clean(library: sound.Library) -> None:
    for entry in library.sfx():
        assert sweep.detect(library.file(entry)) == [], entry.id


def test_silence_breaks_no_rule() -> None:
    import numpy as np

    assert sweep.detect_samples(np.zeros(48000, dtype=np.float32), 48000) == []


def test_the_7_3_numbers() -> None:
    assert (sweep.FLATNESS_MAX, sweep.FLAT_SUSTAIN_S) == (0.03, 0.45)
    assert (sweep.RISE_MIN_S, sweep.RISE_MIN_DB, sweep.RISE_STEP_MAX_DB) == (0.2, 8.0, 3.0)
    assert sweep.RISE_JITTER_DB == 0.5
    assert sweep.CUE_MAX_S == 5.0
    assert (sweep.ATTACK_FLOOR_DB, sweep.ATTACK_MAX_S) == (20.0, 0.15)
