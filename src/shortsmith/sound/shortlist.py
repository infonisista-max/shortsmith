"""The audio shortlist and the approved library (ticket 075; operator grill, 29 Sep 2026).

    python -m shortsmith.sound.shortlist [--slot NAME ...] [--voice PATH]
    python -m shortsmith.sound.shortlist probe
    python -m shortsmith.sound.shortlist fetch-approved

Run04 went out with no audible music and a "phone ring", because every sound was the
first Freesound hit at job time. Now jobs take sounds from a library the operator has
heard: this tool shortlists `keep` candidates per slot (`assets/audio/shortlist.yaml`:
the active moods and flavours of `moods.yaml`, and the effect kinds), and the operator
says yes or no on `/audio/shortlist`.

**Sources.** Two APIs, asked one rung at a time: Openverse audio (`/v1/audio/`, no key,
`license=cc0,by`, `category=music` for a bed and `sound_effect` for an effect; the main
source for beds, so it is asked first for a bed) and Freesound (`sound.freesound`, with
`FREESOUND_API_KEY`; asked first for an effect). A bed rung carries the `anchor` word
("music"); an effect rung asks Freesound with `duration:[0 TO max_len_s]`. Four sources
have no API (Pixabay music, the YouTube Audio Library, Mixkit, Incompetech): the operator
drops their files into `assets/audio/inbox/`, the tool writes a one-line sidecar
`<file>.source.yaml` beside each (`source`, `page_url`, `attribution`, `slot`), and a
file whose sidecar is filled joins its slot's page with the licence text of its source's
committed template (`assets/audio/licences/<source>.txt`, first line). An unfilled one is
listed as "needs source" and cannot be approved.

**Checks, in order; the first that fails costs the candidate one log line.** A no the
operator gave (`refused.yaml`) or a file already in the catalogue; the licence (CC0 or
CC BY only; a drop-folder file carries its source's); 068's kind check on the source's
own name and tags (a drop-folder file: the forbidden words only, since a file name
rarely says "music"); an effect's reported length against `max_len_s` - all before any
download. Then the 023 measure (an effect's measured length against `max_len_s` again),
the sweep detector on every effect but a whoosh (a whoosh is a noise sweep by nature;
060 exempts it within its length), and 069's audibility on every bed: the bed levelled
`bed_db_under_voice` under a reference voice (the fixture clip through the 7.3 voice
chain, or `--voice`) must clear the speech band by the default style's floor. 088: over
its ceiling a bed is no longer skipped - the ear decides; it reaches the page with a note,
its margin and the level it was measured at. Every bed also gets a preview beside it
(`<file>.under_voice.wav`): the levelled bed ducked under the voice, the way a viewer will
hear it, which a yes never copies into the library.

**Best `keep`.** The first candidates that pass, in the sources' own relevance order,
rung by rung (specific to broad); drop-folder files are added beside them. 087: the
`facts_default` slot asks the profile's `queries` (`assets/audio/facts_default.yaml`)
first, then the learned default mood's words; every candidate that passes, whatever query
found it, is ranked by its distance to the profile and the nearest `keep` stay, with every
drop-folder file, nearest first. A yes on one writes the `facts_default` role. Everything
lands in `work/shortlist/` (git-ignored): the files under `<slot>/` and `shortlist.json`.

**Yes and no.** `approve` copies the file to `assets/audio/beds/` or `sfx/` and appends a
`catalog.yaml` entry with the source, its page URL, the licence, the author, the source's
own name and tags, the credits line, the measurements and the closed-list tags the
operator confirmed (a bed: at least one mood from `moods.yaml`, flavours from it; an
effect: its kind). `refuse` adds the key to `refused.yaml`, so the candidate is never
shortlisted again. Both take the candidate off the page. `check_catalogue` runs at app
startup and refuses a tracked entry whose tags are off the closed lists.

**Probe.** One live request per API source, printing its status, its result count and
the first hit's name, licence field and duration; nothing downloaded, nothing written. A
source whose key is missing says so and is not called.

**Re-fetch.** Media is never committed. `fetch-approved` downloads every approved API
file the catalogue names and the folder lacks, by the source's own id; a drop-folder
file is the operator's to keep.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

import httpx
import yaml
from pydantic import Field, SecretStr

from shortsmith import ffmpeg, styles, vocab
from shortsmith.contracts import (
    BED_ROLES,
    FACTS_DEFAULT,
    AudioEntry,
    AudioKind,
    AudioTags,
    StrictModel,
)
from shortsmith.sound import (
    CATALOGUE_NAME,
    CATALOGUE_PATH,
    MONO,
    REPO_ROOT,
    SoundError,
    audibility,
    ceiling_note,
    duck_filter,
    inaudible,
    load_catalogue,
    parse_catalogue,
    seed,
    sweep,
)
from shortsmith.sound import facts_default as fd
from shortsmith.sound import freesound as fs
from shortsmith.sound.kinds import BED, Kind, Kinds, forbidden, load_kinds, refusal

log = logging.getLogger(__name__)

LIBRARY_ROOT = CATALOGUE_PATH.parent
SLOTS_PATH = LIBRARY_ROOT / "shortlist.yaml"
SHORTLIST_DIR = REPO_ROOT / "work" / "shortlist"
SHORTLIST_NAME = "shortlist.json"
REFUSED_NAME = "refused.yaml"
INBOX_DIR = "inbox"
LICENCES_PATH = LIBRARY_ROOT / "licences"
KIND_DIRS: Mapping[AudioKind, str] = {"bed": "beds", "sfx": "sfx"}
OPENVERSE_AUDIO_URL = "https://api.openverse.org/v1/audio/"
OPENVERSE_LICENCES = "cc0,by"
OPENVERSE_ALLOWED = frozenset({"cc0", "by"})
OPENVERSE_CATEGORY: Mapping[AudioKind, str] = {"bed": "music", "sfx": "sound_effect"}
PAGE_SIZE = 5
TIMEOUT_S = 30.0
MAX_BYTES = 60 * 1024 * 1024
# The sources with no API, each with a committed licence template of the same name.
DROP_SOURCES: tuple[str, ...] = ("pixabay", "youtube_audio_library", "mixkit", "incompetech")
ATTRIBUTION_REQUIRED = frozenset({"incompetech"})
AUDIO_SUFFIXES = frozenset({".mp3", ".wav", ".ogg", ".m4a", ".flac"})
SIDECAR_SUFFIX = ".source.yaml"
# 088: the bed under the reference voice, beside the candidate in the shortlist folder.
PREVIEW_SUFFIX = ".under_voice.wav"
SIDECAR_TEMPLATE = '{source: "", page_url: "", attribution: "", slot: ""}\n'
WAITING = "inbox"
PROBE_WORDS = "music"
# An API id (digits, a UUID) passes unchanged, so `fetch-approved` reads it back off the
# entry id; a drop-folder file name becomes lower-case words.
_SLUG = re.compile(r"[^a-z0-9-]+")

Group = Literal["mood", "flavour", "effect", "facts_default"]
Log = Callable[[str], None]


class ShortlistError(ValueError):
    """The slots file is malformed, or a yes / no cannot be carried out: the message
    names the slot, the candidate or the tag."""


class Refused(Exception):
    """A candidate that failed a check: the message says which and why."""


# --- the slots --------------------------------------------------------------------------


class Slot(StrictModel):
    name: str
    kind: AudioKind
    group: Group
    words: list[str] = Field(min_length=1)
    max_len_s: float | None = None
    # 087: the learned default mood a `facts_default` candidate is tagged with on a yes.
    mood: str | None = None


class Slots(StrictModel):
    keep: int = Field(ge=1)
    anchor: str
    slots: dict[str, Slot]


def _words(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ShortlistError(f"{where}: no search words")
    words = [w.strip() for w in cast(list[object], value) if isinstance(w, str) and w.strip()]
    if len(words) != len(cast(list[object], value)):
        raise ShortlistError(f"{where}: every search rung is a few plain words")
    return words


def load_slots(
    path: Path = SLOTS_PATH, *, moods: vocab.Moods | None = None, kinds: Kinds | None = None,
    profile: fd.Profile | None = None, default_mood: str | None = None,
) -> Slots:  # fmt: skip
    """`shortlist.yaml`, checked against the closed lists: a bed slot is an active mood
    or flavour, an effect slot a kind of `kinds.yaml` with a `max_len_s`. 087: the
    `facts_default` slot asks the profile's `queries` first, then the words of the learned
    default mood's slot (`default_mood`, learned from the reference cards when not given),
    then any words it lists itself."""
    moods = moods or vocab.load_moods()
    kinds = kinds or load_kinds()
    if not path.is_file():
        raise ShortlistError(f"{path.name}: not found at {path}")
    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ShortlistError(f"{path.name}: not a mapping with `keep`, `beds` and `effects`")
    data = cast(dict[str, Any], loaded)
    beds = cast(dict[str, Any], data.get("beds") or {})
    effects = cast(dict[str, Any], data.get("effects") or {})
    anchor = beds.get("anchor")
    if not isinstance(anchor, str) or not anchor.strip():
        raise ShortlistError(f"{path.name}: beds.anchor is not a word")
    slots: dict[str, Slot] = {}
    facts_words: list[str] | None = None
    for name, words in cast(dict[str, object], beds.get("slots") or {}).items():
        where = f"{path.name}: bed slot {name!r}"
        if name == FACTS_DEFAULT:
            facts_words = [] if words == [] else _words(words, where)
            continue
        if name in moods.active_moods():
            group: Group = "mood"
        elif name in moods.active_flavours():
            group = "flavour"
        else:
            raise ShortlistError(f"{where} is not an active mood or flavour of moods.yaml")
        slots[name] = Slot(name=name, kind="bed", group=group, words=_words(words, where))
    for name, row in effects.items():
        where = f"{path.name}: effect slot {name!r}"
        if name not in kinds.sfx_kinds():
            raise ShortlistError(f"{where} is not a kind of kinds.yaml")
        if not isinstance(row, dict):
            raise ShortlistError(f"{where} is not a mapping with max_len_s and words")
        fields = cast(dict[str, object], row)
        length = fields.get("max_len_s")
        if not isinstance(length, int | float) or isinstance(length, bool) or length <= 0:
            raise ShortlistError(f"{where} has no positive max_len_s")
        slots[name] = Slot(
            name=name, kind="sfx", group="effect", words=_words(fields.get("words"), where),
            max_len_s=float(length),
        )  # fmt: skip
    keep = data.get("keep")
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 1:
        raise ShortlistError(f"{path.name}: keep is not a whole number of 1 or more")
    if facts_words is not None:
        slots[FACTS_DEFAULT] = _facts_slot(slots, facts_words, profile, default_mood)
    return Slots(keep=keep, anchor=anchor.strip(), slots=slots)


def _facts_slot(
    slots: Mapping[str, Slot], own: list[str], profile: fd.Profile | None,
    default_mood: str | None,
) -> Slot:  # fmt: skip
    profile = profile or fd.load_profile()
    if default_mood is None:
        learned = fd.learned_mood(profile=profile, log=log.info)
        default_mood = learned.mood if learned is not None else None
    mood_slot = slots.get(default_mood) if default_mood is not None else None
    mood_words = (
        mood_slot.words if mood_slot is not None
        else [default_mood.replace("_", " ")] if default_mood is not None else []
    )  # fmt: skip
    words = list(dict.fromkeys([*profile.queries, *mood_words, *own]))
    return Slot(name=FACTS_DEFAULT, kind="bed", group="facts_default", words=words,
                mood=default_mood)  # fmt: skip


def rungs(slot: Slot, anchor: str) -> list[str]:
    """The slot's search words, specific to broad; a bed's each end with the anchor."""
    if slot.kind != "bed":
        return list(slot.words)
    return [" ".join([*[w for w in words.split() if w != anchor], anchor]) for words in slot.words]


# --- what the sources found ---------------------------------------------------------------


@dataclass(frozen=True)
class Found:
    """One API hit before it is fetched: what the source says about it."""

    source: str
    source_id: str
    name: str
    tags: tuple[str, ...]
    licence: str
    licence_ok: bool
    author: str | None
    page_url: str
    file_url: str
    duration_s: float
    credit: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


@dataclass(frozen=True)
class Page:
    status: str
    hits: int
    found: tuple[Found, ...] = ()


def _download(get: Callable[[str], httpx.Response], url: str, dest: Path) -> Path:
    """`url` into `dest` with the URL's suffix; a `SoundError` when it fails, is empty
    or is over `MAX_BYTES`, and nothing is written."""
    try:
        response = get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SoundError(f"{url} could not be downloaded: {exc}") from None
    body = response.content
    if not body:
        raise SoundError(f"{url} answered an empty body")
    if len(body) > MAX_BYTES:
        raise SoundError(f"{url} is {len(body) / 1024 / 1024:.1f} MB, over the limit")
    path = dest.with_name(dest.name + (Path(urlparse(url).path).suffix or ".mp3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


class Source(ABC):
    """One API source of the shortlist."""

    name: str

    @abstractmethod
    def search(self, words: str, slot: Slot) -> Page: ...

    @abstractmethod
    def fetch(self, found: Found, dest: Path) -> Path:
        """The file into `dest` + its suffix."""

    @abstractmethod
    def locate(self, source_id: str) -> str:
        """The file URL of one of this source's sounds by id (`fetch-approved`)."""

    @abstractmethod
    def download(self, url: str, dest: Path) -> Path: ...

    @abstractmethod
    def probe(self) -> str:
        """One live request, as one line."""


