"""099: a named person is not a named place.

`depicts` splits the old `named_entity` into `named_person` (a real, named human) and
`named_place`, `named_era`, `named_event`, `named_object`. Only a named person (and the
old `named_entity`, read exactly as before for stored plans) keeps the no-stock rule:
never a stock stranger, never AI (100). A place, an era, an event or an object may take
a stock clip, stock stills and, as the last rung, a generated image.

The era rule (operator, 30 Sep 2026): on a `named_era` beat, or any beat whose query
names an era, the clip judge is asked, like an editor, whether each clip looks period,
timeless (a desert, the sea, the sky) or modern standing in for the old era. Period
clips come first, then timeless ones (their `era` verdict rides the asset so 102 can
grade them); a modern stand-in is refused with the judge's reason in job.log and the
beat falls to a still. Never a job failure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from shortsmith import assets, grammar, planner
from shortsmith.assets import clips, judge
from shortsmith.assets import generate as gen
from shortsmith.contracts import Beat, Era
from shortsmith.planner import prompt
from shortsmith.styles import StyleSpec
from tests.test_assets import (
    SPEC,
    _beat,  # pyright: ignore[reportPrivateUsage]
    _job_dir,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_grammar import (
    as_clip,
    checked,
    make_plan,
    picture,
    replace,
    rules,
    spec,  # noqa: F401  # pyright: ignore[reportUnusedImport]  (the module fixture)
)

SPLIT = ("named_place", "named_era", "named_event", "named_object")


def _run(
    tmp_path: Path,
    beats: Sequence[Beat],
    *,
    clip_sources: Mapping[str, clips.ClipSource] | None = None,
    sources: Mapping[str, assets.ImageSource] | None = None,
    judging: assets.Judging | None = None,
    generating: assets.Generating | None = None,
    log: list[str] | None = None,
) -> assets.AssetManifest:
    return assets.source_assets(
        _plan(beats), [], "any", spec=SPEC,
        sources=sources if sources is not None else {"web": assets.FakeImageSource("web")},
        order=assets.DEFAULT_ORDER,
        clips=clip_sources if clip_sources is not None else {
            "pexels": clips.FakeClipSource("pexels")},
        judging=judging, generating=generating,
        job_dir=_job_dir(tmp_path),
        log=(log if log is not None else []).append,
    )  # fmt: skip


def _clip(i: int, depicts: str, *, query: str = "oil well pumping in the desert",
          subject: str = "entity") -> Beat:  # fmt: skip
    return _beat(i, subject, kind="clip", query=query, fallback="desert", depicts=depicts,
                 length=2.0)  # fmt: skip


# --- the contract --------------------------------------------------------------------------


@pytest.mark.parametrize("depicts", ["named_person", *SPLIT, "named_entity", "scene"])
def test_the_contract_takes_the_split_and_still_reads_named_entity(depicts: str) -> None:
    beat = _beat(1, "entity", depicts=depicts)
    assert beat.depicts == depicts


def test_the_helpers_say_who_is_a_person_and_who_keeps_the_no_stock_rule() -> None:
    person = _beat(1, "entity", depicts="named_person")
    legacy = _beat(2, "entity", depicts="named_entity")
    unlabelled = _beat(3, "entity")  # a stored plan: depicts None on an entity beat
    assert gen.never_stock(person) and gen.never_stock(legacy) and gen.never_stock(unlabelled)
    assert gen.names_a_person(person) and gen.names_a_person(legacy)
    for depicts in SPLIT:
        beat = _beat(4, "entity", depicts=depicts)
        assert gen.is_named(beat), depicts
        assert not gen.never_stock(beat), depicts
        assert not gen.names_a_person(beat), depicts
    assert not gen.is_named(_beat(5, "concept", depicts="scene"))


# --- the grammar ---------------------------------------------------------------------------


@pytest.mark.parametrize("depicts", SPLIT)
def test_a_place_era_event_or_object_clip_passes_the_grammar(
    depicts: str, spec: StyleSpec,  # noqa: F811
) -> None:
    checked(replace(as_clip(make_plan(), "b06"), "b06", depicts=depicts), spec)


@pytest.mark.parametrize("depicts", ["named_person", "named_entity", None])
def test_a_named_person_clip_is_still_a_hard_violation(
    depicts: str | None, spec: StyleSpec,  # noqa: F811
) -> None:
    result = picture(replace(as_clip(make_plan(), "b06"), "b06", depicts=depicts), spec)
    assert ("b06", "4.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any(v.hard and v.beat_id == "b06" for v in result.items)


# --- sourcing ------------------------------------------------------------------------------


@pytest.mark.parametrize("depicts", SPLIT)
def test_a_place_era_event_or_object_clip_beat_reaches_the_stock_clips(
    tmp_path: Path, depicts: str
) -> None:
    pexels, pixabay = clips.FakeClipSource("pexels"), clips.FakeClipSource("pixabay",
                                                                           nothing_found=True)
    no_pexels = clips.FakeClipSource("pexels", nothing_found=True)
    manifest = _run(tmp_path / "a", [_clip(1, depicts)], clip_sources={"pexels": pexels})
    assert pexels.searches == 1 and manifest.beats[0].treatment == "clip"
    manifest = _run(tmp_path / "b", [_clip(1, depicts)],
                    clip_sources={"pexels": no_pexels, "pixabay": pixabay})  # fmt: skip
    assert pixabay.searches >= 1


@pytest.mark.parametrize("depicts", SPLIT)
def test_a_place_era_event_or_object_still_may_come_from_the_stock_libraries(
    tmp_path: Path, depicts: str
) -> None:
    web = assets.FakeImageSource("web", nothing_found=True)
    pexels = assets.FakeImageSource("pexels")
    beat = _beat(1, "entity", query="Riyadh palace", depicts=depicts)
    log: list[str] = []
    manifest = _run(tmp_path, [beat], sources={"web": web, "pexels": pexels}, log=log)
    assert pexels.searches >= 1
    assert manifest.assets[0].origin == "pexels"
    assert not any("stock stranger" in line for line in log)


@pytest.mark.parametrize("depicts", ["named_person", "named_entity"])
def test_a_named_person_never_gets_stock(tmp_path: Path, depicts: str) -> None:
    pexels_clips = clips.FakeClipSource("pexels")
    pexels = assets.FakeImageSource("pexels")
    web = assets.FakeImageSource("web")
    log: list[str] = []
    beat = _clip(1, depicts, query="King Saud portrait")
    manifest = _run(tmp_path, [beat], clip_sources={"pexels": pexels_clips},
                    sources={"web": web, "pexels": pexels}, log=log)  # fmt: skip
    assert pexels_clips.searches == 0 and pexels.searches == 0
    assert manifest.assets[0].origin == "web"
    assert any("stock stranger" in line for line in log)


def test_a_named_place_may_be_generated_as_the_last_rung(tmp_path: Path) -> None:
    generator = assets.FakeImageGenerator()
    generating = assets.Generating(generator=generator, spec=SPEC, max_images=8)
    for i, depicts in enumerate(SPLIT, 1):
        beat = _beat(i, "entity", query=f"an old Arabian palace {depicts}", depicts=depicts)
        assert generating.make(beat, tmp_path) is not None, depicts
    assert generator.calls == len(SPLIT)
    person = _beat(9, "entity", query="King Saud", depicts="named_person")
    assert generating.make(person, tmp_path, force=True) is None


# --- the era rule --------------------------------------------------------------------------


def test_an_era_beat_is_a_named_era_or_a_query_naming_an_era() -> None:
    assert gen.is_era(_beat(1, "entity", query="Riyadh", depicts="named_era"))
    for query in ("a 1950s oil field", "Riyadh in 1953", "19th century caravan",
                  "ancient Arabian trade route", "vintage plane taking off"):
        assert gen.is_era(_beat(1, "concept", query=query, depicts="scene")), query
    for query in ("a plane taking off", "sand dunes at dusk", "an old Arabian palace"):
        assert not gen.is_era(_beat(1, "concept", query=query, depicts="scene")), query


def test_the_judge_prompt_carries_the_era_rule() -> None:
    text = judge.SYSTEM_PROMPT
    for needle in ("period", "timeless", "modern", "cars", "skylines", "phones", "clothes"):
        assert needle in text, needle
    thumbs = [judge.Thumb(clips.FakeClipSource("pexels").search("x", 1)[0])]
    assert "Era beat" not in judge.request_text("q", "concept", "", thumbs)
    asked = judge.request_text("q", "concept", "", thumbs, era=True)
    assert "Era beat" in asked


def test_the_judge_reply_carries_the_era_verdict_and_its_reason() -> None:
    reply = ('{"candidates": [{"index": 1, "score": 3, "reasons": [], "era": "period", '
             '"why": "grainy 1950s film"}, {"index": 2, "score": 3, "reasons": [], '
             '"era": "modern", "why": "a 2020s SUV on a motorway"}, {"index": 3, '
             '"score": 2, "era": "timeless", "why": "dunes, no modern detail"}]}')
    period, modern, timeless = judge.parse_reply(reply, 3)
    assert (period.era, period.why, period.accepted) == ("period", "grainy 1950s film", True)
    assert (modern.era, modern.accepted) == ("modern", False)
    assert "SUV" in modern.why
    assert (timeless.era, timeless.accepted) == ("timeless", True)


class _Editor(judge.RelevanceJudge):
    """Answers each clip's era from its URL slug, like an editor would from the frame."""

    def __init__(self, eras: dict[str, Era]) -> None:
        self.model = "editor"
        self.eras = eras
        self.asked: list[bool] = []

    def score(
        self, query: str, subject_kind: str, topic: str, thumbs: Sequence[judge.Thumb],
        *, era: bool = False,
    ) -> list[judge.Verdict]:
        self.asked.append(era)
        out: list[judge.Verdict] = []
        for thumb in thumbs:
            found: Era | None = None
            for key, verdict in self.eras.items():
                if key in thumb.candidate.url:
                    found = verdict
            if not era or found is None:
                out.append(judge.Verdict(3))
            else:
                out.append(judge.Verdict(3, era=found, why=f"looks {found}: {query}"))
        return out


