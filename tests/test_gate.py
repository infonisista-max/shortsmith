"""`python -m shortsmith.gate` (ticket 047; decision 14.1): the day-14 printout from
the gate jobs' `out/meta.json`, the component table, the passing jobs' ledgers, the
calibration file and the reference READMEs, with everything incomplete named."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortsmith import gate, render
from shortsmith.contracts import (
    CATEGORIES,
    CRITIC_LINES,
    CostRow,
    CriticLine,
    CriticReport,
    Meta,
    Rating,
    TechnicalResult,
)
from shortsmith.qa import calibration
from shortsmith.qa.calibration import Calibration, Entry
from shortsmith.qa.technical import CHECK_ORDER

T0 = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


def _job_id(n: int) -> str:
    """Time-prefixed like `jobs.new_job_id`, so a higher `n` is a more recent job."""
    return f"20260926-{n:06d}-{n:06x}"


def _critic(overall: int | None) -> CriticReport:
    if overall is None:
        return CriticReport(status="unavailable", model="fake", notes=["timed out"])
    lines = [
        CriticLine(name=n, label=label, score=overall, reason="ok") for n, label in CRITIC_LINES
    ]
    return CriticReport(lines=lines, overall=overall, model="fake")


def _meta(
    n: int,
    *,
    delivered: bool = True,
    rating: int | None = 8,
    overall: int | None = 7,
    failing: tuple[str, ...] = (),
    status: str | None = None,
    cash_inr: float = 0.0,
) -> Meta:
    checks = [
        TechnicalResult(name=name, status="fail" if name in failing else "pass", detail="")
        for name in CHECK_ORDER
    ]
    if status is None:
        status = "delivered" if rating is None else ("passed" if rating >= 6 else "rejected")
    ledger = (
        [CostRow(step="planning", provider="planner", model="m", units={}, inr=cash_inr, at=T0)]
        if cash_inr
        else []
    )
    return Meta(
        job_id=_job_id(n),
        status=status,
        delivered=delivered and not failing,
        style="explainer",
        technical=checks,
        technical_passed=not failing,
        critic=_critic(overall),
        rating=Rating(score=rating, rated_at=T0) if rating is not None else None,
        ledger=ledger,
        cash_inr=cash_inr,
        written_at=T0,
    )


def _write(data_dir: Path, m: Meta) -> Path:
    out = data_dir / "jobs" / m.job_id / "out"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "meta.json"
    path.write_text(m.model_dump_json(indent=2), encoding="utf-8")
    return path


def _components(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    lines = [
        "# Renderer components",
        "",
        "| component | tier | status | explainer smoke | hitech smoke | note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, tier, status, note in rows:
        lines.append(f"| `{name}` | {tier} | {status} | b01 | b01 | {note} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _reference_dir(root: Path, counts: dict[str, int], *, anchors: int = 2) -> Path:
    ref = root / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    pack = ["# Reference pack", "", "Pack version: 3", "", "## The two references", ""]
    for i in range(anchors):
        pack += [f"### Anchor_{i}.mp4 (60.0 s, 26 beats)", "", "What it does well:", "- x", ""]
    pack += ["## Frames", "", "### NKB", "", "| # | File |", "|---|---|", ""]
    (ref / "README.md").write_text("\n".join(pack), encoding="utf-8")
    for category, count in counts.items():
        (ref / category).mkdir(exist_ok=True)
        text = [f"# {category}", "", "## The references", ""]
        for i in range(count):
            text += [f"### {category}_{i}.mp4 (58.0 s, 24 beats)", "", "- MEASURED cuts", ""]
        (ref / category / "README.md").write_text("\n".join(text), encoding="utf-8")
    return ref


@dataclass(frozen=True)
class World:
    data_dir: Path
    components_path: Path
    reference_dir: Path
    registry: list[str]


def _complete_world(tmp_path: Path) -> World:
    """Everything green: five passing gate jobs, ten metered passing jobs, a table row
    for every tier-1 kind with the registry exporting each (the three map animations
    of 028 included), three references in every category."""
    registry = sorted(set(render.registry()) | {"pin_drop", "route_arrow", "object_path"})
    all_implemented = [(name, "1", "implemented", "") for name in registry]
    data_dir = tmp_path / "data"
    for n in range(1, 6):
        _write(data_dir, _meta(n, rating=8, cash_inr=10.0 * n))
    for n in range(6, 16):
        _write(data_dir, _meta(n, rating=7, cash_inr=10.0 * (n - 5)))
    calibration.save(
        data_dir,
        Calibration(
            entries=[
                Entry(
                    job_id=_job_id(n), critic_overall=7, critic_pass=True, rating=8,
                    phone_pass=True, matched=True, at=T0,
                )
                for n in range(1, 6)
            ]
        ),
    )  # fmt: skip
    counts = {c: 3 for c in CATEGORIES if c != "other"}
    return World(
        data_dir=data_dir,
        components_path=_components(tmp_path / "components.md", all_implemented),
        reference_dir=_reference_dir(tmp_path, counts),
        registry=registry,
    )


# --- the table (14.1) -----------------------------------------------------------------------


def test_three_of_five_passes_the_table(tmp_path: Path) -> None:
    for n, rating in enumerate((8, 6, 4, 7, 5), start=1):
        _write(tmp_path, _meta(n, rating=rating))
    report = gate.collect(tmp_path)
    assert [r.job_id for r in report.rows] == [_job_id(n) for n in (5, 4, 3, 2, 1)]
    assert report.passing == 3 and report.table_passes
    text = gate.format_report(report)
    assert '">= 6/10 on 3 of 5": 3 of 5 -> PASS' in text


def test_two_of_five_fails_the_table_and_the_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for n, rating in enumerate((8, 6, 4, 3, 5), start=1):
        _write(tmp_path, _meta(n, rating=rating))
    assert gate.main(["--data-dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert '">= 6/10 on 3 of 5": 2 of 5 -> FAIL' in out
    assert "Result: FAIL" in out


def test_a_row_shows_delivered_the_failing_checks_the_rating_and_the_critic(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _meta(1, rating=8))
    _write(tmp_path, _meta(2, rating=9, failing=("T6", "T9")))
    _write(tmp_path, _meta(3, rating=None, overall=None))
    report = gate.collect(tmp_path, ids=[_job_id(1), _job_id(2), _job_id(3)])
    clean, failed, bare = report.rows
    assert clean.delivered and clean.failed_checks == () and clean.passes
    assert not failed.delivered and failed.failed_checks == ("T6", "T9") and not failed.passes
    assert bare.rating is None and bare.critic_overall is None and not bare.passes
    text = gate.format_report(report)
    assert "T6, T9 fail" in text and "all 13 pass" in text
    assert "unrated" in text and "unavailable" in text
    assert f"job {_job_id(2)}: T6, T9 failed" in report.incomplete
    assert f"job {_job_id(3)}: unrated" in report.incomplete
    assert "gate jobs: 3 of 5 found" in report.incomplete


def test_the_five_most_recent_delivered_rated_jobs_are_picked(tmp_path: Path) -> None:
    for n in range(1, 8):
        _write(tmp_path, _meta(n, rating=7))
    _write(tmp_path, _meta(8, rating=None))  # unrated: not a gate job
    _write(tmp_path, _meta(9, rating=8, failing=("T2",)))  # not delivered: not a gate job
    report = gate.collect(tmp_path)
    assert [r.job_id for r in report.rows] == [_job_id(n) for n in (7, 6, 5, 4, 3)]


def test_a_named_job_without_meta_json_is_listed_by_name(tmp_path: Path) -> None:
    _write(tmp_path, _meta(1))
    report = gate.collect(tmp_path, ids=[_job_id(1), _job_id(2)])
    missing = report.rows[1]
    assert not missing.found and not missing.passes
    assert f"job {_job_id(2)}: no out/meta.json" in report.incomplete


def test_an_empty_data_dir_reports_no_gate_jobs(tmp_path: Path) -> None:
    report = gate.collect(tmp_path)
    assert report.rows == [] and not report.table_passes
    assert "gate jobs: 0 of 5 found" in report.incomplete
    assert "no gate jobs" in gate.format_report(report)


# --- components (9.2) -----------------------------------------------------------------------


def test_component_status_comes_from_the_table_checked_against_the_registry(
    tmp_path: Path,
) -> None:
    table = _components(
        tmp_path / "components.md",
        [
            ("captions", "1", "implemented", "five pages"),
            ("pin_drop", "1", "incomplete", "ticket 028: not in the registry yet"),
            ("ghost", "1", "implemented", "claimed, never exported"),
            ("whip", "transition", "implemented", "not tier 1"),
        ],
    )
    statuses = gate.component_status(table, registry=["captions", "whip"])
    by_name = {s.name: s for s in statuses}
    assert by_name["captions"].implemented and by_name["captions"].reason == ""
    assert not by_name["pin_drop"].implemented
    assert by_name["pin_drop"].reason == "ticket 028: not in the registry yet"
    assert not by_name["ghost"].implemented and "registry" in by_name["ghost"].reason
    assert "whip" not in by_name


def test_a_tier1_kind_with_no_table_row_is_incomplete(tmp_path: Path) -> None:
    table = _components(tmp_path / "components.md", [("captions", "1", "implemented", "")])
    by_name = {s.name: s for s in gate.component_status(table, registry=["captions", "map"])}
    assert not by_name["map"].implemented and "docs/components.md" in by_name["map"].reason
    assert "presenter_full" not in by_name and "presenter_pip" not in by_name


def test_the_repo_table_lists_every_tier1_component_as_implemented(tmp_path: Path) -> None:
    """028 landed the three map animations, the last tier-1 rows the table owed."""
    report = gate.collect(tmp_path)
    by_name = {s.name: s for s in report.components}
    assert {"pin_drop", "route_arrow", "object_path", "map", "captions"} <= set(by_name)
    assert all(s.implemented for s in report.components), [
        f"{s.name}: {s.reason}" for s in report.components if not s.implemented
    ]
    assert not [item for item in report.incomplete if item.startswith("component ")]


# --- the cost distribution (11.3) -----------------------------------------------------------


def test_fewer_than_ten_metered_passing_jobs_is_insufficient_data(tmp_path: Path) -> None:
    for n in range(1, 6):
        _write(tmp_path, _meta(n, rating=8, cash_inr=20.0))
    _write(tmp_path, _meta(6, rating=8, cash_inr=0.0))  # subscription only: not metered
    _write(tmp_path, _meta(7, rating=4, cash_inr=50.0))  # rejected: not a passing job
    report = gate.collect(tmp_path)
    assert report.costs.metered == 5 and not report.costs.sufficient
    assert "insufficient data (5 of 10)" in gate.format_report(report)
    assert "cost distribution: insufficient data (5 of 10 metered passing jobs)" in (
        report.incomplete
    )


def test_ten_metered_passing_jobs_give_the_distribution_and_the_proposed_caps(
    tmp_path: Path,
) -> None:
    for n in range(1, 11):
        _write(tmp_path, _meta(n, rating=7, cash_inr=10.0 * n))
    costs = gate.collect(tmp_path).costs
    assert costs.metered == 10 and costs.sufficient
    assert (costs.minimum, costs.median, costs.p90, costs.maximum) == (10.0, 55.0, 90.0, 100.0)
    assert costs.soft == 90.0 and costs.hard == 135.0  # hard: 1.5 x p90, never under the max
    text = gate.format_report(gate.collect(tmp_path))
    assert "min INR 10.00, median INR 55.00, p90 INR 90.00, max INR 100.00" in text
    assert "soft cap INR 90.00" in text and "hard cap INR 135.00" in text


def test_the_hard_cap_never_sits_under_the_dearest_passing_job() -> None:
    values = tuple(float(v) for v in (10, 10, 10, 10, 10, 10, 10, 10, 10, 400))
    costs = gate.distribution(values)
    assert costs.p90 == 10.0 and costs.soft == 10.0 and costs.hard == 400.0


# --- calibration and the reference library (10.2, 10.3) --------------------------------------


def test_the_match_count_and_the_mode_come_from_calibration_json(tmp_path: Path) -> None:
    entries = [
        Entry(
            job_id=_job_id(n), critic_overall=7, critic_pass=True, rating=8 if m else 4,
            phone_pass=m, matched=m, at=T0,
        )
        for n, m in enumerate((True, False, True, True, True, True, False), start=1)
    ]  # fmt: skip
    calibration.save(tmp_path, Calibration(entries=entries))
    report = gate.collect(tmp_path)
    assert report.calibration.agreed_line == "critic agreed 4 of last 5"
    assert (report.calibration.matched, report.calibration.rated) == (5, 7)
    assert report.calibration.mode == "blocking"
    assert "critic agreed 4 of last 5; 5 of 7 rated jobs overall; blocking" in (
        gate.format_report(report)
    )


def test_no_calibration_file_reads_as_no_rated_jobs(tmp_path: Path) -> None:
    report = gate.collect(tmp_path)
    assert report.calibration.agreed_line == calibration.NO_RATED_JOBS
    assert report.calibration.rated == 0 and report.calibration.mode == "advisory"


def test_reference_counts_per_category_with_the_short_ones_named(tmp_path: Path) -> None:
    ref = _reference_dir(tmp_path, {"history": 3, "finance": 1})
    report = gate.collect(tmp_path / "data", reference_dir=ref)
    counts = {c.category: c.count for c in report.references}
    assert counts["history"] == 3 and counts["finance"] == 1 and counts["science"] == 0
    assert "other" not in counts
    assert report.anchors == 2 and report.pack_version == "3"
    assert "reference library: finance has 1 of 3" in report.incomplete
    assert "reference library: science has 0 of 3" in report.incomplete
    assert not any(line.startswith("reference library: history") for line in report.incomplete)
    text = gate.format_report(report)
    assert "pack version 3" in text
    assert "anchors" in text and "history" in text and "finance" in text


def test_the_repo_pack_readme_counts_its_two_anchors(tmp_path: Path) -> None:
    report = gate.collect(tmp_path)
    assert report.anchors == 2 and report.pack_version == "1"


# --- the whole printout ----------------------------------------------------------------------


def test_exit_code_is_zero_only_when_the_table_passes_and_nothing_is_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = _complete_world(tmp_path)
    report = gate.collect(
        world.data_dir,
        components_path=world.components_path,
        reference_dir=world.reference_dir,
        registry=world.registry,
    )
    assert report.table_passes and report.incomplete == []
    assert report.exit_code == 0
    text = gate.format_report(report)
    assert "Incomplete: nothing" in text and "Result: PASS" in text
    # One incomplete item flips the exit code even with the table passing.
    short = _reference_dir(tmp_path / "again", {c: 3 for c in CATEGORIES if c != "other"})
    (short / "history" / "README.md").write_text("# history\n", encoding="utf-8")
    again = gate.collect(
        world.data_dir,
        components_path=world.components_path,
        reference_dir=short,
        registry=world.registry,
    )
    assert again.table_passes and again.incomplete == ["reference library: history has 0 of 3"]
    assert again.exit_code == 1


def test_main_prints_every_section_and_names_the_incomplete_items(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for n, rating in enumerate((8, 6, 7, 7, 5), start=1):
        _write(tmp_path, _meta(n, rating=rating))
    code = gate.main(["--data-dir", str(tmp_path), _job_id(1), _job_id(2), _job_id(3)])
    out = capsys.readouterr().out
    assert code == 1
    for heading in (
        "Gate jobs", "Tier-1 components", "Cost distribution", "Critic versus phone",
        "Reference library", "Incomplete (",
    ):  # fmt: skip
        assert heading in out, heading
    assert "gate jobs: 3 of 5 found" in out
    assert "component pin_drop:" not in out  # 028: the map animations are implemented
    assert "Result: FAIL" in out


def test_main_rejects_a_malformed_job_id(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["not-a-job-id"]) == 2
    assert "job id" in capsys.readouterr().err