def _dicts(value: object) -> list[dict[str, Any]]:
    """The mappings of a JSON list (an answer's results, a hit's tags); anything else
    is none."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], v) for v in cast(list[object], value) if isinstance(v, dict)]


def _page_status(exc: httpx.HTTPError) -> str:
    return "timeout" if isinstance(exc, httpx.TimeoutException) else f"error {type(exc).__name__}"


class OpenverseSource(Source):
    """Openverse audio: public, no key; Jamendo, ccMixter and Wikimedia audio behind it."""

    name = "openverse"

    def __init__(self, *, client: httpx.Client | None = None, page_size: int = PAGE_SIZE) -> None:
        self._client = client
        self._page_size = page_size

    def _get(self, url: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        from shortsmith.assets.http import USER_AGENT

        headers = {"User-Agent": USER_AGENT}
        if self._client is not None:
            return self._client.get(url, params=params, headers=headers, follow_redirects=True)
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True) as owned:
            return owned.get(url, params=params, headers=headers)

    def _answer(self, words: str, kind: AudioKind) -> tuple[str, int, list[dict[str, Any]]]:
        params = {
            "q": " ".join(words.split()),
            "license": OPENVERSE_LICENCES,
            "category": OPENVERSE_CATEGORY[kind],
            "page_size": str(self._page_size),
        }
        try:
            response = self._get(OPENVERSE_AUDIO_URL, params)
        except httpx.HTTPError as exc:
            return _page_status(exc), 0, []
        status = str(response.status_code)
        if response.is_error:
            return status, 0, []
        try:
            body: object = response.json()
        except ValueError:
            return f"{status} unreadable body", 0, []
        if not isinstance(body, dict):
            return status, 0, []
        data = cast(dict[str, Any], body)
        results = _dicts(data.get("results"))
        count = data.get("result_count")
        return status, count if isinstance(count, int) else len(results), results

    def search(self, words: str, slot: Slot) -> Page:
        from shortsmith.assets.openverse import licence_text

        status, hits, results = self._answer(words, slot.kind)
        found: list[Found] = []
        for hit in results:
            url, sid = str(hit.get("url") or ""), str(hit.get("id") or "")
            if not url or not sid:
                continue
            code = str(hit.get("license") or "").lower()
            version = str(hit.get("license_version") or "") or None
            tags = tuple(str(t.get("name") or "") for t in _dicts(hit.get("tags")))
            duration = hit.get("duration")
            found.append(Found(
                source=self.name, source_id=sid, name=str(hit.get("title") or sid),
                tags=tuple(t for t in tags if t), licence=licence_text(code, version),
                licence_ok=code in OPENVERSE_ALLOWED, author=str(hit.get("creator") or "") or None,
                page_url=str(hit.get("foreign_landing_url") or ""), file_url=url,
                duration_s=duration / 1000 if isinstance(duration, int | float) else 0.0,
                credit=str(hit.get("attribution") or ""),
            ))  # fmt: skip
        return Page(status, hits, tuple(found))

    def download(self, url: str, dest: Path) -> Path:
        return _download(self._get, url, dest)

    def fetch(self, found: Found, dest: Path) -> Path:
        return self.download(found.file_url, dest)

    def locate(self, source_id: str) -> str:
        url = f"{OPENVERSE_AUDIO_URL}{source_id}/"
        try:
            response = self._get(url)
        except httpx.HTTPError as exc:
            raise SoundError(f"{url}: {type(exc).__name__}") from None
        if response.is_error:
            raise SoundError(f"{url}: status {response.status_code}")
        body: object = response.json()
        file_url = cast(dict[str, Any], body).get("url") if isinstance(body, dict) else None
        if not isinstance(file_url, str) or not file_url:
            raise SoundError(f"{url}: no file url")
        return file_url

    def probe(self) -> str:
        status, hits, results = self._answer(PROBE_WORDS, "bed")
        line = f"{self.name}: status {status}, {hits} results"
        if not results:
            return line
        first = results[0]
        duration = first.get("duration")
        seconds = duration / 1000 if isinstance(duration, int | float) else 0.0
        return (
            f"{line}, first {str(first.get('title') or '')!r}, licence "
            f"{first.get('license') or ''} {first.get('license_version') or ''}".rstrip()
            + f", {seconds:.1f} s"
        )


class FreesoundSource(Source):
    """Freesound through its adapter (`sound.freesound`): the same request, token and
    licence filter a job used, with an effect's length in the filter."""

    name = fs.SOURCE

    def __init__(self, search: fs.FreesoundAudioSearch) -> None:
        self._search = search

    def search(self, words: str, slot: Slot) -> Page:
        page = self._search.search(words, slot.kind, max_len_s=slot.max_len_s)
        return Page(page.status, page.hits, tuple(
            Found(
                source=self.name, source_id=c.id, name=c.name, tags=tuple(c.tags),
                licence=c.licence, licence_ok=fs.licence_allowed(c.licence), author=c.author,
                page_url=c.page_url, file_url=c.preview_url, duration_s=c.duration_s,
                credit=f"{c.name} by {c.author or 'unknown'} (freesound.org), {c.licence}",
            )
            for c in page.candidates
        ))  # fmt: skip

    def download(self, url: str, dest: Path) -> Path:
        return _download(lambda u: self._search.get(u), url, dest)

    def fetch(self, found: Found, dest: Path) -> Path:
        return self.download(found.file_url, dest)

    def locate(self, source_id: str) -> str:
        return self._search.preview_url(source_id)

    def probe(self) -> str:
        params = {
            "query": PROBE_WORDS, "filter": fs.search_filter("bed"), "fields": fs.FIELDS,
            "page_size": str(PAGE_SIZE),
        }  # fmt: skip
        try:
            response = self._search.get(fs.API_URL, params=params)
        except httpx.HTTPError as exc:
            return f"{self.name}: status {_page_status(exc)}, 0 results"
        line = f"{self.name}: status {response.status_code}"
        try:
            body: object = response.json()
        except ValueError:
            return f"{line}, unreadable body"
        data = cast(dict[str, Any], body) if isinstance(body, dict) else {}
        results = _dicts(data.get("results"))
        count = data.get("count")
        line += f", {count if isinstance(count, int) else len(results)} results"
        if not results:
            return line
        first = results[0]
        duration = first.get("duration")
        seconds = float(duration) if isinstance(duration, int | float) else 0.0
        return (
            f"{line}, first {str(first.get('name') or '')!r}, licence "
            f"{first.get('license') or ''}, {seconds:.1f} s"
        )


