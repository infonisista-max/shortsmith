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
fixed transcript is `work/asr.json`. Any exception inside a step marks the job
`failed` at that step with the fixed user-facing sentence from `ERROR_TEXT` and the
exception text as `detail` (11.1); a failed technical check adds its name to the
sentence (10.1); a paid adapter's `ledger.BudgetExceeded`, raised before its call,
becomes "Budget exceeded at step X." with the ledger rows so far left on job.json
for the page (11.3).

A failed job can be run again from the step it failed at (043): `jobs.requeue` sends
it back to `uploaded` carrying `retry_from`, and `start_step` slices the step list
there, so everything the failed run left on disk - the transcript, the plan, the
per-job asset cache (5.6), the picture - is the retry's input and is never paid for
twice. A retry from `rendering` therefore calls no planner and no image source, one
from `sourcing` searches only the beats the cache does not have, and one from
`planning` re-transcribes nothing. What the failed run did pay for stays on
`job.json`; the retry's own calls are new rows beside it.

The `planning` step builds the PlanRequest from `job.json`, `brief.md`, `refs.json`
and `work/asr.json` (2.3), calls the planner twice (picture, then sound; 8.1) with
the grammar (`grammar`, ticket 009) after each call: a rejected call is re-sent
exactly once with the previous output and the violation list (`PlanFeedback`), a
second rejection fails the job at `planning` with the list in `job.json.error` and
on the page, and the retry is logged in `job.log` (8.2); a reply the models refuse
(`PlanInvalid`) takes the same path. The planner is bound to the job first so a real
adapter writes its prompt under `work/planner/` and records a ledger row per call and
retry (8.3), and the picture plan's `prompt_version` is recorded in `job.json`. The
sound call receives the snapped picture plan and the catalogue tags. The step builds
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
not loaded fails at `planning`.

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
a failing check fails the job at `qa` naming the check. The gate is built with the
same specs the grammar judged the plan by, since T8 re-validates the plan. When every
check passes the gate composes `out/contact.jpg`, and the job is `delivered` once
`short.mp4`, `contact.jpg`, `rights.json` and `credits.md` exist (10.4).

`Worker` wraps `run_job` in a FIFO queue on one daemon thread for the web app;
`run_next` drains one job synchronously so tests and smoke use the same code path
without threads.

Limits (11.2): the queue depth counts the running job, the waiting jobs and the
slots the upload route has reserved; `submit`/`reserve` raise `QueueFull` at
`max_queue`. A waiting job's position is its 1-based place among the waiting jobs.
`max_job_minutes` arms a `subproc.Watchdog` per job that kills the running step's
subprocesses at the deadline; whichever way the step then ends, the job is `failed`
at that step with "job exceeded N minutes" and the worker moves on.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from shortsmith import assets, captions, grammar, jobs, presenter, render, sound, subproc
from shortsmith.contracts import (
    Constraints,
    PlanFeedback,
    PlanReference,
    PlanRequest,
    PlanStyle,
    ReferenceRecord,
    Transcript,
    ValidatedPlan,
)
from shortsmith.jobs import Clock, Job, Status
from shortsmith.ledger import BudgetExceeded
from shortsmith.planner import PlanInvalid, Planner
from shortsmith.qa.gate import Gate, TechnicalGate
from shortsmith.render import RemotionRenderer, Renderer
from shortsmith.styles import StyleError, StyleSpec
from shortsmith.transcriber import Transcriber

log = logging.getLogger(__name__)

DEFAULT_MAX_QUEUE = 3
DEFAULT_MAX_JOB_MINUTES = 30


def _utc_now() -> datetime:
    return datetime.now(UTC)


def timeout_message(max_job_minutes: float) -> str:
    minutes = int(max_job_minutes) if float(max_job_minutes).is_integer() else max_job_minutes
    return f"The job exceeded {minutes} minutes and was stopped."

