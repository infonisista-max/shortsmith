"""transcriber: interface plus co-located FakeTranscriber returning twelve words aligned
to the fixture's six bursts, deterministic (decision 12.1)."""

from __future__ import annotations

from pathlib import Path

from shortsmith import fixture
from shortsmith.transcriber import FakeTranscriber, Transcriber


def test_fake_is_a_transcriber() -> None:
    assert isinstance(FakeTranscriber(), Transcriber)


def test_twelve_words_two_per_burst_inside_the_burst(fixture_clip: Path) -> None:
    t = FakeTranscriber().transcribe(fixture_clip)
    assert len(t.words) == 12
    assert len(t.segments) == 6
    assert t.duration_s == fixture.DURATION_S
    for i, burst_start in enumerate(fixture.BURST_TIMES):
        burst_end = burst_start + fixture.BURST_LEN_S
        pair = t.words[2 * i : 2 * i + 2]
        assert pair[0].start == burst_start
        for w in pair:
            assert burst_start <= w.start < w.end <= burst_end + 1e-9, w
            assert w.segment == i
        seg = t.segments[i]
        assert (seg.start, seg.end) == (burst_start, burst_end)


def test_words_are_monotonic_and_non_overlapping(fixture_clip: Path) -> None:
    words = FakeTranscriber().transcribe(fixture_clip).words
    for a, b in zip(words, words[1:], strict=False):
        assert a.end <= b.start, (a, b)
    assert all(w.text.strip() == w.text and w.text for w in words)


def test_fake_is_deterministic(fixture_clip: Path, tmp_path: Path) -> None:
    fake = FakeTranscriber()
    first = fake.transcribe(fixture_clip)
    second = FakeTranscriber().transcribe(fixture_clip)
    assert first == second
    assert first == fake.transcribe(tmp_path / "missing.mp4")  # never reads the audio