class MissingSource(Source):
    """A source whose key is not set: never called, and says so."""

    def __init__(self, name: str, why: str) -> None:
        self.name = name
        self.why = why

    def search(self, words: str, slot: Slot) -> Page:
        return Page(f"skipped ({self.why})", 0)

    def fetch(self, found: Found, dest: Path) -> Path:
        raise SoundError(f"{self.name}: {self.why}")

    def download(self, url: str, dest: Path) -> Path:
        raise SoundError(f"{self.name}: {self.why}")

    def locate(self, source_id: str) -> str:
        raise SoundError(f"{self.name}: {self.why}")

    def probe(self) -> str:
        return f"{self.name}: {self.why}; skipped"


def sources_for(
    *, freesound_key: SecretStr | None, client: httpx.Client | None = None
) -> list[Source]:
    """Openverse (no key) and Freesound (`FREESOUND_API_KEY`), or a `MissingSource`."""
    freesound: Source = (
        FreesoundSource(fs.FreesoundAudioSearch(api_key=freesound_key, client=client))
        if freesound_key is not None
        else MissingSource(fs.SOURCE, "FREESOUND_API_KEY is not set in .env")
    )
    return [OpenverseSource(client=client), freesound]


def probe(sources: Sequence[Source]) -> list[str]:
    return [source.probe() for source in sources]


