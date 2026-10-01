"""The worker (PRD `pipeline`): runs a job's steps in the 11.1 order, one job at a time
in submission order (9.1).

`run_job` is the synchronous path: it takes an `uploaded` job through every step
(transcribing, planning, sourcing, rendering, qa) and ends it
`delivered`. The `transcribing` step first measures the face (`presenter.measure`,
ticket 013; 3.3): eight stills, the detector, the PIP geometry onto `job.json`, and
a recording with a face on fewer than six stills fails here, before any paid call,
with the 3.3 sentence rather than the step's own. The detector is injected like the
adapters (`HaarDetector` by default, `FakeFaceDetector` in the pipeline and app
tests, whose flat clips have no face). The transcriber is bound to the job next, so
a real adapter writes under `work/asr/` and records its ledger rows (012); its
fixed transcript is `work/asr.json`.

The rule (097, work/editor-design.md): a small problem never fails the job. An
exception in `sourcing`, `rendering` or `qa` is a rescue, not a failure. When its
message names a beat (`b09: ...`) the editor (`editor.Editor`) picks one of the real
options code built for that beat (drop one layer, a plain cut, frame a map on its
markers' real coordinates, drop its route, replace its visual); the plan is patched
(`work/plan.json`, the picture of `work/plan.validated.json` re-validated on the output
timeline with the soft rules kept, `work/captions.json` rebuilt), a replaced beat is
added to `job.json.replaced` so sourcing re-sources it with the replacement ladder
(096), and the job is rewound (`jobs.rewind`) to `sourcing` and runs on. The same beat
failing the same way a second time takes `replace_visual` without asking, a third time
the gradient (the beat marked replaced with no query), a fourth fails the job. A beat
that breaks the picture render once node runs is the render net's (111d, inside
`render.render_picture`: the failing beats simplified and the picture rendered again);
when the net gives up (`render.NetExhausted`) naming no beat at all, the rescue takes
one plain fallback - every overlay layer stripped from every beat, rewound to
`rendering` - and any other exhausted net fails the job (111g's hook). A failed technical
check (`QaFailed`) offers the beats its detail names plus "deliver with a note" (the
fallback: the check joins `job.json.waived_checks` and `qa` runs again, the check
delivered as `warn`). At most `MAX_RESCUES` rescues per run; every decision is a
`job.json.decisions` row and an `editor:` job.log line, every rescue a `rescue:` line.

A job still fails when there is nothing to deliver: any exception in `transcribing` or
`planning` (no usable recording, face or transcript; both planners down), the hard cap
(`ledger.BudgetExceeded`) or a missing price (`LedgerError`), the watchdog's kill, the
render engine missing (`node`), `work/cut.mp4`, a stem or the picture missing before
the mux, deliverables missing after the gate, or a rescue that ran out of options. A
failure marks the job `failed` at that step with the fixed user-facing sentence from
`ERROR_TEXT` and the exception text as `detail` (11.1), whose first line also ends the
job.log failure line (065); a failed technical check adds its name to the sentence
(10.1); the CLI planner's spent quota has its own sentence (`claude_code.QUOTA_SENTENCE`,
065); a paid adapter's `ledger.BudgetExceeded`, raised before its call, becomes "Budget
exceeded at step X." with the ledger rows so far left on job.json for the page (11.3).

A failed job can be run again from the step it failed at (043): `jobs.requeue` sends
it back to `uploaded` carrying `retry_from`, and `start_step` picks the step to enter
at, so everything the failed run left on disk - the transcript, the plan, the
per-job asset cache (5.6), the picture - is the retry's input and is never paid for
twice. A retry from `rendering` therefore calls no planner and no image source, one
from `sourcing` searches only the beats the cache does not have, and one from
`planning` re-transcribes nothing. What the failed run did pay for stays on
`job.json`; the retry's own calls are new rows beside it.

The `planning` step builds the PlanRequest from `job.json`, `brief.md`, `refs.json`
and `work/asr.json` (2.3), calls the planner twice (picture, then sound; 8.1) with
the grammar (`grammar`, ticket 009) after each call: a rejected call is re-sent
exactly once with the previous output and the violation list (`PlanFeedback`), and the
retry is logged in `job.log` (8.2); a reply the models refuse (`PlanInvalid`) takes the
same path. A second rejection of the picture plan goes to the editor (097): tiling and
runtime breaks are re-tiled by code, then up to `MAX_EDITOR_ROUNDS` rounds of editor
choices on the grammar's structured violations, then the soft rules are kept with a
`kept by the editor:` warning (`keep_soft`), and a hard truth that survives takes the
forced fallback (a beat -> `replace_visual`; the cut -> keep the whole recording; an
unused must-use reference -> shown on its safest beat). A second rejection of the sound
story drops the cues of the beats its violations name, then keeps the soft rules. Only
a plan that still breaks a hard truth, or two replies with no parseable plan, fails the
job at `planning` with the list in `job.json.error` and on the page. The planner is
bound to the job first, once per run of the step, so a real adapter writes its prompt
under this run's `work/planner/run<n>/` (065) and records a ledger row per call and
retry (8.3), and the picture plan's `prompt_version` is recorded in `job.json`. Before
the first call code picks the job's topic and two worked examples (077,
`reference.examples`: the style's v2 cards, then the topic, then Tier B first); the
request carries them, `job.json` and `plan.validated.json` record the topic and the
examples' ids, and `job.log` names them (097: a failure there plans with no examples
or pairings, noted). The sound call receives the snapped picture plan, the catalogue
tags and (076) one music pairing line per reference v2 card (`reference.music`;
`job.log` says how many, or none until the cards are v2). The step builds
the captions (`captions.build`, 6.1-6.3: cut,
hidden from the finale, paged, laid out) from the snapped plan and its clamped
keywords and writes `work/plan.raw.json` and `work/sound.raw.json` (the planner's last
output), `work/plan.json` and `work/sound.json` (snapped and clamped: what the
renderer, the gate and the sheet read), `work/plan.validated.json` (both plus the
clamps and warnings) and `work/captions.json`. The style is the spec
`job.json.style` names (resolved at upload, ticket 008): the PlanRequest carries its
numbers and prose (1.2), the grammar reads its counts and the pager its `captions`
numbers and typography. The specs are loaded once by whoever
builds the worker (`create_app`, smoke) and passed in; a job naming a style that is
not loaded runs with the default style (`styles.DEFAULT`), noted in `job.log` and in
`job.json.style_notice` (097).

Entering `sourcing` or `rendering` first normalises the job's refs (`media.normalise_refs`,
111a), so a retry on a job uploaded before intake converted them is fixed too.

`sourcing` runs the asset step (`assets.Sourcing`, ticket 016): every sourced beat
gets its asset through the 4.4 ladder, and the step writes `work/assets.json`,
`out/rights.json` and `out/credits.md`; a configured source with no adapter yet is
noted in `job.log`. `rendering` runs the whole render (`render.Renderer`, Remotion
plus ffmpeg by default; tickets 004, 005 and 022): the presenter cut, the voice stem, the
picture, the sound director's music and SFX stems, the master and the mux to
`out/short.mp4`, writing the picture render's frame progress into `job.json.progress` as
the job page's percentage (11.1).

The audio catalogue (7.2, ticket 022) is loaded once by whoever builds the worker, like
the specs, and used twice: the sound call is told its tag words (8.1), and the renderer
mixes from it. An empty catalogue - the shipped one, until the operator seeds it - leaves
the short as the voice alone.

`qa` runs the technical gate (`qa.gate.Gate`: T1-T13, 032) which writes `out/qa.json`;
a failing check is rescued as above (a waived check is `warn`). The gate is built with
the same specs the grammar judged the plan by, since T8 re-validates the plan. When
every check passes the gate composes `out/contact.jpg`, and once `short.mp4`,
`contact.jpg`, `rights.json` and `credits.md` exist (10.4) the critic (`qa.critic`, 033;
10.2) scores the short from the sheet, the strips and the plan and writes its report
into the same `out/qa.json`. The critic is advisory until the calibration streak flips
it (034, `qa.calibration`): one that cannot answer leaves an `unavailable` report and
the job is `delivered` all the same; only its hard-cap refusal (`BudgetExceeded`) fails
the job, as every refused paid call does (11.3). The critic is injected like the
adapters (`FakeCritic` unless the app passes the configured one). Once the critic has
scored, the sheet is composed again so its summary panel carries the E1-E10 scores and
the fix notes (035; the critic saw the panel without them). After `delivered` the
verdict (10.4) is applied once: a blocking critic settles the job `passed` (>= 7) or
`rejected` at once; otherwise it waits for the phone rating on the job page. Then
`meta.write` records `out/meta.json` (035): the proof of the bar the gate reads.

Between `delivered` and the verdict the advisory self-inventory runs (074,
`reference.own`): `out/short.mp4` through the same reference tool as the references,
the card in `out/inventory.json` and its comparison with the style's reference cards in
`meta.json`. It never changes the short and never fails the job: any failure writes
`not_analysed` with the reason. It is injected like the critic; the default is Gemini
with no key, which sends nothing. The whole post-delivery tail (the inventory, the
verdict, `meta.write`) is guarded (097): an exception in any of them is a job.log line
and the job stays delivered.

`Worker` wraps `run_job` in a FIFO queue on one daemon thread for the web app;
`run_next` drains one job synchronously so tests and smoke use the same code path
without threads. Both take the `editor` (097); None is `Editor(planner)` on the job's
planner and the renderer's geocoder, so the fake planner makes every decision the
code's fallback.

Limits (11.2): the queue depth counts the running job, the waiting jobs and the
slots the upload route has reserved; `submit`/`reserve` raise `QueueFull` at
`max_queue`. A waiting job's position is its 1-based place among the waiting jobs.
111e: time budgets per step (`budgets.Budgets`): one `subproc.Watchdog` per job,
armed afresh as each step is entered (so a retry or a rescue rewind gets the full
budget of its step), the rendering budget scaled to the short's frames, a render that
still prints progress killed only by the stall clock, and the job's backstop computed
from the step budgets. Whichever limit fires, the running step's subprocesses are
killed, the job is `failed` at that step with a sentence naming the step and saying
Retry starts it fresh, and the worker moves on.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import traceback
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from shortsmith import (
    assets,
    captions,
    geo,
    grammar,
    jobs,
    media,
    meta,
    presenter,
    render,
    sound,
    styles,
    subproc,
)
from shortsmith.budgets import MAX_FRAMES, Budgets, timeout_message
from shortsmith.budgets import defaults as default_budgets
from shortsmith.contracts import (
    PICTURE_TREATMENTS,
    Constraints,
    EditorDecision,
    PicturePlan,
    PlanFeedback,
    PlanReference,
    PlanRequest,
    PlanStyle,
    ReferenceRecord,
    SoundStory,
    Transcript,
    ValidatedPlan,
    Violation,
    WorkedExample,
)
from shortsmith.editor import (
    DELIVER,
    REPLACE,
    Editor,
    Option,
    RepairError,
    Snag,
    beat_options,
    make_snag,
    reference_options,
    repairs,
)
from shortsmith.jobs import Clock, Job, Status
from shortsmith.ledger import BudgetExceeded, LedgerError
from shortsmith.planner import PlanInvalid, Planner, PlannerError, PlannerUnavailable
from shortsmith.planner.claude_code import QUOTA_SENTENCE, QuotaSpent
from shortsmith.qa import calibration
from shortsmith.qa import critic as critic_module
from shortsmith.qa.critic import Critic, FakeCritic
from shortsmith.qa.gate import Gate, TechnicalGate
from shortsmith.reference import INVENTORY_DIR, examples, music, own
from shortsmith.render import NetExhausted, RemotionRenderer, Renderer
from shortsmith.styles import StyleError, StyleSpec
from shortsmith.transcriber import Transcriber

log = logging.getLogger(__name__)

DEFAULT_MAX_QUEUE = 3
MAX_RESCUES = 12  # 097: step rescues per run
# 111a: the steps that first read the refs; entering either normalises them (idempotent).
NORMALISED_STEPS: frozenset[str] = frozenset({"sourcing", "rendering"})
MAX_EDITOR_ROUNDS = 3  # 097: editor rounds on a picture plan rejected twice
FORCE_PASSES = 4  # 097: forced fallbacks on hard survivors, pass after pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def step_frames(job: Job) -> int:
    """111e: the frames the rendering budget scales with - the plan's cut list at the
    render's frame rate, or the longest short when the plan cannot be read."""
    try:
        plan = PicturePlan.model_validate_json(
            (job.work_dir / "plan.json").read_text(encoding="utf-8")
        )
        return round(presenter.total_duration(presenter.cut_list(plan)) * render.FPS)
    except (OSError, ValueError):
        return MAX_FRAMES