ERROR_TEXT: dict[str, str] = {
    "transcribing": "We could not transcribe the recording.",
    "planning": "We could not plan the short.",
    "sourcing": "We could not find or make the pictures for the short.",
    "rendering": "We could not render the short.",
    "qa": "The short failed a technical check.",
}
DELIVERABLES = ("short.mp4", "contact.jpg", "rights.json", "credits.md")  # 10.4

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
    max_job_minutes: float | None = None,
    clock: Clock = _utc_now,
    watchdog_interval_s: float = 1.0,
) -> Job:
    if job.status != "uploaded":
        raise NotRunnable(f"job {job.id} is {job.status!r}, not 'uploaded'")
    renderer = renderer or RemotionRenderer()
    specs = specs if specs is not None else render.loaded_styles()
    gate = gate or TechnicalGate(specs=specs)
    sourcing = sourcing or assets.Sourcing()
    library = library if library is not None else sound.load_catalogue()
    detector = detector or presenter.HaarDetector()
    steps: list[tuple[Status, Step]] = [
        ("transcribing", lambda j: _transcribe(j, transcriber, detector, specs)),
        ("planning", lambda j: _plan(j, planner, specs, library)),
        ("sourcing", lambda j: _source(j, sourcing, specs, clock)),
        ("rendering", lambda j: _render(j, renderer, clock, library)),
        ("qa", lambda j: _qa(j, gate)),
    ]
    steps = steps[jobs.STEPS.index(start_step(job)) :]
    watchdog: subproc.Watchdog | None = None
    if max_job_minutes is not None:
        deadline = clock() + timedelta(minutes=max_job_minutes)
        watchdog = subproc.Watchdog(deadline=deadline, clock=clock, interval_s=watchdog_interval_s)
        watchdog.start()
    try:
        for status, step in steps:
            job = jobs.transition(job, status)
            detail = ""
            try:
                with subproc.guarded(watchdog):
                    step(job)
            except Exception as exc:  # noqa: BLE001 - every step failure lands in job.json the same way
                detail = f"{exc}\n{traceback.format_exc()}"
                if watchdog is None or not watchdog.check():
                    violations = exc.violations if isinstance(exc, PlanRejected) else []
                    return jobs.fail(
                        job,
                        step=status,
                        message=failure_message(status, exc),
                        detail=detail,
                        violations=violations,
                    )
            if watchdog is not None and watchdog.check():
                assert max_job_minutes is not None
                return jobs.fail(
                    job, step=status, message=timeout_message(max_job_minutes), detail=detail
                )
    finally:
        if watchdog is not None:
            watchdog.stop()
    return jobs.transition(job, "delivered")


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
    message = ERROR_TEXT[status]
    if isinstance(exc, QaFailed):
        return f"{message[:-1]} ({exc.check})."
    return message


def _transcribe(
    job: Job, transcriber: Transcriber, detector: presenter.FaceDetector, specs: Specs
) -> None:
    assert job.record.input is not None or (job.input_dir / "raw.mp4").is_file()
    raw = job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")
    # 013: measure first, so a recording with no face costs no transcription. A style
    # that is not loaded is left for `planning` to name (`style_of`), as before.
    spec = specs.get(job.record.style)
    if spec is not None:
        presenter.measure(job, spec, detector=detector)
    transcript = transcriber.bind(job).transcribe(raw)
    (job.work_dir / "asr.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")


def style_of(job: Job, specs: Specs) -> StyleSpec:
    """The loaded spec `job.json.style` names; a name outside the loaded set is a
    config problem to see at `planning`, never a silent fallback."""
    spec = specs.get(job.record.style)
    if spec is None:
        raise StyleError(
            f"job {job.id}: style {job.record.style!r} is not a loaded spec "
            f"(loaded: {sorted(specs)})"
        )
    return spec


