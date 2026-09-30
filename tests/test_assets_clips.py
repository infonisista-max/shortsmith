"""assets.clips (ticket 058; 4.1 and 5.1 as amended): the stock video sources a `clip`
beat draws from.

The two adapters are driven on recorded responses through an `httpx.MockTransport`
(the request they build - endpoint, key placement, video type - and the mapping of the
JSON into `ClipCandidate`s), the file choice is pinned on both sides of the cover bar
(a 1920x1080 landscape at 1.78x is accepted, a 1280x720 at 2.67x is not), the streamed
download refuses what is not a video, Pixabay's key is scrubbed from every note, and
the fake writes a real moving clip with a tone track."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from shortsmith import assets, config, ffmpeg, rights
from shortsmith.assets import base, clips
from shortsmith.assets.clips import ClipCandidate, ClipFile
from shortsmith.contracts import Beat, Candidate
from shortsmith.ledger import Ledger
from tests.test_assets import (
    SPEC,
    _beat,  # pyright: ignore[reportPrivateUsage]
    _job_dir,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_assets_f1 import (
    BABA,
    _named,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_assets_library import Recorded

FIXTURES = Path(__file__).parent / "fixtures"
QUERY = "clouds drifting over hills"
KEY = SecretStr("pixabay-test-key-not-real")
MAX_UPSCALE = 2.0  # explainer's broll.full_bleed_max_upscale (057)


def _recorded(name: str) -> object:
    return json.loads((FIXTURES / name / "videos.json").read_text(encoding="utf-8"))


def _hit(*files: tuple[int, int, int], duration_s: float = 8.0) -> ClipCandidate:
    listed = [
        ClipFile(url=f"https://videos.example/{w}x{h}.mp4", width=w, height=h, size_bytes=size)
        for w, h, size in files
    ]
    largest = max(listed, key=lambda f: f.width * f.height)
    return ClipCandidate(
        url=largest.url, page_url="https://videos.example/page", thumb_url="https://videos.example/t.jpg",
        width=largest.width, height=largest.height, author="A", licence="L", duration_s=duration_s,
        files=listed,
    )  # fmt: skip


# --- the file choice (058 (3)) --------------------------------------------------------------


def test_a_1920x1080_landscape_is_accepted_and_a_1280x720_is_not() -> None:
    """The 9:16 crop of a 1920x1080 clip covers 1080x1920 at 1.78x; 1280x720 needs 2.67x."""
    chosen = clips.choose_file(_hit((1920, 1080, 9_800_000)), max_upscale=MAX_UPSCALE)
    assert chosen is not None and (chosen.width, chosen.height) == (1920, 1080)
    assert clips.choose_file(_hit((1280, 720, 3_000_000)), max_upscale=MAX_UPSCALE) is None
    assert clips.reject_clip(_hit((1280, 720, 3_000_000)), max_upscale=MAX_UPSCALE) is not None
    assert clips.reject_clip(_hit((1920, 1080, 9_800_000)), max_upscale=MAX_UPSCALE) is None


def test_the_smallest_file_meeting_the_bar_is_chosen_under_the_weight_cap() -> None:
    hit = _hit((3840, 2160, 61_000_000), (1920, 1080, 9_800_000), (640, 360, 1_200_000))
    chosen = clips.choose_file(hit, max_upscale=MAX_UPSCALE)
    assert chosen is not None and chosen.url.endswith("1920x1080.mp4")
    heavy = _hit((1920, 1080, clips.CLIP_MAX_BYTES + 1), (3840, 2160, 61_000_000))
    chosen = clips.choose_file(heavy, max_upscale=MAX_UPSCALE)
    assert chosen is not None and chosen.url.endswith("3840x2160.mp4")
    only_heavy = _hit((1920, 1080, clips.CLIP_MAX_BYTES + 1))
    assert clips.choose_file(only_heavy, max_upscale=MAX_UPSCALE) is None
    unknown = _hit((1920, 1080, 0), (1080, 1920, 7_000_000))
    chosen = clips.choose_file(unknown, max_upscale=MAX_UPSCALE)
    assert chosen is not None and chosen.url.endswith("1080x1920.mp4")  # a known weight first


def test_the_chosen_file_carries_the_hits_page_preview_author_licence_and_length() -> None:
    hit = _hit((1080, 1920, 7_000_000), duration_s=7.0)
    chosen = clips.choose_file(hit, max_upscale=MAX_UPSCALE)
    assert chosen == Candidate(
        url="https://videos.example/1080x1920.mp4", page_url="https://videos.example/page",
        thumb_url="https://videos.example/t.jpg", width=1080, height=1920, author="A",
        licence="L", duration_s=7.0,
    )  # fmt: skip
    assert chosen is not None and clips.is_portrait(chosen)
    assert not clips.is_portrait(Candidate(url="x", width=1920, height=1080))


def test_a_stock_preview_host_is_rejected_for_clips_too() -> None:
    """053 rule 3 applies to clips (058 (4))."""
    hit = _hit((1080, 1920, 7_000_000)).model_copy(update={"page_url": "https://www.shutterstock.com/v/1"})
    assert clips.reject_clip(hit, max_upscale=MAX_UPSCALE) == "stock preview host shutterstock.com"


# --- Pexels video ---------------------------------------------------------------------------


def test_pexels_video_sends_the_key_in_the_header_to_the_video_endpoint() -> None:
    tape = Recorded(_recorded("pexels"))
    source = clips.PexelsClipSource(api_key=KEY, client=tape.client())
    source.search(QUERY, 6)
    request = tape.requests[0]
    assert request.url.host == "api.pexels.com" and request.url.path == "/v1/videos/search"
    assert request.headers["authorization"] == KEY.get_secret_value()
    assert (request.url.params["query"], request.url.params["per_page"]) == (QUERY, "6")


def test_pexels_video_maps_every_file_the_preview_the_duration_and_the_user() -> None:
    tape = Recorded(_recorded("pexels"))
    found = clips.PexelsClipSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    assert len(found) == 3  # the video with no files is dropped
    first = found[0]
    assert isinstance(first, ClipCandidate)
    assert first.page_url == "https://www.pexels.com/video/clouds-drifting-over-hills-3045163/"
    assert first.thumb_url.startswith("https://images.pexels.com/videos/3045163/")
    assert (first.duration_s, first.author) == (12.0, "Taryn Elliott")
    assert first.licence == clips.PEXELS_LICENCE
    assert [(f.width, f.height, f.size_bytes) for f in first.files] == [
        (1920, 1080, 9_800_000), (3840, 2160, 61_000_000), (640, 360, 1_200_000),
    ]  # fmt: skip
    assert (first.width, first.height) == (3840, 2160)  # the largest until the step chooses
    chosen = clips.choose_file(first, max_upscale=MAX_UPSCALE)
    assert chosen is not None and chosen.url.endswith("3045163-hd_1920_1080_25fps.mp4")
    portrait = found[1]
    assert isinstance(portrait, ClipCandidate) and clips.is_portrait(portrait)
    small = found[2]
    assert isinstance(small, ClipCandidate)
    assert clips.reject_clip(small, max_upscale=MAX_UPSCALE) is not None  # 1280x720 only


def test_every_clip_search_notes_source_query_status_and_hit_count() -> None:
    """058 (5): the note is written whether or not the search found anything."""
    source = clips.PexelsClipSource(api_key=KEY, client=Recorded(_recorded("pexels")).client())
    source.search(QUERY, 6)
    assert source.drain() == [f"pexels video: {QUERY!r} answered 200 with 3 candidates"]
    empty = clips.PexelsClipSource(api_key=KEY, client=Recorded({"videos": []}).client())
    assert empty.search(QUERY, 6) == []
    assert empty.drain() == [f"pexels video: {QUERY!r} answered 200 with 0 candidates"]
    refused = clips.PexelsClipSource(api_key=KEY, client=Recorded(None, status=429).client())
    assert refused.search(QUERY, 6) == []
    notes = refused.drain()
    assert notes[0] == f"pexels answered 429 for {QUERY!r}"
    assert notes[1] == f"pexels video: {QUERY!r} answered 429 with 0 candidates"


# --- Pixabay video --------------------------------------------------------------------------


def test_pixabay_video_carries_its_key_as_a_query_parameter_and_asks_for_film() -> None:
    tape = Recorded(_recorded("pixabay"))
    clips.PixabayClipSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    params = tape.url.params
    assert tape.url.host == "pixabay.com" and tape.url.path == "/api/videos/"
    assert params["key"] == KEY.get_secret_value()
    assert (params["q"], params["video_type"], params["safesearch"]) == (QUERY, "film", "true")
    assert int(params["per_page"]) >= clips.PIXABAY_MIN_PER_PAGE


def test_pixabay_asks_for_animation_only_when_the_beat_says_so() -> None:
    assert clips.video_type("cheese being made") == "film"
    assert clips.video_type("animated cell dividing") == "animation"
    assert clips.video_type("cartoon sun") == "animation"


def test_pixabay_video_maps_the_variants_the_thumbnail_the_duration_and_the_user() -> None:
    tape = Recorded(_recorded("pixabay"))
    found = clips.PixabayClipSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    assert len(found) == 2  # the hit with no variants is dropped
    first = found[0]
    assert isinstance(first, ClipCandidate)
    assert first.page_url == "https://pixabay.com/videos/clouds-sky-time-lapse-nature-31377/"
    assert first.thumb_url.endswith("31377-381803312_large.jpg")
    assert (first.duration_s, first.author) == (15.0, "Engin_Akyurt")
    assert first.licence == clips.PIXABAY_LICENCE
    assert [(f.quality, f.width, f.height) for f in first.files] == [
        ("large", 1920, 1080), ("medium", 1280, 720), ("small", 640, 360), ("tiny", 480, 270),
    ]  # fmt: skip
    chosen = clips.choose_file(first, max_upscale=MAX_UPSCALE)
    assert chosen is not None and chosen.url.endswith("_large.mp4")  # medium cannot cover
    assert KEY.get_secret_value() not in chosen.url


def test_pixabays_key_is_scrubbed_from_every_note_and_never_printed() -> None:
    """058 (8): the key rides the search URL, so every line the adapter notes goes
    through `scrub`, and so does any step line about its candidates."""
    source = clips.PixabayClipSource(api_key=KEY, client=Recorded(_recorded("pixabay")).client())
    source.search(QUERY, 6)
    source.note(f"https://pixabay.com/api/videos/?key={KEY.get_secret_value()}&q=x answered 200")
    notes = source.drain()
    assert notes and all(KEY.get_secret_value() not in line for line in notes)
    assert any("key=***" in line for line in notes)
    assert source.scrub(f"sourcing: {KEY.get_secret_value()} rejected") == "sourcing: *** rejected"
    assert KEY.get_secret_value() not in repr(source)


# --- the shared download (058 (3), 5.2) ------------------------------------------------------

MP4_HEAD = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 64


def _client(content: bytes, *, content_type: str = "video/mp4") -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=content, headers={"content-type": content_type})
        )
    )


def test_fetch_streams_a_video_body_to_disk_under_its_own_suffix(tmp_path: Path) -> None:
    source = clips.PexelsClipSource(api_key=KEY, client=_client(MP4_HEAD))
    candidate = Candidate(url="https://videos.pexels.com/x.bin", width=1920, height=1080)
    written = source.fetch(candidate, tmp_path / "clip")
    assert written == tmp_path / "clip.mp4" and written.read_bytes() == MP4_HEAD
    assert not (tmp_path / "clip.part").exists()


def test_fetch_refuses_a_body_that_is_not_a_video_and_writes_nothing(tmp_path: Path) -> None:
    source = clips.PexelsClipSource(api_key=KEY, client=_client(b"<html>nope</html>" * 8))
    candidate = Candidate(url="https://videos.pexels.com/x.mp4", width=1920, height=1080)
    with pytest.raises(base.SourceError, match="not a video"):
        source.fetch(candidate, tmp_path / "clip")
    assert not list(tmp_path.iterdir())
    image = clips.PexelsClipSource(api_key=KEY, client=_client(MP4_HEAD, content_type="image/jpeg"))
    with pytest.raises(base.SourceError, match="not a video"):
        image.fetch(candidate, tmp_path / "clip")


def test_fetch_refuses_a_body_over_the_clip_cap(tmp_path: Path) -> None:
    big = _client(MP4_HEAD + b"\x00" * 200)
    source = clips.PexelsClipSource(api_key=KEY, client=big, max_bytes=100)
    candidate = Candidate(url="https://videos.pexels.com/big.mp4", width=1920, height=1080)
    with pytest.raises(base.SourceError, match="over"):
        source.fetch(candidate, tmp_path / "clip")
    assert not list(tmp_path.iterdir())


def test_video_media_type_reads_the_magic_bytes() -> None:
    assert clips.video_media_type(MP4_HEAD) == "video/mp4"
    assert clips.video_media_type(b"\x1aE\xdf\xa3" + b"\x00" * 8) == "video/webm"
    assert clips.video_media_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) is None


# --- the fake (12.1) -------------------------------------------------------------------------


def test_the_fake_clip_source_answers_with_moving_clips_that_carry_a_tone(tmp_path: Path) -> None:
    fake = clips.FakeClipSource("pexels", sizes={QUERY: (1920, 1080)}, durations={QUERY: 2.0})
    found = fake.search(QUERY, 2)
    assert [c.url for c in found] == [
        f"https://fake.invalid/pexels-video/{clips._slug(QUERY)}/{i}.mp4" for i in (1, 2)  # pyright: ignore[reportPrivateUsage]
    ]
    assert all(isinstance(c, ClipCandidate) and c.duration_s == 2.0 for c in found)
    assert fake.drain() == [f"pexels video: {QUERY!r} answered 200 with 2 candidates"]
    chosen = clips.choose_file(found[0], max_upscale=MAX_UPSCALE)  # pyright: ignore[reportArgumentType]
    assert chosen is not None
    path = fake.fetch(chosen, tmp_path / "clip")
    streams = {s["codec_type"] for s in ffmpeg.probe(path)["streams"]}
    assert path.suffix == ".mp4" and streams == {"video", "audio"}
    assert ffmpeg.video_size(path) == (1920, 1080)
    assert ffmpeg.duration_s(path) == pytest.approx(2.0, abs=0.1)
    assert fake.thumbnail(chosen) is not None and (fake.searches, fake.fetches) == (1, 1)
    assert clips.FakeClipSource("pixabay", nothing_for={QUERY}).search(QUERY, 3) == []
    assert clips.FakeClipSource("pixabay", nothing_found=True).search("anything", 3) == []


# --- the asset step (058 (1)-(8)) ------------------------------------------------------------
#
# The step helpers are `tests.test_assets`'s; a clip beat is a concept beat of kind `clip`.

CLOUDS = "clouds drifting over hills"


def _clip_beat(
    i: int = 1, *, query: str = CLOUDS, length: float = 2.0, asset: str | None = None
) -> Beat:
    return _beat(i, "concept", kind="clip", query=query, fallback="sky", depicts="scene",
                 length=length, asset=asset)  # fmt: skip


def _run_clips(
    tmp_path: Path,
    beats: list[Beat],
    *,
    clips_by_name: Mapping[str, clips.ClipSource] | None = None,
    sources: dict[str, assets.ImageSource] | None = None,
    log: list[str] | None = None,
    job: Path | None = None,
) -> assets.AssetManifest:
    if clips_by_name is None:
        clips_by_name = {"pexels": clips.FakeClipSource("pexels")}
    return assets.source_assets(
        _plan(beats), [], "any", spec=SPEC,
        sources=sources if sources is not None else {"web": assets.FakeImageSource("web")},
        order=assets.DEFAULT_ORDER,
        clips=clips_by_name,
        job_dir=job or _job_dir(tmp_path),
        log=(log if log is not None else []).append,
    )  # fmt: skip


def test_a_clip_beat_takes_a_stock_clip_from_pexels_video_before_pixabay(tmp_path: Path) -> None:
    """058 (1, 3, 8): the clip is fetched into the job's asset folder, recorded as a
    `clip` asset with its real size and length, shown as the `clip` treatment at rung 0,
    with one rights row and a "Video by <name> on Pexels" credit line."""
    pexels, pixabay = clips.FakeClipSource("pexels"), clips.FakeClipSource("pixabay")
    job = _job_dir(tmp_path)
    log: list[str] = []
    both = {"pexels": pexels, "pixabay": pixabay}
    manifest = _run_clips(tmp_path, [_clip_beat()], clips_by_name=both, log=log, job=job)
    (beat,) = manifest.beats
    assert (beat.treatment, beat.fallback_rung, beat.treatment_downgraded) == ("clip", 0, False)
    record = manifest.asset("a1")
    assert record is not None and record.kind == "clip" and record.origin == "pexels"
    assert (record.width, record.height) == (1080, 1920)
    assert record.duration_s == pytest.approx(3.0, abs=0.1)
    assert record.file.startswith("work/assets/") and record.file.endswith(".mp4")
    assert (job / record.file).is_file() and record.licence == clips.PEXELS_LICENCE
    assert (pexels.searches, pexels.fetches, pixabay.searches) == (1, 1, 0)
    rows = rights.rows(manifest, _plan([_clip_beat()]).picture)
    assert [(r.kind, r.origin, r.beat_ids) for r in rows] == [("clip", "pexels", ["b01"])]
    credits = rights.credits(rows)
    assert credits.startswith("Video by fake pexels video on Pexels via https://fake.invalid/pexels-video/")
    assert any("pexels video:" in line and "answered 200" in line for line in log)


def test_a_named_entity_beat_is_never_offered_a_clip(tmp_path: Path) -> None:
    """058 (2) with 053's F1 fixture: a clip beat whose subject is a named person keeps
    the still ladder; the clip sources are not even searched, and job.log says why."""
    pexels = clips.FakeClipSource("pexels")
    log: list[str] = []
    beat = _named(kind="clip", query=BABA)
    manifest = _run_clips(tmp_path, [beat], clips_by_name={"pexels": pexels}, log=log)
    assert pexels.searches == 0
    (shown,) = manifest.beats
    record = manifest.asset("a1")
    assert shown.treatment in ("photo", "card") and record is not None and record.kind == "image"
    assert any("b01" in line and "named entity" in line and "still ladder" in line for line in log)


def test_a_1920x1080_clip_is_accepted_and_a_1280x720_one_falls_to_the_still_ladder(
    tmp_path: Path,
) -> None:
    wide = clips.FakeClipSource("pexels", sizes={CLOUDS: (1920, 1080)})
    manifest = _run_clips(tmp_path, [_clip_beat()], clips_by_name={"pexels": wide})
    record = manifest.asset("a1")
    assert record is not None and record.kind == "clip"
    assert (record.width, record.height) == (1920, 1080)
    small = clips.FakeClipSource("pexels", size=(1280, 720))  # for the fallback query too
    log: list[str] = []
    manifest = _run_clips(tmp_path / "b", [_clip_beat()], clips_by_name={"pexels": small}, log=log)
    (shown,) = manifest.beats
    assert shown.treatment != "clip" and shown.fallback_rung == 0
    assert small.fetches == 0
    assert any("1280x720" in line and "covers 1080x1920" in line for line in log)
    fell = [line for line in log if "b01" in line and "no usable clip" in line]
    assert fell and "still ladder" in fell[0]


def test_a_clip_shorter_than_its_beat_is_skipped_for_the_next_candidate(tmp_path: Path) -> None:
    """058 (5): a 1.0 s clip cannot fill a 2.0 s beat; the next source's 3.0 s clip can.
    With no long enough clip anywhere the beat takes the still ladder, logged."""
    short = clips.FakeClipSource("pexels", duration_s=1.0)
    long = clips.FakeClipSource("pixabay")
    log: list[str] = []
    both = {"pexels": short, "pixabay": long}
    manifest = _run_clips(tmp_path, [_clip_beat()], clips_by_name=both, log=log)
    record = manifest.asset("a1")
    assert record is not None and record.origin == "pixabay" and record.kind == "clip"
    assert short.fetches == 0 and long.fetches == 1
    assert any("shorter than the 2" in line for line in log)
    log.clear()
    manifest = _run_clips(tmp_path / "b", [_clip_beat()], clips_by_name={"pexels": short}, log=log)
    assert manifest.beats[0].treatment != "clip"
    assert any("no usable clip" in line for line in log)


def test_the_clip_needed_covers_the_number_beats_that_carry_it_on(tmp_path: Path) -> None:
    """058 (5) / 4.2: a number beat over the clip plays it on, so the clip must run the
    length of both; the carried-on beat shows the same clip record."""
    beats = [_clip_beat(1), _beat(2, "number", query="two", length=2.0)]
    three = clips.FakeClipSource("pexels", duration_s=3.0)
    log: list[str] = []
    manifest = _run_clips(tmp_path, beats, clips_by_name={"pexels": three}, log=log)
    assert manifest.beats[0].treatment != "clip" and three.fetches == 0
    assert any("shorter than the 4" in line for line in log)
    five = clips.FakeClipSource("pexels", duration_s=5.0)
    manifest = _run_clips(tmp_path / "b", beats, clips_by_name={"pexels": five})
    first, second = manifest.beats
    assert (first.treatment, second.treatment) == ("clip", "clip")
    assert first.asset_id == second.asset_id == "a1"


def test_two_clip_beats_asking_the_same_query_fetch_once(tmp_path: Path) -> None:
    """5.6 / 056 (3): the second beat finds the file in the cache and shows it again (a
    clip counts as an image for `reuse_max`); a third is blocked and takes the next
    candidate."""
    pexels = clips.FakeClipSource("pexels")
    beats = [_clip_beat(1), _clip_beat(2)]
    manifest = _run_clips(tmp_path, beats, clips_by_name={"pexels": pexels})
    assert [b.treatment for b in manifest.beats] == ["clip", "clip"]
    assert (pexels.searches, pexels.fetches) == (1, 1)
    assert len({a.sha256 for a in manifest.assets}) == 1
    third = _run_clips(tmp_path / "b", [*beats, _clip_beat(3)],
                       clips_by_name={"pexels": clips.FakeClipSource("pexels")})  # fmt: skip
    assert [b.treatment for b in third.beats] == ["clip", "clip", "clip"]
    assert len({a.sha256 for a in third.assets}) == 2


def test_a_planned_reuse_of_an_earlier_clip_shows_it_again_without_a_search(tmp_path: Path) -> None:
    pexels = clips.FakeClipSource("pexels")
    beats = [_clip_beat(1), _clip_beat(2, query="something else", asset="a1")]
    manifest = _run_clips(tmp_path, beats, clips_by_name={"pexels": pexels})
    assert [b.asset_id for b in manifest.beats] == ["a1", "a1"]
    assert [b.treatment for b in manifest.beats] == ["clip", "clip"]
    assert (pexels.searches, pexels.fetches) == (1, 1)


def test_a_still_beat_never_shows_or_redresses_a_clip(tmp_path: Path) -> None:
    """A photo beat naming a clip's asset is sourced afresh (logged); a rescue never
    re-dresses a clip (it is not a still), so with nothing found the beat is rung 4."""
    web = assets.FakeImageSource("web", nothing_for={"nothing here", "nothing at all"})
    beats = [
        _clip_beat(1),
        _beat(2, "concept", query="nothing here", fallback="nothing at all", asset="a1"),
    ]
    log: list[str] = []
    manifest = _run_clips(tmp_path, beats, sources={"web": web}, log=log)
    first, second = manifest.beats
    assert first.treatment == "clip"
    assert (second.asset_id, second.fallback_rung, second.treatment) == (None, 4, "gradient")
    assert any("b02" in line and "clip" in line and "still" in line for line in log)


def test_pixabays_key_never_reaches_the_job_log(tmp_path: Path) -> None:
    """058 (8): a candidate line the step logs (a file that cannot cover the frame) has
    the key blanked out even when the site put it in the URL."""
    secret = KEY.get_secret_value()
    medium = {
        "url": f"https://cdn.pixabay.com/video/x_medium.mp4?key={secret}",
        "width": 1280, "height": 720, "size": 100,
        "thumbnail": "https://cdn.pixabay.com/video/x.jpg",
    }  # fmt: skip
    hit = {"id": 1, "pageURL": f"https://pixabay.com/videos/x-1/?key={secret}", "duration": 8,
           "user": "U", "videos": {"medium": medium}}  # fmt: skip
    pixabay = clips.PixabayClipSource(api_key=KEY, client=Recorded({"hits": [hit]}).client())
    log: list[str] = []
    _run_clips(tmp_path, [_clip_beat()], clips_by_name={"pixabay": pixabay}, log=log)
    joined = "\n".join(log)
    assert secret not in joined
    assert "key=***" in joined and "pixabay video:" in joined


def _settings(**overrides: object) -> config.Settings:
    return config.Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue, reportArgumentType]


def _no_ledger() -> Ledger:
    raise AssertionError("no ledger needed")


def test_from_settings_builds_the_clip_sources_on_the_image_keys() -> None:
    """058 (3): Pexels video and Pixabay video ride the same free keys; a source left out
    of ASSET_SOURCES, or one whose key is unset, gives no clip source either."""
    none = assets.from_settings(_settings(), ledger=_no_ledger)
    assert none.clips == {} and none.clip_order == clips.CLIP_ORDER
    both = assets.from_settings(
        _settings(pexels_api_key=SecretStr("p"), pixabay_api_key=SecretStr("x")), ledger=_no_ledger
    )
    kinds = [type(s) for s in both.clips.values()]
    assert kinds == [clips.PexelsClipSource, clips.PixabayClipSource]
    assert list(both.clips) == ["pexels", "pixabay"]
    only = assets.from_settings(
        _settings(pexels_api_key=SecretStr("p"), pixabay_api_key=SecretStr("x"),
                  asset_sources="owner,web,pixabay,generate"),
        ledger=_no_ledger,
    )  # fmt: skip
    assert list(only.clips) == ["pixabay"]


# --- 110b: below the clip share target with no usable clip ------------------


def test_no_usable_clip_delivers_below_the_target_with_a_logged_reason(tmp_path: Path) -> None:
    """The low end is a target, never a gate: every clip beat that finds no usable clip
    takes a still, sourcing returns the manifest (no failure) and job.log says why."""
    small = clips.FakeClipSource("pexels", size=(1280, 720))  # never covers 1080x1920
    log: list[str] = []
    manifest = _run_clips(tmp_path, [_clip_beat()], clips_by_name={"pexels": small}, log=log)
    (shown,) = manifest.beats
    assert shown.treatment != "clip"
    below = [line for line in log if "clip_share_target" in line]
    assert len(below) == 1 and "below" in below[0] and "b01" in below[0]
    assert "never a gate" in below[0]


def test_a_clip_share_inside_the_target_logs_nothing(tmp_path: Path) -> None:
    log: list[str] = []
    manifest = _run_clips(tmp_path, [_clip_beat()], log=log)
    assert manifest.asset("a1") is not None
    assert not [line for line in log if "clip_share_target" in line]
