"""vocab: the closed vocabularies the reference card, the planner and the sound director
share (ticket 073): `assets/audio/moods.yaml` (bed moods and regional flavours) and
`assets/reference/topics.yaml` (topics with English and Hindi keywords). Both load at
startup; a duplicate or empty entry is refused naming it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import vocab
from shortsmith.vocab import VocabError

MOODS = (
    "tense_dramatic",
    "investigative_pulse",
    "mysterious_curiosity",
    "calm_ambient",
    "eerie_scifi",
    "upbeat_electronic",
    "energetic_beat",
)
FLAVOURS = ("middle_east", "indian", "east_asian", "european")
TOPICS = ("history", "geopolitics", "science", "business", "tech", "society", "sport", "other")


def test_the_committed_moods_file_carries_the_seven_moods_and_four_flavours() -> None:
    moods = vocab.load_moods()
    assert tuple(moods.moods) == MOODS
    assert tuple(moods.flavours) == FLAVOURS
    assert all(entry.meaning for entry in moods.moods.values())
    # 075's first batch: the first four moods, plus middle_east and indian
    assert moods.active_moods() == MOODS[:4]
    assert moods.active_flavours() == ("middle_east", "indian")


def test_the_committed_topics_file_carries_eight_topics_with_both_languages() -> None:
    topics = vocab.load_topics()
    assert tuple(topics.topics) == TOPICS
    for name, topic in topics.topics.items():
        assert topic.meaning, name
        if name != vocab.OTHER_TOPIC:
            assert topic.en and topic.hi, name
    # Hindi keywords as Whisper writes them: Devanagari, and the romanised forms too
    assert any(any("ऀ" <= ch <= "ॿ" for ch in word) for word in topics.topics["history"].hi)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_duplicate_mood_is_refused_naming_it(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "moods.yaml",
        "moods:\n"
        "  calm_ambient: {meaning: soft pads}\n"
        "  calm_ambient: {meaning: again}\n"
        "flavours:\n"
        "  indian: {meaning: sitar}\n",
    )
    with pytest.raises(VocabError, match="calm_ambient"):
        vocab.load_moods(path)


def test_an_empty_mood_or_flavour_is_refused_naming_it(tmp_path: Path) -> None:
    empty_mood = _write(
        tmp_path, "a.yaml", "moods:\n  calm_ambient:\nflavours:\n  indian: {meaning: sitar}\n"
    )
    with pytest.raises(VocabError, match="calm_ambient"):
        vocab.load_moods(empty_mood)
    blank_meaning = _write(
        tmp_path,
        "b.yaml",
        "moods:\n  calm_ambient: {meaning: soft}\nflavours:\n  indian: {meaning: ''}\n",
    )
    with pytest.raises(VocabError, match="indian"):
        vocab.load_moods(blank_meaning)
    no_moods = _write(tmp_path, "c.yaml", "moods: {}\nflavours:\n  indian: {meaning: sitar}\n")
    with pytest.raises(VocabError, match="moods"):
        vocab.load_moods(no_moods)


def test_a_duplicate_or_empty_topic_is_refused_naming_it(tmp_path: Path) -> None:
    twice = _write(
        tmp_path,
        "a.yaml",
        "topics:\n"
        "  history: {meaning: the past, en: [empire], hi: [itihas]}\n"
        "  history: {meaning: again, en: [king], hi: [raja]}\n"
        "  other: {meaning: anything else}\n",
    )
    with pytest.raises(VocabError, match="history"):
        vocab.load_topics(twice)
    no_hindi = _write(
        tmp_path,
        "b.yaml",
        "topics:\n  science: {meaning: nature, en: [atom], hi: []}\n  other: {meaning: else}\n",
    )
    with pytest.raises(VocabError, match="science"):
        vocab.load_topics(no_hindi)
    word_twice = _write(
        tmp_path,
        "c.yaml",
        "topics:\n  tech: {meaning: t, en: [ai, ai], hi: [takneek]}\n  other: {meaning: else}\n",
    )
    with pytest.raises(VocabError, match="tech"):
        vocab.load_topics(word_twice)
    no_other = _write(tmp_path, "d.yaml", "topics:\n  tech: {meaning: t, en: [ai], hi: [ai]}\n")
    with pytest.raises(VocabError, match="other"):
        vocab.load_topics(no_other)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(VocabError, match="not found"):
        vocab.load_moods(tmp_path / "moods.yaml")
    with pytest.raises(VocabError, match="not found"):
        vocab.load_topics(tmp_path / "topics.yaml")


def test_the_app_does_not_build_with_a_broken_vocabulary(tmp_path: Path) -> None:
    from shortsmith import app as app_module
    from shortsmith.planner import FakePlanner
    from shortsmith.presenter import FakeFaceDetector
    from shortsmith.qa.gate import FakeGate
    from shortsmith.render import FakeRenderer
    from shortsmith.transcriber import FakeTranscriber
    from tests.test_app import _settings  # pyright: ignore[reportPrivateUsage]

    fakes = dict(
        transcriber=FakeTranscriber(), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), detector=FakeFaceDetector(), start_worker=False,
    )  # fmt: skip
    broken_moods = _write(tmp_path, "moods.yaml", "moods:\n  calm_ambient:\nflavours: {}\n")
    with pytest.raises(VocabError, match="calm_ambient"):
        app_module.create_app(_settings(tmp_path), **fakes, audio_moods=broken_moods)  # pyright: ignore[reportArgumentType]
    broken_topics = _write(tmp_path, "topics.yaml", "topics:\n  tech: {meaning: t}\n")
    with pytest.raises(VocabError, match="tech"):
        app_module.create_app(_settings(tmp_path), **fakes, topics=broken_topics)  # pyright: ignore[reportArgumentType]
