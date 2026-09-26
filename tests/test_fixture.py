"""Decision 12.1: 6 s, 1080x1920, 30 fps, moving gradient, face ellipse in the top third,
six tone bursts at known times, under 1 MB, never committed."""

from __future__ import annotations

from pathlib import Path

from shortsmith import fixture, render, styles
from shortsmith.ffmpeg import frame_rgb, probe

REPO = Path(__file__).resolve().parents[1]


def test_fixture_geometry_and_duration(fixture_clip: Path) -> None:
    info = probe(fixture_clip)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["r_frame_rate"] == "30/1"
    assert int(video["nb_frames"]) == 180
    assert len(audio) == 1
    assert abs(float(info["format"]["duration"]) - 6.0) < 0.05


def test_fixture_is_small(fixture_clip: Path) -> None:
    assert fixture_clip.stat().st_size < 1_000_000


def test_face_ellipse_is_in_the_top_third(fixture_clip: Path) -> None:
    cx, cy = fixture.FACE_CENTER
    assert cy < 1920 / 3
    width, _height, pixels = frame_rgb(fixture_clip, at_s=1.0)

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * width + x) * 3
        return pixels[i], pixels[i + 1], pixels[i + 2]

    def close(a: tuple[int, int, int], b: tuple[int, int, int], tol: int) -> bool:
        return all(abs(p - q) <= tol for p, q in zip(a, b, strict=True))

    assert close(px(cx, cy), fixture.FACE_COLOR, tol=24), px(cx, cy)
    # Eyes are dark; nothing skin-coloured sits in the middle or bottom third.
    ex, ey = fixture.EYE_CENTERS[0]
    assert sum(px(ex, ey)) < 200, px(ex, ey)
    for y in (960, 1500, 1850):
        assert not close(px(cx, y), fixture.FACE_COLOR, tol=24), (y, px(cx, y))


def test_no_video_committed_under_tests() -> None:
    media = [p for p in (REPO / "tests").rglob("*") if p.suffix.lower() in {".mp4", ".mov"}]
    assert media == []
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.mp4" in ignored


def test_burst_times_are_the_documented_ones() -> None:
    assert fixture.BURST_TIMES == (0.2, 1.2, 2.2, 3.2, 4.2, 5.2)
    assert fixture.BURST_LEN_S == 0.3
    assert fixture.DURATION_S == 6.0


def test_smoke_specs_scale_the_named_style_and_leave_the_others() -> None:
    """048: the fixture-shaped copy can be made of any loaded style, so the `hitech`
    draft is judged by its own numbers scaled to the clip; the default stays the
    default when no name is given, and the untouched styles are the shipped files'."""
    specs = styles.load_all(render.registry())
    by_default = fixture.smoke_specs(specs)
    assert by_default["explainer"].beats.min_s == fixture.SMOKE_BEATS["min_s"]
    assert by_default["hitech"] == specs["hitech"]
    scaled = fixture.smoke_specs(specs, "hitech")
    assert scaled["hitech"].beats.min_s == fixture.SMOKE_BEATS["min_s"]
    assert scaled["hitech"].sound.cues_max_per_60s == fixture.SMOKE_SOUND["cues_max_per_60s"]
    assert scaled["hitech"].broll.unique_assets_max_per_60s == (
        fixture.SMOKE_BROLL["unique_assets_max_per_60s"]
    )
    # Everything the scaling does not name is the draft's own: palette, typography, PIP.
    assert scaled["hitech"].palette == specs["hitech"].palette
    assert scaled["hitech"].captions == specs["hitech"].captions
    assert scaled["hitech"].pip == specs["hitech"].pip
    assert scaled["hitech"].status == "draft"
    assert scaled["explainer"] == specs["explainer"]
