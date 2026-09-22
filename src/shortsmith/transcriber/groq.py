"""The `groq` transcriber: one direct Groq Whisper call per audio file (12.1, 13.1).

The job's audio goes to `work/asr/audio.mp3` as 16 kHz mono MP3 at 64 kbps (research
§6: how both approved jobs fed the same engine) and is sent to the audio
transcription endpoint through the groq SDK: `verbose_json`, word and segment
timestamps, temperature 0, the language forced when `TRANSCRIBER_LANGUAGE` names one.
The reply is kept as `work/asr/main.json` and mapped to a Transcript with the
per-segment confidence flags. When the tail check fires the tail is cut to
`work/asr/tail.mp3`, sent the same way (`tail.json`) and spliced; then the head-smear
check (against the speech onset ffmpeg detects), the overlap clamp and the language's
fix map run (`fixes`). Every fix that changed something is a `job.log` line.

Each call is a ledger row in audio minutes (the sent file's duration), checked
against the hard cap before it is made and recorded once it answered: a refused call
is not billed. An HTTP error, an unreadable reply or a missing key raises
`TranscriberError` with the API's words, never the key. The ledger is passed as a
callable because the app loads it in its lifespan, after the transcriber is built.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Self

import groq
import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from shortsmith import ffmpeg, jobs
from shortsmith.contracts import Segment, Transcript, Word
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.transcriber import fixes
from shortsmith.transcriber.base import Transcriber, TranscriberError

PROVIDER = "groq"
STEP = "transcribing"
DEFAULT_MODEL = "whisper-large-v3"
TIMEOUT_S = 120.0
MAX_RETRIES = 2


class GroqWord(BaseModel):
    word: str
    start: float
    end: float


class GroqSegment(BaseModel):
    start: float
    end: float
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


class GroqReply(BaseModel):
    """The `verbose_json` fields the transcript needs; everything else is ignored."""

    language: str = ""
    segments: list[GroqSegment]
    words: list[GroqWord]


def to_transcript(reply: GroqReply, *, language: str | None, duration_s: float) -> Transcript:
    """Words stripped of Whisper's leading spaces, never ending before they start, each
    in the segment its midpoint falls in; segments carry the confidence flags."""
    segments = [
        Segment(
            start=round(s.start, 3),
            end=round(max(s.end, s.start), 3),
            avg_logprob=s.avg_logprob,
            low_confidence=fixes.low_confidence(s.avg_logprob),
            no_speech=fixes.no_speech(s.no_speech_prob),
        )
        for s in reply.segments
    ]
    words = [
        Word(text=w.word.strip(), start=round(w.start, 3), end=round(max(w.end, w.start), 3),
             segment=0)
        for w in reply.words
        if w.word.strip()
    ]  # fmt: skip
    code = fixes.language_code(language or reply.language) or "und"
    return Transcript(
        language=code,
        duration_s=round(duration_s, 3),
        segments=segments,
        words=fixes.assign_segments(words, segments),
    )


class GroqTranscriber(Transcriber):
    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        api_key: SecretStr | None,
        model: str = DEFAULT_MODEL,
        language: str | None = "hi",
        http_client: httpx.Client | None = None,
        max_retries: int = MAX_RETRIES,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self._ledger = ledger
        self._api_key = api_key
        self.model = model
        self.language = language
        self._http_client = http_client
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._job: Job | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        return bound

    def transcribe(self, audio: Path) -> Transcript:
        job = self._job
        if job is None:
            raise TranscriberError("GroqTranscriber has no job: bind(job) before calling")
        if self._api_key is None:
            raise TranscriberError("TRANSCRIBER=groq needs GROQ_API_KEY in .env")
        client = groq.Groq(
            api_key=self._api_key.get_secret_value(),
            http_client=self._http_client,
            max_retries=self._max_retries,
            timeout=self._timeout_s,
        )
        folder = job.work_dir / "asr"
        folder.mkdir(parents=True, exist_ok=True)

        main_audio = ffmpeg.extract_speech(audio, folder / "audio.mp3")
        duration = ffmpeg.duration_s(main_audio)
        transcript = self._transcript(client, job, main_audio, "main", duration)

        cut = fixes.tail_cut(transcript)
        if cut is not None:
            tail_audio = ffmpeg.extract_speech(audio, folder / "tail.mp3", start_s=cut.start_s)
            tail = self._transcript(
                client, job, tail_audio, "tail", ffmpeg.duration_s(tail_audio)
            )
            before = len(transcript.words)
            transcript = fixes.splice_tail(transcript, tail, cut)
            jobs.note(
                job,
                f"asr: tail re-run from {cut.start_s:.1f} s spliced at {cut.splice_at_s:.2f} s "
                f"({before} -> {len(transcript.words)} words)",
            )
        return self._fixed(job, transcript, ffmpeg.speech_onset_s(main_audio))

    def _fixed(self, job: Job, transcript: Transcript, onset_s: float) -> Transcript:
        words = transcript.words
        smeared = fixes.head_smear(words, onset_s)
        if smeared != words:
            jobs.note(job, f"asr: head smear moved the opening words to {onset_s:.2f} s")
        clamped = fixes.clamp_overlaps(smeared)
        _note_changes(job, "overlap clamp moved", smeared, clamped)
        mapped = fixes.apply_fix_map(clamped, fixes.load_fix_map(transcript.language))
        _note_changes(job, "fix map changed", clamped, mapped)
        return transcript.model_copy(update={"words": mapped})

    def _transcript(
        self, client: groq.Groq, job: Job, audio: Path, name: str, duration_s: float
    ) -> Transcript:
        minutes = round(duration_s / 60, 4)
        book = self._ledger()
        book.check_before_call(job, STEP, book.estimate(PROVIDER, {"audio_minutes": minutes}))
        try:
            raw = client.audio.transcriptions.with_raw_response.create(
                file=(audio.name, audio.read_bytes()),
                model=self.model,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                temperature=0.0,
                language=self.language or groq.omit,
            )
        except groq.APIStatusError as exc:
            raise TranscriberError(
                f"Groq answered {exc.status_code}: {_error_text(exc.response)}"
            ) from None
        except groq.APIError as exc:
            raise TranscriberError(f"Groq could not be reached: {exc.message}") from None
        text = raw.http_response.text
        (audio.parent / f"{name}.json").write_text(text, encoding="utf-8")
        book.record(job, STEP, PROVIDER, self.model, {"audio_minutes": minutes})
        try:
            reply = GroqReply.model_validate_json(text)
        except ValidationError as exc:
            missing = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
            raise TranscriberError(
                f"the Groq {name} reply is not verbose_json with timestamps "
                f"(missing or bad: {', '.join(missing)})"
            ) from None
        return to_transcript(reply, language=self.language, duration_s=duration_s)


def _note_changes(job: Job, what: str, before: list[Word], after: list[Word]) -> None:
    changed = sum(1 for a, b in zip(before, after, strict=True) if a != b)
    if changed:
        jobs.note(job, f"asr: {what} {changed} word{'s' if changed != 1 else ''}")


def _error_text(response: httpx.Response) -> str:
    try:
        body: object = response.json()
    except json.JSONDecodeError:
        return response.text[:500]
    if isinstance(body, dict):
        error = body.get("error")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(error, dict) and "message" in error:
            return str(error["message"])  # pyright: ignore[reportUnknownArgumentType]
    return response.text[:500]