# --- the checks ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Audible:
    """088: a bed's speech-band margin at `level_db` under the reference voice, the note
    when it is over 069's ceiling (the ear decides), and the bed mixed under the voice."""

    margin_db: float
    level_db: float
    note: str | None
    preview: Path


@dataclass(frozen=True)
class Checked:
    measured: seed.Measured
    audible: Audible | None = None
    numbers: fd.Numbers | None = None


@dataclass
class Checker:
    """The checks that need the file: the 023 measure, the length allowance, the sweep
    detector (effects but a whoosh), 069's audibility (beds). 087: a `facts_default`
    candidate is also measured against the facts-default profile (loaded when not given)."""

    voice: Path
    nums: styles.Sound
    kinds: Kinds
    profile: fd.Profile | None = None
    _voice_db: list[float] = field(default_factory=lambda: [])

    def facts_profile(self) -> fd.Profile:
        if self.profile is None:
            self.profile = fd.load_profile()
        return self.profile

    def kind(self, slot: Slot) -> Kind:
        return self.kinds.kind(BED) if slot.kind == "bed" else self.kinds.for_sfx(slot.name)

    def voice_db(self) -> float:
        if not self._voice_db:
            measured = ffmpeg.mean_volume_db(self.voice)
            if measured is None:
                raise SoundError(f"the reference voice {self.voice} is silent")
            self._voice_db.append(measured)
        return self._voice_db[0]

    def check(self, path: Path, slot: Slot) -> Checked:
        try:
            measured = seed.measure_file(path, kind=slot.kind)
        except ffmpeg.FFmpegError as exc:
            raise Refused(f"not readable audio: {exc}") from None
        if slot.kind == "sfx":
            limit = slot.max_len_s
            if limit is not None and measured.duration_s > limit + 1e-3:
                raise Refused(
                    f"{measured.duration_s:.2f} s long, over {slot.name}'s max_len_s {limit:g}"
                )
            if not styles.is_whoosh(slot.name):
                hits = sweep.detect(path)
                if hits:
                    raise Refused(f"{hits[0].rule} at {hits[0].at_s:.2f} s: {hits[0].detail}")
            return Checked(measured)
        audible = self._audible(path)
        if slot.group != "facts_default":
            return Checked(measured, audible)
        return Checked(measured, audible, fd.measure_file(path, self.facts_profile()))

    def _audible(self, path: Path) -> Audible:
        """069's margin at the mix level. Under the floor the bed crowds the voice and is
        refused; 088: over the ceiling it is kept with a note, and the ear decides on the
        preview - the levelled bed under the voice through the 7.3 sidechain."""
        bed_db = ffmpeg.mean_volume_db(path)
        if bed_db is None:
            raise Refused("silent")
        levelled = path.with_name(path.stem + ".levelled.wav")
        level = self.nums.bed_db_under_voice
        gain = self.voice_db() + level - bed_db
        try:
            ffmpeg.run(
                [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(path), "-af",
                 f"volume={gain:.2f}dB", "-c:a", "pcm_f32le", str(levelled)],
                timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
            )  # fmt: skip
            margin, problem = audibility(self.voice, levelled, self.nums, level_db=level)
            if margin is None:
                raise Refused("nothing in the speech band")
            if inaudible(margin, self.nums):
                return Audible(margin, level, ceiling_note(margin, self.nums, level_db=level),
                               self._under_voice(levelled, path))  # fmt: skip
            if problem is not None:
                raise Refused(problem)
            return Audible(margin, level, None, self._under_voice(levelled, path))
        finally:
            levelled.unlink(missing_ok=True)

    def _under_voice(self, levelled: Path, path: Path) -> Path:
        """088: the levelled bed ducked under the reference voice and summed with it, as
        long as the voice - what a yes judges. It stays beside the candidate in the
        shortlist folder and never reaches the library."""
        out = path.with_name(path.stem + PREVIEW_SUFFIX)
        ffmpeg.run(
            [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(self.voice), "-i", str(levelled),
             "-filter_complex",
             f"[0:a]{MONO},asplit=2[v][chain];[1:a]{MONO}[bed];[bed][chain]{duck_filter()}[d];"
             "[v][d]amix=inputs=2:normalize=0:duration=first[m]",
             "-map", "[m]", "-c:a", "pcm_s16le", str(out)],
            timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
        )  # fmt: skip
        return out


