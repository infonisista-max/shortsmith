"""The plan validator (PRD `grammar`; decisions 2.3, 3.1, 3.2, 3.4 as amended by 055,
4.1, 4.2, 4.3, 6.1, 7.3, 8.2, 9.4). Pure code over PicturePlan / SoundStory,
Transcript and StyleSpec.

Three outcomes per 8.2. Clamps are fixes code makes without changing intent, each
logged as a `Clamp` citing the decision whose number it applied: pauses between kept
words tightened to `cut.max_pause_s` and the head before the first word trimmed to
the snap window (3.4 / 055), beat boundaries snapped to the nearest word end within
`beats.snap_window_s` (3.1), keywords trimmed to `captions.emphasis_max_ratio` (6.1),
planner cues dropped past the 7.3 caps, the mood curve clipped to
`sound.swell_max_db` / `sound.drop_min_db` (7.3), hashtags to five and the title to a
hundred characters (8.2). Rejections come back as a `Violations` list, every line
carrying the beat id (or `plan`) and the decision number, which is what the planner is
re-sent on its one retry. Warnings (no asset reused) ride on the ValidatedPlan for the
contact sheet.

Every count and length comes from the style front matter (`styles.StyleSpec`), so a
style changes the grammar without code (3.2). Per-60 s counts scale with the plan's
runtime: floor for minimums, ceil for maximums.

Timelines (055). The planner writes beat times in recording seconds, the timeline the
transcript is on; word times are recording seconds too. The validator first checks the
cut (`_speech`): the kept spans in the speaker's order, every word kept once and never
cut into - a plan that lifts a line to the front or drops a spoken word is rejected
naming the span. It then derives the cut list (`presenter.cut_list`, tightened by
`presenter.tighten`) and maps every beat boundary onto the output timeline
(`_on_output`), so a validated plan's beats are output seconds and its `cut.keep` is
the tightened list; every later rule reads output seconds and maps a boundary back
through the cut (`presenter.source_time`) before it meets a word. `timeline="output"`
tells the validator the plan it is given is already validated (T8 re-validates
`plan.validated.json`), so nothing is mapped twice.

The opening (3.4 as amended by 055): the first `beats.opening_beats_min` beats are
`presenter.opening_mode` beats over a full-screen image (a `photo` or a `card` with an
asset), the last of them ending by `beats.opening_max_s`; when the job has owner
references the first beat shows one. No hook object, no lifted line, no title card.

Two readings this module fixes where the decisions leave room. Density (3.1, as
amended by 066): what changes on screen, and when. A beat's change times are its
start, every text pop, bubble and sticker at its resolved `at_s` (its word's time on
the cut), its landed event (stamp, ring, lower-third) taken to land mid-beat, and its end;
the largest gap between consecutive times is at most `density_gap_max_s`. So a stamp
alone lets a beat run to twice the gap, a beat with nothing to the gap itself, and a
pop helps only as far as its word splits the still span. Set pieces (list, chart,
split, wall, finale) and beats with overlays change on their own and are not measured
inside.
"""

from __future__ import annotations

import functools
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Literal

from shortsmith import assets, presenter, stickers, styles, vocab
from shortsmith.assets.generate import depicts_of
from shortsmith.contracts import (
    CATEGORIES,
    CUE_KINDS,
    STORY_PARTS,
    TIER2_KINDS,
    Beat,
    Bubble,
    Clamp,
    Cue,
    CutPlan,
    MoodPoint,
    PicturePlan,
    PlanReference,
    SoundStory,
    Span,
    Sticker,
    StrictModel,
    TextPop,
    Transcript,
    ValidatedPlan,
    Violation,
    Word,
)
from shortsmith.styles import StyleSpec

Timeline = Literal["recording", "output"]

EPS = 1e-6
WORD_EDGE_TOL_S = 0.005  # a cut edge this close to a word's edge is on it, not inside it
CONTIGUITY_TOL_S = 0.011  # one frame at 90 fps, the same slack T3 gives the render
HASHTAGS_MAX = 5  # 8.2
TITLE_MAX_CHARS = 100  # 8.2
PRESENTER_KINDS = frozenset({"presenter_full", "presenter_pip"})
FIXED_MOTION_KINDS = frozenset({"finale"})  # motion comes from the spec table
SET_PIECE_KINDS = frozenset({"list", "chart", "split", "wall", "finale"})  # 3.1
DENSITY_EXEMPT_KINDS = SET_PIECE_KINDS
# 055: a full-screen image behind the circle; 058: a moving clip too, when the topic is
# a concept.
OPENING_KINDS = frozenset({"photo", "card", "clip"})
ITEM_KINDS = frozenset({"list", "split", "wall"})  # 027: the set pieces with own content
TITLED_KINDS = frozenset({"list", "split"})  # a header (nkb_04) and a title strip (5.2)
# 021: a chart carries its title strip in the same field, but needs no items.
TITLE_KINDS = TITLED_KINDS | {"chart"}
CHART_KIND, DIAGRAM_KIND = "chart", "infographic"
# 020: the map and the three overlays that animate on it (028).
MAP_KIND = "map"
MAP_OVERLAYS = frozenset({"pin_drop", "route_arrow", "object_path"})
ROUTED_OVERLAYS = frozenset({"route_arrow", "object_path"})
MAX_MAP_LAT = 85.0  # Mercator's edge; a bbox past it has nothing to draw
TIER2_SUBSTITUTES: dict[str, str] = {"parallax": "photo", "vector_illustration": "card"}
# 061: the picture beats a text pop may sit on; 058: the moving `clip` joined them.
TEXT_POP_KINDS = frozenset({"photo", "card", "clip", "presenter_full"})
# 058 (4.1 and 5.1 as amended): the moving footage kind. A clip beat's asset is a stock
# video file, so only another clip beat (or a `number` / `quote` beat carrying it on)
# may name it, and it never names a still beat's asset or appears in a set piece's items.
CLIP_KIND = "clip"
TEXT_POP_WORDS_MAX = 4  # 061 (1): one to four words
# 063: a bubble sits on the same picture beats (its tail points at a person in the
# picture, or at the PIP circle).
BUBBLE_KINDS = TEXT_POP_KINDS
# 062: a sticker pops over the same picture beats (above the PIP circle, or near its
# subject in the picture).
STICKER_KINDS = TEXT_POP_KINDS
# 078: a highlight marks the screenshot the beat shows, so only on a still picture beat.
HIGHLIGHT_KINDS = frozenset({"photo", "card"})


class Violations(StrictModel):
    items: list[Violation]

    def lines(self) -> list[str]:
        return [str(v) for v in self.items]


class PictureCheck(StrictModel):
    picture: PicturePlan
    clamps: list[Clamp] = []
    warnings: list[str] = []


class SoundCheck(StrictModel):
    sound: SoundStory
    clamps: list[Clamp] = []


def validate(
    plan: PicturePlan,
    story: SoundStory,
    transcript: Transcript,
    spec: StyleSpec,
    *,
    brief: str = "",
    must_use: Sequence[str] = (),
    references: Sequence[str] = (),
    timeline: Timeline = "recording",
) -> ValidatedPlan | Violations:
    """Both halves at once; the sound story is checked against the snapped picture
    when the picture passes, against the raw one otherwise so every violation is
    listed."""
    pic = validate_picture(
        plan, transcript, spec, brief=brief, must_use=must_use, references=references,
        timeline=timeline,
    )  # fmt: skip
    picture = pic.picture if isinstance(pic, PictureCheck) else plan
    snd = validate_sound(story, picture, spec)
    items: list[Violation] = []
    if isinstance(pic, Violations):
        items += pic.items
    if isinstance(snd, Violations):
        items += snd.items
    if items:
        return Violations(items=items)
    assert isinstance(pic, PictureCheck) and isinstance(snd, SoundCheck)
    return ValidatedPlan(
        picture=pic.picture,
        sound=snd.sound,
        clamps=pic.clamps + snd.clamps,
        warnings=pic.warnings,
    )


# --- the picture plan ------------------------------------------------------------------


def validate_picture(
    plan: PicturePlan,
    transcript: Transcript,
    spec: StyleSpec,
    *,
    brief: str = "",
    must_use: Sequence[str] = (),
    references: Sequence[str] = (),
    timeline: Timeline = "recording",
) -> PictureCheck | Violations:
    """`references` are the owner's reference ids (the opening shows one first, 055);
    `timeline` says whether the beats are the planner's recording seconds or an
    already validated plan's output seconds (see the module docstring)."""
    if not plan.beats:
        return Violations(items=[Violation(rule="3.1", message="the plan has no beats")])
    found: list[Violation] = []
    clamps: list[Clamp] = []
    warnings: list[str] = []
    words = transcript.words

    found += _speech(plan.cut, words)
    if found:
        return Violations(items=found)  # the cut is not the recording's speech: stop here
    spans, cut, cut_clamps = cut_spans(plan, words, spec)
    clamps += cut_clamps
    runtime = presenter.total_duration(spans)
    if timeline == "recording":
        beats, map_found = _on_output(plan.beats, spans, words)
        if map_found:
            return Violations(items=map_found)
    else:
        beats = list(plan.beats)
    plan = plan.model_copy(update={"beats": beats, "cut": cut})

    found += _tiling(beats, runtime)
    beats, snap_clamps, snap_found = _snap(beats, spans, words, spec.beats.snap_window_s)
    clamps += snap_clamps
    found += snap_found
    found += _lengths(beats, spec)
    found += _presenter(beats, plan, spec)
    found += _opening(beats, spec, references)
    found += _kinds(beats, spec)
    found += _clips(beats, runtime, spec)
    found += _items(beats, spec)
    found += _charts(beats, spec)
    found += _maps(beats, spec)
    found += _overlays(beats)
    pop_found, beats = _text_pops(beats, runtime, spec, words, spans)
    found += pop_found
    bubble_found, beats = _bubbles(beats, runtime, spec, words, spans)
    found += bubble_found
    sticker_found, beats = _stickers(beats, runtime, spec, words, spans)
    found += sticker_found
    highlight_found, beats = _highlights(beats, runtime, spec, words, spans, references)
    found += highlight_found
    found += density(beats, spec)  # 066: after the passes that resolve each `at_s`
    found += _subjects(beats, runtime, brief)
    asset_found, asset_warnings = _assets(beats, runtime, spec)
    found += asset_found
    warnings += asset_warnings
    found += _transitions(beats, runtime, spec)
    found += _must_use(beats, must_use)
    found += _category(plan)
    found += _title_strip(plan, spec)

    if found:
        return Violations(items=found)
    picture, field_clamps = _clamp_fields(plan.model_copy(update={"beats": beats}), words, spec)
    return PictureCheck(picture=picture, clamps=clamps + field_clamps, warnings=warnings)


