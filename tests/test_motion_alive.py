"""Ticket 102: pictures and clips move like an editor moved them.

The clip file choice (the smallest file at least 1080 px wide, else the largest), the
local ffmpeg motion measure on generated fixtures (a still `color` clip against a moving
`testsrc2` one), the window that starts at the clip's most moving stretch, a clip that
does not move passed over for the still ladder, `beat.motion` mapped to distinct moves
from `broll.motion_moves`, the era grade on a `timeless` pick, and (fold-in) every crop
and push that aims at a face aiming at the beat's subject - the face the card's ring
circles - never at a larger stranger."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import assets, ffmpeg, presenter, render
from shortsmith.assets import clips
from shortsmith.assets.clips import ClipCandidate, ClipFile
from shortsmith.contracts import (
    AssetManifest,
    AssetRecord,
    Beat,
    BeatAsset,
    FaceBox,
    VisualSpec,
)
from shortsmith.ffmpeg import FFMPEG
from tests.test_assets_clips import (
    _clip_beat,  # pyright: ignore[reportPrivateUsage]
    _run_clips,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_treatments import _plan as plan_of  # pyright: ignore[reportPrivateUsage]

MAX_UPSCALE = 2.0  # explainer's broll.full_bleed_max_upscale (057)
FPS = 4.0  # explainer's broll.motion.clip.motion_fps


def _hit(*sizes: tuple[int, int]) -> ClipCandidate:
    files = [
        ClipFile(url=f"https://videos.example/{w}x{h}.mp4", width=w, height=h,
                 size_bytes=w * h)
        for w, h in sizes
    ]  # fmt: skip
    return ClipCandidate(
        url=files[0].url, page_url="https://videos.example/page", width=files[0].width,
        height=files[0].height, duration_s=8.0, files=files,
    )  # fmt: skip


# --- the file choice ---------------------------------------------------------------------------


def test_the_smallest_file_at_least_1080_wide_is_chosen_over_a_smaller_upscale() -> None:
    """run05 b18: Pexels served 540x960 (a 2x upscale, passing the bar) beside 1080x1920
    and 2160x3840; the 1080 file is taken, never the soft 540 one."""
    hit = _hit((540, 960), (1080, 1920), (2160, 3840), (720, 1280))
    chosen = clips.choose_file(hit, max_upscale=MAX_UPSCALE)
    assert chosen is not None and (chosen.width, chosen.height) == (1080, 1920)


def test_with_no_file_1080_wide_the_largest_passing_file_is_chosen() -> None:
    hit = _hit((540, 960), (720, 1280), (640, 1138))
    chosen = clips.choose_file(hit, max_upscale=MAX_UPSCALE)
    assert chosen is not None and (chosen.width, chosen.height) == (720, 1280)


# --- the motion measure (local ffmpeg, no API) ------------------------------------------------


def _still_clip(path: Path, seconds: float = 3.0) -> Path:
    ffmpeg.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                f"color=c=0x336699:s=540x960:r=30:d={seconds:g}", "-c:v", "libx264",
                "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)])  # fmt: skip
    return path


def _moving_clip(path: Path, seconds: float = 3.0) -> Path:
    return clips.make_test_clip(path, width=540, height=960, duration_s=seconds)


def _still_then_moving(path: Path) -> Path:
    """3 s of a still frame, then 3 s of `testsrc2`: the moving stretch starts at 3 s."""
    ffmpeg.run([
        FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x336699:s=540x960:r=30:d=3",
        "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=3",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
    ])  # fmt: skip
    return path


def test_a_moving_clip_scores_far_above_a_still_one(tmp_path: Path) -> None:
    still = clips.motion_profile(_still_clip(tmp_path / "still.mp4"), fps=FPS)
    moving = clips.motion_profile(_moving_clip(tmp_path / "moving.mp4"), fps=FPS)
    assert len(moving) >= 10 and len(still) >= 10
    assert max(still) < 0.002
    assert sum(moving) / len(moving) > 0.005
    # the style's bar sits between the two
    bar = float(render.loaded_styles()["explainer"].broll.motion["clip"]["motion_min"])
    assert max(still) < bar < min(moving)


def test_the_window_starts_at_the_most_moving_stretch(tmp_path: Path) -> None:
    path = _still_then_moving(tmp_path / "mixed.mp4")
    profile = clips.motion_profile(path, fps=FPS)
    start, score = clips.best_window(profile, fps=FPS, need_s=2.0, duration_s=6.0)
    assert 2.75 <= start <= 4.0
    assert score > 0.005
    # the window never runs past the file's end
    start, _ = clips.best_window(profile, fps=FPS, need_s=5.5, duration_s=6.0)
    assert start <= 0.5


def test_a_window_longer_than_the_measure_starts_at_zero() -> None:
    assert clips.best_window([0.1, 0.2], fps=FPS, need_s=3.0, duration_s=0.75) == (0.0, 0.15)
    assert clips.best_window([], fps=FPS, need_s=1.0, duration_s=1.0) == (0.0, 0.0)


def test_the_explainer_numbers_are_read_from_front_matter() -> None:
    row = render.loaded_styles()["explainer"].broll.motion["clip"]
    assert float(row["motion_fps"]) == FPS
    assert 0.0 < float(row["motion_min"]) < 0.02
    with pytest.raises(KeyError):
        _ = row["no_such_number"]


# --- the asset step: a still clip is passed over, the window starts where it moves ---------


def test_the_fake_can_write_a_still_or_a_late_moving_clip(tmp_path: Path) -> None:
    still = clips.make_test_clip(tmp_path / "s.mp4", width=540, height=960, duration_s=2.0,
                                 still_s=2.0)  # fmt: skip
    late = clips.make_test_clip(tmp_path / "l.mp4", width=540, height=960, duration_s=4.0,
                                still_s=2.0)  # fmt: skip
    assert max(clips.motion_profile(still, fps=FPS)) < 0.002
    profile = clips.motion_profile(late, fps=FPS)
    assert max(profile[:6]) < 0.002 < min(profile[9:])
    assert ffmpeg.duration_s(late) == pytest.approx(4.0, abs=0.1)


def test_a_clip_that_does_not_move_is_passed_over_for_the_next_hit(tmp_path: Path) -> None:
    log: list[str] = []
    fake = clips.FakeClipSource("pexels", still={1})
    manifest = _run_clips(tmp_path, [_clip_beat()], clips_by_name={"pexels": fake}, log=log)
    (beat,) = manifest.beats
    record = manifest.asset(beat.asset_id or "")
    assert beat.treatment == "clip" and record is not None
    assert "/2.mp4" in record.source_url
    assert any("/1.mp4 skipped" in line and "motion_min" in line and "(102)" in line
               for line in log)  # fmt: skip


def test_when_no_hit_moves_the_beat_takes_a_still_and_says_so(tmp_path: Path) -> None:
    log: list[str] = []
    fake = clips.FakeClipSource("pexels", still=set(range(1, 11)))
    manifest = _run_clips(tmp_path, [_clip_beat()], clips_by_name={"pexels": fake}, log=log)
    (beat,) = manifest.beats
    assert beat.treatment != "clip" and beat.asset_id is not None
    assert any("no usable clip" in line and "still ladder" in line for line in log)


def test_the_clip_starts_at_its_most_moving_stretch(tmp_path: Path) -> None:
    fake = clips.FakeClipSource("pexels", duration_s=6.0, still_s=3.0)
    manifest = _run_clips(tmp_path, [_clip_beat(length=2.0)], clips_by_name={"pexels": fake})
    (beat,) = manifest.beats
    assert beat.treatment == "clip"
    assert 2.75 <= beat.clip_start_s <= 4.0


def test_the_rendered_clip_plays_from_the_chosen_second(tmp_path: Path) -> None:
    beat = Beat.model_validate({"id": "b01", "start": 0.0, "end": 2.0, "mode": "pip",
                                "kind": "clip", "motion": "push_in", "query": "clouds",
                                "subject_kind": "concept"})  # fmt: skip
    record = AssetRecord(id="c1", kind="clip", origin="pexels", file="assets/c1.mp4",
                         sha256="c", width=1080, height=1920, fetched_at="2026-09-30T00:00:00Z",
                         duration_s=6.0)  # fmt: skip
    manifest = AssetManifest(
        assets=[record], runtime_s=2.0, rescued_max=4,
        beats=[BeatAsset(beat_id="b01", asset_id="c1", treatment="clip", fallback_rung=0,
                         clip_start_s=3.25)],
    )  # fmt: skip
    out = render._visuals(  # pyright: ignore[reportPrivateUsage]
        plan_of([beat]), manifest, tmp_path, render.style_numbers("explainer"), pip_top=960,
    )  # fmt: skip
    _mode, visual = out["b01"]
    assert visual is not None and visual.treatment == "clip" and visual.start_s == 3.25
    assert assets.clip_speed(render.loaded_styles()["explainer"]) == visual.speed


# --- beat.motion is honoured: distinct moves from `broll.motion_moves` --------------------------

MOVES = ("push_in", "pull_out", "ken_burns_in", "ken_burns_out", "pan_left", "pan_right",
         "pan_up", "pan_down", "hold")  # fmt: skip
PORTRAIT = (1000, 1406)  # run05 b02: fills the frame, a full-screen photo
GROUP = (870, 614)  # run05 ref4: King Saud in India, an officer in the foreground
BIG = (1740, 1228)  # ref4 at twice the size: it covers the frame within crop_fill's 2.5x


def _still_beat(i: int, *, motion: str = "ken_burns_in", treatment: str | None = None,
                depicts: str = "scene", event: dict[str, str] | None = None) -> Beat:  # fmt: skip
    return Beat.model_validate({
        "id": f"b{i:02d}", "start": 2.0 * i, "end": 2.0 * i + 2.0, "mode": "pip",
        "kind": "photo", "motion": motion, "subject_kind": "entity",
        "query": f"archival photo {i}", "depicts": depicts, "treatment": treatment,
        **({"event": event} if event else {}),
    })  # fmt: skip


def _manifest(beats: list[Beat], size: tuple[int, int], *, fits: bool = True,
              era: str | None = None, kind: str = "image") -> AssetManifest:  # fmt: skip
    judge = {"model": "m", "score": 3, "era": era} if era else None
    records = [
        AssetRecord.model_validate({
            "id": f"a{i}", "kind": kind, "origin": "web", "file": f"assets/a{i}.jpg",
            "sha256": str(i), "width": size[0], "height": size[1],
            "fetched_at": "2026-09-30T00:00:00Z", "judge": judge,
        })
        for i in range(len(beats))
    ]  # fmt: skip
    decided = [
        BeatAsset(beat_id=b.id, asset_id=f"a{i}",
                  treatment="clip" if kind == "clip" else ("photo" if fits else "card"),
                  fallback_rung=0)
        for i, b in enumerate(beats)
    ]  # fmt: skip
    return AssetManifest(assets=records, beats=decided, runtime_s=beats[-1].end, rescued_max=4)


def _drawn(tmp_path: Path, beats: list[Beat], size: tuple[int, int], *, fits: bool = True,
           faces: list[FaceBox] | None = None, era: str | None = None,
           kind: str = "image") -> dict[str, VisualSpec]:  # fmt: skip
    out = render._visuals(  # pyright: ignore[reportPrivateUsage]
        plan_of(beats), _manifest(beats, size, fits=fits, era=era, kind=kind), tmp_path,
        render.style_numbers("explainer"), pip_top=960,
        faces_of=lambda _src: list(faces or []),
    )  # fmt: skip
    return {k: v for k, (_mode, v) in out.items() if v is not None}


def _row(name: str) -> tuple[float, float]:
    row = render.loaded_styles()["explainer"].broll.motion_moves[name]
    return row.scale_from, row.scale_to


def test_two_beats_with_different_motion_get_different_transforms(tmp_path: Path) -> None:
    beats = [_still_beat(0, motion="push_in"), _still_beat(1, motion="pan_left")]
    first, second = _drawn(tmp_path, beats, PORTRAIT).values()
    assert (first.treatment, second.treatment) == ("photo", "photo")
    assert (first.scale_from, first.scale_to) == _row("push_in")
    assert (second.scale_from, second.scale_to) == _row("pan_left")
    assert first.pan_px == 0.0 and second.pan_px != 0.0
    assert (first.scale_from, first.scale_to, first.pan_px) != (
        second.scale_from, second.scale_to, second.pan_px)


def test_every_named_move_is_real_and_distinct(tmp_path: Path) -> None:
    beats = [_still_beat(i, motion=m) for i, m in enumerate(MOVES)]
    drawn = list(_drawn(tmp_path, beats, PORTRAIT).values())
    transforms = {(v.scale_from, v.scale_to, v.pan_px, v.pan_y_px) for v in drawn}
    assert len(transforms) == len(MOVES)
    by = dict(zip(MOVES, drawn, strict=True))
    assert by["push_in"].scale_to > by["push_in"].scale_from
    assert by["pull_out"].scale_to < by["pull_out"].scale_from
    assert by["ken_burns_out"].scale_to < by["ken_burns_out"].scale_from
    assert by["pan_left"].pan_px == -by["pan_right"].pan_px != 0
    assert by["pan_up"].pan_y_px == -by["pan_down"].pan_y_px != 0
    assert by["hold"].scale_to - by["hold"].scale_from < 0.05


def test_a_drift_never_uncovers_the_frame_edge(tmp_path: Path) -> None:
    beats = [_still_beat(i, motion=m) for i, m in enumerate(MOVES)]
    for v in _drawn(tmp_path, beats, PORTRAIT).values():
        low = min(v.scale_from, v.scale_to)
        assert abs(v.pan_px) / 2 <= (low - 1) * 1080 / 2 + 1e-6
        assert abs(v.pan_y_px) / 2 <= (low - 1) * 1920 / 2 + 1e-6


def test_a_motion_with_no_move_row_keeps_the_styles_ken_burns(tmp_path: Path) -> None:
    (v,) = _drawn(tmp_path, [_still_beat(0, motion="reveal")], PORTRAIT).values()
    b = render.style_numbers("explainer").broll
    assert (v.scale_from, v.scale_to) == (b.photo_scale_from, b.photo_scale_to)


def test_crop_fill_takes_the_beats_move(tmp_path: Path) -> None:
    face = FaceBox(left=800, top=400, width=200, height=200)
    beat = _still_beat(0, motion="pull_out", treatment="crop_fill")
    (v,) = _drawn(tmp_path, [beat], BIG, fits=False, faces=[face]).values()
    assert v.treatment == "crop_fill"
    assert (v.scale_from, v.scale_to) == _row("pull_out")


def test_the_move_rows_are_checked_at_load() -> None:
    spec = render.loaded_styles()["explainer"]
    assert set(spec.broll.motion_moves) == set(MOVES)
    bad = spec.broll.model_dump()
    bad["motion_moves"] = {"spin": {"scale_from": 1.0, "scale_to": 1.1, "pan_x": 0.0,
                                    "pan_y": 0.0, "aim": "frame"}}  # fmt: skip
    with pytest.raises(ValueError, match="spin"):
        type(spec.broll).model_validate(bad)


# --- the subject face (fold-in): a crop never swaps the named person for a stranger -----------

OFFICER = FaceBox(left=80, top=156, width=90, height=90)  # the only face Haar finds on ref4
OFFICER2 = FaceBox(left=160, top=312, width=180, height=180)  # the same, on BIG


def test_crop_fill_on_a_named_person_frames_the_subject_not_the_largest_face(
    tmp_path: Path,
) -> None:
    saud = FaceBox(left=820, top=500, width=100, height=100)  # at the ring's point, smaller
    beat = _still_beat(0, motion="push_in", treatment="crop_fill", depicts="named_person")
    (v,) = _drawn(tmp_path, [beat], BIG, fits=False, faces=[OFFICER2, saud]).values()
    assert v.treatment == "crop_fill"
    expected = render.crop_fill_visual("x", *BIG, face=saud,
                                       numbers=render.style_numbers("explainer"))  # fmt: skip
    assert (v.focus_x, v.focus_y) == (expected.focus_x, expected.focus_y)


def test_a_named_person_with_only_a_stranger_found_is_framed_on_the_rings_point(
    tmp_path: Path,
) -> None:
    beat = _still_beat(0, treatment="crop_fill", depicts="named_person")
    (v,) = _drawn(tmp_path, [beat], BIG, fits=False, faces=[OFFICER2]).values()
    assert v.treatment == "crop_fill"
    officer = render.crop_fill_visual("x", *BIG, face=OFFICER2,
                                      numbers=render.style_numbers("explainer"))  # fmt: skip
    assert v.focus_x != officer.focus_x
    assert abs(v.focus_x - 0.5) < 0.1  # the ring's point, the image's middle


def test_with_no_subject_known_the_largest_face_is_aimed_at(tmp_path: Path) -> None:
    small = FaceBox(left=820, top=500, width=100, height=100)
    beat = _still_beat(0, treatment="crop_fill", depicts="scene")
    (v,) = _drawn(tmp_path, [beat], BIG, fits=False, faces=[OFFICER2, small]).values()
    assert v.treatment == "crop_fill"
    expected = render.crop_fill_visual("x", *BIG, face=OFFICER2,
                                       numbers=render.style_numbers("explainer"))  # fmt: skip
    assert (v.focus_x, v.focus_y) == (expected.focus_x, expected.focus_y)


def test_subject_face_picks_the_face_inside_the_ring() -> None:
    near = FaceBox(left=400, top=280, width=60, height=60)
    assert render.subject_face([OFFICER, near], (0.5, 0.5), *GROUP) == near
    assert render.subject_face([OFFICER, near], None, *GROUP) == OFFICER
    assert render.subject_face([], (0.5, 0.5), *GROUP) is None
    at_point = render.subject_face([OFFICER], (0.5, 0.45), *GROUP)
    assert at_point is not None and at_point != OFFICER
    centre = (at_point.left + at_point.width / 2, at_point.top + at_point.height / 2)
    assert centre == pytest.approx((435.0, 276.3), abs=1.0)


def test_a_push_in_on_a_named_photo_aims_at_the_subjects_face(tmp_path: Path) -> None:
    saud = FaceBox(left=450, top=650, width=100, height=100)
    stranger = FaceBox(left=50, top=900, width=300, height=300)
    beat = _still_beat(0, motion="push_in", depicts="named_person",
                       event={"kind": "ring"})  # fmt: skip
    (v,) = _drawn(tmp_path, [beat], PORTRAIT, faces=[stranger, saud]).values()
    assert v.treatment == "photo"
    # the ring's point is the image middle (500, 703): saud's face is inside the ring
    assert (v.focus_x, v.focus_y) == pytest.approx((500 / 1000, 700 / 1406))


def test_a_push_in_with_no_subject_aims_at_the_largest_face(tmp_path: Path) -> None:
    small = FaceBox(left=450, top=650, width=100, height=100)
    big = FaceBox(left=100, top=100, width=300, height=300)
    (v,) = _drawn(tmp_path, [_still_beat(0, motion="push_in")], PORTRAIT,
                  faces=[small, big]).values()  # fmt: skip
    assert (v.focus_x, v.focus_y) == pytest.approx((250 / 1000, 250 / 1406))


# --- the era grade: a `timeless` pick on an era beat is graded --------------------------------


def test_a_timeless_pick_gets_the_styles_era_grade(tmp_path: Path) -> None:
    row = render.loaded_styles()["explainer"].broll.motion["era_grade"]
    (v,) = _drawn(tmp_path, [_still_beat(0)], PORTRAIT, era="timeless").values()
    assert v.grade is not None
    assert (v.grade.sepia, v.grade.saturate, v.grade.contrast) == (
        row["sepia"], row["saturate"], row["contrast"])
    (period,) = _drawn(tmp_path, [_still_beat(0)], PORTRAIT, era="period").values()
    (plain,) = _drawn(tmp_path, [_still_beat(0)], PORTRAIT).values()
    assert period.grade is None and plain.grade is None


def test_a_timeless_clip_is_graded_too(tmp_path: Path) -> None:
    beat = Beat.model_validate({"id": "b00", "start": 0.0, "end": 2.0, "mode": "pip",
                                "kind": "clip", "motion": "push_in", "query": "1950s oil",
                                "subject_kind": "concept"})  # fmt: skip
    (v,) = _drawn(tmp_path, [beat], (1080, 1920), era="timeless", kind="clip").values()
    assert v.treatment == "clip" and v.grade is not None and v.grade.sepia > 0


def test_a_detector_that_finds_one_face_answers_it_for_every_face(tmp_path: Path) -> None:
    box = FaceBox(left=1, top=2, width=30, height=30)
    assert presenter.FakeFaceDetector(box).detect_all(tmp_path / "x.png") == [box]
    assert presenter.FakeFaceDetector(box, found=0).detect_all(tmp_path / "x.png") == []


def test_the_bench_card_rings_the_subject_every_crop_aims_at() -> None:
    from shortsmith import bench

    numbers = render.style_numbers("explainer")
    card = bench.treatment_visual("card", "x", GROUP, face=OFFICER, numbers=numbers,
                                  pip_top=960)  # fmt: skip
    subject = render.subject_face([OFFICER], (card.focus_x, card.focus_y), *GROUP)
    assert (card.focus_x, card.focus_y) == (bench.RING_SUBJECT.focus_x, bench.RING_SUBJECT.focus_y)
    assert subject is not None and subject != OFFICER