def arm_step(watchdog: subproc.Watchdog, budgets: Budgets, job: Job, step: str) -> float:
    """111e: a fresh budget for `step` on the job's watchdog; its seconds. Entering a
    step, a retry and a rescue rewind all come through here (111g's plain reel too)."""
    frames = step_frames(job) if step == "rendering" else 0
    budgets.arm(watchdog, step, frames=frames)
    return budgets.step_s(step, frames=frames)

ERROR_TEXT: dict[str, str] = {
    "transcribing": "We could not transcribe the recording.",
    "planning": "We could not plan the short.",
    "sourcing": "We could not find or make the pictures for the short.",
    "rendering": "We could not render the short.",
    "qa": "The short failed a technical check.",
}
DELIVERABLES = meta.DELIVERABLES  # 10.4: short.mp4, contact.jpg, rights.json, credits.md

MAX_DURATION_S = 60.0  # 3.1 / T3 (global, not a style number)

_REFS = TypeAdapter(list[ReferenceRecord])
Specs = Mapping[str, StyleSpec]


class NotRunnable(Exception):
    """The job is not `uploaded`, so the worker has nothing to start."""


class QueueFull(Exception):
    """`max_queue` jobs are running, waiting or reserved; the submission is refused."""


Step = Callable[[Job], None]