def _v(rule: str, beat_id: str | None, message: str) -> Violation:
    return Violation(rule=rule, beat_id=beat_id, message=message)


def _len(beat: Beat) -> float:
    return round(beat.end - beat.start, 3)


# --- the cut: the speaker's order, silence only (3.4 as amended by 055) ---------------------


def _span_text(span: Span) -> str:
    return f"{span.start:g}-{span.end:g} s"


def _cut_into(word: Word, cut: CutPlan) -> bool:
    """Whether the cut removes or cuts into `word`: it lies outside every kept span or
    overlaps a dropped one, beyond `WORD_EDGE_TOL_S` at either edge."""
    tol = WORD_EDGE_TOL_S
    kept = any(k.start <= word.start + tol and word.end <= k.end + tol for k in cut.keep)
    dropped = any(d.start < word.end - tol and d.end > word.start + tol for d in cut.drop)
    return not kept or dropped


def _speech(cut: CutPlan, words: Sequence[Word]) -> list[Violation]:
    """3.4 (055): the kept spans play in the speaker's order and every transcript word
    is kept, whole, exactly once; `cut.drop` removes only silence. A plan that lifts a
    line to the front lists its span before an earlier one, and is rejected naming it."""
    found: list[Violation] = []
    for a, b in zip(cut.keep, cut.keep[1:], strict=False):
        if b.start < a.end - EPS:
            found.append(
                _v(
                    "3.4",
                    None,
                    f"cut.keep is out of the speaker's order: {_span_text(b)} is listed after "
                    f"{_span_text(a)}; nothing is lifted or re-ordered, the short opens with "
                    "the first spoken word",
                )
            )
            break
    run: list[Word] = []

    def flush() -> None:
        if not run:
            return
        text = " ".join(w.text for w in run)
        span = Span(start=run[0].start, end=run[-1].end)
        found.append(
            _v(
                "3.4",
                None,
                f"the cut removes or cuts into spoken words {text!r} ({_span_text(span)}); "
                "cut.drop removes only silence, breaths and dead air, and every word stays",
            )
        )
        run.clear()

    for word in words:
        if _cut_into(word, cut):
            run.append(word)
        else:
            flush()
    flush()
    return found


def cut_spans(
    plan: PicturePlan, words: Sequence[Word], spec: StyleSpec
) -> tuple[list[Span], CutPlan, list[Clamp]]:
    """The cut list of `plan` with its pauses tightened (055): the spans, the `cut` the
    validated plan carries (the planner's own when nothing changed, else the tightened
    spans as `keep`), and one clamp naming every trim. Re-running on a tightened cut
    changes nothing."""
    spans, trims = presenter.tighten(
        presenter.cut_list(plan), words,
        max_pause_s=spec.cut.max_pause_s, lead_s=spec.beats.snap_window_s,
    )  # fmt: skip
    if not trims:
        return spans, plan.cut, []
    removed = sum(t.end - t.start for t in trims)
    parts = [
        f"{t.gap_s:g} s of head before the first word cut to {spec.beats.snap_window_s:g} s"
        if t.after is None
        else f"{t.gap_s:g} s pause after {t.after!r} ({t.start:g} s) tightened to "
        f"{spec.cut.max_pause_s:g} s"
        for t in trims
    ]
    clamp = Clamp(
        rule="3.4",
        message=(
            f"cut: {len(trims)} silence{'s' if len(trims) != 1 else ''} removed "
            f"({removed:.3f} s; cut.max_pause_s {spec.cut.max_pause_s:g}): " + "; ".join(parts)
        ),
    )
    return spans, CutPlan(keep=spans, drop=[]), [clamp]


def _on_output(
    beats: Sequence[Beat], spans: Sequence[Span], words: Sequence[Word]
) -> tuple[list[Beat], list[Violation]]:
    """Beat boundaries from recording seconds onto the cut (055). The first beat owns
    the lead before the first word: a start at or before that word maps to 0. A beat
    that lies wholly inside removed audio has no length on the cut and is rejected."""
    out: list[Beat] = []
    found: list[Violation] = []
    first_word = words[0].start if words else None
    for i, b in enumerate(beats):
        start = presenter.output_time(spans, b.start)
        if i == 0 and first_word is not None and b.start <= first_word + EPS:
            start = 0.0
        end = presenter.output_time(spans, b.end)
        if end - start <= EPS:
            found.append(
                _v(
                    "3.1",
                    b.id,
                    f"beat {b.start:g}-{b.end:g} s on the recording lies inside removed audio "
                    "and has no length on the cut",
                )
            )
            continue
        out.append(b.model_copy(update={"start": round(start, 3), "end": round(end, 3)}))
    return out, found


def _tiling(beats: Sequence[Beat], runtime: float) -> list[Violation]:
    """3.1: beats tile the cut runtime with no gaps."""
    found: list[Violation] = []
    if abs(beats[0].start) > EPS:
        found.append(
            _v("3.1", beats[0].id, f"the first beat starts at {beats[0].start:g} s, not 0")
        )
    for a, b in zip(beats, beats[1:], strict=False):
        if abs(a.end - b.start) > EPS:
            kind = "gap" if b.start > a.end else "overlap"
            found.append(
                _v(
                    "3.1",
                    b.id,
                    f"{kind}: {a.id} ends at {a.end:g} s, {b.id} starts at {b.start:g} s",
                )
            )
    if abs(beats[-1].end - runtime) > CONTIGUITY_TOL_S:
        found.append(
            _v(
                "3.1",
                None,
                f"beats end at {beats[-1].end:g} s but the cut runs {runtime:.3f} s",
            )
        )
    return found


def _nearest_end(words: Sequence[Word], t: float) -> Word | None:
    return min(words, key=lambda w: abs(w.end - t)) if words else None


def _inside(words: Sequence[Word], t: float) -> Word | None:
    return next((w for w in words if w.start + EPS < t < w.end - EPS), None)


def _snap(
    beats: Sequence[Beat], spans: Sequence[Span], words: Sequence[Word], window: float
) -> tuple[list[Beat], list[Clamp], list[Violation]]:
    """3.1 / 8.2: every interior boundary within `window` of a word end moves onto it;
    a boundary inside a word that cannot snap is a rejection; a boundary in silence
    stays. The first start and the last end are the runtime's edges."""
    out = [b.model_copy() for b in beats]
    clamps: list[Clamp] = []
    found: list[Violation] = []
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if abs(a.end - b.start) > EPS:
            continue  # the tiling rule reports it; nothing to snap
        t = a.end
        s = presenter.source_time(spans, t)
        nearest = _nearest_end(words, s)
        if nearest is None:
            continue
        delta = nearest.end - s
        if abs(delta) <= EPS:
            continue
        if abs(delta) <= window + EPS:
            snapped = round(t + delta, 3)
            out[i] = a.model_copy(update={"end": snapped})
            out[i + 1] = b.model_copy(update={"start": snapped})
            clamps.append(
                Clamp(
                    rule="3.1",
                    beat_id=b.id,
                    message=(
                        f"boundary {t:g} s snapped {abs(delta):.3f} s to the end of "
                        f"{nearest.text!r} at {snapped:g} s (beats.snap_window_s {window:g})"
                    ),
                )
            )
            continue
        word = _inside(words, s)
        if word is not None:
            found.append(
                _v(
                    "3.1",
                    b.id,
                    f"boundary {t:g} s is mid-word: inside {word.text!r} "
                    f"({word.start:g}-{word.end:g} s) and {abs(delta):.3f} s from the nearest "
                    f"word end, over beats.snap_window_s {window:g} s",
                )
            )
    return out, clamps, found


