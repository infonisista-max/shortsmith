"""The transcriber (PRD `transcriber`; decisions 6.1, 12.1, 13.1).

`base` holds the interface, `fake` the twelve fixture words, `fixes` the research §6
fix pass (pure functions plus the per-language fix maps in `fixmaps/`) and `groq` the
direct Groq Whisper adapter. `TRANSCRIBER` selects the adapter: `groq` outside tests,
`fake` in tests and smoke.
"""

from __future__ import annotations

from collections.abc import Callable

from shortsmith.config import Settings
from shortsmith.ledger import Ledger
from shortsmith.transcriber import fixes
from shortsmith.transcriber.base import Transcriber, TranscriberError
from shortsmith.transcriber.fake import FakeTranscriber
from shortsmith.transcriber.groq import GroqTranscriber

__all__ = [
    "AUTO_LANGUAGE",
    "FakeTranscriber",
    "GroqTranscriber",
    "Transcriber",
    "TranscriberError",
    "fixes",
    "from_settings",
]

# 052: the `TRANSCRIBER_LANGUAGE` spelling for "let Whisper detect it". An empty
# value in `.env` now means unset (the default `hi`), so detection needs a word.
AUTO_LANGUAGE = "auto"


def from_settings(settings: Settings, *, ledger: Callable[[], Ledger]) -> Transcriber:
    """The adapter `TRANSCRIBER` names; `ledger` resolves the app's ledger at call time.
    A missing key is the startup check's to report (`config.check_startup`)."""
    if settings.transcriber == "fake":
        return FakeTranscriber()
    language = settings.transcriber_language
    return GroqTranscriber(
        ledger,
        api_key=settings.groq_api_key,
        model=settings.transcriber_model,
        language=None if language in ("", AUTO_LANGUAGE) else language,
    )
