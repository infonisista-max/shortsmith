"""FastAPI app (PRD `app`): upload form, `POST /jobs`, job page, job JSON, retry.

Pages are stdlib `string.Template` files under `templates/`; every user-supplied or
model-generated string passes through `html.escape` before it is substituted. The
worker (`pipeline.Worker`) starts in the lifespan and runs jobs one at a time in
submission order. The sweeper (`sweeper.sweep`, 042) runs in the lifespan as a
background task every 15 minutes and again the moment the disk guard trips.

Passcode (decision 11.2): `PasscodeGuard` is a pure ASGI middleware in front of every
route except `/health` and `POST /passcode`. Without a valid cookie (see `auth`) an
HTML request gets the passcode form (200 on `/`, 401 elsewhere, carrying the path as
`next` so a shared job link survives the login) and a JSON request gets 401 JSON.
The app refuses to start without a passcode: an open link would be a public problem.

Limits (11.2, ticket 041): `POST /jobs` first checks the day limit (jobs created
since midnight IST), then reserves a queue slot (`MAX_QUEUE` counts the running job,
the waiting ones and reservations) so a refused upload costs nothing, then reads the
multipart body through `limited_receive`, which stops the read on the chunk that
crosses the size limit instead of spooling the whole file. Refusals: 503 with
Retry-After for the queue and the day limit, 413 for the size. A waiting job's page
shows "queued, position N" and the JSON carries `queue_position` so the poll reloads
as jobs finish. The daily cash budget (11.3, ticket 044) closes the form the same way
as the day limit, until midnight IST, once `BUDGET_INR_PER_DAY` of cash rows is spent
today. `MAX_JOB_MINUTES` reaches the worker. The disk guard (11.2, ticket 042) sits above
all of them: under 5 GB free beneath the data directory the form is replaced by one
plain sentence, `POST /jobs` answers 503 with Retry-After, and the sweeper runs at
once so the next visit may find room.

Styles (ticket 008, decisions 1.1, 1.4, 2.1): `create_app` loads every spec under
`styles/` against the renderer registry and refuses to build the app on a broken
one (a `StyleError` naming the spec and the problem is the config error). The upload
form offers one chip per shipped style and resolves the style field live through
`GET /styles/resolve?line=`, showing the resolved name, note and draft notice before
submit; `POST /jobs` resolves the same line server-side and stores `style`,
`style_note` and `style_notice` on `job.json`.

Retry (11.1, ticket 043): a failed job's page carries one button, `POST
/jobs/<id>/retry`, which reserves a queue slot, `jobs.requeue`s the job and submits
it; the worker then re-enters the pipeline at the step it failed at, reusing
everything already fetched or generated. The refusals are a page with one sentence:
409 for a job that did not fail or whose files the sweeper has taken (the button is
hidden for the same reason), 503 with Retry-After when the queue is full, and the job
stays failed with its button in both cases.

`create_app` is the factory tests use with their own settings and fake adapters;
the module-level `app` is what `uvicorn shortsmith.app:app` serves.
"""

from __future__ import annotations

import asyncio
import dataclasses
import html
import json
import logging
import math
import re
import shutil
import tempfile
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from string import Template

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import TypeAdapter
from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shortsmith import (
    assets,
    auth,
    config,
    ingest,
    jobs,
    ledger,
    pipeline,
    render,
    styles,
    sweeper,
)
from shortsmith import planner as planner_module
from shortsmith import transcriber as transcriber_module
from shortsmith.auth import COOKIE_NAME, FailureLog
from shortsmith.config import Settings
from shortsmith.contracts import ReferenceRecord
from shortsmith.ingest import Limits, ReferenceUpload, Rejected, VideoUpload
from shortsmith.jobs import SETTLED, STATUS_ORDER, Clock, Job, Status
from shortsmith.pipeline import QueueFull
from shortsmith.planner import Planner
from shortsmith.qa import technical
from shortsmith.qa.gate import Gate
from shortsmith.render import Renderer
from shortsmith.styles import StyleSpec
from shortsmith.transcriber import Transcriber

log = logging.getLogger(__name__)

