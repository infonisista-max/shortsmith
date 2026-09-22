"""assets: the `sourcing` step with only the fake image source (ticket 016).

Source order and the rights-safe policy (5.1, 5.2), the fake source, aspect
classification from real dimensions (5.3), the fallback ladder with its rung per beat
and re-dressed reuse (4.4), `source_intent` and the per-subject-kind source rules
(4.2, 5.1), owner references first (1.3), and the per-job cache (5.6)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import assets, config, render, rights, styles
from shortsmith.contracts import (
    Beat,
    BedQuery,
    Candidate,
    CutPlan,
    Event,
    Finale,
    Generated,
    Hook,
    PicturePlan,
    ReferenceRecord,
    SoundStory,
    Span,
    ValidatedPlan,
)
from shortsmith.ledger import Ledger
from tests.conftest import Media

SPEC = styles.load_all(render.registry())["explainer"]
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def _no_ledger() -> Ledger:
    """No adapter built by `from_settings` bills anything in these tests."""
    raise AssertionError("the ledger is not needed here")


def _clock() -> datetime:
    return NOW


def _beat(i: int, subject: str | None, *, kind: str = "photo", query: str = "",
          fallback: str = "", intent: str | None = "search", asset: str | None = None,
          mode: str = "pip", depicts: str | None = None, event: Event | None = None,
          length: float = 5.0) -> Beat:  # fmt: skip
    return Beat.model_validate(
        {
            "id": f"b{i:02d}",
            "start": (i - 1) * length,
            "end": i * length,
            "mode": mode,
            "kind": kind,
            "motion": None if subject is None else "ken_burns_in",
            "subject_kind": subject,
            "depicts": depicts,
            "query": query or (f"query {i}" if subject else ""),
            "query_fallback": fallback or (f"fallback {i}" if subject else ""),
            "source_intent": intent if subject else None,
            "asset_id": asset if asset is not None else (f"a{i}" if subject else None),
            "event": event or Event(),
        }
    )


def _plan(beats: Sequence[Beat], *, hook_cards: Sequence[str] = ()) -> ValidatedPlan:
    end = beats[-1].end
    picture = PicturePlan(
        prompt_version="t",
        cut=CutPlan(keep=[Span(start=0.0, end=end)]),
        beats=list(beats),
        hook=Hook(
            title="t",
            cold_open_span=Span(start=0.0, end=1.0),
            original_position="drop",
            card_asset_ids=list(hook_cards),
        ),
        finale=Finale(beat_id=beats[-1].id, text="t"),
        title="t",
        description="t",
    )
    sound = SoundStory(
        prompt_version="t", theme="t", mood_curve=[],
        bed_query=BedQuery(theme="t", mood="t", energy=3), cues=[],
    )  # fmt: skip
    return ValidatedPlan(picture=picture, sound=sound)


def _job_dir(tmp_path: Path) -> Path:
    job = tmp_path / "job"
    (job / "input").mkdir(parents=True)
    (job / "work").mkdir()
    return job


def _run(
    tmp_path: Path,
    beats: Sequence[Beat],
    *,
    sources: dict[str, assets.ImageSource] | None = None,
    references: Sequence[ReferenceRecord] = (),
    policy: str = "any",
    generate: assets.Generate | None = None,
    job: Path | None = None,
    hook_cards: Sequence[str] = (),
    judging: assets.Judging | None = None,
    topic: str = "",
    log: list[str] | None = None,
) -> assets.AssetManifest:
    return assets.source_assets(
        _plan(beats, hook_cards=hook_cards),
        list(references),
        policy,  # pyright: ignore[reportArgumentType]
        spec=SPEC,
        sources=sources if sources is not None else {"web": assets.FakeImageSource("web")},
        order=assets.DEFAULT_ORDER,
        job_dir=job or _job_dir(tmp_path),
        generate=generate,
        judging=judging,
        topic=topic,
        log=(log if log is not None else []).append,
        clock=_clock,
    )


# --- source order and policy (5.1, 5.2) ----------------------------------------------


def test_default_order_is_the_5_1_order() -> None:
    assert assets.DEFAULT_ORDER == ("web", "commons", "openverse", "pexels", "pixabay")


def test_any_policy_keeps_the_full_order() -> None:
    assert assets.source_order(assets.DEFAULT_ORDER, "any") == list(assets.DEFAULT_ORDER)


def test_rights_safe_removes_web_search_only() -> None:
    assert assets.source_order(assets.DEFAULT_ORDER, "rights_safe") == [
        "commons", "openverse", "pexels", "pixabay",
    ]  # fmt: skip


def test_order_parses_the_config_string() -> None:
    assert assets.parse_order(" commons, web ,,pexels ") == ("commons", "web", "pexels")


def _settings(**overrides: object) -> config.Settings:
    overrides.setdefault("relevance_judge", "none")
    return config.Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue, reportArgumentType]


def _sourcing(**overrides: object) -> assets.Sourcing:
    return assets.from_settings(_settings(**overrides), ledger=_no_ledger)


def test_from_settings_follows_asset_sources_and_policy() -> None:
    sourcing = _sourcing(asset_sources="fake,web", asset_policy="rights_safe")
    assert (tuple(sourcing.order), sourcing.policy) == (("fake", "web"), "rights_safe")
    assert list(sourcing.sources) == ["fake"]  # the policy dropped `web`
    assert sourcing.missing() == []
    assert sourcing.generate is None  # IMAGE_GEN=none until 019


def test_default_settings_build_every_keyless_adapter_in_the_5_1_order() -> None:
    """018: web search plus the two free libraries that need no key; Pexels and
    Pixabay join as soon as their free keys are in `.env`."""
    sourcing = _sourcing()
    assert isinstance(sourcing.sources["web"], assets.WebImageSource)
    assert isinstance(sourcing.sources["commons"], assets.CommonsImageSource)
    assert isinstance(sourcing.sources["openverse"], assets.OpenverseImageSource)
    assert sourcing.missing() == ["pexels", "pixabay"]
    assert [n for n in sourcing.notes if "PEXELS_API_KEY" in n]
    assert [n for n in sourcing.notes if "PIXABAY_API_KEY" in n]


def test_the_keyed_libraries_are_built_once_their_free_keys_are_set() -> None:
    sourcing = _sourcing(pexels_api_key="pk_x", pixabay_api_key="px_x")
    assert isinstance(sourcing.sources["pexels"], assets.PexelsImageSource)
    assert isinstance(sourcing.sources["pixabay"], assets.PixabayImageSource)
    assert sourcing.missing() == []
    assert list(sourcing.notes) == []


def test_the_ladder_bookends_are_listed_in_the_config_but_never_searched() -> None:
    """5.1: `owner` and `generate` are the fixed ends of the ladder (1.3, 4.4); the
    config spells the whole order out, and only the names between them are searched."""
    sourcing = _sourcing()
    assert tuple(sourcing.order)[0] == "owner" and tuple(sourcing.order)[-1] == "generate"
    assert set(sourcing.sources) <= set(assets.DEFAULT_ORDER)
    assert assets.source_order(("owner", "web", "generate"), "any") == ["web"]


def test_rights_safe_removes_the_web_adapter_and_nothing_else() -> None:
    """5.2: the policy switch is web-search on/off, in one config line."""
    strict = _sourcing(asset_policy="rights_safe")
    assert "web" not in strict.sources
    assert set(strict.sources) == {"commons", "openverse"}
    assert tuple(strict.order) == assets.parse_order(
        config.DEFAULT_ASSET_SOURCES
    )  # the order itself is untouched


def test_the_judge_follows_relevance_judge() -> None:
    assert _sourcing().judge is None
    assert isinstance(_sourcing(relevance_judge="fake").judge, assets.FakeRelevanceJudge)
    api = _sourcing(relevance_judge="api", relevance_judge_model="claude-sonnet-5").judge
    assert isinstance(api, assets.VisionJudge)
    assert api.model == "claude-sonnet-5"


class Counting(assets.FakeImageSource):
    """A fake that appends its own name to one shared list every time it is asked, so
    a test can read the order the ladder walked."""

    def __init__(self, origin: str, calls: list[str], *, found: bool = False) -> None:
        super().__init__(origin, nothing_found=not found)  # pyright: ignore[reportArgumentType]
        self._calls = calls

    def search(self, query: str, n: int) -> list[Candidate]:
        self._calls.append(str(self.origin))
        return super().search(query, n)


def test_the_ladder_walks_the_configured_order_and_stops_at_the_first_hit(
    tmp_path: Path,
) -> None:
    """5.1: every source is tried in the configured order, and the one that answers
    ends the walk; changing the order is a config edit, never a code change."""
    calls: list[str] = []
    sources: dict[str, assets.ImageSource] = {
        name: Counting(name, calls, found=name == "pexels")
        for name in assets.DEFAULT_ORDER
    }
    manifest = _run(tmp_path, [_beat(1, "concept")], sources=sources)
    assert calls == ["web", "commons", "openverse", "pexels"]
    assert manifest.assets[0].origin == "pexels"


def test_a_configured_order_the_operator_reversed_is_the_order_walked(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    sources: dict[str, assets.ImageSource] = {
        name: Counting(name, calls) for name in assets.DEFAULT_ORDER
    }
    sources["commons"] = Counting("commons", calls, found=True)
    assets.source_assets(
        _plan([_beat(1, "concept")]), [], "any", spec=SPEC, sources=sources,
        order=("pixabay", "openverse", "commons", "web"), job_dir=_job_dir(tmp_path),
        clock=_clock,
    )  # fmt: skip
    assert calls == ["pixabay", "openverse", "commons"]


def test_a_library_candidates_licence_and_author_reach_the_rights_row(
    tmp_path: Path,
) -> None:
    """5.4: what the API said about the picture is recorded, never filtered on."""

    class Licensed(assets.FakeImageSource):
        def search(self, query: str, n: int) -> list[Candidate]:
            return [
                c.model_copy(update={"licence": "CC BY-SA 4.0", "author": "Ankit Sharma"})
                for c in super().search(query, n)
            ]

    job = _job_dir(tmp_path)
    beats = [_beat(1, "concept")]
    manifest = _run(tmp_path, beats, sources={"commons": Licensed("commons")}, job=job)
    (row,) = rights.rows(manifest, _plan(beats).picture)
    assert (row.origin, row.licence, row.author) == ("commons", "CC BY-SA 4.0", "Ankit Sharma")
    assert row.page_url and row.source_url
    assert "Photo: Ankit Sharma via" in rights.credits([row])


def test_a_source_that_reports_no_licence_records_unknown(tmp_path: Path) -> None:
    manifest = _run(tmp_path, [_beat(1, "concept")],
                    sources={"openverse": assets.FakeImageSource("openverse")})  # fmt: skip
    assert manifest.assets[0].licence == "unknown"


# --- the search allowance (5.6) ----------------------------------------------------------


def test_queries_are_counted_against_the_styles_search_max_queries(tmp_path: Path) -> None:
    """5.6: a query actually sent counts; one answered from `work/assets/` does not."""
    searching = assets.Searching(max_queries=SPEC.budget.search_max_queries)
    job = _job_dir(tmp_path)
    beats = [_beat(1, "concept"), _beat(2, "entity")]
    first = assets.source_assets(
        _plan(beats), [], "any", spec=SPEC, sources={"web": assets.FakeImageSource("web")},
        job_dir=job, searching=searching, clock=_clock,
    )  # fmt: skip
    assert (first.search_queries, first.search_max) == (2, SPEC.budget.search_max_queries)
    again = assets.source_assets(
        _plan(beats), [], "any", spec=SPEC, sources={"web": assets.FakeImageSource("web")},
        job_dir=job, searching=assets.Searching(max_queries=60), clock=_clock,
    )  # fmt: skip
    assert again.search_queries == 0  # every query came from the cache


def test_passing_the_search_allowance_is_a_note_and_never_a_skipped_beat(
    tmp_path: Path,
) -> None:
    """11.3: cost never degrades quality, and every source shipped so far is free, so
    the allowance is advisory: the beats are still searched, and the job says so."""
    log: list[str] = []
    beats = [_beat(i, "concept") for i in (1, 2, 3)]
    manifest = assets.source_assets(
        _plan(beats), [], "any", spec=SPEC, sources={"web": assets.FakeImageSource("web")},
        job_dir=_job_dir(tmp_path), searching=assets.Searching(max_queries=1),
        log=log.append, clock=_clock,
    )  # fmt: skip
    assert manifest.search_queries == 3
    assert [b.fallback_rung for b in manifest.beats] == [0, 0, 0]
    assert sum("search_max_queries (1)" in line for line in log) == 1


def test_rights_safe_never_calls_web(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    commons = assets.FakeImageSource("commons")
    manifest = _run(tmp_path, [_beat(1, "concept")], sources={"web": web, "commons": commons},
                    policy="rights_safe")  # fmt: skip
    assert web.searches == 0
    assert manifest.assets[0].origin == "commons"


# --- the fake source (12.1) -------------------------------------------------------------


def test_fake_search_returns_fake_urls_at_the_requested_size() -> None:
    fake = assets.FakeImageSource("web", size=(1600, 900), sizes={"tall": (1080, 1920)})
    wide = fake.search("a wide thing", 3)
    tall = fake.search("tall", 1)
    assert len(wide) == 3 and len(tall) == 1
    assert all(c.url.startswith("https://fake.invalid/web/") for c in wide)
    assert (wide[0].width, wide[0].height) == (1600, 900)
    assert (tall[0].width, tall[0].height) == (1080, 1920)
    assert fake.searches == 2


def test_fake_fetch_writes_a_png_of_the_candidate_size(tmp_path: Path) -> None:
    fake = assets.FakeImageSource("commons", size=(800, 1200))
    (candidate,) = fake.search("x", 1)
    path = fake.fetch(candidate, tmp_path / "image")
    with Image.open(path) as image:
        assert image.format == "PNG"
        assert image.size == (800, 1200)
    assert fake.fetches == 1


def test_fake_nothing_found_modes() -> None:
    assert assets.FakeImageSource("web", nothing_found=True).search("x", 3) == []
    fake = assets.FakeImageSource("web", nothing_for={"nope"})
    assert fake.search("nope", 3) == []
    assert len(fake.search("yes", 3)) == 3


# --- classification from real dimensions (5.3) ----------------------------------------


@pytest.mark.parametrize(
    ("size", "planned", "expected"),
    [
        ((1080, 1920), "photo", ("photo", False)),
        ((1079, 1920), "photo", ("card", True)),  # a 1079 px portrait becomes a card
        ((1080, 1279), "photo", ("card", True)),  # covering 1920 would upscale > 1.5x
        ((1080, 1280), "photo", ("photo", False)),  # exactly 1.5x
        ((2000, 3000), "photo", ("photo", False)),
        ((1920, 1080), "photo", ("card", True)),  # landscape
        ((1500, 1500), "photo", ("card", True)),  # square is not portrait
        ((1080, 1920), "card", ("card", False)),  # the planner asked for a card
        ((640, 480), "card", ("card", False)),
    ],
)
def test_classify(size: tuple[int, int], planned: str, expected: tuple[str, bool]) -> None:
    assert assets.classify(*size, planned=planned, origin="commons") == expected  # pyright: ignore[reportArgumentType]


def test_web_images_are_always_cards() -> None:
    assert assets.classify(1080, 1920, planned="photo", origin="web") == ("card", True)


def test_classification_reads_the_fetched_file_not_the_reported_size(tmp_path: Path) -> None:
    class Liar(assets.FakeImageSource):
        """Reports 1080x1920 in search, delivers its real size on fetch."""

        def search(self, query: str, n: int) -> list[Candidate]:
            return [c.model_copy(update={"width": 1080, "height": 1920})
                    for c in super().search(query, n)]  # fmt: skip

        def fetch(self, candidate: Candidate, dest: Path) -> Path:
            real = {"width": self.size[0], "height": self.size[1]}
            return super().fetch(candidate.model_copy(update=real), dest)

    manifest = _run(tmp_path, [_beat(1, "concept")],
                    sources={"commons": Liar("commons", size=(1600, 900))})  # fmt: skip
    beat = manifest.beats[0]
    assert (beat.treatment, beat.treatment_downgraded) == ("card", True)
    assert (manifest.assets[0].width, manifest.assets[0].height) == (1600, 900)


# --- the ladder (4.4) -------------------------------------------------------------------


def _write_png(path: Path, size: tuple[int, int] = (1080, 1920)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (90, 40, 20)).save(path, format="PNG")
    return path


def _generator(calls: list[str]) -> assets.Generate:
    def generate(beat: Beat, dest: Path) -> assets.GeneratedImage | None:
        calls.append(beat.id)
        return assets.GeneratedImage(
            path=_write_png(dest / "generated.png"),
            generated=Generated(model="fake-gen", prompt=f"prompt for {beat.query}",
                                render="photoreal", depicts="scene"),
        )  # fmt: skip

    return generate


def test_rung_0_query_found(tmp_path: Path) -> None:
    manifest = _run(tmp_path, [_beat(1, "concept")])
    (beat,) = manifest.beats
    assert (beat.asset_id, beat.fallback_rung, beat.stamp) == ("a1", 0, None)
    assert manifest.assets[0].source_url.startswith("https://fake.invalid/web/")


def test_rung_1_query_fallback(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web", nothing_for={"query 1"})
    manifest = _run(tmp_path, [_beat(1, "concept")], sources={"web": web})
    assert manifest.beats[0].fallback_rung == 1
    assert "fallback" in manifest.assets[0].source_url


def test_every_source_is_tried_with_query_before_the_fallback(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web", nothing_for={"query 1"})
    commons = assets.FakeImageSource("commons")
    manifest = _run(tmp_path, [_beat(1, "concept")], sources={"web": web, "commons": commons})
    assert (manifest.beats[0].fallback_rung, manifest.assets[0].origin) == (0, "commons")


def test_rung_2_generates_when_search_finds_nothing(tmp_path: Path) -> None:
    calls: list[str] = []
    empty = assets.FakeImageSource("web", nothing_found=True)
    manifest = _run(tmp_path, [_beat(1, "concept")], sources={"web": empty},
                    generate=_generator(calls))  # fmt: skip
    assert calls == ["b01"]
    assert manifest.beats[0].fallback_rung == 2
    record = manifest.assets[0]
    assert record.origin == "generated" and record.generated is not None
    assert record.source_url == ""


def test_rung_2_is_a_no_op_without_a_generator(tmp_path: Path) -> None:
    empty = assets.FakeImageSource("web", nothing_found=True)
    manifest = _run(tmp_path, [_beat(1, "concept")], sources={"web": empty})
    assert manifest.beats[0].fallback_rung == 4


def test_rung_3_redresses_the_nearest_earlier_same_kind_asset(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web", nothing_for={"query 3", "fallback 3"})
    beats = [_beat(1, "concept"), _beat(2, "entity"), _beat(3, "concept")]
    manifest = _run(tmp_path, beats, sources={"web": web})
    first, _, rescued = manifest.beats
    assert (rescued.asset_id, rescued.fallback_rung, rescued.redressed_from) == ("a1", 3, "a1")
    assert rescued.crop != first.crop  # never the identical framing twice
    assert rescued.stamp  # the rescue reads as deliberate: a stamp of the key word
    assert manifest.aliases["a3"] == "a1"
    assert [a.id for a in manifest.assets] == ["a1", "a2"]


def test_each_redress_of_one_asset_gets_a_new_crop(tmp_path: Path) -> None:
    missing = {"query 2", "fallback 2", "query 3", "fallback 3"}
    web = assets.FakeImageSource("web", nothing_for=missing)
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept")]
    crops = [b.crop for b in _run(tmp_path, beats, sources={"web": web}).beats]
    assert len({c.model_dump_json() for c in crops}) == 3


def test_rung_4_pip_over_gradient_when_nothing_earlier(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web", nothing_for={"query 2", "fallback 2"})
    beats = [_beat(1, "entity"), _beat(2, "concept", event=Event(kind="stamp", text="WHY"))]
    manifest = _run(tmp_path, beats, sources={"web": web})
    rescued = manifest.beats[1]
    assert (rescued.asset_id, rescued.treatment, rescued.fallback_rung) == (None, "gradient", 4)
    assert rescued.stamp == "WHY"
    assert manifest.aliases["a2"] is None


def test_every_rung_in_order_on_one_plan(tmp_path: Path) -> None:
    calls: list[str] = []
    web = assets.FakeImageSource(
        "web", nothing_for={"query 2", "query 3", "fallback 3", "query 4", "fallback 4",
                            "query 5", "fallback 5"},
    )  # fmt: skip
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept"),
             _beat(4, "concept"), _beat(5, "entity")]  # fmt: skip

    def only_b03(beat: Beat, dest: Path) -> assets.GeneratedImage | None:
        return _generator(calls)(beat, dest) if beat.id == "b03" else None

    manifest = _run(tmp_path, beats, sources={"web": web}, generate=only_b03)
    assert [b.fallback_rung for b in manifest.beats] == [0, 1, 2, 3, 4]


def test_never_a_blank_beat(tmp_path: Path) -> None:
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(i, "concept") for i in range(1, 7)]
    manifest = _run(tmp_path, beats, sources={"web": empty})
    assert [b.beat_id for b in manifest.beats] == [b.id for b in beats]
    assert all(b.asset_id is not None or b.treatment == "gradient" for b in manifest.beats)


def test_rescued_max_scales_the_style_number_to_the_runtime(tmp_path: Path) -> None:
    sixty = _run(tmp_path, [_beat(i, "concept") for i in range(1, 13)])
    assert (sixty.runtime_s, sixty.rescued_max) == (60.0, 4)
    six = _run(tmp_path / "six", [_beat(1, "concept", length=6.0)])
    assert six.rescued_max == 1  # ceil(4 x 0.1)


def test_fifth_rescue_is_counted(tmp_path: Path) -> None:
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(i, "concept") for i in range(1, 13)]
    manifest = _run(tmp_path, beats, sources={"web": empty})
    assert manifest.rescued == 12 > manifest.rescued_max


# --- source_intent and subject kinds (4.2, 5.1) ----------------------------------------


def test_presenter_hook_and_finale_beats_are_not_sourced(tmp_path: Path) -> None:
    beats = [
        _beat(1, None, kind="presenter_full", mode="full"),
        _beat(2, None, kind="hook_cards", mode="off", asset="a3"),
        _beat(3, "concept"),
        _beat(4, None, kind="finale", mode="off", asset="a3"),
    ]
    manifest = _run(tmp_path, beats, hook_cards=["a3"])
    assert [b.beat_id for b in manifest.beats] == ["b03"]


def test_planned_reuse_of_an_asset_id_fetches_once(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept", asset="a1"), _beat(2, "concept", asset="a1")]
    manifest = _run(tmp_path, beats, sources={"web": web})
    assert web.searches == 1
    assert [b.asset_id for b in manifest.beats] == ["a1", "a1"]
    assert [b.fallback_rung for b in manifest.beats] == [0, 0]
    assert len(manifest.assets) == 1


def test_reuse_intent_takes_the_nearest_earlier_asset_without_searching(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept"), _beat(2, "entity"), _beat(3, "concept", intent="reuse")]
    manifest = _run(tmp_path, beats, sources={"web": web})
    assert web.searches == 2
    assert (manifest.beats[2].asset_id, manifest.beats[2].fallback_rung) == ("a2", 0)
    assert manifest.aliases["a3"] == "a2"


def test_number_and_quote_beats_reuse_the_previous_asset(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept"), _beat(2, "number", intent="generate"),
             _beat(3, "quote", intent="search")]  # fmt: skip
    calls: list[str] = []
    manifest = _run(tmp_path, beats, sources={"web": web}, generate=_generator(calls))
    assert web.searches == 1 and calls == []  # the label forbids search and generation
    assert [b.asset_id for b in manifest.beats] == ["a1", "a1", "a1"]
    assert [a.id for a in manifest.assets] == ["a1"]


def test_generate_intent_on_a_concept_beat_generates_first(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    calls: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "concept", intent="generate")], sources={"web": web},
                    generate=_generator(calls))  # fmt: skip
    assert calls == ["b01"] and web.searches == 0
    assert (manifest.beats[0].fallback_rung, manifest.assets[0].origin) == (2, "generated")


def test_generate_intent_without_a_generator_still_searches(tmp_path: Path) -> None:
    manifest = _run(tmp_path, [_beat(1, "concept", intent="generate")])
    assert (manifest.beats[0].fallback_rung, manifest.assets[0].origin) == (0, "web")


def test_entity_beats_always_search_first(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    calls: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "entity", intent="generate")], sources={"web": web},
                    generate=_generator(calls))  # fmt: skip
    assert calls == [] and web.searches == 1
    assert manifest.assets[0].origin == "web"


# --- owner references first (1.3, 5.1) -------------------------------------------------


def _reference(job: Path, ref_id: str, caption: str, size: tuple[int, int]) -> ReferenceRecord:
    rel = f"refs/{ref_id}.png"
    _write_png(job / "input" / rel, size)
    return ReferenceRecord(
        id=ref_id, file=rel, kind="image", caption=caption, original_name=f"{ref_id}.png",
        width=size[0], height=size[1], size_bytes=(job / "input" / rel).stat().st_size,
    )  # fmt: skip


def test_owner_reference_wins_when_the_query_matches_its_caption(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    ref = _reference(job, "r1", "India Gate at dusk", (1920, 1080))
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "entity", kind="card", query="India Gate Delhi archival photo")]
    manifest = _run(tmp_path, beats, sources={"web": web}, references=[ref], job=job)
    assert web.searches == 0
    record = manifest.assets[0]
    assert (record.origin, record.licence, record.file) == ("owner_supplied", "owner",
                                                            "input/refs/r1.png")  # fmt: skip
    assert manifest.beats[0].asset_id == "a1"


def test_a_reference_whose_caption_shares_no_word_is_not_used(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    ref = _reference(job, "r1", "my photo of the sea", (1920, 1080))
    manifest = _run(tmp_path, [_beat(1, "entity", query="India Gate photo")], references=[ref],
                    job=job)  # fmt: skip
    assert manifest.assets[0].origin == "web"


def test_a_beat_naming_a_reference_id_uses_it(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    ref = _reference(job, "r1", "unrelated caption", (1080, 1920))
    beats = [_beat(1, "concept", asset="r1", query="something else")]
    manifest = _run(tmp_path, beats, references=[ref], job=job)
    assert (manifest.beats[0].asset_id, manifest.assets[0].origin) == ("r1", "owner_supplied")


def test_number_beat_may_use_a_matching_reference(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    ref = _reference(job, "r1", "price tag 499 rupees", (1920, 1080))
    beats = [_beat(1, "concept"), _beat(2, "number", query="499 rupees")]
    manifest = _run(tmp_path, beats, references=[ref], job=job)
    record = manifest.asset(manifest.beats[1].asset_id or "")
    assert record is not None
    assert (record.origin, record.file) == ("owner_supplied", "input/refs/r1.png")


def test_a_clip_reference_is_a_still_frame(tmp_path: Path, media: Media) -> None:
    job = _job_dir(tmp_path)
    clip = media.clip(duration_s=1.0, width=1280, height=720, audio=False)
    rel = "refs/c1.mov"
    (job / "input" / "refs").mkdir(parents=True)
    (job / "input" / rel).write_bytes(clip.read_bytes())
    ref = ReferenceRecord(id="c1", file=rel, kind="clip", caption="factory floor",
                          original_name="c1.mov", width=1280, height=720,
                          size_bytes=clip.stat().st_size)  # fmt: skip
    manifest = _run(tmp_path, [_beat(1, "entity", query="the factory")], references=[ref],
                    job=job)  # fmt: skip
    record = manifest.assets[0]
    assert (record.kind, record.origin) == ("clip_frame", "owner_supplied")
    assert (record.width, record.height) == (1280, 720)
    assert record.file.endswith(".png")


# --- the per-job cache (5.6) -------------------------------------------------------------


def test_cache_key_is_sha256_of_query_plus_source() -> None:
    expected = hashlib.sha256(b"query 1" + b"web").hexdigest()
    assert assets.cache_key("query 1", "web") == expected


def test_rerunning_the_step_fetches_nothing(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    web = assets.FakeImageSource("web", nothing_for={"query 2"})
    beats = [_beat(1, "concept"), _beat(2, "concept")]
    first = _run(tmp_path, beats, sources={"web": web}, job=job)
    counts = (web.searches, web.fetches)
    again = _run(tmp_path, beats, sources={"web": web}, job=job)
    assert (web.searches, web.fetches) == counts
    # The manifest is the same decision, with one difference: the re-run spent nothing.
    assert again == first.model_copy(update={"search_queries": 0})
    assert (first.search_queries, again.search_queries) == (3, 0)
    assert (job / "work" / "assets" / assets.cache_key("query 1", "web")).is_dir()


def test_a_cached_nothing_found_is_not_searched_again(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    web = assets.FakeImageSource("web", nothing_found=True)
    _run(tmp_path, [_beat(1, "concept")], sources={"web": web}, job=job)
    searches = web.searches
    _run(tmp_path, [_beat(1, "concept")], sources={"web": web}, job=job)
    assert web.searches == searches


# --- the asset records ------------------------------------------------------------------


def test_records_carry_real_dimensions_hash_and_fetch_time(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    manifest = _run(tmp_path, [_beat(1, "concept")],
                    sources={"web": assets.FakeImageSource("web", size=(1200, 800))}, job=job)
    record = manifest.assets[0]
    data = (job / record.file).read_bytes()
    assert record.sha256 == hashlib.sha256(data).hexdigest()
    assert (record.width, record.height) == (1200, 800)
    assert record.fetched_at == NOW.isoformat()
    assert record.file.startswith("work/assets/")


def test_step_writes_the_manifest(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    manifest = _run(tmp_path, [_beat(1, "concept")], job=job)
    assets.write_manifest(job, manifest)
    loaded = assets.load_manifest(job)
    assert loaded == manifest
    assert json.loads((job / "work" / "assets.json").read_text(encoding="utf-8"))["assets"]


# --- the hard rejects and the judge inside the step (5.2; ticket 017) --------------------


class Scripted(assets.ImageSource):
    """A source answering fixed candidates, counting what was fetched and judged."""

    def __init__(self, origin: str, candidates: Sequence[Candidate]) -> None:
        self.origin = origin  # pyright: ignore[reportAttributeAccessIssue]
        self.candidates = list(candidates)
        self.fetched: list[str] = []
        self.thumbed: list[str] = []
        self.searches = 0

    def search(self, query: str, n: int) -> list[Candidate]:
        self.searches += 1
        return self.candidates[:n]

    def thumbnail(self, candidate: Candidate) -> bytes | None:
        self.thumbed.append(candidate.url)
        return None

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        self.fetched.append(candidate.url)
        size = (candidate.width or 1600, candidate.height or 1200)
        path = dest.with_suffix(".png")
        _write_png(path, size)
        return path


class Scoring(assets.RelevanceJudge):
    """Scores by candidate URL, and records what it was told about the beat."""

    def __init__(self, scores: dict[str, int], *, default: int = 0) -> None:
        self.model = "scripted"
        self.scores = scores
        self.default = default
        self.asked: list[tuple[str, str, str, tuple[str, ...]]] = []

    def score(self, query: str, subject_kind: str, topic: str,
              thumbs: Sequence[assets.Thumb]) -> list[assets.Verdict]:  # fmt: skip
        self.asked.append((query, subject_kind, topic, tuple(t.candidate.url for t in thumbs)))
        return [assets.Verdict(self.scores.get(t.candidate.url, self.default)) for t in thumbs]


def _candidates(*spec: tuple[str, int, int]) -> list[Candidate]:
    return [
        Candidate(url=f"https://e.example/{name}.png", page_url=f"https://e.example/{name}",
                  width=w, height=h)
        for name, w, h in spec
    ]  # fmt: skip


def _judging(scores: dict[str, int], *, max_calls: int = 40) -> tuple[assets.Judging, Scoring]:
    judge = Scoring({f"https://e.example/{k}.png": v for k, v in scores.items()})
    return assets.Judging(judge=judge, max_calls=max_calls), judge


def test_the_hard_rejects_run_before_the_judge_is_asked_anything(tmp_path: Path) -> None:
    """5.2: a candidate too small or too wide never reaches the judge, and rejecting
    it is never rejecting the beat."""
    source = Scripted("web", _candidates(
        ("small", 640, 480), ("wide", 3600, 900), ("good", 1600, 1200),
    ))  # fmt: skip
    book, judge = _judging({"good": 3})
    log: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source},
                    judging=book, log=log)  # fmt: skip
    assert judge.asked[0][3] == ("https://e.example/good.png",)
    assert source.fetched == ["https://e.example/good.png"]
    assert manifest.beats[0].fallback_rung == 0
    assert log[:2] == [
        "sourcing: https://e.example/small.png rejected: short side 480 px < 800 px",
        "sourcing: https://e.example/wide.png rejected: aspect 4.00:1 > 3:1",
    ]


def test_the_best_candidate_at_two_or_more_wins_ties_by_source_order(tmp_path: Path) -> None:
    source = Scripted("web", _candidates(
        ("first", 1600, 1200), ("best", 1600, 1200), ("tied", 1600, 1200),
    ))  # fmt: skip
    book, _ = _judging({"first": 2, "best": 3, "tied": 3})
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=book)
    assert source.fetched == ["https://e.example/best.png"]  # 3 beats 2; `best` before `tied`
    record = manifest.assets[0]
    assert record.judge is not None
    assert (record.judge.model, record.judge.score) == ("scripted", 3)
    assert manifest.beats[0].judge_skipped is False


def test_every_candidate_under_two_falls_to_the_next_source(tmp_path: Path) -> None:
    """5.2: all < 2 -> the next source in the list -> the 4.4 ladder."""
    web = Scripted("web", _candidates(("weak", 1600, 1200)))
    commons = Scripted("commons", _candidates(("strong", 1600, 1200)))
    book, _ = _judging({"weak": 1, "strong": 3})
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": web, "commons": commons},
                    judging=book)  # fmt: skip
    assert web.fetched == []
    assert commons.fetched == ["https://e.example/strong.png"]
    assert manifest.assets[0].origin == "commons"


def test_nothing_the_judge_accepts_anywhere_ends_on_the_ladder(tmp_path: Path) -> None:
    source = Scripted("web", _candidates(("weak", 1600, 1200)))
    book, _ = _judging({"weak": 1})
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=book)
    assert source.fetched == []
    assert (manifest.beats[0].fallback_rung, manifest.beats[0].treatment) == (4, "gradient")


def test_the_judge_is_told_the_query_subject_kind_and_the_briefs_topic(tmp_path: Path) -> None:
    source = Scripted("web", _candidates(("good", 1600, 1200)))
    book, judge = _judging({"good": 3})
    _run(tmp_path, [_beat(1, "entity", query="India Gate Delhi")], sources={"web": source},
         judging=book, topic="Why Delhi built India Gate")  # fmt: skip
    assert judge.asked[0][:3] == ("India Gate Delhi", "entity", "Why Delhi built India Gate")


def test_a_candidate_whose_download_is_refused_is_dropped_for_the_next_one(
    tmp_path: Path,
) -> None:
    """5.2: a rejection is of the candidate, never of the beat."""

    class Refusing(Scripted):
        def fetch(self, candidate: Candidate, dest: Path) -> Path:
            if "refused" in candidate.url:
                self.fetched.append(candidate.url)
                raise assets.SourceError(f"{candidate.url} rejected: the body is not an image")
            return super().fetch(candidate, dest)

    source = Refusing("web", _candidates(("refused", 1600, 1200), ("good", 1600, 1200)))
    book, _ = _judging({"refused": 3, "good": 2})
    log: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=book,
                    log=log)  # fmt: skip
    assert source.fetched == ["https://e.example/refused.png", "https://e.example/good.png"]
    assert manifest.beats[0].fallback_rung == 0
    assert log == ["sourcing: https://e.example/refused.png rejected: the body is not an image"]


def test_a_downloaded_file_smaller_than_it_claimed_is_dropped(tmp_path: Path) -> None:
    """5.2: the real dimensions are the only size a source cannot misreport."""

    class Lying(Scripted):
        def fetch(self, candidate: Candidate, dest: Path) -> Path:
            self.fetched.append(candidate.url)
            path = dest.with_suffix(".png")
            _write_png(path, (400, 300) if "lying" in candidate.url else (1600, 1200))
            return path

    source = Lying("web", _candidates(("lying", 1600, 1200), ("honest", 1600, 1200)))
    book, _ = _judging({"lying": 3, "honest": 2})
    log: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=book,
                    log=log)  # fmt: skip
    assert manifest.assets[0].source_url == "https://e.example/honest.png"
    assert log == ["sourcing: https://e.example/lying.png rejected: short side 300 px < 800 px"]


def test_verdicts_are_cached_by_url_across_beats(tmp_path: Path) -> None:
    """5.6: the same candidate on a second beat is never paid for twice."""
    source = Scripted("web", _candidates(("good", 1600, 1200)))
    book, judge = _judging({"good": 3})
    beats = [_beat(1, "entity", query="one"), _beat(2, "entity", query="two")]
    manifest = _run(tmp_path, beats, sources={"web": source}, judging=book)
    assert source.searches == 2  # two queries, two searches
    assert len(judge.asked) == 1  # one judge call: the second beat's candidate was cached
    assert manifest.judge_calls == 1


def test_the_judge_budget_stops_further_calls_and_the_beat_records_it(tmp_path: Path) -> None:
    """5.2 / 5.6: `judge_max_calls` spent means unjudged beats, never failed beats."""
    source = assets.FakeImageSource("web")  # a candidate set of its own per query
    judge = Scoring({}, default=3)
    book = assets.Judging(judge=judge, max_calls=1)
    beats = [_beat(i, "entity", query=f"q{i}") for i in (1, 2, 3)]
    log: list[str] = []
    manifest = _run(tmp_path, beats, sources={"web": source}, judging=book, log=log)
    assert len(judge.asked) == 1
    assert [b.judge_skipped for b in manifest.beats] == [False, True, True]
    assert (manifest.judge_calls, manifest.judge_max) == (1, 1)
    assert all(b.fallback_rung == 0 for b in manifest.beats)  # the ladder carried on
    assert log[-1].startswith("judge: the style's judge_max_calls (1) is spent")


def test_with_no_judge_the_first_candidate_wins_and_the_beat_is_unjudged(
    tmp_path: Path,
) -> None:
    """016's behaviour, kept: `RELEVANCE_JUDGE=none` changes nothing but the record."""
    source = Scripted("web", _candidates(("first", 1600, 1200), ("second", 1600, 1200)))
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source})
    assert source.fetched == ["https://e.example/first.png"]
    assert source.thumbed == []
    assert manifest.beats[0].judge_skipped is True
    assert manifest.assets[0].judge is None
    assert (manifest.judge_calls, manifest.judge_max) == (0, 0)