def reference_voice(dest: Path) -> Path:
    """The voice a bed is judged against when no `--voice` is given: the fixture clip
    through the 7.3 voice chain to the voice loudness, as 069's tests build it."""
    from shortsmith import fixture, render

    dest.parent.mkdir(parents=True, exist_ok=True)
    clip = fixture.make_fixture(dest.with_name(dest.stem + ".source.mp4"))
    measured = ffmpeg.measure_loudness(
        clip, prefilter=render.voice_chain(), target_lufs=render.VOICE_LUFS,
        target_tp=render.VOICE_TP,
    )  # fmt: skip
    second = render.loudnorm_second_pass(
        measured, target_lufs=render.VOICE_LUFS, target_tp=render.VOICE_TP
    )
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(clip), "-map", "0:a:0",
         "-af", f"{render.voice_chain()},{second},aresample=48000", "-c:a", "pcm_s16le",
         str(dest)],
        timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
    )  # fmt: skip
    clip.unlink(missing_ok=True)
    return dest


# --- the shortlist ------------------------------------------------------------------------


class Candidate(StrictModel):
    """One file on the listening page."""

    key: str
    slot: str
    kind: AudioKind
    source: str
    source_id: str
    name: str
    page_url: str = ""
    file: str  # relative to the shortlist folder
    licence: str = ""
    author: str | None = None
    source_tags: list[str] = []
    credit: str = ""
    duration_s: float = 0.0
    energy: int | None = None
    bpm: float | None = None
    key_sig: str | None = None
    margin_db: float | None = None
    # 088: the bed level the margin was measured at (dB under the voice), the note when
    # the margin is over 069's ceiling, and the bed under the voice (relative, as `file`).
    level_db: float | None = None
    note: str | None = None
    preview: str | None = None
    tags: AudioTags = AudioTags()
    needs_source: bool = False
    # 087: a `facts_default` candidate's measured profile features and its distance to
    # the profile (nearest first on the page).
    profile: dict[str, float] = {}
    distance: float | None = None

    def numbers(self) -> fd.Numbers:
        return fd.Numbers(key=self.key_sig, **self.profile)

    @property
    def entry_id(self) -> str:
        return f"{self.source}_{_slug(self.source_id)}"


class Shortlist(StrictModel):
    slots: dict[str, list[Candidate]] = {}
    inbox: list[Candidate] = []

    def find(self, key: str) -> Candidate | None:
        for candidate in [*self.inbox, *(c for kept in self.slots.values() for c in kept)]:
            if candidate.key == key:
                return candidate
        return None

    def without(self, key: str) -> Shortlist:
        return Shortlist(
            slots={s: [c for c in kept if c.key != key] for s, kept in self.slots.items()},
            inbox=[c for c in self.inbox if c.key != key],
        )


def _slug(text: str) -> str:
    return _SLUG.sub("_", text.lower()).strip("_") or "file"


def suggested_tags(slot: Slot) -> AudioTags:
    if slot.group == "facts_default":
        return AudioTags(mood=[slot.mood] if slot.mood else [], role=[FACTS_DEFAULT])
    if slot.group == "mood":
        return AudioTags(mood=[slot.name])
    if slot.group == "flavour":
        return AudioTags(flavour=[slot.name])
    return AudioTags(intent=[slot.name])


def load_shortlist(out_dir: Path) -> Shortlist:
    path = out_dir / SHORTLIST_NAME
    if not path.is_file():
        return Shortlist()
    return Shortlist.model_validate_json(path.read_text(encoding="utf-8"))


def _save(out_dir: Path, shortlist: Shortlist) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SHORTLIST_NAME).write_text(shortlist.model_dump_json(indent=2), encoding="utf-8")


def load_refused(library_root: Path) -> list[str]:
    path = library_root / REFUSED_NAME
    if not path.is_file():
        return []
    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    listed = cast(dict[str, Any], loaded).get("refused") if isinstance(loaded, dict) else None
    return [str(k) for k in cast(list[object], listed or [])]


def _candidate(
    slot: Slot, *, source: str, source_id: str, name: str, page_url: str, file: Path,
    out_dir: Path, licence: str, author: str | None, tags: Sequence[str], credit: str,
    checked: Checked,
) -> Candidate:  # fmt: skip
    m = checked.measured
    numbers = checked.numbers
    heard = checked.audible
    return Candidate(
        key=f"{source}:{source_id}", slot=slot.name, kind=slot.kind, source=source,
        source_id=source_id, name=name, page_url=page_url,
        file=file.relative_to(out_dir).as_posix(), licence=licence, author=author,
        source_tags=list(tags), credit=credit, duration_s=m.duration_s, energy=m.energy,
        bpm=m.bpm, key_sig=numbers.key if numbers is not None else m.key,
        margin_db=round(heard.margin_db, 2) if heard is not None else None,
        level_db=heard.level_db if heard is not None else None,
        note=heard.note if heard is not None else None,
        preview=heard.preview.relative_to(out_dir).as_posix() if heard is not None else None,
        tags=suggested_tags(slot), profile=numbers.features() if numbers is not None else {},
    )  # fmt: skip


