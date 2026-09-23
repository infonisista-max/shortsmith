"""sweeper: retention as code (decisions 2.2, 11.2) with the clock injected.

`input/` and `work/` go 24 h after the job was uploaded, the whole job directory at
7 days, a job that is still in flight is never touched, every deletion is a `job.log`
line and a `swept_at` stamp, and `--dry-run` writes nothing. The boundary tests sit on
the exact values in the decisions (23 h 59 min / 24 h 01 min, 6 d 23 h 59 min / 7 d).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import jobs, sweeper
from shortsmith.jobs import STATUS_ORDER, Clock, Job, Status

T0 = datetime(2026, 9, 20, 9, 0, 0, tzinfo=UTC)


def at(moment: datetime) -> Clock:
    return lambda: moment


def make_job(
    data_dir: Path, *, created: datetime = T0, status: Status = "delivered"
) -> Job:
    """A job on disk at `created`, walked to `status`, with a file in every directory."""
    now = at(created)
    job = jobs.create(data_dir, now=now)
    for name, text in (("input", "raw"), ("work", "plan"), ("out", "short")):
        (job.path / name / f"{name}.txt").write_text(text, encoding="utf-8")
    if status == "failed":
        job = jobs.transition(job, "transcribing", now=now)
        return jobs.fail(job, step="transcribing", message="no", now=now)
    target = "delivered" if status in ("passed", "rejected") else status
    for step in STATUS_ORDER[1 : STATUS_ORDER.index(target) + 1]:  # type: ignore[arg-type]
        job = jobs.transition(job, step, now=now)
    if status in ("passed", "rejected"):
        job = jobs.transition(job, status, now=now)
    return job


def record(job: Job) -> dict[str, object]:
    return json.loads((job.json_path).read_text(encoding="utf-8"))


def test_a_job_23_h_59_min_old_is_untouched(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    actions = sweeper.sweep(tmp_path, now=at(T0 + timedelta(hours=23, minutes=59)))
    assert actions == []
    assert (job.input_dir / "input.txt").is_file()
    assert (job.work_dir / "work.txt").is_file()
    assert record(job)["swept_at"] is None


def test_a_job_24_h_01_min_old_loses_input_and_work_only(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    swept_at = T0 + timedelta(hours=24, minutes=1)
    actions = sweeper.sweep(tmp_path, now=at(swept_at))
    assert [(a.job_id, a.scope, a.deleted) for a in actions] == [
        (job.id, "working", ("input", "work"))
    ]
    assert not job.input_dir.exists()
    assert not job.work_dir.exists()
    # 2.2: the finished short and its rights evidence outlive the upload.
    assert (job.out_dir / "out.txt").is_file()
    assert datetime.fromisoformat(str(record(job)["swept_at"])) == swept_at
    log = job.log_path.read_text(encoding="utf-8").splitlines()
    assert log[-1] == f"{swept_at.isoformat()} swept: deleted input/, work/"


def test_a_swept_job_is_not_swept_again(tmp_path: Path) -> None:
    make_job(tmp_path)
    first = T0 + timedelta(hours=25)
    assert len(sweeper.sweep(tmp_path, now=at(first))) == 1
    assert sweeper.sweep(tmp_path, now=at(first + timedelta(hours=1))) == []


def test_a_job_still_in_flight_is_never_touched(tmp_path: Path) -> None:
    job = make_job(tmp_path, status="rendering")
    assert sweeper.sweep(tmp_path, now=at(T0 + timedelta(days=9))) == []
    assert (job.input_dir / "input.txt").is_file()
    assert job.json_path.is_file()


@pytest.mark.parametrize("status", ["uploaded", "planning", "qa"])
def test_every_unsettled_status_is_left_alone(tmp_path: Path, status: Status) -> None:
    job = make_job(tmp_path, status=status)
    assert sweeper.sweep(tmp_path, now=at(T0 + timedelta(days=9))) == []
    assert job.work_dir.is_dir()


@pytest.mark.parametrize("status", ["delivered", "passed", "rejected", "failed"])
def test_a_settled_job_of_7_days_loses_the_whole_directory(
    tmp_path: Path, status: Status
) -> None:
    job = make_job(tmp_path, status=status)
    actions = sweeper.sweep(tmp_path, now=at(T0 + timedelta(days=7, minutes=1)))
    assert [(a.job_id, a.scope) for a in actions] == [(job.id, "job")]
    assert not job.path.exists()


def test_the_day_before_the_7_day_delete_only_the_working_files_go(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    actions = sweeper.sweep(tmp_path, now=at(T0 + timedelta(days=6, hours=23, minutes=59)))
    assert [a.scope for a in actions] == ["working"]
    assert job.path.is_dir()
    assert (job.out_dir / "out.txt").is_file()


def test_dry_run_reports_the_same_actions_and_writes_nothing(tmp_path: Path) -> None:
    young = make_job(tmp_path, created=T0)
    old = make_job(tmp_path, created=T0 - timedelta(days=8))
    now = at(T0 + timedelta(hours=25))
    planned = sweeper.sweep(tmp_path, now=now, dry_run=True)
    assert {(a.job_id, a.scope) for a in planned} == {
        (young.id, "working"),
        (old.id, "job"),
    }
    assert (young.input_dir / "input.txt").is_file()
    assert old.path.is_dir()
    assert record(young)["swept_at"] is None
    assert young.log_path.read_text(encoding="utf-8").count("swept") == 0
    # ...and the real pass then does exactly what the dry run said it would.
    assert [(a.job_id, a.scope) for a in sweeper.sweep(tmp_path, now=now)] == [
        (a.job_id, a.scope) for a in planned
    ]


def test_a_job_directory_without_job_json_is_ignored(tmp_path: Path) -> None:
    orphan = tmp_path / "jobs" / "20260920-090000-abcdef"
    orphan.mkdir(parents=True)
    assert sweeper.sweep(tmp_path, now=at(T0 + timedelta(days=30))) == []
    assert orphan.is_dir()


def test_an_empty_data_dir_sweeps_nothing(tmp_path: Path) -> None:
    assert sweeper.sweep(tmp_path, now=at(T0)) == []


# --- the disk guard (11.2) ------------------------------------------------------


def test_free_bytes_reads_the_nearest_existing_parent(tmp_path: Path) -> None:
    assert sweeper.free_bytes(tmp_path / "not" / "there" / "yet") > 0


def test_low_disk_is_the_5_gb_line(tmp_path: Path) -> None:
    assert sweeper.low_disk(lambda _: sweeper.MIN_FREE_BYTES - 1, tmp_path) is True
    assert sweeper.low_disk(lambda _: sweeper.MIN_FREE_BYTES, tmp_path) is False


# --- the CLI --------------------------------------------------------------------


def test_cli_dry_run_prints_the_actions_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job = make_job(tmp_path, created=T0 - timedelta(days=2))
    code = sweeper.main(["--dry-run"], data_dir=tmp_path, now=at(T0))
    out = capsys.readouterr().out
    assert code == 0
    assert f"{job.id}: deleted input/, work/" in out
    assert "dry run" in out
    assert (job.input_dir / "input.txt").is_file()


def test_cli_without_the_flag_performs_the_deletions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job = make_job(tmp_path, created=T0 - timedelta(days=2))
    code = sweeper.main([], data_dir=tmp_path, now=at(T0))
    assert code == 0
    assert f"{job.id}: deleted input/, work/" in capsys.readouterr().out
    assert not job.input_dir.exists()


def test_cli_says_so_when_there_is_nothing_to_sweep(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_job(tmp_path)
    assert sweeper.main([], data_dir=tmp_path, now=at(T0)) == 0
    assert "nothing to sweep" in capsys.readouterr().out


def test_cli_rejects_an_unknown_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sweeper.main(["--all"], data_dir=tmp_path, now=at(T0)) == 2
    assert "usage" in capsys.readouterr().err
