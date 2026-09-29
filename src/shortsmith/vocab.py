"""The closed vocabularies (ticket 073): bed moods, regional flavours and topics.

The reference card v2 (`shortsmith.reference`), the planner and the sound director share
one list of each, kept as data, never in code:

- `assets/audio/moods.yaml`: `moods` and `flavours`, each entry a one-line `meaning` and
  `active: true` for the first batch the approved library carries (075).
- `assets/reference/topics.yaml`: `topics`, each with a `meaning` and `en` / `hi`
  keywords (single lower-case words; Hindi in Devanagari and romanised) that 077 counts.
  `other` is the fallback and must be there; it alone carries no keywords.

Both load at app startup and when the reference tool builds its prompt. A duplicate
entry (YAML would silently keep the last one), an entry with no meaning, a topic with no
keywords in either language, or a keyword listed twice is a `VocabError` naming it.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

ASSETS = Path(__file__).resolve().parents[2] / "assets"
MOODS_PATH = ASSETS / "audio" / "moods.yaml"
TOPICS_PATH = ASSETS / "reference" / "topics.yaml"
OTHER_TOPIC = "other"


class VocabError(ValueError):
    """A vocabulary file is malformed: the message names the file and the entry."""


@dataclass(frozen=True)
class Entry:
    name: str
    meaning: str
    active: bool = False


@dataclass(frozen=True)
class Moods:
    moods: Mapping[str, Entry]
    flavours: Mapping[str, Entry]

    def active_moods(self) -> tuple[str, ...]:
        return tuple(name for name, entry in self.moods.items() if entry.active)

    def active_flavours(self) -> tuple[str, ...]:
        return tuple(name for name, entry in self.flavours.items() if entry.active)


@dataclass(frozen=True)
class Topic:
    name: str
    meaning: str
    en: tuple[str, ...] = ()
    hi: tuple[str, ...] = ()


@dataclass(frozen=True)
class Topics:
    topics: Mapping[str, Topic]


@dataclass(frozen=True)
class Vocabulary:
    """Both files, as one reader of the closed lists takes them."""

    moods: Moods
    topics: Topics


def load(moods_path: Path = MOODS_PATH, topics_path: Path = TOPICS_PATH) -> Vocabulary:
    return Vocabulary(load_moods(moods_path), load_topics(topics_path))


# --- YAML that refuses a key given twice ------------------------------------------------


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Hashable, Any]:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = cast(object, loader.construct_object(key_node))  # pyright: ignore[reportUnknownMemberType]
        if key in seen:
            raise VocabError(f"{key!r} is listed twice")
        seen.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _unique_mapping,  # pyright: ignore[reportArgumentType]
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise VocabError(f"{path.name}: not found at {path}")
    try:
        loaded: object = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except VocabError as exc:
        raise VocabError(f"{path.name}: {exc}") from None
    if not isinstance(loaded, dict):
        raise VocabError(f"{path.name}: not a mapping")
    return cast(dict[str, Any], loaded)


def _rows(data: Mapping[str, Any], group: str, where: str) -> dict[str, dict[str, object]]:
    rows: object = data.get(group)
    if not isinstance(rows, dict) or not rows:
        raise VocabError(f"{where}: `{group}` is empty or not a mapping of entries")
    out: dict[str, dict[str, object]] = {}
    for name, row in cast(dict[object, object], rows).items():
        if not isinstance(name, str) or not name:
            raise VocabError(f"{where}: {group} entry {name!r} is not a name")
        if not isinstance(row, dict) or not row:
            raise VocabError(f"{where}: {group} entry {name!r} is empty")
        out[name] = cast(dict[str, object], row)
    return out


def _meaning(row: Mapping[str, object], where: str) -> str:
    meaning = row.get("meaning")
    if not isinstance(meaning, str) or not meaning.strip():
        raise VocabError(f"{where} has no `meaning`")
    return meaning.strip()


def _entries(data: Mapping[str, Any], group: str, file: str) -> dict[str, Entry]:
    entries: dict[str, Entry] = {}
    for name, row in _rows(data, group, file).items():
        where = f"{file}: {group} entry {name!r}"
        if set(row) - {"meaning", "active"}:
            raise VocabError(f"{where}: only `meaning` and `active` are allowed")
        active = row.get("active", False)
        if not isinstance(active, bool):
            raise VocabError(f"{where}: `active` is not true or false")
        entries[name] = Entry(name, _meaning(row, where), active)
    return entries


def _keywords(value: object, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise VocabError(f"{where} is not a list of words")
    out: list[str] = []
    for word in cast(list[object], value):
        if not isinstance(word, str) or not word or word != word.lower() or word.split() != [word]:
            raise VocabError(f"{where}: {word!r} is not one lower-case word")
        if word in out:
            raise VocabError(f"{where}: {word!r} is listed twice")
        out.append(word)
    return tuple(out)


def load_moods(path: Path = MOODS_PATH) -> Moods:
    data = _load(path)
    unknown = set(data) - {"moods", "flavours"}
    if unknown:
        raise VocabError(f"{path.name}: unknown key(s) {', '.join(sorted(unknown))}")
    return Moods(_entries(data, "moods", path.name), _entries(data, "flavours", path.name))


def load_topics(path: Path = TOPICS_PATH) -> Topics:
    data = _load(path)
    unknown = set(data) - {"topics"}
    if unknown:
        raise VocabError(f"{path.name}: unknown key(s) {', '.join(sorted(unknown))}")
    topics: dict[str, Topic] = {}
    for name, row in _rows(data, "topics", path.name).items():
        where = f"{path.name}: topic {name!r}"
        if set(row) - {"meaning", "en", "hi"}:
            raise VocabError(f"{where}: only `meaning`, `en` and `hi` are allowed")
        en = _keywords(row.get("en"), f"{where} en")
        hi = _keywords(row.get("hi"), f"{where} hi")
        if name != OTHER_TOPIC and not (en and hi):
            raise VocabError(f"{where} needs English (`en`) and Hindi (`hi`) keywords")
        topics[name] = Topic(name, _meaning(row, where), en, hi)
    if OTHER_TOPIC not in topics:
        raise VocabError(f"{path.name}: no {OTHER_TOPIC!r} topic (the fallback)")
    return Topics(topics)
