"""Worked examples: the planner sees how two top shorts edited lines like yours (ticket 077).

Operator decisions (grill, 29 Sep 2026). An example is a v2 card's beat table (073):
said / shows / match / part / layout / effect / sound per shot. Code picks two per job
(`select`): the cards whose `styles` include the job's style, then those on the job's
topic (when that leaves any), then the operator's own Tier B before Tier A, then by
video id so the pick never wobbles. Tone matching is left out of v1.

The topic is picked by code before the planner runs (`pick_topic`): `topic: <name>` in
the brief wins when it names a topic of `assets/reference/topics.yaml`; otherwise the
topics' English and Hindi keywords are counted in the brief and the transcript, the way
the style resolver counts aliases, and the one topic with the most hits wins. A tie or
no hit is style-only (`name` None).

`section` renders the picture prompt's "How top shorts edit a line like yours": both
beat tables and the rule - copy the moves, never the content. A beat whose effect the
card calls `unregistered` shows the closest registered component for the card's own
name of that effect (`assets/reference/effect_map.yaml`), or "(no equivalent: skip)".
The grammar still judges every number, so an example never takes a plan outside its
style.

`plan_match` is the match share of one of our plans, by the rule the reference cards'
`match` column is read with (literal + named entity + number): a beat counts when it
depicts a named entity or its subject is an entity or a number. `compare_plan` and the
comparison table's plan column read it.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from shortsmith import vocab
from shortsmith.contracts import ExampleRow, PicturePlan, Transcript, WorkedExample
from shortsmith.reference import INVENTORY_DIR, REPO_ROOT, UNREGISTERED, ReferenceInventoryV2
from shortsmith.reference import compare as compare_module

EFFECT_MAP_PATH = REPO_ROOT / "assets" / "reference" / "effect_map.yaml"
EXAMPLES_PER_JOB = 2
TIER_ORDER: Mapping[str, int] = {"B": 0, "A": 1}  # the operator's own shorts first
NO_EQUIVALENT = "(no equivalent: skip)"
NO_EXAMPLES = "(no worked examples for this style)"
MATCHED_SUBJECTS = frozenset({"entity", "number"})

_BRIEF_TOPIC = re.compile(r"\btopic\s*:\s*([A-Za-z_]+)", re.IGNORECASE)
# Words split on white space and punctuation, never on a Devanagari vowel sign.
_SPLIT = re.compile(r"[\s.,!?;:\"'()\[\]{}<>/\\|।॥…–—-]+")

TopicSource = Literal["brief", "keywords", "none"]


class EffectMapError(ValueError):
    """`effect_map.yaml` is malformed or names a component the renderer does not have."""


@dataclass(frozen=True)
class TopicPick:
    name: str | None
    source: TopicSource


# --- the topic ------------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    return [w for w in _SPLIT.split(text.lower()) if w]


def pick_topic(brief: str, transcript: Transcript, topics: vocab.Topics) -> TopicPick:
    for found in _BRIEF_TOPIC.finditer(brief):
        name = found.group(1).lower()
        if name in topics.topics:
            return TopicPick(name=name, source="brief")
    words = _words(brief + " " + " ".join(w.text for w in transcript.words))
    scores = {
        name: sum(1 for w in words if w in {*topic.en, *topic.hi})
        for name, topic in topics.topics.items()
        if name != vocab.OTHER_TOPIC
    }
    best = max(scores.values(), default=0)
    winners = [name for name, score in scores.items() if score == best]
    if best == 0 or len(winners) != 1:
        return TopicPick(name=None, source="none")
    return TopicPick(name=winners[0], source="keywords")


# --- the two cards --------------------------------------------------------------------------


def select(
    cards: Sequence[ReferenceInventoryV2],
    *,
    style: str,
    topic: str | None,
    n: int = EXAMPLES_PER_JOB,
) -> list[ReferenceInventoryV2]:
    pool = [c for c in cards if c.tier != "own" and style in c.styles]
    if topic is not None:
        on_topic = [c for c in pool if c.script.topic == topic]
        pool = on_topic or pool
    return sorted(pool, key=lambda c: (TIER_ORDER.get(c.tier, len(TIER_ORDER)), c.video_id))[:n]


def load_effect_map(
    path: Path = EFFECT_MAP_PATH, *, registry: Collection[str] | None = None
) -> dict[str, str | None]:
    if registry is None:
        from shortsmith import render  # the renderer's registry; imported late, it is heavy

        registry = render.registry()
    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    effects: object = (
        cast(dict[str, object], loaded).get("effects") if isinstance(loaded, dict) else None
    )
    if not isinstance(effects, dict):
        raise EffectMapError(f"{path.name}: no `effects` mapping")
    mapping: dict[str, str | None] = {}
    for name, target in cast(dict[object, object], effects).items():
        if not isinstance(name, str) or not (target is None or isinstance(target, str)):
            raise EffectMapError(f"{path.name}: {name!r}: {target!r} is not a component or null")
        if target is not None and target not in registry:
            raise EffectMapError(
                f"{path.name}: {name} -> {target}: {target!r} is not a registered component"
            )
        mapping[name] = target
    return mapping


def _effect(card: ReferenceInventoryV2, start: float, end: float, effect: str | None,
            effect_map: Mapping[str, str | None]) -> str:  # fmt: skip
    if effect is None:
        return ""
    if effect != UNREGISTERED:
        return effect
    named = sorted(
        (item.at_s, item.name)
        for item in [*card.effects, *card.transitions]
        if item.component == UNREGISTERED and start <= item.at_s < end
    )
    target = effect_map.get(named[0][1]) if named else None
    return f"{target} (closest to {named[0][1]})" if target is not None else NO_EQUIVALENT


def worked(card: ReferenceInventoryV2, effect_map: Mapping[str, str | None]) -> WorkedExample:
    return WorkedExample(
        video_id=card.video_id, tier=card.tier, topic=card.script.topic, tone=card.script.tone,
        rows=[
            ExampleRow(
                start_s=b.start_s, end_s=b.end_s, said=b.said, shows=b.shows, match=b.match,
                part=b.part, layout=b.layout,
                effect=_effect(card, b.start_s, b.end_s, b.effect, effect_map),
                sound=b.sound or "",
            )
            for b in card.beats
        ],
    )  # fmt: skip


def for_job(
    brief: str,
    transcript: Transcript,
    style: str,
    inventory_dir: Path = INVENTORY_DIR,
    *,
    topics: vocab.Topics | None = None,
) -> tuple[TopicPick, list[WorkedExample]]:
    """The job's topic and its two worked examples from the v2 cards in `inventory_dir`."""
    picked = pick_topic(brief, transcript, topics if topics is not None else vocab.load_topics())
    cards = select(compare_module.references_for(style, inventory_dir), style=style,
                   topic=picked.name)  # fmt: skip
    if not cards:
        return picked, []
    effect_map = load_effect_map()
    return picked, [worked(card, effect_map) for card in cards]