def run_job(
    job: Job,
    *,
    transcriber: Transcriber,
    planner: Planner,
    renderer: Renderer | None = None,
    gate: Gate | None = None,
    sourcing: assets.Sourcing | None = None,
    specs: Specs | None = None,
    library: sound.Library | None = None,
    detector: presenter.FaceDetector | None = None,
    critic: Critic | None = None,
    inventory: own.SelfInventory | None = None,
    inventory_dir: Path = INVENTORY_DIR,
    budgets: Budgets | None = None,
    clock: Clock = _utc_now,
    watchdog_interval_s: float = 1.0,
    editor: Editor | None = None,
) -> Job:
    if job.status != "uploaded":
        raise NotRunnable(f"job {job.id} is {job.status!r}, not 'uploaded'")
    renderer = renderer or RemotionRenderer()
    specs = specs if specs is not None else render.loaded_styles()
    gate = gate or TechnicalGate(specs=specs)
    sourcing = sourcing or assets.Sourcing()
    library = library if library is not None else sound.load_catalogue()
    detector = detector or presenter.HaarDetector()
    # 033: the app passes the configured critic (`CRITIC`); there is no keyless real one.
    critic = critic or FakeCritic()
    # 097: the editor asks the job's own planner; the fake answers with every fallback.
    editor = editor or default_editor(planner, renderer, clock=clock)
    steps: list[tuple[Status, Step]] = [
        ("transcribing", lambda j: _transcribe(j, transcriber, detector, specs)),
        ("planning", lambda j: _plan(j, planner, specs, library, inventory_dir, editor)),
        ("sourcing", lambda j: _source(j, sourcing, specs, clock)),
        ("rendering", lambda j: _render(j, renderer, clock, library)),
        ("qa", lambda j: _qa(j, gate, critic)),
    ]
    rescue = Rescue(editor=editor, specs=specs, clock=clock)
    index = jobs.STEPS.index(start_step(job))
    watchdog: subproc.Watchdog | None = None
    if budgets is not None:
        watchdog = budgets.watchdog(clock=clock, interval_s=watchdog_interval_s)
        watchdog.start()
    try:
        while index < len(steps):
            status, step = steps[index]
            job = jobs.transition(job, status)
            detail = ""
            step_s = 0.0
            if watchdog is not None and budgets is not None:
                step_s = arm_step(watchdog, budgets, job, status)  # 111e: fresh each entry
            try:
                with subproc.guarded(watchdog):
                    if status in NORMALISED_STEPS:  # 111a: an old job's refs, made real
                        for line in media.normalise_refs(job.path):
                            jobs.note(job, line, now=clock)
                    step(job)
            except Exception as exc:  # noqa: BLE001 - every step failure lands in job.json the same way
                detail = f"{exc}\n{traceback.format_exc()}"
                if watchdog is None or not watchdog.check():
                    resume = rescue.attempt(job, status, exc)
                    if resume is not None:
                        job = jobs.rewind(job, resume, rescue.why)
                        index = jobs.STEPS.index(resume)
                        continue
                    violations = exc.violations if isinstance(exc, PlanRejected) else []
                    return jobs.fail(
                        job,
                        step=status,
                        message=failure_message(status, exc),
                        detail=detail,
                        violations=violations,
                    )
            if watchdog is not None and budgets is not None and watchdog.check():
                message = timeout_message(
                    status, watchdog.reason, step_s=step_s, stall_s=budgets.stall_s,
                    backstop_s=budgets.backstop_s(),
                )  # fmt: skip
                return jobs.fail(job, step=status, message=message, detail=detail)
            index += 1
    finally:
        if watchdog is not None:
            watchdog.stop()
    delivered = jobs.transition(job, "delivered")
    if any(c.status == "running" for c in delivered.record.changes):
        delivered = jobs.finish_changes(delivered, now=clock)  # 098: a change re-rendered
    return _after_delivery(delivered, inventory, clock)


def _after_delivery(delivered: Job, inventory: own.SelfInventory | None, clock: Clock) -> Job:
    """The post-delivery tail, each part guarded (097): a failure is a job.log line and
    the job stays delivered."""
    # 074: the self-inventory, advisory: our short through the reference tool; any
    # failure is `not_analysed` in out/inventory.json and the job stays delivered.
    try:
        (inventory or own.keyless()).run(delivered)
    except Exception as exc:  # noqa: BLE001 - advisory, never fails a delivered short
        jobs.note(delivered, f"self-inventory failed after delivery: {_first_line(exc)}")
    # 10.4 / 034: a blocking critic settles the short at once (`passed` at 7, else
    # `rejected`); while advisory, or with no critic verdict, it stays `delivered`
    # until the phone rating comes in. Either way every deliverable stays served.
    settled = delivered
    try:
        settled = calibration.apply(delivered, now=clock)
    except Exception as exc:  # noqa: BLE001 - the verdict waits for the phone rating
        jobs.note(delivered, f"verdict not applied after delivery: {_first_line(exc)}")
        settled = jobs.load(delivered.path)
    # 035: the proof of the bar, written once the verdict is in; a rating rewrites it.
    try:
        meta.write(settled, now=clock)
    except Exception as exc:  # noqa: BLE001 - a rating rewrites it later
        jobs.note(settled, f"meta.json not written after delivery: {_first_line(exc)}")
    return settled


def default_editor(
    planner: Planner, renderer: Renderer | None, *, clock: Clock = _utc_now
) -> Editor:
    """097: the editor on the job's planner and the renderer's geocoder (the bundled
    gazetteer when the renderer has none), so `frame_markers` is offered only on names
    the render will resolve."""
    coder = getattr(renderer, "geocoder", None)
    return Editor(planner, geocoder=coder if isinstance(coder, geo.Geocoder) else None,
                  clock=clock)  # fmt: skip


def start_step(job: Job) -> Status:
    """Where this run enters the pipeline: the first step, or the step a retry
    (`jobs.requeue`, 043) re-enters at. Everything before it stays as the failed run
    left it, which is the whole point: the transcript, the plan and the assets on disk
    are the retry's input and are never paid for twice (5.6)."""
    retry_from = job.record.retry_from
    return retry_from if retry_from in jobs.STEPS else jobs.STEPS[0]


def failure_message(status: Status, exc: Exception) -> str:
    """The fixed sentence for the step; a failed check appends its name (10.1); the
    hard cap names the step it stopped before (11.3)."""
    if isinstance(exc, BudgetExceeded):
        return f"Budget exceeded at step {exc.step}."
    if isinstance(exc, presenter.NoFace):
        return str(exc)  # 3.3: the face sentence, not the transcriber's
    if isinstance(exc, QuotaSpent):
        return QUOTA_SENTENCE  # 065: switch the model and press Retry
    message = ERROR_TEXT[status]
    if isinstance(exc, QaFailed):
        return f"{message[:-1]} ({exc.check})."
    return message


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def _transcribe(
    job: Job, transcriber: Transcriber, detector: presenter.FaceDetector, specs: Specs
) -> None:
    assert job.record.input is not None or (job.input_dir / "raw.mp4").is_file()
    raw = job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")
    # 013: measure first, so a recording with no face costs no transcription. 097: a
    # style that is not loaded is measured with the default (`style_of`).
    spec = style_of(job, specs)
    presenter.measure(job, spec, detector=detector)
    transcript = transcriber.bind(job).transcribe(raw)
    (job.work_dir / "asr.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")


def style_of(job: Job, specs: Specs) -> StyleSpec:
    """The loaded spec `job.json.style` names. 097: a name outside the loaded set runs
    with the default style (`styles.DEFAULT`): `job.json.style` becomes it, the notice
    goes to `style_notice` for the page and one line to `job.log`. Only a loaded set
    without the default is a config problem (`StyleError`)."""
    spec = specs.get(job.record.style)
    if spec is not None:
        return spec
    current = jobs.load(job.path).record
    spec = specs.get(current.style)
    if spec is not None:
        return spec
    fallback = specs.get(styles.DEFAULT)
    if fallback is None:
        raise StyleError(
            f"job {job.id}: style {current.style!r} is not a loaded spec "
            f"(loaded: {sorted(specs)}) and neither is the default {styles.DEFAULT!r}"
        )
    notice = f"{current.style} is not available, using {fallback.name}"
    jobs.amend(job, style=fallback.name, style_notice=notice)
    jobs.note(
        job,
        f"style: {current.style!r} is not a loaded spec (loaded: {sorted(specs)}); the job "
        f"runs with the default {fallback.name!r} (plain fallback)",
    )
    return fallback


