"""`python -m shortsmith.gate`: the day-14 printout (decision 14.1; ticket 047).

The worth-continuing decision as one printout, nothing hidden and nothing cut:

- the three-of-five table: one row per gate job (named by id, or the five most recent
  jobs whose `out/meta.json` says `delivered` and carries a phone rating) with
  `delivered`, the T1-T13 result, the phone rating and the critic's overall, and the
  pass line "phone rating >= 6/10 on 3 of 5" evaluated (10.2, 14.1);
- per-component status for the full tier-1 list: the maintained table in
  `docs/components.md`, checked against `src/remotion/registry.json` (9.2);
- the cost distribution of every `passed` job with cash rows: min, median, p90, max,
  the proposed soft cap at p90 and a hard cap above it; under ten metered passing jobs
  it says "insufficient data (N of 10)" (11.3);
- the critic-versus-phone match count from `data/calibration.json` (10.2);
- the reference library count per category from `docs/reference/<category>/README.md`,
  three per category being the 10.3 seed (an entry is a `### <name> (NN s, N beats)`
  heading, the pack README's format; the anchors are the pack README's own entries).

Everything incomplete is listed by name at the end; the exit code is 0 only when the
table passes and that list is empty. The gate reads `out/meta.json` and the files
above, never `job.json`, `qa.json` or a plan: `meta.json` is the proof of the bar
(10.4, 035), so what the gate prints is what the job's own record says.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from shortsmith import config, jobs, meta
from shortsmith.contracts import CATEGORIES, TIER1_KINDS, Meta
from shortsmith.qa import calibration, critic
from shortsmith.qa.technical import CHECK_ORDER

GATE_JOBS = 5  # 14.1: five of Shubham's own recordings
GATE_PASS_MIN = 3  # 14.1: three of the five rate >= 6 on the phone
PHONE_PASS = calibration.PHONE_PASS  # 10.2 / 14.1: the phone's pass line, 6/10
METERED_MIN = 10  # 11.3: the caps come from the first ten metered passing jobs
SOFT_PERCENTILE = 0.9  # 11.3: soft cap ~ p90 of passing jobs
# 11.3 says "hard cap above it" and no more; this is the proposal's arithmetic, printed
# beside the number so the operator reviews the rule, not just the figure.
HARD_OVER_SOFT = 1.5
REFERENCE_MIN = 3  # 10.3(4): at least three reference shorts per category
COMPONENTS_MD = Path(__file__).resolve().parents[2] / "docs" / "components.md"
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "src" / "remotion" / "registry.json"
# The two presenter kinds are modes the PIP and the full-frame cut draw (3.2), not
# components of the registry, so the table carries no row for them.
PRESENTER_KINDS: frozenset[str] = frozenset({"presenter_full", "presenter_pip"})
REPORTED_CATEGORIES: tuple[str, ...] = tuple(c for c in CATEGORIES if c != "other")

_TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|(.*)\|\s*$")
_ENTRY = re.compile(r"^### .+\(\s*[\d.]+\s*s\s*,")


# --- the table (14.1) -----------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One gate job as its `meta.json` describes it. `found` is False for a named id
    with no `meta.json`; every other field is then empty."""

    job_id: str
    found: bool = False
    status: str = ""
    delivered: bool = False
    checks: int = 0
    failed_checks: tuple[str, ...] = ()
    rating: int | None = None
    critic_status: str = "none"  # scored | unavailable | none
    critic_overall: int | None = None

    @property
    def passes(self) -> bool:
        """The 14.1 line: delivered, and the phone says at least 6."""
        return self.delivered and self.rating is not None and self.rating >= PHONE_PASS

    @property
    def checks_text(self) -> str:
        if not self.found:
            return "-"
        if not self.checks:
            return "no checks"
        if not self.failed_checks:
            return f"all {self.checks} pass"
        return ", ".join(self.failed_checks) + " fail"

    @property
    def rating_text(self) -> str:
        return f"{self.rating}/10" if self.rating is not None else "unrated"

    @property
    def critic_text(self) -> str:
        if self.critic_status == "scored" and self.critic_overall is not None:
            return f"{self.critic_overall}/10"
        return self.critic_status


def row_of(m: Meta) -> Row:
    failed = tuple(c.name for c in m.technical if c.status != "pass")
    return Row(
        job_id=m.job_id,
        found=True,
        status=m.status,
        delivered=m.delivered,
        checks=len(m.technical),
        failed_checks=failed,
        rating=m.rating.score if m.rating is not None else None,
        critic_status=m.critic.status if m.critic is not None else "none",
        critic_overall=m.critic.overall if m.critic is not None else None,
    )


