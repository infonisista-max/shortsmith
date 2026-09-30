"""The self-inventory: every delivered short goes through the reference tool (ticket 074).

Operator decision (grill, 29 Sep 2026): our own output is read by the same inventory
tool as the references, so the two can be compared by numbers. `SelfInventory.run(job)`
is the advisory `inventory` step the pipeline runs on every delivered job, after `qa`:
`out/short.mp4` goes through `ReferenceAnalyser.analyse_file` with the same v2 prompt,
the same `REFERENCE_FPS` and the same schema (`reference.inventory`, one retry on a
malformed answer), and the v2 card - `tier: own`, `video_id` the job id, `styles` the
job's style - is written to `out/inventory.json`.

Each request is a `reference` row on the ledger (`input_tokens` the prompt and video,
`output_tokens` the answer and the thinking), priced from `prices.yaml`; the hard cap is
checked before each request. Any failure - no key, an upload refused, an answer that did
not parse after the retry, the hard cap - writes `{"status": "not_analysed", "reason":
...}` instead and a `job.log` line; the step never changes the short, never raises, and
the job stays where the verdict left it.

`summary(job)` is what `meta.json` and the job page read: the comparison of the card
with the style's reference cards (`reference.compare`), or the reason it is missing;
the match-share row carries our plan's share too (077).

110c: whatever the analysis did, the step adds the variety line of the job's final plan
(`work/plan.json`, `reference.variety`) to `out/inventory.json` under `variety`; each
red row is a `job.log` line, never a gate, and `summary` carries the rows.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ValidationError

from shortsmith import jobs, render
from shortsmith.config import Settings
from shortsmith.contracts import (
    STORY_PARTS,
    ComparisonRow,
    OwnInventory,
    PicturePlan,
    SoundStory,
)
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.reference import (
    COMPONENTS_MD,
    INVENTORY_DIR,
    ReferenceInventoryV2,
    ReferenceLink,
    examples,
    inventory,
    load_card,
    variety,
)
from shortsmith.reference import compare as compare_module
from shortsmith.reference.gemini import Answer, GeminiAnalyser, ReferenceAnalyser
from shortsmith.styles import StyleSpec

NAME = "inventory.json"
VIDEO = "short.mp4"
VARIETY = "variety"  # 110c: the key of the variety line in out/inventory.json
STEP = "reference"
PROVIDER = "reference"
LOG_PREFIX = "inventory: "
# The hard-cap estimate before each request (11.3): the 27 Sep spike read about 355
# video tokens per second at 5 fps, so about 71 per sampled frame; the answer is about
# 7k output tokens plus thinking.
TOKENS_PER_FRAME = 71
CHARS_PER_TOKEN = 4
OUTPUT_TOKENS_ESTIMATE = 9000
DEFAULT_DURATION_S = 60.0


class NotAnalysed(BaseModel):
    status: Literal["not_analysed"] = "not_analysed"
    reason: str


class _Metered(ReferenceAnalyser):
    """The analyser with the ledger around each request: the hard cap checked before,
    the row recorded after."""

    def __init__(
        self, inner: ReferenceAnalyser, job: Job, book: Ledger, duration_s: float
    ) -> None:
        self._inner = inner
        self._job = job
        self._book = book
        self._duration_s = duration_s
        self.model = inner.model
        self.fps = inner.fps

    def analyse(self, url: str, prompt: str) -> Answer:
        raise NotImplementedError("the self-inventory reads the job's own file")

    def analyse_file(self, path: Path, prompt: str) -> Answer:
        estimate = {
            "input_tokens": math.ceil(self._duration_s * self.fps * TOKENS_PER_FRAME)
            + math.ceil(len(prompt) / CHARS_PER_TOKEN),
            "output_tokens": OUTPUT_TOKENS_ESTIMATE,
        }
        self._book.check_before_call(self._job, STEP, self._book.estimate(PROVIDER, estimate))
        answer = self._inner.analyse_file(path, prompt)
        usage = answer.usage
        self._book.record(
            self._job, STEP, PROVIDER, answer.model,
            {"input_tokens": usage.prompt_tokens,
             "output_tokens": usage.output_tokens + usage.thoughts_tokens},
        )  # fmt: skip
        return answer


class SelfInventory:
    """The step: `analyser` reads the file; `ledger` (None for a fake, which is free)
    prices each request."""

    def __init__(
        self,
        analyser: ReferenceAnalyser,
        *,
        ledger: Callable[[], Ledger] | None = None,
        registry: Collection[str] | None = None,
        components_md: Path = COMPONENTS_MD,
        specs: Mapping[str, StyleSpec] | None = None,
    ) -> None:
        self.analyser = analyser
        self._specs = specs
        self._ledger = ledger
        self._registry = registry
        self._components_md = components_md

    def run(self, job: Job) -> ReferenceInventoryV2 | NotAnalysed:
        try:
            made = self._analyse(job)
        except Exception as exc:  # noqa: BLE001 - advisory: any failure is `not_analysed`
            made = _not_analysed(job, str(exc).splitlines()[0] if str(exc) else repr(exc))
        try:
            _add_variety(job, self._specs if self._specs is not None else render.loaded_styles())
        except Exception as exc:  # noqa: BLE001 - advisory: the line is logged, never a gate
            jobs.note(job, f"{LOG_PREFIX}variety not measured: {str(exc).splitlines()[0]}")
        return made

    def _analyse(self, job: Job) -> ReferenceInventoryV2:
        video = job.out_dir / VIDEO
        if not video.is_file():
            raise FileNotFoundError(f"out/{VIDEO} is missing")
        analyser = self.analyser
        if self._ledger is not None:
            duration = job.record.input.duration_s if job.record.input else DEFAULT_DURATION_S
            analyser = _Metered(analyser, job, self._ledger(), duration)
        link = ReferenceLink(
            url=f"out/{VIDEO}", video_id=job.id, category=job.record.style, tier="own"
        )
        made = inventory(
            link, analyser, out_dir=job.out_dir, name=NAME, video=video,
            registry=self._registry if self._registry is not None else render.registry(),
            components_md=self._components_md, styles=[job.record.style],
            # job.log: the status trail is the lines with " -> "; the tool's last line
            # names its file that way, so it is reworded here.
            log=lambda line: jobs.note(job, LOG_PREFIX + line.replace(" -> ", " written to ")),
        )  # fmt: skip
        if not isinstance(made, ReferenceInventoryV2):
            raise TypeError("the inventory tool wrote a v1 card; the step needs v2")
        return made


def _not_analysed(job: Job, reason: str) -> NotAnalysed:
    result = NotAnalysed(reason=reason)
    (job.out_dir / NAME).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    jobs.note(job, f"{LOG_PREFIX}not analysed: {reason}")
    return result


def _add_variety(job: Job, specs: Mapping[str, StyleSpec]) -> None:
    """110c: the variety line of `work/plan.json` into `out/inventory.json`; a red row
    is a job.log line only. No plan (a job that never planned): nothing."""
    plan_path = job.work_dir / "plan.json"
    if not plan_path.is_file():
        return
    plan = PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    rows = variety.rows(plan.beats, specs[job.record.style])
    path = job.out_dir / NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data[VARIETY] = [row.model_dump(mode="json") for row in rows]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for row in rows:
        if row.outside:
            spread = "" if row.low is None else f" outside {row.low:g}-{row.high:g}"
            jobs.note(job, f"{LOG_PREFIX}{row.name} {row.ours}{spread} ({row.refs}; logged, "
                      "never a gate)")  # fmt: skip


def load_variety(job: Job) -> list[ComparisonRow]:
    """110c: the variety rows in `out/inventory.json`; none before the step or for a
    job with no plan."""
    path = job.out_dir / NAME
    if not path.is_file():
        return []
    rows = _fields(path).get(VARIETY, [])
    return [ComparisonRow.model_validate(row) for row in cast(list[object], rows)]


def _fields(path: Path) -> dict[str, object]:
    data: object = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, object], data) if isinstance(data, dict) else {}


def load(job: Job) -> ReferenceInventoryV2 | NotAnalysed | None:
    """`out/inventory.json` as written: the card, the reason, or None before the step
    (the 110c `variety` key beside them is `load_variety`'s)."""
    path = job.out_dir / NAME
    if not path.is_file():
        return None
    data = _fields(path)
    data.pop(VARIETY, None)
    text = json.dumps(data)
    try:
        return NotAnalysed.model_validate_json(text)
    except ValidationError:
        pass
    card = load_card(text)
    if not isinstance(card, ReferenceInventoryV2):
        return NotAnalysed(reason="out/inventory.json is a v1 card")
    return card


def summary(job: Job, inventory_dir: Path = INVENTORY_DIR) -> OwnInventory | None:
    """What `meta.json` records: the comparison with the style's reference cards, or
    the reason there is none; None before the step ran."""
    try:
        found = load(job)
        lined = load_variety(job)
    except (ValueError, ValidationError) as exc:
        return OwnInventory(status="not_analysed", reason=f"out/{NAME} does not read: {exc}")
    if found is None:
        return None
    if isinstance(found, NotAnalysed):
        return OwnInventory(status="not_analysed", reason=found.reason, variety=lined)
    style = job.record.style
    cards = compare_module.references_for(style, inventory_dir)
    plan_path = job.work_dir / "plan.json"  # 077: the plan's match share, beside ours
    plan_match = (
        examples.match_share(PicturePlan.model_validate_json(plan_path.read_text("utf-8")))
        if plan_path.is_file()
        else None
    )
    sound_path = job.work_dir / "sound.json"  # 076: the plan's mood per part, beside ours
    plan_moods = (
        part_moods(SoundStory.model_validate_json(sound_path.read_text("utf-8")))
        if sound_path.is_file()
        else None
    )
    return OwnInventory(
        status="analysed",
        comparison=compare_module.compare(
            found, cards, style=style, plan_match=plan_match, plan_moods=plan_moods
        ),
        variety=lined,
    )


def part_moods(story: SoundStory) -> dict[str, str]:
    """076: per story part of the plan, the mood of the bed segment playing in it (its
    flavour in brackets, as the cards write it); empty for a story from before 076."""
    out: dict[str, str] = {}
    for part in story.parts:
        rank = STORY_PARTS.index(part.part)
        playing = [s for s in story.bed if STORY_PARTS.index(s.part_from) <= rank]
        if playing:
            s = playing[-1]
            out[part.part] = f"{s.mood} ({s.flavour})" if s.flavour else s.mood
    return out


def from_settings(settings: Settings, *, ledger: Callable[[], Ledger]) -> SelfInventory:
    """The app's step: Gemini on `REFERENCE_MODEL` / `REFERENCE_FPS` /
    `REFERENCE_ENDPOINT` with `GEMINI_API_KEY`; with no key every job is `not_analysed`
    naming the setting, and nothing is sent."""
    return SelfInventory(
        GeminiAnalyser(
            api_key=settings.gemini_api_key, model=settings.reference_model,
            fps=settings.reference_fps, endpoint=settings.reference_endpoint,
        ),
        ledger=ledger,
    )  # fmt: skip


def keyless() -> SelfInventory:
    """The worker's default when nobody passes a step: Gemini with no key, so every
    job is `not_analysed` naming `GEMINI_API_KEY` and nothing leaves the box."""
    return SelfInventory(GeminiAnalyser(api_key=None))