@dataclass(frozen=True)
class DropFile:
    path: Path
    source: str
    page_url: str
    attribution: str
    slot: str


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + SIDECAR_SUFFIX)


def licence_template(source: str, folder: Path = LICENCES_PATH) -> str:
    """The first line of the committed `licences/<source>.txt`: the licence text an
    entry carries."""
    path = folder / f"{source}.txt"
    if not path.is_file():
        raise ShortlistError(f"no licence template for {source} at {path}")
    return path.read_text(encoding="utf-8").strip().splitlines()[0].strip()


def scan_inbox(inbox: Path, slots: Slots, log: Log) -> tuple[list[DropFile], list[Path]]:
    """The drop folder's audio files: those whose sidecar is filled, and those still
    waiting (a sidecar template is written beside each file that has none)."""
    if not inbox.is_dir():
        return [], []
    filled: list[DropFile] = []
    waiting: list[Path] = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        sidecar = _sidecar(path)
        if not sidecar.is_file():
            sidecar.write_text(SIDECAR_TEMPLATE, encoding="utf-8")
            log(f"inbox: {path.name}: wrote {sidecar.name}; fill in source, page_url, "
                f"attribution and slot")  # fmt: skip
        loaded: object = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        row = cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
        source, page_url, attribution, slot = (
            str(row.get(k) or "").strip() for k in ("source", "page_url", "attribution", "slot")
        )
        missing = [
            why for why, bad in (
                (f"source (one of {', '.join(DROP_SOURCES)})", source not in DROP_SOURCES),
                ("page_url", not page_url),
                ("slot (one of the shortlist's slots)", slot not in slots.slots),
                ("attribution", source in ATTRIBUTION_REQUIRED and not attribution),
            ) if bad
        ]  # fmt: skip
        if missing:
            log(f"inbox: {path.name}: needs source: {', '.join(missing)} in {sidecar.name}")
            waiting.append(path)
            continue
        filled.append(DropFile(path, source, page_url, attribution, slot))
    return filled, waiting


def _refusal_before_download(
    found: Found, slot: Slot, kind: Kind, refused: set[str], approved: set[str]
) -> str | None:
    if found.key in refused:
        return "the operator said no to it"
    if f"{found.source}_{_slug(found.source_id)}" in approved:
        return "already in the approved library"
    if not found.licence_ok:
        return f"licence {found.licence} is not CC0 or CC BY"
    why = refusal(kind, found.name, found.tags)
    if why is not None:
        return why
    limit = slot.max_len_s
    if limit is not None and found.duration_s > limit + 1e-3:
        return f"{found.duration_s:.2f} s long, over {slot.name}'s max_len_s {limit:g}"
    return None


def _preferred(sources: Sequence[Source], kind: AudioKind) -> list[Source]:
    """Openverse first for a bed (the main music source), Freesound first for an effect."""
    first = "openverse" if kind == "bed" else fs.SOURCE
    return sorted(sources, key=lambda s: s.name != first)


def build(
    slots: Slots,
    sources: Sequence[Source],
    *,
    out_dir: Path = SHORTLIST_DIR,
    library_root: Path = LIBRARY_ROOT,
    inbox: Path | None = None,
    checker: Checker,
    only: Sequence[str] = (),
    log: Log = print,
) -> Shortlist:
    """Shortlist every slot of `only` (all when empty) and write `shortlist.json`; the
    slots not asked keep what the last run left on the page."""
    unknown = [n for n in only if n not in slots.slots]
    if unknown:
        raise ShortlistError(f"no slot {', '.join(unknown)} in {SLOTS_PATH.name}")
    names = list(only) or list(slots.slots)
    refused = set(load_refused(library_root))
    approved = {e.id for e in load_catalogue(library_root / CATALOGUE_NAME).entries}
    filled, waiting = scan_inbox(inbox if inbox is not None else library_root / INBOX_DIR,
                                 slots, log)  # fmt: skip
    previous = load_shortlist(out_dir)
    result: dict[str, list[Candidate]] = {
        s: kept for s, kept in previous.slots.items() if s not in names and s in slots.slots
    }
    for name in names:
        slot = slots.slots[name]
        ranked = slot.group == "facts_default"
        kept = _api_candidates(slot, slots, sources, out_dir, checker, refused, approved, log,
                               limit=None if ranked else slots.keep)  # fmt: skip
        drops = _drop_candidates(slot, filled, out_dir, checker, refused, approved, log)
        if ranked:
            kept = _nearest(kept, drops, slots.keep, checker, out_dir, log)
        else:
            kept += drops
        result[name] = kept
        log(f"{name}: {len(kept)} on the page")
    ordered = {s: result[s] for s in slots.slots if s in result}
    shortlist = Shortlist(slots=ordered, inbox=[_waiting(p, out_dir) for p in waiting])
    _save(out_dir, shortlist)
    return shortlist


def _nearest(
    found: list[Candidate], drops: list[Candidate], keep: int, checker: Checker, out_dir: Path,
    log: Log,
) -> list[Candidate]:  # fmt: skip
    """087: every candidate of the `facts_default` slot ranked by its distance to the
    profile, whatever query found it: the nearest `keep` API files and every drop-folder
    file stay, nearest first; the rest leave the folder. A vocal never ranks."""
    everyone = [*found, *drops]
    ranked = fd.rank(
        [(c.name, c.source_tags, c.numbers()) for c in everyone],
        checker.facts_profile(), checker.kinds.kind(BED),
    )  # fmt: skip
    kept: list[Candidate] = []
    api = 0
    dropped = set(range(len(found)))
    for i, gap in ranked:
        candidate = everyone[i].model_copy(update={"distance": round(gap, 3)})
        where = f"{candidate.slot}: {candidate.name!r} distance {gap:.2f} to the profile"
        if i < len(found):
            if api >= keep:
                log(f"{where}; past the nearest {keep}")
                continue
            api += 1
            dropped.discard(i)
        log(where)
        kept.append(candidate)
    for i in dropped:
        for name in (found[i].file, found[i].preview):
            if name is not None:
                (out_dir / name).unlink(missing_ok=True)
    return kept


