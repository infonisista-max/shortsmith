"""publishing: the copyable text the job page offers once a short exists (decision 10.4,
8.2, 5.4; ticket 035): the plan's title, the description with the credits and the
AI-disclosure line appended, and up to five hashtags."""

from __future__ import annotations

from pathlib import Path

from shortsmith import jobs, publishing, rights
from shortsmith.contracts import CutPlan, Finale, Hook, PicturePlan, Span
from shortsmith.grammar import HASHTAGS_MAX
from tests.test_pipeline import _run, _uploaded  # pyright: ignore[reportPrivateUsage]


def _plan(**changes: object) -> PicturePlan:
    given: dict[str, object] = {
        "prompt_version": "t",
        "cut": CutPlan(keep=[Span(start=0.0, end=5.0)]),
        "beats": [],
        "hook": Hook(title="t", cold_open_span=Span(start=0.0, end=1.0),
                     original_position="drop", card_asset_ids=[]),
        "finale": Finale(beat_id="b01", text="t"),
        "title": "Why the sky is blue",
        "description": "Rayleigh scattering in one breath.",
        "hashtags": ["#shorts", "#science"],
    }  # fmt: skip
    given.update(changes)
    return PicturePlan.model_validate(given)


CREDITS = (
    "Photo: Ankit Sharma via https://commons.wikimedia.org/wiki/File:Sky.jpg\n\n"
    f"{rights.DISCLOSURE}\n"
)


def test_assemble_joins_the_description_the_credits_and_the_disclosure() -> None:
    text = publishing.assemble(_plan(), CREDITS)
    assert text.title == "Why the sky is blue"
    assert text.description == (
        "Rayleigh scattering in one breath.\n\n"
        "Photo: Ankit Sharma via https://commons.wikimedia.org/wiki/File:Sky.jpg\n\n"
        f"{rights.DISCLOSURE}"
    )
    assert text.hashtags == ["#shorts", "#science"]
    assert text.hashtag_line == "#shorts #science"


def test_assemble_without_credits_is_the_plan_description_alone() -> None:
    text = publishing.assemble(_plan(), "")
    assert text.description == "Rayleigh scattering in one breath."
    assert publishing.assemble(_plan(), "  \n").description == text.description


def test_hashtags_are_cut_to_five_and_each_starts_with_a_hash() -> None:
    plan = _plan(hashtags=["shorts", "#a", "b", "#c", "#d", "#e", "#f"])
    text = publishing.assemble(plan, "")
    assert len(text.hashtags) == HASHTAGS_MAX == 5
    assert text.hashtags == ["#shorts", "#a", "#b", "#c", "#d"]
    assert publishing.assemble(_plan(hashtags=[]), "").hashtag_line == ""


def test_load_reads_the_plan_and_the_credits_of_a_delivered_job(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job)
    text = publishing.load(done)
    assert text is not None
    assert text.title == "A short about nothing"
    assert text.description.startswith("Six seconds, twelve words, every kind of picture.\n\n")
    credits = (job.out_dir / "credits.md").read_text(encoding="utf-8").strip()
    assert credits and text.description.endswith(credits)
    assert "Photo: fake web via https://fake.invalid/web/" in text.description
    assert text.hashtags == ["#shorts", "#nothing", "#synthetic"]


def test_load_is_none_without_a_plan(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    assert publishing.load(job) is None