TEMPLATES = Path(__file__).parent / "templates"
MAX_REFERENCE_FIELDS = 8
POLL_MS = 3000
PASSCODE_PATH = "/passcode"
# The deliverables a job page may serve from `out/` (10.4), by media type; nothing else
# under the job directory is reachable over HTTP.
OUT_FILES: dict[str, str] = {
    "short.mp4": "video/mp4",
    "contact.jpg": "image/jpeg",
    "qa.json": "application/json",
    "rights.json": "application/json",  # 5.4 rights evidence (016)
    "credits.md": "text/markdown; charset=utf-8",
}
SHOWS_SHORT: frozenset[Status] = frozenset({"delivered", "passed", "rejected"})
QUEUE_RETRY_S = 3600  # "try in an hour"
# 11.2: what the form says when the data disk is under `sweeper.MIN_FREE_BYTES`.
DISK_FULL_SENTENCE = (
    "There is not enough disk space for a new short right now. Try again later."
)
# 2.2: what the job page says once the sweeper has taken the upload and the work files.
SWEPT_SENTENCE = (
    "The recording and the working files were deleted 24 hours after upload. "
    "The short and its credits stay for 7 days."
)
# 043: why a retry is refused. A job that did not fail has nothing to re-run, and a
# swept job has no files left to re-run a step from.
NOT_FAILED_SENTENCE = "This job did not fail, so there is nothing to retry."
SWEPT_RETRY_SENTENCE = (
    "The recording and the working files for this job were deleted, so it cannot be run again."
)
BODY_SLACK = ingest.MIB  # multipart framing and text fields on top of the file limits
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_REFS = TypeAdapter(list[ReferenceRecord])

Delay = Callable[[float], Awaitable[None]]


class BodyTooLarge(Exception):
    """The request body crossed the upload limit; the read stopped there."""


def limited_receive(receive: Receive, *, limit: int) -> Receive:
    """Wrap an ASGI `receive` so the body read raises `BodyTooLarge` on the chunk that
    takes the running total past `limit`; nothing after that chunk is ever pulled."""
    seen = 0

    async def limited() -> Message:
        nonlocal seen
        message = await receive()
        if message["type"] == "http.request":
            seen += len(message.get("body", b""))
            if seen > limit:
                raise BodyTooLarge(seen)
        return message

    return limited


def body_limit(limits: Limits) -> int:
    """The most a well-formed submission can carry: the video, up to nine references
    (so the ninth still gets the count sentence, not this one) and framing slack."""
    return (
        limits.max_upload_bytes
        + (MAX_REFERENCE_FIELDS + 1) * limits.max_reference_bytes
        + BODY_SLACK
    )


