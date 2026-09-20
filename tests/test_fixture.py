"""Decision 12.1: 6 s, 1080x1920, 30 fps, moving gradient, face ellipse in the top third,
six tone bursts at known times, under 1 MB, never committed."""

from __future__ import annotations

from pathlib import Path

from shortsmith import fixture
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