def _judging(eras: dict[str, Era]) -> tuple[assets.Judging, _Editor]:
    editor = _Editor(eras)
    return assets.Judging(judge=editor, max_calls=20), editor


def test_a_modern_stand_in_is_refused_with_its_reason_and_the_beat_falls_to_a_still(
    tmp_path: Path,
) -> None:
    judging, editor = _judging({"pexels-video": "modern", "pixabay-video": "modern"})
    both = {"pexels": clips.FakeClipSource("pexels"), "pixabay": clips.FakeClipSource("pixabay")}
    log: list[str] = []
    beat = _clip(1, "named_era", query="Riyadh streets in the 1950s")
    manifest = _run(tmp_path, [beat], clip_sources=both, judging=judging, log=log)
    assert True in editor.asked
    (shown,) = manifest.beats
    assert shown.treatment in ("photo", "card")
    refused = [line for line in log if "modern" in line and "b01" in line]
    assert refused and any("looks modern" in line for line in refused)


def test_a_period_clip_beats_a_timeless_one_and_the_era_rides_the_asset(tmp_path: Path) -> None:
    judging, _ = _judging({"pexels-video": "timeless", "pixabay-video": "period"})
    both = {"pexels": clips.FakeClipSource("pexels"), "pixabay": clips.FakeClipSource("pixabay")}
    beat = _clip(1, "scene", query="a 1950s oil field", subject="concept")
    manifest = _run(tmp_path, [beat], clip_sources=both, judging=judging)
    record = manifest.asset("a1")
    assert record is not None and record.origin == "pixabay"
    assert record.judge is not None and record.judge.era == "period"