def build_plan_request(
    job: Job,
    specs: Specs,
    inventory_dir: Path = INVENTORY_DIR,
    *,
    note: Callable[[str], None] | None = None,
) -> PlanRequest:
    """PlanRequest per 2.3 from the job's files; nothing else reaches the planner. 077:
    the topic and the two worked examples from the v2 cards in `inventory_dir`, told to
    `note` in one line. 097: a failure picking them plans with no examples (or no music
    pairings), noted."""
    transcript = Transcript.model_validate_json(
        (job.work_dir / "asr.json").read_text(encoding="utf-8")
    )
    brief = (job.input_dir / "brief.md").read_text(encoding="utf-8")
    refs_path = job.input_dir / "refs.json"
    refs = _REFS.validate_json(refs_path.read_text(encoding="utf-8")) if refs_path.is_file() else []
    spec = style_of(job, specs)
    tell = note or _ignore
    try:
        topic, worked = examples.for_job(brief, transcript, spec.name, inventory_dir)
    except Exception as exc:  # noqa: BLE001 - 097: plan without examples rather than fail
        topic, worked = examples.TopicPick(name=None, source="none"), []
        tell(f"worked examples: none ({_first_line(exc)}; plain fallback)")
    try:
        pairings = music.for_job(inventory_dir)
    except Exception as exc:  # noqa: BLE001 - 097: plan without pairings rather than fail
        pairings = []
        tell(f"music pairings: none ({_first_line(exc)}; plain fallback)")
    tell(examples_line(topic, worked))
    tell(music_line(pairings))
    return PlanRequest(
        brief=brief,
        style=PlanStyle(
            name=spec.name, status=spec.status, numbers=spec.numbers(), prose=spec.prose
        ),
        style_note=job.record.style_note,
        transcript=transcript,
        references=[
            PlanReference(
                id=r.id,
                kind="image" if r.kind == "image" else "clip_frame",
                caption=r.caption,
                width=r.width,
                height=r.height,
            )
            for r in refs
        ],
        constraints=Constraints(
            max_duration_s=MAX_DURATION_S,
            target_duration_s=min(MAX_DURATION_S, transcript.duration_s),
        ),
        asset_policy="any",
        topic=topic.name,
        examples=worked,
        music=pairings,
    )


def _ignore(_line: str) -> None:
    return None


def examples_line(topic: examples.TopicPick, worked: Sequence[WorkedExample]) -> str:
    """077: the job.log line naming the topic (and how it was picked) and the examples."""
    named = f"topic {topic.name} ({topic.source})" if topic.name else "topic none (style only)"
    return f"worked examples: {named}; {', '.join(e.video_id for e in worked) or 'none'}"


def music_line(pairings: Sequence[str]) -> str:
    """076: the job.log line saying how many reference cards the sound call learns music
    from; none until the cards are v2 (073), and then the planner picks from the moods."""
    if not pairings:
        return f"music pairings: none ({music.NO_PAIRINGS[1:-1]})"
    return f"music pairings: {len(pairings)} reference cards"


class PlanRejected(Exception):
    """The grammar rejected the planner's `call` ("picture" or "sound") twice (8.2).
    097: `items` are the structured violations of `raw`, the last plan that parsed (None
    when no reply parsed: two `PlanInvalid`s), for the editor."""

    def __init__(
        self,
        call: str,
        violations: Sequence[str],
        *,
        items: Sequence[Violation] = (),
        raw: BaseModel | None = None,
    ) -> None:
        self.call = call
        self.violations = list(violations)
        self.items = list(items)
        self.raw = raw
        listed = "\n".join(self.violations)
        super().__init__(
            f"the {call} plan was rejected twice; violations after the retry:\n{listed}"
        )


def _write(job: Job, name: str, model: BaseModel) -> None:
    (job.work_dir / name).write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _with_one_retry[Raw: BaseModel, Checked](
    job: Job,
    label: str,
    call: Callable[[PlanFeedback | None], Raw],
    raw_name: str,
    validate: Callable[[Raw], Checked | grammar.Violations],
) -> Checked:
    """One planner call, validated; a rejection (the grammar's, or a reply the models
    refuse: `PlanInvalid`) is re-sent once with the previous output and the list (8.2),
    and a second rejection raises `PlanRejected` with the list, carrying the last plan
    that parsed and its structured violations (097: the editor's input)."""
    feedback: PlanFeedback | None = None
    last_raw: Raw | None = None
    last_items: list[Violation] = []
    for attempt in (1, 2):
        try:
            raw = call(feedback)
        except PlanInvalid as exc:
            previous, lines = exc.reply, exc.violations
        else:
            _write(job, raw_name, raw)
            checked = validate(raw)
            if not isinstance(checked, grammar.Violations):
                return checked
            previous, lines = raw.model_dump_json(indent=2), checked.lines()
            last_raw, last_items = raw, list(checked.items)
        if attempt == 2:
            raise PlanRejected(label.split()[0], lines, items=last_items, raw=last_raw)
        jobs.note(job, f"{label} rejected, re-sending once: {'; '.join(lines)}")
        feedback = PlanFeedback(previous=previous, violations=lines)
    raise AssertionError("unreachable")


def bubble_lines(picture: PicturePlan, transcript: Transcript) -> list[str]:
    """063 (2): one job.log line per bubble of the validated plan - the beat, the
    shape, the text and the transcript words (`first`-`last`) it came from - so every
    bubble's words can be checked against the recording."""
    words = transcript.words
    lines: list[str] = []
    for beat in picture.beats:
        for bubble in beat.bubbles:
            said = " ".join(w.text for w in words[bubble.first : bubble.last + 1])
            lines.append(
                f"bubble: {beat.id}: {bubble.shape} {bubble.text!r} from words "
                f"{bubble.first}-{bubble.last} {said!r} (063)"
            )
    return lines


PictureCheckFn = Callable[..., grammar.PictureCheck | grammar.Violations]


