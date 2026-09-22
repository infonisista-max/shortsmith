"""ingest: server-side validation per decision 2.1 and the input/ layout per 2.2.

The pure checks are boundary-tested on plain data at the exact values in 2.1; the
ffmpeg-backed probes and `accept` are tested on synthetic clips and images that the
session generates (12.1). A rejection is one plain sentence and creates no job."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shortsmith import ingest
from shortsmith.fixture import make_clip, make_image
from shortsmith.ingest import Limits, ReferenceInfo, ReferenceUpload, VideoInfo, VideoUpload
from shortsmith.styles import Resolution

LIMITS = Limits()
EXPLAINER = Resolution(name="explainer", note="")


def _video(**overrides: object) -> VideoInfo:
    base: dict[str, object] = {
        "duration_s": 60.0,
        "width": 1080,
        "height": 1920,
        "video_streams": 1,
        "audio_streams": 1,
        "mean_volume_db": -20.0,
        "size_bytes": 10_000_000,
        "extension": ".mp4",
    }
    base.update(overrides)
    return VideoInfo(**base)  # type: ignore[arg-type]


def test_limits_default_to_2_1() -> None:
    assert Limits(
        min_duration_s=20.0,
        max_duration_s=480.0,
        min_mean_volume_db=-50.0,
        max_upscale=1.5,
        brief_min_chars=40,
        brief_max_chars=1500,
        max_references=8,
        max_reference_bytes=20 * 1024 * 1024,
        min_image_short_side=600,
        max_upload_bytes=500 * 1024 * 1024,
    ) == LIMITS


@pytest.mark.parametrize(
    ("width", "height", "factor"),
    [
        (1080, 1920, 1.0),
        (2160, 3840, 0.5),
        (1920, 1080, 1920 / 1080),  # landscape 1080p: crop is 607x1080
        (3840, 2160, 2160 / 2160 * (1920 / 2160)),  # 4K landscape: 0.889
        (1080, 1080, 1920 / 1080),  # square
        (1080, 1290, 1920 / 1290),
    ],
)
def test_upscale_factor_is_1920_over_the_9_16_centre_crop_height(
    width: int, height: int, factor: float
) -> None:
    assert ingest.upscale_factor(width, height) == pytest.approx(factor)


class TestCheckVideo:
    def test_good_video_passes(self) -> None:
        assert ingest.check_video(_video(), LIMITS) is None

    @pytest.mark.parametrize("duration", [20.0, 480.0])
    def test_duration_bounds_inclusive(self, duration: float) -> None:
        assert ingest.check_video(_video(duration_s=duration), LIMITS) is None

    @pytest.mark.parametrize("duration", [19.9, 480.1])
    def test_duration_outside_rejects(self, duration: float) -> None:
        msg = ingest.check_video(_video(duration_s=duration), LIMITS)
        assert msg == "The recording must be between 20 seconds and 8 minutes long."

    def test_minus_49_dbfs_passes_minus_51_rejects(self) -> None:
        assert ingest.check_video(_video(mean_volume_db=-49.0), LIMITS) is None
        assert ingest.check_video(_video(mean_volume_db=-50.0), LIMITS) is None
        msg = ingest.check_video(_video(mean_volume_db=-51.0), LIMITS)
        assert msg == "No speech found in the recording."

    def test_unmeasurable_volume_rejects(self) -> None:
        assert ingest.check_video(_video(mean_volume_db=None), LIMITS) is not None

    def test_upscale_1_49_passes_1_51_rejects(self) -> None:
        assert ingest.check_video(_video(width=1080, height=round(1920 / 1.49)), LIMITS) is None
        msg = ingest.check_video(_video(width=1080, height=round(1920 / 1.51)), LIMITS)
        assert msg == (
            "Filling 9:16 from this recording would need more than a 1.5x upscale, "
            "so record vertical or in 4K."
        )

    def test_landscape_1080p_rejects_but_4k_landscape_passes(self) -> None:
        assert ingest.check_video(_video(width=1920, height=1080), LIMITS) is not None
        assert ingest.check_video(_video(width=3840, height=2160), LIMITS) is None

    @pytest.mark.parametrize(
        ("video_streams", "audio_streams"), [(0, 1), (2, 1), (1, 0), (1, 2)]
    )
    def test_exactly_one_video_and_one_audio_stream(
        self, video_streams: int, audio_streams: int
    ) -> None:
        msg = ingest.check_video(
            _video(video_streams=video_streams, audio_streams=audio_streams), LIMITS
        )
        assert msg == "The recording needs exactly one video stream and one audio track."

    def test_extension_must_be_mp4_or_mov(self) -> None:
        assert ingest.check_video(_video(extension=".mov"), LIMITS) is None
        assert ingest.check_video(_video(extension=".MP4"), LIMITS) is None
        msg = ingest.check_video(_video(extension=".avi"), LIMITS)
        assert msg == "The recording must be an mp4 or mov file."

    def test_upload_size_cap(self) -> None:
        cap = LIMITS.max_upload_bytes
        assert ingest.check_video(_video(size_bytes=cap), LIMITS) is None
        msg = ingest.check_video(_video(size_bytes=cap + 1), LIMITS)
        assert msg == "The recording must be 500 MB or smaller."

    def test_first_failing_rule_wins_in_2_1_order(self) -> None:
        msg = ingest.check_video(_video(audio_streams=0, duration_s=1.0), LIMITS)
        assert msg == "The recording needs exactly one video stream and one audio track."


def test_landscape_gets_the_pip_warning_and_portrait_does_not() -> None:
    assert ingest.video_warnings(_video(width=3840, height=2160)) == [
        "Vertical works best for PIP; this recording is landscape, so it will be centre-cropped."
    ]
    assert ingest.video_warnings(_video()) == []


class TestCheckBrief:
    def test_39_chars_rejects_40_passes(self) -> None:
        assert ingest.check_brief("x" * 39, LIMITS) == (
            "The brief must be between 40 and 1500 characters."
        )
        assert ingest.check_brief("x" * 40, LIMITS) is None

    def test_1500_passes_1501_rejects(self) -> None:
        assert ingest.check_brief("x" * 1500, LIMITS) is None
        assert ingest.check_brief("x" * 1501, LIMITS) is not None

    def test_length_counts_stripped_text(self) -> None:
        assert ingest.check_brief("   " + "x" * 39 + "\n", LIMITS) is not None


def _ref(**overrides: object) -> ReferenceInfo:
    base: dict[str, object] = {
        "original_name": "photo.jpg",
        "caption": "the product",
        "size_bytes": 500_000,
        "width": 1200,
        "height": 800,
        "kind": "image",
    }
    base.update(overrides)
    return ReferenceInfo(**base)  # type: ignore[arg-type]


class TestCheckReferences:
    def test_eight_pass_nine_reject(self) -> None:
        assert ingest.check_references([_ref()] * 8, LIMITS) is None
        assert ingest.check_references([_ref()] * 9, LIMITS) == (
            "At most 8 reference files are allowed."
        )

    def test_short_side_599_rejects_600_passes(self) -> None:
        assert ingest.check_references([_ref(width=600, height=2000)], LIMITS) is None
        assert ingest.check_references([_ref(width=2000, height=600)], LIMITS) is None
        assert ingest.check_references([_ref(width=599, height=2000)], LIMITS) == (
            "Reference photo.jpg must be at least 600 px on its short side."
        )

    def test_size_cap(self) -> None:
        cap = LIMITS.max_reference_bytes
        assert ingest.check_references([_ref(size_bytes=cap)], LIMITS) is None
        assert ingest.check_references([_ref(size_bytes=cap + 1)], LIMITS) == (
            "Reference photo.jpg must be 20 MB or smaller."
        )

    def test_clip_references_skip_the_short_side_rule(self) -> None:
        clip = _ref(original_name="c.mp4", kind="clip", width=320, height=240)
        assert ingest.check_references([clip], LIMITS) is None

    def test_unknown_kind_rejects(self) -> None:
        bad = _ref(original_name="notes.pdf", kind="unknown")
        assert ingest.check_references([bad], LIMITS) == (
            "Reference notes.pdf must be a jpg, png, webp, mp4 or mov file."
        )


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("a.jpg", "image"),
        ("a.JPEG", "image"),
        ("a.png", "image"),
        ("a.webp", "image"),
        ("a.mp4", "clip"),
        ("a.mov", "clip"),
        ("a.gif", "unknown"),
        ("a", "unknown"),
    ],
)
def test_reference_kind_from_name(name: str, kind: str) -> None:
    assert ingest.reference_kind(name) == kind


def test_slug_keeps_letters_digits_and_dashes() -> None:
    assert ingest.slug("My Photo (final) v2.JPG") == "my-photo-final-v2"
    assert ingest.slug("...") == "ref"


# --- ffmpeg-backed ------------------------------------------------------------


def test_probe_video_reads_the_fixture(fixture_clip: Path) -> None:
    info = ingest.probe_video(fixture_clip)
    assert (info.video_streams, info.audio_streams) == (1, 1)
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration_s == pytest.approx(6.0, abs=0.1)
    assert info.mean_volume_db is not None and -30 < info.mean_volume_db < -5
    assert info.size_bytes == fixture_clip.stat().st_size
    assert info.extension == ".mp4"


def test_probe_video_on_a_silent_clip_reports_a_very_low_volume(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "silent.mov", duration_s=2.0, amplitude=0.0)
    info = ingest.probe_video(clip)
    assert info.mean_volume_db is None or info.mean_volume_db < -80


def test_probe_reference_reads_image_dimensions(tmp_path: Path) -> None:
    img = make_image(tmp_path / "wide.png", width=900, height=650)
    info = ingest.probe_reference(img, original_name="Wide Shot.png", caption="c")
    assert (info.width, info.height, info.kind) == (900, 650, "image")
    assert info.size_bytes == img.stat().st_size
    assert info.original_name == "Wide Shot.png"


def test_accept_writes_the_2_2_input_layout(tmp_path: Path, fixture_clip: Path) -> None:
    ref_a = make_image(tmp_path / "up" / "a.png", width=700, height=900)
    ref_b = make_clip(tmp_path / "up" / "b.mov", duration_s=1.0, width=640, height=360)
    job = ingest.accept(
        tmp_path / "data",
        video=VideoUpload(path=fixture_clip, original_name="My Take 1.MP4"),
        brief="This is a brief that is comfortably longer than forty characters.",
        style=Resolution(
            name="explainer",
            note="hitech please",
            notice="hitech not available yet, using explainer",
        ),
        references=[
            ReferenceUpload(path=ref_a, original_name="Logo Final.png", caption="our logo"),
            ReferenceUpload(path=ref_b, original_name="clip.mov", caption=""),
        ],
        limits=Limits(min_duration_s=1.0),
    )
    assert job.status == "uploaded"
    assert (job.input_dir / "raw.mp4").read_bytes() == fixture_clip.read_bytes()
    assert (job.input_dir / "brief.md").read_text(encoding="utf-8") == (
        "This is a brief that is comfortably longer than forty characters."
    )
    assert (job.input_dir / "refs" / "1_logo-final.png").is_file()
    assert (job.input_dir / "refs" / "2_clip.mov").is_file()
    refs = json.loads((job.input_dir / "refs.json").read_text(encoding="utf-8"))
    assert refs == [
        {
            "id": "ref1",
            "file": "refs/1_logo-final.png",
            "kind": "image",
            "caption": "our logo",
            "original_name": "Logo Final.png",
            "width": 700,
            "height": 900,
            "size_bytes": ref_a.stat().st_size,
            "rights": "owner_supplied",
        },
        {
            "id": "ref2",
            "file": "refs/2_clip.mov",
            "kind": "clip",
            "caption": "",
            "original_name": "clip.mov",
            "width": 640,
            "height": 360,
            "size_bytes": ref_b.stat().st_size,
            "rights": "owner_supplied",
        },
    ]
    assert job.record.style == "explainer"
    assert job.record.style_note == "hitech please"
    assert job.record.style_notice == "hitech not available yet, using explainer"
    assert job.record.input is not None
    assert job.record.input.original_name == "My Take 1.MP4"
    assert job.record.input.references == 2
    assert job.record.input.duration_s == pytest.approx(6.0, abs=0.1)
    assert job.record.warnings == []


def test_accept_stores_a_mov_as_raw_mov(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "in.mov", duration_s=1.0)
    job = ingest.accept(
        tmp_path / "data",
        video=VideoUpload(path=clip, original_name="in.mov"),
        brief="x" * 40,
        style=EXPLAINER,
        references=[],
        limits=Limits(min_duration_s=1.0),
    )
    assert (job.input_dir / "raw.mov").is_file()
    assert job.record.input is not None and job.record.input.file == "raw.mov"


def test_accept_rejects_without_creating_a_job(tmp_path: Path, fixture_clip: Path) -> None:
    with pytest.raises(ingest.Rejected) as excinfo:
        ingest.accept(
            tmp_path / "data",
            video=VideoUpload(path=fixture_clip, original_name="f.mp4"),
            brief="x" * 40,
            style=EXPLAINER,
            references=[],
        )
    assert str(excinfo.value) == "The recording must be between 20 seconds and 8 minutes long."
    assert not (tmp_path / "data").exists()


def test_accept_rejects_a_short_reference_image(tmp_path: Path, fixture_clip: Path) -> None:
    small = make_image(tmp_path / "small.png", width=599, height=1000)
    with pytest.raises(ingest.Rejected, match="at least 600 px"):
        ingest.accept(
            tmp_path / "data",
            video=VideoUpload(path=fixture_clip, original_name="f.mp4"),
            brief="x" * 40,
            style=EXPLAINER,
            references=[ReferenceUpload(path=small, original_name="tiny.png", caption="")],
            limits=Limits(min_duration_s=1.0),
        )
    assert not (tmp_path / "data").exists()
