"""Caption pager and layout (PRD `captions`, ticket 010; decisions 6.1, 6.2, 6.3).

Pure code from the final word list and the plan to `Captions`. `build` removes the
planner's cut spans with the same span list the audio uses (`presenter.cut_list`,
`presenter.words_on_cut`), so word times are on the cut timeline and the cold-open
lift reorders them; it hides every word from the finale beat's start onward, pages
the rest and reports the beats a two-line page shows over (6.3: lower-thirds are
suppressed there). Word and keyword indices on the pages are transcript indices.

`page` is the 6.1 pager on words already on the cut: hard breaks after segment
punctuation (the ASR returns it on the word that closes a sentence or clause) and at
an inter-word gap of `gap_break_s` or more (the ticket's boundary test: 0.35 s breaks),
never inside a planner-marked name or number run; inside each stretch between
breaks, pages fill 2-4 words preferring 3 (the partition closest to `prefer`, the
earlier page nearer on a tie), and a page whose layout would need more than
`max_lines` lines is never chosen. Keywords are capped at `emphasis_max_ratio` of the
words by dropping the lowest priority, and a page boxes only its first keyword in
priority order. Timing is research S4.

Layout (6.2): every word is a fixed-advance box at its `active_scale` width, measured
with Pillow on the bundled Poppins at the style size and weight (Devanagari at the
same size; Pillow here has no complex-script shaping, so conjunct widths are the sum
of their glyphs), plus the keyword padding when boxed; boxes are `word_gap_px` apart,
lines greedy-wrapped at `max_width_px` and centred, the block's bottom on `anchor_y`.
A page no partition can fit in `max_lines` lines is a pager bug: `LayoutError`.
Every number is from the style front matter; the renderer draws the boxes it gets.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import ImageFont

from shortsmith import presenter
from shortsmith.contracts import (
    CaptionPage,
    Captions,
    CaptionStyle,
    PicturePlan,
    Transcript,
    Word,
    WordBox,
)
from shortsmith.styles import StyleSpec

# Research S4 timing, global (not style numbers).
LEAD_S = 0.04  # page appears this long before its first word
HOLD_S = 0.9  # page stays this long after its last word unless the next page starts
LAST_HOLD_S = 1.2  # the last page holds this long

WIDTH = 1080  # the composition width the block is centred in
FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
WEIGHT_FILES = {500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
TRAILING = ".,!?;:…।॥"  # segment punctuation: breaks the page, stripped from the text
EPS = 1e-6
OUT_OF_RANGE = 100  # partition cost per word a page sits outside `words_per_page`


class LayoutError(ValueError):
    """A caption page cannot be laid out within the style's line limit (6.2)."""


@dataclass(frozen=True)
class PagerNumbers:
    """The style's 6.1 `captions` pager numbers."""

    words_per_page: tuple[int, int]
    prefer: int
    gap_break_s: float
    emphasis_max_ratio: float


def numbers_for(spec: StyleSpec) -> PagerNumbers:
    c = spec.captions
    return PagerNumbers(
        words_per_page=c.words_per_page,
        prefer=c.prefer,
        gap_break_s=c.gap_break_s,
        emphasis_max_ratio=c.emphasis_max_ratio,
    )


# --- measurement (6.2) -----------------------------------------------------------------


@cache
def _font(family: str, weight: int, size: int) -> ImageFont.FreeTypeFont:
    suffix = WEIGHT_FILES.get(weight)
    path = FONTS_DIR / f"{family}-{suffix}.ttf"
    if suffix is None or not path.is_file():
        raise LayoutError(
            f"no bundled font for {family} weight {weight} under assets/fonts "
            f"(weights {sorted(WEIGHT_FILES)})"
        )
    return ImageFont.truetype(str(path), size)


def text_width(text: str, style: CaptionStyle) -> float:
    """Resting width of `text` at the style's font, weight and size, letter spacing
    included as the composition applies it (after every character)."""
    font = _font(style.font_family, style.font_weight, style.size_px)
    return font.getlength(text) + style.letter_spacing_px * len(text)


def box_width(text: str, *, keyword: bool, style: CaptionStyle) -> float:
    """The fixed box: the `active_scale` width, plus the keyword padding when boxed."""
    width = text_width(text, style) * style.active_scale
    return width + 2 * style.keyword_pad_px if keyword else width


def display_text(text: str) -> str:
    """Verbatim, trailing punctuation stripped (6.1)."""
    return text.rstrip(TRAILING) or text


