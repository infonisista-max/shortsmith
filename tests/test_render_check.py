"""111c: the pre-render check (`shortsmith.render_check`). Every `src` in a finished
spec is probed against what its slot draws (a still or a clip) and repaired before node
starts: a clip in a still's slot becomes its frame grab, a still in a clip's slot is
drawn as a photo, a browser-unsafe file is converted, and a missing or unreadable file
falls back to the beat's next good asset, the gradient (a base) or is dropped (an
item). Each repair is one `check: bNN: ...` line; nothing here ever raises."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from shortsmith import captions, fixture, media, render, render_check
from shortsmith.contracts import (
    AssetManifest,
    AssetRecord,
    BadgeSpec,
    BeatAsset,
    BeatSpec,
    CardBox,
    Constraints,
    ListRow,
    ListSpec,
    PlanRequest,
    PlanStyle,
    RenderSpec,
    SplitPane,
    SplitSpec,
    StickerSpec,
    VisualSpec,
    WallSpec,
)
from shortsmith.fixture import make_clip
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber


def _base_spec() -> RenderSpec:
    transcript = FakeTranscriber().transcribe(Path("unused.mp4"))
    plan = FakePlanner().plan_picture(PlanRequest(
        brief="Topic: a six-second synthetic clip.", style=PlanStyle(name="explainer"),
        style_note="explainer", transcript=transcript, references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    ))  # fmt: skip
    caps = captions.build(transcript, plan, render.loaded_styles()["explainer"])
    return render.build_spec(
        plan, caps, presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
    )  # fmt: skip


def _image(path: Path, *, fmt: str = "JPEG", size: tuple[int, int] = (320, 400)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (170, 85, 51)).save(path, format=fmt)
    return path


def _clip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return make_clip(path, duration_s=1.0, width=320, height=240, audio=False)


def _visual(src: Path, treatment: str = "photo") -> VisualSpec:
    return VisualSpec.model_validate({
        "treatment": treatment, "src": str(src), "width": 320, "height": 400, "zoom": 1.0,
        "focus_x": 0.5, "focus_y": 0.5, "scale_from": 1.0, "scale_to": 1.08, "pan_px": 0.0,
    })  # fmt: skip


def _card(src: Path) -> CardBox:
    return CardBox(src=str(src), width=320, height=400, left=0, top=0, box_width=300,
                   box_height=300, image_width=280, image_height=280, border_px=8,
                   rotate_deg=0)  # fmt: skip


def _sticker(src: Path) -> StickerSpec:
    return StickerSpec(name="star", src=str(src), left=10, top=10, size=200, scale_from=0.6,
                       at_s=0.2, pop_s=0.3, until_s=1.0, float_px=6, float_period_s=2,
                       shadow_px=8)  # fmt: skip


def _with_beat(spec: RenderSpec, **update: object) -> RenderSpec:
    beat = spec.beats[0].model_copy(update={"mode": "off", **update})
    return spec.model_copy(update={"beats": [beat, *spec.beats[1:]]})


def _srcs_and_slots(beat: BeatSpec) -> list[tuple[str, str]]:
    """Every (src, slot kind) the beat draws."""
    out: list[tuple[str, str]] = []
    if beat.visual is not None:
        out.append((beat.visual.src, "video" if beat.visual.treatment == "clip" else "image"))
    out += [(c.src, "image") for c in beat.wall.cells] if beat.wall else []
    out += [(c.src, "image") for c in beat.finale.cards] if beat.finale else []
    out += [(s.src, "image") for s in beat.stickers]
    if beat.split is not None:
        out += [(p.src, "image") for p in beat.split.panes]
        out += [(beat.split.badge.src, "image")] if beat.split.badge else []
    out += [(r.icon_src, "image") for r in beat.list.rows if r.icon_src] if beat.list else []
    return out


def _all_good(beat: BeatSpec) -> None:
    for src, slot in _srcs_and_slots(beat):
        assert media.probe(Path(src)) == slot, src
        assert media.is_browser_safe(Path(src)), src


# --- the mixed bag the ticket names ---------------------------------------------------


def test_every_src_probes_as_its_slots_kind_after_the_check(tmp_path: Path) -> None:
    clip = _clip(tmp_path / "a" / "clip-1.mp4")
    good = _image(tmp_path / "a" / "good.jpg")
    mislabelled = _image(tmp_path / "a" / "webp.jpg", fmt="WEBP")
    gif = _image(tmp_path / "a" / "anim.gif", fmt="GIF")
    missing = tmp_path / "a" / "gone.jpg"
    empty = tmp_path / "a" / "empty.png"
    empty.write_bytes(b"")
    wall = WallSpec(cells=[_card(clip), _card(mislabelled), _card(gif), _card(missing),
                           _card(empty), _card(good)], columns=3, spring_s=0.4)  # fmt: skip
    spec = _with_beat(_base_spec(), visual=_visual(clip), wall=wall,
                      stickers=(_sticker(empty), _sticker(gif)))  # fmt: skip

    checked = render_check.check(spec)

    beat = checked.spec.beats[0]
    _all_good(beat)
    assert beat.visual is not None and beat.visual.treatment == "photo"
    assert Path(beat.visual.src).name == "clip-1-frame.jpg"
    assert beat.wall is not None and len(beat.wall.cells) == 4  # missing + empty dropped
    assert len(beat.stickers) == 1
    b = spec.beats[0].id
    assert all(line.startswith(f"check: {b}: ") and " -> " in line for line in checked.lines)
    # clip base, clip cell, webp, gif cell, missing, empty cell, empty + gif sticker
    assert len(checked.lines) == 8
    assert checked.repairs == 8


def test_a_clean_spec_passes_unchanged_with_no_lines(tmp_path: Path) -> None:
    spec = _with_beat(_base_spec(), visual=_visual(_image(tmp_path / "ok.jpg")))
    checked = render_check.check(spec)
    assert checked.spec == spec
    assert checked.lines == []
    assert render_check.warning(checked.repairs) is None


def test_a_still_in_a_clip_slot_is_drawn_as_a_photo_with_the_camera_move(tmp_path: Path) -> None:
    still = _image(tmp_path / "still.jpg", size=(640, 480))
    spec = _with_beat(_base_spec(), visual=_visual(still, "clip").model_copy(
        update={"speed": 0.8, "start_s": 2.0, "width": 1920, "height": 1080}))
    visual = render_check.check(spec).spec.beats[0].visual
    assert visual is not None and visual.treatment == "photo"
    assert (visual.width, visual.height, visual.start_s) == (640, 480, 0.0)
    assert (visual.scale_from, visual.scale_to) == (1.0, 1.08)


def test_a_non_h264_clip_in_a_clip_slot_is_converted(tmp_path: Path) -> None:
    from shortsmith import ffmpeg

    raw = tmp_path / "raw.mov"
    ffmpeg.run([ffmpeg.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=0x3355AA:s=320x240:r=25:d=1", "-c:v", "mpeg4", str(raw)])  # fmt: skip
    spec = _with_beat(_base_spec(), visual=_visual(raw, "clip"))
    checked = render_check.check(spec)
    visual = checked.spec.beats[0].visual
    assert visual is not None and visual.treatment == "clip"
    assert Path(visual.src).suffix == ".mp4" and media.is_browser_safe(Path(visual.src))
    assert len(checked.lines) == 1


def test_a_missing_base_falls_back_to_the_beats_next_good_asset(tmp_path: Path) -> None:
    spec = _base_spec()
    b = spec.beats[0].id
    good = _image(tmp_path / "work" / "assets" / "h" / "copy.jpg")
    record = {"origin": "web", "sha256": "abc", "width": 320, "height": 400,
              "fetched_at": "2026-10-01T00:00:00Z"}  # fmt: skip
    manifest = AssetManifest(
        assets=[AssetRecord.model_validate({**record, "id": "a1", "file": "work/gone.jpg"}),
                AssetRecord.model_validate({**record, "id": "a2",
                                            "file": "work/assets/h/copy.jpg"})],
        beats=[BeatAsset(beat_id=b, asset_id="a1", treatment="photo", fallback_rung=0)],
        runtime_s=6.0, rescued_max=1,
    )  # fmt: skip
    spec = _with_beat(spec, visual=_visual(tmp_path / "work" / "gone.jpg"))
    checked = render_check.check(spec, manifest=manifest, job_dir=tmp_path)
    visual = checked.spec.beats[0].visual
    assert visual is not None and Path(visual.src) == good.resolve()
    assert len(checked.lines) == 1 and "copy.jpg" in checked.lines[0]


def test_a_missing_base_with_nothing_else_falls_to_the_gradient(tmp_path: Path) -> None:
    spec = _with_beat(_base_spec(), visual=_visual(tmp_path / "gone.jpg"))
    checked = render_check.check(spec)
    beat = checked.spec.beats[0]
    assert beat.visual is None and beat.mode == "pip"
    assert "gradient" in checked.lines[0]


def test_bad_items_are_dropped_or_blanked(tmp_path: Path) -> None:
    gone = tmp_path / "gone.jpg"
    good = _image(tmp_path / "ok.jpg")
    pane = SplitPane(src=str(good), width=320, height=400, left=0, top=0, pane_width=10,
                     pane_height=10)  # fmt: skip
    split = SplitSpec.model_construct(
        panes=[pane, pane], badge=BadgeSpec(src=str(gone), width=1, height=1, left=0, top=0,
                                            diameter=10, ring_px=2, ring_color="#fff"))  # fmt: skip
    rows = [ListRow(text="x", font_px=10, left=0, top=0, width=10, height=10, text_left=0,
                    icon_src=str(gone))]  # fmt: skip
    listed = ListSpec.model_construct(rows=rows)
    spec = _with_beat(_base_spec(), visual=_visual(good), split=split, list=listed)
    beat = render_check.check(spec).spec.beats[0]
    assert beat.split is not None and beat.split.badge is None
    assert beat.list is not None and beat.list.rows[0].icon_src == ""


def test_a_conversion_goes_to_the_cache_dir_when_one_is_given(tmp_path: Path) -> None:
    gif = _image(tmp_path / "job" / "anim.gif", fmt="GIF")
    cache = tmp_path / "scratch"
    spec = _with_beat(_base_spec(), visual=_visual(gif))
    visual = render_check.check(spec, cache_dir=cache).spec.beats[0].visual
    assert visual is not None and Path(visual.src).parent == cache
    assert sorted(p.name for p in gif.parent.iterdir()) == ["anim.gif"]


@pytest.mark.parametrize(("count", "expected"), [
    (1, "1 picture was swapped for a safe version or left out before rendering"),
    (3, "3 pictures were swapped for safe versions or left out before rendering"),
])  # fmt: skip
def test_the_page_warning_counts_the_repairs(count: int, expected: str) -> None:
    assert render_check.warning(count) == expected


def test_render_picture_checks_the_spec_before_the_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shortsmith import jobs

    job = jobs.create(tmp_path)
    gif = _image(job.path / "work" / "assets" / "h" / "anim.gif", fmt="GIF")
    spec = _with_beat(_base_spec(), visual=_visual(gif))
    seen: list[RenderSpec] = []
    def spec_for_job(*_: object, **__: object) -> RenderSpec:
        return spec

    def run_driver(s: RenderSpec, **_: object) -> None:
        seen.append(s)

    monkeypatch.setattr(render, "spec_for_job", spec_for_job)
    monkeypatch.setattr(render, "run_driver", run_driver)

    render.render_picture(job)

    visual = seen[0].beats[0].visual
    assert visual is not None and media.is_browser_safe(Path(visual.src))
    assert "check: " in (job.path / "job.log").read_text(encoding="utf-8")
    assert jobs.load(job.path).record.warnings == [render_check.warning(1)]


def test_two_assets_of_one_name_stay_apart_in_the_cache_dir(tmp_path: Path) -> None:
    one = _image(tmp_path / "h1" / "image.gif", fmt="GIF", size=(100, 100))
    two = _image(tmp_path / "h2" / "image.gif", fmt="GIF", size=(200, 100))
    wall = WallSpec(cells=[_card(one), _card(two)], columns=2, spring_s=0.4)
    spec = _with_beat(_base_spec(), visual=_visual(_image(tmp_path / "ok.jpg")), wall=wall)
    beat = render_check.check(spec, cache_dir=tmp_path / "cache").spec.beats[0]
    assert beat.wall is not None
    assert [(c.width, c.height) for c in beat.wall.cells] == [(100, 100), (200, 100)]
    assert beat.wall.cells[0].src != beat.wall.cells[1].src