def _plan(
    job: Job,
    planner: Planner,
    specs: Specs,
    library: sound.Library,
    inventory_dir: Path = INVENTORY_DIR,
    editor: Editor | None = None,
) -> None:
    request = build_plan_request(job, specs, inventory_dir, note=lambda line: jobs.note(job, line))
    ids = [e.video_id for e in request.examples]
    jobs.amend(job, topic=request.topic, examples=ids)
    spec = style_of(job, specs)
    transcript = request.transcript
    must_use = grammar.must_use_ids(request.brief, request.references)
    editor = editor or Editor(planner)
    planner = planner.bind(job)

    def check_picture(
        raw: PicturePlan, *, keep_soft: bool = False
    ) -> grammar.PictureCheck | grammar.Violations:
        return grammar.validate_picture(
            raw, transcript, spec, brief=request.brief, must_use=must_use,
            references=[r.id for r in request.references], keep_soft=keep_soft,
        )  # fmt: skip

    try:
        checked = _with_one_retry(
            job,
            "picture plan",
            lambda feedback: planner.plan_picture(request, feedback=feedback),
            "plan.raw.json",
            check_picture,
        )
    except PlanRejected as exc:
        if not isinstance(exc.raw, PicturePlan):
            raise  # 097: no plan parsed twice - nothing for the editor to work on
        checked = _rescue_picture(
            job, exc, check_picture, editor, transcript, request.references,
            spec.broll.treatments, spec.broll.enter_transitions,
        )
    picture = checked.picture
    # 8.3 / 035: the prompt and the spec the plan was judged by, for `meta.json`.
    jobs.amend(job, prompt_version=picture.prompt_version, style_version=spec.version)
    for line in bubble_lines(picture, transcript):
        jobs.note(job, line)

    def check_sound(
        raw: SoundStory, *, keep_soft: bool = False
    ) -> grammar.SoundCheck | grammar.Violations:
        return grammar.validate_sound(raw, picture, spec, keep_soft=keep_soft)

    try:
        sound_check = _with_one_retry(
            job,
            "sound story",
            lambda feedback: planner.plan_sound(
                request, picture, library.tags(), feedback=feedback
            ),
            "sound.raw.json",
            check_sound,
        )
    except PlanRejected as exc:
        if not isinstance(exc.raw, SoundStory):
            raise
        sound_check = _rescue_sound(job, exc, exc.raw, check_sound, editor.clock)

    validated = ValidatedPlan(
        picture=picture,
        sound=sound_check.sound,
        clamps=checked.clamps + sound_check.clamps,
        warnings=checked.warnings + sound_check.warnings,
        topic=request.topic,
        examples=ids,
    )
    paged = captions.build(transcript, picture, spec)
    _write(job, "plan.json", picture)
    _write(job, "sound.json", sound_check.sound)
    _write(job, "plan.validated.json", validated)
    _write(job, "captions.json", paged)


# --- 097: the editor on a plan rejected twice ---------------------------------------------

KEPT_PREFIX = "kept by the editor: "  # grammar.kept_note's warning
_TILING = re.compile(r"^(the first beat starts at|gap: |overlap: |beats end at )")
_MUST_USE = re.compile(r"must-use reference '([^']+)'")


def _is_tiling(v: Violation) -> bool:
    return v.rule == "3.1" and not v.hard and _TILING.match(v.message) is not None


def _forced(
    job: Job, step: str, beat_id: str | None, problem: str, choice: str, reason: str,
    clock: Clock,
) -> None:  # fmt: skip
    """A decision code made on its own (by="fallback"): recorded like the editor's."""
    decision = EditorDecision(
        at=clock(), step=step, beat_id=beat_id, problem=problem.strip()[:400], choice=choice,
        reason=reason, by="fallback",
    )  # fmt: skip
    jobs.decide(job, decision, now=clock)


def _mark_replaced(job: Job, beat_id: str) -> None:
    """The beat joins `job.json.replaced`: sourcing re-sources it with the ladder (096)."""
    current = jobs.load(job.path).record.replaced
    if beat_id not in current:
        jobs.amend(job, replaced=[*current, beat_id])


def _recording_end(plan: PicturePlan, transcript: Transcript) -> float:
    """Where the last beat must end on the planner's (recording) timeline: the end of the
    last kept span, which the cut maps to the output runtime."""
    if plan.cut.keep:
        return max(s.end for s in plan.cut.keep)
    return transcript.duration_s


def _problem(items: Sequence[Violation]) -> str:
    return "; ".join(f"({v.rule}) {v.message}" for v in items)


def _planning_snags(
    plan: PicturePlan,
    violations: Sequence[Violation],
    transcript: Transcript,
    references: Sequence[PlanReference],
    geocoder: geo.Geocoder,
    treatments: Sequence[str] = PICTURE_TREATMENTS,
    enters: Sequence[str] = (),
) -> list[Snag]:
    """One snag per beat the violations name (its options from `beat_options`), one per
    plan-level hard truth (the cut -> keep the whole recording; an unused must-use
    reference -> its safe beats), and one for the plan-level soft rules (keep only)."""
    ids = {b.id for b in plan.beats}
    by_beat: dict[str, list[Violation]] = {}
    plan_level: list[Violation] = []
    for v in violations:
        if v.beat_id is not None and v.beat_id in ids:
            by_beat.setdefault(v.beat_id, []).append(v)
        else:
            plan_level.append(v)
    snags: list[Snag] = []

    def sid() -> str:
        return f"s{len(snags) + 1}"

    for beat_id, items in by_beat.items():
        hard = any(v.hard for v in items)
        varies = any(grammar.VARY_ENTER in v.message for v in items)  # 110b: enter swaps
        options = beat_options(plan, beat_id, hard=hard, geocoder=geocoder,
                               treatments=treatments, enters=enters if varies else ())  # fmt: skip
        if options:
            snags.append(make_snag(sid(), "planning", beat_id, _problem(items), hard=hard,
                                   options=options, lines=[str(v) for v in items]))  # fmt: skip
    captions_of = {r.id: r.caption for r in references}
    soft = [v for v in plan_level if not v.hard]
    for v in plan_level:
        if not v.hard:
            continue
        options: list[Option] = []
        if v.rule in ("3.4", "3.1"):
            options = [Option("no_cut", "keep the whole recording as the cut (every word kept, "
                              "in order; the pauses are still tightened)",
                              lambda p: repairs.no_cut(p, transcript))]  # fmt: skip
        elif (m := _MUST_USE.search(v.message)) is not None:
            ref = m.group(1)
            options = reference_options(plan, ref, captions_of.get(ref, ""), transcript)
        if options:
            snags.append(make_snag(sid(), "planning", None, _problem([v]), hard=True,
                                   options=options, lines=[str(v)]))  # fmt: skip
    if soft:
        keep = Option("keep", "keep the plan as it is (the small break is noted)")
        snags.append(make_snag(sid(), "planning", None, _problem(soft), hard=False,
                               options=[keep], lines=[str(v) for v in soft]))  # fmt: skip
    return snags


def _apply(job: Job, plan: PicturePlan, option: Option) -> PicturePlan:
    if option.apply is None:
        return plan
    try:
        patched = option.apply(plan)
    except RepairError as exc:
        jobs.note(job, f"editor: {option.id} could not apply: {exc}")
        return plan
    if option.replaces is not None:
        _mark_replaced(job, option.replaces)
    return patched


def _rescue_picture(
    job: Job,
    exc: PlanRejected,
    check: PictureCheckFn,
    editor: Editor,
    transcript: Transcript,
    references: Sequence[PlanReference],
    treatments: Sequence[str] = PICTURE_TREATMENTS,
    enters: Sequence[str] = (),
) -> grammar.PictureCheck:
    """097: the picture plan the planner sent twice, repaired: tiling re-tiled by code,
    up to `MAX_EDITOR_ROUNDS` editor rounds, the soft rules kept, the hard survivors
    forced. Raises `PlanRejected` when a hard truth still stands."""
    assert isinstance(exc.raw, PicturePlan)
    plan, items = exc.raw, list(exc.items)
    clock = editor.clock
    jobs.note(job, f"picture plan rejected twice; the editor takes over ({len(items)} "
              "violations)")  # fmt: skip
    tiling = [v for v in items if _is_tiling(v)]
    if tiling:
        try:
            plan = repairs.retile(plan, _recording_end(plan, transcript))
            _forced(job, "planning", None, _problem(tiling), "re-tile the beats edge to edge",
                    "the beats must tile the cut; code closes the gaps", clock)  # fmt: skip
        except RepairError as err:
            jobs.note(job, f"editor: re-tiling failed: {err}")
        result = check(plan)
        if isinstance(result, grammar.PictureCheck):
            return result
        items = list(result.items)
    geocoder = editor.geocoder_for(job)
    kept: set[str] = set()
    for _ in range(MAX_EDITOR_ROUNDS):
        open_items = [v for v in items if str(v) not in kept]
        snags = _planning_snags(plan, open_items, transcript, references, geocoder,
                                treatments, enters)  # fmt: skip
        if not snags:
            break
        changed = False
        for choice in editor.pick(job, snags, step="planning", plan=plan, transcript=transcript):
            if choice.option.apply is None:
                kept.update(choice.snag.lines)
                continue
            patched = _apply(job, plan, choice.option)
            changed = changed or patched != plan
            plan = patched
        result = check(plan)
        if isinstance(result, grammar.PictureCheck):
            return result
        items = list(result.items)
        if not changed:
            break
    forced = _force_hard(job, plan, check, transcript, references, "planning", clock)
    if isinstance(forced, grammar.Violations):
        raise PlanRejected("picture", forced.lines(), items=forced.items, raw=None)
    kept_n = sum(w.startswith(KEPT_PREFIX) for w in forced.warnings)
    jobs.note(job, f"picture plan kept by the editor ({kept_n} small breaks noted)")
    return forced


