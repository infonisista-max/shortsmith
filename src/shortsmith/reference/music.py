"""Music in top shorts: the pairings the sound call learns from (ticket 076).

Operator decisions (grill, 29 Sep 2026). The planner picks the mood (and an optional
flavour) for each story part of this script from the closed list of
`assets/audio/moods.yaml`, never in free words, and learns it from the v2 cards' pairings
of script, tone, story parts and music (073). `for_job` reads every reference v2 card
(never our own, tier `own`) - music follows the topic, place, period and tone, not the
editing style - Tier B first, then by video id. `pairing` renders one card as one line:
its topic and tone, the mood per part, and each music change with its `how`. `section`
is the sound prompt's "Music in top shorts": the active moods and flavours with their
meanings, the pairing lines, and the rule to pick for this script.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from shortsmith import vocab
from shortsmith.reference import INVENTORY_DIR, ReferenceInventoryV2
from shortsmith.reference import compare as compare_module

TIER_ORDER = {"B": 0, "A": 1}  # the operator's own shorts first, as 077 orders them
NO_PAIRINGS = "(no v2 reference card yet: pick from the moods alone)"
SECTION_HEAD = (
    "Top shorts scored each story part with one mood of the list below. Pick the mood (and "
    "a flavour only where the place calls for one) for each part of this script by its "
    "topic, place, period and tone, the way these pairings do; never a word outside the "
    "list. At most `sound.bed_changes_max` change per short, only where a story part "
    "starts, and how it sounds (crossfade, hard_cut, drop_to_silence) as the pairings show "
    "for that part boundary."
)


def _mood(card: ReferenceInventoryV2, part: str) -> str:
    found = next((p for p in card.parts if p.part == part), None)
    if found is None:
        return ""
    mood = found.music_mood or "no music"
    return f"{part} {mood} ({found.music_flavour})" if found.music_flavour else f"{part} {mood}"


def pairing(card: ReferenceInventoryV2) -> str:
    moods = ", ".join(m for m in (_mood(card, p.part) for p in card.parts) if m)
    changes = (
        "changes: " + ", ".join(f"{c.from_part} -> {c.to_part} {c.how}" for c in card.music_changes)
        if card.music_changes
        else "no change"
    )
    return (
        f"- {card.video_id} (Tier {card.tier}; topic {card.script.topic}; tone "
        f"{card.script.tone}): {moods}; {changes}"
    )


def for_job(inventory_dir: Path = INVENTORY_DIR) -> list[str]:
    cards = compare_module.all_references(inventory_dir)
    ordered = sorted(cards, key=lambda c: (TIER_ORDER.get(c.tier, len(TIER_ORDER)), c.video_id))
    return [pairing(card) for card in ordered]


def _listed(entries: Sequence[vocab.Entry]) -> str:
    return "\n".join(f"  - `{e.name}`: {e.meaning}" for e in entries)


def section(lines: Sequence[str], moods: vocab.Moods | None = None) -> str:
    moods = moods if moods is not None else vocab.load_moods()
    active = [moods.moods[name] for name in moods.active_moods()]
    flavours = [moods.flavours[name] for name in moods.active_flavours()]
    pairings = "\n".join(lines) if lines else NO_PAIRINGS
    return (
        f"{SECTION_HEAD}\n\n"
        f"Moods:\n{_listed(active)}\n\nFlavours:\n{_listed(flavours)}\n\n"
        f"Pairings:\n{pairings}"
    )
