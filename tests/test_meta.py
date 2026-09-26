"""meta: `out/meta.json`, the proof of the bar for one short (decision 10.4; ticket 035).

It records the technical results, the critic's report, the phone rating and the
published short's audience when present, the reference category and the pack version,
the planner prompt version, the style spec version and the full ledger. The pipeline
writes it once the job is settled; a rating or a performance update rewrites it."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from shortsmith import contracts, jobs, meta
from shortsmith.contracts import Meta
from shortsmith.qa import calibration, technical
from shortsmith.qa.critic import FakeCritic
from tests.test_pipeline import SPECS, _run, _uploaded  # pyright: ignore[reportPrivateUsage]

T0 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=UTC)


def _now() -> datetime:
    return T0


# --- the shared models (the ledger row, the rating, the audience live in contracts) -------


def test_the_job_record_models_live_in_contracts_and_jobs_re_exports_them() -> None:
    """`Meta` carries a `Rating`, a `Performance` and `CostRow`s; they are defined in
    contracts (which jobs imports) and jobs keeps the old names."""
    assert jobs.Rating is contracts.Rating
    assert jobs.Performance is contracts.Performance
    assert jobs.CostRow is contracts.CostRow
    assert jobs.CriticSummary is contracts.CriticSummary
    assert (jobs.RATING_MIN, jobs.RATING_MAX) == (contracts.RATING_MIN, contracts.RATING_MAX)


# --- the pack version and the style version -------------------------------------------------


def test_the_reference_readme_carries_a_pack_version_and_it_is_read(tmp_path: Path) -> None:
    assert meta.pack_version() == "1"
    readme = tmp_path / "README.md"
    readme.write_text("# Pack\n\nPack version: 2.3 (bumped by the tool)\n\n## The bar\n", "utf-8")
    assert meta.pack_version(readme) == "2.3"
    assert meta.pack_version(tmp_path / "missing.md") is None
    readme.write_text("# Pack without a version line\n", "utf-8")
    assert meta.pack_version(readme) is None


def test_every_style_spec_carries_a_version_in_its_front_matter() -> None:
    for spec in SPECS.values():
        assert spec.version, spec.name
        assert "version" in spec.numbers()


# --- meta.json on a delivered job ---------------------------------------------------------


def test_the_pipeline_writes_meta_json_once_the_job_is_delivered(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, critic=FakeCritic())
    assert done.status == "delivered"
    path = job.out_dir / meta.NAME
    assert path.is_file()
    recorded = Meta.model_validate_json(path.read_text(encoding="utf-8"))
    assert recorded.job_id == job.id and recorded.status == "delivered"
    assert recorded.delivered is True
    assert recorded.style == "explainer"
    assert recorded.style_version == SPECS["explainer"].version
    assert recorded.prompt_version == done.record.prompt_version
    assert recorded.category == "science"
    assert recorded.reference_pack_version == meta.pack_version()
    assert [c.name for c in recorded.technical] == list(technical.CHECK_ORDER)
    assert all(c.status == "pass" for c in recorded.technical)
    assert recorded.technical_passed is True
    assert recorded.critic is not None and recorded.critic.overall == FakeCritic.OVERALL
    assert recorded.rating is None and recorded.performance is None
    assert recorded.ledger == [] and recorded.cash_inr == 0.0
    assert recorded.over_soft_cap is False
    assert recorded.clamps == 1 and recorded.rescued == 0
    assert meta.load(job) == recorded


def test_a_rating_and_a_performance_update_rewrite_meta_json(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, critic=FakeCritic())
    first = meta.load(done)
    assert first is not None and first.rating is None
    rated = jobs.rate(done, 8, "clean", now=_now)
    settled = calibration.apply(rated, now=_now)
    written = meta.write(settled, now=_now)
    again = Meta.model_validate_json(written.read_text(encoding="utf-8"))
    assert again.status == "passed" and again.delivered is True
    assert again.rating is not None and again.rating.score == 8 and again.rating.note == "clean"
    assert again.written_at == T0
    published = jobs.set_performance(settled, published_url="https://youtube.com/shorts/abc",
                                     views=120, now=_now)  # fmt: skip
    meta.write(published, now=_now)
    final = meta.load(published)
    assert final is not None and final.performance is not None
    assert final.performance.views == 120


def test_build_tolerates_a_job_with_nothing_but_job_json(tmp_path: Path) -> None:
    """A job that never got past upload still describes itself: no checks, no critic,
    no plan, and `delivered` false."""
    job = jobs.create(tmp_path, style="explainer")
    built = meta.build(job, now=_now)
    assert built.job_id == job.id and built.status == "uploaded"
    assert built.delivered is False and built.technical == [] and built.technical_passed is False
    assert built.critic is None and built.category == "other"
    assert built.prompt_version is None and built.style_version is None
    assert built.clamps == 0 and built.rescued == 0
    assert built.written_at == T0


def test_meta_json_is_plain_json_with_the_documented_keys(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    _run(job)
    data = json.loads((job.out_dir / meta.NAME).read_text(encoding="utf-8"))
    for key in (
        "job_id", "status", "delivered", "style", "style_version", "prompt_version",
        "category", "reference_pack_version", "technical", "technical_passed", "critic",
        "rating", "performance", "ledger", "cash_inr", "tokens_estimated", "inr_equivalent",
        "over_soft_cap", "clamps", "rescued", "written_at",
    ):  # fmt: skip
        assert key in data, key


def test_the_style_version_is_recorded_on_job_json_at_planning(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job)
    assert done.record.style_version == SPECS["explainer"].version
    assert jobs.load(job.path).record.style_version == SPECS["explainer"].version
