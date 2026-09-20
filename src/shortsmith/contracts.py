"""Shared Pydantic models (PRD "Global contracts").

Only the Transcript family lives here yet; PlanRequest, PicturePlan, SoundStory and
CaptionPage arrive with ticket 003. Planner-facing models use `extra="forbid"` so the
JSON schema generated from them is the single source of truth (decisions 2.3, 8.1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Word(StrictModel):
    """One spoken word with final times in seconds (decision 6.1: never touched by the planner)."""

    text: str
    start: float
    end: float
    segment: int

    @model_validator(mode="after")
    def _end_after_start(self) -> Word:
        if self.end < self.start:
            raise ValueError(
                f"word {self.text!r} ends ({self.end}) before it starts ({self.start})"
            )
        return self


class Segment(StrictModel):
    """ASR segment with its confidence flags (research §6 fix pass reads these)."""

    start: float
    end: float
    avg_logprob: float
    low_confidence: bool = False
    no_speech: bool = False

    @model_validator(mode="after")
    def _end_after_start(self) -> Segment:
        if self.end < self.start:
            raise ValueError(f"segment ends ({self.end}) before it starts ({self.start})")
        return self


class Transcript(StrictModel):
    language: str = "und"
    duration_s: float
    segments: list[Segment]
    words: list[Word]


ReferenceKind = Literal["image", "clip"]


class ReferenceRecord(StrictModel):
    """One row of `input/refs.json` (decision 2.2): the first rows of the rights log.

    `file` is relative to the job's `input/` directory. Reference clips are stills in
    v1 (1.3); their `kind` is `clip` here and `clip_frame` once a frame is extracted.
    """

    id: str
    file: str
    kind: ReferenceKind
    caption: str
    original_name: str
    width: int
    height: int
    size_bytes: int
    rights: Literal["owner_supplied"] = "owner_supplied"
