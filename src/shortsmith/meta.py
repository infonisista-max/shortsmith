"""`out/meta.json`: the proof of the bar for one short (decision 10.4; ticket 035).

`build(job)` reads what the job left on disk - `job.json` (status, style, the prompt and
style versions recorded at `planning`, the ledger rows, the rating, the critic summary
and the audience), `out/qa.json` (T1-T13 and the critic's report), `work/plan.json`
(the category), `work/plan.validated.json` (the clamps) and `work/assets.json` (the
rescued beats) - and the reference pack's version from `docs/reference/README.md`, and
returns a `contracts.Meta`. Nothing here fails a job: a file that is missing reads as
absent, so a job that never got past upload still describes itself.

`write(job)` is called by the pipeline once the job is settled and by the app after
every rating or performance save, so the file always reflects the latest verdict; the
day-14 gate (047) reads it and nothing else. `delivered` is the 10.4 rule: every
technical check passed and the four deliverables exist.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from shortsmith import assets, jobs, ledger
from shortsmith.contracts import Meta, PicturePlan, TechnicalResult, ValidatedPlan
from shortsmith.jobs import Clock, Job
from shortsmith.qa import critic, technical

NAME = "meta.json"
DELIVERABLES = ("short.mp4", "contact.jpg", "rights.json", "credits.md")  # 10.4
_PACK_VERSION = re.compile(r"^Pack version:\s*(\S+)", re.MULTILINE)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def pack_version(readme: Path = critic.REFERENCE_README) -> str | None:
    """The `Pack version: <v>` line of the reference pack's README; None when the file
    or the line is missing (an unversioned pack is recorded as such, never as "1")."""
    if not readme.is_file():
        return None
    match = _PACK_VERSION.search(readme.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def path(job: Job) -> Path:
    return job.out_dir / NAME


def build(job: Job, *, now: Clock = _utc_now, readme: Path = critic.REFERENCE_README) -> Meta:
    """The record from the job's files as they are now (job.json is re-read: the ledger
    and the rating write it behind the caller's `Job` value)."""
    record = jobs.load(job.path).record
    report = technical.load_report(job)
    plan_path = job.work_dir / "plan.json"
    category = (
        PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8")).category
        if plan_path.is_file()
        else "other"
    )
    validated_path = job.work_dir / "plan.validated.json"
    clamps = (
        len(ValidatedPlan.model_validate_json(validated_path.read_text(encoding="utf-8")).clamps)
        if validated_path.is_file()
        else 0
    )
    manifest = assets.load_manifest(job.path)
    rescued = sum(1 for b in manifest.beats if b.rescued) if manifest is not None else 0
    checks = (
        [TechnicalResult(name=c.name, status=c.status, detail=c.detail) for c in report.checks]
        if report is not None
        else []
    )
    passed = report is not None and report.passed
    delivered = passed and all((job.out_dir / name).is_file() for name in DELIVERABLES)
    return Meta(
        job_id=record.id,
        status=record.status,
        delivered=delivered,
        style=record.style,
        style_version=record.style_version,
        prompt_version=record.prompt_version,
        category=category,
        reference_pack_version=pack_version(readme),
        technical=checks,
        technical_passed=passed,
        critic=report.critic if report is not None else None,
        rating=record.rating,
        performance=record.performance,
        ledger=list(record.cost),
        cash_inr=ledger.cash_total(record),
        tokens_estimated=ledger.tokens_total(record),
        inr_equivalent=ledger.equivalent_total(record),
        over_soft_cap=record.over_soft_cap,
        clamps=clamps,
        rescued=rescued,
        written_at=now(),
    )


def write(job: Job, *, now: Clock = _utc_now, readme: Path = critic.REFERENCE_README) -> Path:
    """Build and write `out/meta.json`, replacing the previous one."""
    out = path(job)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(job, now=now, readme=readme).model_dump_json(indent=2), encoding="utf-8")
    return out


def load(job: Job) -> Meta | None:
    out = path(job)
    if not out.is_file():
        return None
    return Meta.model_validate_json(out.read_text(encoding="utf-8"))
