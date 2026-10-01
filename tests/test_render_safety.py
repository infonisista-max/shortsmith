"""111f: the test that would have caught job 20261001-082005-826f78 (b52, a stock clip as
a wall's background). A whole job runs through the real renderer (real driver, real
mux) on the fixture clip with a plan in which every beat kind appears, and every asset
the sourcing step wrote is broken on disk before the picture is built:

1. a clip where a still was expected;
2. an image whose extension lies (WebP saved as .jpg, PNG saved as .mp4);
3. a missing file.

The job delivers each time: the short is the cut's length with an audio stream,
`job.log` has the 111c `check:` lines and the page carries its warning. Two more runs
take the safety net away to prove the rungs behind it: one broken wall cell (b52
itself) is simplified by the 111d net, and a picture broken on every beat ends in the
111g plain reel. None of this is faked below the spec: the failures are Chrome's own."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Literal, get_args

import pytest
from PIL import Image

from shortsmith import (
    assets,
    ffmpeg,
    fixture,
    geo,
    jobs,
    media,
    pipeline,
    presenter,
    render,
    render_check,
    smoke,
    sound,
)
from shortsmith.contracts import TIER1_KINDS, TIER2_KINDS, AssetRecord, BeatSpec, RenderSpec
from shortsmith.fixture import make_clip
from shortsmith.planner import FakePlanner
from shortsmith.qa.critic import FakeCritic
from shortsmith.qa.gate import FakeGate
from shortsmith.transcriber import FakeTranscriber
from tests.test_plain_reel import SPECS, _uploaded  # pyright: ignore[reportPrivateUsage]

Variant = Literal["clip_for_still", "lying_extension", "missing"]
VARIANTS: tuple[Variant, ...] = get_args(Variant)
# Every kind a beat can carry (`contracts.Kind`); the renderer draws each.
ALL_KINDS = {*TIER1_KINDS, *TIER2_KINDS}

# The fake plan draws eleven of the kinds as beats and six more as the overlays and
# events its set pieces carry; the other three are beats this test splits off (a
# tier-2 kind never leaves the grammar today, but the renderer must still draw one),
# the presenter_pip one carrying the lower third the plan's card strip hides.
SPLIT_OFF: dict[str, tuple[str, ...]] = {
    "photo": ("parallax", "vector_illustration"),
    "clip": ("presenter_pip",),
}


def _overlay(beat: BeatSpec) -> set[str]:
    out: set[str] = set()
    out |= {"stamp"} if beat.stamp else set()
    out |= {"lower_third"} if beat.lower_third else set()
    out |= {"counter"} if beat.counter else set()
    out |= {"label_flyin"} if beat.infographic and beat.infographic.labels else set()
    if beat.map is not None:
        out |= {k for k in ("pin_drop", "route_arrow", "object_path") if getattr(beat.map, k)}
    return out


def kinds_drawn(spec: RenderSpec) -> set[str]:
    """Every kind `spec` draws: a beat's own kind, or an overlay or event it carries."""
    return {b.kind for b in spec.beats} | {k for b in spec.beats for k in _overlay(b)}


def _every_kind(spec: RenderSpec) -> RenderSpec:
    """`spec` with the SPLIT_OFF kinds cut out of the end of the beat they follow."""
    beats: list[BeatSpec] = []
    for beat in spec.beats:
        extra = SPLIT_OFF.get(beat.kind, ())
        if not extra:
            beats.append(beat)
            continue
        step = (beat.end_frame - beat.start_frame) // (len(extra) + 1)
        assert step >= 2, f"{beat.id} is too short to split"
        start = beat.start_frame
        for i, kind in enumerate((beat.kind, *extra)):
            end = beat.end_frame if i == len(extra) else start + step
            update: dict[str, object] = {"id": beat.id if not i else f"{beat.id}{kind[0]}",
                                         "kind": kind, "start_frame": start, "end_frame": end}
            if i:
                update.update(stamp=None, lower_third=None, counter=None, enter="cut")
            if kind == "presenter_pip":
                # The plan's one lower third hides under its card strip; this one shows.
                label = render.lower_third_spec("Ada Lovelace · mathematician",
                                                numbers=render.style_numbers("explainer"))
                update.update(visual=None, mode="pip", lower_third=label)
            beats.append(beat.model_copy(update=update))
            start = end
    return spec.model_copy(update={"beats": beats})


