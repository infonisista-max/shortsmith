"""Ticket 096: the sourcing replacement ladder (operator answer 1) and the step that
never fails for one beat.

A replaced beat (its visual removed by the editor or the change box) takes a stock clip,
else an image generated for the line, else the gradient; a named entity is never
generated: its owner reference, else a real image of it already in the reel, else the
gradient. An opening beat with nothing is the gradient, not an `AssetError`, and an
exception on one beat is that beat's gradient while the others are sourced as usual.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from shortsmith import assets
from shortsmith.assets import clips
from shortsmith.assets.http import domain
from shortsmith.assets.judge import JudgeError, parse_reply
from shortsmith.contracts import Beat, Candidate, ReferenceRecord
from shortsmith.ledger import BudgetExceeded
from shortsmith.styles import StyleSpec
from tests.test_assets import (
    EXPLAINER,
    SPEC,
    _beat,  # pyright: ignore[reportPrivateUsage]
    _job_dir,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
    _reference,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_assets_f1 import BABA, _named  # pyright: ignore[reportPrivateUsage]

CLOUDS = "clouds drifting over hills"


def _concept(i: int = 1, *, query: str = CLOUDS) -> Beat:
    """A replaced beat as `replace_visual` leaves it: a photo, a concept, a scene."""
    return _beat(i, "concept", query=query, fallback="sky", depicts="scene", length=2.0)


def _generating(*, nothing_for: Sequence[str] = (), cap: int = 8,
                spent: int = 0) -> tuple[assets.Generating, assets.FakeImageGenerator]:  # fmt: skip
    generator = assets.FakeImageGenerator(nothing_for=nothing_for)
    generating = assets.Generating(generator=generator, spec=SPEC, max_images=cap)
    generating.images = spent
    return generating, generator


def _run(
    tmp_path: Path,
    beats: Sequence[Beat],
    *,
    replaced: frozenset[str] = frozenset(),
    sources: Mapping[str, assets.ImageSource] | None = None,
    clips_by_name: Mapping[str, clips.ClipSource] | None = None,
    references: Sequence[ReferenceRecord] = (),
    generating: assets.Generating | None = None,
    job: Path | None = None,
    log: list[str] | None = None,
    spec: StyleSpec = SPEC,
) -> assets.AssetManifest:
    return assets.source_assets(
        _plan(beats), list(references), "any", spec=spec,
        sources=sources if sources is not None else {"web": assets.FakeImageSource("web")},
        order=assets.DEFAULT_ORDER,
        clips=clips_by_name if clips_by_name is not None else {},
        job_dir=job or _job_dir(tmp_path),
        generating=generating,
        log=(log if log is not None else []).append,
        replaced=replaced,
    )  # fmt: skip


def _ladder(log: list[str], beat_id: str) -> list[str]:
    return [line for line in log if line.startswith(f"sourcing: {beat_id}: replacement ladder:")]


# --- a thing, a place, an idea ---------------------------------------------------------------


def test_a_replaced_concept_beat_takes_a_stock_clip_before_any_still(tmp_path: Path) -> None:
    web, pexels = assets.FakeImageSource("web"), clips.FakeClipSource("pexels")
    generating, generator = _generating()
    log: list[str] = []
    manifest = _run(tmp_path, [_concept()], replaced=frozenset({"b01"}), sources={"web": web},
                    clips_by_name={"pexels": pexels}, generating=generating, log=log)  # fmt: skip
    (shown,) = manifest.beats
    assert (shown.treatment, shown.fallback_rung) == ("clip", 0)
    record = manifest.asset(shown.asset_id or "")
    assert record is not None and record.kind == "clip" and record.origin == "pexels"
    assert (web.searches, generator.calls) == (0, 0)  # the ladder ran first, nothing else
    assert any("stock clip" in line for line in _ladder(log, "b01"))


def test_a_replaced_concept_beat_with_no_clip_is_generated_past_the_cap(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    pexels = clips.FakeClipSource("pexels", nothing_found=True)
    generating, generator = _generating(cap=1, spent=1)  # the cap is spent: forced anyway
    log: list[str] = []
    manifest = _run(tmp_path, [_concept()], replaced=frozenset({"b01"}), sources={"web": web},
                    clips_by_name={"pexels": pexels}, generating=generating, log=log)  # fmt: skip
    (shown,) = manifest.beats
    record = manifest.asset(shown.asset_id or "")
    assert shown.fallback_rung == 2
    assert record is not None and record.origin == "generated"
    assert generator.calls == 1 and web.searches == 0 and pexels.searches == 2  # query, fallback
    lines = _ladder(log, "b01")
    assert any("no usable stock clip" in line for line in lines)
    assert any("generated image" in line for line in lines)


def test_a_replaced_concept_beat_with_no_clip_and_no_image_is_the_gradient(
    tmp_path: Path,
) -> None:
    generating, _ = _generating(nothing_for=["clouds"])
    log: list[str] = []
    manifest = _run(tmp_path, [_concept()], replaced=frozenset({"b01"}),
                    clips_by_name={"pexels": clips.FakeClipSource("pexels", nothing_found=True)},
                    generating=generating, log=log)  # fmt: skip
    (shown,) = manifest.beats
    assert (shown.treatment, shown.fallback_rung, shown.asset_id) == ("gradient", 4, None)
    assert any("gradient" in line for line in _ladder(log, "b01"))


def test_a_beat_not_replaced_keeps_its_usual_ladder(tmp_path: Path) -> None:
    web, pexels = assets.FakeImageSource("web"), clips.FakeClipSource("pexels")
    log: list[str] = []
    manifest = _run(tmp_path, [_concept()], sources={"web": web},
                    clips_by_name={"pexels": pexels}, log=log)  # fmt: skip
    assert manifest.beats[0].treatment in ("photo", "card")
    assert (web.searches, pexels.searches) == (1, 0) and not _ladder(log, "b01")


# --- a named person or entity: never AI ----------------------------------------------------


def test_a_replaced_named_entity_takes_its_owner_reference_and_is_never_generated(
    tmp_path: Path,
) -> None:
    job = _job_dir(tmp_path)
    ref = _reference(job, "r1", "Neem Karoli Baba at the ashram", (1080, 1920))
    web, pexels = assets.FakeImageSource("web"), clips.FakeClipSource("pexels")
    generating, generator = _generating()
    log: list[str] = []
    manifest = _run(tmp_path, [_named(1)], replaced=frozenset({"b01"}), sources={"web": web},
                    clips_by_name={"pexels": pexels}, references=[ref],
                    generating=generating, job=job, log=log)  # fmt: skip
    (shown,) = manifest.beats
    record = manifest.asset(shown.asset_id or "")
    assert record is not None and record.origin == "owner_supplied" and shown.fallback_rung == 0
    assert (generator.calls, web.searches, pexels.searches) == (0, 0, 0)
    assert any("owner reference 'r1'" in line for line in _ladder(log, "b01"))


def test_a_replaced_named_entity_redresses_an_earlier_image_of_the_same_entity(
    tmp_path: Path,
) -> None:
    web, pexels = assets.FakeImageSource("web"), clips.FakeClipSource("pexels")
    generating, generator = _generating()
    log: list[str] = []
    beats = [_named(1), _named(2, query=f"{BABA} smiling")]
    manifest = _run(tmp_path, beats, replaced=frozenset({"b02"}), sources={"web": web},
                    clips_by_name={"pexels": pexels}, generating=generating, log=log)  # fmt: skip
    first, second = manifest.beats
    assert (second.asset_id, second.redressed_from, second.fallback_rung) == (
        first.asset_id, first.asset_id, 3)  # fmt: skip
    assert second.crop != first.crop
    assert (generator.calls, web.searches, pexels.searches) == (0, 1, 0)  # b01 only
    assert any("re-dressed" in line for line in _ladder(log, "b02"))


def test_a_replaced_named_entity_with_nothing_of_it_is_the_gradient_never_ai(
    tmp_path: Path,
) -> None:
    """Another person's image already in the reel is not taken (071), and nothing is
    generated for a named entity, even with a generator configured."""
    generating, generator = _generating()
    log: list[str] = []
    beats = [_named(1, query="Virat Kohli batting", fallback="Virat Kohli"), _named(2)]
    manifest = _run(tmp_path, beats, replaced=frozenset({"b02"}), generating=generating,
                    clips_by_name={"pexels": clips.FakeClipSource("pexels")}, log=log)  # fmt: skip
    shown = manifest.beats[1]
    assert (shown.treatment, shown.asset_id) == ("gradient", None)
    assert generator.calls == 0
    assert any("never generated" in line for line in _ladder(log, "b02"))


# --- the opening, and one beat's failure ---------------------------------------------------


def test_an_opening_beat_with_nothing_is_the_gradient_and_the_step_goes_on(
    tmp_path: Path,
) -> None:
    empty = assets.FakeImageSource("web", nothing_found=True)
    log: list[str] = []
    beats = [_beat(1, "concept"), _beat(2, "concept")]
    manifest = _run(tmp_path, beats, sources={"web": empty}, spec=EXPLAINER, log=log)
    assert [(b.beat_id, b.treatment) for b in manifest.beats] == [
        ("b01", "gradient"), ("b02", "gradient")]  # fmt: skip
    assert any(line.startswith("sourcing: b01: opening beat has no image") for line in log)


class _Exploding(assets.FakeImageSource):
    """A source with a bug on one query."""

    def __init__(self, bad: str, error: Exception) -> None:
        super().__init__("web")
        self.bad, self.error = bad, error

    def search(self, query: str, n: int) -> list[Candidate]:
        if query == self.bad:
            raise self.error
        return super().search(query, n)


def test_an_exception_on_one_beat_is_its_gradient_and_the_others_are_sourced(
    tmp_path: Path,
) -> None:
    log: list[str] = []
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept")]
    source = _Exploding("query 2", RuntimeError("the parser broke"))
    manifest = _run(tmp_path, beats, sources={"web": source}, log=log)
    assert [(b.beat_id, b.treatment == "gradient") for b in manifest.beats] == [
        ("b01", False), ("b02", True), ("b03", False)]  # fmt: skip
    assert "sourcing: b02: the parser broke; shown over the gradient (plain fallback)" in log


def test_budget_exceeded_on_a_beat_still_stops_the_step(tmp_path: Path) -> None:
    error = BudgetExceeded("sourcing", spent_inr=1.0, estimated_inr=1.0, hard_inr=1.5)
    with pytest.raises(BudgetExceeded):
        _run(tmp_path, [_beat(1, "concept")], sources={"web": _Exploding("query 1", error)})


# --- malformed URLs and scores ---------------------------------------------------------------


def test_a_url_httpx_cannot_parse_has_no_domain() -> None:
    assert domain("::::") is None
    assert domain("https://www.example.com/a.png") == "example.com"


@pytest.mark.parametrize("score", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_judge_score_is_a_judge_error(score: str) -> None:
    with pytest.raises(JudgeError):
        parse_reply(f'{{"candidates": [{{"index": 1, "score": {score}}}]}}', 1)
