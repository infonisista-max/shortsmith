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
drop point lands nearest the first stamp. Below `BED_SCORE_MIN` - no tag hit at all -
`choose_bed` asks the `AudioSearch` adapter with the same query (Freesound in 024;
`FakeAudioSearch` returns seeded catalogue entries only, so no test reaches the network).

**Floor hits (7.1).** The Dyson v2 mechanical hits are derived from plan events as the
guaranteed floor so a short is never flat: `floor_hits` reads the style's
`sound.floor_hits` map (which hit class each event earns) and the plan (which beats earn
which events). A whip cut, a punch-in, a ring and a lower-third earn nothing, because no
style names them. A `counter` (029) lands as a stamp does and earns the stamp's class; its
hit, and any `event` cue on its beat, fires where its digits land - the last
`broll.motion.stamp.duration_s` of the beat (`landing_s`) - not at the beat's start.

**Cues (7.1, 7.3).** One cue per beat (`cues_per_beat_max`): the planner's intent when it
named one for that beat, else the beat's floor hit. An intent that matches no SFX `intent`
tag falls back to the beat's floor class - never silence, never a random file. The hit
class travels with the cue whether the planner named it or not, because the class is what
sets the level: every cue sits in the style's `cue_db_min`-`cue_db_max` band under the
voice, the drum at the top of the band, then the bass, then the thump and the planner's
own intents. Every step the envelope takes also places the changeover cue 7.3 requires a
drop to be followed by. `cues_max_per_60s` counts all of them together; over the cap the
classed cues are kept first (drum and changeover, then bass, then thump, earlier before
later) and the planner's extras fill what is left.

**Envelope (7.3).** `envelope` turns the mood curve into the music stem's volume
automation: levels clipped to `swell_max_db` / `drop_min_db`, ramps left as they are, and
a fall faster than `ramp_min_s` realised as a step - the level holds until the beat
boundary and drops there - with a changeover cue scheduled on the step.

**Mix (7.3, research §5).** `build_mix` writes `work/stems/{voice,music,sfx}.wav` and the
premix the master is cut from, plus `work/stems/balance.json`. The bed is looped or padded
to the runtime, level-matched to `bed_db_under_voice` under the voice's RMS, run through
the envelope and the style's fades, then ducked under the voice with the 7.3 sidechain
(threshold 0.06, ratio 2, attack 20, release 400). Each cue is delayed to its time and
peak-matched to its class level. The acceptance is in code: the bed's median must sit
inside `bed_accept_db` under the voice, the speech band must clear the bed by
`speech_band_margin_db`, and the ducking must stay under `duck_max_db` - outside any of
them the step fails with the measured numbers, after writing the report.

