"""The transcriber interface (decisions 6.1, 12.1, 13.1).

`transcribe(audio)` returns the word-level transcript with final times: the research
§6 fix pass has run, and the planner never touches them (6.1). `bind(job)` hands an
adapter the job it is about to transcribe, so a real adapter can write under the job's
`work/asr/`, note its fixes in `job.log` and record its ledger rows; the fake ignores
it. A transcriber that cannot answer raises `TranscriberError` and the job fails at
`transcribing`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Self

from shortsmith.contracts import Transcript
from shortsmith.jobs import Job


class TranscriberError(Exception):
    """The transcriber could not answer (HTTP error, unreadable reply, no key)."""


class Transcriber(ABC):
    def bind(self, job: Job) -> Self:
        """This transcriber for `job`; adapters that write files or ledger rows override it."""
        return self

    @abstractmethod
    def transcribe(self, audio: Path) -> Transcript:
        """Word-level transcript with final times; the planner never touches them (6.1)."""
