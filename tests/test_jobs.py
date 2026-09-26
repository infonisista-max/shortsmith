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
    job = jobs.create(
        tmp_path,
        style="explainer",
        style_note="hitech please",
        style_notice="hitech not available yet, using explainer",
        now=clock,
    )
    assert job.path == tmp_path / "jobs" / job.id
    for name in ("input", "work", "out"):
        assert (job.path / name).is_dir()
    record = json.loads((job.path / "job.json").read_text(encoding="utf-8"))
    assert record["id"] == job.id
    assert record["status"] == "uploaded"
    # 1.1 / 2.2: the resolved style, the full line as the note, the 1.4 notice.
    assert record["style"] == "explainer"
    assert record["style_note"] == "hitech please"
    assert record["style_notice"] == "hitech not available yet, using explainer"
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


def test_progress_is_written_without_a_log_line_and_cleared_by_the_next_transition(
    tmp_path: Path, clock: Clock
) -> None:
    """11.1: a percentage during `rendering` from Remotion frame progress (ticket 004)."""
    job = jobs.create(tmp_path, now=clock)
    assert job.record.progress is None
    for status in ("transcribing", "planning", "sourcing", "rendering"):
        job = jobs.transition(job, status, now=clock)
    lines_before = len((job.path / "job.log").read_text(encoding="utf-8").splitlines())
    job = jobs.set_progress(job, 42, now=clock)
    assert jobs.load(job.path).record.progress == 42
    assert len((job.path / "job.log").read_text(encoding="utf-8").splitlines()) == lines_before
    job = jobs.transition(job, "qa", now=clock)
    assert jobs.load(job.path).record.progress is None


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


def _failed_at(tmp_path: Path, clock: Clock, step: Status) -> jobs.Job:
    """A job that ran as far as `step` and failed there (043)."""
    job = jobs.create(tmp_path, now=clock)
    for status in STATUS_ORDER[1 : STATUS_ORDER.index(step) + 1]:
        job = jobs.transition(job, status, now=clock)
    return jobs.fail(job, step=step, message="we could not do it", detail="boom", now=clock)


def test_requeue_returns_a_failed_job_to_uploaded_carrying_the_step(
    tmp_path: Path, clock: Clock
) -> None:
    """043: the retry re-queues the job and says where it re-enters; the error leaves
    job.json (the page is waiting again now) but stays in job.log."""
    job = _failed_at(tmp_path, clock, "rendering")
    requeued = jobs.requeue(job, now=clock)
    assert requeued.status == "uploaded"
    assert requeued.record.retry_from == "rendering"
    assert requeued.record.error is None
    assert jobs.load(job.path).record.retry_from == "rendering"
    last = (job.path / "job.log").read_text(encoding="utf-8").splitlines()[-1]
    assert "failed -> uploaded retry_from=rendering" in last


def test_a_requeued_job_may_re_enter_at_its_step_and_nowhere_else(
    tmp_path: Path, clock: Clock
) -> None:
    """The forward jump is the retry's alone: `uploaded -> rendering` is legal only
    while `retry_from` says so, so a fresh job still cannot skip a step."""
    job = jobs.requeue(_failed_at(tmp_path, clock, "rendering"), now=clock)
    with pytest.raises(IllegalTransition):
        jobs.transition(job, "qa", now=clock)
    job = jobs.transition(job, "rendering", now=clock)
    assert jobs.load(job.path).status == "rendering"


def test_requeue_refuses_a_job_that_did_not_fail(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, now=clock)
    before = (job.path / "job.json").read_bytes()
    with pytest.raises(IllegalTransition):
        jobs.requeue(job, now=clock)
    assert (job.path / "job.json").read_bytes() == before


def test_a_job_that_fails_twice_at_the_same_step_keeps_both_errors_in_the_log(
    tmp_path: Path, clock: Clock
) -> None:
    job = _failed_at(tmp_path, clock, "rendering")
    job = jobs.requeue(job, now=clock)
    job = jobs.transition(job, "rendering", now=clock)
    job = jobs.fail(job, step="rendering", message="we could not do it", detail="again", now=clock)
    failures = [
        line for line in (job.path / "job.log").read_text(encoding="utf-8").splitlines()
        if "-> failed" in line
    ]  # fmt: skip
    assert len(failures) == 2
    assert all("step=rendering" in line for line in failures)


def _delivered(tmp_path: Path, clock: Clock) -> jobs.Job:
    job = jobs.create(tmp_path, now=clock)
    for status in STATUS_ORDER[1:]:
        job = jobs.transition(job, status, now=clock)
    return job


