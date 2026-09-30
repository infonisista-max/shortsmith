"""assets: the `sourcing` step with only the fake image source (ticket 016).

Source order and the rights-safe policy (5.1, 5.2), the fake source, aspect
classification from real dimensions (5.3), the fallback ladder with its rung per beat
and re-dressed reuse (4.4), `source_intent` and the per-subject-kind source rules
(4.2, 5.1), owner references first (1.3), and the per-job cache (5.6)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
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
    PicturePlan,
    ReferenceRecord,
    SoundStory,
    Span,
    ValidatedPlan,
)
from shortsmith.ledger import Ledger
from tests.conftest import Media

EXPLAINER = styles.load_all(render.registry())["explainer"]
# 055: the explainer's first two beats are the opening, with their own ladder (best
# score across every source, generation past the cap, never a rescue). The ladder tests
# below exercise the body's rungs on b01 and b02, so the shared spec switches the
# opening off; the opening's own tests pass `spec=EXPLAINER`.
SPEC = EXPLAINER.model_copy(deep=True)
SPEC.beats.opening_beats_min = 0
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


def _plan(beats: Sequence[Beat]) -> ValidatedPlan:
    end = beats[-1].end
    picture = PicturePlan(
        prompt_version="t",
        cut=CutPlan(keep=[Span(start=0.0, end=end)]),
        beats=list(beats),
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
    generating: assets.Generating | None = None,
    job: Path | None = None,
    judging: assets.Judging | None = None,
    topic: str = "",
    log: list[str] | None = None,
    spec: styles.StyleSpec = SPEC,
) -> assets.AssetManifest:
    return assets.source_assets(
        _plan(beats),
        list(references),
        policy,  # pyright: ignore[reportArgumentType]
        spec=spec,
        sources=sources if sources is not None else {"web": assets.FakeImageSource("web")},
        order=assets.DEFAULT_ORDER,
        job_dir=job or _job_dir(tmp_path),
        generating=generating,
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
    assert sourcing.generator is None  # IMAGE_GEN=none makes rung 2 a no-op (5.5)
    # 062: the free sticker fetch, cached under the data dir.
    assert sourcing.stickers is not None
    assert sourcing.stickers.cache_dir == _settings().shortsmith_data_dir / "cache" / "stickers"


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


def test_image_gen_names_the_generator_of_rung_2() -> None:
    """5.5: `none` is a no-op rung, `fake` a local run, `gemini` the REST adapter."""
    assert _sourcing(image_gen="fake").generator is not None
    gemini = _sourcing(
        image_gen="gemini", gemini_api_key="g_x", image_gen_model="gemini-x"
    ).generator
    assert isinstance(gemini, assets.GeminiImageGenerator)
    assert gemini.model == "gemini-x"
    assert gemini.endpoint == config.Settings(_env_file=None).image_gen_endpoint  # pyright: ignore[reportCallIssue]


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


FULL_BLEED_MAX = EXPLAINER.broll.full_bleed_max_upscale  # 057: 2.0, read from the style


@pytest.mark.parametrize(
    ("size", "planned", "expected"),
    [
        ((1080, 1920), "photo", ("photo", False)),
        ((1079, 1920), "photo", ("photo", False)),  # 057: width is judged after the upscale
        ((1080, 1279), "photo", ("photo", False)),  # 1.50x on the height, under 2.0
        ((1080, 1280), "photo", ("photo", False)),
        ((1000, 1406), "photo", ("photo", False)),  # run03's owner photo: 1.37x
        ((819, 1024), "photo", ("photo", False)),  # run03's main portrait: 1.875x
        ((540, 960), "photo", ("photo", False)),  # exactly 2.0x
        ((540, 959), "photo", ("card", True)),  # one pixel over 2.0x on the height
        ((500, 900), "photo", ("card", True)),  # needs 2.16x
        ((2000, 3000), "photo", ("photo", False)),
        ((1920, 1080), "photo", ("card", True)),  # landscape stays a card
        ((1600, 1169), "photo", ("card", True)),  # run03's b19
        ((1024, 632), "photo", ("card", True)),  # run03's b22
        ((1500, 1500), "photo", ("photo", False)),  # 057: square counts as portrait
        ((1080, 1920), "card", ("card", False)),  # the planner asked for a card
        ((640, 480), "card", ("card", False)),
        ((1080, 1920), "auto", ("photo", False)),
        ((640, 480), "auto", ("card", False)),  # `auto` never records a downgrade
    ],
)
def test_classify(size: tuple[int, int], planned: str, expected: tuple[str, bool]) -> None:
    assert assets.classify(*size, planned=planned, max_upscale=FULL_BLEED_MAX) == expected  # pyright: ignore[reportArgumentType]


def test_the_full_bleed_limit_is_the_styles_not_a_constant() -> None:
    """057: the 2.0 lives in `broll.full_bleed_max_upscale`; a stricter style (1.5, the
    old 5.3 line) turns the 1.875x portrait back into a card."""
    assert FULL_BLEED_MAX == 2.0
    assert assets.full_bleed(819, 1024, max_upscale=FULL_BLEED_MAX)
    assert not assets.full_bleed(819, 1024, max_upscale=1.5)
    assert assets.classify(819, 1024, planned="photo", max_upscale=1.5) == ("card", True)


def test_a_web_image_goes_full_bleed_like_any_other_origin(tmp_path: Path) -> None:
    """057 (2), amending 5.1: the origin no longer matters - a 1000x1406 web image
    covers the frame at 1.37x and is drawn full-bleed under the Ken Burns; a landscape
    web image stays a card, exactly as before."""
    web = assets.FakeImageSource(
        "web", sizes={"query 1": (1000, 1406), "query 2": (1600, 1000)}
    )
    manifest = _run(tmp_path, [_beat(1, "entity"), _beat(2, "entity")], sources={"web": web})
    first, second = manifest.beats
    assert manifest.assets[0].origin == "web"
    assert (first.treatment, first.treatment_downgraded) == ("photo", False)
    assert (second.treatment, second.treatment_downgraded) == ("card", True)


def test_source_assets_reads_the_full_bleed_limit_from_the_spec(tmp_path: Path) -> None:
    """057: the same 819x1024 portrait is a photo under the explainer's 2.0 and a card
    under a spec copy that says 1.5."""
    strict = SPEC.model_copy(deep=True)
    strict.broll.full_bleed_max_upscale = 1.5
    web = assets.FakeImageSource("web", size=(819, 1024))
    roomy = _run(tmp_path / "roomy", [_beat(1, "entity")], sources={"web": web})
    tight = _run(tmp_path / "tight", [_beat(1, "entity")], sources={"web": web}, spec=strict)
    assert roomy.beats[0].treatment == "photo"
    assert (tight.beats[0].treatment, tight.beats[0].treatment_downgraded) == ("card", True)


# 057: run03 (job 20260927-140915-bbad1c) beat by beat - the planned kind, the fetched
# file's origin and real size, and what the beat must be drawn as under the amended 5.3.
# Transcribed from its `work/plan.json` and `work/assets.json`.
RUN03 = [
    ("b01", "photo", "owner_supplied", (819, 1024), "photo"),  # ref1, 1.875x
    ("b02", "card", "owner_supplied", (696, 1000), "card"),  # planned card stays a card
    ("b03", "card", "web", (1466, 1920), "card"),
    ("b04", "card", "web", (1120, 1496), "card"),
    ("b05", "photo", "owner_supplied", (819, 1024), "photo"),
    ("b06", "card", "owner_supplied", (819, 1024), "card"),
    ("b07", "photo", "commons", (2275, 2324), "photo"),  # stays a photo
    ("b08", "photo", "owner_supplied", (819, 1024), "photo"),
    ("b10", "photo", "owner_supplied", (819, 1024), "photo"),
    ("b13", "photo", "owner_supplied", (819, 1024), "photo"),
    ("b14", "photo", "web", (908, 1024), "photo"),  # a web image, 1.875x
    ("b15", "card", "owner_supplied", (819, 1024), "card"),
    ("b18", "card", "owner_supplied", (870, 614), "card"),
    ("b19", "photo", "web", (1600, 1169), "card"),  # landscape
    ("b22", "photo", "web", (1024, 632), "card"),  # landscape
    ("b24", "card", "owner_supplied", (1000, 1406), "card"),
]


@pytest.mark.parametrize(("beat_id", "planned", "origin", "size", "treatment"), RUN03)
def test_run03_beats_under_the_amended_5_3(
    beat_id: str, planned: str, origin: str, size: tuple[int, int], treatment: str
) -> None:
    """057: b01, b05, b08, b10, b13 (819x1024, planned photo) and b14 (web, 908x1024)
    become photos; b19 and b22 (landscape) and every planned card stay cards; b07 stays
    a photo. The origin plays no part."""
    got, downgraded = assets.classify(*size, planned=planned, max_upscale=FULL_BLEED_MAX)  # pyright: ignore[reportArgumentType]
    assert got == treatment, (beat_id, origin)
    assert downgraded is (planned == "photo" and treatment == "card"), beat_id


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


def _write_png(
    path: Path, size: tuple[int, int] = (1080, 1920), color: tuple[int, int, int] = (90, 40, 20)
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _generating(*, nothing_for: Sequence[str] = (), cap: int = 8) -> assets.Generating:
    """019: rung 2 on the fake generator, which needs no key and no network."""
    return assets.Generating(
        generator=assets.FakeImageGenerator(nothing_for=nothing_for), spec=SPEC, max_images=cap
    )


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
    generating = _generating()
    empty = assets.FakeImageSource("web", nothing_found=True)
    manifest = _run(tmp_path, [_beat(1, "concept")], sources={"web": empty},
                    generating=generating)  # fmt: skip
    assert generating.images == 1
    assert manifest.beats[0].fallback_rung == 2
    record = manifest.assets[0]
    assert record.origin == "generated" and record.generated is not None
    assert record.generated.prompt and record.generated.depicts == "scene"
    assert record.source_url == ""
    assert (manifest.generated_images, manifest.gen_max) == (1, 8)


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
    """Three showings of one image need a style that allows three (056 (3): the shipped
    `reuse_max` is 2, so the shared spec would send the third beat to rung 4)."""
    missing = {"query 2", "fallback 2", "query 3", "fallback 3"}
    web = assets.FakeImageSource("web", nothing_for=missing)
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept")]
    roomy = SPEC.model_copy(deep=True)
    roomy.broll.reuse_max = 3
    crops = [b.crop for b in _run(tmp_path, beats, sources={"web": web}, spec=roomy).beats]
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
    web = assets.FakeImageSource(
        "web", nothing_for={"query 2", "query 3", "fallback 3", "query 4", "fallback 4",
                            "query 5", "fallback 5"},
    )  # fmt: skip
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept"),
             _beat(4, "concept"), _beat(5, "entity")]  # fmt: skip
    # Only b03 can be generated, so b04 falls to the re-dress and b05 to the gradient.
    generating = _generating(nothing_for=["query 4", "query 5"])
    manifest = _run(tmp_path, beats, sources={"web": web}, generating=generating)
    assert [b.fallback_rung for b in manifest.beats] == [0, 1, 2, 3, 4]
    assert generating.images == 1


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


def test_presenter_and_finale_beats_are_not_sourced(tmp_path: Path) -> None:
    beats = [
        _beat(1, None, kind="presenter_full", mode="full"),
        _beat(2, None, kind="presenter_pip", mode="pip"),
        _beat(3, "concept"),
        _beat(4, None, kind="finale", mode="off", asset="a3"),
    ]
    manifest = _run(tmp_path, beats)
    assert [b.beat_id for b in manifest.beats] == ["b03"]


# --- the opening beats (ticket 055; 3.4 as amended) ----------------------------------------
#
# Under the real explainer spec the first two beats are the opening: owner reference
# first, then the best-scored image across every source, then a generated image past
# the cap, never rung 3 or 4.


def test_an_owner_reference_the_plan_names_opens_the_short(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    ref = _reference(job, "r1", "my product", (1080, 1920))
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept", asset="r1"), _beat(2, "entity"), _beat(3, "concept")]
    manifest = _run(tmp_path, beats, sources={"web": web}, references=[ref], job=job,
                    spec=EXPLAINER)  # fmt: skip
    first = manifest.beats[0]
    assert (first.asset_id, first.fallback_rung) == ("r1", 0)
    assert manifest.assets[0].origin == "owner_supplied"
    assert web.searches == 2  # b02 and b03; the reference beat searched nothing


def test_an_opening_beat_takes_the_best_scored_candidate_across_every_source(
    tmp_path: Path,
) -> None:
    """055: the opening is the short's strongest image, so every source in the order is
    asked and the highest judge score wins (ties by source order); a body beat still
    stops at the first source that answers."""
    web = Scripted("web", _candidates(("web-pic", 1600, 1200)))
    commons = Scripted("commons", _candidates(("commons-pic", 1600, 1200)))
    judge = Scoring({"https://e.example/web-pic.png": 2, "https://e.example/commons-pic.png": 3})
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept")]
    manifest = _run(tmp_path, beats, sources={"web": web, "commons": commons},
                    judging=assets.Judging(judge, 40), spec=EXPLAINER)  # fmt: skip
    origins = {b.beat_id: manifest.asset(b.asset_id or "") for b in manifest.beats}
    assert origins["b01"] is not None and origins["b01"].origin == "commons"  # 3 beats 2
    assert origins["b02"] is not None and origins["b02"].origin == "commons"
    assert origins["b03"] is not None and origins["b03"].origin == "web"  # first hit wins
    assert [b.fallback_rung for b in manifest.beats] == [0, 0, 0]
    assert (web.searches, commons.searches) == (3, 2)  # b03 stopped at web


def test_an_opening_beat_is_generated_past_the_cap_and_never_rescued(tmp_path: Path) -> None:
    """A concept topic (no named person) with nothing found: the opening beats are
    generated even with `gen_max_per_short` spent (11.3: cost never degrades quality);
    the body beat behind them falls to the ladder as before."""
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(1, "concept", query="a wheel of cheese"),
             _beat(2, "concept", query="a cheese cave"),
             _beat(3, "concept", query="a cheese market")]  # fmt: skip
    generating = _generating(cap=1)
    manifest = _run(tmp_path, beats, sources={"web": empty}, generating=generating,
                    spec=EXPLAINER)  # fmt: skip
    assert [b.fallback_rung for b in manifest.beats] == [2, 2, 3]
    assert generating.images == 2 and manifest.rescued == 1
    made = [manifest.asset(b.asset_id or "") for b in manifest.beats[:2]]
    assert all(a is not None and a.origin == "generated" and a.generated is not None
               and a.generated.depicts == "scene" for a in made)  # fmt: skip


def test_an_opening_beat_with_no_image_and_no_generator_falls_to_the_gradient(
    tmp_path: Path,
) -> None:
    """055 as amended by the editor rule (096): a small problem never fails the job.
    With nothing found and no generator the opening beat is shown over the gradient,
    as the very last step, rather than failing the step."""
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(1, "concept"), _beat(2, "concept")]
    manifest = _run(tmp_path, beats, sources={"web": empty}, spec=EXPLAINER)
    first = manifest.beats[0]
    assert first.beat_id == "b01" and first.asset_id is None and first.fallback_rung == 4


def test_a_named_opening_subject_still_skips_the_stock_libraries(tmp_path: Path) -> None:
    """053's rule holds inside the opening: a named person is never a stock stranger,
    so with only Pexels answering the opening beat is illustrated, not found."""
    pexels = assets.FakeImageSource("pexels")
    web = assets.FakeImageSource("web", nothing_found=True)
    generating = _generating()
    beats = [_beat(1, "entity", query="Neem Karoli Baba portrait", depicts="named_entity"),
             _beat(2, "concept")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": web, "pexels": pexels},
                    generating=generating, spec=EXPLAINER)  # fmt: skip
    assert pexels.searches == 1  # b02, a scene, may use it; b01 never did
    first = manifest.asset(manifest.beats[0].asset_id or "")
    assert first is not None and first.origin == "generated" and first.generated is not None
    assert first.generated.render == "illustration"


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
    generating = _generating()
    manifest = _run(tmp_path, beats, sources={"web": web}, generating=generating)
    # The label forbids search and generation alike.
    assert web.searches == 1 and generating.images == 0
    assert [b.asset_id for b in manifest.beats] == ["a1", "a1", "a1"]
    assert [a.id for a in manifest.assets] == ["a1"]


def test_generate_intent_on_a_concept_beat_generates_first(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    generating = _generating()
    manifest = _run(tmp_path, [_beat(1, "concept", intent="generate")], sources={"web": web},
                    generating=generating)  # fmt: skip
    assert generating.images == 1 and web.searches == 0
    assert (manifest.beats[0].fallback_rung, manifest.assets[0].origin) == (2, "generated")


def test_generate_intent_without_a_generator_still_searches(tmp_path: Path) -> None:
    manifest = _run(tmp_path, [_beat(1, "concept", intent="generate")])
    assert (manifest.beats[0].fallback_rung, manifest.assets[0].origin) == (0, "web")


def test_entity_beats_always_search_first(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    generating = _generating()
    manifest = _run(tmp_path, [_beat(1, "entity", intent="generate")], sources={"web": web},
                    generating=generating)  # fmt: skip
    assert generating.images == 0 and web.searches == 1
    assert manifest.assets[0].origin == "web"


def test_the_generation_cap_sends_the_beat_on_to_the_ladder(tmp_path: Path) -> None:
    """5.5 / 11.3: `gen_max_per_short` spent means rung 3, never a failed job."""
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(1, "concept"), _beat(2, "concept"), _beat(3, "concept")]
    log: list[str] = []
    generating = _generating(cap=1)
    manifest = _run(tmp_path, beats, sources={"web": empty}, generating=generating, log=log)
    # 056 (3): the one generated image is re-dressed once (its second showing) and never
    # a third time, so the last beat is the gradient.
    assert [b.fallback_rung for b in manifest.beats] == [2, 3, 4]
    assert (manifest.generated_images, manifest.gen_max) == (1, 1)
    assert [line for line in log if "gen_max_per_short (1) is spent" in line]


def test_two_beats_asking_for_the_same_picture_generate_once(tmp_path: Path) -> None:
    """5.6: the generated file is cached by prompt and model, like a search result."""
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(1, "concept", query="same scene"), _beat(2, "concept", query="same scene")]
    generating = _generating()
    manifest = _run(tmp_path, beats, sources={"web": empty}, generating=generating)
    assert generating.images == 1
    assert [b.fallback_rung for b in manifest.beats] == [2, 2]
    assert [a.sha256 for a in manifest.assets].count(manifest.assets[0].sha256) == 2


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
        super().__init__()
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
        # 056 (3): images are counted by file, so each candidate is its own picture.
        digest = hashlib.sha256(candidate.url.encode("utf-8")).digest()
        _write_png(path, size, color=(digest[0], digest[1], digest[2]))
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
        ("small", 320, 240), ("wide", 3600, 900), ("good", 1600, 1200),
    ))  # fmt: skip
    book, judge = _judging({"good": 3})
    log: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "entity")], sources={"web": source},
                    judging=book, log=log)  # fmt: skip
    assert judge.asked[0][3] == ("https://e.example/good.png",)
    assert source.fetched == ["https://e.example/good.png"]
    assert manifest.beats[0].fallback_rung == 0
    assert log[:2] == [
        "sourcing: https://e.example/small.png rejected: 320x240 px cannot fill a 839 px "
        "wide card at <= 1.5x",
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
    assert log == [
        "sourcing: https://e.example/lying.png rejected: 400x300 px cannot fill a 839 px "
        "wide card at <= 1.5x"
    ]


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


# --- 056: an owner photo goes only to beats about what its caption names ------------------
#
# run03 (job 20260927-140915-bbad1c): the caption "king saud image" shared "king" with
# nearly every query, so one portrait filled eleven beats, one of them about King Faisal.

RUN03_CAPTIONS = (
    ("ref1", "king saud image"),
    ("ref2", "king saud with stepbrother who abducted his throne"),
    ("ref3", "with daughter"),
    ("ref4", "with nizab hyderabad"),
)


def _run03_refs(job: Path) -> list[ReferenceRecord]:
    return [_reference(job, ref_id, caption, (819, 1024)) for ref_id, caption in RUN03_CAPTIONS]


def test_a_title_word_never_creates_a_match(tmp_path: Path) -> None:
    """056 (2): "king" is a title, so "king saud image" does not match the Faisal beat."""
    job = _job_dir(tmp_path)
    refs = _run03_refs(job)
    beat = _beat(1, "entity", kind="card", query="King Faisal bin Abdulaziz 1964 portrait",
                 fallback="King Faisal Saudi Arabia", asset="faisal")  # fmt: skip
    assert assets.matching_reference(beat, refs) is None
    manifest = _run(tmp_path, [beat], references=refs, job=job)
    assert manifest.assets[0].origin == "web"


def test_a_caption_that_names_the_beats_subject_still_matches(tmp_path: Path) -> None:
    job = _job_dir(tmp_path)
    refs = _run03_refs(job)
    old = _beat(1, "entity", kind="card", query="King Saud old age 1960s photo", asset="saud_old")
    found = assets.matching_reference(old, refs)
    assert found is not None and found.id == "ref1"
    brother = _beat(2, "entity", kind="card", query="King Saud with King Faisal stepbrother")
    found = assets.matching_reference(brother, refs)
    assert found is not None and found.id in ("ref1", "ref2")


def test_a_vague_caption_goes_only_where_the_planner_named_it(tmp_path: Path) -> None:
    """056 (2): "with daughter" names nobody, so it matches no query; the beat that names
    the reference id still gets it."""
    job = _job_dir(tmp_path)
    refs = _run03_refs(job)
    daughter = _beat(1, "entity", kind="card", query="Princess Dalal with her daughter", asset="x1")
    assert assets.matching_reference(daughter, refs) is None
    saud = _beat(1, "entity", kind="card", query="King Saud with daughter", asset="x1")
    found = assets.matching_reference(saud, refs)
    assert found is not None and found.id == "ref1", "Saud is named; 'with daughter' is not"
    named = _beat(1, "entity", kind="card", query="King Saud with daughter", asset="ref3")
    manifest = _run(tmp_path, [named], references=refs, job=job)
    assert (manifest.beats[0].asset_id, manifest.assets[0].origin) == ("ref3", "owner_supplied")


def test_generic_words_are_not_subject_words() -> None:
    for word in ("king", "prince", "president", "image", "photo", "with", "portrait"):
        assert word in assets.TITLE_WORDS or word in assets.STOPWORDS, word


# --- 056: no image on repeat, counted by file --------------------------------------------


def _shas(manifest: assets.AssetManifest) -> dict[str, str]:
    return {a.id: a.sha256 for a in manifest.assets}


def test_the_manifest_carries_the_styles_reuse_max(tmp_path: Path) -> None:
    manifest = _run(tmp_path, [_beat(1, "concept")])
    assert manifest.reuse_max == SPEC.broll.reuse_max == 2


def test_a_third_beat_wanting_the_same_image_gets_the_next_candidate(tmp_path: Path) -> None:
    """056 (3): one image at most twice per short; the third beat that plans the same
    asset id takes the next candidate of its own search, never the same file."""
    web = assets.FakeImageSource("web")
    log: list[str] = []
    beats = [_beat(1, "concept", asset="a1", query="same"),
             _beat(2, "concept", asset="a1", query="same"),
             _beat(3, "concept", asset="a1", query="same")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": web}, log=log)
    shown = [b.asset_id for b in manifest.beats]
    assert shown[0] == shown[1] == "a1" and shown[2] not in (None, "a1")
    shas = _shas(manifest)
    assert shas[shown[2]] != shas["a1"], "the third beat shows another picture"
    assert manifest.beats[2].fallback_rung == 0 and not manifest.beats[2].rescued
    assert web.searches == 1, "the cached search's next candidate, not a new search"
    assert any("already shown 2 times" in line and "b03" in line for line in log), log


def test_several_ids_for_one_file_count_as_one_image(tmp_path: Path) -> None:
    """run03: `saud_1953`, `saud_young`, `royal_court`, `saud_old` and `faisal` were
    five ids for `ref1`'s file. Counted by sha256 they are one image."""
    job = _job_dir(tmp_path)
    ref = _reference(job, "ref1", "king saud image", (819, 1024))
    beats = [
        _beat(1, "entity", kind="card", query="King Saud portrait", asset="ref1"),
        _beat(2, "entity", kind="card", query="King Saud accession 1953", asset="saud_1953"),
        _beat(3, "entity", kind="card", query="young Prince Saud 1920s", asset="saud_young"),
        _beat(4, "entity", kind="card", query="King Saud old age", asset="saud_old"),
    ]
    manifest = _run(tmp_path, beats, references=[ref], job=job)
    origins: list[str] = []
    for shown in manifest.beats:
        record = manifest.asset(shown.asset_id or "")
        assert record is not None
        origins.append(record.origin)
    assert origins == ["owner_supplied", "owner_supplied", "web", "web"]
    counts = Counter(_shas(manifest)[b.asset_id] for b in manifest.beats if b.asset_id)
    assert max(counts.values()) <= 2


