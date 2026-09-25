"""The plan validator (PRD `grammar`; decisions 2.3, 3.1, 3.2, 3.4, 4.1, 4.2, 4.3, 6.1,
7.3, 8.2, 9.4). Pure code over PicturePlan / SoundStory, Transcript and StyleSpec.

Three outcomes per 8.2. Clamps are fixes code makes without changing intent, each
logged as a `Clamp` citing the decision whose number it applied: beat boundaries
snapped to the nearest word end within `beats.snap_window_s` (3.1), keywords trimmed
to `captions.emphasis_max_ratio` (6.1), planner cues dropped past the 7.3 caps, the
mood curve clipped to `sound.swell_max_db` / `sound.drop_min_db` (7.3), hashtags to
five and the title to a hundred characters (8.2). Rejections come back as a
`Violations` list, every line carrying the beat id (or `plan`) and the decision
number, which is what the planner is re-sent on its one retry. Warnings (no asset
reused, a title that ignores a numeric hook wish) ride on the ValidatedPlan for the
contact sheet.

Every count and length comes from the style front matter (`styles.StyleSpec`), so a
style changes the grammar without code (3.2). Per-60 s counts scale with the plan's
runtime: floor for minimums, ceil for maximums. Beat times are output (cut-timeline)
seconds; word times are recording seconds, so a boundary is mapped through the cut
list (`presenter.cut_list`) before it meets the transcript.

Two readings this module fixes where the decisions leave room. Density (3.1): visual
events are beat starts and landed events; a landed event is taken to land mid-beat,
so a beat with one event may run to twice `density_gap_max_s` and a beat with none to
the gap itself. Set pieces (list, chart, split, wall, finale, hook cards), beats
with overlays and the cold open (its punch-in, 3.4) change on their own and are not
measured inside. Cold-open repeats (3.4): `presenter.cut_list` removes the lifted
span from the body under `drop`, so a repeat can only be deliberate (`keep`), and
`keep` on a span the cut drops is the contradiction this module rejects; a plan that
forgot the repeat in its runtime fails the tiling rule with the reason spelled out.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from shortsmith import presenter
from shortsmith.contracts import (
    TIER2_KINDS,
    Beat,
    Clamp,
    Cue,
    MoodPoint,
    PicturePlan,
    PlanReference,
    SoundStory,
    Span,
    StrictModel,
    Transcript,
    ValidatedPlan,
    Violation,
    Word,
)
from shortsmith.styles import StyleSpec

EPS = 1e-6
CONTIGUITY_TOL_S = 0.011  # one frame at 90 fps, the same slack T3 gives the render
HASHTAGS_MAX = 5  # 8.2
TITLE_MAX_CHARS = 100  # 8.2
PRESENTER_KINDS = frozenset({"presenter_full", "presenter_pip"})
FIXED_MOTION_KINDS = frozenset({"hook_cards", "finale"})  # motion comes from the spec table
SET_PIECE_KINDS = frozenset({"list", "chart", "split", "wall", "finale"})  # 3.1
DENSITY_EXEMPT_KINDS = SET_PIECE_KINDS | {"hook_cards"}
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
NUMBER_WORDS = {
    "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
    "7": "seven", "8": "eight", "9": "nine", "10": "ten", "12": "twelve",
}  # fmt: skip


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
) -> ValidatedPlan | Violations:
    """Both halves at once; the sound story is checked against the snapped picture
    when the picture passes, against the raw one otherwise so every violation is
    listed."""
    pic = validate_picture(plan, transcript, spec, brief=brief, must_use=must_use)
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
) -> PictureCheck | Violations:
    if not plan.beats:
        return Violations(items=[Violation(rule="3.1", message="the plan has no beats")])
    found: list[Violation] = []
    clamps: list[Clamp] = []
    warnings: list[str] = []
    spans = presenter.cut_list(plan)
    runtime = presenter.total_duration(spans)
    words = transcript.words

    found += _tiling(plan, runtime)
    beats, snap_clamps, snap_found = _snap(plan.beats, spans, words, spec.beats.snap_window_s)
    clamps += snap_clamps
    found += snap_found
    found += _lengths(beats, spec)
    found += _density(beats, spec)
    found += _presenter(beats, plan, spec)
    found += _hook(beats, plan, words, spec)
    found += _kinds(beats, spec)
    found += _items(beats, spec)
    found += _charts(beats, spec)
    found += _maps(beats, spec)
    found += _overlays(beats)
    found += _subjects(beats, runtime, brief)
    asset_found, asset_warnings = _assets(beats, runtime, spec)
    found += asset_found
    warnings += asset_warnings
    found += _transitions(beats, spec)
    found += _must_use(beats, plan, must_use)
    warnings += _hook_wish(plan, brief)

    if found:
        return Violations(items=found)
    picture, field_clamps = _clamp_fields(plan.model_copy(update={"beats": beats}), words, spec)
    return PictureCheck(picture=picture, clamps=clamps + field_clamps, warnings=warnings)


def _v(rule: str, beat_id: str | None, message: str) -> Violation:
    return Violation(rule=rule, beat_id=beat_id, message=message)


def _len(beat: Beat) -> float:
    return round(beat.end - beat.start, 3)


def _tiling(plan: PicturePlan, runtime: float) -> list[Violation]:
    """3.1: beats tile the cut runtime with no gaps."""
    beats = plan.beats
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
        why = ""
        if plan.hook.original_position == "keep":
            why = " (the cold open plays twice under hook.original_position 'keep')"
        found.append(
            _v(
                "3.1",
                None,
                f"beats end at {beats[-1].end:g} s but the cut runs {runtime:.3f} s{why}",
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


def _density(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """3.1: the gap between consecutive visual events (beat starts, landed events) is
    at most `density_gap_max_s`; see the module docstring for the mid-beat reading."""
    gap_max = spec.beats.density_gap_max_s
    found: list[Violation] = []
    for i, b in enumerate(beats):
        if i == 0 or b.kind in DENSITY_EXEMPT_KINDS or b.overlays:
            continue  # the cold open carries its punch-in (3.4)
        length = _len(b)
        landed = b.event.kind != "none"
        gap = round(length / 2, 3) if landed else length
        if gap > gap_max + EPS:
            found.append(
                _v(
                    "3.1",
                    b.id,
                    f"nothing changes on screen for {gap:g} s "
                    f"({'one landed event' if landed else 'no landed event'} in a {length:g} s "
                    f"beat), over beats.density_gap_max_s {gap_max:g} s",
                )
            )
    return found


def _presenter(beats: Sequence[Beat], plan: PicturePlan, spec: StyleSpec) -> list[Violation]:
    """3.2: modes, reason tags, never-consecutive `full`, the full fraction, pip and
    off run caps, the hook beat's mode and the finale's."""
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
    if beats[0].mode not in pres.hook_modes:
        found.append(
            _v(
                "3.2",
                beats[0].id,
                f"hook beat is {beats[0].mode!r}; presenter.hook_modes {pres.hook_modes}",
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


def _hook(
    beats: Sequence[Beat], plan: PicturePlan, words: Sequence[Word], spec: StyleSpec
) -> list[Violation]:
    """3.4: the two-beat shape, slot lengths, title word count, card ids, the lifted
    span on word boundaries, `keep` consistent with the cut."""
    nums = spec.beats
    found: list[Violation] = []
    cold = beats[0]
    if cold.mode != "full" or cold.reason != "cold_open":
        found.append(
            _v(
                "3.4",
                cold.id,
                "the first beat must be the full cold open tagged 'cold_open' "
                f"(it is {cold.mode}/{cold.reason})",
            )
        )
    length = _len(cold)
    if length < nums.cold_open_min_s - EPS or length > nums.cold_open_max_s + EPS:
        found.append(
            _v(
                "3.4",
                cold.id,
                f"cold open is {length:g} s, outside beats.cold_open_min_s-beats.cold_open_max_s "
                f"{nums.cold_open_min_s:g}-{nums.cold_open_max_s:g} s",
            )
        )
    if len(beats) < 2:
        found.append(_v("3.4", None, "the plan needs an off hook-cards beat after the cold open"))
        cards = cold
    else:
        cards = beats[1]
        if cards.kind != "hook_cards" or cards.mode != "off":
            found.append(
                _v(
                    "3.4",
                    cards.id,
                    f"the second beat must be off hook cards (it is {cards.mode}/{cards.kind})",
                )
            )
        length = _len(cards)
        if length < nums.hook_cards_min_s - EPS or length > nums.hook_cards_max_s + EPS:
            found.append(
                _v(
                    "3.4",
                    cards.id,
                    f"hook cards run {length:g} s, outside "
                    "beats.hook_cards_min_s-beats.hook_cards_max_s "
                    f"{nums.hook_cards_min_s:g}-{nums.hook_cards_max_s:g} s",
                )
            )
    title_words = len(plan.hook.title.split())
    if title_words > nums.hook_title_max_words:
        found.append(
            _v(
                "3.4",
                cards.id,
                f"hook title has {title_words} words, over beats.hook_title_max_words "
                f"{nums.hook_title_max_words}",
            )
        )
    assets = {b.asset_id for b in beats if b.asset_id}
    missing = [i for i in plan.hook.card_asset_ids if i not in assets]
    if missing:
        found.append(_v("3.4", cards.id, f"hook card asset ids {missing} are not plan assets"))
    span = plan.hook.cold_open_span
    for edge, t in (("start", span.start), ("end", span.end)):
        word = _inside(words, t)
        if word is not None:
            found.append(
                _v(
                    "3.4",
                    cold.id,
                    f"cold_open_span {edge} {t:g} s is inside the word {word.text!r} "
                    f"({word.start:g}-{word.end:g} s)",
                )
            )
    if plan.hook.original_position == "keep":
        dropped = any(d.start <= span.start and span.end <= d.end for d in plan.cut.drop)
        if dropped:
            found.append(
                _v(
                    "3.4",
                    cold.id,
                    "hook.original_position is 'keep' but cut.drop removes the cold_open_span",
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
    a warning when nothing is reused. Hook cards are a montage of plan assets and are
    not showings."""
    nums = spec.broll
    found: list[Violation] = []
    warnings: list[str] = []
    unique = {b.asset_id for b in beats if b.asset_id}
    uses = Counter(b.asset_id for b in beats if b.asset_id and b.kind != "hook_cards")
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


