"""The sound director (PRD `sound`; decisions 7.1, 7.2, 7.3, 5.4; ticket 022).

Sound is a director, not a hit table (7.1). This module is the whole of it: the text
catalogue, the bed choice, the floor hits, the cue matching, the mood envelope and the
research §5 mix graph. Everything above the ffmpeg calls is pure and measured in tests;
every number it obeys comes from the style's `sound` front matter (7.3), never from code.

**Catalogue (7.2).** `assets/audio/catalog.yaml` is the library as text: one entry per
file with its licence, its measured `duration_s` / `bpm` / `key` / `energy`, its
hand-written `theme` / `mood` / `intent` tags and its drop points. `load_catalogue`
returns a `Library` - the parsed entries plus the directory their `file` paths are
relative to. A missing catalogue is an empty library, not an error: the shipped file is
empty until the operator seeds it by hand (ticket 025), and an empty library simply
leaves the voice alone. The planner reads `Library.tags()` as text and never names a
track.

**Bed (7.2).** `select_bed` scores every bed by tag overlap (theme, mood) less the
energy distance, so a tag hit always outranks a closer energy; ties go to the bed whose
drop point lands nearest the first stamp. Below the style's `sound.bed_score_threshold`
(the shipped 0.5 reads "no tag hit at all") `choose_bed` asks the `AudioSearch` adapter
and the library it may grow: `sound.freesound` (024) searches, fetches, measures, checks
and appends the result to the catalogue with its licence and author, so the rights row
is an ordinary library row; `FakeAudioSearch` answers from a shelf of catalogue entries
and records every query, so no test reaches the network.

**The bed per story part (076).** A sound story names its story `parts` and a `bed` of
one or two segments `{part_from, mood, flavour?}` from the closed list of `moods.yaml`.
`score_candidates` gives each segment the best approved bed of its mood (`mood_beds`: a
flavour match first, then the energy distance to `bed_query.energy`, then the drop fit;
`fetched/` never), and the one change sits on the second segment's part start with the
planned `how`. `span_gates` renders it with sample-exact fades - an equal-power
`bed_crossfade_s` crossfade, a hard cut faded over `bed_cut_fade_s`, or `bed_silence_s`
of nothing between the beds - each bed in its own stem (`music.1.wav`, `music.2.wav`,
summed into `music.wav`), levelled where it plays alone, the envelope inside each. The
balance measures each bed's window and the crossfade too (`balance_windows`). A failed
two-bed mix drops the change for the first segment's beds alone. A segment with no
approved bed drops the change and asks the search for one bed of that mood
(`FALLBACK_LINE`, on the job page and in `job.log`); so does a mood whose approved beds all
fail the balance. A story from before 076 (no `bed`) is scored by its `bed_query` below.
087: a flavour or mood miss first takes an approved bed tagged `facts_default` (the bed
fact channels use, `sound.facts_default`) with `FACTS_DEFAULT_LINE` - before a same-mood
bed of another flavour where the style's `sound.facts_default_first` says so, after it
otherwise (`segment_beds`); the search only runs when the library has no such bed. A
speech-band line names the bed level it was measured at (`level_note`).

**Search ladders (054).** F1 went out silent: the planner's whole theme and mood
sentences were one query, and the empty shipped catalogue returned before the search
was even asked. Now the search is asked with plain keywords, specific to broad
(`bed_queries`: theme and mood words, fewer of them, the mood alone, one mood word,
then the style's `sound.default_bed_query`; every rung at most `QUERY_MAX_WORDS`),
stopping at the first adoption. 070: effects are never searched for at job time - they
come only from the approved library (below). Only CC0 and CC BY files are adopted. Every
search is one `SearchOutcome` - source, query, status, hit count, what was adopted and
why the rest were skipped - and `build_mix` hands every line to the job log as it is
made, then the placement decisions, then the summary; a short that goes out voice-only
says why (`NO_SEARCH_LINE`, `SEARCH_EMPTY_LINE`) on the job page as well.

**Floor hits (7.1).** The Dyson v2 mechanical hits are derived from plan events as the
guaranteed floor so a short is never flat: `floor_hits` reads the style's
`sound.floor_hits` map (which hit class each event earns) and the plan (which beats earn
which events). A whip cut, a punch-in, a ring and a lower-third earn nothing, because no
style names them. A `counter` (029) lands as a stamp does and earns the stamp's class; its
hit, and any `event` cue on its beat, fires where its digits land - the last
`broll.motion.stamp.duration_s` of the beat (`landing_s`) - not at the beat's start.

**Cues (7.1, 7.3; the closed palette of 070).** Every cue is one kind of `CUE_KINDS` -
tick, whoosh, bass, drum, thump, ding - and plays the shortest file of that kind in the
approved library (the tracked catalogue, never `fetched/`) no longer than the style's
length for it (`kind_max_len_s`); a kind with no such file drops its cues with a line.
One cue per beat (`cues_per_beat_max`): the planner's cue when it named one for that beat,
then the changeover a drop needs, then the beat's floor hit, then the soft marks the
director derives itself (`mark_candidates`: a tick on each pop-in, a whoosh on each
non-cut enter the whoosh row names, a ding instead of the tick on an `idea` sticker),
each kind - the planner's and the derived together - within its row's `max_per_60s`
and `min_gap_s`. The kind sets the level: every cue sits in the style's
`cue_db_min`-`cue_db_max` band under the voice, the drum at the top, then the bass and
the changeover, then the thump and the whoosh, the tick and the ding softest. The
changeover plays the approved bass. `cues_max_per_60s` counts all of them together; over
the cap the classed cues are kept first (drum and changeover, then bass, then thump,
earlier before later) and the soft marks fill what is left.

**Envelope (7.3).** `envelope` turns the mood curve into the music stem's volume
automation: levels clipped to `swell_max_db` / `drop_min_db`, ramps left as they are, and
a fall faster than `ramp_min_s` realised as a step - the level holds until the beat
boundary and drops there - with a changeover cue scheduled on the step.

**Mix (7.3, research §5).** `build_mix` writes `work/stems/{voice,music,sfx}.wav` and the
premix the master is cut from, plus `work/stems/balance.json` and `work/stems/cues.json`
(023: every cue's start and end, so gate T6 can name the cue a sweep hit falls in).
The bed is looped or padded to the runtime, level-matched to `bed_db_under_voice` under
the voice's RMS, run through the envelope and the style's fades, then ducked under the
voice with the 7.3 sidechain (threshold 0.06, ratio 2, attack 20, release 400). Each cue
is delayed to its time and peak-matched to its class level. The acceptance is in code:
the bed's median must sit inside `bed_accept_db` under the voice, the speech band must
clear the bed by `speech_band_margin_db` and by no more than `speech_band_margin_max_db`
(069: past it a phone speaker plays nothing of the bed; `audibility` is that check on
two files), and the ducking must stay under `duck_max_db`
- outside any of them the step fails with the measured numbers, after writing the report.

**No sweeps (7.3; 023).** `sound.sweep` is the R1-R4 detector gate T6 runs on the SFX
stem, and `sound.seed` the seed-time commands: `check` runs it on every catalogue SFX,
`measure` fills each entry's `duration_s` / `bpm` / `key` / `energy`.

**Rights (5.4).** `rights_rows` gives the bed and every SFX file its row with origin
`library` and the catalogue's source URL; the renderer writes them beside the asset rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from shortsmith import ffmpeg, styles
from shortsmith.contracts import (
    CUE_KINDS,
    FACTS_DEFAULT,
    AudioEntry,
    AudioKind,
    BalanceReport,
    BalanceWindow,
    Beat,
    BedHow,
    BedQuery,
    BedSegment,
    Catalogue,
    Cue,
    CueRecord,
    CueSheet,
    PicturePlan,
    RightsRow,
    SoundStory,
)
from shortsmith.sound.kinds import BED, Kinds, load_kinds, refusal

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE_NAME = "catalog.yaml"
CATALOGUE_PATH = REPO_ROOT / "assets" / "audio" / CATALOGUE_NAME
# 056 (6): what the runtime search fetches lives beside the files it describes, in the
# git-ignored `fetched/` folder, so a job never changes the tracked catalogue.
FETCHED_DIR = "fetched"
SAMPLE_RATE = ffmpeg.SAMPLE_RATE
MIX_TIMEOUT_S = 1800.0
MONO = f"aformat=channel_layouts=mono:sample_rates={SAMPLE_RATE}"


class SoundError(RuntimeError):
    """The catalogue is broken, or the mix missed the 7.3 acceptance band."""


# --- the catalogue (7.2) ----------------------------------------------------------------


@dataclass(frozen=True)
class Library:
    """The parsed catalogue and the directory its `file` paths are relative to.
    `fetched` names the entries read from the runtime `fetched/` catalogue (070: never
    an effect a job may play; only the tracked catalogue is the approved library)."""

    root: Path
    entries: tuple[AudioEntry, ...] = ()
    fetched: frozenset[str] = frozenset()

    @property
    def catalogue(self) -> Path:
        """The tracked text file under `root`: the operator's hand-seeded catalogue
        (7.2), which `seed` writes and no job ever changes (056 (6))."""
        return self.root / CATALOGUE_NAME

    @property
    def fetched_catalogue(self) -> Path:
        """The runtime catalogue the audio search appends to (024; 056 (6)): under the
        git-ignored `fetched/` folder beside the files it describes, read after the
        tracked one by `load_catalogue`. Its `file` paths stay relative to `root`."""
        return self.root / FETCHED_DIR / CATALOGUE_NAME

    def beds(self) -> tuple[AudioEntry, ...]:
        return tuple(e for e in self.entries if e.kind == "bed")

    def sfx(self) -> tuple[AudioEntry, ...]:
        return tuple(e for e in self.entries if e.kind == "sfx")

    def approved_sfx(self) -> tuple[AudioEntry, ...]:
        """070: the effects a job may play - those the operator approved into the
        tracked catalogue (075), never one a runtime search fetched."""
        return tuple(e for e in self.sfx() if e.id not in self.fetched)

    def adding(self, entry: AudioEntry) -> Library:
        """This library with `entry` appended (a bed the search adopted, 054)."""
        if self.entry(entry.id) is not None:
            return self
        return replace(self, entries=(*self.entries, entry))

    def entry(self, entry_id: str) -> AudioEntry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def file(self, entry: AudioEntry) -> Path:
        return (self.root / entry.file).resolve()

    def tags(self) -> tuple[str, ...]:
        """Every tag in the library, sorted and unique: what the sound call is told the
        library holds (8.1). The planner picks from these words, never from filenames."""
        found: set[str] = set()
        for e in self.entries:
            found |= {*e.tags.theme, *e.tags.mood, *e.tags.intent}
        return tuple(sorted(found))


def parse_catalogue(text: str, *, name: str) -> Catalogue:
    loaded: object = yaml.safe_load(text)
    if loaded is None:
        return Catalogue()
    if not isinstance(loaded, dict):
        raise SoundError(f"{name}: the catalogue is not a mapping with an `entries` list")
    try:
        return Catalogue.model_validate(loaded)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise SoundError(f"{name}: invalid catalogue: {problems}") from None


def load_catalogue(path: Path = CATALOGUE_PATH) -> Library:
    """The library at `path`: the tracked catalogue, then (056 (6)) the runtime
    adoptions in `fetched/catalog.yaml` beside it, a fetched id the tracked file already
    holds left out. A file that is not there is an empty library (7.2: the shipped
    catalogue is empty until the operator seeds it by hand, ticket 025)."""
    entries: list[AudioEntry] = []
    if path.is_file():
        entries += parse_catalogue(path.read_text(encoding="utf-8"), name=path.name).entries
    fetched = path.parent / FETCHED_DIR / CATALOGUE_NAME
    runtime: list[AudioEntry] = []
    if fetched.is_file():
        known = {e.id for e in entries}
        name = f"{FETCHED_DIR}/{fetched.name}"
        adopted = parse_catalogue(fetched.read_text(encoding="utf-8"), name=name).entries
        runtime = [e for e in adopted if e.id not in known]
    return Library(
        root=path.parent,
        entries=(*entries, *runtime),
        fetched=frozenset(e.id for e in runtime),
    )


# --- bed selection (7.2) ----------------------------------------------------------------

# A tag hit is worth 1, so the energy distance (at most 4) can only order beds that
# already agree on the tags; the style's `sound.bed_score_threshold` of 0.5 therefore
# reads "at least one tag matched" (7.2; the number lives in the front matter, 024).
ENERGY_WEIGHT = 0.1


def bed_score(entry: AudioEntry, query: BedQuery) -> float:
    """Tag overlap (theme, mood) less the energy distance (7.2)."""
    overlap = sum(
        1
        for wanted, tagged in ((query.theme, entry.tags.theme), (query.mood, entry.tags.mood))
        if wanted.strip().lower() in {t.strip().lower() for t in tagged}
    )
    return overlap - ENERGY_WEIGHT * abs(entry.energy - query.energy)


def drop_fit(entry: AudioEntry, first_stamp_s: float) -> float:
    """How near the bed's nearest drop point lands to the first stamp; a bed with no
    drop points fits worst (7.2)."""
    if not entry.drop_points_s:
        return math.inf
    return min(abs(d - first_stamp_s) for d in entry.drop_points_s)


def select_bed(
    library: Library, query: BedQuery, *, first_stamp_s: float, threshold: float
) -> AudioEntry | None:
    """The best-scoring bed, ties broken by drop-point fit; None under `threshold`
    (the style's `sound.bed_score_threshold`)."""
    beds = library.beds()
    if not beds:
        return None
    best = min(
        beds, key=lambda e: (-bed_score(e, query), drop_fit(e, first_stamp_s), e.id)
    )
    return best if bed_score(best, query) >= threshold else None


# --- the search ladders (054) ------------------------------------------------------------

# A text search over a sound library wants a few plain words, not the planner's sentence
# (F1's "Himalayan spiritual documentary, tanpura drone with soft tabla pulse and low
# synth" matched nothing). Each rung is at most this many words; the rungs go from
# specific to broad and the style's `sound.default_bed_query` is always the last try.
QUERY_MAX_WORDS = 6
STOPWORDS = frozenset(
    ["a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is", "it", "its", "of",
     "on", "or", "the", "to", "with", "over", "under", "that", "this", "these", "those",
     "some", "very"]
)  # fmt: skip
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
NO_SEARCH_LINE = "no audio search configured"
SEARCH_EMPTY_LINE = "every audio search came back empty"


def keywords(text: str) -> list[str]:
    """The plain lower-case words of `text`, stopwords and repeats gone, in order."""
    out: list[str] = []
    for word in _WORD.findall(text.lower()):
        if word not in STOPWORDS and word not in out:
            out.append(word)
    return out


def _rungs(*candidates: Sequence[str], anchor: Sequence[str] = ()) -> tuple[str, ...]:
    """Each candidate as one rung of at most `QUERY_MAX_WORDS`, repeats gone. 069: the
    `anchor` words end every rung, the candidate's own words cut to make room."""
    out: list[str] = []
    room = QUERY_MAX_WORDS - len(anchor)
    for words in candidates:
        own = [w for w in words if w not in anchor][:room]
        rung = " ".join([*own, *anchor] if own else [])
        if rung and rung not in out:
            out.append(rung)
    return tuple(out)


def bed_queries(query: BedQuery, default: str, anchor: str = "") -> tuple[str, ...]:
    """The bed search's queries, specific to broad (054 (2)): keywords from the theme and
    the mood, fewer of them, the mood alone, one mood word, then the style's default.
    069: every rung carries the style's `sound.bed_query_anchor` ("music"), so the
    ladder never narrows to a word that is not about music (run04's `'regal'`)."""
    theme, mood = keywords(query.theme), keywords(query.mood)
    return _rungs(
        theme[:3] + mood[:3],
        theme[:2] + mood[:1],
        mood[:3],
        mood[:1],
        keywords(default),
        anchor=keywords(anchor),
    )


def sfx_queries(intent: str) -> tuple[str, ...]:
    """The SFX search's queries for one intent (054 (3)): a floor class asks for its hit
    ("bass hit") and then the class word alone; any other intent asks with its words.
    070: a job never searches for an effect; the Freesound adapter keeps the ladder."""
    if intent in styles.FLOOR_CLASSES:
        return (f"{intent} hit", intent)
    return _rungs(keywords(intent.replace("_", " ")))


@dataclass(frozen=True)
class SearchOutcome:
    """One search of one source (054 (1)): what was asked, what the source answered
    (an HTTP status or the error, and its hit count), what was adopted, and one note per
    candidate that was skipped and why. `line()` is the job-log line."""

    source: str
    kind: AudioKind
    query: str
    status: str
    hits: int
    adopted: AudioEntry | None = None
    notes: tuple[str, ...] = ()

    def line(self) -> str:
        taken = f", adopted {self.adopted.id}" if self.adopted is not None else ""
        return (
            f"audio search {self.source} {self.kind} {self.query!r}: status {self.status}, "
            f"{self.hits} hits{taken}"
        )


class AudioSearch(ABC):
    """The runtime audio search (7.2): asked one ladder rung at a time when the library
    has no bed over the threshold or no SFX for an intent, and given the library so what
    it finds can be measured, checked and appended to that catalogue (`sound.freesound`,
    024). Never raises into the mix: a source that fails is an outcome with its status."""

    @abstractmethod
    def bed(self, words: str, query: BedQuery, library: Library) -> SearchOutcome:
        """Search `words` for a bed and adopt the first result that passes; the query
        is what the adopted entry is tagged with."""

    @abstractmethod
    def sfx(
        self, words: str, intent: str, library: Library, *, whoosh_max_len_s: float | None = None
    ) -> SearchOutcome:
        """Search `words` for a cue and adopt the first result that passes the sweep
        detector, tagged with `intent`. 060 (5): for the `whoosh` intent alone,
        `whoosh_max_len_s` is the style's `sound.whoosh.max_len_s` - a file no longer
        than it is exempt from the detector, a longer one is refused; None means the
        style allows no whoosh and the detector runs as for any cue."""


def kind_refusal(entry: AudioEntry, intent: str, kinds: Kinds) -> str | None:
    """068: why a catalogued entry is not the kind it is wanted for, judged on its
    source's own name and tags (`kinds.yaml`); None when it is. An entry with no source
    name was seeded by hand after the operator listened, so its tags stand."""
    if entry.source_name is None:
        return None
    kind = kinds.kind(BED) if entry.kind == "bed" else kinds.for_sfx(intent)
    return refusal(kind, entry.source_name, entry.source_tags)


class FakeAudioSearch(AudioSearch):
    """12.1: answers from a shelf of catalogue entries - the library it is asked with,
    unless given one - so no test reaches the network, and records every query so a
    test can assert the ladder. An empty shelf makes every search a miss. 068: a shelf
    entry whose source name and tags fail the kind is refused with a note, as the
    Freesound adapter refuses a hit."""

    def __init__(self, shelf: Library | None = None, *, kinds: Kinds | None = None) -> None:
        self.shelf = shelf
        self.calls: list[str] = []
        self.sfx_calls: list[str] = []
        self.sfx_max_len_s: list[float | None] = []
        self._kinds = kinds

    @property
    def kinds(self) -> Kinds:
        if self._kinds is None:
            self._kinds = load_kinds()
        return self._kinds

    def _shelf(self, library: Library) -> Library:
        return self.shelf if self.shelf is not None else library

    def _checked(
        self, entries: Iterable[AudioEntry], intent: str
    ) -> tuple[list[AudioEntry], tuple[str, ...]]:
        kept: list[AudioEntry] = []
        notes: list[str] = []
        for entry in entries:
            why = kind_refusal(entry, intent, self.kinds)
            if why is None:
                kept.append(entry)
            else:
                notes.append(f"fake: {entry.source_name} ({entry.id}) skipped: {why}")
        return kept, tuple(notes)

    def bed(self, words: str, query: BedQuery, library: Library) -> SearchOutcome:
        self.calls.append(words)
        shelved = self._shelf(library).beds()
        beds, notes = self._checked(shelved, BED)
        best = min(beds, key=lambda e: (abs(e.energy - query.energy), e.id)) if beds else None
        return SearchOutcome("fake", "bed", words, "200", len(shelved), adopted=best, notes=notes)

    def sfx(
        self, words: str, intent: str, library: Library, *, whoosh_max_len_s: float | None = None
    ) -> SearchOutcome:
        self.sfx_calls.append(words)
        self.sfx_max_len_s.append(whoosh_max_len_s)
        limit = whoosh_max_len_s if styles.is_whoosh(intent) else None
        shelf = self._shelf(library)
        wanted = intent.strip().lower()
        tagged = [e for e in shelf.sfx() if wanted in {t.strip().lower() for t in e.tags.intent}]
        kept, notes = self._checked(tagged, intent)
        refused = {e.id for e in tagged} - {e.id for e in kept}
        clean = Library(shelf.root, tuple(e for e in shelf.entries if e.id not in refused))
        found = match_sfx(intent, clean, max_duration_s=limit)
        return SearchOutcome(
            "fake", "sfx", words, "200", int(found is not None), adopted=found, notes=notes
        )


def bed_candidates(
    library: Library,
    query: BedQuery,
    *,
    first_stamp_s: float,
    threshold: float,
    search: AudioSearch | None = None,
    default_query: str = "",
    anchor: str = "",
) -> Iterator[tuple[AudioEntry | None, tuple[str, ...]]]:
    """The beds to try, best first, each with the lines the job log gets (054 (1)):
    every library bed over `threshold` in `select_bed`'s order, then the search ladder
    `bed_queries` rung by rung (7.2, 054 (2)), one item per adoption. The last item is
    `(None, why)` when the ladder runs out. 056 (1) walks on to the next candidate when
    a bed fails the 7.3 balance after every repair; `choose_bed` stops at the first."""
    beds = sorted(
        library.beds(), key=lambda e: (-bed_score(e, query), drop_fit(e, first_stamp_s), e.id)
    )
    for entry in beds:
        score = bed_score(entry, query)
        if score >= threshold:
            yield entry, (f"bed {entry.id} from the library (score {score:.2f})",)
    asked = f"no bed for theme {query.theme!r} mood {query.mood!r}"
    if search is None:
        yield None, (f"{asked}: nothing in the library scored and {NO_SEARCH_LINE}",)
        return
    for words in bed_queries(query, default_query, anchor):
        outcome = search.bed(words, query, library)
        lines = [outcome.line(), *outcome.notes]
        if outcome.adopted is not None:
            lines.append(f"bed {outcome.adopted.id} from the audio search (query {words!r})")
            yield outcome.adopted, tuple(lines)
        else:
            yield None, tuple(lines)
    yield None, (f"{asked}: nothing in the library scored and {SEARCH_EMPTY_LINE}",)


def choose_bed(
    library: Library,
    query: BedQuery,
    *,
    first_stamp_s: float,
    threshold: float,
    search: AudioSearch | None = None,
    default_query: str = "",
    anchor: str = "",
) -> tuple[AudioEntry | None, tuple[str, ...]]:
    """The first bed of `bed_candidates` and every line up to it: the library's best
    over `threshold`, else the search ladder stopping at the first adoption, else none
    and why."""
    lines: list[str] = []
    for entry, more in bed_candidates(
        library, query, first_stamp_s=first_stamp_s, threshold=threshold, search=search,
        default_query=default_query, anchor=anchor,
    ):  # fmt: skip
        lines += more
        if entry is not None:
            return entry, tuple(lines)
    return None, tuple(lines)


# --- the bed per story part (076) --------------------------------------------------------

FALLBACK_LINE = "fallback bed: {mood}, no approved bed"
FACTS_DEFAULT_LINE = "fallback bed: facts_default {entry} for {wanted}, no approved bed"
SAME_BED_LINE = "bed {entry} plays through {part}: no other approved bed, the change is dropped"


@dataclass(frozen=True)
class BedSpan:
    """One bed of the score: the entry, the story part and mood it plays from, and when
    its part starts on the timeline."""

    entry: AudioEntry
    part: str
    mood: str
    start_s: float = 0.0


@dataclass(frozen=True)
class Score:
    """The beds the music stem plays: one, or two with the `how` of the one change at
    the second bed's `start_s` (076)."""

    spans: tuple[BedSpan, ...]
    how: BedHow | None = None

    @classmethod
    def single(cls, entry: AudioEntry, *, part: str = "hook", mood: str = "") -> Score:
        return cls(spans=(BedSpan(entry=entry, part=part, mood=mood),))

    @property
    def beds(self) -> tuple[AudioEntry, ...]:
        return tuple(s.entry for s in self.spans)

    @property
    def change_s(self) -> float | None:
        return self.spans[1].start_s if len(self.spans) > 1 else None

    @property
    def key(self) -> tuple[object, ...]:
        return (*(s.entry.id for s in self.spans), self.how)

    @property
    def label(self) -> str:
        return " + ".join(s.entry.id for s in self.spans)


def approved_beds(library: Library) -> tuple[AudioEntry, ...]:
    """076: the beds a segment may play - the operator's approved library (075), never
    one a runtime search fetched."""
    return tuple(e for e in library.beds() if e.id not in library.fetched)


def mood_beds(
    library: Library, segment: BedSegment, *, energy: int, first_stamp_s: float
) -> list[AudioEntry]:
    """The approved beds tagged with the segment's mood, best first: a flavour match,
    then the energy distance, then the drop-point fit, then the id."""
    matching = [e for e in approved_beds(library) if segment.mood in e.tags.mood]
    flavour = segment.flavour

    def rank(e: AudioEntry) -> tuple[int, int, float, str]:
        flavoured = 0 if flavour is not None and flavour in e.tags.flavour else 1
        return (flavoured, abs(e.energy - energy), drop_fit(e, first_stamp_s), e.id)

    return sorted(matching, key=rank)


def select_mood_bed(
    library: Library, segment: BedSegment, *, energy: int, first_stamp_s: float
) -> AudioEntry | None:
    found = mood_beds(library, segment, energy=energy, first_stamp_s=first_stamp_s)
    return found[0] if found else None


def facts_default_beds(
    library: Library, *, energy: int, first_stamp_s: float
) -> list[AudioEntry]:
    """087: the approved beds the operator tagged `facts_default`, best first: the energy
    distance, then the drop-point fit, then the id."""
    tagged = [e for e in approved_beds(library) if FACTS_DEFAULT in e.tags.role]
    return sorted(tagged, key=lambda e: (abs(e.energy - energy), drop_fit(e, first_stamp_s), e.id))


def segment_beds(
    library: Library, segment: BedSegment, *, energy: int, first_stamp_s: float, facts_first: bool
) -> list[tuple[AudioEntry, str | None]]:
    """087: a segment's approved beds in the director's order, each with its fallback line
    when it is the facts default. The planned mood + flavour (the mood alone when the plan
    names no flavour) comes first; then, with the style's `sound.facts_default_first`, a
    `facts_default` bed before a same-mood bed of another flavour, else after it (076)."""
    same = mood_beds(library, segment, energy=energy, first_stamp_s=first_stamp_s)
    flavour = segment.flavour
    exact = [e for e in same if flavour is None or flavour in e.tags.flavour]
    other = [e for e in same if e not in exact]
    wanted = f"{segment.mood}/{flavour}" if flavour else segment.mood
    facts: list[tuple[AudioEntry, str | None]] = [
        (e, FACTS_DEFAULT_LINE.format(entry=e.id, wanted=wanted))
        for e in facts_default_beds(library, energy=energy, first_stamp_s=first_stamp_s)
    ]
    plain: list[tuple[AudioEntry, str | None]] = [(e, None) for e in other]
    rungs = [(e, None) for e in exact] + (facts + plain if facts_first else plain + facts)
    seen: set[str] = set()
    out: list[tuple[AudioEntry, str | None]] = []
    for entry, line in rungs:
        if entry.id not in seen:
            seen.add(entry.id)
            out.append((entry, line))
    return out


def part_start_s(story: SoundStory, plan: PicturePlan, part: str) -> float:
    """When a story part's first beat starts on the plan's timeline (0 when unnamed)."""
    first = next((p.first_beat for p in story.parts if p.part == part), None)
    return next((b.start for b in plan.beats if b.id == first), 0.0)


def _segment_beds_from(
    library: Library, segment: BedSegment, story: SoundStory, plan: PicturePlan, start_s: float,
    *, facts_first: bool,
) -> list[tuple[AudioEntry, str | None]]:  # fmt: skip
    stamps = [
        b.start - start_s for b in plan.beats if b.event.kind == "stamp" and b.start >= start_s
    ]
    stamp = min(stamps) if stamps else 0.0
    return segment_beds(library, segment, energy=story.bed_query.energy, first_stamp_s=stamp,
                        facts_first=facts_first)  # fmt: skip


def score_candidates(
    library: Library,
    story: SoundStory,
    plan: PicturePlan,
    nums: styles.Sound,
    *,
    search: AudioSearch | None = None,
) -> Iterator[tuple[Score | None, tuple[str, ...], str | None]]:
    """The scores to try, best first, each with its log lines and the fallback line
    when it is a Freesound fallback (076).

    A story with no `bed` segments is scored the pre-076 way (`bed_candidates` over its
    `bed_query`). Otherwise every segment takes the first of its `segment_beds` - the
    planned mood + flavour, then (087) the `facts_default` bed and a same-mood bed of
    another flavour in the style's order, the facts default with its fallback line - and
    the change sits on the second segment's part start; after it, the first segment's
    approved beds alone (a change never survives a failed balance). A segment with no
    approved bed at all drops the change: one Freesound bed is searched for that mood with
    069's music-anchored ladder, and its line says so. The second segment never takes the
    first's bed (two misses would both reach the one `facts_default`): it takes its next
    approved bed, and with none the first bed plays through with the change dropped."""
    if not story.bed:
        for entry, said in bed_candidates(
            library, story.bed_query, first_stamp_s=first_stamp_s(plan),
            threshold=nums.bed_score_threshold, search=search,
            default_query=nums.default_bed_query, anchor=nums.bed_query_anchor,
        ):  # fmt: skip
            yield (Score.single(entry) if entry is not None else None), said, None
        return
    spans: list[BedSpan] = []
    lines: list[str] = []
    stood_in: str | None = None
    first_in = nums.facts_default_first
    for i, segment in enumerate(story.bed[:2]):
        start = 0.0 if i == 0 else part_start_s(story, plan, segment.part_from)
        found = _segment_beds_from(library, segment, story, plan, start, facts_first=first_in)
        flavour = f" ({segment.flavour})" if segment.flavour else ""
        if not found:
            fallback = FALLBACK_LINE.format(mood=segment.mood)
            yield from _fallback(library, story, nums, segment, search, fallback)
            return
        # A change to the bed already playing would restart its file mid-short: the
        # second segment takes its next bed, else the first plays through.
        taken = spans[0].entry.id if spans else None
        picked = next((f for f in found if f[0].id != taken), None)
        if picked is None:
            lines.append(SAME_BED_LINE.format(entry=taken, part=segment.part_from))
            break
        entry, stand_in = picked
        if stand_in is not None:
            lines.append(stand_in)
            stood_in = stood_in or stand_in
        else:
            lines.append(
                f"bed {entry.id} for {segment.part_from}: {segment.mood}{flavour} from the "
                "approved library"
            )
        spans.append(BedSpan(entry=entry, part=segment.part_from, mood=segment.mood, start_s=start))
    change = story.change if len(spans) > 1 else None
    how = change.how if change is not None else None
    if change is not None:
        lines.append(f"bed change at {spans[1].start_s:.2f} s ({change.at_beat}): {change.how}")
    yield Score(spans=tuple(spans), how=how), tuple(lines), stood_in
    first = story.bed[0]
    for entry, stand_in in segment_beds(
        library, first, energy=story.bed_query.energy, first_stamp_s=first_stamp_s(plan),
        facts_first=first_in,
    ):  # fmt: skip
        said = (f"bed {entry.id} alone for {first.mood}: the change is dropped",) if how else ()
        yield (
            Score.single(entry, part=first.part_from, mood=first.mood),
            (*((stand_in,) if stand_in else ()), *said),
            stand_in,
        )
    if search is not None:
        # 056 (1): past the library's candidates the search supplies the next bed.
        spent = FALLBACK_LINE.format(mood=first.mood) + " passed the 7.3 balance"
        yield from _fallback(library, story, nums, first, search, spent)


def _fallback(
    library: Library,
    story: SoundStory,
    nums: styles.Sound,
    segment: BedSegment,
    search: AudioSearch | None,
    line: str,
) -> Iterator[tuple[Score | None, tuple[str, ...], str | None]]:
    """076: one bed from the search (or a bed it fetched before), never an approved bed
    of another mood; the mood's words ask for it."""
    kept = tuple(e for e in library.entries if e.kind != "bed" or e.id in library.fetched)
    unapproved = replace(library, entries=kept)
    query = story.bed_query.model_copy(update={"mood": segment.mood.replace("_", " ")})
    first = True
    for entry, lines in bed_candidates(
        unapproved, query, first_stamp_s=0.0, threshold=nums.bed_score_threshold,
        search=search, default_query=nums.default_bed_query, anchor=nums.bed_query_anchor,
    ):  # fmt: skip
        head = (line,) if first else ()
        first = False
        score = Score.single(entry, part=segment.part_from, mood=segment.mood) if entry else None
        yield score, (*head, *lines), line


def span_gates(score: Score, nums: styles.Sound) -> tuple[tuple[float, str], ...]:
    """Per bed of the score, where its file starts on the timeline and the sample-exact
    fades that let it in and out at the change (076): a crossfade is an equal-power
    `bed_crossfade_s` from the change; a hard cut fades the old bed out over
    `bed_cut_fade_s` up to the change and the new one in over it from there; a drop to
    silence does the same with `bed_silence_s` of nothing between them."""
    t = score.change_s
    if t is None or score.how is None:
        return tuple((0.0, "") for _ in score.spans)
    fade = nums.bed_cut_fade_s
    if score.how == "crossfade":
        length = nums.bed_crossfade_s
        return (
            (0.0, f"afade=t=out:st={t:g}:d={length:g}:curve=qsin"),
            (t, f"afade=t=in:st={t:g}:d={length:g}:curve=qsin"),
        )
    out = (0.0, f"afade=t=out:st={max(0.0, t - fade):g}:d={min(fade, t) or fade:g}")
    enter = t if score.how == "hard_cut" else t + nums.bed_silence_s
    return (out, (enter, f"afade=t=in:st={enter:g}:d={fade:g}"))


@dataclass(frozen=True)
class Window:
    name: str
    start_s: float
    end_s: float
    span: int | None  # the bed measured alone; None for the crossfade (the summed stem)


def balance_windows(score: Score, nums: styles.Sound, *, runtime_s: float) -> tuple[Window, ...]:
    """076: the stretches a two-bed short is measured on - each bed where it plays alone,
    and the crossfade where both do. One bed has none: the whole stem is its window."""
    t = score.change_s
    if t is None or score.how is None:
        return ()
    a, b = score.spans
    enter = {"crossfade": t + nums.bed_crossfade_s, "hard_cut": t,
             "drop_to_silence": t + nums.bed_silence_s}[score.how]  # fmt: skip
    windows = [Window(f"{a.part}: {a.mood} ({a.entry.id})", 0.0, t, 0)]
    if score.how == "crossfade":
        windows.append(Window(f"crossfade {t:.2f}-{enter:.2f} s", t, enter, None))
    name = f"{b.part}: {b.mood} ({b.entry.id})"
    windows.append(Window(name, min(enter, runtime_s), runtime_s, 1))
    return tuple(windows)


def trim(start_s: float, end_s: float) -> str:
    return f"atrim=start={start_s:g}:end={end_s:g}"


# --- the floor hits (7.1) ---------------------------------------------------------------

# Which plan fact earns which named event, most specific first: a beat that is both a
# money reveal and a stamp earns the money reveal, so the style's drum lands on it rather
# than its bass. The names are the style's (`sound.floor_hits`); the mapping from the plan
# to them is this engine's reading of the beat grammar.
CARD_KINDS = frozenset({"card", "wall"})  # 055: the hook-cards beat is gone
HEADER_KINDS = frozenset({"list"})
TRIGGER_ORDER: tuple[str, ...] = (
    "finale_word",
    "money_reveal",
    "header",
    "reveal",
    "stamp",
    "card_fly_in",
)


@dataclass(frozen=True)
class FloorHit:
    beat_id: str
    at_s: float
    hit: str
    trigger: str


def beat_triggers(plan: PicturePlan) -> dict[str, tuple[str, ...]]:
    """Per beat id, the named events it earns, most specific first (7.1)."""
    out: dict[str, tuple[str, ...]] = {}
    for beat in plan.beats:
        found: set[str] = set()
        if beat.id == plan.finale.beat_id:
            found.add("finale_word")
        if beat.money_reveal:
            found.add("money_reveal")
        if beat.kind in HEADER_KINDS:
            found.add("header")
        if beat.motion == "reveal":
            found.add("reveal")
        if beat.event.kind == "stamp" or beat.counter is not None:
            found.add("stamp")  # 029: the counter lands as a stamp does
        if beat.kind in CARD_KINDS:
            found.add("card_fly_in")
        out[beat.id] = tuple(t for t in TRIGGER_ORDER if t in found)
    return out


def hit_classes(nums: styles.Sound) -> dict[str, str]:
    """The style's `sound.floor_hits` inverted: event name -> hit class."""
    return {event: hit for hit, events in nums.floor_hits.items() for event in events}


def landing_s(beat: Beat, counter_land_s: float | None) -> float:
    """When a beat's landed event lands: its start (a stamp lands there, 026), or for a
    `counter` the start of its last `counter_land_s`, where the digits land (029). The
    land time is the picture's (`broll.motion.stamp.duration_s`); without it the counter
    is placed like a stamp. 061 / 063 / 062: a beat with no landed event that carries
    text pops, bubbles or a sticker lands where its first pop does (a text pop before a
    bubble before a sticker; `at_s`, written by the grammar; the start when it was never
    written)."""
    if beat.counter is not None and counter_land_s is not None:
        return max(beat.start, beat.end - counter_land_s)
    popping = [*beat.text_pops, *beat.bubbles, *beat.stickers]
    if beat.event.kind == "none" and beat.counter is None and popping:
        first = popping[0].at_s
        return beat.start if first is None else max(beat.start, first)
    return beat.start


def floor_hits(
    plan: PicturePlan, nums: styles.Sound, *, counter_land_s: float | None = None
) -> list[FloorHit]:
    """The guaranteed floor (7.1): at most one hit per beat, where its event lands
    (`landing_s`), its class read from the style."""
    classes = hit_classes(nums)
    triggers = beat_triggers(plan)
    out: list[FloorHit] = []
    for beat in plan.beats:
        trigger = next((t for t in triggers[beat.id] if t in classes), None)
        if trigger is None:
            continue
        out.append(
            FloorHit(beat_id=beat.id, at_s=landing_s(beat, counter_land_s),
                     hit=classes[trigger], trigger=trigger)  # fmt: skip
        )
    return out


# --- cues (7.1, 7.3) --------------------------------------------------------------------

# Where each kind sits in the style's `cue_db_min`-`cue_db_max` band: the drum at the
# top, then the changeover and the bass, then the thump and the whoosh, with the tick and
# the ding softest (070: marks sit at the quiet end, thump level or below). The band is
# the style's; these are the engine's weights, like the geometry constants in `render`.
CHANGEOVER = "changeover"
# 070: the palette has no changeover kind, so the cue 7.3 puts after a drop plays the
# approved bass file, at the bass level.
CHANGEOVER_KIND = "bass"
CLASS_LEVEL: Mapping[str, float] = {
    "drum": 1.0, CHANGEOVER: 0.75, "bass": 0.75, "thump": 0.4, styles.WHOOSH: 0.4,
    styles.TICK: 0.2, styles.DING: 0.2,
}  # fmt: skip
PLANNER_LEVEL = 0.5
# Which cue survives the cap: the classes first (the short is never flat, and a drop is
# never left without its changeover), then the soft marks. Earlier beats win inside a
# rank.
CLASS_RANK: Mapping[str, int] = {"drum": 3, CHANGEOVER: 3, "bass": 2, "thump": 1}
MARK_KINDS: tuple[str, ...] = (styles.TICK, styles.WHOOSH, styles.DING)
IDEA = "idea"  # 062's sticker tag a ding rides (070)
NO_APPROVED_LINE = "no approved sfx in the audio library"
BOUNDARY_TOL_S = 0.05  # how near a mood point must sit to a beat start to be that beat's

CueSource = Literal["planner", "floor"]


@dataclass(frozen=True)
class PlacedCue:
    """One cue on the SFX stem. `hit` is the palette kind its level and its place in the
    cap come from (070): the kind the planner named, the floor class the beat earned
    (7.1), `tick` / `whoosh` / `ding` for a mark the director derived, or `changeover`
    for the cue a drop must be followed by (7.3; it plays the bass file). `source` is
    who chose the cue - the planner, or this code."""

    beat_id: str
    at_s: float
    intent: str
    hit: str
    entry_id: str
    gain_db: float
    source: CueSource


def cue_kind(cue: PlacedCue) -> str:
    """070: the palette kind whose approved file a placed cue plays."""
    return CHANGEOVER_KIND if cue.hit == CHANGEOVER else cue.hit


@dataclass(frozen=True)
class PlacedCues:
    """The cues, the log lines, and the library they were matched from."""

    library: Library
    cues: tuple[PlacedCue, ...] = ()
    notes: tuple[str, ...] = ()


def mark_row(kind: str, nums: styles.Sound) -> styles.Mark | None:
    """070: the style's row for a mark kind (tick, whoosh, ding); None for a floor class,
    and for a whoosh where the style carries no allowance."""
    if kind == styles.TICK:
        return nums.tick
    if kind == styles.DING:
        return nums.ding
    if kind == styles.WHOOSH:
        return nums.whoosh if styles.allows_whoosh(nums) else None
    return None


def kind_max_len_s(kind: str, nums: styles.Sound) -> float:
    """070: the longest file a cue of `kind` may play - its row's `max_len_s`, or for a
    floor class `sound.floor_max_len_s`. Every kind has a length."""
    row = mark_row(kind, nums)
    if row is not None:
        return row.max_len_s
    if kind in nums.floor_max_len_s:
        return nums.floor_max_len_s[kind]
    raise SoundError(f"the style's sound rows give no length for the cue kind {kind!r} (070)")


def mark_cap(row: styles.Mark, *, runtime_s: float) -> int:
    """A mark row's `max_per_60s` scaled to the runtime, rounded up like gate T6's
    whoosh cap, so a six-second fixture still allows one."""
    return math.ceil(row.max_per_60s * runtime_s / 60.0 - 1e-6)


@dataclass(frozen=True)
class MarkCandidate:
    """One place the director may put a soft mark (070)."""

    beat_id: str
    at_s: float
    kind: str


def mark_candidates(plan: PicturePlan, nums: styles.Sound) -> list[MarkCandidate]:
    """070 (7.3 as amended): every visible change a soft mark may sit on, in time order -
    a whoosh on each non-cut enter `sound.whoosh.on` names, a tick on each pop-in (every
    text pop, bubble and sticker at its `at_s`, the beat's start when unwritten), and a
    ding instead of the tick on a sticker tagged `idea`. The director considers each
    one; the caps decide which it marks."""
    whoosh = mark_row(styles.WHOOSH, nums)
    ding = styles.IDEA_STICKER in nums.ding.on
    tick = styles.POP in nums.tick.on
    out: list[MarkCandidate] = []
    for beat in plan.beats:
        if whoosh is not None and beat.enter != "cut" and beat.enter in whoosh.on:
            out.append(MarkCandidate(beat.id, beat.start, styles.WHOOSH))
        popping: list[tuple[float | None, bool]] = [
            *((p.at_s, False) for p in beat.text_pops),
            *((b.at_s, False) for b in beat.bubbles),
            *((s.at_s, s.intent == IDEA) for s in beat.stickers),
        ]
        for at_s, idea in popping:
            kind = styles.DING if idea and ding else styles.TICK if tick else None
            if kind is not None:
                at = beat.start if at_s is None else max(beat.start, at_s)
                out.append(MarkCandidate(beat.id, at, kind))
    return sorted(out, key=lambda m: (m.at_s, m.beat_id, m.kind))


class SfxShelf:
    """What `place_cues` matches a palette kind against (070): the approved library
    alone (075) - the shortest file tagged with the kind and no longer than its
    `kind_max_len_s`. No effect is ever searched for at job time. A kind with no such
    file is one note, remembered, and its cues are dropped."""

    def __init__(self, library: Library, nums: styles.Sound) -> None:
        self.library = library
        self._approved = replace(library, entries=library.approved_sfx())
        self._nums = nums
        self.notes: list[str] = []
        self._resolved: dict[str, AudioEntry | None] = {}

    def resolve(self, kind: str) -> AudioEntry | None:
        key = kind.strip().lower()
        if key in self._resolved:
            return self._resolved[key]
        limit = kind_max_len_s(key, self._nums)
        found = match_sfx(key, self._approved, max_duration_s=limit)
        if found is None:
            self.notes.append(
                f"no approved sfx for {key!r} no longer than {limit:g} s in the library: "
                "its cues are dropped"
            )
        self._resolved[key] = found
        return found


def cue_cap(nums: styles.Sound, *, runtime_s: float) -> int:
    """`cues_max_per_60s` scaled to the runtime, floor hits included (7.3)."""
    return math.floor(nums.cues_max_per_60s * runtime_s / 60.0 + 1e-9)


def cue_level_db(hit: str, nums: styles.Sound) -> float:
    fraction = CLASS_LEVEL.get(hit, PLANNER_LEVEL)
    return nums.cue_db_min + fraction * (nums.cue_db_max - nums.cue_db_min)


def match_sfx(
    intent: str, library: Library, *, max_duration_s: float | None = None
) -> AudioEntry | None:
    """The SFX whose `intent` tags carry this intent (7.2), the shortest file first so a
    hit is a hit and not a bed; None when nothing is tagged with it. `max_duration_s`
    (070: the kind's `max_len_s`) leaves longer files out."""
    wanted = intent.strip().lower()
    if not wanted:
        return None
    matched = [
        e
        for e in library.sfx()
        if wanted in {t.strip().lower() for t in e.tags.intent}
        and (max_duration_s is None or e.duration_s <= max_duration_s + 1e-9)
    ]
    return min(matched, key=lambda e: (e.duration_s, e.id)) if matched else None


def _planner_at_s(beat: Beat, cue: Cue, counter_land_s: float | None) -> float:
    """Where a planner cue fires: an `event` cue where the beat's event lands
    (`landing_s`) - a ding where its `idea` sticker pops in (070) - else the beat's start
    or end."""
    if cue.at != "event":
        return cue_time(beat.start, beat.end, cue.at)
    if cue.intent == styles.DING:
        idea = next((s for s in beat.stickers if s.intent == IDEA), None)
        if idea is not None and idea.at_s is not None:
            return max(beat.start, idea.at_s)
    return landing_s(beat, counter_land_s)


def place_cues(
    plan: PicturePlan,
    story: SoundStory,
    library: Library,
    nums: styles.Sound,
    *,
    runtime_s: float,
    counter_land_s: float | None = None,
) -> PlacedCues:
    """The short's cues, matched to approved files, levelled and capped (7.1, 7.3).

    In order: the planner's cues, then a changeover on every drop the envelope steps,
    then the floor hits the plan's events earn, then the soft marks the director derives
    on pop-ins and transitions (`mark_candidates`, 070). A beat takes at most
    `sound.cues_per_beat_max` of them, so the earlier pass owns its slot; a tick, whoosh
    or ding - the planner's or derived - stays within its row's `max_per_60s` and
    `min_gap_s`. Every candidate left unmarked has its line.

    070: every cue plays a file of its palette kind from the approved library, no longer
    than the kind's `max_len_s`; nothing is searched for, and a kind with no file drops
    its cues with a line."""
    if not library.approved_sfx():
        return PlacedCues(library=library, notes=(f"{NO_APPROVED_LINE}: the short has no cues",))
    beats = {b.id: b for b in plan.beats}
    floor = {h.beat_id: h for h in floor_hits(plan, nums, counter_land_s=counter_land_s)}
    shelf = SfxShelf(library, nums)
    steps = changeover_times(story, nums, runtime_s=runtime_s)
    placed: list[PlacedCue] = []
    per_beat: dict[str, int] = {}
    marked: dict[str, list[float]] = {}

    def full(beat_id: str) -> bool:
        return per_beat.get(beat_id, 0) >= nums.cues_per_beat_max

    def take(cue: PlacedCue) -> None:
        placed.append(cue)
        per_beat[cue.beat_id] = per_beat.get(cue.beat_id, 0) + 1
        if cue.hit in MARK_KINDS:
            marked.setdefault(cue.hit, []).append(cue.at_s)

    def over_row(kind: str, at_s: float) -> str | None:
        row = mark_row(kind, nums)
        if row is None:
            return None
        times = marked.get(kind, [])
        cap = mark_cap(row, runtime_s=runtime_s)
        if len(times) >= cap:
            return (
                f"sound.{kind}.max_per_60s {row.max_per_60s} allows {cap} over {runtime_s:g} s"
            )
        near = [t for t in times if abs(t - at_s) + 1e-9 < row.min_gap_s]
        if near:
            return (
                f"{abs(at_s - near[0]):.2f} s from the {kind} at {near[0]:.2f} s, under "
                f"sound.{kind}.min_gap_s {row.min_gap_s:g}"
            )
        return None

    notes = shelf.notes  # the library lines first, then the placement decisions
    for cue in story.cues:
        beat = beats.get(cue.beat_id)
        if beat is None:
            notes.append(f"{cue.beat_id}: cue {cue.intent!r} names a beat that is not in the plan")
            continue
        if cue.intent not in CUE_KINDS:
            # 070: the grammar has refused this already; nothing outside the palette is
            # ever matched.
            notes.append(f"{cue.beat_id}: cue {cue.intent!r} dropped: outside the sound palette")
            continue
        if full(cue.beat_id):
            notes.append(
                f"{cue.beat_id}: cue {cue.intent!r} dropped, sound.cues_per_beat_max "
                f"{nums.cues_per_beat_max}"
            )
            continue
        if styles.is_whoosh(cue.intent) and not styles.allows_whoosh(nums):
            notes.append(
                f"{cue.beat_id}: cue {cue.intent!r} dropped: whooshes are in sound.forbidden "
                "for this style (060)"
            )
            continue
        at_s = _planner_at_s(beat, cue, counter_land_s)
        why = over_row(cue.intent, at_s)
        if why is not None:
            notes.append(f"{cue.beat_id}: cue {cue.intent!r} dropped: {why}")
            continue
        entry = shelf.resolve(cue.intent)
        if entry is None:
            notes.append(f"{cue.beat_id}: cue {cue.intent!r} dropped: no approved file of its kind")
            continue
        take(
            PlacedCue(
                beat_id=cue.beat_id, at_s=at_s, intent=cue.intent, hit=cue.intent,
                entry_id=entry.id, gain_db=cue_level_db(cue.intent, nums), source="planner",
            )  # fmt: skip
        )

    # 7.3: a drop is a step down at a beat boundary *followed by a changeover cue*, so
    # the director places one on the beat the step lands on unless the planner already
    # cued it. This runs before the floor so the changeover takes the beat's slot.
    for t in steps:
        beat = next((b for b in plan.beats if abs(b.start - t) <= BOUNDARY_TOL_S), None)
        if beat is None or full(beat.id):
            continue
        entry = shelf.resolve(CHANGEOVER_KIND)
        if entry is None:
            notes.append(f"{beat.id}: no approved {CHANGEOVER_KIND!r} file for the drop at {t:g} s")
            continue
        take(
            PlacedCue(
                beat_id=beat.id, at_s=beat.start, intent=CHANGEOVER, hit=CHANGEOVER,
                entry_id=entry.id, gain_db=cue_level_db(CHANGEOVER, nums), source="floor",
            )  # fmt: skip
        )

    for hit in floor.values():
        if full(hit.beat_id):
            continue
        entry = shelf.resolve(hit.hit)
        if entry is None:
            notes.append(f"{hit.beat_id}: no approved {hit.hit!r} file for the floor hit")
            continue
        take(
            PlacedCue(
                beat_id=hit.beat_id, at_s=hit.at_s, intent=hit.trigger, hit=hit.hit,
                entry_id=entry.id, gain_db=cue_level_db(hit.hit, nums), source="floor",
            )  # fmt: skip
        )

    # 070: the soft marks, never on every event - each candidate in time order, as long as
    # its beat has a slot and its row's caps allow it.
    for mark in mark_candidates(plan, nums):
        if any(
            c.beat_id == mark.beat_id and c.hit == mark.kind and abs(c.at_s - mark.at_s) < 1e-6
            for c in placed
        ):
            continue  # the planner marked it
        where = f"{mark.beat_id}: {mark.kind} at {mark.at_s:.2f} s not marked"
        if full(mark.beat_id):
            notes.append(
                f"{where}: the beat has its sound.cues_per_beat_max {nums.cues_per_beat_max}"
            )
            continue
        why = over_row(mark.kind, mark.at_s)
        if why is not None:
            notes.append(f"{where}: {why}")
            continue
        entry = shelf.resolve(mark.kind)
        if entry is None:
            notes.append(f"{where}: no approved file of its kind")
            continue
        take(
            PlacedCue(
                beat_id=mark.beat_id, at_s=mark.at_s, intent=mark.kind, hit=mark.kind,
                entry_id=entry.id, gain_db=cue_level_db(mark.kind, nums), source="floor",
            )  # fmt: skip
        )

    cap = cue_cap(nums, runtime_s=runtime_s)
    kept = sorted(placed, key=lambda c: (-CLASS_RANK.get(c.hit, 0), c.at_s, c.beat_id))
    if len(kept) > cap:
        for cue in kept[cap:]:
            notes.append(
                f"{cue.beat_id}: cue {cue.intent!r} dropped: {len(kept)} cues over "
                f"{runtime_s:g} s, sound.cues_max_per_60s {nums.cues_max_per_60s} allows {cap}"
            )
        kept = kept[:cap]
    ordered = tuple(sorted(kept, key=lambda c: (c.at_s, c.beat_id)))
    for cue in ordered:  # 054 (1): one line per cue placed
        notes.append(
            f"{cue.beat_id}: cue {cue.intent!r} placed at {cue.at_s:.2f} s "
            f"({cue.entry_id}, {cue.hit}, {cue.source})"
        )
    return PlacedCues(library=library, cues=ordered, notes=tuple(notes))


def cue_time(start: float, end: float, at: str) -> float:
    """Where the cue fires: a beat's landed event and its entry both sit at its start
    (the stamp lands there, 026); `end` is the only other place a cue may sit."""
    return end if at == "end" else start


def first_stamp_s(plan: PicturePlan) -> float:
    """When the short's first stamp lands: what a bed's drop point is fitted to (7.2)."""
    stamped = [b.start for b in plan.beats if b.event.kind == "stamp"]
    return min(stamped) if stamped else (plan.beats[0].start if plan.beats else 0.0)


# --- the mood envelope (7.3) ------------------------------------------------------------

STEP_S = 0.01  # how long a "step" takes: short enough to hear as one, long enough to draw
DB_TO_LINEAR = math.log(10.0) / 20.0


@dataclass(frozen=True)
class EnvelopePoint:
    t: float
    level_db: float


def _clipped(story: SoundStory, nums: styles.Sound, runtime_s: float) -> list[EnvelopePoint]:
    points = [
        EnvelopePoint(
            t=min(max(p.t, 0.0), runtime_s),
            level_db=min(max(p.level, nums.drop_min_db), nums.swell_max_db),
        )
        for p in story.mood_curve
    ]
    points.sort(key=lambda p: p.t)
    if not points:
        return [EnvelopePoint(t=0.0, level_db=0.0), EnvelopePoint(t=runtime_s, level_db=0.0)]
    if points[0].t > 0.0:
        points.insert(0, EnvelopePoint(t=0.0, level_db=points[0].level_db))
    if points[-1].t < runtime_s:
        points.append(EnvelopePoint(t=runtime_s, level_db=points[-1].level_db))
    return points


def _is_drop(a: EnvelopePoint, b: EnvelopePoint, nums: styles.Sound) -> bool:
    return b.level_db < a.level_db and (b.t - a.t) + 1e-9 < nums.ramp_min_s


def envelope(
    story: SoundStory, nums: styles.Sound, *, runtime_s: float
) -> tuple[EnvelopePoint, ...]:
    """The music stem's automation: the clipped curve with every drop realised as a step
    that holds its level until the boundary (7.3)."""
    points = _clipped(story, nums, runtime_s)
    out: list[EnvelopePoint] = [points[0]]
    for a, b in zip(points, points[1:], strict=False):
        if _is_drop(a, b, nums) and b.t - STEP_S > a.t:
            out.append(EnvelopePoint(t=b.t - STEP_S, level_db=a.level_db))
        out.append(b)
    return tuple(out)


def changeover_times(
    story: SoundStory, nums: styles.Sound, *, runtime_s: float
) -> tuple[float, ...]:
    """Where the envelope steps down, and so where 7.3 wants a changeover cue. Read off
    the same clipped points `envelope` builds, so a step and its cue can never disagree."""
    points = _clipped(story, nums, runtime_s)
    return tuple(b.t for a, b in zip(points, points[1:], strict=False) if _is_drop(a, b, nums))


def eval_db(points: Sequence[EnvelopePoint], t: float) -> float:
    """The envelope in Python: the same piecewise line `volume_expr` draws in ffmpeg."""
    if not points:
        return 0.0
    if t <= points[0].t:
        return points[0].level_db
    for a, b in zip(points, points[1:], strict=False):
        if t < b.t:
            span = b.t - a.t
            if span <= 0:
                return b.level_db
            return a.level_db + (b.level_db - a.level_db) * (t - a.t) / span
    return points[-1].level_db


def db_expr(points: Sequence[EnvelopePoint]) -> str:
    """The envelope as an ffmpeg expression in dB."""
    if not points:
        return "0"
    expr = f"{points[-1].level_db:g}"
    for a, b in reversed(list(zip(points, points[1:], strict=False))):
        span = b.t - a.t
        segment = (
            f"{b.level_db:g}"
            if span <= 0
            else f"({a.level_db:g}+({b.level_db - a.level_db:g})*(t-{a.t:g})/{span:g})"
        )
        expr = f"if(lt(t,{b.t:g}),{segment},{expr})"
    return f"if(lt(t,{points[0].t:g}),{points[0].level_db:g},{expr})"


def volume_expr(points: Sequence[EnvelopePoint]) -> str:
    """The same envelope as the linear multiplier the `volume` filter wants."""
    return f"exp({DB_TO_LINEAR:.9g}*({db_expr(points)}))"


# --- the mix graph (7.3, research S5) ---------------------------------------------------

DUCK_THRESHOLD, DUCK_RATIO, DUCK_ATTACK_MS, DUCK_RELEASE_MS = 0.06, 2, 20, 400


def duck_filter() -> str:
    """The 7.3 sidechain, verbatim: the music is the main input, the voice the chain."""
    return (
        f"sidechaincompress=threshold={DUCK_THRESHOLD:g}:ratio={DUCK_RATIO:g}"
        f":attack={DUCK_ATTACK_MS:g}:release={DUCK_RELEASE_MS:g}"
    )


def dip_filter(nums: styles.Sound, depth_db: float) -> str:
    """056 (1), the first repair: a peaking EQ cut over the style's speech band, centred
    on its geometric middle and as wide as the band in octaves, `depth_db` deep."""
    low, high = nums.speech_band_hz
    centre = math.sqrt(low * high)
    octaves = math.log2(high / low)
    return f"equalizer=f={centre:g}:width_type=o:width={octaves:g}:g={-depth_db:g}"


def music_filter(
    *,
    gain_db: float,
    points: Sequence[EnvelopePoint],
    runtime_s: float,
    nums: styles.Sound,
    dip_db: float = 0.0,
    delay_s: float = 0.0,
    gate: str = "",
) -> str:
    """The music stem: level-matched to the bed target, the envelope on top, the style's
    fades at both ends, exactly `runtime_s` long; with `dip_db` the speech-band dip of
    056 (1) before the level match, so the median still lands on the target. 076: a bed
    of a two-bed score starts `delay_s` into the short (its file from its start) and
    `gate` is its `span_gates` fades, so the envelope still shapes it inside its span."""
    fade_out_at = max(0.0, runtime_s - nums.fade_out_s)
    dip = f"{dip_filter(nums, dip_db)}," if dip_db > 0 else ""
    delay = f"adelay=delays={round(delay_s * 1000)}:all=1," if delay_s > 0 else ""
    return (
        f"{MONO},{delay}apad,atrim=0:{runtime_s:g},asetpts=N/SR/TB,"
        f"{dip}"
        f"volume={gain_db:.2f}dB,"
        f"volume='{volume_expr(points)}':eval=frame,"
        f"afade=t=in:st=0:d={nums.fade_in_s:g},"
        f"afade=t=out:st={fade_out_at:g}:d={nums.fade_out_s:g}"
        + (f",{gate}" if gate else "")
    )


def sfx_graph(
    cues: Sequence[PlacedCue], *, gains_db: Sequence[float], runtime_s: float
) -> str:
    """One input per cue, delayed to its time and gained to its class level, summed."""
    parts: list[str] = []
    labels = ""
    for i, gain in enumerate(gains_db):
        delay_ms = round(cues[i].at_s * 1000)
        parts.append(
            f"[{i}:a]{MONO},volume={gain:.2f}dB,adelay=delays={delay_ms}:all=1[c{i}]"
        )
        labels += f"[c{i}]"
    tail = f"apad,atrim=0:{runtime_s:g},asetpts=N/SR/TB,{MONO}"
    if len(gains_db) == 1:
        parts.append(f"[c0]{tail}[out]")
    else:
        parts.append(
            f"{labels}amix=inputs={len(gains_db)}:normalize=0:duration=longest,{tail}[out]"
        )
    return ";".join(parts)


# --- the mix (7.3) ----------------------------------------------------------------------

BALANCE_NAME = "balance.json"
CUES_NAME = "cues.json"


@dataclass(frozen=True)
class MixResult:
    """What the sound step left behind: the premix the master is cut from, the stems,
    and what was chosen and measured."""

    premix: Path
    music: Path | None
    sfx: Path | None
    bed: AudioEntry | None
    cues: tuple[PlacedCue, ...]
    balance: BalanceReport
    notes: tuple[str, ...]
    # 054: the library as the searches left it - what the rights rows are read from.
    library: Library
    # 076: every bed the music stem plays (two across a change, `bed` the first), the
    # change's `how` and time, and the fallback line when the bed came from the search.
    beds: tuple[AudioEntry, ...] = ()
    how: BedHow | None = None
    change_s: float | None = None
    fallback: str | None = None

    def summary(self) -> str:
        """The closing line of the job log's sound trail: what the director chose. Every
        search and every per-cue decision precedes it in `notes` (054 (1))."""
        bed = f"bed {self.bed.id}" if self.bed is not None else "no bed"
        if len(self.beds) > 1 and self.change_s is not None:
            bed += f", then {self.beds[1].id} by {self.how} at {self.change_s:.2f} s"
        planned = sum(1 for c in self.cues if c.source == "planner")
        dropped = sum(1 for n in self.notes if "dropped" in n)
        return (
            f"sound: {bed}, {len(self.cues)} cues ({planned} from the planner, "
            f"{len(self.cues) - planned} derived, {dropped} dropped by the caps)"
        )


def _speech_band(nums: styles.Sound) -> str:
    low, high = nums.speech_band_hz
    return f"highpass=f={low:g},lowpass=f={high:g}"


def _median_db(path: Path, *, prefilter: str = "") -> float | None:
    windows = ffmpeg.rms_windows_db(path, prefilter=prefilter)
    return statistics.median(windows) if windows else None


def _render(argv: list[str]) -> None:
    ffmpeg.run(argv, timeout_s=MIX_TIMEOUT_S)


def _bed_source_args(entry: AudioEntry, runtime_s: float, path: Path) -> list[str]:
    """A bed shorter than the short is looped when the catalogue says it may be, and
    padded with silence when it may not (7.2: `loop_ok` is measured at seed time)."""
    loop = ["-stream_loop", "-1"] if entry.loop_ok and entry.duration_s < runtime_s else []
    return [ffmpeg.FFMPEG, "-v", "error", "-y", *loop, "-t", f"{runtime_s:.3f}", "-i", str(path)]


# 056 (1): a music check never fails the job. When the balance misses a line the mix
# repairs itself, in the operator's order: a speech-band dip on the bed (the depth
# escalates from the shortfall until the line is reached or `MAX_DIP_DB`), then the bed
# lowered to the floor of the acceptance window, then the next bed candidate (at most
# `BED_CANDIDATES_MAX` beds are mixed), and only then the voice and the hits alone.
MAX_DIP_DB = 24.0
BED_CANDIDATES_MAX = 3
VOICE_AND_HITS_LINE = "voice and hits only: no bed passed the 7.3 balance after every repair"


def dip_depths(shortfall_db: float) -> tuple[float, ...]:
    """The dip depths to try for a margin `shortfall_db` short of the line: the
    shortfall plus a decibel of headroom, then doubling, never past `MAX_DIP_DB`. The
    level match undoes part of every dip (the bed is put back on its target), so one
    depth is rarely enough and the next is measured, never modelled."""
    depths: list[float] = []
    depth = float(math.ceil(max(shortfall_db, 0.0)) + 1)
    while depth <= MAX_DIP_DB:
        depths.append(depth)
        depth *= 2
    return tuple(depths)


@dataclass(frozen=True)
class _BedMix:
    """One bed mixed and measured: its stems, its balance, and the repairs it took."""

    music: Path | None
    ducked: Path | None
    balance: BalanceReport
    repairs: tuple[str, ...] = ()
    dip_db: float = 0.0


def build_mix(
    *,
    stems: Path,
    voice: Path,
    plan: PicturePlan,
    story: SoundStory,
    nums: styles.Sound,
    library: Library,
    runtime_s: float,
    search: AudioSearch | None = None,
    counter_land_s: float | None = None,
    log: Callable[[str], None] | None = None,
) -> MixResult:
    """Build the music and SFX stems beside `voice` and the premix the master is cut
    from, and write `balance.json`. A mix that misses the 7.3 band is repaired, never
    failed (056 (1)): the dip, the lower bed, the next bed, and last the voice and the
    hits alone with `VOICE_AND_HITS_LINE` in the notes and `bed_dropped` in the report.
    `log` gets every note as it is made (054 (1): the searches, the decisions and
    every repair reach `job.log`)."""
    stems.mkdir(parents=True, exist_ok=True)
    voice_db = ffmpeg.mean_volume_db(voice)
    if voice_db is None:
        raise SoundError(f"{voice.name} is silent: the mix has nothing to sit under")
    notes: list[str] = []

    def note(lines: Iterable[str]) -> None:
        for line in lines:
            notes.append(line)
            if log is not None:
                log(line)

    # 070: `search` is asked for beds alone; every cue comes from the approved library.
    placed = place_cues(
        plan, story, library, nums, runtime_s=runtime_s, counter_land_s=counter_land_s
    )
    note(placed.notes)
    sfx = _sfx_stem(
        stems, cues=placed.cues, library=library, voice_db=voice_db, runtime_s=runtime_s
    )
    sheet = cue_records(placed.cues, library, runtime_s=runtime_s)
    (stems / CUES_NAME).write_text(sheet.model_dump_json(indent=2), encoding="utf-8")

    score: Score | None = None
    mixed: _BedMix | None = None
    repairs: list[str] = []
    dropped: str | None = None
    fallback: str | None = None
    tried: set[tuple[object, ...]] = set()
    for candidate, lines, fallen in score_candidates(library, story, plan, nums, search=search):
        note(lines)
        if candidate is None or candidate.key in tried:
            continue
        tried.add(candidate.key)
        for entry in candidate.beds:
            library = library.adding(entry)
        attempt = _repaired_bed(
            stems, score=candidate, library=library, story=story, nums=nums, voice=voice,
            voice_db=voice_db, runtime_s=runtime_s, cues=len(placed.cues), note=note,
        )  # fmt: skip
        repairs += attempt.repairs
        if not attempt.balance.problems:
            # 087: the page names the fallback of the bed that plays, not of one dropped
            score, mixed, fallback = candidate, attempt, fallen
            break
        dropped = f"{candidate.label}: {'; '.join(attempt.balance.problems)}"
        if len(tried) >= BED_CANDIDATES_MAX:
            note((f"{BED_CANDIDATES_MAX} beds mixed and dropped; no further candidate is tried",))
            break
        note((f"bed {candidate.label} dropped after every repair; trying the next bed",))
    if mixed is None or score is None or len(score.spans) < 2:
        _clear_span_stems(stems)
    if mixed is None:
        for name in ("music.wav", "music.ducked.wav"):
            (stems / name).unlink(missing_ok=True)
        balance = _balance(
            stems, voice=voice, music=None, ducked=None, nums=nums, voice_db=voice_db,
            cues=len(placed.cues),
        )  # fmt: skip
        mixed = _BedMix(music=None, ducked=None, balance=balance)
        if dropped is not None:
            note((f"{VOICE_AND_HITS_LINE} (last bed {dropped})",))
    balance = mixed.balance.model_copy(
        update={"repairs": repairs, "dip_db": mixed.dip_db or None, "bed_dropped": dropped}
    )
    premix = _premix(stems, voice=voice, ducked=mixed.ducked, sfx=sfx)
    (stems / BALANCE_NAME).write_text(balance.model_dump_json(indent=2), encoding="utf-8")
    beds = score.beds if score is not None and mixed.music is not None else ()
    return MixResult(
        premix=premix, music=mixed.music, sfx=sfx, bed=beds[0] if beds else None,
        cues=placed.cues, balance=balance, notes=tuple(notes), library=library, beds=beds,
        how=score.how if beds and score is not None else None,
        change_s=score.change_s if beds and score is not None else None, fallback=fallback,
    )  # fmt: skip


def _clear_span_stems(stems: Path) -> None:
    for path in stems.glob("music.[0-9].wav"):
        path.unlink(missing_ok=True)


def _mix_bed(
    stems: Path,
    *,
    score: Score,
    library: Library,
    story: SoundStory,
    nums: styles.Sound,
    voice: Path,
    voice_db: float,
    runtime_s: float,
    cues: int,
    dip_db: float,
    under_db: float | None,
) -> _BedMix:
    """One score rendered, ducked and measured, with the given dip and target."""
    music, spans = _music_stem(
        stems, score=score, library=library, story=story, nums=nums, voice_db=voice_db,
        runtime_s=runtime_s, dip_db=dip_db, under_db=under_db,
    )  # fmt: skip
    ducked = _ducked(stems, voice=voice, music=music)
    balance = _balance(
        stems, voice=voice, music=music, ducked=ducked, nums=nums, voice_db=voice_db, cues=cues,
        windows=[(w, spans[w.span] if w.span is not None else music)
                 for w in balance_windows(score, nums, runtime_s=runtime_s)],
    )  # fmt: skip
    return _BedMix(music=music, ducked=ducked, balance=balance, dip_db=dip_db)


def _margins(balance: BalanceReport) -> tuple[float | None, float | None]:
    """The lowest and the highest speech-band margin the balance measured: the whole
    stem's and, across a bed change, each window's (076). The dip answers the lowest;
    069's ceiling reads the highest."""
    found = [m for m in (balance.speech_band_margin_db,
                         *(w.speech_band_margin_db for w in balance.windows)) if m is not None]
    return (min(found), max(found)) if found else (None, None)


def _repaired_bed(
    stems: Path,
    *,
    score: Score,
    library: Library,
    story: SoundStory,
    nums: styles.Sound,
    voice: Path,
    voice_db: float,
    runtime_s: float,
    cues: int,
    note: Callable[[Iterable[str]], None],
) -> _BedMix:
    """The bed mixed as planned and, when it misses the 7.3 band, repaired rung by rung
    (056 (1)): the speech-band dip at escalating depths while the margin is the problem,
    then the bed lowered to the floor of `bed_accept_db`. Every repair is one line in
    `repairs` and in the log, the dip with its depth in dB and the margin it reached.
    The result carries the last balance measured; the caller reads `problems`."""
    plain = _mix_bed(
        stems, score=score, library=library, story=story, nums=nums, voice=voice,
        voice_db=voice_db, runtime_s=runtime_s, cues=cues, dip_db=0.0, under_db=None,
    )  # fmt: skip
    if not plain.balance.problems:
        return plain
    note((f"bed {score.label} misses the 7.3 band: {'; '.join(plain.balance.problems)}",))
    if inaudible(_margins(plain.balance)[1], nums):
        # 069: a dip or a lower bed only pushes the band further down; the caller walks
        # on to the next candidate.
        note((
            f"bed {score.label}: no repair makes a bed the phone speaker cannot play audible"
            f"{level_note(plain.balance.bed_under_voice_db)}",
        ))  # fmt: skip
        return plain
    low_hz, high_hz = nums.speech_band_hz
    repairs: list[str] = []
    current = plain
    margin = _margins(plain.balance)[0]
    if margin is not None and margin < nums.speech_band_margin_db:
        for depth in dip_depths(nums.speech_band_margin_db - margin):
            current = _mix_bed(
                stems, score=score, library=library, story=story, nums=nums, voice=voice,
                voice_db=voice_db, runtime_s=runtime_s, cues=cues, dip_db=depth, under_db=None,
            )  # fmt: skip
            reached = _margins(current.balance)[0]
            line = (
                f"bed {score.label}: speech band {low_hz}-{high_hz} Hz dipped by {depth:g} dB "
                f"(margin {margin:.1f} -> {reached if reached is None else round(reached, 1)} dB, "
                f"line {nums.speech_band_margin_db:g})"
                f"{level_note(current.balance.bed_under_voice_db)}"
            )
            repairs.append(line)
            note((line,))
            if not current.balance.problems:
                return _BedMix(current.music, current.ducked, current.balance,
                               tuple(repairs), depth)  # fmt: skip
            if reached is not None and reached >= nums.speech_band_margin_db:
                break  # the margin is fixed; whatever is left is not the dip's
    # The lowest target that still converges inside the window: the floor plus the
    # tolerance the level match stops at.
    low = nums.bed_accept_db[0] + BED_TOLERANCE_DB
    current = _mix_bed(
        stems, score=score, library=library, story=story, nums=nums, voice=voice,
        voice_db=voice_db, runtime_s=runtime_s, cues=cues, dip_db=current.dip_db, under_db=low,
    )  # fmt: skip
    reached = _margins(current.balance)[0]
    line = (
        f"bed {score.label}: lowered to {low:g} dB under the voice, the floor of "
        f"sound.bed_accept_db {nums.bed_accept_db[0]:g} dB (margin now "
        f"{reached if reached is None else round(reached, 1)} dB)"
    )
    repairs.append(line)
    note((line,))
    if current.dip_db > 0 and inaudible(_margins(current.balance)[1], nums):
        # 069: the dip fixed the margin at the loud level; lowered as well, the band is
        # past the ceiling, so the lowered bed goes out without it.
        current = _mix_bed(
            stems, score=score, library=library, story=story, nums=nums, voice=voice,
            voice_db=voice_db, runtime_s=runtime_s, cues=cues, dip_db=0.0, under_db=low,
        )  # fmt: skip
        reached = _margins(current.balance)[0]
        line = (
            f"bed {score.label}: lowered without the dip, which left the band over "
            f"sound.speech_band_margin_max_db {nums.speech_band_margin_max_db:g} dB (margin now "
            f"{reached if reached is None else round(reached, 1)} dB)"
            f"{level_note(current.balance.bed_under_voice_db)}"
        )
        repairs.append(line)
        note((line,))
    return _BedMix(current.music, current.ducked, current.balance, tuple(repairs), current.dip_db)


BED_TOLERANCE_DB = 0.3
BED_PASSES = 4


def _music_stem(
    stems: Path,
    *,
    score: Score,
    library: Library,
    story: SoundStory,
    nums: styles.Sound,
    voice_db: float,
    runtime_s: float,
    dip_db: float = 0.0,
    under_db: float | None = None,
) -> tuple[Path, tuple[Path, ...]]:
    """The music stem and the stem of each bed in it (076: `music.1.wav`, `music.2.wav`
    across a change, summed into `music.wav`; one bed is `music.wav` itself). Each bed
    is converged on the target alone, measured where it plays alone (`balance_windows`),
    its envelope and its `span_gates` fades applied."""
    points = envelope(story, nums, runtime_s=runtime_s)
    target = voice_db + (nums.bed_db_under_voice if under_db is None else under_db)
    if len(score.spans) == 1:
        out = _bed_stem(
            stems / "music.wav", bed=score.spans[0].entry, library=library, nums=nums,
            points=points, target=target, runtime_s=runtime_s, dip_db=dip_db,
        )  # fmt: skip
        return out, (out,)
    windows = {w.span: w for w in balance_windows(score, nums, runtime_s=runtime_s)}
    beds: list[Path] = []
    for i, (span, (delay_s, gate)) in enumerate(zip(score.spans, span_gates(score, nums),
                                                   strict=True)):  # fmt: skip
        own = windows.get(i)
        beds.append(
            _bed_stem(
                stems / f"music.{i + 1}.wav", bed=span.entry, library=library, nums=nums,
                points=points, target=target, runtime_s=runtime_s, dip_db=dip_db,
                delay_s=delay_s, gate=gate,
                measured=trim(own.start_s, own.end_s) if own is not None else "",
            )  # fmt: skip
        )
    out = stems / "music.wav"
    inputs = [arg for path in beds for arg in ("-i", str(path))]
    labels = "".join(f"[{i}:a]" for i in range(len(beds)))
    _render(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex",
            f"{labels}amix=inputs={len(beds)}:normalize=0:duration=first[m]",
            "-map", "[m]", "-c:a", "pcm_f32le", str(out),
        ]  # fmt: skip
    )
    return out, tuple(beds)


