"""sound.sweep: the no-sweep rules R1-R4 (decision 7.3), each with a synthesised offender
and its clean twin on the other side of the boundary (12.2). A file may break more than
one rule - a slow attack is also a crescendo - so each test asserts the one rule it is
about, and the clean clicks and the fixture SFX must break none."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from shortsmith import sound
from shortsmith.sound import sweep
from tests.conftest import STEM_RATE, Sounds, ring, stem, swell, tone, write_wav


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
    assert sweep.detect_samples(np.zeros(48000, dtype=np.float32), 48000) == []


# --- 050: R3 and R4 per cue slice on a mixed stem ---------------------------------------

RATE = STEM_RATE
# A cue 15 dB down that barely decays, so its tail is still within 20 dB of the next
# hit's peak when that hit lands (the ticket's third case).
QUIET_RING = ring(amplitude=0.5 * 10 ** (-15 / 20), decay=0.1)


def _slices(starts: list[float], ends: list[float]) -> list[tuple[float, float]]:
    """Each cue from its start to the earlier of its end and the next start (050)."""
    out: list[tuple[float, float]] = []
    for i, (a, b) in enumerate(zip(starts, ends, strict=True)):
        nxt = starts[i + 1] if i + 1 < len(starts) else b
        out.append((a, min(b, nxt)))
    return out


def test_chained_ringing_tails_read_as_one_sound_whole_but_pass_per_cue() -> None:
    starts = [0.0, 1.5, 3.0, 4.5, 6.0]
    x = stem([(s, ring(length_s=2.0)) for s in starts], runtime_s=9.0)
    assert "R3" in _rules(sweep.detect_samples(x, RATE)), "the 023 misfire this fixes"
    assert sweep.detect_stem(x, RATE, _slices(starts, [s + 2.0 for s in starts])) == []


def test_two_overlapping_cues_pass_per_cue() -> None:
    starts, ends = [0.0, 0.8], [2.0, 2.8]
    x = stem([(0.0, ring(amplitude=0.25)), (0.8, ring(amplitude=0.5))], runtime_s=3.5)
    assert "R4" in _rules(sweep.detect_samples(x, RATE)), "the 023 misfire this fixes"
    assert sweep.detect_stem(x, RATE, _slices(starts, ends)) == []


def _attack(hit: sweep.Hit) -> float:
    match = re.match(r"attack of ([\d.]+) s", hit.detail)
    assert match is not None, hit
    return float(match.group(1))


def test_a_quiet_cue_then_a_loud_hit_passes_per_cue() -> None:
    starts, ends = [0.0, 1.0], [2.0, 3.0]
    x = stem([(0.0, QUIET_RING), (1.0, ring())], runtime_s=3.5)
    whole = [h for h in sweep.detect_samples(x, RATE) if h.rule == "R4"]
    assert whole and "1.00 s" in whole[0].detail, "the 023 misfire this fixes"
    assert sweep.detect_stem(x, RATE, _slices(starts, ends)) == []


def test_a_long_tone_among_clean_cues_fails_r3_naming_its_slice() -> None:
    starts, ends = [0.0, 3.0, 9.0], [2.0, 8.1, 11.0]
    x = stem([(0.0, ring()), (3.0, tone(length_s=5.1)), (9.0, ring())], runtime_s=11.5)
    hits = sweep.detect_stem(x, RATE, _slices(starts, ends))
    assert [h.rule for h in hits] == ["R3"]
    assert hits[0].slice == 1
    assert 3.0 <= hits[0].at_s <= 8.1
    assert "5.10 s" in hits[0].detail


def test_a_swell_after_a_quiet_ring_fails_r4_with_its_own_attack() -> None:
    # Whole-stem, the attack is timed across the quiet ring's tail (about 1.2 s); per
    # cue it is the swell's own 200 ms.
    starts, ends = [0.0, 1.0, 3.0], [2.0, 1.4, 5.0]
    x = stem([(0.0, QUIET_RING), (1.0, swell(over_s=0.2)), (3.0, ring())], runtime_s=5.5)
    whole = [h for h in sweep.detect_samples(x, RATE) if h.rule == "R4"]
    assert whole and _attack(whole[0]) == pytest.approx(1.2, abs=0.05), "the 023 misfire"
    hits = [h for h in sweep.detect_stem(x, RATE, _slices(starts, ends)) if h.rule == "R4"]
    assert len(hits) == 1
    assert hits[0].slice == 1
    assert 1.0 <= hits[0].at_s <= 1.4
    assert _attack(hits[0]) == pytest.approx(0.2, abs=0.03)  # the tail under it costs ~20 ms


def test_r1_and_r2_still_read_the_whole_stem_and_carry_no_slice() -> None:
    rng = np.random.default_rng(23)
    noise = 0.3 * rng.uniform(-1.0, 1.0, round(0.5 * RATE))
    x = stem([(0.0, ring()), (2.5, noise)], runtime_s=3.5)
    hits = sweep.detect_stem(x, RATE, [(0.0, 2.0), (2.5, 3.0)])
    assert [h.rule for h in hits] == ["R1"]
    assert hits[0].slice is None
    assert hits[0].at_s == pytest.approx(2.5, abs=0.02)


def test_detect_from_a_file_takes_the_same_slices(tmp_path: Path) -> None:
    x = stem([(0.0, ring()), (3.0, tone(length_s=5.1))], runtime_s=8.5)
    path = write_wav(tmp_path / "sfx.wav", x)
    hits = sweep.detect(path, slices=[(0.0, 2.0), (3.0, 8.1)])
    assert [(h.rule, h.slice) for h in hits] == [("R3", 1)]


def test_the_7_3_numbers() -> None:
    assert (sweep.FLATNESS_MAX, sweep.FLAT_SUSTAIN_S) == (0.03, 0.45)
    assert (sweep.RISE_MIN_S, sweep.RISE_MIN_DB, sweep.RISE_STEP_MAX_DB) == (0.2, 8.0, 3.0)
    assert sweep.RISE_JITTER_DB == 0.5
    assert sweep.CUE_MAX_S == 5.0
    assert (sweep.ATTACK_FLOOR_DB, sweep.ATTACK_MAX_S) == (20.0, 0.15)