def _wrap(widths: Sequence[float], style: CaptionStyle) -> list[list[int]]:
    """Greedy lines of positions no wider than `max_width_px` (a word wider than that
    sits alone on its line)."""
    lines: list[list[int]] = [[]]
    used = 0.0
    for n, width in enumerate(widths):
        extra = width if not lines[-1] else style.word_gap_px + width
        if lines[-1] and used + extra > style.max_width_px:
            lines.append([n])
            used = width
        else:
            lines[-1].append(n)
            used += extra
    return lines


def _count(n: int) -> str:
    return {3: "three", 4: "four", 5: "five"}.get(n, str(n))


# --- paging (6.1) ----------------------------------------------------------------------


def _keywords(keywords: Sequence[int], count: int, ratio: float) -> list[int]:
    valid = [k for k in dict.fromkeys(keywords) if 0 <= k < count]
    return valid[: math.floor(count * ratio + EPS)]


def _joined(runs: Sequence[tuple[int, int]], count: int) -> set[int]:
    """Positions `i` with no page boundary allowed between `i` and `i + 1`."""
    joined: set[int] = set()
    for first, last in runs:
        if 0 <= first <= last < count:
            joined.update(range(first, last))
    return joined


def _breaks_after(words: Sequence[Word], i: int, gap_break_s: float) -> bool:
    here, after = words[i], words[i + 1]
    return here.text.endswith(tuple(TRAILING)) or after.start - here.end >= gap_break_s - EPS


class _Pager:
    def __init__(self, words: Sequence[Word], keywords: list[int], numbers: PagerNumbers,
                 style: CaptionStyle) -> None:  # fmt: skip
        self.words = words
        self.texts = [display_text(w.text) for w in words]
        self.priority = {k: rank for rank, k in enumerate(keywords)}
        self.numbers = numbers
        self.style = style
        self._lines: dict[tuple[int, int], int] = {}

    def keyword(self, a: int, b: int) -> int | None:
        on_page = [i for i in range(a, b) if i in self.priority]
        return min(on_page, key=lambda i: self.priority[i]) if on_page else None

    def widths(self, a: int, b: int) -> list[float]:
        keyword = self.keyword(a, b)
        return [box_width(self.texts[i], keyword=i == keyword, style=self.style)
                for i in range(a, b)]  # fmt: skip

    def lines(self, a: int, b: int) -> int:
        if (a, b) not in self._lines:
            self._lines[(a, b)] = len(_wrap(self.widths(a, b), self.style))
        return self._lines[(a, b)]

    def cost(self, size: int) -> int:
        lo, hi = self.numbers.words_per_page
        if size < lo:
            return OUT_OF_RANGE * (lo - size)
        if size > hi:
            return OUT_OF_RANGE * (size - hi)
        return abs(size - self.numbers.prefer)

    def partition(self, a: int, b: int, cuts: set[int]) -> list[tuple[int, int]]:
        """The page ranges of stretch [a, b): boundaries only at `cuts`, least total
        cost, the first page nearer `prefer` on a tie, no page over `max_lines`."""
        stops = sorted({*cuts, b})
        best: dict[int, tuple[int, list[tuple[int, int]]]] = {b: (0, [])}
        for i in sorted({a, *cuts}, reverse=True):
            choice: tuple[int, list[tuple[int, int]]] | None = None
            for k in sorted((k for k in stops if k > i and k in best),
                            key=lambda k: (self.cost(k - i), k)):  # fmt: skip
                if self.lines(i, k) > self.style.max_lines:
                    continue
                total = self.cost(k - i) + best[k][0]
                if choice is None or total < choice[0]:
                    choice = (total, [(i, k), *best[k][1]])
            if choice is not None:
                best[i] = choice
        if a not in best:
            self._raise(a, b, cuts)
        return best[a][1]

    def _raise(self, a: int, b: int, cuts: set[int]) -> None:
        bounds = sorted({a, *cuts, b})
        for i, k in zip(bounds, bounds[1:], strict=False):
            if self.lines(i, k) > self.style.max_lines:
                text = " ".join(self.texts[i:k])
                raise LayoutError(
                    f"caption words {i}-{k - 1} cannot be split and need "
                    f"{_count(self.lines(i, k))} lines (max {self.style.max_lines}): {text!r}"
                )
        raise LayoutError(f"caption words {a}-{b - 1} have no page layout")  # pragma: no cover

    def boxes(self, a: int, b: int) -> list[WordBox]:
        widths = self.widths(a, b)
        keyword = self.keyword(a, b)
        lines = _wrap(widths, self.style)
        style = self.style
        line_h = style.size_px * style.line_height
        top = style.anchor_y - len(lines) * line_h
        out: list[WordBox] = []
        for n, line in enumerate(lines):
            x = (WIDTH - sum(widths[p] for p in line) - style.word_gap_px * (len(line) - 1)) / 2
            for p in line:
                word = self.words[a + p]
                out.append(WordBox(text=self.texts[a + p], start=word.start, end=word.end, x=x,
                                   y=top + n * line_h, width=widths[p], height=line_h,
                                   keyword=a + p == keyword))  # fmt: skip
                x += widths[p] + style.word_gap_px
        return out