**Rights (5.4).** `rights_rows` gives the bed and every SFX file its row with origin
`library` and the catalogue's source URL; the renderer writes them beside the asset rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from shortsmith import ffmpeg, styles
from shortsmith.contracts import (
    AudioEntry,
    BalanceReport,
    Beat,
    BedQuery,
    Catalogue,
    PicturePlan,
    RightsRow,
    SoundStory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = REPO_ROOT / "assets" / "audio" / "catalog.yaml"
SAMPLE_RATE = ffmpeg.SAMPLE_RATE
MIX_TIMEOUT_S = 1800.0
MONO = f"aformat=channel_layouts=mono:sample_rates={SAMPLE_RATE}"


class SoundError(RuntimeError):
    """The catalogue is broken, or the mix missed the 7.3 acceptance band."""


# --- the catalogue (7.2) ----------------------------------------------------------------


@dataclass(frozen=True)
class Library:
    """The parsed catalogue and the directory its `file` paths are relative to."""

    root: Path
    entries: tuple[AudioEntry, ...] = ()

    def beds(self) -> tuple[AudioEntry, ...]:
        return tuple(e for e in self.entries if e.kind == "bed")

    def sfx(self) -> tuple[AudioEntry, ...]:
        return tuple(e for e in self.entries if e.kind == "sfx")

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
    """The library at `path`; a file that is not there is an empty library (7.2: the
    shipped catalogue is empty until the operator seeds it by hand, ticket 025)."""
    if not path.is_file():
        return Library(root=path.parent)
    catalogue = parse_catalogue(path.read_text(encoding="utf-8"), name=path.name)
    return Library(root=path.parent, entries=tuple(catalogue.entries))


# --- bed selection (7.2) ----------------------------------------------------------------

# A tag hit is worth 1, so the energy distance (at most 4) can only order beds that
# already agree on the tags; `BED_SCORE_MIN` is therefore "at least one tag matched".
ENERGY_WEIGHT = 0.1
BED_SCORE_MIN = 0.5


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


def select_bed(library: Library, query: BedQuery, *, first_stamp_s: float) -> AudioEntry | None:
    """The best-scoring bed, ties broken by drop-point fit; None below the threshold."""
    beds = library.beds()
    if not beds:
        return None
    best = min(
        beds, key=lambda e: (-bed_score(e, query), drop_fit(e, first_stamp_s), e.id)
    )
    return best if bed_score(best, query) >= BED_SCORE_MIN else None


class AudioSearch(ABC):
    """The runtime audio search (7.2): asked with the same bed query when the library
    scores below the threshold. Freesound is ticket 024."""

    @abstractmethod
    def search(self, query: BedQuery) -> list[AudioEntry]:
        """Beds matching `query`, best first; empty when nothing matched."""


class FakeAudioSearch(AudioSearch):
    """12.1: returns seeded catalogue entries only, so no test reaches the network."""

    def __init__(self, library: Library) -> None:
        self._library = library
        self.calls: list[BedQuery] = []

    def search(self, query: BedQuery) -> list[AudioEntry]:
        self.calls.append(query)
        beds = self._library.beds()
        return sorted(beds, key=lambda e: (abs(e.energy - query.energy), e.id))


def choose_bed(
    library: Library,
    query: BedQuery,
    *,
    first_stamp_s: float,
    search: AudioSearch | None = None,
) -> tuple[AudioEntry | None, str]:
    """The bed and the note the job log gets: the library's best, else the search
    adapter's best, else none (7.2)."""
    chosen = select_bed(library, query, first_stamp_s=first_stamp_s)
    if chosen is not None:
        return chosen, f"bed {chosen.id} from the library"
    if search is None:
        return None, (
            f"no bed for theme {query.theme!r} mood {query.mood!r}: nothing in the library "
            "scored and no audio search is configured"
        )
    found = search.search(query)
    if not found:
        return None, f"no bed for theme {query.theme!r} mood {query.mood!r}: the search found none"
    return found[0], f"bed {found[0].id} from the audio search"


# --- the floor hits (7.1) ---------------------------------------------------------------

# Which plan fact earns which named event, most specific first: a beat that is both a
# money reveal and a stamp earns the money reveal, so the style's drum lands on it rather
# than its bass. The names are the style's (`sound.floor_hits`); the mapping from the plan
# to them is this engine's reading of the beat grammar.
CARD_KINDS = frozenset({"hook_cards", "card", "wall"})
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
    is placed like a stamp."""
    if beat.counter is None or counter_land_s is None:
        return beat.start
    return max(beat.start, beat.end - counter_land_s)


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

# Where each class sits in the style's `cue_db_min`-`cue_db_max` band: the drum at the
# top, then the changeover and the bass, then the thump, with a planner intent that
# earned no class taking the middle. The band is the style's; these are the engine's
# weights, like the geometry constants in `render`.
CHANGEOVER = "changeover"
CLASS_LEVEL: Mapping[str, float] = {"drum": 1.0, CHANGEOVER: 0.75, "bass": 0.75, "thump": 0.4}
PLANNER_LEVEL = 0.5
# Which cue survives the cap: the classes first (the short is never flat, and a drop is
# never left without its changeover), then the planner's extras. Earlier beats win
# inside a rank.
CLASS_RANK: Mapping[str, int] = {"drum": 3, CHANGEOVER: 3, "bass": 2, "thump": 1}
BOUNDARY_TOL_S = 0.05  # how near a mood point must sit to a beat start to be that beat's

CueSource = Literal["planner", "floor"]


@dataclass(frozen=True)
class PlacedCue:
    """One cue on the SFX stem. `hit` is the class its level and its place in the cap
    come from: the floor class the beat earned (7.1), `changeover` for the cue a drop
    must be followed by (7.3), or "" for a planner intent on a beat that earned neither.
    `source` is who named the intent - the planner, or this code."""

    beat_id: str
    at_s: float
    intent: str
    hit: str
    entry_id: str
    gain_db: float
    source: CueSource


@dataclass(frozen=True)
class PlacedCues:
    cues: tuple[PlacedCue, ...] = ()
    notes: tuple[str, ...] = ()


def cue_cap(nums: styles.Sound, *, runtime_s: float) -> int:
    """`cues_max_per_60s` scaled to the runtime, floor hits included (7.3)."""
    return math.floor(nums.cues_max_per_60s * runtime_s / 60.0 + 1e-9)


def cue_level_db(hit: str, nums: styles.Sound) -> float:
    fraction = CLASS_LEVEL.get(hit, PLANNER_LEVEL)
    return nums.cue_db_min + fraction * (nums.cue_db_max - nums.cue_db_min)


def match_sfx(intent: str, library: Library) -> AudioEntry | None:
    """The SFX whose `intent` tags carry this intent (7.2), the shortest file first so a
    hit is a hit and not a bed; None when nothing is tagged with it."""
    wanted = intent.strip().lower()
    if not wanted:
        return None
    matched = [e for e in library.sfx() if wanted in {t.strip().lower() for t in e.tags.intent}]
    return min(matched, key=lambda e: (e.duration_s, e.id)) if matched else None


def place_cues(
    plan: PicturePlan,
    story: SoundStory,
    library: Library,
    nums: styles.Sound,
    *,
    runtime_s: float,
    counter_land_s: float | None = None,
) -> PlacedCues:
    """The short's cues, matched to files, levelled and capped (7.1, 7.3).

    In order: the planner's intents, then a changeover on every drop the envelope steps,
    then the floor hits the plan's events earn. A beat takes at most
    `sound.cues_per_beat_max` of them, so the earlier pass owns its slot. An `event` cue
    and a floor hit sit where the beat's event lands (`landing_s`)."""
    if not library.sfx():
        return PlacedCues(notes=("no sfx in the audio catalogue: the short has no cues",))
    beats = {b.id: b for b in plan.beats}
    floor = {h.beat_id: h for h in floor_hits(plan, nums, counter_land_s=counter_land_s)}
    notes: list[str] = []
    placed: list[PlacedCue] = []
    per_beat: dict[str, int] = {}

    def full(beat_id: str) -> bool:
        return per_beat.get(beat_id, 0) >= nums.cues_per_beat_max

    for cue in story.cues:
        beat = beats.get(cue.beat_id)
        if beat is None:
            notes.append(f"{cue.beat_id}: cue {cue.intent!r} names a beat that is not in the plan")
            continue
        if full(cue.beat_id):
            notes.append(
                f"{cue.beat_id}: cue {cue.intent!r} dropped, sound.cues_per_beat_max "
                f"{nums.cues_per_beat_max}"
            )
            continue
        hit = floor[cue.beat_id].hit if cue.beat_id in floor else ""
        entry = match_sfx(cue.intent, library)
        if entry is None:
            entry = match_sfx(hit, library) if hit else None
            if entry is None:
                notes.append(
                    f"{cue.beat_id}: cue {cue.intent!r} matched no sfx tag and its beat earns "
                    "no floor hit; dropped"
                )
                continue
            notes.append(
                f"{cue.beat_id}: cue {cue.intent!r} matched no sfx tag, fell back to the "
                f"{hit} floor hit ({entry.id})"
            )
        placed.append(
            PlacedCue(
                beat_id=cue.beat_id,
                at_s=(
                    landing_s(beat, counter_land_s)
                    if cue.at == "event"
                    else cue_time(beat.start, beat.end, cue.at)
                ),
                intent=cue.intent,
                hit=hit,
                entry_id=entry.id,
                gain_db=cue_level_db(hit, nums),
                source="planner",
            )
        )
        per_beat[cue.beat_id] = per_beat.get(cue.beat_id, 0) + 1

    # 7.3: a drop is a step down at a beat boundary *followed by a changeover cue*, so
    # the director places one on the beat the step lands on unless the planner already
    # cued it. This runs before the floor so the changeover takes the beat's slot.
    for t in changeover_times(story, nums, runtime_s=runtime_s):
        beat = next((b for b in plan.beats if abs(b.start - t) <= BOUNDARY_TOL_S), None)
        if beat is None or full(beat.id):
            continue
        entry = match_sfx(CHANGEOVER, library)
        if entry is None:
            notes.append(f"{beat.id}: no sfx tagged {CHANGEOVER!r} for the drop at {t:g} s")
            continue
        placed.append(
            PlacedCue(
                beat_id=beat.id, at_s=beat.start, intent=CHANGEOVER, hit=CHANGEOVER,
                entry_id=entry.id, gain_db=cue_level_db(CHANGEOVER, nums), source="floor",
            )  # fmt: skip
        )
        per_beat[beat.id] = per_beat.get(beat.id, 0) + 1

    for hit in floor.values():
        if full(hit.beat_id):
            continue
        entry = match_sfx(hit.hit, library)
        if entry is None:
            notes.append(f"{hit.beat_id}: no sfx tagged {hit.hit!r} for the floor hit")
            continue
        placed.append(
            PlacedCue(
                beat_id=hit.beat_id,
                at_s=hit.at_s,
                intent=hit.trigger,
                hit=hit.hit,
                entry_id=entry.id,
                gain_db=cue_level_db(hit.hit, nums),
                source="floor",
            )
        )
        per_beat[hit.beat_id] = per_beat.get(hit.beat_id, 0) + 1

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
    return PlacedCues(cues=ordered, notes=tuple(notes))


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


def music_filter(
    *, gain_db: float, points: Sequence[EnvelopePoint], runtime_s: float, nums: styles.Sound
) -> str:
    """The music stem: level-matched to the bed target, the envelope on top, the style's
    fades at both ends, exactly `runtime_s` long."""
    fade_out_at = max(0.0, runtime_s - nums.fade_out_s)
    return (
        f"{MONO},apad,atrim=0:{runtime_s:g},asetpts=N/SR/TB,"
        f"volume={gain_db:.2f}dB,"
        f"volume='{volume_expr(points)}':eval=frame,"
        f"afade=t=in:st=0:d={nums.fade_in_s:g},"
        f"afade=t=out:st={fade_out_at:g}:d={nums.fade_out_s:g}"
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

    def summary(self) -> str:
        """The one line the job log gets: what the director chose. The per-cue reasons
        stay in `notes` for the caller that wants them, so the operator's trail is one
        line per step, not one per dropped cue."""
        bed = f"bed {self.bed.id}" if self.bed is not None else "no bed"
        planned = sum(1 for c in self.cues if c.source == "planner")
        dropped = sum(1 for n in self.notes if "dropped" in n)
        return (
            f"sound: {bed}, {len(self.cues)} cues ({planned} from the planner, "
            f"{len(self.cues) - planned} derived, {dropped} dropped by the caps)"
        )


def _speech_band(nums: styles.Sound) -> str:
    low, high = nums.speech_band_hz
    return f"highpass=f={low:g},lowpass=f={high:g}"


def _median_db(path: Path) -> float | None:
    windows = ffmpeg.rms_windows_db(path)
    return statistics.median(windows) if windows else None


def _render(argv: list[str]) -> None:
    ffmpeg.run(argv, timeout_s=MIX_TIMEOUT_S)


def _bed_source_args(entry: AudioEntry, runtime_s: float, path: Path) -> list[str]:
    """A bed shorter than the short is looped when the catalogue says it may be, and
    padded with silence when it may not (7.2: `loop_ok` is measured at seed time)."""
    loop = ["-stream_loop", "-1"] if entry.loop_ok and entry.duration_s < runtime_s else []
    return [ffmpeg.FFMPEG, "-v", "error", "-y", *loop, "-t", f"{runtime_s:.3f}", "-i", str(path)]


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
) -> MixResult:
    """Build the music and SFX stems beside `voice` and the premix the master is cut
    from, write `balance.json`, and fail the step when the mix misses the 7.3 band."""
    stems.mkdir(parents=True, exist_ok=True)
    voice_db = ffmpeg.mean_volume_db(voice)
    if voice_db is None:
        raise SoundError(f"{voice.name} is silent: the mix has nothing to sit under")
    notes: list[str] = []

    bed, note = choose_bed(
        library, story.bed_query, first_stamp_s=first_stamp_s(plan), search=search
    )
    notes.append(note)
    music = _music_stem(
        stems, bed=bed, library=library, story=story, nums=nums,
        voice_db=voice_db, runtime_s=runtime_s,
    )  # fmt: skip
    placed = place_cues(
        plan, story, library, nums, runtime_s=runtime_s, counter_land_s=counter_land_s
    )
    notes += list(placed.notes)
    sfx = _sfx_stem(
        stems, cues=placed.cues, library=library, voice_db=voice_db, runtime_s=runtime_s
    )
    ducked = _ducked(stems, voice=voice, music=music)
    premix = _premix(stems, voice=voice, ducked=ducked, sfx=sfx)
    balance = _balance(
        stems, voice=voice, music=music, ducked=ducked, nums=nums,
        voice_db=voice_db, cues=len(placed.cues),
    )  # fmt: skip
    (stems / BALANCE_NAME).write_text(balance.model_dump_json(indent=2), encoding="utf-8")
    if balance.problems:
        raise SoundError("; ".join(balance.problems))
    return MixResult(
        premix=premix, music=music, sfx=sfx, bed=bed, cues=placed.cues,
        balance=balance, notes=tuple(notes),
    )  # fmt: skip


BED_TOLERANCE_DB = 0.3
BED_PASSES = 4


def _music_stem(
    stems: Path,
    *,
    bed: AudioEntry | None,
    library: Library,
    story: SoundStory,
    nums: styles.Sound,
    voice_db: float,
    runtime_s: float,
) -> Path | None:
    """The music stem, converged on the target.

    7.3 puts the bed `bed_db_under_voice` under the voice *on the median*, and the
    envelope and the fades both move the median away from the flat gain that would hit
    it. So the stem is rendered, its median measured and the gain corrected, at most
    `BED_PASSES` times - the loop `render.master` uses for the master's loudness, for the
    same reason: the target is a property of the rendered file, not of the filter."""
    if bed is None:
        return None
    source = library.file(bed)
    if not source.is_file():
        raise SoundError(f"the bed {bed.id} names {bed.file}, which is not in the library folder")
    bed_db = ffmpeg.mean_volume_db(source)
    if bed_db is None:
        raise SoundError(f"the bed {bed.id} ({bed.file}) is silent")
    target = voice_db + nums.bed_db_under_voice
    gain_db = target - bed_db
    points = envelope(story, nums, runtime_s=runtime_s)
    out = stems / "music.wav"
    for _ in range(BED_PASSES):
        _render(
            [
                *_bed_source_args(bed, runtime_s, source),
                "-af",
                music_filter(gain_db=gain_db, points=points, runtime_s=runtime_s, nums=nums),
                "-c:a", "pcm_f32le", str(out),
            ]  # fmt: skip
        )
        median = _median_db(out)
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


def _balance(
    stems: Path,
    *,
    voice: Path,
    music: Path | None,
    ducked: Path | None,
    nums: styles.Sound,
    voice_db: float,
    cues: int,
) -> BalanceReport:
    """The 7.3 acceptance, measured: the bed's median level under the voice, the speech
    band's margin over the bed, and how far the sidechain pulled the bed down."""
    low, high = nums.bed_accept_db
    report: dict[str, object] = {
        "voice_db": round(voice_db, 2),
        "bed_accept_db": (low, high),
        "speech_band_margin_min_db": nums.speech_band_margin_db,
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
            band = _speech_band(nums)
            voice_band = ffmpeg.mean_volume_db(voice, prefilter=band)
            bed_band = ffmpeg.mean_volume_db(music, prefilter=band)
            if voice_band is not None and bed_band is not None:
                margin = voice_band - bed_band
                report["speech_band_margin_db"] = round(margin, 2)
                if margin + 1e-9 < nums.speech_band_margin_db:
                    lo_hz, hi_hz = nums.speech_band_hz
                    problems.append(
                        f"the speech band {lo_hz}-{hi_hz} Hz clears the bed by only "
                        f"{margin:.1f} dB, under sound.speech_band_margin_db "
                        f"{nums.speech_band_margin_db:g} dB"
                    )
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


def rights_rows(result: MixResult, library: Library) -> list[RightsRow]:
    """One row per music and SFX file the mix used (5.4), the bed's beats being the
    whole short and a cue's the beats it fired on."""
    rows: list[RightsRow] = []
    if result.bed is not None:
        rows.append(_audio_row(result.bed, library, kind="music", beat_ids=[]))
    fired: dict[str, list[str]] = {}
    for cue in result.cues:
        fired.setdefault(cue.entry_id, []).append(cue.beat_id)
    for entry_id, beat_ids in fired.items():
        entry = library.entry(entry_id)
        if entry is None:
            continue
        rows.append(_audio_row(entry, library, kind="sfx", beat_ids=beat_ids))
    return rows


def balance_report(stems: Path) -> BalanceReport | None:
    path = stems / BALANCE_NAME
    if not path.is_file():
        return None
    return BalanceReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
