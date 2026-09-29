"""The gap report (ticket 036): what the references do that the renderer cannot draw.

`report(inventories)` renders `GAPS.md` from every `ReferenceInventory`: the
unregistered effects and the unregistered transitions ranked by how many references
use them (grouped by the model's own `name` for the technique), each with up to
`EXAMPLES` links to the moment (`&t=<s>s`) so the operator can watch them; the off-list
words the cards stored as `other` with their counts (092, only when there are any); then one
table per `<category> / Tier <tier>` - Tier A, Tier B and facts are never pooled (10.3)
- with each reference's share of runtime by layout and by background (moving footage
split by kind), median clip length, shots per 10 s and sound effects per 10 s. Every
figure is ESTIMATED, as the inventories are. `write(folder)` reads every `*.json` in the
inventory folder and writes the report beside them.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import median

from pydantic import ValidationError

from shortsmith.reference import (
    UNREGISTERED,
    Effect,
    ReferenceInventory,
    Transition,
    load_card,
)

REPORT_NAME = "GAPS.md"
EXAMPLES = 3
WATCH_AT = "https://www.youtube.com/watch?v={id}&t={s}s"
_ROW_NUMBER = re.compile(r"\.\d+(?=\.|$)")


def load_all(folder: Path) -> list[ReferenceInventory]:
    """Every inventory JSON in the folder, v1 or v2 (073), by video id; a file that is
    not one is skipped."""
    found: list[ReferenceInventory] = []
    for path in sorted(folder.glob("*.json")):
        try:
            found.append(load_card(path.read_text(encoding="utf-8")))
        except (ValidationError, ValueError):
            continue
    return found


def write(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / REPORT_NAME
    path.write_text(report(load_all(folder)), encoding="utf-8")
    return path


def report(inventories: Sequence[ReferenceInventory]) -> str:
    lines = [
        "# Gaps - what the references do that the renderer cannot draw yet",
        "",
        f"Written by `python -m shortsmith.reference gaps` from {len(inventories)} "
        f"inventories under `docs/reference/inventory/`. Every figure is ESTIMATED: "
        "model-observed on frames sampled from the YouTube link, timestamps approximate. "
        "Tier A, Tier B and facts are separate tables, never pooled (decision 10.3).",
        "",
    ]
    if not inventories:
        lines += ["There are no inventories yet: run `inventory <url>` first.", ""]
        return "\n".join(lines)
    lines += _unregistered("Unregistered effects", inventories, "effects")
    lines += _unregistered("Unregistered transitions", inventories, "transitions")
    lines += _off_list(inventories)
    groups: dict[tuple[str, str], list[ReferenceInventory]] = defaultdict(list)
    for made in inventories:
        groups[(made.category, made.tier)].append(made)
    for (category, tier), members in sorted(groups.items()):
        lines += _group_table(f"{category} / Tier {tier}", members)
    return "\n".join(lines)


def _unregistered(
    heading: str, inventories: Iterable[ReferenceInventory], attribute: str
) -> list[str]:
    users: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, list[tuple[str, float]]] = defaultdict(list)
    described: dict[str, str] = {}
    for made in inventories:
        listed: Sequence[Effect | Transition] = getattr(made, attribute)
        for item in listed:
            if item.component != UNREGISTERED:
                continue
            key = item.name.strip().lower().replace(" ", "_") or "unnamed"
            users[key].add(made.video_id)
            if len([e for e in examples[key] if e[0] == made.video_id]) < 1:
                examples[key].append((made.video_id, item.at_s))
            described.setdefault(key, item.description)
    lines = [f"## {heading}", ""]
    if not users:
        lines += ["None: every one the references use has a registered component.", ""]
        return lines
    lines += ["| name | references | examples | what it looks like |", "| --- | --- | --- | --- |"]
    ranked = sorted(users.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for key, videos in ranked:
        links = ", ".join(
            f"[{vid} {int(at)}s]({WATCH_AT.format(id=vid, s=int(at))})"
            for vid, at in examples[key][:EXAMPLES]
        )
        lines.append(f"| `{key}` | {len(videos)} | {links} | {described[key]} |")
    lines.append("")
    return lines


def _off_list(inventories: Iterable[ReferenceInventory]) -> list[str]:
    """092: the words the model gave off a closed list (stored as `other`), by field with
    the row numbers as `N`, ranked by how often they were said. No section when none."""
    times: Counter[tuple[str, str]] = Counter()
    users: dict[tuple[str, str], set[str]] = defaultdict(set)
    for made in inventories:
        for row in made.off_list:
            key = (_ROW_NUMBER.sub(".N", row.field), row.said.strip().lower())
            times[key] += 1
            users[key].add(made.video_id)
    if not times:
        return []
    lines = [
        "## Off-list labels",
        "",
        "Words the model gave off a closed list; each card stores them as `other`. "
        "Growing a list is the operator's decision (083).",
        "",
        "| field | word | times | references |",
        "| --- | --- | --- | --- |",
    ]
    for (field, word), n in sorted(times.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{field}` | `{word}` | {n} | {len(users[(field, word)])} |")
    lines.append("")
    return lines


def _group_table(heading: str, members: Sequence[ReferenceInventory]) -> list[str]:
    lines = [
        f"## {heading}",
        "",
        "| video | creator | s | shots/10 s | effects/10 s | sfx/10 s | median clip s | "
        "layout share | background share |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for made in sorted(members, key=lambda m: m.video_id):
        clips = [s.clip_s for s in made.shots if s.clip_s is not None and s.clip_s > 0]
        median_clip = f"{median(clips):.1f}" if clips else "-"
        lines.append(
            f"| [{made.video_id}]({made.url}) | {made.creator or '-'} | {made.duration_s:.0f} | "
            f"{made.counts.shots_per_10s} | {made.counts.effects_per_10s} | "
            f"{made.counts.sfx_per_10s} | {median_clip} | {_layout_share(made)} | "
            f"{_background_share(made)} |"
        )
    lines.append("")
    return lines


def _shares(weights: dict[str, float], total: float) -> list[tuple[str, int]]:
    return sorted(
        ((name, round(100 * w / total)) for name, w in weights.items() if w > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )


def _layout_share(made: ReferenceInventory) -> str:
    total = sum(s.length_s for s in made.shots) or made.duration_s
    weights: defaultdict[str, float] = defaultdict(float)
    for shot in made.shots:
        weights[shot.layout] += shot.length_s
    return ", ".join(f"{name} {pct}%" for name, pct in _shares(weights, total)) or "-"


def _background_share(made: ReferenceInventory) -> str:
    total = sum(s.length_s for s in made.shots) or made.duration_s
    weights: defaultdict[str, float] = defaultdict(float)
    kinds: defaultdict[str, float] = defaultdict(float)
    for shot in made.shots:
        weights[shot.background] += shot.length_s
        if shot.background == "moving_footage":
            kinds[shot.footage_kind or "unknown"] += shot.length_s
    parts: list[str] = []
    for name, pct in _shares(weights, total):
        part = f"{name} {pct}%"
        if name == "moving_footage" and kinds:
            split = ", ".join(f"{k} {p}%" for k, p in _shares(kinds, total))
            part += f" ({split})"
        parts.append(part)
    return ", ".join(parts) or "-"
