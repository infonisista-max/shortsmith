"""Caption pager (decision 6.1), minimal form for ticket 003.

Pure code from the final word list and the plan's keywords to CaptionPage objects:
fill 2-4 words per page preferring three, time pages per research S4, one keyword
per page (the highest-priority keyword that falls on the page). The full rules -
never split a marked name run, break on segment punctuation and inter-word gaps
over 0.35 s, remove cut spans, hide from the finale word, the 0.25 emphasis cap and
the layout measurement - come with ticket 010, which also moves `PagerNumbers` to
style front matter.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from shortsmith.contracts import CaptionPage, Word

# Research S4 timing, global (not style numbers).
LEAD_S = 0.04  # page appears this long before its first word
HOLD_S = 0.9  # page stays this long after its last word unless the next page starts
LAST_HOLD_S = 1.2  # the last page holds this long


@dataclass(frozen=True)
class PagerNumbers:
    """The explainer `captions` front-matter numbers the pager reads (1.2, 6.1)."""

    words_per_page: tuple[int, int] = (2, 4)
    prefer: int = 3


def group(count: int, numbers: PagerNumbers) -> list[int]:
    """Page sizes for `count` words: runs of `prefer`, the remainder folded so no page
    is below the minimum (a leftover of one joins the previous page)."""
    lo, hi = numbers.words_per_page
    if count <= 0:
        return []
    if count < lo:
        return [count]
    sizes: list[int] = []
    left = count
    while left > 0:
        take = min(numbers.prefer, left)
        if 0 < left - take < lo:  # the leftover would be too short for a page
            take = left if left <= hi else max(lo, left - lo)
        sizes.append(take)
        left -= take
    return sizes


def page(
    words: Sequence[Word],
    keywords: Sequence[int],
    numbers: PagerNumbers,
    *,
    duration_s: float | None = None,
) -> list[CaptionPage]:
    """Page and time `words`; `keywords` are word indices in priority order."""
    sizes = group(len(words), numbers)
    ranges: list[list[int]] = []
    cursor = 0
    for size in sizes:
        ranges.append(list(range(cursor, cursor + size)))
        cursor += size
    priority = {idx: rank for rank, idx in reversed(list(enumerate(keywords)))}
    pages: list[CaptionPage] = []
    for n, indices in enumerate(ranges):
        first, last = words[indices[0]], words[indices[-1]]
        start = max(0.0, first.start - LEAD_S)
        if n + 1 < len(ranges):
            next_start = max(0.0, words[ranges[n + 1][0]].start - LEAD_S)
            end = min(last.end + HOLD_S, next_start)
        else:
            end = last.end + LAST_HOLD_S
            if duration_s is not None:
                end = min(end, duration_s)
        on_page = [i for i in indices if i in priority]
        keyword = min(on_page, key=lambda i: priority[i]) if on_page else None
        pages.append(
            CaptionPage(
                index=n,
                word_indices=indices,
                texts=[words[i].text for i in indices],
                start=round(start, 3),
                end=round(end, 3),
                keyword=keyword,
            )
        )
    return pages
