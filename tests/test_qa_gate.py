"""qa.gate: the interface the pipeline's `qa` step calls. The fake passes every check and
leaves the same files as the real gate (`out/qa.json`, `out/contact.jpg`) without
touching the media; the real gate is `technical.run` plus `contact_sheet.compose`."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from shortsmith import ffmpeg, jobs
from shortsmith.qa import technical
from shortsmith.qa.gate import FakeGate, Gate, TechnicalGate


def test_fake_gate_passes_every_check_and_writes_qa_json(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    gate: Gate = FakeGate()
    report = gate.check(job)
    assert report.passed
    assert [c.name for c in report.checks] == list(technical.CHECK_ORDER)
    assert [c.name for c in report.checks][-3:] == ["T11", "T12", "T13"]
    # 031: the 032 placeholders are recorded, never passed silently, even by the fake.
    assert [c.status for c in report.checks[-3:]] == ["not_implemented"] * 3
    assert all(c.status == "pass" for c in report.checks[:-3])
    assert technical.load_report(job) == report


def test_fake_gate_writes_a_small_valid_contact_sheet(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    gate = FakeGate()
    gate.check(job)
    out = gate.contact_sheet(job)
    assert out == job.out_dir / "contact.jpg"
    with Image.open(out) as image:
        assert image.format == "JPEG"
    assert gate.jobs == [job.path]


def test_fake_gate_can_be_told_to_fail_a_named_check(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    report = FakeGate(fail="T2").check(job)
    assert not report.passed
    assert [c.name for c in report.checks] == ["T1", "T2"]
    assert report.failed is not None and report.failed.name == "T2"


def test_technical_gate_probes_the_real_short(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    (job.out_dir / "short.mp4").write_bytes(b"")  # what FakeRenderer leaves: not a video
    gate: Gate = TechnicalGate()
    with pytest.raises(ffmpeg.FFmpegError):
        gate.check(job)