def test_a_timeless_clip_is_taken_when_no_period_one_exists_and_carries_its_era(
    tmp_path: Path,
) -> None:
    judging, _ = _judging({"pexels-video": "timeless", "pixabay-video": "modern"})
    both = {"pexels": clips.FakeClipSource("pexels"), "pixabay": clips.FakeClipSource("pixabay")}
    beat = _clip(1, "named_era", query="Arabia in the 1950s")
    manifest = _run(tmp_path, [beat], clip_sources=both, judging=judging)
    record = manifest.asset("a1")
    assert record is not None and record.kind == "clip" and record.origin == "pexels"
    assert record.judge is not None and record.judge.era == "timeless"


def test_a_beat_without_an_era_is_judged_as_before(tmp_path: Path) -> None:
    judging, editor = _judging({"pexels-video": "modern"})
    beat = _clip(1, "named_place", query="a plane taking off")
    manifest = _run(tmp_path, [beat], judging=judging)
    assert editor.asked == [False]
    record = manifest.asset("a1")
    assert record is not None and record.kind == "clip"
    assert record.judge is not None and record.judge.era is None


# --- the prompt and the fake plan ----------------------------------------------------------


def test_picture_v20_is_current_and_carries_the_split_and_the_era_rule() -> None:
    assert prompt.PROMPT_VERSION == "v20"
    text = (prompt.PROMPTS_DIR / "picture_v20.md").read_text(encoding="utf-8")
    for needle in ("named_person", "named_place", "named_era", "named_event", "named_object",
                   "a 1950s oil field", "an old Arabian palace", "a plane taking off",
                   "skylines", "sepia"):
        assert needle in text, needle
    v19 = (prompt.PROMPTS_DIR / "picture_v19.md").read_text(encoding="utf-8")
    assert "named_person" not in v19
    assert (prompt.PROMPTS_DIR / "sound_v20.md").read_text(encoding="utf-8") == (
        prompt.PROMPTS_DIR / "sound_v19.md").read_text(encoding="utf-8")  # fmt: skip


