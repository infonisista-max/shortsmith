"""ledger: one row per paid call priced from the operator's prices file (5.6), the
soft cap that only flags, the hard cap that stops the job before the next paid call,
subscription tokens valued for display only (8.3, 11.3), and the daily sum 044 will
close the form on. Boundary tests at the exact values in the decisions (12.2)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import jobs, ledger
from shortsmith.config import Settings
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, LedgerError, Prices

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "shortsmith"
T0 = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)  # 17:30 IST

PRICES = Prices(
    {
        "groq": {"audio_minutes": 0.5},
        "gemini": {"images": 3.0},
        "judge": {"input_tokens": 0.25, "output_tokens": 1.25},
        "planner": {"input_tokens": 0.25, "output_tokens": 1.25},
        "search": {"queries": 0.2},
        "api_equivalent": {"input_tokens": 0.25, "output_tokens": 1.25},
    }
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        shortsmith_data_dir=tmp_path / "data",
        **overrides,  # pyright: ignore[reportArgumentType]
    )


def _ledger(
    per_job: float | None = None, hard: float | None = None, per_day: float = 500.0
) -> Ledger:
    return Ledger(PRICES, Caps(per_job=per_job, hard=hard, per_day=per_day), clock=lambda: T0)


def _job(tmp_path: Path, name: str = "data") -> jobs.Job:
    return jobs.create(tmp_path / name, now=lambda: T0)


# --- settings ---------------------------------------------------------------------


def test_per_job_caps_are_disabled_until_the_operator_sets_them(tmp_path: Path) -> None:
    """11.3: the caps are derived from the first metered passing jobs, so nothing is
    invented here; only the daily guard has a number."""
    settings = _settings(tmp_path)
    assert settings.budget_inr_per_job is None
    assert settings.budget_inr_hard is None
    assert settings.budget_inr_per_day == 500.0
    assert settings.prices_file == Path("prices.yaml")


def test_env_example_documents_the_caps_and_the_p90_rule() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("PRICES_FILE", "BUDGET_INR_PER_JOB", "BUDGET_INR_HARD", "BUDGET_INR_PER_DAY"):
        assert key in text
    assert "p90" in text and "10" in text


# --- prices file ------------------------------------------------------------------


def test_prices_example_covers_every_provider_and_unit() -> None:
    prices = ledger.load_prices(ROOT / "prices.example.yaml")
    for provider, units in ledger.REQUIRED_UNITS.items():
        assert provider in prices.providers, provider
        for unit in units:
            assert unit in prices.providers[provider], f"{provider}.{unit}"


def test_prices_yaml_is_operator_edited_and_git_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "prices.yaml" in ignored


def test_missing_file_is_a_startup_error_only_when_a_paid_provider_is_in_use(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "prices.yaml"
    # Every fake selected, no keys: nothing is priced, so no file is needed.
    quiet = ledger.from_settings(_settings(tmp_path, planner="fake", prices_file=missing))
    assert quiet.prices.providers == {}
    with pytest.raises(LedgerError, match=r"prices\.yaml.*prices\.example\.yaml"):
        ledger.from_settings(_settings(tmp_path, planner="api", prices_file=missing))


def test_missing_price_for_a_provider_in_use_is_a_startup_error(tmp_path: Path) -> None:
    path = tmp_path / "prices.yaml"
    path.write_text("groq:\n  audio_minutes: 0.5\n", encoding="utf-8")
    with pytest.raises(LedgerError, match=r"planner"):
        ledger.from_settings(_settings(tmp_path, planner="api", prices_file=path))
    path.write_text("planner:\n  input_tokens: 0.25\n", encoding="utf-8")
    with pytest.raises(LedgerError, match=r"planner\.output_tokens"):
        ledger.from_settings(_settings(tmp_path, planner="api", prices_file=path))


def test_providers_in_use_follow_the_config(tmp_path: Path) -> None:
    assert ledger.providers_in_use(_settings(tmp_path, planner="fake")) == frozenset()
    assert ledger.providers_in_use(_settings(tmp_path, planner="api")) == {"planner"}
    assert ledger.providers_in_use(_settings(tmp_path, planner="claude_code")) == {
        "api_equivalent"
    }
    full = _settings(
        tmp_path, planner="api", image_gen="gemini", groq_api_key="k"  # noqa: S106 - test value
    )
    assert ledger.providers_in_use(full) == {"planner", "gemini", "groq"}


def test_from_settings_reads_the_file_and_the_caps(tmp_path: Path) -> None:
    path = tmp_path / "prices.yaml"
    path.write_text("groq:\n  audio_minutes: 0.5\n", encoding="utf-8")
    built = ledger.from_settings(
        _settings(
            tmp_path, planner="fake", prices_file=path, budget_inr_per_job=50, budget_inr_hard=80
        )
    )
    assert built.prices.providers == {"groq": {"audio_minutes": 0.5}}
    assert built.caps == Caps(per_job=50.0, hard=80.0, per_day=500.0)


# --- rows -------------------------------------------------------------------------


def test_record_prices_units_from_the_file_and_appends_to_job_json(tmp_path: Path) -> None:
    job = _job(tmp_path)
    row = _ledger().record(job, "transcribing", "groq", "whisper-large-v3", {"audio_minutes": 2})
    assert row.inr == 1.0
    assert row.units == {"audio_minutes": 2.0}
    assert row.tokens_estimated == 0
    assert row.at == T0
    on_disk = jobs.load(job.path).record
    assert on_disk.cost == [row]
    assert on_disk.status == "uploaded"
    assert ledger.cash_total(on_disk) == 1.0


def test_tokens_are_priced_per_thousand(tmp_path: Path) -> None:
    row = _ledger().record(
        _job(tmp_path), "planning", "planner", "m", {"input_tokens": 2000, "output_tokens": 400}
    )
    assert row.inr == pytest.approx(2 * 0.25 + 0.4 * 1.25)


def test_a_row_for_an_unpriced_provider_or_unit_is_an_error(tmp_path: Path) -> None:
    job = _job(tmp_path)
    with pytest.raises(LedgerError, match="pexels"):
        _ledger().record(job, "sourcing", "pexels", "-", {"queries": 1})
    with pytest.raises(LedgerError, match=r"groq\.images"):
        _ledger().record(job, "sourcing", "groq", "-", {"images": 1})
    assert jobs.load(job.path).record.cost == []


def test_rows_survive_a_later_transition(tmp_path: Path) -> None:
    """The worker holds its own Job object; a row appended mid-step must not be lost
    when the step ends and the worker writes the next status."""
    job = _job(tmp_path)
    running = jobs.transition(job, "transcribing")
    _ledger().record(running, "transcribing", "groq", "w", {"audio_minutes": 1})
    after = jobs.transition(running, "planning")
    assert len(after.record.cost) == 1
    assert len(jobs.load(job.path).record.cost) == 1


# --- caps -------------------------------------------------------------------------


def test_soft_cap_only_flags(tmp_path: Path) -> None:
    job = _job(tmp_path)
    book = _ledger(per_job=1.0)
    book.record(job, "sourcing", "gemini", "g", {"images": 0.3})  # 0.9: under
    assert jobs.load(job.path).record.over_soft_cap is False
    book.record(job, "sourcing", "gemini", "g", {"images": 0.1})  # 1.2: over
    record = jobs.load(job.path).record
    assert record.over_soft_cap is True
    assert record.status == "uploaded" and record.error is None
    book.check_before_call(job, "sourcing", 100.0)  # no hard cap: never raises


def test_exactly_the_soft_cap_is_not_over_it(tmp_path: Path) -> None:
    job = _job(tmp_path)
    _ledger(per_job=3.0).record(job, "sourcing", "gemini", "g", {"images": 1})
    assert jobs.load(job.path).record.over_soft_cap is False


class _MeteredAdapter:
    """What a paid adapter does: ask the ledger first, then call, then report units."""

    def __init__(self, book: Ledger, estimate_inr: float) -> None:
        self.book = book
        self.estimate_inr = estimate_inr
        self.calls = 0

    def call(self, job: jobs.Job) -> None:
        self.book.check_before_call(job, "sourcing", self.estimate_inr)
        self.calls += 1
        self.book.record(job, "sourcing", "gemini", "g", {"images": 1})


def test_hard_cap_fails_before_the_paid_call(tmp_path: Path) -> None:
    job = _job(tmp_path)
    book = _ledger(hard=1.0)
    book.record(job, "transcribing", "groq", "w", {"audio_minutes": 1.8})  # 0.9 spent
    adapter = _MeteredAdapter(book, estimate_inr=0.2)  # 0.9 + 0.2 > 1.0
    with pytest.raises(BudgetExceeded) as caught:
        adapter.call(job)
    assert caught.value.step == "sourcing"
    assert adapter.calls == 0
    assert len(jobs.load(job.path).record.cost) == 1


def test_exactly_the_hard_cap_still_runs(tmp_path: Path) -> None:
    job = _job(tmp_path)
    book = _ledger(hard=1.0)
    book.record(job, "transcribing", "groq", "w", {"audio_minutes": 1.8})  # 0.9 spent
    adapter = _MeteredAdapter(book, estimate_inr=0.1)  # 0.9 + 0.1 == 1.0: not over
    adapter.call(job)
    assert adapter.calls == 1


def test_subscription_tokens_never_enter_inr(tmp_path: Path) -> None:
    job = _job(tmp_path)
    book = _ledger(per_job=0.01, hard=0.01)
    row = book.record(
        job, "planning", "claude_code", "cli", {"input_tokens": 1000, "output_tokens": 500}
    )
    assert row.inr == 0.0
    assert row.tokens_estimated == 1500
    assert row.inr_equivalent == pytest.approx(1 * 0.25 + 0.5 * 1.25)
    record = jobs.load(job.path).record
    assert ledger.cash_total(record) == 0.0
    assert ledger.tokens_total(record) == 1500
    assert record.over_soft_cap is False
    book.check_before_call(job, "planning", 0.0)  # tokens do not count toward the hard cap


def test_cash_spent_today_sums_rows_since_midnight_ist(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    book = _ledger()
    today = jobs.create(data_dir, now=lambda: T0)
    other = jobs.create(data_dir, now=lambda: T0 - timedelta(days=1))
    book.record(today, "transcribing", "groq", "w", {"audio_minutes": 2})  # 1.0
    book.record(today, "planning", "claude_code", "cli", {"input_tokens": 1000})  # tokens only
    yesterday = Ledger(PRICES, book.caps, clock=lambda: T0 - timedelta(days=1))
    yesterday.record(other, "transcribing", "groq", "w", {"audio_minutes": 4})  # 2.0, yesterday
    assert book.cash_spent_today(data_dir, T0) == 1.0
    # 00:30 IST on the 23rd is 19:00 UTC on the 22nd: midnight IST has passed.
    assert book.cash_spent_today(data_dir, T0 + timedelta(hours=7)) == 0.0


# --- 11.3: nothing is ever degraded for cost ---------------------------------------


def test_over_soft_cap_is_read_only_by_the_page_and_the_contact_sheet() -> None:
    readers = {
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".html"}
        and re.search(r"over_soft_cap", path.read_text(encoding="utf-8"))
    }
    # jobs.py declares the field and ledger.py writes it; only these two read it.
    assert readers - {"jobs.py", "ledger.py"} == {"app.py", "contact_sheet.py"}