def _bed_stem(
    out: Path,
    *,
    bed: AudioEntry,
    library: Library,
    nums: styles.Sound,
    points: Sequence[EnvelopePoint],
    target: float,
    runtime_s: float,
    dip_db: float = 0.0,
    delay_s: float = 0.0,
    gate: str = "",
    measured: str = "",
) -> Path:
    """One bed's stem, converged on the target.

    7.3 puts the bed `bed_db_under_voice` under the voice *on the median*, and the
    envelope and the fades both move the median away from the flat gain that would hit
    it. So the stem is rendered, its median measured and the gain corrected, at most
    `BED_PASSES` times - the loop `render.master` uses for the master's loudness, for the
    same reason: the target is a property of the rendered file, not of the filter.
    056 (1): `dip_db` is the speech-band dip, `target` the style's or the repaired,
    lower one. 076: `measured` trims the median to where the bed plays alone."""
    source = library.file(bed)
    if not source.is_file():
        raise SoundError(f"the bed {bed.id} names {bed.file}, which is not in the library folder")
    bed_db = ffmpeg.mean_volume_db(source)
    if bed_db is None:
        raise SoundError(f"the bed {bed.id} ({bed.file}) is silent")
    gain_db = target - bed_db
    for _ in range(BED_PASSES):
        _render(
            [
                *_bed_source_args(bed, runtime_s, source),
                "-af",
                music_filter(gain_db=gain_db, points=points, runtime_s=runtime_s, nums=nums,
                             dip_db=dip_db, delay_s=delay_s, gate=gate),
                "-c:a", "pcm_f32le", str(out),
            ]  # fmt: skip
        )
        median = _median_db(out, prefilter=measured)
        if median is None:
            break
        error = target - median
        if abs(error) <= BED_TOLERANCE_DB:
            break
        gain_db += error
    return out


