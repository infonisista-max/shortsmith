"""jobs: directory layout per decision 2.2, status machine per 11.1.

Every transition writes job.json and appends a timestamped line to job.log; illegal
transitions raise; `failed` carries {step, message, detail}."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import jobs
from shortsmith.jobs import STATUS_ORDER, Clock, IllegalTransition, JobError, Status


def _clock(start: datetime) -> Clock:
    t = [start]

    def now() -> datetime:
        t[0] += timedelta(seconds=1)
        return t[0]

    return now


@pytest.fixture
def clock() -> Clock:
    return _clock(datetime(2026, 9, 20, 9, 0, 0, tzinfo=UTC))


def test_create_makes_the_2_2_layout(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, style_line="explainer", now=clock)
    assert job.path == tmp_path / "jobs" / job.id
    for name in ("input", "work", "out"):
        assert (job.path / name).is_dir()
    record = json.loads((job.path / "job.json").read_text(encoding="utf-8"))
    assert record["id"] == job.id
    assert record["status"] == "uploaded"
    assert record["style_line"] == "explainer"
    assert record["error"] is None
    assert record["cost"] == []
    log = (job.path / "job.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1
    assert log[0].startswith("2026-09-20T09:00:01+00:00 ") and log[0].endswith("uploaded")


def test_job_ids_sort_in_creation_order(tmp_path: Path, clock: Clock) -> None:
    ids = [jobs.create(tmp_path, now=clock).id for _ in range(3)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 3


def test_status_order_is_11_1() -> None:
    assert STATUS_ORDER == (
        "uploaded",
        "transcribing",
        "planning",
        "sourcing",
        "rendering",
        "qa",
        "delivered",
    )


def test_every_transition_writes_json_and_one_log_line(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, now=clock)
    chain: list[Status] = [*STATUS_ORDER[1:], "passed"]
    for i, status in enumerate(chain, start=1):
        job = jobs.transition(job, status, now=clock)
        on_disk = jobs.load(job.path)
        assert on_disk.record.status == status
        assert on_disk.record.updated_at == job.record.updated_at
        lines = (job.path / "job.log").read_text(encoding="utf-8").splitlines()
        assert len(lines) == i + 1
        assert lines[-1].endswith(f" {chain[i - 2] if i > 1 else 'uploaded'} -> {status}")


def test_delivered_can_be_rejected(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, now=clock)
    for status in STATUS_ORDER[1:]:
        job = jobs.transition(job, status, now=clock)
    job = jobs.transition(job, "rejected", now=clock)
    assert jobs.load(job.path).record.status == "rejected"


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        ((), "planning"),  # skipping a step
        ((), "uploaded"),  # self-transition
        (("transcribing",), "uploaded"),  # backwards
        (("transcribing",), "passed"),  # passed only from delivered
        ((*STATUS_ORDER[1:], "passed"), "rejected"),  # terminal
        ((*STATUS_ORDER[1:], "passed"), "failed"),  # terminal
    ],
)
def test_illegal_transitions_raise_and_leave_no_trace(
    tmp_path: Path, clock: Clock, path: tuple[Status, ...], bad: Status
) -> None:
    job = jobs.create(tmp_path, now=clock)
    for status in path:
        job = jobs.transition(job, status, now=clock)
    before_json = (job.path / "job.json").read_bytes()
    before_log = (job.path / "job.log").read_bytes()
    with pytest.raises(IllegalTransition):
        jobs.transition(job, bad, now=clock)
    assert (job.path / "job.json").read_bytes() == before_json
    assert (job.path / "job.log").read_bytes() == before_log


def test_failed_carries_step_message_detail(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, now=clock)
    job = jobs.transition(job, "transcribing", now=clock)
    job = jobs.fail(
        job, step="transcribing", message="we could not hear any speech", detail="rms=-61dB",
        now=clock,
    )
    record = json.loads((job.path / "job.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["error"] == {
        "step": "transcribing",
        "message": "we could not hear any speech",
        "detail": "rms=-61dB",
    }
    last = (job.path / "job.log").read_text(encoding="utf-8").splitlines()[-1]
    assert "transcribing -> failed" in last and "step=transcribing" in last
    with pytest.raises(IllegalTransition):
        jobs.transition(job, "planning", now=clock)


def test_failed_requires_an_error_and_others_refuse_one(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, now=clock)
    with pytest.raises(ValueError):
        jobs.transition(job, "failed", now=clock)
    err = JobError(step="uploaded", message="m", detail="d")
    with pytest.raises(ValueError):
        jobs.transition(job, "transcribing", error=err, now=clock)


def test_load_round_trips(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, style_line="hitech please", now=clock)
    loaded = jobs.load(job.path)
    assert loaded.record == job.record
    assert loaded.path == job.path
    assert loaded.input_dir == job.path / "input"
    assert loaded.work_dir == job.path / "work"
    assert loaded.out_dir == job.path / "out"


def test_write_survives_a_concurrent_reader(tmp_path: Path) -> None:
    """The job page polls job.json while the worker rewrites it. On Windows the atomic
    replace fails with PermissionError while a reader holds the file open, so the
    writer retries; neither side may ever see an error or a half-written file."""
    import threading

    created = [jobs.create(tmp_path) for _ in range(40)]
    stop = threading.Event()
    reads = 0
    errors: list[BaseException] = []

    def reader() -> None:
        nonlocal reads
        while not stop.is_set():
            for job in created:
                try:
                    jobs.load(job.path)
                    reads += 1
                except BaseException as exc:  # noqa: BLE001 - collected for the assertion
                    errors.append(exc)
                    return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for job in created:
            current = job
            for status in STATUS_ORDER[1:]:
                current = jobs.transition(current, status)
            jobs.transition(current, "passed")
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not errors, errors[0]
    assert reads > 0
    assert all(jobs.load(j.path).status == "passed" for j in created)
