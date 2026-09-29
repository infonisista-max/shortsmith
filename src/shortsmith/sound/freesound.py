"""The Freesound audio search: the runtime rung under the local catalogue (decisions
7.1, 7.2, 5.4, 12.1, 13.1; ticket 024).

7.2: when no catalogue bed clears the style's `sound.bed_score_threshold`, or no SFX is
tagged with an intent the short needs (054), the director asks this adapter one ladder
rung at a time - a few plain words, never the planner's sentence (`sound.bed_queries`,
`sound.sfx_queries`). It searches Freesound's text endpoint (one GET, the free API key as
a `Token` header, never in the URL), downloads the best result, measures it with the 023
script, runs a cue through the R1-R4 detector, and appends it to the runtime catalogue
`fetched/catalog.yaml` (056 (6): beside the fetched files, git-ignored; the tracked
`catalog.yaml` is the operator's and no job changes it) with `source: freesound`, its
licence text and its author. `sound.load_catalogue` reads the tracked file and then the
fetched one, so the result is an ordinary library entry: its rights row (5.4) is the row
every library file gets, and the next job finds it in the library without a call.

**What is fetched.** Freesound's original files need an OAuth2 grant; the previews need
only the token, so the HQ mp3 preview (else the HQ ogg) is what lands under
`<library>/fetched/` - git-ignored like every audio file - and the original's download
URL is kept on the candidate for the log. A hit with no preview is dropped.

**What it is (068).** Run04 catalogued a car exhaust as a bed and a beeping score counter
as a cue: the first hit was adopted and tagged with the query's words. Now every hit's
own name and tags are checked against the kind it is fetched for (`assets/audio/
kinds.yaml`, `sound.kinds`) before the catalogue is asked or anything is downloaded; a
miss costs one candidate and names the words. An adopted entry keeps Freesound's
`source_name` and `source_tags`, and its planner-facing tags are derived from them
(`derived_tags`), never from the query. `retag` (`seed retag`) applies the same check to
what is already in the fetched catalogue.

**What is checked.** A fetched SFX goes through R1-R4 like a seeded one (7.3) and is
rejected on any hit. A bed is one sound longer than 5 s by definition (R3) and swells by
design (R2, R4), so the detector is the cue rule and does not run on beds - the same
split as `seed check`, which runs it on the catalogue's SFX only. The measured fields
come from `seed.measure_file`; `loop_ok` is read from Freesound's own tags (`loop`,
`loopable`, `seamless`), since nothing measures a seam yet; drop points stay empty.

**What it costs.** Nothing: the key is free and the search is not metered, so no ledger
row is written (the same footing as Pexels and Pixabay, 018).

**Rights (5.4; 054 (4)).** Only CC0 and CC BY are adopted, beds and SFX alike: the
request carries `LICENCE_FILTER`, and every result's licence is checked again
(`licence_allowed`) before anything is downloaded - a CC BY-NC track the API hands back
anyway is skipped with a note. The licence text and the author travel on the entry into
the rights row and `credits.md`.

**Failure (054 (1)).** A source that cannot be reached is a `SearchPage` with its HTTP
status or `timeout` and no hits, never an exception into the mix; the director logs it.
A body that is not audio, a file ffmpeg cannot decode or a detector hit each cost one
candidate: `bed` and `sfx` try the results in Freesound's order and return the first
that is adopted in their `SearchOutcome`, with one note per candidate skipped and why. A
candidate rejected once is remembered by id and never downloaded again in this process.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from shortsmith import ffmpeg, styles
from shortsmith import sound as sound_module
from shortsmith.config import Settings
from shortsmith.contracts import AudioCandidate, AudioEntry, AudioKind, AudioTags, BedQuery
from shortsmith.sound import (
    AudioSearch,
    Library,
    SearchOutcome,
    SoundError,
    keywords,
    load_catalogue,
    parse_catalogue,
    seed,
    sweep,
)
from shortsmith.sound.kinds import BED, Kind, Kinds, load_kinds, refusal

log = logging.getLogger(__name__)

API_URL = "https://freesound.org/apiv2/search/text/"
# 068: one sound read back by id, for `seed retag`.
SOUND_URL = "https://freesound.org/apiv2/sounds/{id}/"
SOUND_FIELDS = "id,name,tags"
FIELDS = "id,name,tags,license,username,url,previews,download,duration,type"
PAGE_SIZE = 5
TIMEOUT_S = 30.0
MAX_BYTES = 30 * 1024 * 1024
SOURCE = "freesound"
FETCHED_DIR = sound_module.FETCHED_DIR
ID_PREFIX = "freesound_"
# The previews, best first: the HQ mp3 is what a bed is fetched as; ogg when there is none.
PREVIEWS: tuple[str, ...] = ("preview-hq-mp3", "preview-hq-ogg", "preview-lq-mp3", "preview-lq-ogg")
# 7.2 / 7.3: a bed has to carry a short (or loop); a cue is a hit, never over 5 s (R3).
DURATION_FILTER: Mapping[AudioKind, str] = {
    "bed": "duration:[20 TO 600]",
    "sfx": "duration:[0 TO 5]",
}
# 054 (4): Freesound's own licence names for CC0 and CC BY; the filter is in the request
# and the result is checked again by `licence_allowed`.
LICENCE_FILTER = 'license:("Attribution" OR "Creative Commons 0")'
# 069: a bed is asked for among sounds Freesound's uploaders tagged as music (run04's
# fourth rung found a car's exhaust); 068's kind check stays the backstop.
KIND_FILTER: Mapping[AudioKind, str] = {"bed": "tag:music", "sfx": ""}


def search_filter(kind: AudioKind, max_len_s: float | None = None) -> str:
    """The request's `filter`: length, then (a bed) the music tag, then the licences.
    075: `max_len_s` narrows the length to an effect kind's allowance."""
    duration = DURATION_FILTER[kind] if max_len_s is None else f"duration:[0 TO {max_len_s:g}]"
    return " ".join(p for p in (duration, KIND_FILTER[kind], LICENCE_FILTER) if p)