def _force_hard(
    job: Job,
    plan: PicturePlan,
    check: PictureCheckFn,
    transcript: Transcript,
    references: Sequence[PlanReference],
    step: str,
    clock: Clock,
) -> grammar.PictureCheck | grammar.Violations:
    """097: validate with the soft rules kept; every hard violation left takes its forced
    fallback (a beat -> `replace_visual`; the cut or a beat with no length on it -> keep
    the whole recording; an unused must-use reference -> its safest beat), pass after
    pass, until the plan passes or nothing more can be done."""
    captions_of = {r.id: r.caption for r in references}
    result = check(plan, keep_soft=True)
    for _ in range(FORCE_PASSES):
        if isinstance(result, grammar.PictureCheck):
            return result
        patched = plan
        for v in result.items:
            if not v.hard:
                continue
            ids = {b.id for b in patched.beats}
            if v.rule == "3.4" or (v.rule == "3.1" and "removed audio" in v.message):
                patched = repairs.no_cut(patched, transcript)
                choice = "keep the whole recording as the cut (every word kept)"
            elif (m := _MUST_USE.search(v.message)) is not None:
                ref = m.group(1)
                options = reference_options(patched, ref, captions_of.get(ref, ""), transcript)
                if not options:
                    continue
                patched = _apply(job, patched, options[0])
                choice = options[0].label
            elif v.beat_id in ids and v.beat_id != patched.finale.beat_id:
                assert v.beat_id is not None
                patched = repairs.replace_visual(patched, v.beat_id)
                _mark_replaced(job, v.beat_id)
                choice = "replace this beat's visual with a plain re-sourced picture"
            else:
                continue
            _forced(job, step, v.beat_id, str(v), choice,
                    "a hard truth is never kept; code's forced fallback", clock)  # fmt: skip
        if patched == plan:
            break
        plan = patched
        result = check(plan, keep_soft=True)
    return result


def _rescue_sound(
    job: Job,
    exc: PlanRejected,
    story: SoundStory,
    check: Callable[..., grammar.SoundCheck | grammar.Violations],
    clock: Clock,
) -> grammar.SoundCheck:
    """097: the sound story rejected twice: the cues of every beat a violation names are
    dropped, then the soft rules are kept; a hard one left fails as before."""
    beats = sorted({v.beat_id for v in exc.items if v.beat_id is not None})
    if beats:
        kept = [c for c in story.cues if c.beat_id not in beats]
        story = story.model_copy(update={"cues": kept})
        for beat_id in beats:
            named = [v for v in exc.items if v.beat_id == beat_id]
            _forced(job, "planning", beat_id, _problem(named), "drop this beat's sound cues",
                    "the sound story was rejected twice; these cues go", clock)  # fmt: skip
    result = check(story, keep_soft=True)
    if isinstance(result, grammar.Violations):
        raise PlanRejected("sound", result.lines(), items=result.items, raw=None)
    jobs.note(job, f"sound story kept by the editor ({len(result.warnings)} small breaks noted)")
    return result


def _source(job: Job, sourcing: assets.Sourcing, specs: Specs, clock: Clock) -> None:
    for note in sourcing.notes:
        jobs.note(job, note, now=clock)
    missing = sourcing.missing()
    if missing:
        jobs.note(
            job,
            f"no image source for: {', '.join(missing)}; those rungs are skipped",
            now=clock,
        )
    sourcing.run(job, style_of(job, specs), clock=clock)


def _render(job: Job, renderer: Renderer, clock: Clock, library: sound.Library) -> None:
    def on_progress(pct: int) -> None:
        jobs.set_progress(job, pct, now=clock)

    renderer.render(job, on_progress=on_progress, library=library)