def test_a_carry_on_beat_is_part_of_the_same_showing(tmp_path: Path) -> None:
    """056 (3): a number or quote beat over the previous picture does not spend a
    showing, so the picture may still come back once more later."""
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept", asset="a1"), _beat(2, "number", asset="a1"),
             _beat(3, "quote", asset="a1"), _beat(4, "entity"),
             _beat(5, "concept", asset="a1"), _beat(6, "concept", asset="a1")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": web})
    shown = [b.asset_id for b in manifest.beats]
    assert shown[:5] == ["a1", "a1", "a1", "a4", "a1"]
    assert shown[5] not in ("a1", None) and _shas(manifest)[shown[5]] != _shas(manifest)["a1"]


def test_a_set_piece_base_is_not_a_showing(tmp_path: Path) -> None:
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept", asset="a1"), _beat(2, "concept", kind="wall", asset="a1"),
             _beat(3, "concept", asset="a1")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": web})
    assert [b.asset_id for b in manifest.beats] == ["a1", "a1", "a1"]


def test_a_rescue_never_redresses_a_saturated_image(tmp_path: Path) -> None:
    """056 (3): rung 3 re-dresses only an image with a showing left; with none left the
    beat goes to rung 4, never the same picture a third time."""
    web = assets.FakeImageSource("web", nothing_for={"query 3", "fallback 3"})
    beats = [_beat(1, "concept", asset="a1"), _beat(2, "concept", asset="a1"),
             _beat(3, "concept")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": web})
    assert (manifest.beats[2].asset_id, manifest.beats[2].fallback_rung) == (None, 4)


def test_image_reuse_problems_name_the_image_over_the_cap(tmp_path: Path) -> None:
    """The T8 view of the rule: a manifest whose ids hide one file shown three times."""
    web = assets.FakeImageSource("web")
    beats = [_beat(1, "concept", asset="a1"), _beat(2, "concept", asset="a1")]
    manifest = _run(tmp_path, beats, sources={"web": web})
    record = manifest.assets[0]
    twin = record.model_copy(update={"id": "twin"})
    extra = manifest.beats[1].model_copy(update={"beat_id": "b03", "asset_id": "twin"})
    tripled = manifest.model_copy(
        update={"assets": [record, twin], "beats": [*manifest.beats, extra]}
    )
    plan = _plan([*beats, _beat(3, "concept", asset="twin")]).picture
    assert assets.image_reuse_problems(manifest, plan) == []
    (problem,) = assets.image_reuse_problems(tripled, plan)
    assert "3 times" in problem and "a1" in problem and "twin" in problem


# --- 071: a named-entity beat never carries another person's picture ---------------------

# Run04 (job 20260928-140620-f774e1) b01-b05 as the planner wrote them, overlays left out.
RUN04_BEATS = """[
 {"id": "b01", "start": 0.0, "end": 1.9, "mode": "pip", "kind": "photo",
  "motion": "ken_burns_in", "subject_kind": "entity", "depicts": "named_entity",
  "query": "King Saud bin Abdulaziz portrait", "query_fallback": "King Saud Saudi Arabia 1950s",
  "source_intent": "reuse", "asset_id": "ref1"},
 {"id": "b02", "start": 1.9, "end": 3.5, "mode": "pip", "kind": "photo",
  "motion": "ken_burns_out", "subject_kind": "entity", "depicts": "named_entity",
  "query": "King Saud bin Abdulaziz royal robes throne",
  "query_fallback": "King Saud of Saudi Arabia", "source_intent": "search",
  "asset_id": "saud_robes"},
 {"id": "b03", "start": 3.5, "end": 4.4, "mode": "pip", "kind": "photo",
  "motion": "ken_burns_in", "subject_kind": "entity", "depicts": "named_entity",
  "query": "Narendra Modi portrait", "query_fallback": "Prime Minister Narendra Modi",
  "source_intent": "search", "asset_id": "modi",
  "event": {"kind": "lower_third", "text": "नरेंद्र मोदी"}},
 {"id": "b04", "start": 4.4, "end": 5.78, "mode": "pip", "kind": "photo",
  "motion": "ken_burns_out", "subject_kind": "entity", "depicts": "named_entity",
  "query": "Donald Trump portrait", "query_fallback": "President Donald Trump",
  "source_intent": "search", "asset_id": "trump",
  "event": {"kind": "lower_third", "text": "डोनाल्ड ट्रंप"}},
 {"id": "b05", "start": 5.78, "end": 7.34, "mode": "off", "kind": "photo",
  "motion": "ken_burns_in", "subject_kind": "entity", "depicts": "named_entity",
  "query": "King Saud bin Abdulaziz portrait", "query_fallback": "King Saud Saudi Arabia",
  "source_intent": "reuse", "asset_id": "ref1",
  "event": {"kind": "lower_third", "text": "किंग साऊद"}}
]"""


def _run04_beats() -> list[Beat]:
    return [Beat.model_validate(b) for b in json.loads(RUN04_BEATS)]


class Asked(assets.FakeImageSource):
    """The fake web source, recording every query it was asked."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__("web", **kwargs)  # pyright: ignore[reportArgumentType]
        self.asked: list[str] = []

    def search(self, query: str, n: int) -> list[Candidate]:
        self.asked.append(query)
        return super().search(query, n)


SAUD_QUERIES = ("King Saud bin Abdulaziz portrait", "King Saud Saudi Arabia")


def _run04(tmp_path: Path, web: assets.ImageSource, *, log: list[str] | None = None,
           generating: assets.Generating | None = None,
           extra: Sequence[Beat] = ()) -> assets.AssetManifest:  # fmt: skip
    job = _job_dir(tmp_path)
    ref = _reference(job, "ref1", "king saud image", (819, 1024))
    return _run(tmp_path, [*_run04_beats(), *extra], sources={"web": web}, references=[ref],
                job=job, log=log, generating=generating)  # fmt: skip


def test_run04_b05_searches_king_saud_when_the_owner_portrait_is_capped(
    tmp_path: Path,
) -> None:
    web = Asked()
    log: list[str] = []
    manifest = _run04(tmp_path, web, log=log)
    shown = {b.beat_id: b.asset_id for b in manifest.beats}
    assert shown["b04"] == "trump" and shown["b05"] not in (None, "trump")
    shas = _shas(manifest)
    assert shas[shown["b05"] or ""] not in (shas["trump"], shas["ref1"])
    assert SAUD_QUERIES[0] in web.asked
    assert any(
        "b05" in line and "'ref1'" in line and "searched afresh" in line for line in log
    ), log


def test_run04_b05_with_every_saud_search_failing_never_shows_trump(tmp_path: Path) -> None:
    manifest = _run04(tmp_path, Asked(nothing_for=SAUD_QUERIES))
    b05 = next(b for b in manifest.beats if b.beat_id == "b05")
    assert (b05.asset_id, b05.fallback_rung) == (None, 4)
    generated = _run04(tmp_path / "gen", Asked(nothing_for=SAUD_QUERIES),
                       generating=_generating())  # fmt: skip
    b05 = next(b for b in generated.beats if b.beat_id == "b05")
    record = generated.asset(b05.asset_id or "")
    assert record is not None and (record.origin, b05.fallback_rung) == ("generated", 2)


def test_a_number_beat_after_trump_still_carries_trump_on(tmp_path: Path) -> None:
    trump = _run04_beats()[3]
    number = _beat(5, "number", asset="n5").model_copy(update={"start": 5.78, "end": 7.0})
    manifest = _run(tmp_path, [trump, number], sources={"web": Asked()})
    assert [b.asset_id for b in manifest.beats] == ["trump", "trump"]


def test_a_rescue_on_a_named_entity_redresses_only_that_entitys_image(tmp_path: Path) -> None:
    """Rung 3 on a named-entity beat: the nearest earlier image of the same entity, never
    the image just before it of someone else."""
    web = Asked(nothing_for={"King Saud 1960s", "King Saud old age"})
    saud = _beat(1, "entity", depicts="named_entity", query="King Saud 1950s", asset="s1")
    trump = _beat(2, "entity", depicts="named_entity", query="Donald Trump portrait",
                  asset="t2")  # fmt: skip
    later = _beat(3, "entity", depicts="named_entity", query="King Saud 1960s",
                  fallback="King Saud old age", asset="s3")  # fmt: skip
    manifest = _run(tmp_path, [saud, trump, later], sources={"web": web})
    assert (manifest.beats[2].asset_id, manifest.beats[2].fallback_rung) == ("s1", 3)


def test_entity_crossings_name_run04s_b04_and_b05(tmp_path: Path) -> None:
    """The T8 view (071): run04's manifest showed b04's Trump on b05's King Saud line."""
    manifest = _run04(tmp_path, Asked())
    plan = _plan(_run04_beats()).picture
    assert assets.entity_crossings(manifest, plan) == []
    as_it_was = manifest.model_copy(update={"beats": [
        b.model_copy(update={"asset_id": "trump"}) if b.beat_id == "b05" else b
        for b in manifest.beats
    ]})  # fmt: skip
    (problem,) = assets.entity_crossings(as_it_was, plan)
    assert "b05" in problem and "b04" in problem and "trump" in problem


def test_a_number_carry_on_is_not_an_entity_crossing(tmp_path: Path) -> None:
    trump = _run04_beats()[3]
    number = _beat(5, "number", asset="n5", depicts="named_entity").model_copy(
        update={"start": 5.78, "end": 7.0}
    )
    manifest = _run(tmp_path, [trump, number], sources={"web": Asked()})
    assert assets.entity_crossings(manifest, _plan([trump, number]).picture) == []