def _sfx_stem(
    stems: Path,
    *,
    cues: Sequence[PlacedCue],
    library: Library,
    voice_db: float,
    runtime_s: float,
) -> Path | None:
    if not cues:
        return None
    peaks: dict[str, float] = {}
    inputs: list[str] = []
    gains: list[float] = []
    for cue in cues:
        entry = library.entry(cue.entry_id)
        if entry is None:
            raise SoundError(
                f"cue on {cue.beat_id} names {cue.entry_id!r}, which is not in the library"
            )
        path = library.file(entry)
        if entry.id not in peaks:
            peak = ffmpeg.max_volume_db(path)
            if peak is None:
                raise SoundError(f"the cue file {entry.id} ({entry.file}) is silent")
            peaks[entry.id] = peak
        inputs += ["-i", str(path)]
        gains.append((voice_db + cue.gain_db) - peaks[entry.id])
    out = stems / "sfx.wav"
    _render(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", *inputs,
            "-filter_complex", sfx_graph(cues, gains_db=gains, runtime_s=runtime_s),
            "-map", "[out]", "-c:a", "pcm_f32le", str(out),
        ]  # fmt: skip
    )
    return out


def _ducked(stems: Path, *, voice: Path, music: Path | None) -> Path | None:
    """The music under the 7.3 sidechain, kept beside the stems so the ducking is a
    measurement rather than a model."""
    if music is None:
        return None
    out = stems / "music.ducked.wav"
    _render(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(music), "-i", str(voice),
            "-filter_complex", f"[0:a][1:a]{duck_filter()}[d]",
            "-map", "[d]", "-c:a", "pcm_f32le", str(out),
        ]  # fmt: skip
    )
    return out