def build_plan_request(job: Job, specs: Specs) -> PlanRequest:
    """PlanRequest per 2.3 from the job's files; nothing else reaches the planner."""
    transcript = Transcript.model_validate_json(
        (job.work_dir / "asr.json").read_text(encoding="utf-8")
    )
    brief = (job.input_dir / "brief.md").read_text(encoding="utf-8")
    refs_path = job.input_dir / "refs.json"
    refs = _REFS.validate_json(refs_path.read_text(encoding="utf-8")) if refs_path.is_file() else []
    spec = style_of(job, specs)
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
    )


class PlanRejected(Exception):
    """The grammar rejected the planner's `call` ("picture" or "sound") twice (8.2)."""

    def __init__(self, call: str, violations: Sequence[str]) -> None:
        self.call = call
        self.violations = list(violations)
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
    and a second rejection raises `PlanRejected` with the list."""
    feedback: PlanFeedback | None = None
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
        if attempt == 2:
            raise PlanRejected(label.split()[0], lines)
        jobs.note(job, f"{label} rejected, re-sending once: {'; '.join(lines)}")
        feedback = PlanFeedback(previous=previous, violations=lines)
    raise AssertionError("unreachable")


def _plan(job: Job, planner: Planner, specs: Specs, library: sound.Library) -> None:
    request = build_plan_request(job, specs)
    spec = style_of(job, specs)
    transcript = request.transcript
    must_use = grammar.must_use_ids(request.brief, request.references)
    planner = planner.bind(job)

    checked = _with_one_retry(
        job,
        "picture plan",
        lambda feedback: planner.plan_picture(request, feedback=feedback),
        "plan.raw.json",
        lambda raw: grammar.validate_picture(
            raw, transcript, spec, brief=request.brief, must_use=must_use
        ),
    )
    picture = checked.picture
    jobs.amend(job, prompt_version=picture.prompt_version)

    sound = _with_one_retry(
        job,
        "sound story",
        lambda feedback: planner.plan_sound(
            request, picture, library.tags(), feedback=feedback
        ),
        "sound.raw.json",
        lambda raw: grammar.validate_sound(raw, picture, spec),
    )

    validated = ValidatedPlan(
        picture=picture,
        sound=sound.sound,
        clamps=checked.clamps + sound.clamps,
        warnings=checked.warnings,
    )
    paged = captions.build(transcript, picture, spec)
    _write(job, "plan.json", picture)
    _write(job, "sound.json", sound.sound)
    _write(job, "plan.validated.json", validated)
    _write(job, "captions.json", paged)


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


def _qa(job: Job, gate: Gate) -> None:
    report = gate.check(job)
    failed = report.failed
    if failed is not None or not report.passed:
        name = failed.name if failed is not None else "qa"
        raise QaFailed(name, failed.detail if failed is not None else "no checks ran")
    gate.contact_sheet(job)
    missing = [name for name in DELIVERABLES if not (job.out_dir / name).is_file()]
    if missing:
        raise QaFailed("deliverables", f"missing out/{', out/'.join(missing)}")


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
        max_queue: int = DEFAULT_MAX_QUEUE,
        max_job_minutes: float | None = DEFAULT_MAX_JOB_MINUTES,
        clock: Clock = _utc_now,
        watchdog_interval_s: float = 1.0,
    ) -> None:
        self._transcriber = transcriber
        self._planner = planner
        self._renderer = renderer or RemotionRenderer()
        self._specs = specs if specs is not None else render.loaded_styles()
        self._gate = gate or TechnicalGate(specs=self._specs)
        self._sourcing = sourcing or assets.Sourcing()
        self._library = library if library is not None else sound.load_catalogue()
        self._detector = detector or presenter.HaarDetector()
        self._max_queue = max_queue
        self._max_job_minutes = max_job_minutes
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
                max_job_minutes=self._max_job_minutes,
                clock=self._clock,
                watchdog_interval_s=self._watchdog_interval_s,
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