def _api_candidates(
    slot: Slot, slots: Slots, sources: Sequence[Source], out_dir: Path, checker: Checker,
    refused: set[str], approved: set[str], log: Log, *, limit: int | None,
) -> list[Candidate]:  # fmt: skip
    """The first `limit` candidates that pass, rung by rung (all of them when None)."""
    kind = checker.kind(slot)
    kept: list[Candidate] = []
    seen: set[str] = set()
    for words in rungs(slot, slots.anchor):
        for source in _preferred(sources, slot.kind):
            if limit is not None and len(kept) >= limit:
                return kept
            page = source.search(words, slot)
            log(f"{slot.name}: {source.name} {words!r}: status {page.status}, {page.hits} hits")
            for found in page.found:
                if limit is not None and len(kept) >= limit:
                    return kept
                if found.key in seen:
                    continue
                seen.add(found.key)
                where = f"{slot.name}: {source.name} {found.name!r} ({found.page_url})"
                why = _refusal_before_download(found, slot, kind, refused, approved)
                if why is not None:
                    log(f"{where} skipped: {why}")
                    continue
                try:
                    stem = f"{source.name}_{_slug(found.source_id)}"
                    path = source.fetch(found, out_dir / slot.name / stem)
                except SoundError as exc:
                    log(f"{where} skipped: {exc}")
                    continue
                try:
                    checked = checker.check(path, slot)
                except Refused as exc:
                    path.unlink(missing_ok=True)
                    log(f"{where} skipped: {exc}")
                    continue
                kept.append(_candidate(
                    slot, source=source.name, source_id=found.source_id, name=found.name,
                    page_url=found.page_url, file=path, out_dir=out_dir, licence=found.licence,
                    author=found.author, tags=found.tags, credit=found.credit, checked=checked,
                ))  # fmt: skip
                log(f"{where} shortlisted")
    return kept


def _drop_candidates(
    slot: Slot, filled: Sequence[DropFile], out_dir: Path, checker: Checker,
    refused: set[str], approved: set[str], log: Log,
) -> list[Candidate]:  # fmt: skip
    kept: list[Candidate] = []
    for drop in (d for d in filled if d.slot == slot.name):
        key = f"{drop.source}:{drop.path.name}"
        where = f"{slot.name}: inbox {drop.path.name!r} ({drop.source})"
        if key in refused:
            log(f"{where} skipped: the operator said no to it")
            continue
        if f"{drop.source}_{_slug(drop.path.name)}" in approved:
            log(f"{where} skipped: already in the approved library")
            continue
        why = forbidden(checker.kind(slot), drop.path.stem, [])
        if why is not None:
            log(f"{where} skipped: {why}")
            continue
        copy = out_dir / slot.name / f"{drop.source}_{_slug(drop.path.name)}{drop.path.suffix}"
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(drop.path, copy)
        try:
            checked = checker.check(copy, slot)
        except Refused as exc:
            copy.unlink(missing_ok=True)
            log(f"{where} skipped: {exc}")
            continue
        kept.append(_candidate(
            slot, source=drop.source, source_id=drop.path.name, name=drop.path.name,
            page_url=drop.page_url, file=copy, out_dir=out_dir,
            licence=licence_template(drop.source), author=None, tags=(),
            credit=drop.attribution, checked=checked,
        ))  # fmt: skip
        log(f"{where} shortlisted")
    return kept


def _waiting(path: Path, out_dir: Path) -> Candidate:
    """A drop-folder file with no filled sidecar: listed, playable, not approvable."""
    copy = out_dir / WAITING / path.name
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, copy)
    return Candidate(
        key=f"{WAITING}:{path.name}", slot="", kind="bed", source=WAITING, source_id=path.name,
        name=path.name, file=copy.relative_to(out_dir).as_posix(), needs_source=True,
    )  # fmt: skip


# --- yes and no ---------------------------------------------------------------------------


def tags_problem(
    kind: AudioKind, tags: AudioTags, *, moods: vocab.Moods, kinds: Kinds
) -> str | None:
    """Why `tags` are not closed-list tags for a `kind` entry, or None: a bed carries at
    least one mood of `moods.yaml` and only its flavours; an effect one kind of
    `kinds.yaml` and nothing else."""
    if tags.theme:
        return f"theme tags {tags.theme} are not on a closed list"
    off_roles = [r for r in tags.role if r not in BED_ROLES]
    if off_roles:
        return f"role {', '.join(off_roles)} is not one of {', '.join(BED_ROLES)}"
    if kind != "bed" and tags.role:
        return f"an effect carries no role (given {', '.join(tags.role)})"
    if kind == "bed":
        if tags.intent:
            return f"a bed carries no intent (given {tags.intent})"
        if not tags.mood:
            return "a bed needs at least one mood of moods.yaml"
        off = [m for m in tags.mood if m not in moods.moods]
        if off:
            return f"mood {', '.join(off)} is not in moods.yaml"
        off = [f for f in tags.flavour if f not in moods.flavours]
        if off:
            return f"flavour {', '.join(off)} is not in moods.yaml"
        return None
    if tags.mood or tags.flavour:
        return "an effect carries its kind as its intent, no mood or flavour"
    if len(tags.intent) != 1:
        return f"an effect carries exactly one intent (given {tags.intent})"
    if tags.intent[0] not in kinds.sfx_kinds():
        return f"intent {tags.intent[0]} is not a kind of kinds.yaml"
    return None


def check_catalogue(
    path: Path = CATALOGUE_PATH, *, moods: vocab.Moods | None = None, kinds: Kinds | None = None
) -> None:
    """At startup: every tracked catalogue entry carries closed-list tags (the fetched
    catalogue is the runtime search's, 024, and is not asked). A `SoundError` names the
    entry and the tag."""
    if not path.is_file():
        return
    moods = moods or vocab.load_moods()
    kinds = kinds or load_kinds()
    for entry in parse_catalogue(path.read_text(encoding="utf-8"), name=path.name).entries:
        problem = tags_problem(entry.kind, entry.tags, moods=moods, kinds=kinds)
        if problem is not None:
            raise SoundError(f"{path.name}: entry {entry.id}: {problem}")


