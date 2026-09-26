"""qa.calibration: the critic-versus-phone streak (decisions 10.2, 10.4; ticket 034).

`record` appends one entry per rated job (critic pass = overall >= 7, phone pass =
rating >= 6); `mode` is `blocking` once the last five carry at least four matches;
`verdict` is the 10.4 status rule in both modes. Pure arithmetic on `data/calibration.json`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import jobs
from shortsmith.jobs import STATUS_ORDER, Clock, CriticSummary, IllegalTransition, Rating
from shortsmith.qa import calibration
from shortsmith.qa.calibration import Calibration, Entry

T0 = datetime(2026, 9, 26, 9, 0, 0, tzinfo=UTC)


def _clock() -> Clock:
    t = [T0]

    def now() -> datetime:
        t[0] += timedelta(seconds=1)
        return t[0]

    return now


def _delivered(data_dir: Path, *, overall: int | None, advisory: bool = True) -> jobs.Job:
    """A job at `delivered` with the critic's summary on job.json, as `critic.run` leaves
    it; `overall` None is a critic that could not answer."""
    job = jobs.create(data_dir, now=_clock())
    for status in STATUS_ORDER[1:]:
        job = jobs.transition(job, status, now=_clock())
    summary = CriticSummary(
        status="scored" if overall is not None else "unavailable",
        overall=overall,
        advisory=advisory,
        model="fake",
    )
    return jobs.amend(job, critic=summary)


def _entry(job_id: str, *, critic_pass: bool, phone_pass: bool) -> Entry:
    return Entry(
        job_id=job_id,
        critic_overall=8 if critic_pass else 5,
        critic_pass=critic_pass,
        rating=7 if phone_pass else 4,
        phone_pass=phone_pass,
        matched=critic_pass == phone_pass,
        at=T0,
    )


def _entries(*matches: bool) -> Calibration:
    return Calibration(
        entries=[
            _entry(f"j{i}", critic_pass=True, phone_pass=m) for i, m in enumerate(matches)
        ]
    )


# --- the streak (10.2) ----------------------------------------------------------------------


def test_three_of_five_matches_is_advisory_and_four_of_five_is_blocking() -> None:
    assert calibration.mode_of(_entries(True, True, True, False, False)) == "advisory"
    assert calibration.mode_of(_entries(True, True, True, True, False)) == "blocking"
    assert calibration.mode_of(_entries(True, True, True, True, True)) == "blocking"


def test_only_the_last_five_count_so_the_mode_flips_and_flips_back() -> None:
    # Five matches then two misses: the window slides past the streak.
    on = _entries(True, True, True, True, True)
    assert calibration.mode_of(on) == "blocking"
    off = _entries(True, True, True, True, True, False, False)
    assert calibration.mode_of(off) == "advisory"  # last five: T T T F F = 3
    back = _entries(True, True, True, True, True, False, False, True, True, True, True)
    assert calibration.mode_of(back) == "blocking"  # last five: F T T T T = 4


def test_fewer_than_five_rated_jobs_need_four_matches_all_the_same() -> None:
    assert calibration.mode_of(_entries()) == "advisory"
    assert calibration.mode_of(_entries(True, True, True)) == "advisory"
    assert calibration.mode_of(_entries(True, True, True, True)) == "blocking"


def test_the_agreed_line_counts_matches_in_the_window() -> None:
    assert calibration.agreed_line(_entries()) == "no rated jobs yet"
    assert calibration.agreed_line(_entries(True, False, True)) == "critic agreed 2 of last 3"
    assert (
        calibration.agreed_line(_entries(True, True, True, True, False, False))
        == "critic agreed 3 of last 5"  # the sixth-from-last match is outside the window
    )


# --- record (10.3) --------------------------------------------------------------------------


def test_record_appends_the_job_with_critic_pass_at_7_and_phone_pass_at_6(tmp_path: Path) -> None:
    high = jobs.rate(_delivered(tmp_path, overall=7), 6, "fine", now=_clock())
    low = jobs.rate(_delivered(tmp_path, overall=6), 5, "meh", now=_clock())
    calibration.record(high, now=_clock())
    cal = calibration.record(low, now=_clock())
    assert calibration.path(tmp_path).is_file()
    assert cal == calibration.load(tmp_path)
    first, second = cal.entries
    assert first.job_id == high.id and first.critic_pass and first.phone_pass and first.matched
    assert first.critic_overall == 7 and first.rating == 6
    assert second.job_id == low.id and not second.critic_pass and not second.phone_pass
    assert second.matched  # both said no: the critic agreed


def test_record_replaces_the_entry_when_a_job_is_rated_again(tmp_path: Path) -> None:
    job = jobs.rate(_delivered(tmp_path, overall=8), 7, "", now=_clock())
    calibration.record(job, now=_clock())
    job = jobs.rate(job, 3, "on second viewing", now=_clock())
    cal = calibration.record(job, now=_clock())
    assert len(cal.entries) == 1
    assert cal.entries[0].rating == 3 and not cal.entries[0].matched


def test_an_unavailable_critic_never_matches(tmp_path: Path) -> None:
    job = jobs.rate(_delivered(tmp_path, overall=None), 4, "", now=_clock())
    (entry,) = calibration.record(job, now=_clock()).entries
    assert entry.critic_overall is None and not entry.critic_pass and not entry.matched


def test_record_refuses_an_unrated_job(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no rating"):
        calibration.record(_delivered(tmp_path, overall=8), now=_clock())


def test_mode_reads_the_file_and_an_absent_file_is_advisory(tmp_path: Path) -> None:
    assert calibration.mode(tmp_path) == "advisory"
    for _ in range(4):
        job = jobs.rate(_delivered(tmp_path, overall=8), 8, "", now=_clock())
        calibration.record(job, now=_clock())
    assert calibration.mode(tmp_path) == "blocking"


# --- the verdict (10.4) ---------------------------------------------------------------------


def _summary(overall: int | None, *, advisory: bool) -> CriticSummary:
    return CriticSummary(
        status="scored" if overall is not None else "unavailable",
        overall=overall,
        advisory=advisory,
        model="fake",
    )


def _rating(score: int) -> Rating:
    return Rating(score=score, note="", rated_at=T0)


@pytest.mark.parametrize(
    ("overall", "score", "expected"),
    [
        (3, None, "delivered"),  # advisory: the critic alone settles nothing
        (9, None, "delivered"),
        (3, 6, "passed"),  # the phone rating is the verdict
        (9, 5, "rejected"),
        (None, 6, "passed"),
    ],
)
def test_while_advisory_the_rating_alone_decides(
    overall: int | None, score: int | None, expected: str
) -> None:
    rating = _rating(score) if score is not None else None
    assert calibration.verdict(_summary(overall, advisory=True), rating) == expected


@pytest.mark.parametrize(
    ("overall", "score", "expected"),
    [
        (7, None, "passed"),  # the critic's pass line is 7
        (6, None, "rejected"),
        (7, 6, "passed"),
        (7, 5, "rejected"),  # the rating, when given, must also pass
        (6, 9, "rejected"),  # and the critic must
        (None, 6, "passed"),  # an unavailable critic cannot block: the rating decides
        (None, None, "delivered"),
    ],
)
def test_while_blocking_the_critic_and_the_rating_must_both_pass(
    overall: int | None, score: int | None, expected: str
) -> None:
    rating = _rating(score) if score is not None else None
    assert calibration.verdict(_summary(overall, advisory=False), rating) == expected


def test_no_critic_at_all_is_advisory() -> None:
    assert calibration.verdict(None, None) == "delivered"
    assert calibration.verdict(None, _rating(6)) == "passed"


def test_apply_settles_the_job_by_its_own_report_and_rating(tmp_path: Path) -> None:
    """The verdict is taken from job.json (the critic summary and the rating), so a
    re-rating moves a job between `passed` and `rejected` and a blocking critic settles
    an unrated job at delivery."""
    advisory = _delivered(tmp_path, overall=9, advisory=True)
    assert calibration.apply(advisory, now=_clock()).status == "delivered"
    rated = jobs.rate(advisory, 6, "", now=_clock())
    assert calibration.apply(rated, now=_clock()).status == "passed"
    rated = jobs.rate(rated, 5, "", now=_clock())
    assert calibration.apply(rated, now=_clock()).status == "rejected"
    blocking = _delivered(tmp_path, overall=7, advisory=False)
    assert calibration.apply(blocking, now=_clock()).status == "passed"
    log = blocking.log_path.read_text("utf-8")
    assert "delivered -> passed" in log and "critic 7/10" in log


def test_apply_refuses_a_job_that_is_not_delivered(tmp_path: Path) -> None:
    job = jobs.create(tmp_path, now=_clock())
    with pytest.raises(IllegalTransition):
        calibration.apply(job, now=_clock())
