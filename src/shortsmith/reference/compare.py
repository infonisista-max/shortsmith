"""Our card against the references, by numbers (ticket 074).

`compare(ours, cards, style=...)` sets each number of our own v2 card (`tier: own`,
written by the `inventory` step, `reference.own`) beside the median and the range
(min-max) of the reference v2 cards whose `styles` include the job's style
(`references_for`: v1 cards and other styles are skipped). A number outside the range
is `outside` - red on the job page. Fewer than `MIN_REFERENCES` cards is "not enough
references": our numbers are shown with no range and nothing is red.

The rows: shots, effects and SFX (by kind) per 10 s, the median clip length, the share
of SFX on a visible event, the layout share of the references' top three layouts (ours
when there is no reference), the bed, the mood per story part against the plan's moods
(076 fills the plan's side; until then "—"), the music change and its `how`, and the
match share (literal + named entity + number, as a share of beats; 077 reads it). Every
figure is computed from the cards' lists, never from the rounded `counts`.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from shortsmith.contracts import ComparisonRow, InventoryComparison
from shortsmith.reference import (
    INVENTORY_DIR,
    Layout,
    ReferenceInventory,
    ReferenceInventoryV2,
    SfxKind,
    StoryPart,
    load_card,
    v2_cards,
)

log = logging.getLogger(__name__)

MIN_REFERENCES = 2
NOT_ENOUGH = "not enough references"
NO_PLAN = "—"  # 076 fills the plan's moods
TOP_LAYOUTS = 3
MATCHED = frozenset({"literal", "named_entity", "number"})
INVISIBLE_EVENT = "other"  # every other `SfxEvent` is something seen on screen
DIGITS = 2

Measure = Callable[[ReferenceInventoryV2], float | None]


def references_for(style: str, inventory_dir: Path = INVENTORY_DIR) -> list[ReferenceInventoryV2]:
    """The reference v2 cards in `inventory_dir` whose `styles` include `style`; a v1
    card is skipped with a log line, a file that is not a card with a warning."""
    cards: list[ReferenceInventory] = []
    for path in sorted(inventory_dir.glob("*.json")) if inventory_dir.is_dir() else []:
        try:
            cards.append(load_card(path.read_text(encoding="utf-8")))
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            log.warning("%s is not a reference card: %s", path.name, exc)
    return [
        card
        for card in v2_cards(cards, log=log.debug)
        if card.tier != "own" and style in card.styles
    ]


def compare(
    ours: ReferenceInventoryV2,
    cards: Sequence[ReferenceInventoryV2],
    *,
    style: str,
    plan_moods: Mapping[str, str] | None = None,
) -> InventoryComparison:
    enough = len(cards) >= MIN_REFERENCES
    kinds = [k for k in get_args(SfxKind) if any(_sfx_count(c, k) for c in [ours, *cards])]
    numbers: list[tuple[str, Measure]] = [
        ("shots per 10 s", lambda c: _per_10s(c, len(c.shots))),
        ("effects per 10 s", lambda c: _per_10s(c, len(c.effects))),
        ("median clip length (s)", _median_clip),
        *[(f"SFX per 10 s: {k}", _sfx_rate(k)) for k in kinds],
        ("SFX on a visible event (share)", _visible_share),
        *[(f"layout share: {name}", _layout_share(name)) for name in _top_layouts(ours, cards)],
        ("match share (literal + named entity + number)", _match_share),
    ]
    rows = [_number_row(name, measure, ours, cards, enough) for name, measure in numbers]
    rows.append(_bed_row(ours, cards))
    rows += [_mood_row(part, ours, cards, plan_moods) for part in get_args(StoryPart)]
    rows.append(_change_row(ours, cards))
    return InventoryComparison(
        style=style, references=len(cards), enough=enough,
        note="" if enough else NOT_ENOUGH, rows=rows,
    )  # fmt: skip


# --- the number rows ---------------------------------------------------------------------


def _number_row(
    name: str,
    measure: Measure,
    ours: ReferenceInventoryV2,
    cards: Sequence[ReferenceInventoryV2],
    enough: bool,
) -> ComparisonRow:
    value = _round(measure(ours))
    theirs = [v for v in (measure(c) for c in cards) if v is not None]
    if not enough or not theirs:
        return ComparisonRow(name=name, ours=value)
    low, high = _round(min(theirs)), _round(max(theirs))
    assert low is not None and high is not None
    return ComparisonRow(
        name=name, ours=value, median=_round(statistics.median(theirs)), low=low, high=high,
        outside=value is not None and not low <= value <= high,
    )  # fmt: skip


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, DIGITS)


def _per_10s(card: ReferenceInventoryV2, count: int) -> float:
    return count * 10.0 / card.duration_s


def _median_clip(card: ReferenceInventoryV2) -> float | None:
    lengths = [s.length_s for s in card.shots]
    return statistics.median(lengths) if lengths else None


def _sfx_count(card: ReferenceInventoryV2, kind: str) -> int:
    return sum(1 for e in card.sound.effects if e.kind == kind)


def _sfx_rate(kind: str) -> Measure:
    return lambda card: _per_10s(card, _sfx_count(card, kind))


def _visible_share(card: ReferenceInventoryV2) -> float | None:
    effects = card.sound.effects
    if not effects:
        return None
    return sum(1 for e in effects if e.event != INVISIBLE_EVENT) / len(effects)


def _layout_share(layout: str) -> Callable[[ReferenceInventoryV2], float]:
    """The layout's share of the card's shot time."""

    def share(card: ReferenceInventoryV2) -> float:
        total = sum(s.length_s for s in card.shots)
        on = sum(s.length_s for s in card.shots if s.layout == layout)
        return on / total if total > 0 else 0.0

    return share


def _top_layouts(
    ours: ReferenceInventoryV2, cards: Sequence[ReferenceInventoryV2]
) -> list[str]:
    """The references' three layouts with the most screen time (summed over their shares,
    so every card weighs the same), or ours when there is no reference; ties in the
    `Layout` order."""
    pooled: dict[str, float] = dict.fromkeys(get_args(Layout), 0.0)
    for card in cards or [ours]:
        for layout in get_args(Layout):
            pooled[layout] += _layout_share(layout)(card)
    ranked = sorted(get_args(Layout), key=lambda name: -pooled[name])
    return [name for name in ranked if pooled[name] > 0][:TOP_LAYOUTS]


def _match_share(card: ReferenceInventoryV2) -> float | None:
    if not card.beats:
        return None
    return sum(1 for b in card.beats if b.match in MATCHED) / len(card.beats)


# --- the rows that are not numbers -------------------------------------------------------


def _tally(values: Sequence[str]) -> str:
    return ", ".join(f"{value} {n}" for value, n in Counter(values).most_common())


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _bed_row(ours: ReferenceInventoryV2, cards: Sequence[ReferenceInventoryV2]) -> ComparisonRow:
    beds = sum(1 for c in cards if c.sound.bed)
    refs = f"yes in {beds} of {len(cards)}" if cards else ""
    return ComparisonRow(name="bed present", ours=_yes(ours.sound.bed), refs=refs)


def _mood_of(card: ReferenceInventoryV2, part: str) -> str | None:
    for found in card.parts:
        if found.part == part:
            mood = found.music_mood or "no music"
            return f"{mood} ({found.music_flavour})" if found.music_flavour else mood
    return None


def _mood_row(
    part: str,
    ours: ReferenceInventoryV2,
    cards: Sequence[ReferenceInventoryV2],
    plan_moods: Mapping[str, str] | None,
) -> ComparisonRow:
    theirs = [m for m in (_mood_of(c, part) for c in cards) if m is not None]
    return ComparisonRow(
        name=f"mood: {part}", ours=_mood_of(ours, part), refs=_tally(theirs),
        plan=(plan_moods or {}).get(part, NO_PLAN),
    )  # fmt: skip


def _change(card: ReferenceInventoryV2) -> str:
    if not card.music_changes:
        return "no"
    return f"yes ({', '.join(c.how for c in card.music_changes)})"


def _change_row(ours: ReferenceInventoryV2, cards: Sequence[ReferenceInventoryV2]) -> ComparisonRow:
    changed = [c for c in cards if c.music_changes]
    hows = [m.how for c in changed for m in c.music_changes]
    refs = f"yes in {len(changed)} of {len(cards)}" if cards else ""
    if hows:
        refs += f" ({_tally(hows)})"
    return ComparisonRow(name="music change", ours=_change(ours), refs=refs)