# --- breaking the sourced assets on disk ---------------------------------------------------


def _png(path: Path, fmt: str = "PNG") -> None:
    Image.new("RGB", (480, 640), (40, 120, 200)).save(path, format=fmt)


def _break(job_dir: Path, variant: Variant, scratch: Path) -> int:
    """Break every sourced asset as `variant` says; the number of files broken."""
    manifest = assets.load_manifest(job_dir)
    assert manifest is not None and manifest.assets, "sourcing wrote no assets"
    clip = make_clip(scratch / "stock.mp4", duration_s=1.0, width=320, height=240, audio=False)
    records: list[AssetRecord] = []
    broken = 0
    for i, record in enumerate(manifest.assets):
        path = job_dir / record.file
        is_clip = media.probe(path) == "video"
        if variant == "clip_for_still" and not is_clip:
            shutil.copyfile(clip, path)
        elif variant == "lying_extension" and (is_clip or i % 2):
            moved = path.with_suffix(".mp4") if not is_clip else path
            path.unlink(missing_ok=True)
            _png(moved)
            record = record.model_copy(update={"file": moved.relative_to(job_dir).as_posix()})
        elif variant == "lying_extension":
            _png(path, "WEBP")
        elif variant == "missing":
            path.unlink(missing_ok=True)
        else:
            records.append(record)
            continue
        broken += 1
        records.append(record)
    assets.write_manifest(job_dir, manifest.model_copy(update={"assets": records}))
    return broken


# --- the job ---------------------------------------------------------------------------------


class Run:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                 fixture_clip: Path, library: sound.Library) -> None:  # fmt: skip
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.clip = fixture_clip
        self.library = library
        self.built: list[RenderSpec] = []

    def go(self, *, before: Callable[[jobs.Job], object] = lambda _j: None,
           after: Callable[[RenderSpec], RenderSpec] = lambda s: s) -> jobs.Job:  # fmt: skip
        """The job end to end; `before` runs once on the job before its first spec is
        built, `after` edits every spec built (the net's re-renders keep the edit)."""
        real = render.spec_for_job
        done: list[bool] = []

        def spec_for_job(job: jobs.Job, **kw: object) -> RenderSpec:
            if not done:
                before(job)
                done.append(True)
            spec = after(_every_kind(real(job, **kw)))  # pyright: ignore[reportArgumentType]
            self.built.append(spec)
            return spec

        self.monkeypatch.setattr(render, "spec_for_job", spec_for_job)
        job = _uploaded(self.tmp / "data", self.clip)
        return pipeline.run_job(
            job, transcriber=FakeTranscriber(), planner=FakePlanner(),
            renderer=render.RemotionRenderer(search=sound.FakeAudioSearch(),
                                             geocoder=geo.FakeGeocoder()),
            gate=FakeGate(), sourcing=smoke.smoke_sourcing(), specs=SPECS,
            library=self.library, detector=presenter.FakeFaceDetector(), critic=FakeCritic(),
        )  # fmt: skip


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixture_clip: Path,
        library: sound.Library) -> Run:  # fmt: skip
    return Run(tmp_path, monkeypatch, fixture_clip, library)


def _assert_short(done: jobs.Job) -> None:
    short = done.out_dir / "short.mp4"
    assert short.is_file()
    streams = {s["codec_type"] for s in ffmpeg.probe(short)["streams"]}
    assert streams >= {"video", "audio"}, streams
    assert ffmpeg.duration_s(short) == pytest.approx(fixture.DURATION_S, abs=0.25)