ALLOWED_LICENCES: tuple[str, ...] = ("CC0", "CC BY")
LOOP_TAGS = frozenset({"loop", "loopable", "seamless"})
# The licence URLs Freesound hands out, as the text the rights row carries (5.4).
LICENCE_NAMES: Mapping[str, str] = {
    "publicdomain/zero": "CC0",
    "licenses/by": "CC BY",
    "licenses/by-nc": "CC BY-NC",
    "licenses/by-sa": "CC BY-SA",
    "licenses/by-nd": "CC BY-ND",
    "licenses/by-nc-sa": "CC BY-NC-SA",
    "licenses/by-nc-nd": "CC BY-NC-ND",
    "licenses/sampling+": "CC Sampling+",
}


class Rejected(SoundError):
    """A fetched file the adapter will not catalogue: the message says which rule."""


def licence_text(url: str) -> str:
    """`http://creativecommons.org/licenses/by/4.0/` -> `CC BY 4.0`; a URL this table
    does not know is recorded as it is, and no URL at all is `unknown`."""
    if not url.strip():
        return "unknown"
    parts = [p for p in urlparse(url).path.split("/") if p]
    for i in range(len(parts) - 1):
        name = LICENCE_NAMES.get(f"{parts[i]}/{parts[i + 1]}")
        if name is not None:
            version = parts[i + 2] if i + 2 < len(parts) else ""
            return f"{name} {version}".strip()
    return url.strip()


def licence_allowed(text: str) -> bool:
    """054 (4): `CC0 1.0` and `CC BY 4.0` are adopted; `CC BY-NC`, `CC BY-SA`, an
    unknown URL or no licence at all are not."""
    return any(text == name or text.startswith(f"{name} ") for name in ALLOWED_LICENCES)


def entry_id(candidate: AudioCandidate) -> str:
    return f"{ID_PREFIX}{candidate.id}"


def derived_tags(
    kind: AudioKind, source_tags: Sequence[str], *, mood: Sequence[str] = (), intent: str = ""
) -> AudioTags:
    """068: the planner-facing tags of a fetched sound, from what Freesound says it is.
    A bed's theme is its own tags, lower-cased; its mood is those of `mood` (the query's
    mood words, or the entry's old ones on a retag) that Freesound also tagged it with.
    A cue carries the intent it was checked against. A word only in the query never
    lands."""
    own = list(dict.fromkeys(t.strip().lower() for t in source_tags if t.strip()))
    if kind == "bed":
        wanted = {m.strip().lower() for m in mood}
        return AudioTags(theme=own, mood=[t for t in own if t in wanted])
    return AudioTags(intent=[intent] if intent else [])


