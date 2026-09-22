"""The fake transcriber (decision 12.1): the test and smoke default, so tests never
call a paid API."""

from __future__ import annotations

from pathlib import Path

from shortsmith import fixture
from shortsmith.contracts import Segment, Transcript, Word
from shortsmith.transcriber.base import Transcriber


class FakeTranscriber(Transcriber):
    """Twelve words, two per fixture tone burst, each pair filling its 0.3 s burst.

    Never reads the file: the output is a function of the fixture constants alone, so
    it is deterministic and works on any path.
    """

    WORDS: tuple[str, ...] = (
        "hello", "there",
        "this", "is",
        "a", "short",
        "about", "nothing",
        "made", "by",
        "ffmpeg", "alone",
    )  # fmt: skip
    LANGUAGE = "en"
    FIRST_WORD_LEN_S = 0.14
    GAP_S = 0.02

    def transcribe(self, audio: Path) -> Transcript:
        words: list[Word] = []
        segments: list[Segment] = []
        for i, burst_start in enumerate(fixture.BURST_TIMES):
            burst_end = round(burst_start + fixture.BURST_LEN_S, 3)
            split = round(burst_start + self.FIRST_WORD_LEN_S, 3)
            first, second = self.WORDS[2 * i], self.WORDS[2 * i + 1]
            words.append(Word(text=first, start=burst_start, end=split, segment=i))
            words.append(
                Word(text=second, start=round(split + self.GAP_S, 3), end=burst_end, segment=i)
            )
            segments.append(Segment(start=burst_start, end=burst_end, avg_logprob=-0.05))
        return Transcript(
            language=self.LANGUAGE,
            duration_s=fixture.DURATION_S,
            segments=segments,
            words=words,
        )
