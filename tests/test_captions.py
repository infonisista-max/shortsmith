"""captions (minimal pager, ticket 003): fill 2-4 words per page preferring 3, time
pages per research S4 (start - 0.04 s, end = min(last end + 0.9 s, next start), last
page holds 1.2 s), one keyword slot per page. The full 6.1-6.3 rules (name runs,
gap breaks, layout measurement, emphasis cap) come with ticket 010."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import captions
from shortsmith.captions import PagerNumbers
from shortsmith.contracts import CaptionPage, Word
from shortsmith.transcriber import FakeTranscriber

NUMBERS = PagerNumbers(words_per_page=(2, 4), prefer=3)


def _words(n: int, *, gap: float = 0.1, length: float = 0.2) -> list[Word]:
    out: list[Word] = []
    t = 1.0
    for i in range(n):
        out.append(Word(text=f"w{i}", start=round(t, 3), end=round(t + length, 3), segment=0))
        t += length + gap
    return out


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
    pages = captions.page(_words(count), [], NUMBERS)
    assert [len(p.word_indices) for p in pages] == sizes
    flat = [i for p in pages for i in p.word_indices]
    assert flat == list(range(count))
    assert all(2 <= len(p.word_indices) <= 4 for p in pages)
    assert [p.index for p in pages] == list(range(len(pages)))


def test_one_word_is_its_own_page() -> None:
    """A single spoken word cannot reach the minimum; it still gets a page."""
    pages = captions.page(_words(1), [], NUMBERS)
    assert len(pages) == 1 and pages[0].word_indices == [0]


def test_no_words_no_pages() -> None:
    assert captions.page([], [], NUMBERS) == []


def test_page_timing_per_research_s4() -> None:
    words = FakeTranscriber().transcribe(Path("unused.mp4")).words
    pages = captions.page(words, [], NUMBERS, duration_s=6.0)
    assert len(pages) == 4
    # Page 0: hello there this -> starts 0.04 s before "hello", ends at the next page start
    # because "is" starts (1.36 - 0.04) before "this" ends + 0.9 s.
    assert pages[0].start == pytest.approx(0.2 - 0.04)
    assert pages[0].end == pytest.approx(1.36 - 0.04)
    assert pages[1].start == pytest.approx(1.36 - 0.04)
    assert pages[1].end == pytest.approx(3.2 - 0.04)
    assert pages[2].end == pytest.approx(4.36 - 0.04)
    # Last page holds 1.2 s after its last word, clamped to the clip.
    assert pages[3].start == pytest.approx(4.36 - 0.04)
    assert pages[3].end == pytest.approx(6.0)
    unclamped = captions.page(words, [], NUMBERS)
    assert unclamped[3].end == pytest.approx(5.5 + 1.2)
    for a, b in zip(pages, pages[1:], strict=False):
        assert a.end <= b.start


def test_page_end_uses_hold_when_the_gap_is_long() -> None:
    words = _words(4, gap=2.0)
    pages = captions.page(words, [], NUMBERS)
    assert [len(p.word_indices) for p in pages] == [4]
    assert pages[0].end == pytest.approx(words[-1].end + 1.2)
    two = captions.page(_words(6, gap=2.0), [], NUMBERS)
    assert two[0].end == pytest.approx(_words(6, gap=2.0)[2].end + 0.9)


def test_page_start_never_before_zero() -> None:
    words = [
        Word(text="go", start=0.0, end=0.2, segment=0),
        Word(text="on", start=0.25, end=0.4, segment=0),
    ]
    assert captions.page(words, [], NUMBERS)[0].start == 0.0


def test_one_keyword_per_page_highest_priority_first() -> None:
    words = _words(6)
    # Priority order: word 4 first, then 1, then 0 (0 loses to 1 on page 0).
    pages = captions.page(words, [4, 1, 0], NUMBERS)
    assert [p.keyword for p in pages] == [1, 4]
    assert all(isinstance(p, CaptionPage) for p in pages)
    assert pages[0].texts == ["w0", "w1", "w2"]


def test_pages_ignore_keywords_outside_the_word_list() -> None:
    pages = captions.page(_words(3), [99], NUMBERS)
    assert pages[0].keyword is None