def load_meta(job_dir: Path) -> Meta | None:
    """The job's `out/meta.json`; None when it is missing or does not parse (one job
    never breaks the printout; a named job that is missing is listed by name)."""
    path = job_dir / "out" / meta.NAME
    if not path.is_file():
        return None
    try:
        return Meta.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def all_metas(data_dir: Path) -> list[Meta]:
    """Every job's `meta.json` under the data directory, newest first (the ids are
    time-prefixed, so the directory name sorts in submission order)."""
    root = data_dir / "jobs"
    if not root.is_dir():
        return []
    found: list[Meta] = []
    for d in sorted((d for d in root.iterdir() if jobs.JOB_ID.match(d.name)), reverse=True):
        m = load_meta(d)
        if m is not None:
            found.append(m)
    return found


def gate_rows(metas: Sequence[Meta], ids: Sequence[str] | None) -> list[Row]:
    """Named ids in the order given (a missing one is a not-found row), or the five most
    recent jobs that are `delivered` and rated."""
    if ids is not None:
        by_id = {m.job_id: m for m in metas}
        return [row_of(by_id[i]) if i in by_id else Row(job_id=i) for i in ids]
    picked = [m for m in metas if m.delivered and m.rating is not None][:GATE_JOBS]
    return [row_of(m) for m in picked]


# --- components (9.2) -----------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentStatus:
    name: str
    implemented: bool
    reason: str = ""  # the table's one-line note when incomplete


def tier1_table(path: Path) -> list[tuple[str, str, str]]:
    """The `docs/components.md` rows with tier `1`: (name, status, note)."""
    if not path.is_file():
        return []
    rows: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TABLE_ROW.match(line)
        if match is None:
            continue
        name, tier, status, rest = match.groups()
        if tier.strip() != "1":
            continue
        rows.append((name, status.strip(), rest.rsplit("|", 1)[-1].strip()))
    return rows


def load_registry(path: Path = REGISTRY_PATH) -> list[str]:
    """The renderer's component names (9.2), read the way `render.registry` reads them
    without importing the renderer."""
    return list(json.loads(path.read_text(encoding="utf-8"))["components"])


def component_status(
    table_path: Path = COMPONENTS_MD, *, registry: Sequence[str] | None = None
) -> list[ComponentStatus]:
    """The table's tier-1 rows judged against the registry: `implemented` only when the
    table says so and the registry exports the name. A tier-1 kind of the contracts
    with no row at all is incomplete too, so a stale table cannot hide a component."""
    exported = set(registry if registry is not None else load_registry())
    statuses: list[ComponentStatus] = []
    seen: set[str] = set()
    for name, status, note in tier1_table(table_path):
        seen.add(name)
        if status == "implemented" and name in exported:
            statuses.append(ComponentStatus(name, True))
        elif status == "implemented":
            statuses.append(
                ComponentStatus(
                    name, False, "docs/components.md says implemented but the registry "
                    "does not export it"
                )
            )  # fmt: skip
        else:
            statuses.append(ComponentStatus(name, False, note or status))
    for kind in TIER1_KINDS:
        if kind not in seen and kind not in PRESENTER_KINDS:
            statuses.append(
                ComponentStatus(kind, False, "no row in docs/components.md for this tier-1 kind")
            )
    return statuses


# --- the cost distribution (11.3) -----------------------------------------------------------


