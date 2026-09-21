"""The gate as the pipeline's `qa` step sees it (10.1, 10.4): `check` runs the
technical checks and writes `out/qa.json`; `contact_sheet` composes `out/contact.jpg`
once the checks pass. `TechnicalGate` is the real one; `FakeGate` passes T1-T4 and
writes a one-pixel JPEG so the pipeline and app tests stay off the media (12.1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

from shortsmith import contact_sheet
from shortsmith.jobs import Job
from shortsmith.qa import technical
from shortsmith.qa.technical import QaCheck, QaReport


class Gate(ABC):
    @abstractmethod
    def check(self, job: Job) -> QaReport:
        """Run the checks in order, write `out/qa.json`, return the report."""

    @abstractmethod
    def contact_sheet(self, job: Job) -> Path:
        """Write `out/contact.jpg` and return it."""


class TechnicalGate(Gate):
    def check(self, job: Job) -> QaReport:
        return technical.run(job)

    def contact_sheet(self, job: Job) -> Path:
        return contact_sheet.compose(job)


class FakeGate(Gate):
    """Every check passes, or the checks up to `fail` with that one failing."""

    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.jobs: list[Path] = []

    def check(self, job: Job) -> QaReport:
        self.jobs.append(job.path)
        checks: list[QaCheck] = []
        for name in contact_sheet.TECHNICAL_CHECKS:
            failed = name == self.fail
            checks.append(QaCheck(name=name, passed=not failed, detail=f"fake {name}"))
            if failed:
                break
        report = QaReport(checks=checks, passed=all(c.passed for c in checks))
        technical.write_report(job, report)
        return report

    def contact_sheet(self, job: Job) -> Path:
        out = job.out_dir / "contact.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1, 1), contact_sheet.BG_COLOUR).save(out, format="JPEG")
        return out