class QaFailed(Exception):
    """A technical check failed, or a deliverable is missing after the gate passed."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__(f"{check}: {detail}")
        self.check = check
        self.detail = detail


def _qa(job: Job, gate: Gate, critic: Critic) -> None:
    report = gate.check(job)
    failed = report.failed
    if failed is not None or not report.passed:
        name = failed.name if failed is not None else "qa"
        raise QaFailed(name, failed.detail if failed is not None else "no checks ran")
    gate.contact_sheet(job)
    missing = [name for name in DELIVERABLES if not (job.out_dir / name).is_file()]
    if missing:
        raise QaFailed("deliverables", f"missing out/{', out/'.join(missing)}")
    # 033 / 10.2: the editorial gate, on the sheet the gate just composed; advisory, so
    # it writes its report (or `unavailable`) and never stops delivery from here.
    critic_module.run(job, critic)
    # 035 / 10.4: the sheet once more, now with the critic's scores and notes drawn in
    # its summary panel (the critic had to see the sheet before it could score it).
    gate.contact_sheet(job)


# --- 097: the step rescue ------------------------------------------------------------------

RESCUED_STEPS: frozenset[str] = frozenset({"sourcing", "rendering", "qa"})
# Nothing to deliver: the render engine, the presenter cut, a stem or the picture missing.
FATAL_TEXT: tuple[str, ...] = (
    "node is not on PATH",
    "work/cut.mp4 is missing",
    "is missing before mux",
)
NOT_RESCUED: tuple[type[BaseException], ...] = (
    BudgetExceeded,
    LedgerError,
    PlannerError,
    PlannerUnavailable,
    PlanRejected,
    presenter.NoFace,
    subproc.Killed,
)
_BEAT = re.compile(r"(?:^|[\s'\"(\[])(b\d+):")
_BEAT_WORD = re.compile(r"\b(b\d+)\b")
STRIP_LABEL = (
    "strip every overlay layer (text pops, bubbles, stickers, highlight, counter, landed "
    "event, motion overlays) on every beat"
)


def rescuable(status: str, exc: BaseException) -> bool:
    """097: the exceptions a rescue may answer: any in sourcing, rendering or qa except
    the hard cap, a missing price, the planners, the face, the watchdog's kill and the
    render engine or its inputs missing; a missing deliverable after the gate."""
    if status not in RESCUED_STEPS or isinstance(exc, NOT_RESCUED):
        return False
    if isinstance(exc, QaFailed) and exc.check == "deliverables":
        return False
    text = str(exc)
    return not any(fatal in text for fatal in FATAL_TEXT)


def named_beat(text: str, beat_ids: Sequence[str]) -> str | None:
    """The first plan beat the message names as `bNN:` (the render's and sourcing's
    shape, e.g. "b09: the map region ... is not in the gazetteer")."""
    for m in _BEAT.finditer(text):
        if m.group(1) in beat_ids:
            return m.group(1)
    return None


def _problem_key(text: str) -> str:
    return re.sub(r"^\s*b\d+:\s*", "", text).strip()


@dataclass
class Rescue:
    """097: the step rescues of one run (see the module docstring): a snag per failure,
    the plan patched, the step to resume from in `attempt`'s return (None: the job
    fails), the rewind's reason in `why`."""

    editor: Editor
    specs: Specs
    clock: Clock
    count: int = 0
    seen: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])
    stripped: bool = False
    patched_checks: set[str] = field(default_factory=set[str])
    why: str = ""

    def attempt(self, job: Job, status: str, exc: Exception) -> Status | None:
        if not rescuable(status, exc):
            return None
        validated = load_validated(job)
        if validated is None:
            return None
        if self.count >= MAX_RESCUES:
            jobs.note(job, f"rescue: the {MAX_RESCUES} rescues of this run are spent; the "
                      "job fails")  # fmt: skip
            return None
        self.count += 1
        problem = _first_line(exc)
        jobs.note(job, f"rescue {self.count}/{MAX_RESCUES}: {status}: {problem}")
        try:
            if isinstance(exc, QaFailed):
                return self._qa(job, exc, validated)
            if isinstance(exc, NetExhausted):
                return self._net_exhausted(job, exc, problem, validated)
            ids = [b.id for b in validated.picture.beats]
            beat_id = named_beat(str(exc), ids)
            if beat_id is not None:
                return self._beat(job, status, beat_id, problem, validated)
        except Exception as err:  # noqa: BLE001 - a rescue that breaks fails the job as before
            jobs.note(job, f"rescue: could not apply ({type(err).__name__}: {_first_line(err)})")
            return None
        jobs.note(job, f"rescue: nothing left to try for {status}: {problem}")
        return None

    # the three kinds of snag

    def _beat(
        self, job: Job, status: str, beat_id: str, problem: str, validated: ValidatedPlan
    ) -> Status | None:
        picture = validated.picture
        key = (beat_id, _problem_key(problem))
        self.seen[key] += 1
        times = self.seen[key]
        if times == 1:
            options = beat_options(picture, beat_id, hard=True,
                                   geocoder=self.editor.geocoder_for(job), keep=False)  # fmt: skip
            if not options:
                return None
            snag = make_snag("s1", status, beat_id, problem, hard=True, options=options)
            choice = self.editor.pick(job, [snag], step=status, plan=picture,
                                      transcript=_transcript(job))[0]  # fmt: skip
            option = choice.option
        elif times == 2:
            option = next(
                (o for o in beat_options(picture, beat_id, hard=True, keep=False)
                 if o.id == REPLACE), None,
            )  # fmt: skip
            if option is None:
                return None
            _forced(job, status, beat_id, problem, option.label,
                    "the same problem came back after the first fix", self.clock)  # fmt: skip
        elif times == 3:
            option = Option(
                "gradient", "show the beat over the gradient",
                lambda p: _gradient(p, beat_id), replaces=beat_id,
            )  # fmt: skip
            _forced(job, status, beat_id, problem, option.label,
                    "the same problem came back a third time", self.clock)  # fmt: skip
        else:
            return None
        patched = option.apply(picture) if option.apply is not None else picture
        if not self._patch(job, validated, patched, status):
            return None
        if option.replaces is not None:
            _mark_replaced(job, option.replaces)
        self.why = f"the editor fixed {beat_id} ({option.id})"
        return "sourcing"

    def _net_exhausted(
        self, job: Job, exc: NetExhausted, problem: str, validated: ValidatedPlan
    ) -> Status | None:
        """111d: the render net (`render.render_picture`) gave up. Naming no beat (no
        frame, no failing still): the 097 strip of every overlay, once. Else this is the
        net's one exit, where 111g hooks the plain reel; today the job fails."""
        if exc.unnamed and not self.stripped:
            return self._strip(job, problem, validated)
        jobs.note(job, "rescue: the render net is exhausted"
                  + (f" ({', '.join(exc.beats)})" if exc.beats else "")
                  + "; the job fails")  # fmt: skip
        return None

    def _strip(self, job: Job, problem: str, validated: ValidatedPlan) -> Status | None:
        self.stripped = True
        _forced(job, "rendering", None, problem, STRIP_LABEL,
                "the render failed naming no beat; plain fallback, once", self.clock)  # fmt: skip
        if not self._patch(job, validated, repairs.strip_overlays(validated.picture),
                           "rendering"):  # fmt: skip
            return None
        self.why = "every overlay layer stripped after a render failure naming no beat"
        return "rendering"

    def _qa(self, job: Job, exc: QaFailed, validated: ValidatedPlan) -> Status | None:
        if exc.check in jobs.load(job.path).record.waived_checks:
            jobs.note(job, f"rescue: {exc.check} still fails although it is waived; the "
                      "job fails")  # fmt: skip
            return None
        picture = validated.picture
        ids = [b.id for b in picture.beats]
        named = list(dict.fromkeys(b for b in _BEAT_WORD.findall(exc.detail) if b in ids))
        deliver = Option(DELIVER, f"deliver with a note (check {exc.check} shown as warn)",
                         resume_step="qa")  # fmt: skip
        problem = f"{exc.check}: {exc.detail}"
        snags: list[Snag] = []
        if named and exc.check not in self.patched_checks:
            coder = self.editor.geocoder_for(job)
            for beat_id in named:
                options = [*beat_options(picture, beat_id, hard=True, geocoder=coder,
                                         keep=False), deliver]  # fmt: skip
                snags.append(Snag(id=f"s{len(snags) + 1}", step="qa", beat_id=beat_id,
                                  problem=problem, hard=False, options=tuple(options),
                                  fallback_id=DELIVER))  # fmt: skip
        else:
            snags.append(Snag(id="s1", step="qa", beat_id=None, problem=problem, hard=False,
                              options=(deliver,), fallback_id=DELIVER))  # fmt: skip
        choices = self.editor.pick(job, snags, step="qa", plan=picture,
                                   transcript=_transcript(job))  # fmt: skip
        patched = picture
        replaced: list[str] = []
        for choice in choices:
            if choice.option.apply is not None:
                patched = choice.option.apply(patched)
                if choice.option.replaces is not None:
                    replaced.append(choice.option.replaces)
        if patched != picture:
            self.patched_checks.add(exc.check)
            if not self._patch(job, validated, patched, "qa"):
                return None
            for beat_id in replaced:
                _mark_replaced(job, beat_id)
            self.why = f"the editor fixed {', '.join(c.snag.beat_id or 'plan' for c in choices)} "
            self.why += f"after {exc.check} failed"
            return "sourcing"
        waived = jobs.load(job.path).record.waived_checks
        jobs.amend(job, waived_checks=[*waived, exc.check])
        self.why = f"{exc.check} delivered with a note (warn)"
        return "qa"

    # the patch

    def _patch(
        self, job: Job, validated: ValidatedPlan, picture: PicturePlan, step: str
    ) -> bool:
        """Write the patched picture (`patch_picture`, hard survivors forced). False when
        a hard truth still stands (the job then fails)."""
        result = patch_picture(job, validated, picture, self.specs, step=step, clock=self.clock)
        if isinstance(result, grammar.Violations):
            jobs.note(job, "rescue: the patched plan still breaks a hard rule: "
                      + "; ".join(result.lines()))  # fmt: skip
            return False
        return True


