"""The Freesound audio search: the runtime rung under the local catalogue (decisions
7.1, 7.2, 5.4, 12.1, 13.1; ticket 024).

7.2: when no catalogue bed clears the style's `sound.bed_score_threshold`, or no SFX is
tagged with an intent the short needs (054), the director asks this adapter one ladder
rung at a time - a few plain words, never the planner's sentence (`sound.bed_queries`,
`sound.sfx_queries`). It searches Freesound's text endpoint (one GET, the free API key as
a `Token` header, never in the URL), downloads the best result, measures it with the 023
script, runs a cue through the R1-R4 detector, and appends it to `catalog.yaml` with
`source: freesound`, its licence text and its author. The result is an ordinary library
entry, so its rights row (5.4) is the row every library file gets, and the next job
finds it in the catalogue without a call.

**What is fetched.** Freesound's original files need an OAuth2 grant; the previews need
only the token, so the HQ mp3 preview (else the HQ ogg) is what lands under
`<library>/fetched/` - git-ignored like every audio file - and the original's download
URL is kept on the candidate for the log. A hit with no preview is dropped.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from shortsmith import ffmpeg
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

log = logging.getLogger(__name__)

API_URL = "https://freesound.org/apiv2/search/text/"
FIELDS = "id,name,tags,license,username,url,previews,download,duration,type"
PAGE_SIZE = 5
TIMEOUT_S = 30.0
MAX_BYTES = 30 * 1024 * 1024
SOURCE = "freesound"
FETCHED_DIR = "fetched"
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
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._timeout_s = timeout_s
        self._page_size = page_size
        self._max_bytes = max_bytes
        self.searches = 0
        self._rejected: dict[str, str] = {}  # candidate id -> why, so no second download

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._api_key.get_secret_value()}"}

    def _get(self, url: str, *, params: Mapping[str, str] | None = None) -> httpx.Response:
        client = self._client
        if client is not None:
            return client.get(url, params=params, headers=self._headers(), follow_redirects=True)
        with httpx.Client(timeout=self._timeout_s, follow_redirects=True) as owned:
            return owned.get(url, params=params, headers=self._headers())

    # -- the two HTTP calls --

    def search(self, query: str, kind: AudioKind) -> SearchPage:
        """Freesound's hits for the plain words `query`, in its order, mapped to
        candidates, with the status and the hit count for the log; a source that fails
        is a page with its status and no hits, never an exception."""
        self.searches += 1
        params = {
            "query": " ".join(query.split()),
            "filter": f"{DURATION_FILTER[kind]} {LICENCE_FILTER}",
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
        theme: Sequence[str] = (),
        mood: Sequence[str] = (),
        intent: str = "",
    ) -> AudioEntry:
        """Fetch `candidate` into `library`, measure it (023), run a cue through R1-R4,
        and append it to the library's catalogue tagged with the query words it
        answered. `Rejected` on a detector hit; `SoundError` when it cannot be fetched
        or read. A rejected or unreadable file is removed."""
        path = self.fetch(candidate, into=library.root)
        try:
            measured = seed.measure_file(path, kind=candidate.kind)
            if candidate.kind == "sfx":
                hits = sweep.detect(path)
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
            licence=candidate.licence,
            author=candidate.author,
            duration_s=measured.duration_s,
            bpm=measured.bpm,
            key=measured.key,
            tags=AudioTags(theme=list(theme), mood=list(mood), intent=[intent] if intent else []),
            drop_points_s=[],
            loop_ok=candidate.kind == "bed" and bool(LOOP_TAGS & {t.lower() for t in candidate.tags}),  # noqa: E501
            energy=measured.energy,
        )
        append_entry(library.catalogue, entry)
        return entry

    def bed(self, words: str, query: BedQuery, library: Library) -> SearchOutcome:
        """The director's bed call for one ladder rung (7.2, 054 (2)): the first result
        that is adopted, tagged with the query's theme and mood words."""
        return self._first_adopted(
            words, "bed", library, theme=keywords(query.theme), mood=keywords(query.mood)
        )

    def sfx(self, words: str, intent: str, library: Library) -> SearchOutcome:
        """The director's SFX call for one ladder rung (054 (3)): the first result that
        passes R1-R4, tagged with `intent`."""
        return self._first_adopted(words, "sfx", library, intent=intent)

    def _first_adopted(
        self,
        words: str,
        kind: AudioKind,
        library: Library,
        *,
        theme: Sequence[str] = (),
        mood: Sequence[str] = (),
        intent: str = "",
    ) -> SearchOutcome:
        """Freesound's order is kept; a result already in the catalogue is reused without
        a download; a licence outside CC0 / CC BY, a candidate rejected earlier, a failed
        fetch or a detector hit each cost one candidate and leave one note."""
        page = self.search(words, kind)
        notes: list[str] = []
        adopted: AudioEntry | None = None
        for candidate in page.candidates:
            where = f"{SOURCE}: {candidate.name} ({candidate.page_url})"
            if not licence_allowed(candidate.licence):
                notes.append(f"{where} skipped: licence {candidate.licence} is not CC0 or CC BY")
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
                    candidate, library=library, theme=theme, mood=mood, intent=intent
                )
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


def from_settings(settings: Settings) -> AudioSearch | None:
    """The configured runtime audio search: Freesound with `FREESOUND_API_KEY`, none
    without (the director then has no search and says so in the job log and, when the
    short goes out voice-only, on the job page; 054 (5))."""
    if settings.freesound_api_key is None:
        return None
    return FreesoundAudioSearch(api_key=settings.freesound_api_key)
