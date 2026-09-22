"""ffmpeg speech helpers for the transcriber (research §6): the 16 kHz mono 64 kbps MP3
the ASR is fed, optionally from an offset (the tail re-run), its duration, and the
speech onset the head-smear check compares the first word against."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from shortsmith import ffmpeg


def _tone_after(path: Path, *, silence_s: float, tone_s: float = 1.0) -> Path:
    delay_ms = int(silence_s * 1000)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={tone_s},adelay={delay_ms}",
            "-ar", "48000", "-ac", "2", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def test_extract_speech_writes_16_khz_mono_mp3_at_64_kbps(
    tmp_path: Path, fixture_clip: Path
) -> None:
    out = ffmpeg.extract_speech(fixture_clip, tmp_path / "audio.mp3")
    (stream,) = ffmpeg.probe(out)["streams"]
    assert (stream["codec_name"], stream["sample_rate"], stream["channels"]) == ("mp3", "16000", 1)
    assert ffmpeg.duration_s(out) == pytest.approx(6.0, abs=0.1)


def test_extract_speech_from_an_offset_keeps_the_rest(tmp_path: Path, fixture_clip: Path) -> None:
    out = ffmpeg.extract_speech(fixture_clip, tmp_path / "tail.mp3", start_s=4.0)
    assert ffmpeg.duration_s(out) == pytest.approx(2.0, abs=0.1)


def test_speech_onset_is_the_end_of_the_opening_silence(tmp_path: Path) -> None:
    clip = _tone_after(tmp_path / "late.wav", silence_s=1.72)
    assert ffmpeg.speech_onset_s(clip) == pytest.approx(1.72, abs=0.05)


def test_speech_onset_is_zero_when_speech_starts_at_once(tmp_path: Path) -> None:
    clip = _tone_after(tmp_path / "early.wav", silence_s=0.0)
    assert ffmpeg.speech_onset_s(clip) == 0.0


def test_speech_onset_is_zero_for_the_fixture_clip(fixture_clip: Path) -> None:
    """The fixture's first burst is at 0.2 s: shorter than the minimum silence."""
    assert ffmpeg.speech_onset_s(fixture_clip) == 0.0
