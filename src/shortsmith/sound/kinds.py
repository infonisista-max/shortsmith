"""What each audio kind must be (ticket 068; decision 7.2 as amended at run04 QA).

Run04 went out with a car exhaust and an a-cappella chant catalogued as beds and a
beeping score counter as a cue: the search adopted its first hit and tagged it with the
words it was searched with. `assets/audio/kinds.yaml` now says, per kind, the words a
sound's own name or tags must carry (`needs`, at least one) and may not (`forbids`,
none); every SFX kind also forbids the file's `sfx_forbids` (no rings, bells or chimes).
The Freesound adapter and the fake search ask `refusal` before a hit is adopted, and
`seed retag` asks it of every fetched entry.

Words are single lower-case tokens. A sound's name and tags are split into tokens the
same way (`buick regal gs_magnaflow.mp3` is buick, regal, gs, magnaflow, mp3), and a
token matches a word as written or with a plural `s` / `es`. An SFX intent the file does
not name (a planner's own `date_stamp`) needs its own words and carries the SFX
forbidden list, until 070 closes the palette. The file is loaded at startup; a kind with
no `needs`, a word in both lists, or no `bed` is a `KindError` naming it.

This module imports nothing from the rest of `shortsmith.sound`, so the package's
`__init__` can import it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

KINDS_PATH = Path(__file__).resolve().parents[3] / "assets" / "audio" / "kinds.yaml"
BED = "bed"
_TOKEN = re.compile(r"[a-z0-9]+")
_PLURALS = ("", "s", "es")


class KindError(ValueError):
    """`kinds.yaml` is malformed: the message names the file, the kind and the word."""


def tokens(text: str) -> list[str]:
    """The lower-case word tokens of `text`, in order."""
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Kind:
    name: str
    needs: tuple[str, ...]
    forbids: tuple[str, ...] = ()


def _hits(words: Iterable[str], found: Sequence[str]) -> list[str]:
    """The tokens of `found` that match one of `words`, each once, in `found`'s order."""
    wanted = {w + p for w in words for p in _PLURALS}
    out: list[str] = []
    for token in found:
        if token in wanted and token not in out:
            out.append(token)
    return out


def refusal(kind: Kind, name: str, tags: Sequence[str]) -> str | None:
    """Why a sound called `name` with `tags` is not a `kind`, or None when it is: a
    forbidden word is named first, then the absence of any needed word."""
    found = [t for text in (name, *tags) for t in tokens(text)]
    bad = _hits(kind.forbids, found)
    if bad:
        return f"name/tags carry {', '.join(bad)!r}, forbidden for {kind.name}"
    if not _hits(kind.needs, found):
        shown = ", ".join(tags) if tags else name
        return f"name/tags {shown!r} carry no {kind.name} word"
    return None


@dataclass(frozen=True)
class Kinds:
    kinds: Mapping[str, Kind]
    sfx_forbids: tuple[str, ...] = ()

    def kind(self, name: str) -> Kind:
        return self.kinds[name]

    def sfx_kinds(self) -> tuple[str, ...]:
        return tuple(k for k in self.kinds if k != BED)

    def for_sfx(self, intent: str) -> Kind:
        """The kind a cue fetched for `intent` is checked against: the file's own row with
        the SFX forbidden list added, or - for an intent the file does not name - the
        intent's own words as `needs`."""
        own = self.kinds.get(intent) if intent != BED else None
        needs = own.needs if own is not None else tuple(dict.fromkeys(tokens(intent)))
        forbids = own.forbids if own is not None else ()
        return Kind(intent, needs, tuple(dict.fromkeys((*forbids, *self.sfx_forbids))))


def _words(value: object, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise KindError(f"{where} is not a list of words")
    out: list[str] = []
    for word in cast(list[object], value):
        if not isinstance(word, str) or _TOKEN.fullmatch(word) is None:
            raise KindError(f"{where}: {word!r} is not one lower-case word")
        if word in out:
            raise KindError(f"{where}: {word!r} is listed twice")
        out.append(word)
    return tuple(out)


def parse_kinds(text: str, *, name: str) -> Kinds:
    loaded: object = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise KindError(f"{name}: not a mapping with `kinds`")
    data = cast(dict[str, Any], loaded)
    unknown = set(data) - {"kinds", "sfx_forbids"}
    if unknown:
        raise KindError(f"{name}: unknown key(s) {', '.join(sorted(unknown))}")
    shared = _words(data.get("sfx_forbids"), f"{name}: sfx_forbids")
    rows: object = data.get("kinds")
    if not isinstance(rows, dict) or not rows:
        raise KindError(f"{name}: `kinds` is not a mapping of kinds")
    parsed: dict[str, Kind] = {}
    for kind_name, row in cast(dict[object, object], rows).items():
        where = f"{name}: kind {kind_name!r}"
        if not isinstance(kind_name, str) or not isinstance(row, dict):
            raise KindError(f"{where} is not a mapping with `needs`")
        fields = cast(dict[str, object], row)
        if set(fields) - {"needs", "forbids"}:
            raise KindError(f"{where}: only `needs` and `forbids` are allowed")
        needs = _words(fields.get("needs"), f"{where} needs")
        forbids = _words(fields.get("forbids"), f"{where} forbids")
        if not needs:
            raise KindError(f"{where} has no required words (`needs`)")
        lists = [("forbids", forbids)] + ([("sfx_forbids", shared)] if kind_name != BED else [])
        for label, against in lists:
            both = [w for w in needs if w in against]
            if both:
                raise KindError(f"{where}: {', '.join(both)!r} is in both needs and {label}")
        parsed[kind_name] = Kind(kind_name, needs, forbids)
    if BED not in parsed:
        raise KindError(f"{name}: no 'bed' kind")
    return Kinds(kinds=parsed, sfx_forbids=shared)


def load_kinds(path: Path = KINDS_PATH) -> Kinds:
    """`kinds.yaml`, validated; a missing file is a `KindError` - the check is not
    optional (068)."""
    if not path.is_file():
        raise KindError(f"{path.name}: not found at {path}")
    return parse_kinds(path.read_text(encoding="utf-8"), name=path.name)
