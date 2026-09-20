"""FastAPI app (PRD `app`), first routes: upload form, `POST /jobs`, job page, job JSON.

Pages are stdlib `string.Template` files under `templates/`; every user-supplied or
model-generated string passes through `html.escape` before it is substituted. The
worker (`pipeline.Worker`) starts in the lifespan and runs jobs one at a time in
submission order. Passcode (040), queue limits (041), sweeper (042) come later.

`create_app` is the factory tests use with their own settings and a fake transcriber;
the module-level `app` is what `uvicorn shortsmith.app:app` serves.
"""

from __future__ import annotations

import html
import re
import shutil
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from string import Template

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import TypeAdapter
from starlette.datastructures import UploadFile

from shortsmith import config, ingest, jobs, pipeline
from shortsmith.config import Settings
from shortsmith.contracts import ReferenceRecord
from shortsmith.ingest import Limits, ReferenceUpload, Rejected, VideoUpload
from shortsmith.jobs import STATUS_ORDER, TERMINAL, Job
from shortsmith.transcriber import FakeTranscriber, Transcriber

TEMPLATES = Path(__file__).parent / "templates"
MAX_REFERENCE_FIELDS = 8
POLL_MS = 3000
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_REFS = TypeAdapter(list[ReferenceRecord])


def _template(name: str) -> Template:
    return Template((TEMPLATES / name).read_text(encoding="utf-8"))


def create_app(
    settings: Settings | None = None,
    *,
    transcriber: Transcriber | None = None,
    limits: Limits | None = None,
    start_worker: bool = True,
) -> FastAPI:
    settings = settings or config.load()
    # The Groq transcriber arrives with ticket 012; until then the fake is the only one.
    transcriber = transcriber or FakeTranscriber()
    limits = limits or Limits(max_upload_bytes=settings.shortsmith_max_upload_mb * ingest.MIB)
    worker = pipeline.Worker(transcriber=transcriber)
    data_dir = settings.shortsmith_data_dir

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        (data_dir / "jobs").mkdir(parents=True, exist_ok=True)
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="Shortsmith", lifespan=lifespan)
    app.state.data_dir = data_dir
    app.state.worker = worker
    app.state.limits = limits

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def upload_form() -> HTMLResponse:
        return HTMLResponse(render_upload_form(limits))

    @app.post("/jobs")
    async def submit(request: Request) -> Response:
        form = await request.form()
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
                    limits, "Please choose a video file to upload.", brief, style_line, captions
                )
            try:
                job = await run_in_threadpool(
                    ingest.accept,
                    data_dir,
                    video=video_upload,
                    brief=brief,
                    style_line=style_line,
                    references=references,
                    limits=limits,
                )
            except Rejected as exc:
                return _rejection(limits, str(exc), brief, style_line, captions)
        worker.submit(job.path)
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/jobs/{job_id}.json")
    async def job_json(job_id: str) -> Response:
        job = jobs.find(data_dir, job_id)
        if job is None:
            return JSONResponse({"error": "no such job"}, status_code=404)
        return Response(job.record.model_dump_json(indent=2), media_type="application/json")

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_page(job_id: str) -> Response:
        job = jobs.find(data_dir, job_id)
        if job is None:
            return HTMLResponse("<h1>No such job</h1>", status_code=404)
        return HTMLResponse(render_job_page(job))

    return app


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
    limits: Limits, sentence: str, brief: str, style_line: str, captions: list[str]
) -> HTMLResponse:
    page = render_upload_form(
        limits, rejection=sentence, brief=brief, style_line=style_line, captions=captions
    )
    return HTMLResponse(page, status_code=422)


# --- rendering ------------------------------------------------------------------


def render_upload_form(
    limits: Limits,
    *,
    rejection: str = "",
    brief: str = "",
    style_line: str = "",
    captions: list[str] | None = None,
) -> str:
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
    return _template("upload.html").substitute(
        rejection=f'<p class="reject">{html.escape(rejection)}</p>' if rejection else "",
        max_upload_mb=limits.max_upload_bytes // ingest.MIB,
        brief=html.escape(brief),
        style=html.escape(style_line),
        references="\n".join(refs),
    )


def _elapsed(job: Job, now: datetime) -> str:
    end = job.record.updated_at if job.status in TERMINAL else now
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


def render_job_page(job: Job, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    record = job.record
    brief_path = job.input_dir / "brief.md"
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    warnings = "\n".join(f'<p class="warning">{html.escape(w)}</p>' for w in record.warnings)
    error = ""
    if record.error is not None:
        error = (
            f'<p class="error">Failed at {html.escape(record.error.step)}: '
            f"{html.escape(record.error.message)}</p>"
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
        style_line=html.escape(record.style_line) or "–",
        references=references,
        brief=html.escape(brief),
        json_url=f"/jobs/{html.escape(job.id)}.json",
        created_at=record.created_at.isoformat(),
        terminal="true" if record.status in TERMINAL else "false",
        poll_ms=POLL_MS,
    )


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
