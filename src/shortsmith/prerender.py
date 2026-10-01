"""112b: the strict pre-render gate. After sourcing and before node starts, count the
b-roll beats (the sourced ones in `assets.json`; presenter-only beats are never sourced
and never count) whose final visual is the gradient or a generated image the plan did
not ask for. Above `STRICT_SETTLED_MAX_SHARE` the job stops before rendering with the
list (`render.render_picture` makes that one stop, with the build's and the check's
findings); at or under it the list goes to job.log as `settled:` lines and to the
quality log as `settled` rows. Forgiving mode never runs the gate.

Each finding says what the beat wanted (its query), what it used and why (the
sourcing log's last line for that beat)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from shortsmith import assets, config, jobs, quality
from shortsmith.contracts import AssetManifest, Beat, PicturePlan
from shortsmith.jobs import Job, QualityFinding

__all__ = ["Settled", "gate", "max_share", "settled"]

NO_REASON = "no reason in the sourcing log"


@dataclass(frozen=True)
class Settled:
    """The settled-for beats of one job and how many b-roll beats it has."""

    findings: list[QualityFinding] = field(default_factory=list[QualityFinding])
    broll: int = 0

    @property
    def share(self) -> float:
        return len(self.findings) / self.broll if self.broll else 0.0

    def over(self, line: float) -> bool:
        return self.share > line

    def headline(self) -> str:
        return (f"stopped before rendering: {len(self.findings)} of {self.broll} picture "
                "beats settled for a gradient or a generated image")  # fmt: skip

    def note(self, job: Job) -> None:
        """Under the line: one `settled:` job.log line and one `settled` quality-log
        row per beat."""
        for finding in self.findings:
            jobs.note(job, f"settled: {finding.line()}")
            quality.log(job, "settled", finding)


def max_share() -> float:
    """`STRICT_SETTLED_MAX_SHARE` as configured now (the environment, then `.env`)."""
    return config.load().strict_settled_max_share


def _reason(beat_id: str, log_text: str) -> str:
    pattern = re.compile(rf"sourcing: {re.escape(beat_id)}: (.+?)\s*$")
    found = [m.group(1) for line in log_text.splitlines() if (m := pattern.search(line))]
    return found[-1] if found else NO_REASON


def settled(manifest: AssetManifest | None, beats: Sequence[Beat], log_text: str) -> Settled:
    """The settled-for beats of `manifest`, named against the plan's `beats`."""
    if manifest is None:
        return Settled()
    by_id = {b.id: b for b in beats}
    origins = {r.id: r.origin for r in manifest.assets}
    findings: list[QualityFinding] = []
    for row in manifest.beats:
        beat = by_id.get(row.beat_id)
        if row.treatment == "gradient" or row.asset_id is None:
            used = "the gradient"
        elif origins.get(row.asset_id) == "generated" and (
            beat is None or beat.source_intent != "generate"
        ):
            used = f"a generated image ({row.asset_id})"
        else:
            continue
        wanted = repr(beat.query) if beat is not None and beat.query else "a picture"
        findings.append(QualityFinding(
            beat=row.beat_id, kind=beat.kind if beat is not None else "",
            cause=f"settled for {used}; wanted {wanted}; why: {_reason(row.beat_id, log_text)}",
            detail=f"fallback rung {row.fallback_rung}",
        ))  # fmt: skip
    return Settled(findings=findings, broll=len(manifest.beats))


def gate(job: Job) -> Settled:
    """`settled` from the job's own files; a job with no plan names no wanted query."""
    plan_path = job.work_dir / "plan.json"
    beats: list[Beat] = []
    if plan_path.is_file():
        beats = PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8")).beats
    log_path = job.path / "job.log"
    log_text = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    return settled(assets.load_manifest(job.path), beats, log_text)