def approve(
    key: str,
    *,
    tags: AudioTags,
    out_dir: Path = SHORTLIST_DIR,
    library_root: Path = LIBRARY_ROOT,
    moods: vocab.Moods | None = None,
    kinds: Kinds | None = None,
) -> AudioEntry:
    """The operator's yes: the file into `beds/` or `sfx/`, its entry appended to the
    catalogue, the candidate off the page."""
    shortlist = load_shortlist(out_dir)
    candidate = shortlist.find(key)
    if candidate is None:
        raise ShortlistError(f"{key}: not on the shortlist")
    if candidate.needs_source:
        raise ShortlistError(
            f"{candidate.name}: needs source - fill in its {SIDECAR_SUFFIX} sidecar in "
            f"{INBOX_DIR}/ and run the shortlist again"
        )
    problem = tags_problem(
        candidate.kind, tags, moods=moods or vocab.load_moods(), kinds=kinds or load_kinds()
    )
    if problem is not None:
        raise ShortlistError(f"{candidate.name}: {problem}")
    catalogue = library_root / CATALOGUE_NAME
    entry_id = candidate.entry_id
    if load_catalogue(catalogue).entry(entry_id) is not None:
        raise ShortlistError(f"{entry_id} is already in {CATALOGUE_NAME}")
    source = out_dir / candidate.file
    if not source.is_file():
        raise ShortlistError(f"{candidate.name}: {candidate.file} is gone from the shortlist")
    dest = library_root / KIND_DIRS[candidate.kind] / f"{entry_id}{source.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    loops = candidate.kind == "bed" and bool(
        fs.LOOP_TAGS & {t.lower() for t in candidate.source_tags}
    )
    entry = AudioEntry(
        id=entry_id, kind=candidate.kind, file=dest.relative_to(library_root).as_posix(),
        source=candidate.source, source_url=candidate.page_url, source_name=candidate.name,
        source_tags=list(candidate.source_tags), licence=candidate.licence,
        author=candidate.author, credit=candidate.credit or None,
        duration_s=candidate.duration_s, bpm=candidate.bpm, key=candidate.key_sig,
        tags=tags, drop_points_s=[], loop_ok=loops, energy=candidate.energy or 1,
    )  # fmt: skip
    try:
        fs.append_entry(catalogue, entry)
    except SoundError:
        dest.unlink(missing_ok=True)
        raise
    _save(out_dir, shortlist.without(key))
    return entry


def refuse(key: str, *, out_dir: Path = SHORTLIST_DIR, library_root: Path = LIBRARY_ROOT) -> None:
    """The operator's no: the key remembered in `refused.yaml`, the candidate off the
    page."""
    shortlist = load_shortlist(out_dir)
    if shortlist.find(key) is None:
        raise ShortlistError(f"{key}: not on the shortlist")
    path = library_root / REFUSED_NAME
    keys = load_refused(library_root)
    if key not in keys:
        keys.append(key)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    header = text[: text.index("refused:")] if "refused:" in text else text
    path.write_text(header + yaml.safe_dump({"refused": keys}, sort_keys=False), encoding="utf-8")
    _save(out_dir, shortlist.without(key))


def page_moods(moods: vocab.Moods) -> tuple[str, ...]:
    """The moods the page offers: the active ones."""
    return moods.active_moods()


# --- re-fetching approved files -----------------------------------------------------------


def fetch_approved(catalogue: Path, sources: Sequence[Source], log: Log = print) -> int:
    """Every tracked entry from an API source whose file is missing, downloaded again by
    its source id; 1 when any could not be."""
    by_name = {s.name: s for s in sources}
    root = catalogue.parent
    failed = 0
    for entry in load_catalogue(catalogue).entries:
        target = root / entry.file
        if target.is_file():
            continue
        source = by_name.get(entry.source)
        if source is None:
            log(f"{entry.id}: {entry.file} is missing; a {entry.source} file is the "
                "operator's to keep")  # fmt: skip
            continue
        source_id = entry.id.removeprefix(f"{entry.source}_")
        try:
            url = source.locate(source_id)
            got = source.download(url, target.with_suffix(""))
        except SoundError as exc:
            failed += 1
            log(f"{entry.id}: could not be fetched: {exc}")
            continue
        if got != target:
            got.replace(target)
        log(f"{entry.id}: fetched into {entry.file}")
    return 1 if failed else 0


# --- the command --------------------------------------------------------------------------

COMMANDS = ("build", "probe", "fetch-approved")


def main(argv: Sequence[str] | None = None) -> int:
    from shortsmith import config, render

    parser = argparse.ArgumentParser(prog="python -m shortsmith.sound.shortlist")
    parser.add_argument("command", nargs="?", default="build", choices=COMMANDS)
    parser.add_argument("--slot", action="append", default=[], help="one slot (repeatable)")
    parser.add_argument("--voice", type=Path, default=None, help="the voice beds are judged by")
    args = parser.parse_args(argv)
    settings = config.load()
    sources = sources_for(freesound_key=settings.freesound_api_key)
    if args.command == "probe":
        for line in probe(sources):
            print(line)
        return 0
    if args.command == "fetch-approved":
        return fetch_approved(CATALOGUE_PATH, sources)
    voice = cast(Path | None, args.voice) or reference_voice(SHORTLIST_DIR / "voice.wav")
    checker = Checker(
        voice=voice, nums=render.loaded_styles()[styles.DEFAULT].sound, kinds=load_kinds(),
        profile=fd.load_profile(),
    )  # fmt: skip
    shortlist = build(load_slots(), sources, checker=checker, only=cast(list[str], args.slot))
    total = sum(len(kept) for kept in shortlist.slots.values())
    print(f"{total} candidates on the page, {len(shortlist.inbox)} drop-folder files need a source")
    print(f"listen at /audio/shortlist; written to {SHORTLIST_DIR / SHORTLIST_NAME}")
    print(json.dumps({s: len(k) for s, k in shortlist.slots.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