def test_a_cached_search_makes_no_judge_call_at_all(tmp_path: Path) -> None:
    """5.6: a plan retry or a re-render searches, judges and fetches nothing."""
    job = _job_dir(tmp_path)
    source = Scripted("web", _candidates(("good", 1600, 1200)))
    book, judge = _judging({"good": 3})
    first = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=book, job=job)
    again_book, again_judge = _judging({"good": 3})
    again = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=again_book,
                 job=job)  # fmt: skip
    assert (len(judge.asked), len(again_judge.asked)) == (1, 0)
    assert source.searches == 1
    assert again.assets[0].judge == first.assets[0].judge
    assert again.beats[0].judge_skipped is False


def test_the_verdict_reaches_the_rights_row(tmp_path: Path) -> None:
    """5.2 / 5.4: every rights row carries `judge: {model, score, reasons}`."""
    source = Scripted("web", _candidates(("good", 1600, 1200)))
    judge = Scoring({"https://e.example/good.png": 2})
    book = assets.Judging(judge=judge, max_calls=40)
    job = _job_dir(tmp_path)
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source}, judging=book, job=job)
    rights.write(job, manifest, _plan([_beat(1, "entity")]).picture)
    rows = rights.load(job)
    assert rows is not None
    assert rows[0].judge is not None
    assert (rows[0].judge.model, rows[0].judge.score) == ("scripted", 2)


def test_the_topic_line_is_the_briefs_first_line(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    assert assets.topic_line(job) == ""
    (job / "input" / "brief.md").write_text(
        "\n# Topic: why India Gate was built\n\nMust-say: 1931.\n", encoding="utf-8"
    )
    assert assets.topic_line(job) == "Topic: why India Gate was built"