@dataclass(frozen=True)
class SearchPage:
    """One search's answer (054 (1)): the candidates in Freesound's order, the HTTP
    status (or `timeout` / the error class) and Freesound's own hit count."""

    candidates: tuple[AudioCandidate, ...]
    status: str
    hits: int


def _field(value: object, name: str) -> object:
    if isinstance(value, dict):
        return value.get(name)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (_text(v) for v in value) if t]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _preview(previews: object) -> str:
    for name in PREVIEWS:
        url = _text(_field(previews, name))
        if url:
            return url
    return ""


def candidate_from(hit: object, kind: AudioKind) -> AudioCandidate | None:
    """One search result as an `AudioCandidate`; None when it has no id or no preview."""
    sound_id = _field(hit, "id")
    if not isinstance(sound_id, int) or isinstance(sound_id, bool):
        return None
    preview = _preview(_field(hit, "previews"))
    if not preview:
        return None
    licence_url = _text(_field(hit, "license"))
    return AudioCandidate(
        id=str(sound_id),
        name=_text(_field(hit, "name")) or str(sound_id),
        kind=kind,
        tags=_strings(_field(hit, "tags")),
        licence=licence_text(licence_url),
        licence_url=licence_url,
        author=_text(_field(hit, "username")) or None,
        page_url=_text(_field(hit, "url")),
        preview_url=preview,
        download_url=_text(_field(hit, "download")),
        duration_s=_number(_field(hit, "duration")),
    )