def test_rate_stores_score_note_and_time_on_job_json_with_a_log_line(
    tmp_path: Path, clock: Clock
) -> None:
    """10.3 / 034: the phone rating lands on `job.json.rating` and the log says so; a
    second rating overwrites the first (the slider re-posts) and both are in the log."""
    job = _delivered(tmp_path, clock)
    assert job.record.rating is None
    rated = jobs.rate(job, 7, "good hook, weak finale", now=clock)
    on_disk = jobs.load(job.path).record
    assert on_disk.rating == rated.record.rating
    assert on_disk.rating is not None
    assert on_disk.rating.score == 7 and on_disk.rating.note == "good hook, weak finale"
    assert on_disk.rating.rated_at == on_disk.updated_at
    assert on_disk.status == "delivered"  # the verdict is the calibration's, not here
    rated = jobs.rate(rated, 4, "", now=clock)
    assert jobs.load(job.path).record.rating == rated.record.rating
    lines = job.log_path.read_text(encoding="utf-8").splitlines()
    assert lines[-2].endswith("rated 7/10: good hook, weak finale")
    assert lines[-1].endswith("rated 4/10")


@pytest.mark.parametrize("score", [0, 11])
def test_rate_refuses_a_score_off_the_1_to_10_scale(
    tmp_path: Path, clock: Clock, score: int
) -> None:
    job = _delivered(tmp_path, clock)
    with pytest.raises(ValueError):
        jobs.rate(job, score, "", now=clock)
    assert jobs.load(job.path).record.rating is None


def test_rate_refuses_a_job_that_has_no_short_yet(tmp_path: Path, clock: Clock) -> None:
    job = jobs.transition(jobs.create(tmp_path, now=clock), "transcribing", now=clock)
    with pytest.raises(IllegalTransition):
        jobs.rate(job, 7, "", now=clock)


def test_settle_moves_a_job_between_delivered_passed_and_rejected_only(
    tmp_path: Path, clock: Clock
) -> None:
    """10.4: the verdict may change with the rating (a `passed` job rated 4 is
    `rejected`), so the three settled statuses move among themselves by `settle` and
    by nothing else; `transition` still treats `passed` and `rejected` as terminal."""
    job = _delivered(tmp_path, clock)
    job = jobs.settle(job, "passed", "rating 7/10", now=clock)
    assert jobs.load(job.path).status == "passed"
    job = jobs.settle(job, "rejected", "rating 4/10", now=clock)
    assert jobs.load(job.path).status == "rejected"
    job = jobs.settle(job, "delivered", "rating withdrawn", now=clock)
    assert jobs.load(job.path).status == "delivered"
    lines = job.log_path.read_text(encoding="utf-8").splitlines()
    assert lines[-3].endswith("delivered -> passed by rating 7/10")
    assert lines[-2].endswith("passed -> rejected by rating 4/10")
    assert lines[-1].endswith("rejected -> delivered by rating withdrawn")
    with pytest.raises(IllegalTransition):
        jobs.transition(jobs.settle(job, "passed", "x", now=clock), "rejected", now=clock)


def test_settle_to_the_same_status_writes_nothing(tmp_path: Path, clock: Clock) -> None:
    job = _delivered(tmp_path, clock)
    before_json = job.json_path.read_bytes()
    before_log = job.log_path.read_bytes()
    assert jobs.settle(job, "delivered", "no change", now=clock).status == "delivered"
    assert job.json_path.read_bytes() == before_json
    assert job.log_path.read_bytes() == before_log


@pytest.mark.parametrize("status", ["uploaded", "failed"])
def test_settle_refuses_a_job_that_is_not_settled_or_a_status_that_is_not_a_verdict(
    tmp_path: Path, clock: Clock, status: str
) -> None:
    job = jobs.create(tmp_path, now=clock)
    with pytest.raises(IllegalTransition):
        jobs.settle(job, "passed", "x", now=clock)
    with pytest.raises(IllegalTransition):
        jobs.settle(_delivered(tmp_path, clock), status, "x", now=clock)  # type: ignore[arg-type]


def test_set_performance_stores_the_youtube_fields_with_a_log_line(
    tmp_path: Path, clock: Clock
) -> None:
    """14.1(a): the published URL, views and retention are fields on the job, filled by
    hand or by a read-only pull; never an upload."""
    job = _delivered(tmp_path, clock)
    assert job.record.performance is None
    stored = jobs.set_performance(
        job,
        published_url="https://youtube.com/shorts/abc123DEF45",
        views=1200,
        retention_pct=63.5,
        views_source="manual",
        now=clock,
    )
    on_disk = jobs.load(job.path).record
    assert on_disk.performance == stored.record.performance
    assert on_disk.performance is not None
    assert on_disk.performance.published_url == "https://youtube.com/shorts/abc123DEF45"
    assert on_disk.performance.views == 1200 and on_disk.performance.retention_pct == 63.5
    assert on_disk.performance.views_source == "manual"
    assert on_disk.performance.updated_at == on_disk.updated_at
    assert on_disk.status == "delivered"
    last = job.log_path.read_text(encoding="utf-8").splitlines()[-1]
    assert last.endswith(
        "performance: https://youtube.com/shorts/abc123DEF45 views 1200 (manual) retention 63.5%"
    )


def test_set_performance_refuses_a_job_that_has_no_short_yet(tmp_path: Path, clock: Clock) -> None:
    with pytest.raises(IllegalTransition):
        jobs.set_performance(jobs.create(tmp_path, now=clock), published_url="x", now=clock)


