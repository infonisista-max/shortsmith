"""The cost ledger (PRD `ledger`; decisions 5.6, 8.3, 11.3).

Every paid adapter reports units only (`{"audio_minutes": 2}`, `{"images": 1}`,
`{"input_tokens": 1200, "output_tokens": 300}`, `{"queries": 1}`); the ledger prices
them from the operator-edited prices file (`PRICES_FILE`, default `prices.yaml`,
example in `prices.example.yaml`) and appends one `CostRow` to `job.json.cost`. Token
prices are INR per 1,000 tokens; every other unit is priced per unit. A price the file
does not carry is a `LedgerError`, never a silent zero.

Caps (11.3): only rows with `inr > 0` count. `check_before_call` raises
`BudgetExceeded` naming the step when the cash total plus the adapter's estimate would
pass the hard cap, so the paid call never happens; the pipeline turns that into a
`failed` job with "budget exceeded at step X" and the rows so far on the page. Passing
the soft cap sets `job.json.over_soft_cap` and nothing else: no step is ever skipped
or degraded for cost. Both per-job caps are unset until the operator derives them from
the first ten metered passing jobs; the daily guard (`BUDGET_INR_PER_DAY`) is read
through `cash_spent_today`, which ticket 044 wires to the upload form.

Subscription calls (8.3, `PLANNER=claude_code`) are rows with `inr` zero, the tokens
in `tokens_estimated`, and `inr_equivalent` valued at the file's `api_equivalent` rate
for the side-by-side display on the page; they never enter the cash total.

Startup (`from_settings`): the providers the config puts in use must be priced, so a
missing file or a missing price for one of them is a plain error naming it. With every
fake selected nothing is priced and no file is needed, which is how tests and smoke run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import RootModel, ValidationError

from shortsmith import jobs
from shortsmith.config import Settings
from shortsmith.jobs import CostRow, Job, JobRecord

EXAMPLE_FILE = "prices.example.yaml"
TOKENS_PER_PRICE = 1000  # token prices are per 1k tokens
TOKEN_SUFFIX = "_tokens"
API_EQUIVALENT = "api_equivalent"  # the display-only rate for subscription rows
SUBSCRIPTION_PROVIDERS: frozenset[str] = frozenset({"claude_code"})
# What each priced provider must carry; a provider in use without one of these fails
# startup. `judge` and `search` join `providers_in_use` with ticket 017.
REQUIRED_UNITS: Mapping[str, tuple[str, ...]] = {
    "groq": ("audio_minutes",),
    "gemini": ("images",),
    "judge": ("input_tokens", "output_tokens"),
    # 015: prompt-cache writes and reads are priced apart from fresh input tokens.
    "planner": (
        "input_tokens",
        "cache_write_input_tokens",
        "cache_read_input_tokens",
        "output_tokens",
    ),
    "search": ("queries",),
    API_EQUIVALENT: ("input_tokens", "output_tokens"),
}

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LedgerError(Exception):
    """A missing prices file or a missing price: a config problem, reported plainly."""


class BudgetExceeded(Exception):
    """The next paid call would pass the hard cap; raised before the call (11.3)."""

    def __init__(self, step: str, *, spent_inr: float, estimated_inr: float, hard_inr: float):
        super().__init__(
            f"budget exceeded at step {step}: INR {spent_inr:.2f} spent + "
            f"INR {estimated_inr:.2f} estimated > hard cap INR {hard_inr:.2f}"
        )
        self.step = step
        self.spent_inr = spent_inr
        self.estimated_inr = estimated_inr
        self.hard_inr = hard_inr


class Prices(RootModel[dict[str, dict[str, float]]]):
    """provider -> unit -> INR per unit (per 1k for `*_tokens`)."""

    @property
    def providers(self) -> dict[str, dict[str, float]]:
        return self.root

    def rate(self, provider: str, unit: str) -> float:
        units = self.root.get(provider)
        if units is None:
            raise LedgerError(f"no prices for provider {provider!r} in the prices file")
        if unit not in units:
            raise LedgerError(f"no price for {provider}.{unit} in the prices file")
        return units[unit]

    def value(self, provider: str, units: Mapping[str, float]) -> float:
        total = 0.0
        for unit, quantity in units.items():
            per = TOKENS_PER_PRICE if unit.endswith(TOKEN_SUFFIX) else 1
            total += quantity * self.rate(provider, unit) / per
        return total


@dataclass(frozen=True)
class Caps:
    per_job: float | None  # soft: flags only
    hard: float | None  # hard: fails the job before the next paid call
    per_day: float


def load_prices(path: Path) -> Prices:
    if not path.is_file():
        raise LedgerError(
            f"prices file {path} is missing: copy {EXAMPLE_FILE} to {path.name} and edit it"
        )
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Prices.model_validate(loaded if loaded is not None else {})
    except (yaml.YAMLError, ValidationError) as exc:
        raise LedgerError(f"prices file {path} is not provider -> unit -> INR: {exc}") from exc


def providers_in_use(settings: Settings) -> frozenset[str]:
    """The providers the config will bill: each must be priced at startup."""
    used: set[str] = set()
    if settings.planner == "api":
        used.add("planner")
    elif settings.planner == "claude_code":
        used.add(API_EQUIVALENT)
    if settings.image_gen == "gemini":
        used.add("gemini")
    if settings.transcriber == "groq":
        used.add("groq")
    return frozenset(used)


def from_settings(settings: Settings, *, clock: Clock = _utc_now) -> Ledger:
    """The app's ledger: the file is required, and checked, only for providers in use."""
    used = providers_in_use(settings)
    path = settings.prices_file
    prices = load_prices(path) if used or path.is_file() else Prices({})
    for provider in sorted(used):
        for unit in REQUIRED_UNITS.get(provider, ()):
            prices.rate(provider, unit)  # raises the LedgerError naming the gap
    caps = Caps(
        per_job=settings.budget_inr_per_job,
        hard=settings.budget_inr_hard,
        per_day=settings.budget_inr_per_day,
    )
    return Ledger(prices, caps, clock=clock)