# --- the prompt section ---------------------------------------------------------------------

SECTION_HEAD = (
    "Top shorts of this style show, shot by shot, how a spoken line became a picture, an "
    "effect and a sound: what was said (a gist), what the picture showed, how the two "
    "matched, the story part, the layout, the effect and the sound. Copy the moves - what "
    "kind of picture goes with what kind of line, where effects and sounds land, how the "
    "parts are paced - never the content: no names, facts or pictures from an example; "
    "every picture comes from this transcript. An effect in these tables is the closest one "
    "you may use, or \"(no equivalent: skip)\". Every count still comes from section 1; an "
    "example never outranks a number."
)
_TABLE_HEAD = (
    "| time (s) | part | said | shows | match | layout | effect | sound |\n"
    "|---|---|---|---|---|---|---|---|"
)


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip() or "-"


def section(examples: Sequence[WorkedExample]) -> str:
    if not examples:
        return NO_EXAMPLES
    blocks = [SECTION_HEAD]
    for i, example in enumerate(examples, start=1):
        tone = f", tone {example.tone}" if example.tone else ""
        rows = "\n".join(
            f"| {r.start_s:.1f}-{r.end_s:.1f} | {_cell(r.part)} | {_cell(r.said)} | "
            f"{_cell(r.shows)} | {_cell(r.match)} | {_cell(r.layout)} | {_cell(r.effect)} | "
            f"{_cell(r.sound)} |"
            for r in example.rows
        )
        blocks.append(
            f"### Example {i}: {example.video_id} (Tier {example.tier}, topic "
            f"{example.topic}{tone})\n\n{_TABLE_HEAD}\n{rows}"
        )
    return "\n\n".join(blocks)


# --- our plan's match share -----------------------------------------------------------------


def plan_match(plan: PicturePlan) -> tuple[int, int]:
    """(beats that match what is said, all beats): a named entity depicted, or an entity
    or a number as the subject."""
    matched = sum(
        1
        for b in plan.beats
        if b.depicts == "named_entity" or b.subject_kind in MATCHED_SUBJECTS
    )
    return matched, len(plan.beats)


def match_share(plan: PicturePlan) -> float | None:
    matched, total = plan_match(plan)
    return matched / total if total else None