def page(
    words: Sequence[Word],
    keywords: Sequence[int],
    numbers: PagerNumbers,
    style: CaptionStyle,
    *,
    runs: Sequence[tuple[int, int]] = (),
    hide_from: float | None = None,
    duration_s: float | None = None,
) -> list[CaptionPage]:
    """Page, lay out and time `words` (on the cut timeline, in order). `keywords` and
    `runs` (inclusive `(first, last)`) are indices into `words`; words starting at or
    after `hide_from` (the finale beat's start) get no caption."""
    count = len(words)
    shown = sum(1 for w in words if hide_from is None or w.start < hide_from - EPS)
    pager = _Pager(words, _keywords(keywords, count, numbers.emphasis_max_ratio), numbers, style)
    joined = _joined(runs, count)
    ranges: list[tuple[int, int]] = []
    start = 0
    for i in range(shown):
        last = i == shown - 1
        if last or (i not in joined and _breaks_after(words, i, numbers.gap_break_s)):
            cuts = {k for k in range(start + 1, i + 1) if k - 1 not in joined}
            ranges.extend(pager.partition(start, i + 1, cuts))
            start = i + 1
    pages: list[CaptionPage] = []
    for n, (a, b) in enumerate(ranges):
        first, last_word = words[a], words[b - 1]
        begin = max(0.0, first.start - LEAD_S)
        if n + 1 < len(ranges):
            end = min(last_word.end + HOLD_S, max(0.0, words[ranges[n + 1][0]].start - LEAD_S))
        else:
            end = last_word.end + LAST_HOLD_S
            if duration_s is not None:
                end = min(end, duration_s)
        if hide_from is not None:
            end = min(end, hide_from)
        pages.append(
            CaptionPage(
                index=n,
                word_indices=list(range(a, b)),
                texts=pager.texts[a:b],
                start=round(begin, 3),
                end=round(end, 3),
                keyword=pager.keyword(a, b),
                lines=pager.lines(a, b),
                words=pager.boxes(a, b),
            )
        )
    return pages


# --- the whole step --------------------------------------------------------------------


def _runs_on_cut(plan: PicturePlan, source: Sequence[int]) -> list[tuple[int, int]]:
    """Each marked run as the stretches of the cut list that carry it in order."""
    out: list[tuple[int, int]] = []
    for run in plan.name_runs:
        p = 0
        while p < len(source):
            if run.first <= source[p] <= run.last:
                q = p
                while q + 1 < len(source) and source[q + 1] == source[q] + 1 <= run.last:
                    q += 1
                out.append((p, q))
                p = q + 1
            else:
                p += 1
    return out


def build(transcript: Transcript, plan: PicturePlan, spec: StyleSpec) -> Captions:
    """The captions of a validated plan: cut, hidden from the finale, paged, laid out."""
    spans = presenter.cut_list(plan)
    placed = presenter.words_on_cut(spans, transcript.words)
    source = [i for i, _ in placed]
    words = [w for _, w in placed]
    positions: dict[int, list[int]] = {}
    for p, i in enumerate(source):
        positions.setdefault(i, []).append(p)
    keywords = [p for k in plan.keywords for p in positions.get(k, [])]
    finale = next((b for b in plan.beats if b.id == plan.finale.beat_id), None)
    pages = page(
        words,
        keywords,
        numbers_for(spec),
        spec.caption_style(),
        runs=_runs_on_cut(plan, source),
        hide_from=finale.start if finale is not None else None,
        duration_s=presenter.total_duration(spans),
    )
    pages = [
        p.model_copy(update={
            "word_indices": [source[i] for i in p.word_indices],
            "keyword": source[p.keyword] if p.keyword is not None else None,
        })
        for p in pages
    ]  # fmt: skip
    two_lines = [
        b.id
        for b in plan.beats
        if any(p.lines >= 2 and p.start < b.end and b.start < p.end for p in pages)
    ]
    return Captions(pages=pages, beats_with_two_lines=two_lines)
