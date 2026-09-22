"""The ASR fix pass (research §6, decision 6.1): pure functions on word lists, so word
times are final before planning.

Order, as on the two approved jobs: tail re-run and splice, head smear, overlap clamp,
then the fix map (text only, after timing, before cuts).

- Tail re-run: when the audio runs more than `TAIL_GAP_S` past the last word's end,
  re-transcribe from `floor(last_end - TAIL_WINDOW_S)` and splice at `last_end`,
  keeping the main words before it and the tail words at or after it (research,
  verbatim). A low-confidence last segment is re-run the same way, spliced at its
  start, so its words are replaced by the re-run's.
- Head smear: words heard in the opening silence (a first onset more than
  `HEAD_SMEAR_S` before the detected speech onset; Dyson's first word sat at 0.00 in
  1.72 s of silence) move to the onset. The research check was manual; the threshold
  is ours. The overlap clamp then gives them room.
- Overlap clamp: a word starting more than `OVERLAP_TOLERANCE_S` before the previous
  end starts at that end; a word with `end <= start` gets `MIN_WORD_S` (verbatim).
- Fix map: exact whole-token replacement from `fixmaps/<language>.json` in the
  documented `{"map": {wrong: right}, "only_before": [{word, next, else}]}` format;
  an `only_before` rule reverts `word` to `else` unless the next word is `next`.

Segment flags use Whisper's own thresholds: `avg_logprob` below -1.0 is low
confidence, `no_speech_prob` above 0.6 is no speech.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from shortsmith.contracts import Segment, Transcript, Word

TAIL_GAP_S = 1.5
TAIL_WINDOW_S = 3.0
HEAD_SMEAR_S = 0.3
OVERLAP_TOLERANCE_S = 0.05
MIN_WORD_S = 0.12
LOW_LOGPROB = -1.0  # Whisper's logprob_threshold
NO_SPEECH_PROB = 0.6  # Whisper's no_speech_threshold

FIXMAPS_DIR = Path(__file__).parent / "fixmaps"
# Whisper replies with language names; the fix maps are keyed by ISO 639-1 code.
LANGUAGE_CODES: dict[str, str] = {"hindi": "hi", "english": "en"}


def _r(t: float) -> float:
    return round(t, 3)


def low_confidence(avg_logprob: float) -> bool:
    return avg_logprob < LOW_LOGPROB


def no_speech(no_speech_prob: float) -> bool:
    return no_speech_prob > NO_SPEECH_PROB


def language_code(language: str) -> str:
    """`hi`, `HI`, `hindi` and `Hindi` are all `hi`; an unknown name is lowercased."""
    lowered = language.strip().lower()
    return LANGUAGE_CODES.get(lowered, lowered)


def assign_segments(words: Sequence[Word], segments: Sequence[Segment]) -> list[Word]:
    """Each word takes the last segment starting at or before its midpoint (0 when
    none does), so a word in a gap between segments joins the one before it."""
    out: list[Word] = []
    for word in words:
        mid = (word.start + word.end) / 2
        index = 0
        for i, segment in enumerate(segments):
            if segment.start <= mid:
                index = i
        out.append(word.model_copy(update={"segment": index}))
    return out


# --- tail re-run ------------------------------------------------------------------------


@dataclass(frozen=True)
class TailCut:
    """Re-transcribe the audio from `start_s`; splice the result at `splice_at_s`."""

    start_s: float
    splice_at_s: float


def tail_cut(transcript: Transcript) -> TailCut | None:
    """The re-run the research §6 tail check asks for, or None."""
    if not transcript.words:
        return None
    last_end = transcript.words[-1].end
    if _r(transcript.duration_s - last_end) > TAIL_GAP_S:
        return TailCut(start_s=float(max(0, math.floor(last_end - TAIL_WINDOW_S))),
                       splice_at_s=last_end)  # fmt: skip
    if transcript.segments and transcript.segments[-1].low_confidence:
        splice_at = transcript.segments[-1].start
        start = max(0, math.floor(min(splice_at, last_end - TAIL_WINDOW_S)))
        return TailCut(start_s=float(start), splice_at_s=splice_at)
    return None


def splice_tail(main: Transcript, tail: Transcript, cut: TailCut) -> Transcript:
    """Main words (and segments) starting before the splice, tail words starting at or
    after it and tail segments ending after it, the tail's times offset by the cut."""
    offset = cut.start_s

    def shifted_word(w: Word) -> Word:
        return w.model_copy(update={"start": _r(w.start + offset), "end": _r(w.end + offset)})

    def shifted_segment(s: Segment) -> Segment:
        return s.model_copy(update={"start": _r(s.start + offset), "end": _r(s.end + offset)})

    words = [w for w in main.words if w.start < cut.splice_at_s]
    words += [w for w in map(shifted_word, tail.words) if w.start >= cut.splice_at_s]
    segments = [s for s in main.segments if s.start < cut.splice_at_s]
    segments += [s for s in map(shifted_segment, tail.segments) if s.end > cut.splice_at_s]
    return main.model_copy(
        update={"words": assign_segments(words, segments), "segments": segments}
    )


# --- head smear and overlaps --------------------------------------------------------------


def head_smear(words: Sequence[Word], onset_s: float) -> list[Word]:
    """Words heard in the opening silence move to the speech onset."""
    if not words or _r(onset_s - words[0].start) <= HEAD_SMEAR_S:
        return list(words)
    return [
        w.model_copy(update={"start": onset_s, "end": max(w.end, onset_s)})
        if w.start < onset_s
        else w
        for w in words
    ]


def clamp_overlaps(words: Sequence[Word]) -> list[Word]:
    out: list[Word] = []
    for word in words:
        start, end = word.start, word.end
        if out and start < out[-1].end - OVERLAP_TOLERANCE_S:
            start = out[-1].end
        if end <= start:
            end = _r(start + MIN_WORD_S)
        out.append(word.model_copy(update={"start": start, "end": end}))
    return out


# --- fix map ------------------------------------------------------------------------------


class Lookahead(BaseModel):
    """`word` stays only before `next`; anywhere else it becomes `else`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    word: str
    next: str
    else_: str = Field(alias="else")


class FixMap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    map: dict[str, str] = {}
    only_before: list[Lookahead] = []


@cache
def load_fix_map(language: str) -> FixMap:
    """The shipped map for the language (code or Whisper's name); empty when none."""
    path = FIXMAPS_DIR / f"{language_code(language)}.json"
    if not path.is_file():
        return FixMap()
    return FixMap.model_validate(json.loads(path.read_text(encoding="utf-8")))


def apply_fix_map(words: Sequence[Word], fixmap: FixMap) -> list[Word]:
    texts = [fixmap.map.get(w.text, w.text) for w in words]
    for i, text in enumerate(texts):
        for rule in fixmap.only_before:
            following = texts[i + 1] if i + 1 < len(texts) else None
            if text == rule.word and following != rule.next:
                texts[i] = rule.else_
    return [
        w if w.text == text else w.model_copy(update={"text": text})
        for w, text in zip(words, texts, strict=True)
    ]