class FreesoundAudioSearch(AudioSearch):
    """`search` and `fetch` are the two HTTP calls; `adopt` is the 7.2 measure-check-
    append; `beds` is what the director calls. `client` is the seam the tests replace
    with an `httpx.MockTransport`; the key is a `SecretStr` and never reaches a repr."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        page_size: int = PAGE_SIZE,
        max_bytes: int = MAX_BYTES,
        kinds: Kinds | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._timeout_s = timeout_s
        self._page_size = page_size
        self._max_bytes = max_bytes
        self._kinds = kinds
        self.searches = 0
        self._rejected: dict[str, str] = {}  # candidate id -> why, so no second download

    @property
    def kinds(self) -> Kinds:
        """`assets/audio/kinds.yaml` (068), read on first use unless given."""
        if self._kinds is None:
            self._kinds = load_kinds()
        return self._kinds

    def kind_for(self, kind: AudioKind, intent: str = "") -> Kind:
        return self.kinds.kind(BED) if kind == "bed" else self.kinds.for_sfx(intent)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._api_key.get_secret_value()}"}

    def get(self, url: str, *, params: Mapping[str, str] | None = None) -> httpx.Response:
        """One authorised GET (075: the shortlist's downloads and lookups)."""
        return self._get(url, params=params)

    def preview_url(self, sound_id: str) -> str:
        """075, `shortlist fetch-approved`: the HQ preview of one sound by id; a
        `SoundError` with the status when it cannot be read."""
        url = SOUND_URL.format(id=sound_id)
        try:
            response = self._get(url, params={"fields": "previews"})
        except httpx.HTTPError as exc:
            raise SoundError(f"{url}: {type(exc).__name__}") from None
        if response.is_error:
            raise SoundError(f"{url}: status {response.status_code}")
        try:
            body: object = response.json()
        except ValueError:
            raise SoundError(f"{url}: status {response.status_code} unreadable body") from None
        preview = _preview(_field(body, "previews"))
        if not preview:
            raise SoundError(f"{url}: no preview")
        return preview

    def _get(self, url: str, *, params: Mapping[str, str] | None = None) -> httpx.Response:
        client = self._client
        if client is not None:
            return client.get(url, params=params, headers=self._headers(), follow_redirects=True)
        with httpx.Client(timeout=self._timeout_s, follow_redirects=True) as owned:
            return owned.get(url, params=params, headers=self._headers())

    # -- the two HTTP calls --

    def search(self, query: str, kind: AudioKind, *, max_len_s: float | None = None) -> SearchPage:
        """Freesound's hits for the plain words `query`, in its order, mapped to
        candidates, with the status and the hit count for the log; a source that fails
        is a page with its status and no hits, never an exception. 075: `max_len_s` is
        an effect kind's length allowance, asked in the filter."""
        self.searches += 1
        params = {
            "query": " ".join(query.split()),
            "filter": search_filter(kind, max_len_s),
            "fields": FIELDS,
            "page_size": str(self._page_size),
        }
        try:
            response = self._get(API_URL, params=params)
        except httpx.TimeoutException:
            return SearchPage((), "timeout", 0)
        except httpx.HTTPError as exc:
            return SearchPage((), f"error {type(exc).__name__}", 0)
        status = str(response.status_code)
        if response.is_error:
            return SearchPage((), status, 0)
        try:
            body: object = response.json()
        except ValueError:
            return SearchPage((), f"{status} unreadable body", 0)
        results = _field(body, "results")
        if not isinstance(results, list):
            return SearchPage((), status, 0)
        hits: list[object] = list(results)  # pyright: ignore[reportUnknownArgumentType]
        count = _field(body, "count")
        total = count if isinstance(count, int) and not isinstance(count, bool) else len(hits)
        found: list[AudioCandidate] = []
        for hit in hits:
            candidate = candidate_from(hit, kind)
            if candidate is not None:
                found.append(candidate)
        return SearchPage(tuple(found), status, total)

    def sound_info(self, sound_id: str) -> tuple[str, list[str]]:
        """068: Freesound's own name and tags for one sound id; a `SoundError` with the
        status when it cannot be read."""
        url = SOUND_URL.format(id=sound_id)
        try:
            response = self._get(url, params={"fields": SOUND_FIELDS})
        except httpx.HTTPError as exc:
            raise SoundError(f"{url}: {type(exc).__name__}") from None
        if response.is_error:
            raise SoundError(f"{url}: status {response.status_code}")
        try:
            body: object = response.json()
        except ValueError:
            raise SoundError(f"{url}: status {response.status_code} unreadable body") from None
        return _text(_field(body, "name")), _strings(_field(body, "tags"))

    def fetch(self, candidate: AudioCandidate, *, into: Path) -> Path:
        """Download the candidate's preview to `<into>/fetched/<entry id><suffix>`; a
        download that fails, is empty or is over the cap is a `SoundError` and nothing
        is written."""
        try:
            response = self._get(candidate.preview_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SoundError(f"{candidate.preview_url} could not be downloaded: {exc}") from None
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_bytes:
            raise SoundError(
                f"{candidate.preview_url} is {int(declared) / 1024 / 1024:.1f} MB, over the "
                f"{self._max_bytes // 1024 // 1024} MB limit"
            )
        body = response.content
        if not body:
            raise SoundError(f"{candidate.preview_url} answered an empty body")
        if len(body) > self._max_bytes:
            raise SoundError(
                f"{candidate.preview_url} is {len(body) / 1024 / 1024:.1f} MB, over the "
                f"{self._max_bytes // 1024 // 1024} MB limit"
            )
        suffix = Path(urlparse(candidate.preview_url).path).suffix or ".mp3"
        path = into / FETCHED_DIR / f"{entry_id(candidate)}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    # -- 7.2: measure, check, score, append --

    def adopt(
        self,
        candidate: AudioCandidate,
        *,
        library: Library,
        mood: Sequence[str] = (),
        intent: str = "",
        whoosh_max_len_s: float | None = None,
    ) -> AudioEntry:
        """Fetch `candidate` into `library`, measure it (023), run a cue through R1-R4,
        and append it to the library's catalogue with Freesound's own name and tags and
        the tags `derived_tags` reads from them (068) - never the query's words.
        `Rejected` on a detector hit; `SoundError` when it cannot be fetched or read. A
        rejected or unreadable file is removed. The kind check runs before this, in
        `_first_adopted`, so nothing refused is ever downloaded.

        060 (5): a file fetched for the `whoosh` intent under an allowance
        (`whoosh_max_len_s`, the style's `sound.whoosh.max_len_s`) is exempt from the
        detector - a whoosh is a noise sweep by nature - when it is no longer than that;
        a longer one is rejected naming its length. Any other intent, or no allowance,
        runs the detector as before."""
        path = self.fetch(candidate, into=library.root)
        try:
            measured = seed.measure_file(path, kind=candidate.kind)
            if candidate.kind == "sfx":
                exempt = styles.is_whoosh(intent) and whoosh_max_len_s is not None
                if whoosh_max_len_s is not None and exempt and (
                    measured.duration_s > whoosh_max_len_s + 1e-3
                ):
                    raise Rejected(
                        f"{candidate.name} ({candidate.page_url}): {measured.duration_s:.2f} s "
                        f"long, over sound.whoosh.max_len_s {whoosh_max_len_s:g} (060)"
                    )
                hits = [] if exempt else sweep.detect(path)
                if hits:
                    hit = hits[0]
                    raise Rejected(
                        f"{candidate.name} ({candidate.page_url}): {hit.rule} at "
                        f"{hit.at_s:.2f} s: {hit.detail}"
                    )
        except ffmpeg.FFmpegError as exc:
            path.unlink(missing_ok=True)
            raise SoundError(
                f"{candidate.name} ({candidate.page_url}): not readable audio: {exc}"
            ) from None
        except Rejected:
            path.unlink(missing_ok=True)
            raise
        entry = AudioEntry(
            id=entry_id(candidate),
            kind=candidate.kind,
            file=path.relative_to(library.root).as_posix(),
            source=SOURCE,
            source_url=candidate.page_url,
            source_name=candidate.name,
            source_tags=list(candidate.tags),
            licence=candidate.licence,
            author=candidate.author,
            duration_s=measured.duration_s,
            bpm=measured.bpm,
            key=measured.key,
            tags=derived_tags(candidate.kind, candidate.tags, mood=mood, intent=intent),
            drop_points_s=[],
            loop_ok=candidate.kind == "bed" and bool(LOOP_TAGS & {t.lower() for t in candidate.tags}),  # noqa: E501
            energy=measured.energy,
        )
        # 056 (6): the runtime catalogue, never the tracked one.
        append_entry(library.fetched_catalogue, entry)
        return entry

    def bed(self, words: str, query: BedQuery, library: Library) -> SearchOutcome:
        """The director's bed call for one ladder rung (7.2, 054 (2)): the first result
        that is a bed by its own name and tags (068) and is adopted; its mood tags are the
        query's mood words Freesound also used."""
        return self._first_adopted(words, "bed", library, mood=keywords(query.mood))

    def sfx(
        self, words: str, intent: str, library: Library, *, whoosh_max_len_s: float | None = None
    ) -> SearchOutcome:
        """The director's SFX call for one ladder rung (054 (3)): the first result that
        passes R1-R4, tagged with `intent`; a whoosh under its allowance instead (060)."""
        return self._first_adopted(
            words, "sfx", library, intent=intent, whoosh_max_len_s=whoosh_max_len_s
        )

    def _first_adopted(
        self,
        words: str,
        kind: AudioKind,
        library: Library,
        *,
        mood: Sequence[str] = (),
        intent: str = "",
        whoosh_max_len_s: float | None = None,
    ) -> SearchOutcome:
        """Freesound's order is kept; a result already in the catalogue is reused without
        a download; a licence outside CC0 / CC BY, a name and tags that do not fit the
        kind (068, checked before the catalogue is even asked, so a mislabelled entry is
        never reused), a candidate rejected earlier, a failed fetch or a detector hit
        each cost one candidate and leave one note."""
        page = self.search(words, kind)
        checked = self.kind_for(kind, intent)
        notes: list[str] = []
        adopted: AudioEntry | None = None
        for candidate in page.candidates:
            where = f"{SOURCE}: {candidate.name} ({candidate.page_url})"
            if not licence_allowed(candidate.licence):
                notes.append(f"{where} skipped: licence {candidate.licence} is not CC0 or CC BY")
                continue
            why = refusal(checked, candidate.name, candidate.tags)
            if why is not None:
                notes.append(f"{where} skipped: {why}")
                log.info("freesound: %s skipped: %s", candidate.name, why)
                continue
            if candidate.id in self._rejected:
                notes.append(f"{where} rejected earlier: {self._rejected[candidate.id]}")
                continue
            known = load_catalogue(library.catalogue).entry(entry_id(candidate))
            if known is not None:
                adopted = known
                break
            try:
                adopted = self.adopt(
                    candidate, library=library, mood=mood, intent=intent,
                    whoosh_max_len_s=whoosh_max_len_s,
                )  # fmt: skip
            except SoundError as exc:
                self._rejected[candidate.id] = str(exc)
                notes.append(f"{where} skipped: {exc}")
                log.warning("freesound: %s skipped: %s", candidate.name, exc)
                continue
            log.info("freesound: %s adopted for %s %r", adopted.id, kind, words)
            break
        return SearchOutcome(
            source=SOURCE, kind=kind, query=words, status=page.status, hits=page.hits,
            adopted=adopted, notes=tuple(notes),
        )  # fmt: skip


def append_entry(catalogue: Path, entry: AudioEntry) -> None:
    """Append `entry` to the catalogue file (created with an empty list when it is not
    there), keeping the header comment; the result is validated before it is written."""
    text = catalogue.read_text(encoding="utf-8") if catalogue.is_file() else "entries: []\n"
    entries = [*seed.raw_entries(text), seed.entry_dict(entry)]
    new_text = seed.catalogue_text(text, entries)
    parse_catalogue(new_text, name=catalogue.name)  # SoundError names the problem
    catalogue.parent.mkdir(parents=True, exist_ok=True)
    catalogue.write_text(new_text, encoding="utf-8")


def retag(catalogue: Path, search: FreesoundAudioSearch) -> int:
    """068, `seed retag`: read every Freesound entry of the fetched catalogue beside
    `catalogue` back by id, keep its source name and tags and re-derive its tags, and
    remove every entry - and its file - whose own name and tags fail its kind. One line
    per entry. The tracked `catalogue` is never touched. Any entry that cannot be read
    back stops the command before anything is written or removed (exit 1)."""
    fetched = catalogue.parent / FETCHED_DIR / sound_module.CATALOGUE_NAME
    if not fetched.is_file():
        print(f"no fetched catalogue at {fetched}")
        return 0
    text = fetched.read_text(encoding="utf-8")
    name = f"{FETCHED_DIR}/{fetched.name}"
    entries = parse_catalogue(text, name=name).entries
    kept: list[AudioEntry] = []
    removed: list[AudioEntry] = []
    lines: list[str] = []
    failures: list[str] = []
    for entry in entries:
        if entry.source != SOURCE or not entry.id.startswith(ID_PREFIX):
            kept.append(entry)
            lines.append(f"{entry.id}: kept (source {entry.source}, not read back)")
            continue
        try:
            source_name, source_tags = search.sound_info(entry.id.removeprefix(ID_PREFIX))
        except SoundError as exc:
            failures.append(f"{entry.id}: could not be read back: {exc}")
            continue
        intent = entry.tags.intent[0] if entry.tags.intent else ""
        kind = search.kind_for(entry.kind, intent)
        why = refusal(kind, source_name, source_tags)
        if why is not None:
            removed.append(entry)
            lines.append(f"{entry.id}: removed ({source_name!r}: {why})")
            continue
        tags = derived_tags(entry.kind, source_tags, mood=entry.tags.mood, intent=intent)
        kept.append(entry.model_copy(
            update={"source_name": source_name, "source_tags": source_tags, "tags": tags}
        ))  # fmt: skip
        lines.append(f"{entry.id}: kept as {kind.name} ({source_name!r})")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"{name} not written; nothing removed", file=sys.stderr)
        return 1
    new_text = seed.catalogue_text(text, [seed.entry_dict(e) for e in kept])
    parse_catalogue(new_text, name=name)  # SoundError names the problem
    fetched.write_text(new_text, encoding="utf-8")
    root = catalogue.parent
    for entry in removed:
        (root / entry.file).unlink(missing_ok=True)
    for line in lines:
        print(line)
    print(f"{len(kept)} kept, {len(removed)} removed from {name}")
    return 0


def from_settings(settings: Settings) -> AudioSearch | None:
    """The configured runtime audio search: Freesound with `FREESOUND_API_KEY`, none
    without (the director then has no search and says so in the job log and, when the
    short goes out voice-only, on the job page; 054 (5))."""
    if settings.freesound_api_key is None:
        return None
    return FreesoundAudioSearch(api_key=settings.freesound_api_key)