def cash_total(record: JobRecord) -> float:
    """What counts toward the caps: cash rows only (11.3)."""
    return sum(row.inr for row in record.cost if row.inr > 0)


def tokens_total(record: JobRecord) -> int:
    return sum(row.tokens_estimated for row in record.cost)


def equivalent_total(record: JobRecord) -> float:
    """The display-only value of the subscription rows at the api-equivalent rate."""
    return sum(row.inr_equivalent for row in record.cost)


class Ledger:
    def __init__(self, prices: Prices, caps: Caps, *, clock: Clock = _utc_now) -> None:
        self.prices = prices
        self.caps = caps
        self._clock = clock

    def estimate(self, provider: str, units: Mapping[str, float]) -> float:
        """INR the units would cost, for `check_before_call`; nothing is written."""
        return self.prices.value(provider, units)

    def record(
        self, job: Job, step: str, provider: str, model: str, units: Mapping[str, float]
    ) -> CostRow:
        """Price one call and append it to job.json; sets `over_soft_cap` when the cash
        total passes the soft cap. The price is resolved before anything is written."""
        quantities = {unit: float(q) for unit, q in units.items()}
        if provider in SUBSCRIPTION_PROVIDERS:
            row = CostRow(
                step=step,
                provider=provider,
                model=model,
                units=quantities,
                inr=0.0,
                tokens_estimated=round(
                    sum(q for unit, q in quantities.items() if unit.endswith(TOKEN_SUFFIX))
                ),
                inr_equivalent=self.prices.value(API_EQUIVALENT, quantities),
                at=self._clock(),
            )
        else:
            row = CostRow(
                step=step,
                provider=provider,
                model=model,
                units=quantities,
                inr=self.prices.value(provider, quantities),
                at=self._clock(),
            )
        current = jobs.load(job.path).record
        spent = cash_total(current) + max(row.inr, 0.0)
        over = self.caps.per_job is not None and spent > self.caps.per_job
        jobs.amend(job, cost=[*current.cost, row], over_soft_cap=current.over_soft_cap or over)
        return row

    def check_before_call(self, job: Job, step: str, estimated_inr: float) -> None:
        """Raise `BudgetExceeded` when the cash so far plus the estimate passes the hard
        cap; the adapter calls this first so the paid call never happens."""
        if self.caps.hard is None:
            return
        spent = cash_total(jobs.load(job.path).record)
        if spent + estimated_inr > self.caps.hard:
            raise BudgetExceeded(
                step, spent_inr=spent, estimated_inr=estimated_inr, hard_inr=self.caps.hard
            )

    def cash_spent_today(self, data_dir: Path, now: datetime) -> float:
        """Cash rows recorded since midnight IST across every job (11.3 daily guard)."""
        since = jobs.midnight_ist(now)
        total = 0.0
        for job in jobs.iter_jobs(data_dir):
            total += sum(row.inr for row in job.record.cost if row.inr > 0 and row.at >= since)
        return total
