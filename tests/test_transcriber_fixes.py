"""transcriber.fixes: the research §6 ASR fix pass as pure functions on synthetic word
lists (decision 6.1: word times are final before planning). Tail re-run decision and
splice (1.5 s gap, 3 s window), head smear (a first onset before the detected speech
onset), overlap clamp (0.05 s tolerance, 0.12 s minimum word) and the fix map (exact
whole-token replacement plus the `only_before` lookahead). Boundary values are the
research numbers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shortsmith.contracts import Segment, Transcript, Word
from shortsmith.transcriber import fixes
from shortsmith.transcriber.fixes import FixMap, Lookahead, TailCut

ROOT = Path(__file__).resolve().parents[1]


def _w(text: str, start: float, end: float, segment: int = 0) -> Word:
    return Word(text=text, start=start, end=end, segment=segment)


def _seg(start: float, end: float, *, low: bool = False) -> Segment:
    return Segment(start=start, end=end, avg_logprob=-1.5 if low else -0.2, low_confidence=low)


def _t(words: list[Word], segments: list[Segment], duration_s: float) -> Transcript:
    return Transcript(language="hi", duration_s=duration_s, segments=segments, words=words)


# --- confidence flags ----------------------------------------------------------------


def test_segment_flags_follow_the_whisper_thresholds() -> None:
    assert fixes.low_confidence(-1.0) is False
    assert fixes.low_confidence(-1.01) is True
    assert fixes.no_speech(0.6) is False
    assert fixes.no_speech(0.61) is True


# --- segment assignment --------------------------------------------------------------


def test_words_take_the_segment_their_midpoint_falls_in() -> None:
    segments = [_seg(0.0, 2.0), _seg(2.0, 4.0), _seg(5.0, 6.0)]
    words = [_w("a", 0.1, 0.5), _w("b", 1.8, 2.4), _w("c", 4.2, 4.6), _w("d", 5.1, 5.4)]
    assigned = fixes.assign_segments(words, segments)
    # b's midpoint 2.1 is in the second segment; c sits in the gap, so the last
    # segment starting before it.
    assert [w.segment for w in assigned] == [0, 1, 1, 2]


def test_words_without_segments_all_take_segment_zero() -> None:
    assert [w.segment for w in fixes.assign_segments([_w("a", 0, 1)], [])] == [0]


# --- tail re-run (research §6: 1.5 s gap, 3 s window) --------------------------------


def test_no_tail_rerun_when_the_gap_is_at_most_1_5_s() -> None:
    t = _t([_w("a", 0.5, 1.0), _w("b", 1.2, 8.5)], [_seg(0.5, 8.5)], duration_s=10.0)
    assert fixes.tail_cut(t) is None


def test_tail_rerun_past_1_5_s_cuts_at_floor_of_last_end_minus_3() -> None:
    t = _t([_w("a", 0.5, 1.0), _w("b", 1.2, 8.49)], [_seg(0.5, 8.49)], duration_s=10.0)
    assert fixes.tail_cut(t) == TailCut(start_s=5.0, splice_at_s=8.49)


def test_nkb_numbers_cut_at_46_and_splice_at_the_last_word_end() -> None:
    """NKB: the word list ended at 49.28 s of 59.93 s."""
    t = _t([_w("a", 48.0, 49.28)], [_seg(48.0, 49.28)], duration_s=59.93)
    assert fixes.tail_cut(t) == TailCut(start_s=46.0, splice_at_s=49.28)


def test_a_low_confidence_last_segment_is_re_run_from_its_start() -> None:
    t = _t(
        [_w("a", 0.5, 1.0, 0), _w("b", 6.2, 6.8, 1), _w("c", 7.0, 9.4, 1)],
        [_seg(0.5, 1.0), _seg(6.2, 9.4, low=True)],
        duration_s=10.0,
    )
    assert fixes.tail_cut(t) == TailCut(start_s=6.0, splice_at_s=6.2)


def test_no_words_means_no_tail_rerun() -> None:
    assert fixes.tail_cut(_t([], [], duration_s=10.0)) is None


def test_splice_keeps_main_before_the_splice_and_tail_words_at_or_after_it() -> None:
    main = _t(
        [_w("one", 5.0, 5.5, 0), _w("two", 6.0, 8.0, 0)],
        [_seg(5.0, 8.0)],
        duration_s=12.0,
    )
    # The tail run covers 5.0 s onward, so its times are offset by 5.0.
    tail = _t(
        [_w("two", 1.0, 3.0, 0), _w("three", 3.0, 3.6, 1), _w("four", 3.7, 4.4, 1)],
        [_seg(1.0, 3.0), _seg(3.0, 4.4)],
        duration_s=7.0,
    )
    spliced = fixes.splice_tail(main, tail, TailCut(start_s=5.0, splice_at_s=8.0))
    assert [(w.text, w.start, w.end) for w in spliced.words] == [
        ("one", 5.0, 5.5),
        ("two", 6.0, 8.0),
        ("three", 8.0, 8.6),
        ("four", 8.7, 9.4),
    ]
    assert [(s.start, s.end) for s in spliced.segments] == [(5.0, 8.0), (8.0, 9.4)]
    assert [w.segment for w in spliced.words] == [0, 0, 1, 1]
    assert spliced.duration_s == 12.0
    assert spliced.language == "hi"


def test_splice_for_a_low_confidence_segment_replaces_its_words() -> None:
    main = _t(
        [_w("a", 0.5, 1.0, 0), _w("garbled", 6.2, 6.8, 1), _w("words", 7.0, 9.4, 1)],
        [_seg(0.5, 1.0), _seg(6.2, 9.4, low=True)],
        duration_s=10.0,
    )
    tail = _t(
        [_w("clear", 0.2, 0.8, 0), _w("words", 1.0, 3.4, 0)],
        [_seg(0.2, 3.4)],
        duration_s=4.0,
    )
    spliced = fixes.splice_tail(main, tail, TailCut(start_s=6.0, splice_at_s=6.2))
    assert [w.text for w in spliced.words] == ["a", "clear", "words"]
    assert [(s.start, s.end, s.low_confidence) for s in spliced.segments] == [
        (0.5, 1.0, False),
        (6.2, 9.4, False),
    ]


# --- head smear ------------------------------------------------------------------------


def test_head_smear_moves_words_heard_in_the_opening_silence_to_the_onset() -> None:
    """Dyson: the first word started at 0.00 with 1.72 s of real silence."""
    words = [_w("a", 0.0, 0.9), _w("b", 1.0, 2.0), _w("c", 2.1, 2.5)]
    fixed = fixes.head_smear(words, onset_s=1.72)
    assert [(w.start, w.end) for w in fixed] == [(1.72, 1.72), (1.72, 2.0), (2.1, 2.5)]


def test_head_smear_leaves_a_first_word_within_the_threshold() -> None:
    words = [_w("a", 1.42, 1.9)]
    assert fixes.head_smear(words, onset_s=1.72) == words  # 0.30 s early: allowed
    assert fixes.head_smear(words, onset_s=1.73)[0].start == 1.73  # 0.31 s early


def test_head_smear_without_words_or_onset_is_a_no_op() -> None:
    assert fixes.head_smear([], onset_s=1.0) == []
    words = [_w("a", 0.0, 0.5)]
    assert fixes.head_smear(words, onset_s=0.0) == words


# --- overlap clamp (0.05 s / 0.12 s) ---------------------------------------------------


def test_a_start_more_than_0_05_s_before_the_previous_end_moves_to_that_end() -> None:
    words = [_w("a", 1.0, 2.0), _w("b", 1.94, 2.5), _w("c", 2.46, 3.0)]
    fixed = fixes.clamp_overlaps(words)
    # b starts 0.06 s early: moved; c starts 0.04 s early: within tolerance, kept.
    assert [(w.start, w.end) for w in fixed] == [(1.0, 2.0), (2.0, 2.5), (2.46, 3.0)]


def test_a_word_left_with_no_length_gets_0_12_s() -> None:
    words = [_w("a", 1.0, 2.0), _w("b", 1.5, 1.8), _w("c", 1.72, 1.72)]
    fixed = fixes.clamp_overlaps(words)
    assert [(w.start, w.end) for w in fixed] == [(1.0, 2.0), (2.0, 2.12), (2.12, 2.24)]


def test_head_smear_output_is_repaired_by_the_overlap_clamp() -> None:
    fixed = fixes.clamp_overlaps(
        fixes.head_smear([_w("a", 0.0, 0.9), _w("b", 1.0, 2.0)], onset_s=1.72)
    )
    assert [(w.start, w.end) for w in fixed] == [(1.72, 1.84), (1.84, 2.0)]


# --- fix map ---------------------------------------------------------------------------


def test_fix_map_replaces_whole_tokens_only_and_keeps_times() -> None:
    fixmap = FixMap(map={"डाइसन": "Dyson", "साफ": "साफ़"}, only_before=[])
    words = [_w("डाइसन", 0.1, 0.5), _w("साफ़", 0.6, 0.9), _w("डाइसनका", 1.0, 1.4)]
    fixed = fixes.apply_fix_map(words, fixmap)
    assert [w.text for w in fixed] == ["Dyson", "साफ़", "डाइसनका"]
    assert [(w.start, w.end) for w in fixed] == [(w.start, w.end) for w in words]


def test_only_before_reverts_a_mapping_unless_the_next_word_matches() -> None:
    fixmap = FixMap(
        map={"इन": "In", "फैक्ट": "fact"},
        only_before=[Lookahead(word="In", next="fact", **{"else": "इन"})],
    )
    words = [_w("इन", 0, 0.2), _w("फैक्ट", 0.3, 0.6), _w("इन", 0.7, 0.9), _w("दिनों", 1, 1.3)]
    assert [w.text for w in fixes.apply_fix_map(words, fixmap)] == ["In", "fact", "इन", "दिनों"]
    assert [w.text for w in fixes.apply_fix_map(words[:1], fixmap)] == ["इन"]


def test_the_hindi_fix_map_ships_as_data_and_loads_by_language() -> None:
    hindi = fixes.load_fix_map("hi")
    assert hindi.map["डाइसन"] == "Dyson"
    assert hindi.map["दाथ"] == "दाँत"
    assert len(hindi.map) == 38
    assert hindi.only_before == [Lookahead(word="In", next="fact", **{"else": "इन"})]
    assert fixes.load_fix_map("xx") == FixMap(map={}, only_before=[])


def test_every_shipped_fix_map_is_valid_json_in_the_documented_format() -> None:
    folder = ROOT / "src" / "shortsmith" / "transcriber" / "fixmaps"
    files = sorted(folder.glob("*.json"))
    assert files
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) <= {"_source", "map", "only_before"}, path.name
        FixMap.model_validate(data)


@pytest.mark.parametrize("language", ["hi", "HI", "hindi", "Hindi"])
def test_language_names_and_codes_resolve_to_the_same_map(language: str) -> None:
    assert fixes.load_fix_map(language).map["डाइसन"] == "Dyson"