def _lengths(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """3.1: min/max per beat after snapping, set pieces to `set_piece_max_s`, the plan
    mean inside `mean_min_s`-`mean_max_s`."""
    nums = spec.beats
    found: list[Violation] = []
    lengths = [_len(b) for b in beats]
    for b, length in zip(beats, lengths, strict=True):
        if length < nums.min_s - EPS:
            found.append(
                _v("3.1", b.id, f"beat is {length:g} s, under beats.min_s {nums.min_s:g} s")
            )
            continue
        set_piece = b.kind in SET_PIECE_KINDS
        cap = nums.set_piece_max_s if set_piece else nums.max_s
        name = "beats.set_piece_max_s" if set_piece else "beats.max_s"
        if length > cap + EPS:
            found.append(_v("3.1", b.id, f"beat is {length:g} s, over {name} {cap:g} s"))
    mean = round(sum(lengths) / len(lengths), 3)
    if mean < nums.mean_min_s - EPS or mean > nums.mean_max_s + EPS:
        found.append(
            _v(
                "3.1",
                None,
                f"plan mean is {mean:g} s, outside beats.mean_min_s-beats.mean_max_s "
                f"{nums.mean_min_s:g}-{nums.mean_max_s:g} s",
            )
        )
    return found


def pops_in(beat: Beat) -> bool:
    """061 / 063 / 062: the beat carries something that pops in over the picture - a
    text pop, a bubble or a sticker: a change for 3.1, something an `event` cue may hit
    and the `pop` trigger of the whoosh allowance."""
    return bool(beat.text_pops) or bool(beat.bubbles) or bool(beat.stickers)


def change_times(beat: Beat) -> list[float]:
    """066 (3.1): when something changes on screen in `beat`, sorted: its start, every
    text pop, bubble and sticker at its resolved `at_s` (061 / 063 / 062), a highlight's
    sweep at its first word (078), its landed
    event (stamp, ring, lower-third) at mid-beat, and its end. A counter rides an
    overlay, whose beat `density` does not measure."""
    times = [beat.start, beat.end]
    if beat.event.kind != "none":
        times.append(round((beat.start + beat.end) / 2, 3))
    # 078: a highlight's marker starts sweeping at its first word.
    lit = [beat.highlight] if beat.highlight is not None else []
    for item in (*beat.text_pops, *beat.bubbles, *beat.stickers, *lit):
        if item.at_s is not None:
            times.append(min(max(item.at_s, beat.start), beat.end))
    return sorted(times)


def density(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """3.1: the largest gap between consecutive `change_times` of a beat is at most
    `density_gap_max_s`; see the module docstring for the reading. Runs after the pop,
    bubble and sticker passes, whose resolved `at_s` it reads."""
    gap_max = spec.beats.density_gap_max_s
    found: list[Violation] = []
    for b in beats:
        if b.kind in DENSITY_EXEMPT_KINDS or b.overlays:
            continue
        times = change_times(b)
        lo, hi = max(pairwise(times), key=lambda pair: pair[1] - pair[0])
        gap = round(hi - lo, 3)
        if gap > gap_max + EPS:
            found.append(
                _v("3.1", b.id, f"nothing changes on screen from {lo:.2f} s to {hi:.2f} s "
                                f"({round(gap, 2):g} s), over beats.density_gap_max_s "
                                f"{gap_max:g} s; add a pop on a word in that span or split "
                                "the beat")  # fmt: skip
            )
    return found


def _presenter(beats: Sequence[Beat], plan: PicturePlan, spec: StyleSpec) -> list[Violation]:
    """3.2: modes, reason tags, never-consecutive `full`, the full fraction, pip and
    off run caps, and the finale's mode."""
    pres = spec.presenter
    found: list[Violation] = []
    total = sum(_len(b) for b in beats)
    full_s = sum(_len(b) for b in beats if b.mode == "full")
    if total > 0 and full_s / total > pres.full_max_fraction + EPS:
        found.append(
            _v(
                "3.2",
                None,
                f"full beats are {full_s / total:.3f} of the runtime, over "
                f"presenter.full_max_fraction {pres.full_max_fraction:g}",
            )
        )
    run_mode, run_len = "", 0
    for i, b in enumerate(beats):
        if b.mode not in pres.modes:
            found.append(
                _v("3.2", b.id, f"mode {b.mode!r} is not in presenter.modes {pres.modes}")
            )
        if b.mode == "full":
            if b.reason is None:
                found.append(
                    _v(
                        "3.2",
                        b.id,
                        "full beat without a reason tag from presenter.full_reasons "
                        f"{pres.full_reasons}",
                    )
                )
            elif b.reason not in pres.full_reasons:
                found.append(
                    _v(
                        "3.2",
                        b.id,
                        f"reason {b.reason!r} is not in presenter.full_reasons "
                        f"{pres.full_reasons}",
                    )
                )
            if pres.full_never_consecutive and i > 0 and beats[i - 1].mode == "full":
                found.append(
                    _v(
                        "3.2",
                        b.id,
                        f"consecutive full beats ({beats[i - 1].id} then {b.id}); "
                        "presenter.full_never_consecutive",
                    )
                )
        if b.mode == run_mode:
            run_len += 1
        else:
            run_mode, run_len = b.mode, 1
        cap = {"pip": pres.pip_max_run, "off": pres.off_max_run}.get(b.mode)
        if cap is not None and run_len == cap + 1:
            found.append(
                _v(
                    "3.2",
                    b.id,
                    f"{run_len} consecutive {b.mode} beats, over presenter.{b.mode}_max_run {cap}",
                )
            )
    finale = next((b for b in beats if b.id == plan.finale.beat_id), None)
    if finale is None:
        found.append(_v("3.2", None, f"finale beat {plan.finale.beat_id!r} is not in the plan"))
    else:
        if finale is not beats[-1]:
            found.append(_v("3.2", finale.id, "the finale is not the last beat"))
        if finale.mode != pres.finale_mode:
            found.append(
                _v(
                    "3.2",
                    finale.id,
                    f"finale beat is {finale.mode!r}; presenter.finale_mode is "
                    f"{pres.finale_mode!r}",
                )
            )
    return found


def _opening(beats: Sequence[Beat], spec: StyleSpec, references: Sequence[str]) -> list[Violation]:
    """3.4 as amended by 055: the first `beats.opening_beats_min` beats are
    `presenter.opening_mode` beats over a full-screen image (a `photo` or `card` with
    an asset) of the main subject, the last of them ending by `beats.opening_max_s`;
    with owner references, the first beat shows one of them."""
    nums = spec.beats
    n = min(nums.opening_beats_min, len(beats))
    mode = spec.presenter.opening_mode
    found: list[Violation] = []
    for b in beats[:n]:
        image = b.kind in OPENING_KINDS and bool(b.asset_id)
        if b.mode != mode or not image:
            what = f"{b.mode}/{b.kind}" + ("" if b.asset_id else " with no asset")
            found.append(
                _v(
                    "3.4",
                    b.id,
                    f"opening beat is {what}; the first {nums.opening_beats_min} beats are "
                    f"{mode} over a full-screen image ({' or '.join(sorted(OPENING_KINDS))}) "
                    "of the main subject, the speaker's own first words, no hook title or cards",
                )
            )
    if n:
        last = beats[n - 1]
        if last.end > nums.opening_max_s + EPS:
            found.append(
                _v(
                    "3.4",
                    last.id,
                    f"the opening's {n} beats run to {last.end:g} s, past beats.opening_max_s "
                    f"{nums.opening_max_s:g} s; the opening is quick beats over the first "
                    "sentence",
                )
            )
        first = beats[0]
        if references and first.asset_id not in references:
            found.append(
                _v(
                    "3.4",
                    first.id,
                    f"the first beat shows {first.asset_id!r}, not one of the owner's references "
                    f"({', '.join(references)}); the opening shows the owner's image first",
                )
            )
    return found


def _kinds(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """4.1: kinds inside the style list, tier-2 named with its substitute, exactly one
    motion on every non-presenter beat."""
    found: list[Violation] = []
    allowed = spec.broll.kinds
    for b in beats:
        if b.kind not in allowed:
            if b.kind in TIER2_KINDS or b.kind in spec.broll.tier2_kinds:
                sub = TIER2_SUBSTITUTES.get(b.kind, "photo")
                found.append(
                    _v(
                        "4.1",
                        b.id,
                        f"{b.kind!r} is a tier-2 kind this style does not enable; "
                        f"the nearest tier-1 substitute is {sub!r}",
                    )
                )
            else:
                found.append(_v("4.1", b.id, f"kind {b.kind!r} is not in broll.kinds {allowed}"))
        if b.kind in PRESENTER_KINDS or b.kind in FIXED_MOTION_KINDS:
            continue
        if b.motion is None:
            found.append(
                _v(
                    "4.1",
                    b.id,
                    f"non-presenter beat ({b.kind}) has no motion; every non-presenter beat "
                    "has exactly one",
                )
            )
    return found


def clip_share(beats: Sequence[Beat]) -> float:
    """058 (6): the seconds of the plan its `clip` beats cover."""
    return round(sum(_len(b) for b in beats if b.kind == CLIP_KIND), 3)


def _clips(beats: Sequence[Beat], runtime: float, spec: StyleSpec) -> list[Violation]:
    """058 (4.1 and 5.1 as amended): a `clip` beat shows a concept, never a named entity
    (2: a stock stranger is never King Saud; those beats keep the still ladder); clip
    beats cover at most `broll.clip_max_fraction` of the runtime (6); and a clip's asset
    is moving footage (7): another clip beat or a carry-on `number` / `quote` beat may
    name it, a still beat or a set-piece item (stills only) may not, and a clip beat
    never names a still beat's asset."""
    found: list[Violation] = []
    clip_ids = {b.asset_id for b in beats if b.kind == CLIP_KIND and b.asset_id}
    still_ids = {
        b.asset_id
        for b in beats
        if b.kind != CLIP_KIND and b.asset_id and b.subject_kind not in assets.REUSING_KINDS
    }
    for b in beats:
        if b.kind == CLIP_KIND:
            if depicts_of(b) == "named_entity":
                found.append(
                    _v("4.1", b.id, "a clip never shows a named entity (a person, place, "
                                    "product or event keeps the still ladder); this clip "
                                    f"beat's subject is {b.subject_kind!r} depicting a named "
                                    "entity (058)")  # fmt: skip
                )
            if b.asset_id in still_ids:
                found.append(
                    _v("4.1", b.id, f"clip beat names {b.asset_id!r}, a still beat's asset; a "
                                    "clip's asset is moving footage of its own or another clip "
                                    "beat's (058)")  # fmt: skip
                )
        elif b.asset_id in clip_ids and b.subject_kind not in assets.REUSING_KINDS:
            found.append(
                _v("4.1", b.id, f"{b.kind} beat names {b.asset_id!r}, a clip beat's asset; only "
                                "a clip beat, or a number or quote beat carrying the clip on, "
                                "may show it (058)")  # fmt: skip
            )
        for i, item in enumerate(b.items):
            if item.asset_id in clip_ids:
                found.append(
                    _v("4.1", b.id, f"item {i} names {item.asset_id!r}, a clip beat's asset; a "
                                    "set piece shows stills (058)")  # fmt: skip
                )
    share = clip_share(beats)
    cap = spec.broll.clip_max_fraction * runtime
    if share > cap + EPS:
        fraction = share / runtime if runtime else 0.0
        found.append(
            _v("4.1", None, f"clip beats cover {share:g} s of {runtime:g} s ({fraction:.2f}); "
                            f"broll.clip_max_fraction {spec.broll.clip_max_fraction:g} allows "
                            f"{cap:.1f} s (058)")  # fmt: skip
        )
    return found


def _item_count(spec: StyleSpec, kind: str) -> tuple[int, int, str]:
    """The style's item range for a set-piece kind and the front-matter key it came
    from (027): `list` 1..items_max, `split` exactly `panes`, `wall` cells_min..max."""
    row = spec.broll.motion.get(kind, {})
    if kind == "list":
        top = int(row.get("items_max", 0))
        return 1, top, "broll.motion.list.items_max"
    if kind == "split":
        panes = int(row.get("panes", 0))
        return panes, panes, "broll.motion.split.panes"
    return (
        int(row.get("cells_min", 0)),
        int(row.get("cells_max", 0)),
        "broll.motion.wall.cells_min-cells_max",
    )


def _items(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """4.1 / 5.2 (ticket 027): a set piece's own content. `items` and `set_piece_title`
    belong to `list`, `split` and `wall` only; each kind's count comes from its
    `broll.motion` row; a list row may be text only but a pane and a cell always name
    an asset; and an item's asset id is one the plan already sources (4.3), the way the
    hook's cards are."""
    found: list[Violation] = []
    planned = {b.asset_id for b in beats if b.asset_id}
    for b in beats:
        if b.kind not in ITEM_KINDS:
            if b.items:
                found.append(
                    _v("4.1", b.id, f"kind {b.kind!r} carries items; only {sorted(ITEM_KINDS)} do")
                )
            if b.set_piece_title and b.kind not in TITLE_KINDS:
                found.append(
                    _v("4.1", b.id, f"kind {b.kind!r} carries a set_piece_title; only a "
                                    "list, a split or a chart has one")  # fmt: skip
                )
            continue
        low, high, key = _item_count(spec, b.kind)
        if not low <= len(b.items) <= high:
            found.append(
                _v("4.1", b.id, f"{b.kind} has {len(b.items)} items; {key} allows {low}-{high}")
            )
        if b.kind in TITLED_KINDS and not b.set_piece_title.strip():
            found.append(
                _v("4.1", b.id, f"a {b.kind} needs a set_piece_title (its header or title strip)")
            )
        for i, item in enumerate(b.items):
            if item.asset_id is None:
                if b.kind != "list":
                    found.append(
                        _v("5.2", b.id, f"item {i} of this {b.kind} names no asset; only a list "
                                        "row may be text only")  # fmt: skip
                    )
            elif item.asset_id not in planned:
                found.append(
                    _v("4.3", b.id, f"item {i} asset id {item.asset_id!r} is not a plan asset")
                )
            if b.kind != "wall" and not item.text.strip():
                found.append(_v("4.1", b.id, f"item {i} of this {b.kind} has no text"))
    return found


def _motion_count(spec: StyleSpec, kind: str, key: str) -> int:
    return int(spec.broll.motion.get(kind, {}).get(key, 0))


def _charts(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """9.2 / 9.3 (ticket 021): the two infographic kinds carry their own data.
    `chart_form`, `series` and `value_unit` belong to a `chart` beat and `labels` to an
    `infographic` beat; the counts come from `broll.motion.chart.marks_max` and
    `broll.motion.infographic.labels_max`; every value is labelled and non-negative
    (the chart is drawn from the real numbers, so a chart that cannot be drawn is a
    rejection, not a clamp)."""
    found: list[Violation] = []
    marks_max = _motion_count(spec, CHART_KIND, "marks_max")
    labels_max = _motion_count(spec, DIAGRAM_KIND, "labels_max")
    for b in beats:
        if b.kind != CHART_KIND:
            if b.series or b.chart_form is not None or b.value_unit:
                found.append(
                    _v("9.2", b.id, f"kind {b.kind!r} carries chart data (chart_form, series "
                                    "or value_unit); only a chart does")  # fmt: skip
                )
        else:
            found += _chart_beat(b, marks_max)
        if b.kind != DIAGRAM_KIND:
            if b.labels:
                found.append(
                    _v("9.3", b.id, f"kind {b.kind!r} carries labels; only an infographic "
                                    "(a labelled diagram) does")  # fmt: skip
                )
            continue
        if not 1 <= len(b.labels) <= labels_max:
            found.append(
                _v("9.3", b.id, f"this infographic has {len(b.labels)} labels; broll.motion."
                                f"infographic.labels_max allows 1-{labels_max}")  # fmt: skip
            )
        for i, label in enumerate(b.labels):
            if not label.text.strip():
                found.append(_v("9.3", b.id, f"label {i} has no text"))
    return found


def _chart_beat(b: Beat, marks_max: int) -> list[Violation]:
    """One `chart` beat's form and series (9.2)."""
    found: list[Violation] = []
    if b.chart_form is None:
        found.append(
            _v("9.2", b.id, "a chart beat needs a chart_form (bar | line | comparison)")
        )
    if b.chart_form == "comparison":
        low, high, key = 2, 2, "a comparison draws exactly two values"
    else:
        low, high, key = 2, marks_max, f"broll.motion.chart.marks_max allows 2-{marks_max}"
    if not low <= len(b.series) <= high:
        found.append(_v("9.2", b.id, f"this chart has {len(b.series)} series values; {key}"))
    for i, point in enumerate(b.series):
        if not point.label.strip():
            found.append(_v("9.2", b.id, f"series value {i} ({point.value:g}) has no label"))
        if point.value < 0:
            found.append(
                _v("9.2", b.id, f"series value {point.label!r} is {point.value:g}; chart "
                                "values are non-negative in v1")  # fmt: skip
            )
    if b.series and max(p.value for p in b.series) <= 0:
        found.append(_v("9.2", b.id, "every series value is zero: there is no scale to draw"))
    return found


def _maps(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """9.3 (ticket 020): a `map` beat carries its recipe - a region name or a bbox of
    west, south, east, north on the earth, 1 to `broll.motion.map.markers_max` named
    markers, and a route of two or more named places when it has one. The names are
    geocoded at render time from the bundled gazetteer; the plan's own coordinates are
    never read. Only a map carries the recipe."""
    found: list[Violation] = []
    markers_max = _motion_count(spec, MAP_KIND, "markers_max")
    for b in beats:
        if b.kind != MAP_KIND:
            if b.map is not None:
                found.append(
                    _v("9.3", b.id, f"kind {b.kind!r} carries a map recipe; only a map does")
                )
            continue
        if b.map is None:
            found.append(
                _v("9.3", b.id, "a map beat needs `map` (a region name or a bbox, and markers)")
            )
            continue
        recipe = b.map
        if not recipe.region.strip() and recipe.bbox is None:
            found.append(_v("9.3", b.id, "a map needs a region name or a bbox"))
        if recipe.bbox is not None:
            west, south, east, north = recipe.bbox
            lon_ok = -180.0 <= west < east <= 180.0
            lat_ok = -MAX_MAP_LAT <= south < north <= MAX_MAP_LAT
            if not (lon_ok and lat_ok):
                found.append(
                    _v("9.3", b.id, f"bbox {list(recipe.bbox)} is not west < east within "
                                    f"+-180 and south < north within +-{MAX_MAP_LAT:g}")
                )
        if not 1 <= len(recipe.markers) <= markers_max:
            found.append(
                _v("9.3", b.id, f"this map has {len(recipe.markers)} markers; broll.motion."
                                f"map.markers_max allows 1-{markers_max}")  # fmt: skip
            )
        for i, marker in enumerate(recipe.markers):
            if not marker.name.strip():
                found.append(_v("9.3", b.id, f"marker {i} has no name"))
        if recipe.route and len(recipe.route) < 2:
            found.append(_v("9.3", b.id, "a route is two or more named places, in order"))
        for i, name in enumerate(recipe.route):
            if not name.strip():
                found.append(_v("9.3", b.id, f"route point {i} has no name"))
    return found


def _overlays(beats: Sequence[Beat]) -> list[Violation]:
    """Ticket 029: the two overlays the renderer draws. `label_flyin` flies an
    infographic's labels in (9.3), so it rides on nothing else. A `counter` overlay and
    the `counter` numbers come together (9.2) and must count somewhere; the counter is
    the beat's one landed event (3.1), so the beat carries no stamp or lower-third; and
    it counts as a `number` beat over the previous asset (4.2). Ticket 020: the three
    map overlays ride on a `map`, and the two that follow the route need one; the
    moving object needs its sprite named."""
    found: list[Violation] = []
    for b in beats:
        if "label_flyin" in b.overlays and b.kind != DIAGRAM_KIND:
            found.append(
                _v("9.3", b.id, f"label_flyin rides on an infographic's labels; this beat is "
                                f"a {b.kind!r}")  # fmt: skip
            )
        for overlay in sorted(MAP_OVERLAYS & set(b.overlays)):
            if b.kind != MAP_KIND:
                found.append(
                    _v("9.3", b.id, f"{overlay} rides on a map; this beat is a {b.kind!r}")
                )
                continue
            routed = b.map is not None and len(b.map.route) >= 2
            if overlay in ROUTED_OVERLAYS and not routed:
                found.append(_v("9.3", b.id, f"{overlay} follows the map's route; there is none"))
            if overlay == "object_path" and (b.map is None or b.map.object is None):
                found.append(
                    _v("9.3", b.id, "object_path moves the map's `object` (plane | ship | arrow); "
                                    "none is named")  # fmt: skip
                )
        if ("counter" in b.overlays) != (b.counter is not None):
            found.append(
                _v("9.2", b.id, "a counter overlay needs `counter` (start, target, unit, "
                                "decimals), and `counter` needs the overlay")  # fmt: skip
            )
        if b.counter is None:
            continue
        if b.counter.start == b.counter.target:
            found.append(
                _v("9.2", b.id, f"the counter starts at its target ({b.counter.target:g}); "
                                "there is nothing to count")  # fmt: skip
            )
        if b.event.kind != "none":
            found.append(
                _v("3.1", b.id, "the counter is this beat's landed event; it cannot also "
                                f"carry a {b.event.kind}")  # fmt: skip
            )
        if b.subject_kind != "number":
            found.append(
                _v("4.2", b.id, f"a counter beat is a number beat, not {b.subject_kind!r}")
            )
    return found


def text_pop_cap(spec: StyleSpec, *, runtime: float) -> int:
    """061: `broll.text_pops_max_per_60s` scaled to the runtime, rounded up like the
    other per-60 s maxima (4.3), so a six-second fixture allows one pop under a style
    that allows ten a minute; 0 stays 0."""
    return math.ceil(spec.broll.text_pops_max_per_60s * runtime / 60 - EPS)


def _text_pops(
    beats: Sequence[Beat],
    runtime: float,
    spec: StyleSpec,
    words: Sequence[Word],
    spans: Sequence[Span],
) -> tuple[list[Violation], list[Beat]]:
    """061 (4.1 as amended): a text pop sits on a picture beat (`TEXT_POP_KINDS`), is
    one to `TEXT_POP_WORDS_MAX` words, names a transcript word the beat covers, and
    there are at most `broll.motion.text_pop.max_per_beat` per beat and `text_pop_cap`
    over the runtime (a style with the cap at 0 has none). Beats are output seconds
    here, so every pop's `at_s` is rewritten as its word's start on the output timeline
    (`presenter.output_time`), whatever the planner put there."""
    found: list[Violation] = []
    out: list[Beat] = []
    cap = text_pop_cap(spec, runtime=runtime)
    per_beat = int(spec.broll.motion.get("text_pop", {}).get("max_per_beat", 0))
    total = 0
    for b in beats:
        if not b.text_pops:
            out.append(b)
            continue
        kind = "presenter_full" if b.mode == "full" else b.kind
        if kind not in TEXT_POP_KINDS:
            picture_kinds = ", ".join(sorted(TEXT_POP_KINDS))
            found.append(
                _v("4.1", b.id, f"text pops sit on a picture beat ({picture_kinds}); this "
                                f"beat is a {b.kind!r}")  # fmt: skip
            )
        if len(b.text_pops) > per_beat:
            found.append(
                _v("4.1", b.id, f"{len(b.text_pops)} text pops on one beat; broll.motion."
                                f"text_pop.max_per_beat allows {per_beat}")  # fmt: skip
            )
        resolved: list[TextPop] = []
        for i, pop in enumerate(b.text_pops):
            total += 1
            if total > cap:
                found.append(
                    _v("4.1", b.id, f"text pop {total} over {runtime:g} s; "
                                    f"broll.text_pops_max_per_60s "
                                    f"{spec.broll.text_pops_max_per_60s} allows {cap} "
                                    "(061)")  # fmt: skip
                )
            count = len(pop.text.split())
            if not 1 <= count <= TEXT_POP_WORDS_MAX:
                found.append(
                    _v("4.1", b.id, f"text pop {i} {pop.text!r} is {count} words; a pop is 1-"
                                    f"{TEXT_POP_WORDS_MAX} words")  # fmt: skip
                )
            if not 0 <= pop.word < len(words):
                found.append(
                    _v("4.1", b.id, f"text pop {i} {pop.text!r} lands on word {pop.word}; "
                                    f"the transcript has {len(words)} words "
                                    f"(0-{len(words) - 1})")  # fmt: skip
                )
                resolved.append(pop)
                continue
            at = round(presenter.output_time(spans, words[pop.word].start), 3)
            if not b.start - CONTIGUITY_TOL_S <= at < b.end:
                found.append(
                    _v("4.1", b.id, f"text pop {i} {pop.text!r} lands on word {pop.word} "
                                    f"({words[pop.word].text!r} at {at:g} s on the cut), "
                                    f"which this beat ({b.start:g}-{b.end:g} s) does not "
                                    "cover")  # fmt: skip
                )
            resolved.append(pop.model_copy(update={"at_s": max(at, b.start)}))
        out.append(b.model_copy(update={"text_pops": resolved}))
    return found, out


def bubble_cap(spec: StyleSpec, *, runtime: float) -> int:
    """063: `broll.bubbles_max_per_60s` scaled to the runtime, rounded up like the other
    per-60 s maxima (4.3): a six-second fixture allows two (one dialogue pair) under a
    style that allows twenty a minute; 0 stays 0."""
    return math.ceil(spec.broll.bubbles_max_per_60s * runtime / 60 - EPS)


def bubble_gap(spec: StyleSpec) -> tuple[float, float]:
    """063 (3): how long after the first bubble of a beat the second lands, the style's
    `broll.motion.bubble.dialogue_gap_min_s` and `dialogue_gap_max_s`."""
    row = spec.broll.motion.get("bubble", {})
    return float(row.get("dialogue_gap_min_s", 0.0)), float(row.get("dialogue_gap_max_s", 0.0))


def _bubbles(
    beats: Sequence[Beat],
    runtime: float,
    spec: StyleSpec,
    words: Sequence[Word],
    spans: Sequence[Span],
) -> tuple[list[Violation], list[Beat]]:
    """063 (4.1 as amended): a bubble sits on a picture beat (`BUBBLE_KINDS`), is one to
    `broll.motion.bubble.words_max` words, names the transcript words it came from
    (`first`-`last`, which exist and start before the beat ends), and there are at most
    `motion.bubble.max_per_beat` per beat and `bubble_cap` over the runtime (a style
    with the cap at 0 has none). Beats are output seconds here, so every bubble's
    `at_s` is rewritten: the first source word's start on the output timeline, or the
    beat's start when the words were said earlier; a second bubble lands
    `dialogue_gap_min_s`-`dialogue_gap_max_s` after the one before it (its word's time
    when inside that window, else the nearer edge), and a beat that ends before the
    window opens cannot hold the pair."""
    found: list[Violation] = []
    out: list[Beat] = []
    cap = bubble_cap(spec, runtime=runtime)
    row = spec.broll.motion.get("bubble", {})
    per_beat, words_max = int(row.get("max_per_beat", 0)), int(row.get("words_max", 0))
    gap_min, gap_max = bubble_gap(spec)
    total = 0
    for b in beats:
        if not b.bubbles:
            out.append(b)
            continue
        kind = "presenter_full" if b.mode == "full" else b.kind
        if kind not in BUBBLE_KINDS:
            picture_kinds = ", ".join(sorted(BUBBLE_KINDS))
            found.append(
                _v("4.1", b.id, f"bubbles sit on a picture beat ({picture_kinds}); this beat "
                                f"is a {b.kind!r}")  # fmt: skip
            )
        if len(b.bubbles) > per_beat:
            found.append(
                _v("4.1", b.id, f"{len(b.bubbles)} bubbles on one beat; broll.motion.bubble."
                                f"max_per_beat allows {per_beat}")  # fmt: skip
            )
        resolved: list[Bubble] = []
        previous: float | None = None
        for i, bubble in enumerate(b.bubbles):
            total += 1
            if total > cap:
                found.append(
                    _v("4.1", b.id, f"bubble {total} over {runtime:g} s; "
                                    f"broll.bubbles_max_per_60s {spec.broll.bubbles_max_per_60s} "
                                    f"allows {cap} (063)")  # fmt: skip
                )
            count = len(bubble.text.split())
            if not 1 <= count <= words_max:
                found.append(
                    _v("4.1", b.id, f"bubble {i} {bubble.text!r} is {count} words; a bubble is "
                                    f"1-{words_max} words")  # fmt: skip
                )
            if not 0 <= bubble.first <= bubble.last < len(words):
                found.append(
                    _v("4.1", b.id, f"bubble {i} {bubble.text!r} comes from words {bubble.first}-"
                                    f"{bubble.last}; the transcript has {len(words)} words "
                                    f"(0-{len(words) - 1})")  # fmt: skip
                )
                resolved.append(bubble)
                continue
            said = round(presenter.output_time(spans, words[bubble.first].start), 3)
            if said >= b.end - CONTIGUITY_TOL_S:
                found.append(
                    _v("4.1", b.id, f"bubble {i} {bubble.text!r} quotes word {bubble.first} "
                                    f"({words[bubble.first].text!r} at {said:g} s on the cut), "
                                    f"said only after this beat ({b.start:g}-{b.end:g} s) "
                                    "ends")  # fmt: skip
                )
            at = max(said, b.start)
            if previous is not None:
                window = (round(previous + gap_min, 3), round(previous + gap_max, 3))
                at = min(max(at, window[0]), window[1])
                if window[0] >= b.end - CONTIGUITY_TOL_S:
                    found.append(
                        _v("4.1", b.id, f"bubble {i} {bubble.text!r} would land {gap_min:g} s "
                                        f"after the one before it, at {window[0]:g} s, past this "
                                        f"beat's end ({b.end:g} s): too short for a dialogue pair "
                                        "(063)")  # fmt: skip
                    )
            previous = at
            resolved.append(bubble.model_copy(update={"at_s": round(at, 3)}))
        out.append(b.model_copy(update={"bubbles": resolved}))
    return found, out


def sticker_cap(spec: StyleSpec, *, runtime: float) -> int:
    """062: `broll.stickers_max_per_60s` scaled to the runtime, rounded up like the other
    per-60 s maxima (4.3); 0 stays 0."""
    return math.ceil(spec.broll.stickers_max_per_60s * runtime / 60 - EPS)


def _stickers(
    beats: Sequence[Beat],
    runtime: float,
    spec: StyleSpec,
    words: Sequence[Word],
    spans: Sequence[Span],
) -> tuple[list[Violation], list[Beat]]:
    """062 (4.1 as amended): a sticker sits on a picture beat (`STICKER_KINDS`), is
    picked by a tag of the committed catalogue (`stickers.shipped`) and, when it names a
    row, a row carrying that tag - never a file; it lands on a transcript word the beat
    covers; off the PIP (a `full` beat) it needs its `{x, y}`, there being no circle to
    sit above. At most `motion.sticker.max_per_beat` per beat and `sticker_cap` over the
    runtime (a style with the cap at 0 has none). Every sticker's `name` is written (the
    tag's first row when empty) and its `at_s` rewritten as its word's start on the
    output timeline, whatever the planner put there."""
    found: list[Violation] = []
    out: list[Beat] = []
    cap = sticker_cap(spec, runtime=runtime)
    per_beat = int(spec.broll.motion.get("sticker", {}).get("max_per_beat", 0))
    catalogue = stickers.shipped()
    total = 0
    for b in beats:
        if not b.stickers:
            out.append(b)
            continue
        kind = "presenter_full" if b.mode == "full" else b.kind
        if kind not in STICKER_KINDS:
            picture_kinds = ", ".join(sorted(STICKER_KINDS))
            found.append(
                _v("4.1", b.id, f"stickers sit on a picture beat ({picture_kinds}); this beat "
                                f"is a {b.kind!r}")  # fmt: skip
            )
        if len(b.stickers) > per_beat:
            found.append(
                _v("4.1", b.id, f"{len(b.stickers)} stickers on one beat; broll.motion.sticker."
                                f"max_per_beat allows {per_beat}")  # fmt: skip
            )
        resolved: list[Sticker] = []
        for i, sticker in enumerate(b.stickers):
            total += 1
            if total > cap:
                found.append(
                    _v("4.1", b.id, f"sticker {total} over {runtime:g} s; "
                                    f"broll.stickers_max_per_60s "
                                    f"{spec.broll.stickers_max_per_60s} allows {cap} "
                                    "(062)")  # fmt: skip
                )
            entry = catalogue.pick(sticker.intent, sticker.name)
            if entry is None:
                wanted = f"row {sticker.name!r} tagged {sticker.intent!r}" if sticker.name else (
                    f"tag {sticker.intent!r}"
                )
                found.append(
                    _v("4.1", b.id, f"sticker {i}: the catalogue has no {wanted}; pick a tag "
                                    f"from {catalogue.tags()} and, if you name a row, one "
                                    "listed under that tag (062)")  # fmt: skip
                )
            if b.mode != "pip" and sticker.x is None:
                found.append(
                    _v("4.1", b.id, f"sticker {i} {sticker.intent!r} on a {b.mode!r} beat has no "
                                    "PIP circle to sit above; give its {x, y}")  # fmt: skip
                )
            name = entry.name if entry is not None else sticker.name
            if not 0 <= sticker.word < len(words):
                found.append(
                    _v("4.1", b.id, f"sticker {i} {sticker.intent!r} lands on word "
                                    f"{sticker.word}; the transcript has {len(words)} words "
                                    f"(0-{len(words) - 1})")  # fmt: skip
                )
                resolved.append(sticker.model_copy(update={"name": name}))
                continue
            at = round(presenter.output_time(spans, words[sticker.word].start), 3)
            if not b.start - CONTIGUITY_TOL_S <= at < b.end:
                found.append(
                    _v("4.1", b.id, f"sticker {i} {sticker.intent!r} lands on word "
                                    f"{sticker.word} ({words[sticker.word].text!r} at {at:g} s "
                                    f"on the cut), which this beat ({b.start:g}-{b.end:g} s) "
                                    "does not cover")  # fmt: skip
                )
            resolved.append(sticker.model_copy(update={"name": name, "at_s": max(at, b.start)}))
        out.append(b.model_copy(update={"stickers": resolved}))
    return found, out


def highlight_cap(spec: StyleSpec, *, runtime: float) -> int:
    """078: `broll.highlights_max_per_60s` scaled to the runtime, rounded up like the other
    per-60 s maxima (4.3); 0 stays 0."""
    return math.ceil(spec.broll.highlights_max_per_60s * runtime / 60 - EPS)


def _highlights(
    beats: Sequence[Beat],
    runtime: float,
    spec: StyleSpec,
    words: Sequence[Word],
    spans: Sequence[Span],
    references: Sequence[str],
) -> tuple[list[Violation], list[Beat]]:
    """078 (4.1 as amended): a highlight sits on a `photo` or `card` beat with the picture
    on screen (not `full`), marks the owner's uploaded screenshot - one of `references`,
    never a searched or generated page - that the beat itself shows, names transcript
    words the beat says (the first one starts inside it), and there are at most
    `highlight_cap` over the runtime (a style with the cap at 0 has none). Beats are output
    seconds here, so `at_s` is rewritten as the first word's start and `end_s` as the last
    word's end on the output timeline, whatever the planner put there."""
    found: list[Violation] = []
    out: list[Beat] = []
    cap = highlight_cap(spec, runtime=runtime)
    total = 0
    for b in beats:
        lit = b.highlight
        if lit is None:
            out.append(b)
            continue
        total += 1
        label = f"highlight {lit.sentence!r}"
        if total > cap:
            found.append(
                _v("4.1", b.id, f"{label}: highlight {total} over {runtime:g} s; "
                                f"broll.highlights_max_per_60s "
                                f"{spec.broll.highlights_max_per_60s} allows {cap} "
                                "(078)")  # fmt: skip
            )
        if b.kind not in HIGHLIGHT_KINDS or b.mode == "full":
            found.append(
                _v("4.1", b.id, f"{label} sits on a photo or card beat with the picture on "
                                f"screen; this beat is a {b.mode} {b.kind!r}")  # fmt: skip
            )
        if lit.asset_id not in references:
            found.append(
                _v("4.1", b.id, f"{label} marks {lit.asset_id!r}, which is not one of the "
                                "owner's uploaded references; a highlight marks only the "
                                "owner's article or document screenshot, never a made-up "
                                "page (078)")  # fmt: skip
            )
        if lit.asset_id != b.asset_id:
            found.append(
                _v("4.1", b.id, f"{label} marks {lit.asset_id!r} but the beat shows "
                                f"{b.asset_id!r}; the beat shows the screenshot it "
                                "highlights")  # fmt: skip
            )
        first, last = lit.words
        if not last < len(words):
            found.append(
                _v("4.1", b.id, f"{label} is said by words {first}-{last}; the transcript "
                                f"has {len(words)} words (0-{len(words) - 1})")  # fmt: skip
            )
            out.append(b)
            continue
        at = round(presenter.output_time(spans, words[first].start), 3)
        end = round(presenter.output_time(spans, words[last].end), 3)
        if not b.start - CONTIGUITY_TOL_S <= at < b.end:
            found.append(
                _v("4.1", b.id, f"{label} starts on word {first} ({words[first].text!r} at "
                                f"{at:g} s on the cut), which this beat ({b.start:g}-"
                                f"{b.end:g} s) does not say")  # fmt: skip
            )
        resolved = lit.model_copy(update={"at_s": max(at, b.start), "end_s": max(end, at)})
        out.append(b.model_copy(update={"highlight": resolved}))
    return found, out


def _subjects(beats: Sequence[Beat], runtime: float, brief: str) -> list[Violation]:
    """4.2: subject_kind and query on every B-roll beat; an entity beat per 60 s when
    the brief names something."""
    found: list[Violation] = []
    for b in beats:
        if b.kind in PRESENTER_KINDS or b.kind in FIXED_MOTION_KINDS:
            continue
        if b.subject_kind is None:
            found.append(_v("4.2", b.id, "no subject_kind (entity | concept | number | quote)"))
        if not b.query.strip():
            found.append(_v("4.2", b.id, "no query"))
    nouns = proper_nouns(brief)
    if nouns:
        needed = max(1, math.ceil(runtime / 60 - EPS))
        entities = sum(1 for b in beats if b.subject_kind == "entity")
        if entities < needed:
            found.append(
                _v(
                    "4.2",
                    None,
                    f"{entities} entity beats over {runtime:g} s; at least one per 60 s "
                    f"({needed}) when the brief names something ({', '.join(nouns[:3])})",
                )
            )
    return found


def _assets(
    beats: Sequence[Beat], runtime: float, spec: StyleSpec
) -> tuple[list[Violation], list[str]]:
    """4.3: unique assets inside the per-60 s range, `reuse_max` showings per asset,
    a warning when nothing is reused. Set-piece items are a montage of plan assets and
    are not showings; nor (056 (3)) is a `number` / `quote` beat carrying on the previous
    beat's asset, or the wall's base and the finale's cards (`assets.is_showing`)."""
    nums = spec.broll
    found: list[Violation] = []
    warnings: list[str] = []
    unique = {b.asset_id for b in beats if b.asset_id}
    uses: Counter[str] = Counter()
    previous: str | None = None
    for b in beats:
        if b.asset_id and assets.is_showing(b, b.asset_id, previous):
            uses[b.asset_id] += 1
        previous = b.asset_id
    scale = runtime / 60
    lo = math.floor(nums.unique_assets_min_per_60s * scale + EPS)
    hi = math.ceil(nums.unique_assets_max_per_60s * scale - EPS)
    if len(unique) < lo:
        found.append(
            _v(
                "4.3",
                None,
                f"{len(unique)} unique assets over {runtime:g} s; "
                f"broll.unique_assets_min_per_60s {nums.unique_assets_min_per_60s} "
                f"needs at least {lo}",
            )
        )
    if len(unique) > hi:
        found.append(
            _v(
                "4.3",
                None,
                f"{len(unique)} unique assets over {runtime:g} s; "
                f"broll.unique_assets_max_per_60s {nums.unique_assets_max_per_60s} "
                f"allows at most {hi}",
            )
        )
    for asset, count in sorted(uses.items()):
        if count > nums.reuse_max:
            found.append(
                _v(
                    "4.3",
                    None,
                    f"asset {asset!r} is shown {count} times, over broll.reuse_max "
                    f"{nums.reuse_max}",
                )
            )
    if uses and max(uses.values()) < 2:
        warnings.append(
            "plan (4.3): no asset is reused; callbacks and payoffs return to an earlier asset"
        )
    return found, warnings


def flash_cap(spec: StyleSpec, *, runtime: float) -> int:
    """060: `broll.flash_max_per_60s` scaled to the runtime, rounded up like the other
    per-60 s maxima (4.3), so a six-second fixture still allows one flash."""
    return math.ceil(spec.broll.flash_max_per_60s * runtime / 60 - EPS)


def _transitions(beats: Sequence[Beat], runtime: float, spec: StyleSpec) -> list[Violation]:
    """9.4: names inside the style list, `whip_max_per_3_beats`, never two whips in a
    row; 060: at most `flash_cap` flashes over the runtime, never two in a row."""
    nums = spec.broll
    found: list[Violation] = []
    flashes = 0
    cap = flash_cap(spec, runtime=runtime)
    for i, b in enumerate(beats):
        if b.enter not in nums.enter_transitions:
            found.append(
                _v(
                    "9.4",
                    b.id,
                    f"enter {b.enter!r} is not in broll.enter_transitions "
                    f"{nums.enter_transitions}",
                )
            )
        if b.enter == "flash":
            flashes += 1
            if i > 0 and beats[i - 1].enter == "flash":
                found.append(
                    _v("9.4", b.id, f"two flashes in a row ({beats[i - 1].id} then {b.id}) (060)")
                )
            elif flashes > cap:
                found.append(
                    _v(
                        "9.4",
                        b.id,
                        f"flash {flashes} over {runtime:g} s; broll.flash_max_per_60s "
                        f"{nums.flash_max_per_60s} allows {cap} (060)",
                    )
                )
        if b.enter != "whip":
            continue
        if i > 0 and beats[i - 1].enter == "whip":
            found.append(_v("9.4", b.id, f"two whips in a row ({beats[i - 1].id} then {b.id})"))
            continue
        window = beats[max(0, i - 2) : i + 1]
        whips = sum(1 for w in window if w.enter == "whip")
        if whips > nums.whip_max_per_3_beats:
            found.append(
                _v(
                    "9.4",
                    b.id,
                    f"{whips} whips within three beats, over broll.whip_max_per_3_beats "
                    f"{nums.whip_max_per_3_beats}",
                )
            )
    return found


def _must_use(beats: Sequence[Beat], must_use: Sequence[str]) -> list[Violation]:
    """2.3: every reference the brief marks must-use appears in the plan, on a beat or
    as a set-piece item."""
    used = {b.asset_id for b in beats if b.asset_id}
    used |= {i.asset_id for b in beats for i in b.items if i.asset_id}
    return [
        _v("2.3", None, f"must-use reference {ref!r} is not used by any beat or set-piece item")
        for ref in must_use
        if ref not in used
    ]


def _category(plan: PicturePlan) -> list[Violation]:
    """10.3 (033): the short's category comes from the fixed list the reference
    library is organised by; the message carries the list so the retry can pick."""
    if plan.category in CATEGORIES:
        return []
    return [
        _v(
            "10.3",
            None,
            f"category {plan.category!r} is not one of {', '.join(CATEGORIES)}",
        )
    ]


def _title_strip(plan: PicturePlan, spec: StyleSpec) -> list[Violation]:
    """059 (4.1 as amended): a style with `broll.title_strip` draws the plan's
    `title_strip` for the whole short, so the plan writes the topic in 1 to `words_max`
    words; a style without the row draws none, so the plan leaves it empty."""
    row = spec.broll.title_strip
    count = len(plan.title_strip.split())
    if row is None:
        if not count:
            return []
        message = (f"title_strip {plan.title_strip!r} is set, but style {spec.name!r} draws "
                   "no title strip; leave it empty")  # fmt: skip
    elif count == 0:
        message = (f"style {spec.name!r} draws a title strip: write title_strip, the topic in "
                   f"1-{row.words_max} words")  # fmt: skip
    elif count > row.words_max:
        message = (f"title_strip {plan.title_strip!r} is {count} words; "
                   f"broll.title_strip.words_max is {row.words_max}")  # fmt: skip
    else:
        return []
    return [_v("4.1", None, message)]


def _clamp_fields(
    plan: PicturePlan, words: Sequence[Word], spec: StyleSpec
) -> tuple[PicturePlan, list[Clamp]]:
    """6.1 keywords, 8.2 hashtags and title."""
    clamps: list[Clamp] = []
    changes: dict[str, object] = {}
    ratio = spec.captions.emphasis_max_ratio
    cap = math.floor(len(words) * ratio + EPS)
    if len(plan.keywords) > cap:
        changes["keywords"] = list(plan.keywords[:cap])
        clamps.append(
            Clamp(
                rule="6.1",
                message=(
                    f"keywords: {len(plan.keywords)} trimmed to {cap} "
                    f"(captions.emphasis_max_ratio {ratio:g} of {len(words)} words)"
                ),
            )
        )
    if len(plan.hashtags) > HASHTAGS_MAX:
        changes["hashtags"] = list(plan.hashtags[:HASHTAGS_MAX])
        clamps.append(
            Clamp(rule="8.2", message=f"hashtags: {len(plan.hashtags)} trimmed to {HASHTAGS_MAX}")
        )
    if len(plan.title) > TITLE_MAX_CHARS:
        changes["title"] = plan.title[:TITLE_MAX_CHARS].rstrip()
        clamps.append(
            Clamp(
                rule="8.2", message=f"title: {len(plan.title)} characters cut to {TITLE_MAX_CHARS}"
            )
        )
    return (plan.model_copy(update=changes) if changes else plan), clamps


# --- the sound story --------------------------------------------------------------------


IDEA = "idea"  # 062's sticker tag a ding may ride (070)


def _mark_problem(cue: Cue, beat: Beat, nums: styles.Sound, *, on_pop: bool) -> str | None:
    """070 (7.3 as amended): why a tick or a ding cue is not where its row allows, else
    None (a whoosh keeps 060's own lines; the floor classes 9.4's)."""
    if cue.intent == styles.TICK:
        if styles.POP in nums.tick.on and on_pop:
            return None
        return (
            f"cue {cue.intent!r} at {cue.at!r}: a tick sits only on a pop-in - at the event "
            "of a beat carrying text pops, bubbles or a sticker (070)"
        )
    if cue.intent == styles.DING:
        idea = any(s.intent == IDEA for s in beat.stickers)
        if styles.IDEA_STICKER in nums.ding.on and cue.at == "event" and idea:
            return None
        return (
            f"cue {cue.intent!r} at {cue.at!r}: a ding sits only on the pop-in of a sticker "
            f"tagged {IDEA!r} - at the event of its beat (070); rings, bells and chimes never"
        )
    return None


@functools.cache
def _shipped_moods() -> vocab.Moods:
    return vocab.load_moods()


def _closed(name: str, group: str, entries: Mapping[str, vocab.Entry]) -> str | None:
    """076: why `name` is not a usable mood (or flavour), else None."""
    if name not in entries:
        return f"{group} {name!r} is not a {group} of moods.yaml ({', '.join(entries)})"
    if not entries[name].active:
        return (
            f"{group} {name!r} is not active in moods.yaml: the approved library has no bed "
            "for it"
        )
    return None


def _part_problems(story: SoundStory, picture: PicturePlan) -> list[str]:
    """076: the story parts tile the plan's beats in order, hook to ending, once each."""
    order = [b.id for b in picture.beats]
    index = {beat_id: i for i, beat_id in enumerate(order)}
    if not story.parts:
        return ["the sound story names no story `parts` (hook / build_up / reveal / ending)"]
    problems: list[str] = []
    ranks = [STORY_PARTS.index(p.part) for p in story.parts]
    if ranks != sorted(set(ranks)):
        problems.append("the story parts are not in story order, each once (hook, build_up, "
                        "reveal, ending)")  # fmt: skip
    expected = 0
    for p in story.parts:
        unknown = [b for b in (p.first_beat, p.last_beat) if b not in index]
        if unknown:
            problems.append(f"part {p.part} names {', '.join(unknown)}, not a beat of the plan")
            continue
        first, last = index[p.first_beat], index[p.last_beat]
        if first != expected or last < first:
            problems.append(
                f"part {p.part} ({p.first_beat}-{p.last_beat}) does not start where the part "
                f"before it ends ({order[expected] if expected < len(order) else 'the end'}): "
                "the parts must tile the beats in order"
            )
            return problems
        expected = last + 1
    if expected != len(order):
        problems.append(f"the story parts end before the plan does ({order[expected]} onward "
                        "belongs to no part)")  # fmt: skip
    return problems


def _bed_problems(
    story: SoundStory, picture: PicturePlan, nums: styles.Sound, moods: vocab.Moods
) -> list[Violation]:
    """076 (7.2 / 7.3 as amended): the bed per story part. One or two segments, their
    moods and flavours from the closed list and active, at most `sound.bed_changes_max`
    changes, and the change on the first beat of the second segment's part."""
    found = [_v("7.2", None, line) for line in _part_problems(story, picture)]
    if not story.bed:
        found.append(_v("7.2", None, "the sound story names no bed segment {part_from, mood}"))
        return found
    for segment in story.bed:
        why = [_closed(segment.mood, "mood", moods.moods)]
        if segment.flavour is not None:
            why.append(_closed(segment.flavour, "flavour", moods.flavours))
        found += [_v("7.2", None, f"bed from {segment.part_from}: {w}") for w in why if w]
    changes = len(story.bed) - 1
    if changes > nums.bed_changes_max:
        found.append(
            _v("7.3", None, f"{len(story.bed)} bed segments make {changes} changes: "
                            f"sound.bed_changes_max {nums.bed_changes_max} allows "
                            f"{nums.bed_changes_max}")  # fmt: skip
        )
        return found
    starts = {p.part: p.first_beat for p in story.parts}
    if story.bed[0].part_from != (story.parts[0].part if story.parts else "hook"):
        found.append(_v("7.2", None, f"the first bed segment starts at {story.bed[0].part_from}, "
                                     "not at the first story part"))  # fmt: skip
    if changes == 0:
        if story.change is not None:
            found.append(_v("7.3", story.change.at_beat,
                            "a bed change with one bed segment: drop the change or add the "
                            "second segment"))  # fmt: skip
        return found
    second = story.bed[1]
    if story.change is None:
        found.append(_v("7.3", None, f"two bed segments and no change: say at which beat and "
                                     f"how the bed changes for {second.part_from}"))  # fmt: skip
        return found
    at = story.change.at_beat
    boundary = starts.get(second.part_from)
    if boundary is None or STORY_PARTS.index(second.part_from) <= STORY_PARTS.index(
        story.bed[0].part_from
    ):
        found.append(_v("7.3", at, f"the second bed segment's part {second.part_from} is not a "
                                   "later story part of this script"))  # fmt: skip
    elif at != boundary:
        found.append(_v("7.3", at, f"the bed change at {at} is not on a story-part boundary: "
                                   f"{second.part_from} starts at {boundary}"))  # fmt: skip
    return found


def validate_sound(
    story: SoundStory, picture: PicturePlan, spec: StyleSpec, *, moods: vocab.Moods | None = None
) -> SoundCheck | Violations:
    """7.3 / 8.2 / 9.4 on the SoundStory against the (snapped) picture plan; 076 the bed
    per story part against the closed mood list (`moods`, the shipped file unless given)."""
    nums = spec.sound
    beats = {b.id: b for b in picture.beats}
    runtime = picture.beats[-1].end if picture.beats else 0.0
    found: list[Violation] = _bed_problems(
        story, picture, nums, moods if moods is not None else _shipped_moods()
    )
    clamps: list[Clamp] = []

    cues: list[Cue] = []
    per_beat: Counter[str] = Counter()
    allowance = nums.whoosh if styles.allows_whoosh(nums) else None
    for cue in story.cues:
        beat = beats.get(cue.beat_id)
        if beat is None:
            found.append(
                _v("8.2", cue.beat_id, f"cue {cue.intent!r} names a beat that is not in the plan")
            )
            continue
        if cue.intent not in CUE_KINDS:
            # 070 (7.1 as amended): the palette is closed; a name outside it is never
            # searched for or matched, so the plan is sent back naming it.
            found.append(
                _v(
                    "7.1",
                    beat.id,
                    f"cue {cue.intent!r} is outside the sound palette ({', '.join(CUE_KINDS)})",
                )
            )
            continue
        # 029: a counter lands; 061 / 063 / 062: a text pop, a bubble or a sticker pops
        # in, so an `event` cue has something to hit there too.
        popping = pops_in(beat)
        bare = beat.event.kind == "none" and beat.counter is None and not popping
        # 060 / 070 (7.3 as amended): a whoosh rides a non-cut enter its row names or a
        # pop-in (a `whoosh` at the `event` of a beat carrying text pops, bubbles or a
        # sticker rides the first one); a tick only a pop-in; a ding only an `idea`
        # sticker's pop-in.
        whoosh = styles.is_whoosh(cue.intent)
        on_enter = cue.at == "start" and beat.enter != "cut"
        on_pop = cue.at == "event" and popping
        whoosh_ok = (
            whoosh
            and allowance is not None
            and ((on_enter and beat.enter in allowance.on)
                 or (styles.POP in allowance.on and on_pop))
        )  # fmt: skip
        mark = _mark_problem(cue, beat, nums, on_pop=on_pop)
        if mark is not None:
            found.append(_v("7.3", beat.id, mark))
        elif whoosh and allowance is None:
            found.append(
                _v(
                    "7.3",
                    beat.id,
                    f"cue {cue.intent!r}: whooshes are in sound.forbidden for this style "
                    f"(no sound.whoosh allowance; 060)",
                )
            )
        elif whoosh and not whoosh_ok:
            found.append(
                _v(
                    "7.3",
                    beat.id,
                    f"cue {cue.intent!r} at {cue.at!r} on a {beat.enter!r} enter: a whoosh is "
                    f"allowed only on {allowance.on} - at the start of a beat entering on one "
                    "of those, or at the event of a beat carrying text pops, bubbles or a "
                    "sticker (060, 070)"
                    if allowance is not None
                    else f"cue {cue.intent!r}: whooshes are forbidden (060)",
                )
            )
        elif cue.at == "event" and bare:
            found.append(
                _v(
                    "9.4",
                    beat.id,
                    f"cue {cue.intent!r} at the event of a beat with no landed event",
                )
            )
        elif cue.at == "start" and bare and beat.enter != "cut" and not whoosh_ok:
            found.append(
                _v(
                    "9.4",
                    beat.id,
                    f"cue {cue.intent!r} on the {beat.enter!r} enter of a beat with no landed "
                    "event (no cue on a bare transition)",
                )
            )
        if per_beat[beat.id] >= nums.cues_per_beat_max:
            clamps.append(
                Clamp(
                    rule="7.3",
                    beat_id=beat.id,
                    message=(
                        f"cue {cue.intent!r} dropped: sound.cues_per_beat_max "
                        f"{nums.cues_per_beat_max}"
                    ),
                )
            )
            continue
        per_beat[beat.id] += 1
        cues.append(cue)
    cap = math.floor(nums.cues_max_per_60s * runtime / 60 + EPS)
    if len(cues) > cap:
        for cue in cues[cap:]:
            clamps.append(
                Clamp(
                    rule="7.3",
                    beat_id=cue.beat_id,
                    message=(
                        f"cue {cue.intent!r} dropped: {len(cues)} cues over {runtime:g} s, "
                        f"sound.cues_max_per_60s {nums.cues_max_per_60s} allows {cap}"
                    ),
                )
            )
        cues = cues[:cap]

    points: list[MoodPoint] = []
    for p in story.mood_curve:
        level = min(max(p.level, nums.drop_min_db), nums.swell_max_db)
        if level != p.level:
            clamps.append(
                Clamp(
                    rule="7.3",
                    message=(
                        f"mood level {p.level:g} dB at {p.t:g} s clipped to {level:g} dB "
                        f"(sound.swell_max_db {nums.swell_max_db:g}, "
                        f"sound.drop_min_db {nums.drop_min_db:g})"
                    ),
                )
            )
        if p.t < -EPS or p.t > runtime + EPS:
            found.append(
                _v("7.3", None, f"mood point at {p.t:g} s is outside the runtime 0-{runtime:g} s")
            )
        points.append(MoodPoint(t=p.t, level=level))
    if any(b.t < a.t for a, b in zip(points, points[1:], strict=False)):
        found.append(_v("7.3", None, "mood curve times are not in order"))
    boundaries = sorted({b.start for b in picture.beats} | {b.end for b in picture.beats})
    for a, b in zip(points, points[1:], strict=False):
        dt, dl = b.t - a.t, b.level - a.level
        if dl == 0 or dt + EPS >= nums.ramp_min_s:
            continue
        at_boundary = any(abs(b.t - x) <= CONTIGUITY_TOL_S for x in boundaries)
        if dl < 0 and at_boundary:
            continue  # a drop: a step down at a beat boundary (7.3)
        found.append(
            _v(
                "7.3",
                None,
                f"mood curve {'rises' if dl > 0 else 'falls'} {abs(dl):g} dB over {dt:g} s "
                f"({a.t:g} to {b.t:g} s), under sound.ramp_min_s {nums.ramp_min_s:g} s"
                + ("" if dl > 0 else "; a drop must step down at a beat boundary"),
            )
        )
    if found:
        return Violations(items=found)
    clamped = story.model_copy(update={"cues": cues, "mood_curve": points})
    return SoundCheck(sound=clamped, clamps=clamps)


# --- brief parsing (2.3, 4.2) -----------------------------------------------------------

_SENTENCES = re.compile(r"[.!?\n]+")
_MUST_USE = re.compile(r"must[\s_-]*use", re.IGNORECASE)
_CAPITALISED = re.compile(r"[A-Z][a-z]+")


def proper_nouns(text: str) -> list[str]:
    """Capitalised words that do not open a sentence: the 4.2 'brief has a proper
    noun' test. A field label's first word ('Topic: Why ...') counts, which errs on
    the side of asking for an entity beat."""
    nouns: list[str] = []
    for sentence in _SENTENCES.split(text):
        tokens = sentence.split()
        for token in tokens[1:]:
            core = token.strip("()[],;:\"'")
            if _CAPITALISED.fullmatch(core) and core not in nouns:
                nouns.append(core)
    return nouns


def must_use_ids(brief: str, references: Sequence[PlanReference]) -> list[str]:
    """Reference ids the brief marks must-use (2.3): a sentence saying 'must use'
    that names the reference by id or caption."""
    ids: list[str] = []
    for sentence in _SENTENCES.split(brief):
        if not _MUST_USE.search(sentence):
            continue
        lowered = sentence.lower()
        for ref in references:
            named = ref.id in sentence or (ref.caption and ref.caption.lower() in lowered)
            if named and ref.id not in ids:
                ids.append(ref.id)
    return ids