def test_the_fake_plan_uses_the_split() -> None:
    from tests.test_planner_prompt import _request  # pyright: ignore[reportPrivateUsage]

    plan = planner.FakePlanner().plan_picture(_request())
    depicted = {b.depicts for b in plan.beats}
    assert "named_place" in depicted and "named_entity" not in depicted


# --- the other readers of `depicts` ----------------------------------------------------------


@pytest.mark.parametrize("depicts", ["named_person", *SPLIT])
def test_t9_fails_any_named_value_generated_photoreal(depicts: str) -> None:
    from shortsmith.contracts import Generated
    from tests.test_rights import (
        _beat_asset,  # pyright: ignore[reportPrivateUsage]
        _problems,  # pyright: ignore[reportPrivateUsage]
        _record,  # pyright: ignore[reportPrivateUsage]
    )
    from tests.test_rights import (
        _plan as _rights_plan,  # pyright: ignore[reportPrivateUsage]
    )

    plan = _rights_plan(("b01", "photo", "g1"))
    photo = Generated(model="gen", prompt="x", render="photoreal", depicts=depicts)  # pyright: ignore[reportArgumentType]
    problems = _problems([_record("g1", "generated", generated=photo)],
                         [_beat_asset("b01", "g1", 2)], plan)  # fmt: skip
    assert problems == ["g1: a named entity rendered photoreal (4.2 requires illustration)"]


def test_the_match_share_counts_every_named_value() -> None:
    from shortsmith.reference import examples

    beats = [_beat(i, "concept", depicts=d) for i, d in enumerate(("named_era", "scene"), 1)]
    assert examples.plan_match(_plan(beats).picture) == (1, 2)