def _template(name: str) -> Template:
    return Template((TEMPLATES / name).read_text(encoding="utf-8"))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    settings: Settings | None = None,
    *,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
    renderer: Renderer | None = None,
    gate: Gate | None = None,
    sourcing: assets.Sourcing | None = None,
    limits: Limits | None = None,
    start_worker: bool = True,
    start_sweeper: bool = True,
    sweep_interval_s: float = sweeper.INTERVAL_S,
    free_disk: sweeper.FreeBytes = sweeper.free_bytes,
    clock: Clock = _utc_now,
    delay: Delay = asyncio.sleep,
    styles_dir: Path | None = None,
    book: ledger.Ledger | None = None,
    specs: Mapping[str, StyleSpec] | None = None,
) -> FastAPI:
    settings = settings or config.load()
    # Every style spec loads here, at startup, or the app does not build (1.2, 1.4).
    # Tests pass `specs` when the fake plan must be judged by the fixture rule set.
    if specs is None:
        specs = styles.load_all(render.registry(), styles_dir or styles.STYLES_DIR)
    chips = styles.shipped(specs)
    # The ledger loads the prices file at startup (5.6), in the lifespan like the
    # passcode check, so `import shortsmith.app` never needs the file: a provider the
    # config puts in use without a price is a `LedgerError` that stops the server with
    # its message. Paid adapters (012, 014, 015, 017, 019) take the ledger at
    # construction and report units to it.
    books: list[ledger.Ledger | None] = [book]

    # `TRANSCRIBER` (012) and `PLANNER` (8.3) select the adapters; a paid one without
    # its key stops the server in `check_startup`, never plans with the fake. The paid
    # adapters read the ledger when they record, so the lifespan's ledger is used.
    def _book() -> ledger.Ledger:
        if books[0] is None:
            raise RuntimeError("the ledger is loaded when the server starts")
        return books[0]

    transcriber = transcriber or transcriber_module.from_settings(settings, ledger=_book)
    planner = planner or planner_module.from_settings(settings, ledger=_book)
    limits = limits or Limits(max_upload_bytes=settings.shortsmith_max_upload_mb * ingest.MIB)
    # `renderer` None means Remotion (ticket 004) and `gate` None the technical gate
    # (006); tests pass `FakeRenderer` and `FakeGate`. The asset step follows
    # `ASSET_SOURCES` / `ASSET_POLICY` (016) with the `web` adapter (017), the free
    # libraries (018) and the relevance judge `RELEVANCE_JUDGE` names (017).
    worker = pipeline.Worker(
        transcriber=transcriber,
        planner=planner,
        renderer=renderer,
        gate=gate,
        sourcing=sourcing or assets.from_settings(settings, ledger=_book),
        specs=specs,
        max_queue=settings.max_queue,
        max_job_minutes=settings.max_job_minutes,
        clock=clock,
    )
    max_jobs_per_day = settings.max_jobs_per_day
    data_dir = settings.shortsmith_data_dir
    secret = settings.shortsmith_passcode
    passcode = secret.get_secret_value() if secret is not None else ""
    failures = FailureLog(clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        if not passcode:
            raise RuntimeError(
                "SHORTSMITH_PASSCODE is not set: add one to .env before serving (decision 11.2)"
            )
        config.check_startup(settings)  # ConfigError says the fix (11.3)
        if books[0] is None:
            books[0] = ledger.from_settings(settings, clock=clock)  # LedgerError names the gap
        app.state.ledger = books[0]
        (data_dir / "jobs").mkdir(parents=True, exist_ok=True)
        if start_worker:
            worker.start()
        sweeping = asyncio.create_task(sweep_loop()) if start_sweeper else None
        try:
            yield
        finally:
            if sweeping is not None:
                sweeping.cancel()
                with suppress(asyncio.CancelledError):
                    await sweeping
            worker.stop()

    def sweep_now() -> list[sweeper.Action]:
        return sweeper.sweep(data_dir, now=clock)

    async def sweep_loop() -> None:
        """11.2: retention runs in-process every 15 minutes. One pass failing (a file
        held open on Windows, say) is a log line, never the end of the task."""
        while True:
            await asyncio.sleep(sweep_interval_s)
            try:
                for action in await run_in_threadpool(sweep_now):
                    log.info("swept %s", action.line())
            except Exception:  # noqa: BLE001 - the background task must never die
                log.exception("the sweeper pass failed")

    app = FastAPI(title="Shortsmith", lifespan=lifespan)
    app.state.data_dir = data_dir
    app.state.worker = worker
    app.state.limits = limits
    app.state.failures = failures
    app.state.specs = specs
    app.add_middleware(PasscodeGuard, passcode=passcode, clock=clock)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post(PASSCODE_PATH)
    async def enter_passcode(request: Request) -> Response:
        form = await request.form()
        given = _text(form.get("passcode"))
        next_url = _local_path(_text(form.get("next")))
        ip = request.client.host if request.client else "unknown"
        remaining = failures.blocked_for(ip)
        if remaining is not None:
            page = render_passcode_form(_blocked(remaining), next_url)
            return HTMLResponse(page, status_code=429)
        if passcode and auth.passcode_matches(given, passcode):
            response = RedirectResponse(next_url, status_code=303)
            response.set_cookie(
                COOKIE_NAME,
                auth.issue_cookie(passcode, now=clock()),
                max_age=auth.COOKIE_MAX_AGE_S,
                path="/",
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
            return response
        failures.record_failure(ip)
        await delay(auth.WRONG_PASSCODE_DELAY_S)
        return HTMLResponse(render_passcode_form("Wrong passcode.", next_url), status_code=401)

    def closed_until_midnight() -> str:
        """Why the form is closed until midnight IST, or "": the day's job limit (11.2)
        or the day's cash budget (11.3, 044). Tokens never count toward the budget."""
        now = clock()
        if jobs.created_since(data_dir, jobs.midnight_ist(now)) >= max_jobs_per_day:
            return (
                f"Today's limit of {max_jobs_per_day} shorts is reached. "
                "Try again after midnight IST."
            )
        if _book().daily_budget_reached(data_dir, now):
            return "Daily budget reached. Try again after midnight IST."
        return ""

    def disk_guard_tripped() -> bool:
        """11.2: under the line the form refuses, and the sweeper runs at once, so the
        space a finished job no longer needs is back before the next visit."""
        if not sweeper.low_disk(free_disk, data_dir):
            return False
        for action in sweep_now():
            log.info("disk guard swept %s", action.line())
        return True

    @app.get("/", response_class=HTMLResponse)
    async def upload_form() -> HTMLResponse:
        if await run_in_threadpool(disk_guard_tripped):
            return HTMLResponse(render_upload_form(limits, closed=DISK_FULL_SENTENCE))
        closed = await run_in_threadpool(closed_until_midnight)
        if closed:
            return HTMLResponse(render_upload_form(limits, closed=closed))
        return HTMLResponse(render_upload_form(limits, chips=chips))

    @app.get("/styles/resolve")
    async def resolve_style(line: str = "") -> Response:
        """The live resolution the form shows before submit (1.1): the same code
        path `POST /jobs` stores, so the page never promises a different style."""
        return JSONResponse(dataclasses.asdict(styles.resolve(line, specs)))

    @app.post("/jobs")
    async def submit(request: Request) -> Response:
        if await run_in_threadpool(disk_guard_tripped):
            return HTMLResponse(
                render_upload_form(limits, closed=DISK_FULL_SENTENCE),
                status_code=503,
                headers={"Retry-After": str(sweeper.INTERVAL_S)},
            )
        closed = await run_in_threadpool(closed_until_midnight)
        if closed:
            return HTMLResponse(
                render_upload_form(limits, closed=closed),
                status_code=503,
                headers={"Retry-After": str(_seconds_to_next_midnight_ist(clock()))},
            )
        try:
            worker.reserve()
        except QueueFull:
            return HTMLResponse(
                render_upload_form(
                    limits,
                    chips=chips,
                    rejection=f"{worker.depth()} shorts are already in the queue; try in an hour.",
                ),
                status_code=503,
                headers={"Retry-After": str(QUEUE_RETRY_S)},
            )
        submitted = False
        try:
            response = await _submit_reserved(request)
            submitted = response.status_code == 303
            return response
        finally:
            if not submitted:
                worker.release()

    async def _submit_reserved(request: Request) -> Response:
        too_large = _too_large(limits, chips)
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > body_limit(limits):
            return too_large
        try:
            form = await Request(
                request.scope, limited_receive(request.receive, limit=body_limit(limits))
            ).form()
        except BodyTooLarge:
            return too_large
        brief = _text(form.get("brief"))
        style_line = _text(form.get("style"))
        captions = [_text(form.get(f"caption_{n}")) for n in range(1, MAX_REFERENCE_FIELDS + 1)]
        video = form.get("video")
        with tempfile.TemporaryDirectory(prefix="shortsmith-upload-") as tmp:
            tmp_dir = Path(tmp)
            video_upload = _spool(video, tmp_dir / "video")
            references: list[ReferenceUpload] = []
            for n in range(1, MAX_REFERENCE_FIELDS + 1):
                spooled = _spool(form.get(f"ref_{n}"), tmp_dir / f"ref_{n}")
                if spooled is not None:
                    references.append(
                        ReferenceUpload(
                            path=spooled.path,
                            original_name=spooled.original_name,
                            caption=captions[n - 1],
                        )
                    )
            # Extra file fields beyond the eight named ones count too (2.1 cap by count).
            for key, value in form.multi_items():
                if key.startswith("ref_") and key[4:].isdigit() and int(key[4:]) > 8:
                    spooled = _spool(value, tmp_dir / key)
                    if spooled is not None:
                        references.append(
                            ReferenceUpload(path=spooled.path, original_name=spooled.original_name)
                        )
            if video_upload is None:
                return _rejection(
                    limits, chips, "Please choose a video file to upload.", brief, style_line,
                    captions,
                )  # fmt: skip
            try:
                job = await run_in_threadpool(
                    ingest.accept,
                    data_dir,
                    video=video_upload,
                    brief=brief,
                    style=styles.resolve(style_line, specs),
                    references=references,
                    limits=limits,
                    now=clock,
                )
            except Rejected as exc:
                return _rejection(limits, chips, str(exc), brief, style_line, captions)
        worker.submit(job.path, reserved=True)
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/jobs/{job_id}.json")
    async def job_json(job_id: str) -> Response:
        job = jobs.find(data_dir, job_id)
        if job is None:
            return JSONResponse({"error": "no such job"}, status_code=404)
        payload = json.loads(job.record.model_dump_json())
        payload["queue_position"] = _queue_position(job, worker)
        return Response(json.dumps(payload, indent=2), media_type="application/json")

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_page(job_id: str) -> Response:
        job = jobs.find(data_dir, job_id)
        if job is None:
            return HTMLResponse("<h1>No such job</h1>", status_code=404)
        average = await run_in_threadpool(ledger.running_average, data_dir)
        return HTMLResponse(
            render_job_page(job, position=_queue_position(job, worker), average=average)
        )

    @app.post("/jobs/{job_id}/retry")
    async def retry(job_id: str) -> Response:
        """Run a failed job again from the step it failed at (043). The queue rules of
        041 apply: the slot is reserved before the job is requeued, so a retry the
        queue has no room for leaves the job failed with its button still there."""
        job = jobs.find(data_dir, job_id)
        if job is None:
            return JSONResponse({"error": "no such job"}, status_code=404)
        refusal = retry_refusal(job)
        if refusal:
            return HTMLResponse(render_refusal(job, refusal), status_code=409)
        try:
            worker.reserve()
        except QueueFull:
            return HTMLResponse(
                render_refusal(job, f"{worker.depth()} shorts are already in the queue; "
                                    "try in an hour."),  # fmt: skip
                status_code=503,
                headers={"Retry-After": str(QUEUE_RETRY_S)},
            )
        try:
            requeued = await run_in_threadpool(jobs.requeue, job, now=clock)
        except Exception:
            worker.release()
            raise
        worker.submit(requeued.path, reserved=True)
        return RedirectResponse(f"/jobs/{requeued.id}", status_code=303)

    @app.get("/jobs/{job_id}/{name}")
    async def job_file(job_id: str, name: str, download: bool = False) -> Response:
        """One of the `out/` deliverables (10.4); `?download=1` makes it an attachment."""
        job = jobs.find(data_dir, job_id)
        media_type = OUT_FILES.get(name)
        if job is None or media_type is None or not (job.out_dir / name).is_file():
            return JSONResponse({"error": "no such file"}, status_code=404)
        headers = None
        if download:
            headers = {"Content-Disposition": f'attachment; filename="{job.id}-{name}"'}
        return FileResponse(job.out_dir / name, media_type=media_type, headers=headers)

    return app


def retry_refusal(job: Job) -> str:
    """Why this job cannot be retried (043), or "" when it can. The page hides the
    button for the same reason, so the route and the button always agree."""
    if job.status != "failed":
        return NOT_FAILED_SENTENCE
    if job.record.swept_at is not None:
        return SWEPT_RETRY_SENTENCE
    return ""


def render_refusal(job: Job, sentence: str) -> str:
    """One sentence and the way back to the job: what a refused retry answers."""
    return _template("upload.html").substitute(
        rejection=f'<p class="reject">{html.escape(sentence)}</p>',
        body=f'<p><a href="/jobs/{html.escape(job.id)}">Back to the job</a></p>',
    )


def _queue_position(job: Job, worker: pipeline.Worker) -> int | None:
    """Only an `uploaded` job that is waiting has a position (11.1 "queued, position N")."""
    return worker.position(job.path) if job.status == "uploaded" else None


def _seconds_to_next_midnight_ist(now: datetime) -> int:
    next_midnight = jobs.midnight_ist(now) + timedelta(days=1)
    return max(1, int((next_midnight - now).total_seconds()))


def _too_large(limits: Limits, chips: Sequence[str]) -> HTMLResponse:
    sentence = f"The recording must be {limits.max_upload_bytes // ingest.MIB} MB or smaller."
    return HTMLResponse(
        render_upload_form(limits, chips=chips, rejection=sentence), status_code=413
    )


# --- passcode guard -------------------------------------------------------------


class PasscodeGuard:
    """ASGI middleware: every HTTP request except `/health` and `POST /passcode` needs a
    cookie signed with the current passcode. Non-HTTP scopes (lifespan) pass through."""

    def __init__(self, app: ASGIApp, *, passcode: str, clock: Clock) -> None:
        self._app = app
        self._passcode = passcode
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request = Request(scope)
        path = request.url.path
        exempt = path == "/health" or (path == PASSCODE_PATH and request.method == "POST")
        if exempt or auth.verify_cookie(
            request.cookies.get(COOKIE_NAME), self._passcode, now=self._clock()
        ):
            await self._app(scope, receive, send)
            return
        await _unauthorized(request)(scope, receive, send)


def _unauthorized(request: Request) -> Response:
    if _wants_json(request):
        return JSONResponse({"error": "passcode required"}, status_code=401)
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    if target == "/" and request.method == "GET":
        return HTMLResponse(render_passcode_form("", "/"), status_code=200)
    return HTMLResponse(render_passcode_form("", _local_path(target)), status_code=401)


def _wants_json(request: Request) -> bool:
    if request.url.path.endswith(".json"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _local_path(value: str) -> str:
    """Only a same-site absolute path may be a post-login target; anything else is `/`."""
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def _blocked(remaining_s: float) -> str:
    minutes = max(1, math.ceil(remaining_s / 60))
    return f"Too many wrong passcodes from this address. Try again in {minutes} minutes."


# --- form handling --------------------------------------------------------------


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _spool(value: object, dest_dir: Path) -> VideoUpload | None:
    """Copy one multipart file to `dest_dir`; None for an empty or absent field."""
    if not isinstance(value, UploadFile) or not value.filename:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = _SAFE_NAME.sub("_", Path(value.filename).name) or "upload"
    target = dest_dir / safe
    value.file.seek(0)
    with target.open("wb") as fh:
        shutil.copyfileobj(value.file, fh)
    if target.stat().st_size == 0:
        return None
    return VideoUpload(path=target, original_name=Path(value.filename).name)


def _rejection(
    limits: Limits,
    chips: Sequence[str],
    sentence: str,
    brief: str,
    style_line: str,
    captions: list[str],
) -> HTMLResponse:
    page = render_upload_form(
        limits,
        chips=chips,
        rejection=sentence,
        brief=brief,
        style_line=style_line,
        captions=captions,
    )
    return HTMLResponse(page, status_code=422)


# --- rendering ------------------------------------------------------------------


def render_passcode_form(message: str, next_url: str) -> str:
    return _template("passcode.html").substitute(
        message=f'<p class="reject">{html.escape(message)}</p>' if message else "",
        next=html.escape(next_url),
    )


def render_upload_form(
    limits: Limits,
    *,
    chips: Sequence[str] = (),
    rejection: str = "",
    brief: str = "",
    style_line: str = "",
    captions: list[str] | None = None,
    closed: str = "",
) -> str:
    """The upload page; `chips` are the shipped style names (2.1); with `closed` set,
    the notice replaces the form (11.2 day limit)."""
    if closed:
        body = f'<p class="closed">{html.escape(closed)}</p>'
    else:
        captions = captions or []
        refs: list[str] = []
        for n in range(1, MAX_REFERENCE_FIELDS + 1):
            caption = captions[n - 1] if n - 1 < len(captions) else ""
            refs.append(
                f'    <div class="ref"><input name="ref_{n}" type="file" '
                f'accept=".jpg,.jpeg,.png,.webp,.mp4,.mov">'
                f'<input name="caption_{n}" type="text" placeholder="one-line caption" '
                f'value="{html.escape(caption)}"></div>'
            )
        body = _template("upload_form.html").substitute(
            max_upload_mb=limits.max_upload_bytes // ingest.MIB,
            brief=html.escape(brief),
            style=html.escape(style_line),
            chips="".join(
                f'<span class="chip" role="button" tabindex="0" data-chip="{html.escape(c)}">'
                f"{html.escape(c)}</span>"
                for c in chips
            ),
            references="\n".join(refs),
        )
    return _template("upload.html").substitute(
        rejection=f'<p class="reject">{html.escape(rejection)}</p>' if rejection else "",
        body=body,
    )


def _elapsed(job: Job, now: datetime) -> str:
    end = job.record.updated_at if job.status in SETTLED else now
    seconds = max(0, int((end - job.record.created_at).total_seconds()))
    return f"{seconds // 60}m {seconds % 60}s"


def _step_items(job: Job) -> str:
    status = job.status
    failed_at = job.record.error.step if job.record.error else None
    items: list[str] = []
    if status in STATUS_ORDER:
        current_index = STATUS_ORDER.index(status)
    elif status in ("passed", "rejected"):
        current_index = len(STATUS_ORDER)
    else:  # failed
        current_index = STATUS_ORDER.index(failed_at) if failed_at in STATUS_ORDER else -1  # type: ignore[arg-type]
    for i, step in enumerate(STATUS_ORDER):
        if status == "failed" and i == current_index:
            cls = "step failed"
        elif i < current_index:
            cls = "step done"
        elif i == current_index:
            cls = "step current"
        else:
            cls = "step"
        items.append(f'  <li data-step="{step}" class="{cls}">{step}</li>')
    if status in ("passed", "rejected"):
        items.append(f'  <li data-step="{status}" class="step current">{status}</li>')
    return "\n".join(items)


def render_job_page(
    job: Job,
    *,
    now: datetime | None = None,
    position: int | None = None,
    average: ledger.RunningAverage | None = None,
) -> str:
    now = now or datetime.now(UTC)
    record = job.record
    brief_path = job.input_dir / "brief.md"
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    lines = list(record.warnings)
    if record.swept_at is not None:  # 2.2: say why the brief and the references are gone
        lines.append(SWEPT_SENTENCE)
    warnings = "\n".join(f'<p class="warning">{html.escape(w)}</p>' for w in lines)
    error = ""
    if record.error is not None:
        error = (
            f'<p class="error">Failed at {html.escape(record.error.step)}: '
            f"{html.escape(record.error.message)}</p>"
        )
        if record.error.violations:  # 8.2: the grammar's list, one line per beat and rule
            items = "\n".join(
                f"  <li>{html.escape(line)}</li>" for line in record.error.violations
            )
            error += (
                "<p>The planner's output broke these rules twice:</p>\n"
                f'<ul class="violations">\n{items}\n</ul>\n'
            )
        if not retry_refusal(job):  # 043: one button, naming the step it re-enters at
            error += (
                f'<form class="retry" method="post" action="/jobs/{html.escape(job.id)}/retry">\n'
                f'  <button type="submit">Retry from {html.escape(record.error.step)}</button>\n'
                "</form>\n"
            )
    if record.input is not None:
        inp = record.input
        input_line = (
            f"{html.escape(inp.original_name)} · {inp.width}x{inp.height} · "
            f"{inp.duration_s:.1f} s · {inp.size_bytes / ingest.MIB:.1f} MB"
        )
    else:
        input_line = "–"
    references = _reference_lines(job)
    return _template("job.html").substitute(
        job_id=html.escape(job.id),
        status=html.escape(record.status),
        elapsed=_elapsed(job, now),
        steps=_step_items(job),
        warnings=warnings,
        error=error,
        input_line=input_line,
        style=html.escape(record.style),
        style_notice=(
            f' <span class="notice">{html.escape(record.style_notice)}</span>'
            if record.style_notice
            else ""
        ),
        style_note=html.escape(record.style_note) or "–",
        references=references,
        brief=html.escape(brief),
        result=_result_block(job),
        ledger=_ledger_block(job, average),
        json_url=f"/jobs/{html.escape(job.id)}.json",
        created_at=record.created_at.isoformat(),
        terminal="true" if record.status in SETTLED else "false",
        poll_ms=POLL_MS,
        position=f" (queued, position {position})" if position is not None else "",
        position_json=json.dumps(position),
    )


def _result_block(job: Job) -> str:
    """The short, the contact sheet and the download links once the job is `delivered`
    (11.1, 10.4), and the technical check list whenever `out/qa.json` exists, so a job
    that failed at `qa` still shows which check stopped it."""
    report = technical.load_report(job)
    if report is None:
        return ""
    base = f"/jobs/{html.escape(job.id)}"
    items = "\n".join(
        f'  <li class="check {"pass" if c.passed else "fail"}">{html.escape(c.name)} '
        f'{"pass" if c.passed else "FAIL"} · {html.escape(c.detail)}</li>'
        for c in report.checks
    )
    media = ""
    if job.status in SHOWS_SHORT and (job.out_dir / "short.mp4").is_file():
        media = _template("result.html").substitute(base=base)
    return f"{media}<h2>Technical checks</h2>\n<ul class=\"checks\">\n{items}\n</ul>\n"


def _ledger_block(job: Job, average: ledger.RunningAverage | None = None) -> str:
    """The cost panel (11.3, 044): one row per step with its cash beside its
    subscription tokens and their api-equivalent value, a total row, the soft-cap flag,
    and the running average per passing short across jobs. The table waits for the
    first paid call, so a fake-only job shows no empty table, only the average."""
    record = job.record
    parts: list[str] = []
    if record.cost:
        rows = "\n".join(
            f'  <tr data-step="{html.escape(s.step)}"><td>{html.escape(s.step)}</td>'
            f"<td>{html.escape(_calls(s.rows))}</td>"
            f"{_cost_cells(s.cash_inr, s.tokens, s.inr_equivalent)}</tr>"
            for s in ledger.by_step(record)
        )
        total = _cost_cells(
            ledger.cash_total(record), ledger.tokens_total(record), ledger.equivalent_total(record)
        )
        parts.append(
            '<table class="ledger">\n'
            "  <tr><th>step</th><th>calls</th><th>cash</th><th>tokens</th>"
            "<th>tokens at the API rate</th></tr>\n"
            f"{rows}\n"
            f'  <tr class="total"><th>total</th><td></td>{total}</tr>\n'
            "</table>\n"
            "<p>Only cash counts toward the budgets; subscription tokens are valued at "
            "the API rate for comparison and never added to it.</p>"
        )
        if record.over_soft_cap:
            parts.append(
                '<p class="warning">This job is over the soft cap; nothing was skipped '
                "for cost.</p>"
            )
    if average is not None:
        line = f"Running average: INR {average.cash_inr:.2f} per passing short"
        if average.inr_equivalent:
            line += f" plus tokens worth INR {average.inr_equivalent:.2f} at the API rate"
        passed = "short" if average.passed == 1 else "shorts"
        parts.append(f'<p class="average">{line}, over {average.passed} passed {passed}.</p>')
    if not parts:
        return ""
    return "<h2>Cost</h2>\n" + "\n".join(parts) + "\n"


def _cost_cells(cash: float, tokens: int, equivalent: float) -> str:
    return (
        f"<td>{f'INR {cash:.2f}' if cash > 0 else '-'}</td>"
        f"<td>{f'{tokens} tokens' if tokens else '-'}</td>"
        f"<td>{f'INR {equivalent:.2f}' if tokens else '-'}</td>"
    )


def _calls(rows: Sequence[jobs.CostRow]) -> str:
    return "; ".join(f"{r.provider} {r.model} ({_units(r.units)})" for r in rows)


def _units(units: dict[str, float]) -> str:
    return ", ".join(f"{name} {quantity:g}" for name, quantity in units.items())


def _reference_lines(job: Job) -> str:
    refs_path = job.input_dir / "refs.json"
    if not refs_path.is_file():
        return "none"
    rows = _REFS.validate_json(refs_path.read_text(encoding="utf-8"))
    if not rows:
        return "none"
    return "<br>".join(
        f"{html.escape(r.original_name)} ({r.width}x{r.height}) "
        f"{html.escape(r.caption) if r.caption else ''}".rstrip()
        for r in rows
    )


app = create_app()
