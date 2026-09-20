"""Global contracts: Transcript with words and per-segment logprob flags, extra="forbid"."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shortsmith.contracts import Segment, Transcript, Word


def _transcript() -> Transcript:
    return Transcript(
        language="en",
        duration_s=6.0,
        segments=[Segment(start=0.2, end=0.5, avg_logprob=-0.1, low_confidence=False)],
        words=[Word(text="hello", start=0.2, end=0.35, segment=0)],
    )


def test_transcript_round_trips_through_json() -> None:
    t = _transcript()
    assert Transcript.model_validate_json(t.model_dump_json()) == t


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        Word.model_validate({"text": "x", "start": 0.0, "end": 0.1, "segment": 0, "score": 1})
    with pytest.raises(ValidationError):
        Transcript.model_validate({**_transcript().model_dump(), "engine": "whisper"})


def test_word_end_must_not_precede_start() -> None:
    with pytest.raises(ValidationError):
        Word(text="x", start=1.0, end=0.9, segment=0)


def test_segment_flags_default_off() -> None:
    seg = Segment(start=0.0, end=1.0, avg_logprob=-0.2)
    assert (seg.low_confidence, seg.no_speech) == (False, False)