def test_data_dir_of_is_the_directory_the_job_was_created_under(
    tmp_path: Path, clock: Clock
) -> None:
    job = jobs.create(tmp_path, now=clock)
    assert jobs.data_dir_of(job) == tmp_path


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
        "violations": [],  # 009: the grammar's list when the planner was rejected twice
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


def test_a_job_json_from_before_008_still_loads(tmp_path: Path, clock: Clock) -> None:
    """Jobs written before the style fields carried `style_line`; it becomes the note
    and the style is explainer, so an old data directory keeps loading."""
    job = jobs.create(tmp_path, now=clock)
    old = json.loads(job.json_path.read_text(encoding="utf-8"))
    for key in ("style", "style_note", "style_notice"):
        old.pop(key)
    old["style_line"] = "hitech please"
    job.json_path.write_text(json.dumps(old), encoding="utf-8")
    loaded = jobs.load(job.path)
    assert (loaded.record.style, loaded.record.style_note, loaded.record.style_notice) == (
        "explainer", "hitech please", "",
    )  # fmt: skip


def test_load_round_trips(tmp_path: Path, clock: Clock) -> None:
    job = jobs.create(tmp_path, style_note="hitech please", now=clock)
    loaded = jobs.load(job.path)
    assert loaded.record == job.record
    assert loaded.path == job.path
    assert loaded.input_dir == job.path / "input"
    assert loaded.work_dir == job.path / "work"
    assert loaded.out_dir == job.path / "out"


def test_created_since_counts_jobs_at_and_after_the_instant(tmp_path: Path) -> None:
    """11.2: MAX_JOBS_PER_DAY counts jobs created since midnight IST; the caller
    supplies the instant, this counts on `created_at` from job.json."""
    midnight = datetime(2026, 9, 20, 18, 30, 0, tzinfo=UTC)  # 2026-09-21 00:00 IST
    stamps = [midnight - timedelta(seconds=1), midnight, midnight + timedelta(hours=5)]
    for stamp in stamps:
        jobs.create(tmp_path, now=lambda stamp=stamp: stamp)
    (tmp_path / "jobs" / "not-a-job").mkdir()
    assert jobs.created_since(tmp_path, midnight) == 2
    assert jobs.created_since(tmp_path, midnight - timedelta(days=1)) == 3
    assert jobs.created_since(tmp_path, midnight + timedelta(days=1)) == 0
    assert jobs.created_since(tmp_path / "elsewhere", midnight) == 0


def test_list_recent_is_the_newest_n_by_creation_time(tmp_path: Path) -> None:
    """11.1 job list: newest first by `created_at` from job.json, not by directory
    name, which only resolves to the second (two jobs in one second sort at random)."""
    t = datetime(2026, 9, 20, 9, 0, 0, tzinfo=UTC)
    stamps = [t + timedelta(microseconds=us) for us in (300, 100, 200)]
    stamps.append(t - timedelta(hours=1))
    made = [jobs.create(tmp_path, now=lambda s=s: s) for s in stamps]
    listed = jobs.list_recent(tmp_path)
    assert [j.id for j in listed] == [made[0].id, made[2].id, made[1].id, made[3].id]
    assert [j.id for j in jobs.list_recent(tmp_path, n=2)] == [made[0].id, made[2].id]
    assert jobs.list_recent(tmp_path / "elsewhere") == []


def test_list_recent_can_leave_out_jobs_created_before_an_instant(tmp_path: Path) -> None:
    """2.2: a job past 7 days is gone from the list even if the sweeper has not run
    yet, and the cut to `n` is taken after that, so old jobs never crowd out new ones."""
    t = datetime(2026, 9, 20, 9, 0, 0, tzinfo=UTC)
    old = jobs.create(tmp_path, now=lambda: t - timedelta(days=8))
    new = jobs.create(tmp_path, now=lambda: t)
    assert [j.id for j in jobs.list_recent(tmp_path, since=t - timedelta(days=7))] == [new.id]
    assert [j.id for j in jobs.list_recent(tmp_path)] == [new.id, old.id]


def test_listing_tolerates_a_job_directory_mid_write(tmp_path: Path, clock: Clock) -> None:
    """A directory whose job.json is not there yet, is half written, or went between
    the listing and the read is skipped, never an error for the whole page."""
    good = jobs.create(tmp_path, now=clock)
    root = tmp_path / "jobs"
    (root / "20260920-090010-aaaaaa" / "input").mkdir(parents=True)  # no job.json yet
    half = root / "20260920-090011-bbbbbb"
    half.mkdir()
    (half / "job.json").write_text('{"id": "20260920-090011-bbbbbb", "sta', encoding="utf-8")
    wrong = root / "20260920-090012-cccccc"
    wrong.mkdir()
    (wrong / "job.json").write_text('{"id": 1}', encoding="utf-8")
    (root / "not-a-job").mkdir()
    assert [j.id for j in jobs.list_recent(tmp_path)] == [good.id]
    assert [j.id for j in jobs.iter_jobs(tmp_path)] == [good.id]


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