@dataclass(frozen=True)
class CostDistribution:
    """Cash per passing short over the metered `passed` jobs; the figures are None under
    `METERED_MIN` jobs, when there is not yet a distribution to propose caps from."""

    metered: int
    minimum: float | None = None
    median: float | None = None
    p90: float | None = None
    maximum: float | None = None
    soft: float | None = None
    hard: float | None = None

    @property
    def sufficient(self) -> bool:
        return self.metered >= METERED_MIN


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile of sorted `values`."""
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def distribution(values: Sequence[float]) -> CostDistribution:
    if len(values) < METERED_MIN:
        return CostDistribution(metered=len(values))
    p90 = percentile(values, SOFT_PERCENTILE)
    maximum = max(values)
    return CostDistribution(
        metered=len(values),
        minimum=min(values),
        median=float(statistics.median(values)),
        p90=p90,
        maximum=maximum,
        soft=p90,
        # Above p90, and never under the dearest short that passed the bar: a cap that
        # would have stopped a passing short is not a cap on waste (11.3).
        hard=max(p90 * HARD_OVER_SOFT, maximum),
    )


def cost_distribution(metas: Sequence[Meta]) -> CostDistribution:
    """Metered means cash rows: a subscription-only job (`inr` zero throughout) is not
    evidence for a cash cap."""
    return distribution([m.cash_inr for m in metas if m.status == "passed" and m.cash_inr > 0])


# --- calibration and the reference library (10.2, 10.3) --------------------------------------


@dataclass(frozen=True)
class CalibrationSummary:
    agreed_line: str
    matched: int  # over every rated job
    rated: int
    mode: calibration.Mode


def calibration_summary(data_dir: Path) -> CalibrationSummary:
    cal = calibration.load(data_dir)
    return CalibrationSummary(
        agreed_line=calibration.agreed_line(cal),
        matched=sum(1 for e in cal.entries if e.matched),
        rated=len(cal.entries),
        mode=calibration.mode_of(cal),
    )


@dataclass(frozen=True)
class ReferenceCount:
    category: str
    count: int

    @property
    def seeded(self) -> bool:
        return self.count >= REFERENCE_MIN


def entry_count(readme: Path) -> int:
    """Entries in a reference README: the `### <name> (NN s, N beats)` headings."""
    if not readme.is_file():
        return 0
    return sum(1 for line in readme.read_text(encoding="utf-8").splitlines() if _ENTRY.match(line))


def reference_counts(reference_dir: Path) -> list[ReferenceCount]:
    return [
        ReferenceCount(category, entry_count(reference_dir / category / "README.md"))
        for category in REPORTED_CATEGORIES
    ]


# --- the report -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    data_dir: Path
    rows: list[Row]
    components: list[ComponentStatus]
    costs: CostDistribution
    calibration: CalibrationSummary
    references: list[ReferenceCount]
    anchors: int
    pack_version: str | None

    @property
    def passing(self) -> int:
        return sum(1 for r in self.rows if r.passes)

    @property
    def table_passes(self) -> bool:
        """Three of five, and five there are: fewer rows cannot make the line."""
        return len(self.rows) >= GATE_JOBS and self.passing >= GATE_PASS_MIN

    @property
    def incomplete(self) -> list[str]:
        items: list[str] = []
        if len(self.rows) < GATE_JOBS:
            items.append(f"gate jobs: {len(self.rows)} of {GATE_JOBS} found")
        for row in self.rows:
            if not row.found:
                items.append(f"job {row.job_id}: no out/{meta.NAME}")
                continue
            if row.failed_checks:
                items.append(f"job {row.job_id}: {', '.join(row.failed_checks)} failed")
            elif not row.delivered:
                items.append(f"job {row.job_id}: not delivered")
            if row.rating is None:
                items.append(f"job {row.job_id}: unrated")
        for c in self.components:
            if not c.implemented:
                items.append(f"component {c.name}: {c.reason}")
        if not self.costs.sufficient:
            items.append(
                f"cost distribution: insufficient data ({self.costs.metered} of {METERED_MIN} "
                "metered passing jobs)"
            )
        for ref in self.references:
            if not ref.seeded:
                items.append(
                    f"reference library: {ref.category} has {ref.count} of {REFERENCE_MIN}"
                )
        return items

    @property
    def exit_code(self) -> int:
        return 0 if self.table_passes and not self.incomplete else 1


def collect(
    data_dir: Path,
    *,
    ids: Sequence[str] | None = None,
    components_path: Path = COMPONENTS_MD,
    reference_dir: Path = critic.REFERENCE_DIR,
    registry: Sequence[str] | None = None,
) -> Report:
    metas = all_metas(data_dir)
    readme = reference_dir / "README.md"
    return Report(
        data_dir=data_dir,
        rows=gate_rows(metas, ids),
        components=component_status(components_path, registry=registry),
        costs=cost_distribution(metas),
        calibration=calibration_summary(data_dir),
        references=reference_counts(reference_dir),
        anchors=entry_count(readme),
        pack_version=meta.pack_version(readme),
    )


def _inr(value: float | None) -> str:
    return f"INR {value:.2f}" if value is not None else "-"


def format_report(report: Report) -> str:
    out: list[str] = []
    out.append(f"Shortsmith day-14 gate (decision 14.1) - data dir {report.data_dir}")
    out.append("")
    out.append(
        f"Gate jobs ({GATE_PASS_MIN} of {GATE_JOBS} must rate >= {PHONE_PASS}/10 on the phone)"
    )
    if not report.rows:
        out.append("  no gate jobs: no delivered, rated job has an out/meta.json")
    else:
        width = max(len(r.job_id) for r in report.rows)
        out.append(
            f"  {'job':<{width}}  {'delivered':<9}  {'T1-T' + str(len(CHECK_ORDER)):<14}  "
            f"{'phone':<7}  critic"
        )
        for r in report.rows:
            delivered = "yes" if r.delivered else ("no" if r.found else "missing")
            out.append(
                f"  {r.job_id:<{width}}  {delivered:<9}  {r.checks_text:<14}  "
                f"{r.rating_text:<7}  {r.critic_text}"
            )
    verdict = "PASS" if report.table_passes else "FAIL"
    out.append(
        f'  Pass line ">= {PHONE_PASS}/10 on {GATE_PASS_MIN} of {GATE_JOBS}": '
        f"{report.passing} of {len(report.rows)} -> {verdict}"
    )
    out.append("")
    out.append("Tier-1 components (docs/components.md against src/remotion/registry.json)")
    name_width = max((len(c.name) for c in report.components), default=4)
    for c in report.components:
        status = "implemented" if c.implemented else "incomplete "
        line = f"  {c.name:<{name_width}}  {status}"
        out.append(line + (f"  {c.reason}" if c.reason else ""))
    out.append("")
    out.append(
        f"Cost distribution (passed jobs with cash rows; soft cap = p{int(SOFT_PERCENTILE * 100)}, "
        f"hard cap = {HARD_OVER_SOFT:g} x soft and never under the max)"
    )
    costs = report.costs
    if not costs.sufficient:
        out.append(f"  insufficient data ({costs.metered} of {METERED_MIN})")
    else:
        out.append(
            f"  {costs.metered} metered passing jobs: min {_inr(costs.minimum)}, "
            f"median {_inr(costs.median)}, p90 {_inr(costs.p90)}, max {_inr(costs.maximum)}"
        )
        out.append(f"  proposed soft cap {_inr(costs.soft)}, proposed hard cap {_inr(costs.hard)}")
    out.append("")
    out.append("Critic versus phone (calibration.json)")
    cal = report.calibration
    out.append(f"  {cal.agreed_line}; {cal.matched} of {cal.rated} rated jobs overall; {cal.mode}")
    out.append("")
    pack = report.pack_version if report.pack_version is not None else "unversioned"
    out.append(
        f"Reference library (docs/reference, pack version {pack}; >= {REFERENCE_MIN} per category)"
    )
    cat_width = max(len(c.category) for c in report.references) if report.references else 7
    cat_width = max(cat_width, len("anchors"))
    out.append(f"  {'anchors':<{cat_width}}  {report.anchors}  (the approved shorts)")
    for ref in report.references:
        mark = "" if ref.seeded else f"  (short of {REFERENCE_MIN})"
        out.append(f"  {ref.category:<{cat_width}}  {ref.count}{mark}")
    out.append("")
    incomplete = report.incomplete
    if incomplete:
        out.append(f"Incomplete ({len(incomplete)})")
        out.extend(f"  - {item}" for item in incomplete)
    else:
        out.append("Incomplete: nothing")
    out.append("")
    out.append(f"Result: {'PASS' if report.exit_code == 0 else 'FAIL'} (exit {report.exit_code})")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shortsmith.gate",
        description="Print the day-14 gate: the three-of-five table, component status, "
        "cost distribution with proposed caps, critic-versus-phone match count and the "
        "reference library counts, naming everything incomplete (decision 14.1).",
    )
    parser.add_argument(
        "ids",
        nargs="*",
        metavar="JOB_ID",
        help="the gate jobs by id; default: the five most recent delivered, rated jobs",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="the data directory (default: SHORTSMITH_DATA_DIR from the environment)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    ids: list[str] = list(args.ids)
    bad = [i for i in ids if not jobs.JOB_ID.match(i)]
    if bad:
        print(f"gate: not a job id: {', '.join(bad)}", file=sys.stderr)
        return 2
    data_dir: Path = (
        args.data_dir if args.data_dir is not None else config.load().shortsmith_data_dir
    )
    report = collect(data_dir, ids=ids or None)
    print(format_report(report))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