def _transitions(beats: Sequence[Beat], spec: StyleSpec) -> list[Violation]:
    """9.4: names inside the style list, `whip_max_per_3_beats`, never two whips in a row."""
    nums = spec.broll
    found: list[Violation] = []
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


def _must_use(
    beats: Sequence[Beat], plan: PicturePlan, must_use: Sequence[str]
) -> list[Violation]:
    """2.3: every reference the brief marks must-use appears in the plan."""
    used = {b.asset_id for b in beats if b.asset_id} | set(plan.hook.card_asset_ids)
    return [
        _v("2.3", None, f"must-use reference {ref!r} is not used by any beat or hook card")
        for ref in must_use
        if ref not in used
    ]


def _hook_wish(plan: PicturePlan, brief: str) -> list[str]:
    """3.4: a title that ignores a numeric hook wish is a warning, never a rejection."""
    match = re.search(r"hook wish:\s*([^.\n]*)", brief, re.IGNORECASE)
    if match is None:
        return []
    wish = match.group(1).strip()
    title = plan.hook.title.lower()
    for number in re.findall(r"\d+", wish):
        if number in title or NUMBER_WORDS.get(number, "\0") in title:
            continue
        return [f"plan (3.4): the hook title ignores the numeric hook wish {wish!r}"]
    return []


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


def validate_sound(
    story: SoundStory, picture: PicturePlan, spec: StyleSpec
) -> SoundCheck | Violations:
    """7.3 / 8.2 / 9.4 on the SoundStory against the (snapped) picture plan."""
    nums = spec.sound
    beats = {b.id: b for b in picture.beats}
    runtime = picture.beats[-1].end if picture.beats else 0.0
    found: list[Violation] = []
    clamps: list[Clamp] = []

    cues: list[Cue] = []
    per_beat: Counter[str] = Counter()
    for cue in story.cues:
        beat = beats.get(cue.beat_id)
        if beat is None:
            found.append(
                _v("8.2", cue.beat_id, f"cue {cue.intent!r} names a beat that is not in the plan")
            )
            continue
        bare = beat.event.kind == "none" and beat.counter is None  # 029: a counter lands
        if cue.at == "event" and bare:
            found.append(
                _v(
                    "9.4",
                    beat.id,
                    f"cue {cue.intent!r} at the event of a beat with no landed event",
                )
            )
        elif cue.at == "start" and bare and beat.enter != "cut":
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
