"""captions (ticket 010; decisions 6.1, 6.2, 6.3): the deterministic pager and its
layout. Paging fills 2-4 words preferring 3, never splits a planner-marked name or
number run, breaks on segment punctuation and inter-word gaps of 0.35 s; the keyword
cap is 0.25 with one per page; captions are hidden from the finale word; cut spans
are removed and word times moved onto the cut timeline before paging. Every word is a
fixed-advance box at its 1.08-scaled width measured with Pillow on the bundled
Poppins; a page is wrapped before render and never needs more than two lines."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from PIL import ImageFont

from shortsmith import captions, presenter, render, styles
from shortsmith.captions import LayoutError, PagerNumbers
from shortsmith.contracts import (
    Beat,
    CaptionPage,
    CutPlan,
    Finale,
    Hook,
    PicturePlan,
    Segment,
    Span,
    Transcript,
    Word,
    WordRun,
)
from shortsmith.transcriber import FakeTranscriber

SPEC = styles.load_all(render.registry())["explainer"]
STYLE = SPEC.caption_style()
NUMBERS = captions.numbers_for(SPEC)
FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _words(texts: list[str] | int, *, gap: float = 0.1, length: float = 0.2) -> list[Word]:
    if isinstance(texts, int):
        texts = [f"w{i}" for i in range(texts)]
    out: list[Word] = []
    t = 1.0
    for text in texts:
        out.append(Word(text=text, start=round(t, 3), end=round(t + length, 3), segment=0))
        t += length + gap
    return out


def _page(words: list[Word], keywords: list[int] | None = None, **kw: object) -> list[CaptionPage]:
    return captions.page(words, keywords or [], NUMBERS, STYLE, **kw)  # type: ignore[arg-type]


def _sizes(pages: list[CaptionPage]) -> list[int]:
    return [len(p.word_indices) for p in pages]


# --- numbers from the style (6.1) ------------------------------------------------------


def test_numbers_come_from_the_style_front_matter() -> None:
    assert PagerNumbers(
        words_per_page=(2, 4), prefer=3, gap_break_s=0.35, emphasis_max_ratio=0.25
    ) == NUMBERS
    wide = SPEC.model_copy(deep=True)
    wide.captions.words_per_page = (2, 6)
    wide.captions.prefer = 6
    wide.captions.gap_break_s = 0.5
    assert captions.numbers_for(wide).words_per_page == (2, 6)
    assert captions.numbers_for(wide).prefer == 6
    assert captions.numbers_for(wide).gap_break_s == 0.5


# --- filling (6.1) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "sizes"),
    [
        (2, [2]),
        (3, [3]),
        (4, [4]),
        (5, [3, 2]),
        (6, [3, 3]),
        (7, [3, 4]),
        (12, [3, 3, 3, 3]),
        (13, [3, 3, 3, 4]),
        (14, [3, 3, 3, 3, 2]),
    ],
)
def test_fill_two_to_four_words_preferring_three(count: int, sizes: list[int]) -> None:
    pages = _page(_words(count))
    assert _sizes(pages) == sizes
    assert [i for p in pages for i in p.word_indices] == list(range(count))
    assert [p.index for p in pages] == list(range(len(pages)))


def test_one_word_is_its_own_page_and_no_words_no_pages() -> None:
    (only,) = _page(_words(1))
    assert only.word_indices == [0]
    assert _page([]) == []


# --- breaks (6.1) ----------------------------------------------------------------------


def test_a_gap_of_0_35_s_breaks_the_page_and_0_34_s_does_not() -> None:
    """Six words with one pause after the second: filling alone gives [3, 3]."""
    head = _words(2)  # 1.0-1.2, 1.3-1.5
    for gap, sizes in ((0.35, [2, 4]), (0.34, [3, 3])):
        tail_start = head[-1].end + gap
        tail = [
            Word(text=f"x{i}", start=round(tail_start + 0.3 * i, 3),
                 end=round(tail_start + 0.3 * i + 0.2, 3), segment=0)
            for i in range(4)
        ]  # fmt: skip
        assert _sizes(_page(head + tail)) == sizes, gap


def test_segment_punctuation_breaks_the_page_and_is_stripped() -> None:
    words = _words(["so", "it", "began.", "then", "we", "left!"])
    pages = _page(words)
    assert _sizes(pages) == [3, 3]
    assert pages[0].texts == ["so", "it", "began"]
    assert pages[1].texts == ["then", "we", "left"]
    comma = _page(_words(["yes,", "and", "no", "more"]))
    assert [p.texts for p in comma] == [["yes"], ["and", "no", "more"]]


def test_verbatim_text_keeps_inner_punctuation() -> None:
    (page,) = _page(_words(["it's", "3.5", "lakh?"]))
    assert page.texts == ["it's", "3.5", "lakh"]


# --- marked runs (6.1) -----------------------------------------------------------------


def test_a_marked_name_run_is_never_split() -> None:
    words = _words(["we", "met", "Narendra", "Damodardas", "Modi"])
    assert _sizes(_page(words)) == [3, 2]  # unmarked: splits the name
    pages = _page(words, runs=[(2, 4)])
    assert [p.texts for p in pages] == [["we", "met"], ["Narendra", "Damodardas", "Modi"]]


def test_a_marked_run_survives_a_gap_and_punctuation_inside_it() -> None:
    words = _words(["costs", "Rs.", "500", "crore", "now"], gap=0.5)
    pages = _page(words, runs=[(1, 3)])
    assert ["Rs", "500", "crore"] in [p.texts for p in pages]


def test_runs_outside_the_word_list_are_ignored() -> None:
    assert _sizes(_page(_words(6), runs=[(4, 9), (-1, 2)])) == [3, 3]


# --- keywords (6.1) --------------------------------------------------------------------


def test_keyword_cap_is_a_quarter_of_the_words_and_one_per_page() -> None:
    words = _words(8)
    # Cap floor(8 x 0.25) = 2 keeps [0, 1], both on page 0: only the first is boxed.
    pages = _page(words, [0, 1, 2, 5])
    assert _sizes(pages) == [3, 3, 2]
    assert [p.keyword for p in pages] == [0, None, None]
    assert [sum(w.keyword for w in p.words) for p in pages] == [1, 0, 0]


def test_the_first_keyword_in_priority_order_wins_the_page() -> None:
    pages = _page(_words(8), [1, 0])
    assert pages[0].keyword == 1


# --- finale (6.1) ----------------------------------------------------------------------


def test_captions_are_absent_from_the_finale_word_onward() -> None:
    words = _words(9, gap=0.1)  # starts 1.0, 1.3, ... 3.4
    pages = _page(words, hide_from=words[6].start)
    shown = [i for p in pages for i in p.word_indices]
    assert shown == list(range(6))
    assert all(p.end <= words[6].start for p in pages)


def test_page_timing_per_research_s4_on_the_fixture() -> None:
    words = FakeTranscriber().transcribe(Path("unused.mp4")).words
    pages = _page(words, duration_s=6.0, hide_from=5.0)
    # Every burst is its own page: the 0.7 s silence between bursts breaks.
    assert [p.texts for p in pages] == [
        ["hello", "there"], ["this", "is"], ["a", "short"], ["about", "nothing"],
        ["made", "by"],
    ]  # fmt: skip
    assert pages[0].start == pytest.approx(0.2 - 0.04)
    assert pages[0].end == pytest.approx(1.2 - 0.04)  # next page start beats end + 0.9
    assert pages[-1].start == pytest.approx(4.2 - 0.04)
    assert pages[-1].end == pytest.approx(5.0)  # last hold 1.2 s cut at the finale
    unclamped = _page(words)
    assert unclamped[-1].end == pytest.approx(5.5 + 1.2)
    assert _page(words, duration_s=6.0)[-1].end == pytest.approx(6.0)
    for a, b in zip(pages, pages[1:], strict=False):
        assert a.end <= b.start


def test_page_start_never_before_zero() -> None:
    words = [Word(text="go", start=0.0, end=0.2, segment=0),
             Word(text="on", start=0.25, end=0.4, segment=0)]  # fmt: skip
    assert _page(words)[0].start == 0.0


# --- measurement and layout (6.2, 6.3) -------------------------------------------------


def test_widths_are_measured_with_pillow_on_the_bundled_poppins() -> None:
    font = ImageFont.truetype(str(FONTS / "Poppins-ExtraBold.ttf"), STYLE.size_px)
    expected = font.getlength("hello") + STYLE.letter_spacing_px * len("hello")
    assert captions.text_width("hello", STYLE) == pytest.approx(expected)
    assert captions.box_width("hello", keyword=False, style=STYLE) == pytest.approx(
        expected * STYLE.active_scale
    )
    assert captions.box_width("hello", keyword=True, style=STYLE) == pytest.approx(
        expected * STYLE.active_scale + 2 * STYLE.keyword_pad_px
    )


def test_the_font_file_follows_the_style_weight() -> None:
    bold = STYLE.model_copy(update={"font_weight": 700})
    font = ImageFont.truetype(str(FONTS / "Poppins-Bold.ttf"), STYLE.size_px)
    assert captions.text_width("hello", bold) == pytest.approx(
        font.getlength("hello") + STYLE.letter_spacing_px * 5
    )
    with pytest.raises(LayoutError, match="weight 300"):
        captions.text_width("x", STYLE.model_copy(update={"font_weight": 300}))


def test_devanagari_words_are_measured_at_the_same_size() -> None:
    word = "भारत"
    font = ImageFont.truetype(str(FONTS / "Poppins-ExtraBold.ttf"), STYLE.size_px)
    assert captions.text_width(word, STYLE) == pytest.approx(
        font.getlength(word) + STYLE.letter_spacing_px * len(word)
    )
    # Poppins carries Devanagari: the width is the glyphs', not a fallback box's.
    assert captions.text_width(word, STYLE) > 3 * font.getlength("□")
    double = STYLE.model_copy(update={"size_px": 2 * STYLE.size_px, "letter_spacing_px": 0.0})
    single = STYLE.model_copy(update={"letter_spacing_px": 0.0})
    assert captions.text_width(word, double) == pytest.approx(
        2 * captions.text_width(word, single), rel=0.02
    )
    (page,) = _page(_words(["यह", "भारत", "है"]))
    assert page.lines == 1 and len(page.words) == 3


def test_boxes_advance_by_the_fixed_gap_and_the_block_is_centred_on_the_anchor() -> None:
    (page,) = _page(_words(["hello", "there", "this", "one"]), [1])  # cap: 1 of 4 words
    line = page.words
    for left, right in zip(line, line[1:], strict=False):
        assert right.x == pytest.approx(left.x + left.width + STYLE.word_gap_px)
    line_h = STYLE.size_px * STYLE.line_height
    assert page.lines == 1
    assert all(w.y == pytest.approx(STYLE.anchor_y - line_h) for w in line)
    assert all(w.height == pytest.approx(line_h) for w in line)
    left, right = line[0].x, line[-1].x + line[-1].width
    assert left == pytest.approx(1080 - right)
    assert [w.keyword for w in line] == [False, True, False, False]
    assert [(w.start, w.end) for w in line][:2] == [(1.0, 1.2), (1.3, 1.5)]
    assert _page(_words(["hello", "there", "this"]), [1])[0].keyword is None  # cap 0 of 3


def test_a_wide_page_wraps_to_two_lines_above_the_anchor() -> None:
    (page,) = _page(_words(["remarkable", "discoveries", "await"]))
    assert page.lines == 2
    line_h = STYLE.size_px * STYLE.line_height
    tops = sorted({w.y for w in page.words})
    assert tops == pytest.approx([STYLE.anchor_y - 2 * line_h, STYLE.anchor_y - line_h])
    for y in tops:
        row = [w for w in page.words if w.y == y]
        assert row[-1].x + row[-1].width - row[0].x <= STYLE.max_width_px


def test_four_words_never_make_three_lines() -> None:
    long = ["extraordinary", "misunderstanding", "responsibilities", "internationally"]
    pages = _page(_words(long))
    assert all(p.lines <= STYLE.max_lines for p in pages)
    assert [i for p in pages for i in p.word_indices] == [0, 1, 2, 3]
    assert len(pages) >= 2


def test_a_page_needing_three_lines_is_a_pager_bug_and_raises() -> None:
    long = ["incomprehensibilities", "counterrevolutionaries", "electroencephalographically"]
    with pytest.raises(LayoutError, match="three lines"):
        _page(_words(long), runs=[(0, 2)])


# --- the whole step: cut, finale, two-line beats ---------------------------------------


def _transcript(texts: list[str], *, gap: float = 0.1) -> Transcript:
    words = _words(texts, gap=gap)
    return Transcript(
        duration_s=words[-1].end + 1.0,
        segments=[Segment(start=words[0].start, end=words[-1].end, avg_logprob=-0.1)],
        words=words,
    )


def _plan(beats: list[tuple[str, float, float]], *, keep: list[Span],
          drop: Sequence[Span] = (), cold_open: Span | None = None,
          finale: str | None = None, keywords: Sequence[int] = (),
          runs: Sequence[WordRun] = ()) -> PicturePlan:  # fmt: skip
    """A plan on the output timeline; the default cold open is empty at the head."""
    return PicturePlan(
        prompt_version="t",
        cut=CutPlan(keep=keep, drop=list(drop)),
        beats=[Beat(id=i, start=s, end=e, mode="pip", kind="photo") for i, s, e in beats],
        hook=Hook(title="t", cold_open_span=cold_open or Span(start=keep[0].start,
                  end=keep[0].start), original_position="drop", card_asset_ids=[]),  # fmt: skip
        finale=Finale(beat_id=finale or beats[-1][0], text="t"),
        keywords=list(keywords),
        name_runs=list(runs),
        title="t",
        description="t",
    )  # fmt: skip


def test_build_removes_cut_spans_and_moves_times_onto_the_cut_timeline() -> None:
    transcript = _transcript(["a", "b", "c", "d", "e", "f", "g", "h"])  # 1.0, 1.3 ... 3.1
    drop = Span(start=1.55, end=2.15)  # "c" (1.6-1.8) and "d" (1.9-2.1) are cut
    plan = _plan([("b1", 0.0, 2.0), ("b2", 2.0, 3.6), ("fin", 3.6, 3.7)],
                 keep=[Span(start=0.0, end=4.3)], drop=[drop], finale="fin")  # fmt: skip
    out = captions.build(transcript, plan, SPEC)
    shown = [i for p in out.pages for i in p.word_indices]
    assert shown == [0, 1, 4, 5, 6, 7]  # source transcript indices
    assert [t for p in out.pages for t in p.texts] == ["a", "b", "e", "f", "g", "h"]
    spans = presenter.cut_list(plan)
    boxes = [w for p in out.pages for w in p.words]
    e = transcript.words[4]
    assert boxes[2].start == pytest.approx(presenter.output_time(spans, e.start))
    assert boxes[2].start == pytest.approx(e.start - 0.6)


def test_build_follows_the_cold_open_lift() -> None:
    transcript = _transcript(["one", "two", "three", "four", "five", "six"], gap=0.5)
    # Words at 1.0, 1.7, 2.4, 3.1, 3.8, 4.5 (0.2 s each); lift "five six" to the front.
    lift = Span(start=3.75, end=4.75)
    plan = _plan([("b1", 0.0, 1.0), ("b2", 1.0, 4.0), ("b3", 4.0, 4.9)],
                 keep=[Span(start=0.0, end=4.9)], cold_open=lift)  # fmt: skip
    out = captions.build(transcript, plan, SPEC)
    order = [t for p in out.pages for t in p.texts]
    assert order[:2] == ["five", "six"]
    first = out.pages[0].words[0]
    assert first.start == pytest.approx(3.8 - 3.75)


def test_build_hides_the_finale_and_maps_keywords_and_runs_to_the_cut() -> None:
    transcript = _transcript(["we", "met", "Narendra", "Modi", "today", "bye", "now"])
    # Words 1.0 1.3 1.6 1.9 2.2 2.5 2.8; finale from 2.45 hides "bye now".
    plan = _plan([("b1", 0.0, 2.45), ("fin", 2.45, 3.5)], keep=[Span(start=0.0, end=3.5)],
                 finale="fin", keywords=[3], runs=[WordRun(first=2, last=3)])  # fmt: skip
    out = captions.build(transcript, plan, SPEC)
    assert [p.texts for p in out.pages] == [["we", "met"], ["Narendra", "Modi", "today"]]
    assert out.pages[1].keyword == 3
    assert all(p.end <= 2.45 for p in out.pages)


def test_build_reports_the_beats_that_carry_two_line_pages() -> None:
    transcript = _transcript(["remarkable", "discoveries", "await", "us", "here"], gap=0.1)
    # "remarkable discoveries await" is two lines (1.0-1.8), "us here" one (1.9-2.4).
    plan = _plan([("b1", 0.0, 1.5), ("b2", 1.5, 2.0), ("b3", 2.0, 3.0), ("fin", 3.0, 3.4)],
                 keep=[Span(start=0.0, end=3.4)], finale="fin")  # fmt: skip
    out = captions.build(transcript, plan, SPEC)
    assert [p.lines for p in out.pages] == [2, 1]
    # Page 0 shows from 0.96 until page 1 starts at 1.86: beats b1 and b2.
    assert out.beats_with_two_lines == ["b1", "b2"]
