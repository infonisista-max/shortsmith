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

from shortsmith import assets, config, render, styles
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
from tests.conftest import Media

SPEC = styles.load_all(render.registry())["explainer"]
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


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


def test_from_settings_follows_asset_sources_and_policy() -> None:
    settings = config.Settings(asset_sources="fake,commons", asset_policy="rights_safe",
                               _env_file=None)  # pyright: ignore[reportCallIssue]  # fmt: skip
    sourcing = assets.from_settings(settings)
    assert (tuple(sourcing.order), sourcing.policy) == (("fake", "commons"), "rights_safe")
    assert list(sourcing.sources) == ["fake"]
    assert sourcing.missing() == ["commons"]  # no real adapter until 017 / 018
    assert sourcing.generate is None  # IMAGE_GEN=none until 019


def test_default_settings_have_no_adapter_yet() -> None:
    sourcing = assets.from_settings(config.Settings(_env_file=None))  # pyright: ignore[reportCallIssue]
    assert sourcing.missing() == list(assets.DEFAULT_ORDER)


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
    assert again == first
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