def _premix(stems: Path, *, voice: Path, ducked: Path | None, sfx: Path | None) -> Path:
    """Voice, ducked bed and cues summed; with nothing to add the voice is the premix."""
    layers = [p for p in (ducked, sfx) if p is not None]
    if not layers:
        return voice
    inputs: list[str] = []
    labels = ""
    for i, path in enumerate([voice, *layers]):
        inputs += ["-i", str(path)]
        labels += f"[{i}:a]"
    out = stems / "premix.wav"
    _render(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", *inputs,
            "-filter_complex",
            f"{labels}amix=inputs={len(layers) + 1}:normalize=0:duration=first[mix]",
            "-map", "[mix]", "-c:a", "pcm_f32le", str(out),
        ]  # fmt: skip
    )
    return out


def level_note(level_db: float | None) -> str:
    """087: the bed level a margin was measured at, for its line - a margin without its
    level is not comparable across yardsticks."""
    return "" if level_db is None else f" (bed level {level_db:.1f} dB under the voice)"


def margin_problem(
    margin_db: float, nums: styles.Sound, *, level_db: float | None = None
) -> str | None:
    """The 7.3 speech-band window (as amended by 064 and 069): `None` when the voice
    clears the bed by at least `speech_band_margin_db` and at most
    `speech_band_margin_max_db`, else the problem line. Under the floor the bed crowds
    the voice and the repair ladder starts; over the ceiling the bed has nothing in the
    band a phone speaker plays (run04's car exhaust, 28.7 dB) and no repair helps. 087:
    the line names `level_db`, the bed level the margin was measured at."""
    lo_hz, hi_hz = nums.speech_band_hz
    at = level_note(level_db)
    if margin_db > nums.speech_band_margin_max_db + 1e-9:
        return (
            f"the speech band {lo_hz}-{hi_hz} Hz clears the bed by {margin_db:.1f} dB{at}, "
            f"over sound.speech_band_margin_max_db {nums.speech_band_margin_max_db:g} dB: "
            "a phone speaker does not play this bed"
        )
    if margin_db + 1e-9 >= nums.speech_band_margin_db:
        return None
    return (
        f"the speech band {lo_hz}-{hi_hz} Hz clears the bed by only {margin_db:.1f} dB{at}, "
        f"under sound.speech_band_margin_db {nums.speech_band_margin_db:g} dB"
    )


