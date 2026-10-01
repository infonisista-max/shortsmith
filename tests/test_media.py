"""111a: the one media probe and the converters (`shortsmith.media`). Every fixture is
made in code: Pillow writes the stills, ffmpeg the clips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import ffmpeg, media
from shortsmith.fixture import make_clip
from shortsmith.presenter import HaarDetector


def _image(path: Path, *, fmt: str, size: tuple[int, int] = (640, 800), mode: str = "RGB") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    colour = (170, 85, 51, 128) if mode == "RGBA" else (170, 85, 51)
    Image.new(mode, size, colour).save(path, format=fmt)
    return path


def _codec(path: Path) -> str:
    streams = ffmpeg.probe(path)["streams"]
    return next(s["codec_name"] for s in streams if s.get("codec_type") == "video")


def _mpeg4_clip(path: Path) -> Path:
    ffmpeg.run([
        ffmpeg.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
        "color=c=0x3355AA:s=320x240:r=25:d=1", "-c:v", "mpeg4", str(path),
    ])  # fmt: skip
    return path


# --- probe ----------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "AVIF", "GIF", "BMP", "TIFF"])
def test_probe_calls_any_pillow_image_an_image_whatever_its_name(tmp_path: Path, fmt: str) -> None:
    assert media.probe(_image(tmp_path / "x.jpg", fmt=fmt)) == "image"


def test_probe_calls_a_clip_a_video(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "c.mp4", duration_s=1.0, width=320, height=240)
    assert media.probe(clip) == "video"


def test_probe_answers_none_for_text_empty_and_missing_files(tmp_path: Path) -> None:
    text = tmp_path / "fake.jpg"
    text.write_text("hello, I am not a photo", encoding="utf-8")
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert media.probe(text) is None
    assert media.probe(empty) is None
    assert media.probe(tmp_path / "missing.jpg") is None


# --- as_still -------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["WEBP", "AVIF", "GIF", "BMP", "TIFF"])
def test_as_still_writes_a_real_jpg(tmp_path: Path, fmt: str) -> None:
    src = _image(tmp_path / "in" / "x.jpg", fmt=fmt)
    out = media.as_still(src, tmp_path / "out" / "x.jpg")
    assert out == tmp_path / "out" / "x.jpg"
    with Image.open(out) as im:
        assert (im.format, im.size) == ("JPEG", (640, 800))


def test_as_still_keeps_alpha_as_png(tmp_path: Path) -> None:
    src = _image(tmp_path / "logo.webp", fmt="WEBP", mode="RGBA")
    out = media.as_still(src, tmp_path / "logo.jpg")
    assert out == tmp_path / "logo.png"
    with Image.open(out) as im:
        assert im.format == "PNG" and "A" in im.mode


def test_as_still_applies_the_exif_rotation(tmp_path: Path) -> None:
    src = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW on display
    Image.new("RGB", (800, 600), (10, 20, 30)).save(src, format="JPEG", exif=exif)
    with Image.open(media.as_still(src, tmp_path / "upright.jpg")) as im:
        assert im.size == (600, 800)


def test_as_still_overwrites_its_own_source_in_place(tmp_path: Path) -> None:
    src = _image(tmp_path / "x.jpg", fmt="AVIF")
    assert media.as_still(src, src) == src
    with Image.open(src) as im:
        assert im.format == "JPEG"


def test_as_still_grabs_a_frame_from_a_video(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "c.mp4", duration_s=1.5, width=320, height=240)
    out = media.as_still(clip, tmp_path / "frame.jpg")
    with Image.open(out) as im:
        assert (im.format, im.size) == ("JPEG", (320, 240))


def test_as_still_refuses_a_file_that_is_no_media(tmp_path: Path) -> None:
    text = tmp_path / "fake.jpg"
    text.write_text("nope", encoding="utf-8")
    with pytest.raises(media.MediaError):
        media.as_still(text, tmp_path / "out.jpg")


# --- as_clip --------------------------------------------------------------------


def test_as_clip_leaves_an_h264_mp4_alone(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "c.mp4", duration_s=1.0, width=320, height=240)
    assert media.as_clip(clip, tmp_path / "out.mp4") == clip
    assert not (tmp_path / "out.mp4").exists()


def test_as_clip_reencodes_another_codec_to_h264_mp4(tmp_path: Path) -> None:
    src = _mpeg4_clip(tmp_path / "old.mp4")
    out = media.as_clip(src, tmp_path / "new.webm")
    assert out == tmp_path / "new.mp4"
    assert _codec(out) == "h264"


def test_as_clip_reencodes_a_mov_container(tmp_path: Path) -> None:
    src = make_clip(tmp_path / "c.mov", duration_s=1.0, width=320, height=240)
    out = media.as_clip(src, tmp_path / "c.mp4")
    assert out.suffix == ".mp4" and _codec(out) == "h264"
    assert media.is_browser_safe(out)


def test_browser_safe_means_jpg_png_webp_or_h264_mp4(tmp_path: Path) -> None:
    assert media.is_browser_safe(_image(tmp_path / "a.jpg", fmt="JPEG"))
    assert media.is_browser_safe(_image(tmp_path / "a.png", fmt="PNG"))
    assert media.is_browser_safe(_image(tmp_path / "a.webp", fmt="WEBP"))
    assert not media.is_browser_safe(_image(tmp_path / "b.jpg", fmt="AVIF"))
    assert not media.is_browser_safe(_image(tmp_path / "a.bmp", fmt="BMP"))
    assert not media.is_browser_safe(_mpeg4_clip(tmp_path / "m.mp4"))
    h264 = make_clip(tmp_path / "h.mp4", duration_s=1.0, width=320, height=240)
    assert media.is_browser_safe(h264)


# --- normalise_refs -------------------------------------------------------------


def _job_with_refs(tmp_path: Path, files: dict[str, str]) -> Path:
    """A job dir with `input/refs/<name>` written in the Pillow format given."""
    job_dir = tmp_path / "job"
    rows: list[dict[str, object]] = []
    for n, (name, fmt) in enumerate(files.items(), start=1):
        _image(job_dir / "input" / "refs" / name, fmt=fmt)
        rows.append({
            "id": f"ref{n}", "file": f"refs/{name}", "kind": "image", "caption": "",
            "original_name": name, "width": 640, "height": 800, "size_bytes": 1,
            "rights": "owner_supplied",
        })  # fmt: skip
    (job_dir / "input" / "refs.json").write_text(json.dumps(rows), encoding="utf-8")
    return job_dir


def test_normalise_refs_fixes_a_mislabelled_ref_once(tmp_path: Path) -> None:
    job_dir = _job_with_refs(tmp_path, {"1_ok.jpg": "JPEG", "7_sri.jpg": "AVIF"})
    lines = media.normalise_refs(job_dir)
    assert len(lines) == 1 and "7_sri.jpg" in lines[0]
    rows = json.loads((job_dir / "input" / "refs.json").read_text(encoding="utf-8"))
    assert [r["file"] for r in rows] == ["refs/1_ok.jpg", "refs/7_sri.jpg"]
    fixed = job_dir / "input" / "refs" / "7_sri.jpg"
    with Image.open(fixed) as im:
        assert im.format == "JPEG"
    assert rows[1]["size_bytes"] == fixed.stat().st_size
    assert rows[1]["rights"] == "owner_supplied"
    before = (job_dir / "input" / "refs.json").read_bytes()
    assert media.normalise_refs(job_dir) == []
    assert (job_dir / "input" / "refs.json").read_bytes() == before


def test_normalise_refs_renames_a_converted_ref_and_points_refs_json_at_it(
    tmp_path: Path,
) -> None:
    job_dir = _job_with_refs(tmp_path, {"2_scan.bmp": "BMP"})
    assert len(media.normalise_refs(job_dir)) == 1
    rows = json.loads((job_dir / "input" / "refs.json").read_text(encoding="utf-8"))
    assert rows[0]["file"] == "refs/2_scan.jpg"
    assert (job_dir / "input" / "refs" / "2_scan.jpg").is_file()


def test_normalise_refs_logs_an_unreadable_ref_and_never_raises(tmp_path: Path) -> None:
    job_dir = _job_with_refs(tmp_path, {"3_bad.jpg": "JPEG"})
    (job_dir / "input" / "refs" / "3_bad.jpg").write_text("broken", encoding="utf-8")
    lines = media.normalise_refs(job_dir)
    assert len(lines) == 1 and "3_bad.jpg" in lines[0]


def test_normalise_refs_without_refs_json_does_nothing(tmp_path: Path) -> None:
    assert media.normalise_refs(tmp_path) == []


def test_a_real_webp_is_a_real_still_and_a_mislabelled_one_is_not(tmp_path: Path) -> None:
    """112b: a WebP by content under a `.webp` name is what the browser draws; only a
    mislabelled one is converted."""
    assert media.is_real_still(_image(tmp_path / "a.webp", fmt="WEBP"))
    assert not media.is_real_still(_image(tmp_path / "b.jpg", fmt="WEBP"))
    assert media.is_real_still(tmp_path / "b.jpg", suffix=".webp")
    assert not media.is_real_still(_image(tmp_path / "c.webp", fmt="AVIF"))


def test_normalise_refs_keeps_a_real_webp_byte_for_byte(tmp_path: Path) -> None:
    job_dir = _job_with_refs(tmp_path, {"4_logo.webp": "WEBP"})
    ref = job_dir / "input" / "refs" / "4_logo.webp"
    before = ref.read_bytes()
    refs_json = (job_dir / "input" / "refs.json").read_bytes()
    assert media.normalise_refs(job_dir) == []
    assert ref.read_bytes() == before
    assert (job_dir / "input" / "refs.json").read_bytes() == refs_json


# --- faces read the normalised file -----------------------------------------------


@pytest.mark.parametrize("fmt", ["WEBP", "AVIF"])
def test_the_face_detector_reads_a_converted_ref(tmp_path: Path, fmt: str) -> None:
    src = _image(tmp_path / "x.jpg", fmt=fmt)
    out = media.as_still(src, src)
    assert HaarDetector().detect_all(out) == []  # read, no face on a flat colour


def test_the_face_detector_reads_a_real_webp(tmp_path: Path) -> None:
    """112b: a WebP ref is kept as it is, so the detector must read one."""
    src = _image(tmp_path / "x.webp", fmt="WEBP")
    assert HaarDetector().detect_all(src) == []
    assert HaarDetector().detect(src) is None


def test_the_face_detector_reads_a_mislabelled_ref_through_pillow(tmp_path: Path) -> None:
    src = _image(tmp_path / "x.jpg", fmt="AVIF")
    assert HaarDetector().detect_all(src) == []