def _log(done: jobs.Job) -> str:
    return done.log_path.read_text(encoding="utf-8")


def test_the_kind_list_is_complete() -> None:
    """A new kind fails here until this file draws it."""
    planned = {"photo", "card", "clip", "presenter_full", "map", "chart", "infographic",
               "list", "split", "wall", "finale"}  # fmt: skip
    carried = {"stamp", "lower_third", "counter", "label_flyin", "pin_drop", "route_arrow",
               "object_path"}  # fmt: skip
    split_off = {k for ks in SPLIT_OFF.values() for k in ks}
    assert planned | carried | split_off == ALL_KINDS


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_kind_with_a_bad_asset_still_delivers(run: Run, variant: Variant) -> None:
    broken: list[int] = []
    done = run.go(before=lambda job: broken.append(_break(job.path, variant, run.tmp)))

    assert done.status == "delivered", done.record.error
    assert broken and broken[0] > 0
    assert kinds_drawn(run.built[0]) == ALL_KINDS
    assert not done.record.plain_reel, _log(done)[-3000:]
    _assert_short(done)
    log = _log(done)
    assert "check: " in log
    # The check repaired every asset before node started: the net had nothing to catch.
    assert "rescue: render net" not in log, log[-3000:]
    assert any(w.endswith("left out before rendering") for w in done.record.warnings), (
        done.record.warnings
    )


# --- with the check taken away: the rungs behind it -------------------------------------------


def _no_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def unchecked(spec: RenderSpec, **_k: object) -> render_check.Checked:
        return render_check.Checked(spec)

    monkeypatch.setattr(render_check, "check", unchecked)


def test_b52_a_clip_as_a_wall_cell_is_simplified_by_the_net(run: Run) -> None:
    """Today's job in small: Chrome cannot draw an .mp4 in a wall cell's <Img>."""
    _no_check(run.monkeypatch)
    clip = make_clip(run.tmp / "stock" / "clip-1.mp4", duration_s=1.0, width=320, height=240,
                     audio=False)  # fmt: skip

    def clip_in_the_wall(spec: RenderSpec) -> RenderSpec:
        beats: list[BeatSpec] = []
        for beat in spec.beats:
            if beat.wall is not None:
                cells = [beat.wall.cells[0].model_copy(update={"src": str(clip)}),
                         *beat.wall.cells[1:]]  # fmt: skip
                beat = beat.model_copy(update={"wall": beat.wall.model_copy(
                    update={"cells": cells})})  # fmt: skip
            beats.append(beat)
        return spec.model_copy(update={"beats": beats})

    done = run.go(after=clip_in_the_wall)

    assert done.status == "delivered", done.record.error
    assert not done.record.plain_reel, _log(done)[-3000:]
    wall = next(b.id for b in run.built[0].beats if b.wall is not None)
    assert f"rescue: render net: round 1/3: {wall} simplified" in _log(done)
    number = wall.lstrip("b").lstrip("0")
    assert any(f"beat {number}" in w and "simple picture" in w
               for w in done.record.warnings), done.record.warnings  # fmt: skip
    _assert_short(done)


def test_a_picture_broken_on_every_beat_delivers_the_plain_reel(run: Run) -> None:
    """Every sourced file gone and nothing to repair it before node: each beat that
    draws one fails in Chrome, more than the net's rounds can simplify."""
    _no_check(run.monkeypatch)

    done = run.go(before=lambda job: _break(job.path, "missing", run.tmp))

    assert done.status == "delivered", done.record.error
    assert done.record.plain_reel
    assert any(w.startswith(pipeline.PLAIN_LEAD) for w in done.record.warnings)
    assert any(d.choice == pipeline.PLAIN_CHOICE for d in done.record.decisions)
    log = _log(done)
    assert "rescue: render net" in log and "plain reel:" in log
    _assert_short(done)