def inaudible(margin_db: float | None, nums: styles.Sound) -> bool:
    """069: the margin is over the style's ceiling."""
    return margin_db is not None and margin_db > nums.speech_band_margin_max_db + 1e-9


def audibility(
    voice: Path, music: Path, nums: styles.Sound, *, window: str = "",
    level_db: float | None = None,
) -> tuple[float | None, str | None]:  # fmt: skip
    """069: the speech-band margin of `voice` over `music` (a bed already levelled
    against it) and its `margin_problem`; `(None, None)` when either is silent in the
    band. The mix's balance runs it, and 075's shortlist runs it on every bed candidate
    before the operator hears one. 076: `window` (an `atrim`) measures one stretch. 087:
    `level_db` is the bed level under the voice, named in the problem line."""
    band = f"{window},{_speech_band(nums)}" if window else _speech_band(nums)
    voice_band = ffmpeg.mean_volume_db(voice, prefilter=band)
    bed_band = ffmpeg.mean_volume_db(music, prefilter=band)
    if voice_band is None or bed_band is None:
        return None, None
    margin = voice_band - bed_band
    return margin, margin_problem(margin, nums, level_db=level_db)


def _balance(
    stems: Path,
    *,
    voice: Path,
    music: Path | None,
    ducked: Path | None,
    nums: styles.Sound,
    voice_db: float,
    cues: int,
    windows: Sequence[tuple[Window, Path]] = (),
) -> BalanceReport:
    """The 7.3 acceptance, measured: the bed's median level under the voice, the speech
    band's margin over the bed, and how far the sidechain pulled the bed down. 076:
    across a bed change, each bed where it plays alone passes the same median and
    margin lines on its own stem, and the crossfade's margin is measured on the sum."""
    low, high = nums.bed_accept_db
    report: dict[str, object] = {
        "voice_db": round(voice_db, 2),
        "bed_accept_db": (low, high),
        "speech_band_margin_min_db": nums.speech_band_margin_db,
        "speech_band_margin_max_db": nums.speech_band_margin_max_db,
        "duck_max_db": nums.duck_max_db,
        "cues": cues,
    }
    problems: list[str] = []
    if music is not None:
        bed_median = _median_db(music)
        if bed_median is None:
            problems.append("the music stem is silent")
        else:
            under = bed_median - voice_db
            report["bed_median_db"] = round(bed_median, 2)
            report["bed_under_voice_db"] = round(under, 2)
            if not low - 1e-9 <= under <= high + 1e-9:
                problems.append(
                    f"the bed sits {under:.1f} dB under the voice, outside "
                    f"sound.bed_accept_db {low:g} to {high:g} dB"
                )
            margin, problem = audibility(voice, music, nums, level_db=under)
            if margin is not None:
                report["speech_band_margin_db"] = round(margin, 2)
            if problem is not None:
                problems.append(problem)
        if ducked is not None:
            ducked_db = ffmpeg.mean_volume_db(ducked)
            music_db = ffmpeg.mean_volume_db(music)
            if ducked_db is not None and music_db is not None:
                duck = max(0.0, music_db - ducked_db)
                report["duck_db"] = round(duck, 2)
                if duck > nums.duck_max_db + 1e-9:
                    problems.append(
                        f"the sidechain pulls the bed down {duck:.1f} dB, over "
                        f"sound.duck_max_db {nums.duck_max_db:g} dB"
                    )
    measured: list[BalanceWindow] = []
    for window, stem in windows:
        if window.end_s - window.start_s <= 0:
            continue
        cut = trim(window.start_s, window.end_s)
        median = _median_db(stem, prefilter=cut)
        under = None if median is None else median - voice_db
        if window.span is not None:
            if under is None:
                problems.append(f"{window.name}: the bed is silent")
            elif not low - 1e-9 <= under <= high + 1e-9:
                problems.append(
                    f"{window.name}: the bed sits {under:.1f} dB under the voice, outside "
                    f"sound.bed_accept_db {low:g} to {high:g} dB"
                )
        margin, problem = audibility(voice, stem, nums, window=cut, level_db=under)
        if problem is not None:
            problems.append(f"{window.name}: {problem}")
        measured.append(
            BalanceWindow(
                name=window.name, start_s=round(window.start_s, 3), end_s=round(window.end_s, 3),
                bed_under_voice_db=None if under is None else round(under, 2),
                speech_band_margin_db=None if margin is None else round(margin, 2),
            )  # fmt: skip
        )
    report["windows"] = measured
    report["problems"] = problems
    return BalanceReport.model_validate(report)


