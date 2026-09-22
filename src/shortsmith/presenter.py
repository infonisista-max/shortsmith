"""The presenter cut list (PRD `presenter`, ticket 005; decisions 3.4, 8.1, 9.1).

`cut_list(plan)` turns the plan's kept and dropped spans plus the cold-open lift into
the ordered list of source spans that make up the output timeline: the cold-open span
first (the only editorial reordering in v1), then the kept spans minus the dropped
ones, minus the cold-open span itself at its original place when the planner said
`original_position: drop`. With `keep` the lifted line stays where it was and plays
twice; the validator (009) is what rejects an accidental repeat.

`output_time` maps a source time onto that timeline; `words_on_cut` applies the same
spans to the word list, so the pager (010) pages exactly the words the audio keeps,
at their times on the cut. Face measurement is ticket 013.

`crop_window` is the 2.1 geometry: the largest centred 9:16 window of the source,
refused when filling 1080x1920 from it would upscale past `MAX_UPSCALE` (ingest
rejects such uploads first; the cut checks again so a job never renders a soft
presenter).
"""

from __future__ import annotations

from collections.abc import Sequence

from shortsmith.contracts import PicturePlan, Span, Word

TARGET_WIDTH, TARGET_HEIGHT = 1080, 1920
MAX_UPSCALE = 1.5  # decision 2.1; the same number as `ingest.Limits.max_upscale`


class UpscaleExceeded(ValueError):
    """The source is too small to fill 9:16 within the 1.5x rule."""


def upscale_factor(width: int, height: int) -> float:
    """Scale needed to fill 1080x1920 from the largest 9:16 centre crop of the source."""
    crop_height = min(height, width * TARGET_HEIGHT / TARGET_WIDTH)
    return TARGET_HEIGHT / crop_height


def _even(n: float) -> int:
    return int(round(n / 2)) * 2


def crop_window(source_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """(width, height, x, y) of the largest centred 9:16 window with even edges, or
    `UpscaleExceeded` when scaling it to 1080x1920 would pass the 1.5x rule."""
    width, height = source_size
    factor = upscale_factor(width, height)
    if factor > MAX_UPSCALE + 1e-9:
        raise UpscaleExceeded(
            f"filling 1080x1920 from {width}x{height} needs a {factor:.2f}x upscale, "
            f"more than the {MAX_UPSCALE:g}x rule allows"
        )
    if width * TARGET_HEIGHT >= height * TARGET_WIDTH:  # wider than 9:16: keep the height
        crop_w, crop_h = min(width, _even(height * TARGET_WIDTH / TARGET_HEIGHT)), height
    else:  # taller than 9:16: keep the width
        crop_w, crop_h = width, min(height, _even(width * TARGET_HEIGHT / TARGET_WIDTH))
    return crop_w, crop_h, (width - crop_w) // 2, (height - crop_h) // 2


def _subtract(spans: Sequence[Span], holes: Sequence[Span]) -> list[Span]:
    out: list[Span] = []
    for span in spans:
        pieces = [span]
        for hole in holes:
            next_pieces: list[Span] = []
            for piece in pieces:
                if hole.end <= piece.start or hole.start >= piece.end:
                    next_pieces.append(piece)
                    continue
                if hole.start > piece.start:
                    next_pieces.append(Span(start=piece.start, end=hole.start))
                if hole.end < piece.end:
                    next_pieces.append(Span(start=hole.end, end=piece.end))
            pieces = next_pieces
        out.extend(p for p in pieces if p.end > p.start)
    return out


def cut_list(plan: PicturePlan) -> list[Span]:
    """Source spans in output order: cold open, then the kept spans with the dropped
    spans (and, under `drop`, the cold open's original place) removed."""
    cold_open = plan.hook.cold_open_span
    holes = list(plan.cut.drop)
    if plan.hook.original_position == "drop":
        holes.append(cold_open)
    kept = sorted(plan.cut.keep, key=lambda s: s.start)
    body = _subtract(kept, holes)
    return [Span(start=cold_open.start, end=cold_open.end), *body]


def total_duration(spans: Sequence[Span]) -> float:
    return sum(s.end - s.start for s in spans)


def source_time(spans: Sequence[Span], output_t: float) -> float:
    """Where output time `output_t` comes from in the recording: the inverse of
    `output_time`. The end of the last span maps to that span's end; a time past the
    runtime is clamped there."""
    if not spans:
        return output_t
    offset = 0.0
    for i, span in enumerate(spans):
        length = span.end - span.start
        if output_t < offset + length or i == len(spans) - 1:
            return span.start + min(max(output_t - offset, 0.0), length)
        offset += length
    return spans[-1].end


def words_on_cut(spans: Sequence[Span], words: Sequence[Word]) -> list[tuple[int, Word]]:
    """The words the cut keeps, in output order, each with its index in `words` and its
    times moved onto the cut timeline (6.1): a word is kept by the span holding its
    midpoint, so a dropped span loses its words and the cold-open lift moves them to
    the front. Inside one span this is `output_time`; a lifted line kept at its
    original place (`keep`) is placed in both spans, as it plays twice."""
    placed: list[tuple[int, Word]] = []
    offset = 0.0
    for span in spans:
        for i, word in enumerate(words):
            mid = (word.start + word.end) / 2
            if span.start <= mid < span.end:
                start = offset + max(word.start, span.start) - span.start
                end = offset + min(word.end, span.end) - span.start
                placed.append(
                    (i, word.model_copy(update={"start": round(start, 3), "end": round(end, 3)}))
                )
        offset += span.end - span.start
    return placed


def output_time(spans: Sequence[Span], source_t: float) -> float:
    """Where `source_t` lands on the cut timeline. A time on a boundary belongs to the
    later span; a time inside no span maps to the end of the last span before it."""
    offset = 0.0
    hit: float | None = None
    for span in spans:
        if span.start <= source_t < span.end:
            hit = offset + (source_t - span.start)
        offset += span.end - span.start
    if hit is not None:
        return hit
    # Not inside any span: the end of the nearest earlier span, else 0.
    offset = 0.0
    best = 0.0
    for span in spans:
        offset += span.end - span.start
        if span.end <= source_t:
            best = offset
    return best