def patch_picture(
    job: Job,
    validated: ValidatedPlan,
    picture: PicturePlan,
    specs: Specs,
    *,
    step: str,
    clock: Clock,
    force: bool = True,
) -> grammar.PictureCheck | grammar.Violations:
    """097 / 098: write a patched picture: re-validated on the output timeline with the
    soft rules kept, into `work/plan.json` and the picture of `work/plan.validated.json`
    (the sound, clamps, topic and examples kept; the new warnings added), and
    `work/captions.json` rebuilt. With `force` (the rescues) the hard survivors take
    their forced fallbacks first; without it (the change box) a hard violation is
    returned and nothing is written."""
    spec = style_of(job, specs)
    transcript = _transcript(job)
    brief = (job.input_dir / "brief.md").read_text(encoding="utf-8")
    refs_path = job.input_dir / "refs.json"
    refs = (
        _REFS.validate_json(refs_path.read_text(encoding="utf-8"))
        if refs_path.is_file()
        else []
    )
    references = [
        PlanReference(id=r.id, kind="image" if r.kind == "image" else "clip_frame",
                      caption=r.caption, width=r.width, height=r.height)
        for r in refs
    ]  # fmt: skip
    must_use = grammar.must_use_ids(brief, references)

    def check(
        plan: PicturePlan, *, keep_soft: bool = True
    ) -> grammar.PictureCheck | grammar.Violations:
        return grammar.validate_picture(
            plan, transcript, spec, brief=brief, must_use=must_use,
            references=[r.id for r in references], timeline="output", keep_soft=keep_soft,
        )  # fmt: skip

    result = (
        _force_hard(job, picture, check, transcript, references, step, clock)
        if force
        else check(picture, keep_soft=True)
    )
    if isinstance(result, grammar.Violations):
        return result
    warnings = list(validated.warnings)
    warnings += [w for w in result.warnings if w not in warnings]
    updated = validated.model_copy(update={"picture": result.picture, "warnings": warnings})
    _write(job, "plan.json", result.picture)
    _write(job, "plan.validated.json", updated)
    _write(job, "captions.json", captions.build(transcript, result.picture, spec))
    return result


def _gradient(plan: PicturePlan, beat_id: str) -> PicturePlan:
    """097: the third time a beat fails the same way it is replaced with no query, so
    the replacement ladder has nothing to search for and shows the gradient."""
    replaced = repairs.replace_visual(plan, beat_id)
    beats = [
        b.model_copy(update={"query": "", "query_fallback": "", "text_pops": [], "bubbles": [],
                             "stickers": []})
        if b.id == beat_id else b
        for b in replaced.beats
    ]  # fmt: skip
    return replaced.model_copy(update={"beats": beats})


def load_validated(job: Job) -> ValidatedPlan | None:
    path = job.work_dir / "plan.validated.json"
    if not path.is_file():
        return None
    return ValidatedPlan.model_validate_json(path.read_text(encoding="utf-8"))


def _transcript(job: Job) -> Transcript:
    return Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))


class Worker:
    """One thread, one job at a time, submission order, `max_queue` deep."""

    def __init__(
        self,
        *,
        transcriber: Transcriber,
        planner: Planner,
        renderer: Renderer | None = None,
        gate: Gate | None = None,
        sourcing: assets.Sourcing | None = None,
        specs: Specs | None = None,
        library: sound.Library | None = None,
        detector: presenter.FaceDetector | None = None,
        critic: Critic | None = None,
        inventory: own.SelfInventory | None = None,
        max_queue: int = DEFAULT_MAX_QUEUE,
        budgets: Budgets | None = None,
        clock: Clock = _utc_now,
        watchdog_interval_s: float = 1.0,
        editor: Editor | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._planner = planner
        self._renderer = renderer or RemotionRenderer()
        self._specs = specs if specs is not None else render.loaded_styles()
        self._gate = gate or TechnicalGate(specs=self._specs)
        self._sourcing = sourcing or assets.Sourcing()
        self._library = library if library is not None else sound.load_catalogue()
        self._detector = detector or presenter.HaarDetector()
        self._critic = critic or FakeCritic()  # 033: the app passes the configured one
        # 074: the app passes the configured step; the default sends nothing.
        self._inventory = inventory or own.keyless()
        # 097: the editor on the job's planner and the renderer's geocoder.
        self._editor = editor or default_editor(planner, self._renderer, clock=clock)
        self._max_queue = max_queue
        self._budgets = budgets if budgets is not None else default_budgets()  # 111e
        self._clock = clock
        self._watchdog_interval_s = watchdog_interval_s
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._waiting: list[Path] = []
        self._running: Path | None = None
        self._reserved = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # -- admission (11.2) --

    def _depth_locked(self) -> int:
        return len(self._waiting) + (1 if self._running is not None else 0) + self._reserved

    def depth(self) -> int:
        """Running + waiting + reserved slots."""
        with self._lock:
            return self._depth_locked()

    def reserve(self) -> None:
        """Hold a slot before the upload is read; `release` it or `submit(reserved=True)`."""
        with self._lock:
            if self._depth_locked() >= self._max_queue:
                raise QueueFull(self._max_queue)
            self._reserved += 1

    def release(self) -> None:
        with self._lock:
            self._reserved = max(0, self._reserved - 1)

    def submit(self, job_dir: Path, *, reserved: bool = False) -> None:
        with self._lock:
            if reserved:
                self._reserved = max(0, self._reserved - 1)
            elif self._depth_locked() >= self._max_queue:
                raise QueueFull(self._max_queue)
            self._waiting.append(job_dir)
        self._queue.put(job_dir)

    def pending(self) -> list[Path]:
        """The running job (if any) followed by the waiting ones, in submission order."""
        with self._lock:
            running = [self._running] if self._running is not None else []
            return running + list(self._waiting)

    def position(self, job_dir: Path) -> int | None:
        """1-based place among the waiting jobs; None when running or not queued."""
        with self._lock:
            if job_dir in self._waiting:
                return self._waiting.index(job_dir) + 1
            return None

    # -- running --

    def run_next(self, *, timeout_s: float = 0.0) -> bool:
        """Run the next queued job synchronously; False when the queue is empty."""
        try:
            item = self._queue.get(timeout=timeout_s) if timeout_s else self._queue.get_nowait()
        except queue.Empty:
            return False
        if item is None:
            return False
        self._run(item)
        return True

    def _run(self, job_dir: Path) -> None:
        with self._lock:
            if job_dir in self._waiting:
                self._waiting.remove(job_dir)
            self._running = job_dir
        try:
            self._run_unguarded(job_dir)
        finally:
            with self._lock:
                self._running = None

    def _run_unguarded(self, job_dir: Path) -> None:
        if not (job_dir / "job.json").is_file():
            log.warning("job %s vanished before it ran", job_dir.name)
            return
        job = jobs.load(job_dir)
        try:
            run_job(
                job,
                transcriber=self._transcriber,
                planner=self._planner,
                renderer=self._renderer,
                gate=self._gate,
                sourcing=self._sourcing,
                specs=self._specs,
                library=self._library,
                detector=self._detector,
                critic=self._critic,
                inventory=self._inventory,
                budgets=self._budgets,
                clock=self._clock,
                watchdog_interval_s=self._watchdog_interval_s,
                editor=self._editor,
            )
        except NotRunnable as exc:
            log.warning("%s", exc)
        except Exception:  # noqa: BLE001 - the worker thread must never die
            log.exception("job %s crashed outside a step", job.id)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="shortsmith-worker", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            self._run(item)

    def stop(self, *, timeout_s: float = 30.0) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=timeout_s)
        self._thread = None