# --- rights (5.4) -----------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _audio_row(
    entry: AudioEntry, library: Library, *, kind: str, beat_ids: Iterable[str]
) -> RightsRow:
    path = library.file(entry)
    return RightsRow(
        id=entry.id,
        beat_ids=list(beat_ids),
        kind="music" if kind == "music" else "sfx",
        origin="library",
        source_url=entry.source_url,
        licence=entry.licence,
        author=entry.author,
        file=entry.file,
        sha256=_sha256(path) if path.is_file() else "",
        width=0,
        height=0,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def rights_rows(result: MixResult) -> list[RightsRow]:
    """One row per music and SFX file the mix used (5.4), the bed's beats being the
    whole short and a cue's the beats it fired on, read from the library as the mix's
    searches left it (054)."""
    library = result.library
    rows: list[RightsRow] = []
    for bed in result.beds or ((result.bed,) if result.bed is not None else ()):
        rows.append(_audio_row(bed, library, kind="music", beat_ids=[]))  # 076: every bed
    fired: dict[str, list[str]] = {}
    for cue in result.cues:
        fired.setdefault(cue.entry_id, []).append(cue.beat_id)
    for entry_id, beat_ids in fired.items():
        entry = library.entry(entry_id)
        if entry is None:
            continue
        rows.append(_audio_row(entry, library, kind="sfx", beat_ids=beat_ids))
    return rows


def cue_records(
    cues: Sequence[PlacedCue], library: Library, *, runtime_s: float
) -> CueSheet:
    """Each placed cue from where it fires to where its file ends, inside the runtime."""
    records: list[CueRecord] = []
    for cue in cues:
        entry = library.entry(cue.entry_id)
        length = entry.duration_s if entry is not None else 0.0
        records.append(
            CueRecord(
                beat_id=cue.beat_id, intent=cue.intent, entry_id=cue.entry_id,
                start_s=cue.at_s, end_s=min(cue.at_s + length, runtime_s),
            )  # fmt: skip
        )
    return CueSheet(cues=records)


def cue_sheet(stems: Path) -> CueSheet | None:
    path = stems / CUES_NAME
    if not path.is_file():
        return None
    return CueSheet.model_validate_json(path.read_text(encoding="utf-8"))


def balance_report(stems: Path) -> BalanceReport | None:
    path = stems / BALANCE_NAME
    if not path.is_file():
        return None
    return BalanceReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
