"""reference card v2 (ticket 073): the script, its story parts, the music in each part,
and a beat table of what was said and what was shown.

A hand-written v2 answer (`fixtures/gemini/inventory_v2.json`: `S5j-2CWYYwM`'s v1 card
plus plausible v2 fields) parses into the v2 model and is served by `FakeAnalyser`; the
committed v1 cards still load, and `gaps` reads both. Every closed-list label is checked
(an unknown mood, flavour or topic from the data files; part, match, event, `how` from
the schema) with one retry, then the reference stops naming the field and writes
nothing. `said` over 12 words is refused at parse time. The prompt lists the
vocabularies from `moods.yaml` and `topics.yaml` and is pinned by a snapshot under
`tests/fixtures/reference/`; set SHORTSMITH_UPDATE_SNAPSHOTS=1 to re-record it after a
deliberate change. No network, no key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from shortsmith import render, vocab
from shortsmith.reference import (
    PROMPT_VERSION,
    UNREGISTERED,
    AnswerInvalid,
    InventoryAnswer,
    InventoryAnswerV2,
    ReferenceError,
    ReferenceInventory,
    ReferenceInventoryV2,
    ReferenceLink,
    build_prompt,
    gaps,
    inventory,
    load_card,
    parse_answer,
    styles_for,
    v2_cards,
)
from shortsmith.reference import __main__ as cli
from shortsmith.reference.gemini import FakeAnalyser

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]
INVENTORY = REPO / "docs" / "reference" / "inventory"
# The 12 v1 cards as committed before the v2 re-analysis (079 step 2), frozen so the v1
# loader stays pinned after `docs/reference/inventory/` moved to v2.
INVENTORY_V1 = FIXTURES / "reference" / "inventory_v1"
REGISTRY = render.registry()
SNAPSHOT_REGISTRY = ("cut", "flash", "stamp", "text_pop", "map", "whip")


def _answer() -> dict[str, Any]:
    body = json.loads((FIXTURES / "gemini" / "inventory_v2.json").read_text(encoding="utf-8"))
    return json.loads(body["candidates"][0]["content"]["parts"][0]["text"])


def _text(answer: dict[str, Any] | None = None) -> str:
    return json.dumps(answer if answer is not None else _answer(), ensure_ascii=False)


def _link(vid: str = "S5j-2CWYYwM") -> ReferenceLink:
    return ReferenceLink(
        url=f"https://www.youtube.com/watch?v={vid}", video_id=vid, category="facts", tier="A",
        creator="Dhruv Rathee Shorts", title="What Would Happen If the Sun Disappeared?",
    )  # fmt: skip


def _fake(*answers: str) -> FakeAnalyser:
    return FakeAnalyser(list(answers), model="fake-video", fps=5.0)


# --- the v2 answer -------------------------------------------------------------------------


def test_the_v2_default_and_v1_still_possible() -> None:
    assert PROMPT_VERSION == "v2"
    assert "## JSON schema (InventoryAnswer)" in build_prompt(REGISTRY, version="v1")


def test_the_recorded_v2_answer_parses_into_the_v2_model() -> None:
    answer = parse_answer(_text(), registry=REGISTRY)
    assert isinstance(answer, InventoryAnswerV2)
    assert answer.script.topic == "science" and answer.script.language == "hi"
    assert [p.part for p in answer.parts] == ["hook", "build_up", "reveal", "ending"]
    assert answer.parts[1].music_mood == "eerie_scifi"
    assert [c.how for c in answer.music_changes] == ["crossfade", "hard_cut", "drop_to_silence"]
    assert len(answer.beats) == len(answer.shots) == 24
    first = answer.beats[0]
    assert (first.match, first.part, first.sound) == ("literal", "hook", "whoosh")
    assert first.effect == UNREGISTERED  # the model's label is checked like a component
    assert answer.beats[1].effect == "stamp"
    assert answer.effects[1].motion.entrance == "pop_overshoot"
    stamp = answer.sound.effects[1]
    assert (stamp.event, stamp.loudness, stamp.length_s) == ("stamp", "loud", 0.4)


def test_a_v1_reply_is_not_a_v2_answer_and_the_reasons_name_the_missing_fields() -> None:
    v1 = {k: v for k, v in _answer().items() if k not in {"script", "parts", "beats"}}
    with pytest.raises(AnswerInvalid) as raised:
        parse_answer(_text(v1), registry=REGISTRY)
    reasons = "\n".join(raised.value.reasons)
    assert "script" in reasons and "parts" in reasons and "beats" in reasons


def test_said_longer_than_twelve_words_is_refused_at_parse_time() -> None:
    answer = _answer()
    answer["beats"][3]["said"] = "one two three four five six seven eight nine ten eleven twelve"
    assert parse_answer(_text(answer), registry=REGISTRY)  # twelve is the limit
    answer["beats"][3]["said"] += " thirteen"
    with pytest.raises(AnswerInvalid) as raised:
        parse_answer(_text(answer), registry=REGISTRY)
    assert any(r.startswith("beats.3.said") and "12 words" in r for r in raised.value.reasons)


@pytest.mark.parametrize(
    ("path", "value", "field"),
    [
        (("parts", 1, "music_mood"), "jazzy_lounge", "parts.1.music_mood"),
        (("parts", 2, "music_flavour"), "latin", "parts.2.music_flavour"),
        (("script", "topic"), "cooking", "script.topic"),
        (("music_changes", 0, "how"), "fade_out", "music_changes.0.how"),
        (("beats", 5, "match"), "vibe", "beats.5.match"),
        (("beats", 5, "part"), "climax", "beats.5.part"),
        (("sound", "effects", 2, "event"), "explosion", "sound.effects.2.event"),
    ],
)
def test_an_unknown_closed_list_label_is_invalid_naming_the_field(
    path: tuple[str | int, ...], value: str, field: str
) -> None:
    answer = _answer()
    target: Any = answer
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(AnswerInvalid) as raised:
        parse_answer(_text(answer), registry=REGISTRY)
    assert any(r.startswith(field) for r in raised.value.reasons), raised.value.reasons


def test_an_unknown_mood_is_retried_once_then_the_reference_stops_naming_the_field(
    tmp_path: Path,
) -> None:
    bad = _answer()
    bad["parts"][0]["music_mood"] = "jazzy_lounge"
    fake = _fake(_text(bad), _text(bad))
    with pytest.raises(ReferenceError) as raised:
        inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert "parts.0.music_mood" in str(raised.value) and "jazzy_lounge" in str(raised.value)
    assert list(tmp_path.iterdir()) == []  # no partial JSON
    assert len(fake.calls) == 2
    assert "parts.0.music_mood" in fake.calls[1][1]  # the retry carries the reason


def test_an_unknown_topic_is_retried_once_and_a_good_second_answer_is_written(
    tmp_path: Path,
) -> None:
    bad = _answer()
    bad["script"]["topic"] = "cooking"
    fake = _fake(_text(bad), _text())
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert made.prompt_version == "v2" and (tmp_path / "S5j-2CWYYwM.json").is_file()
    assert "script.topic" in fake.calls[1][1]


# --- the card ------------------------------------------------------------------------------


def test_the_fake_analyser_serves_the_v2_fixture_into_a_v2_card(tmp_path: Path) -> None:
    fake = _fake(_text())
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert isinstance(made, ReferenceInventoryV2)
    assert made.prompt_version == "v2"
    # the styles this reference informs, from the trace table in styles/README.md
    assert made.styles == ["footage"]
    loaded = load_card((tmp_path / "S5j-2CWYYwM.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, ReferenceInventoryV2) and loaded == made
    assert "`tense_dramatic`" in fake.calls[0][1]  # the v2 prompt went out


def test_the_style_and_topic_flags_set_the_card(tmp_path: Path) -> None:
    fake = _fake(_text())
    made = inventory(
        _link("AAAAAAAAAAA"), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None,
        styles=["vishva"], topic="history",
    )  # fmt: skip
    assert isinstance(made, ReferenceInventoryV2)
    assert made.styles == ["vishva"] and made.script.topic == "history"


def test_styles_for_reads_the_trace_table() -> None:
    assert styles_for("S5j-2CWYYwM") == ["footage"]
    assert styles_for("nBihHUlYOQk") == ["vishva"]
    assert styles_for("zXK42RMPKUY") == ["fastfacts"]
    assert styles_for("AAAAAAAAAAA") == []


def test_every_committed_v1_card_still_loads_unchanged_as_v1() -> None:
    paths = sorted(INVENTORY_V1.glob("*.json"))
    assert len(paths) == 12
    for path in paths:
        text = path.read_text(encoding="utf-8")
        card = load_card(text)
        assert type(card) is ReferenceInventory, path.name
        assert card.prompt_version == "v1"
        assert json.loads(card.model_dump_json()) == json.loads(text), path.name


def test_a_reader_of_v2_fields_skips_a_v1_card_with_a_log_line(tmp_path: Path) -> None:
    v1 = load_card((INVENTORY_V1 / "zXK42RMPKUY.json").read_text(encoding="utf-8"))
    v2 = inventory(_link(), _fake(_text()), out_dir=tmp_path, registry=REGISTRY, log=print)
    lines: list[str] = []
    assert v2_cards([v1, v2], log=lines.append) == [v2]
    assert lines == ["zXK42RMPKUY: a v1 card has no v2 fields; skipped"]


def test_gaps_keeps_working_on_both_versions(tmp_path: Path) -> None:
    for name in ("zXK42RMPKUY.json", "nBihHUlYOQk.json"):
        (tmp_path / name).write_text((INVENTORY_V1 / name).read_text(encoding="utf-8"), "utf-8")
    inventory(_link(), _fake(_text()), out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    cards = gaps.load_all(tmp_path)
    assert sorted(c.video_id for c in cards) == ["S5j-2CWYYwM", "nBihHUlYOQk", "zXK42RMPKUY"]
    text = gaps.report(cards)
    assert "3 inventories" in text and "S5j-2CWYYwM" in _section(text, "facts / Tier A")


def test_the_committed_gaps_report_is_unchanged_by_the_loader() -> None:
    assert gaps.report(gaps.load_all(INVENTORY)) == (INVENTORY / "GAPS.md").read_text("utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


# --- the prompt ----------------------------------------------------------------------------


def test_the_v2_prompt_lists_the_vocabularies_from_the_data_files() -> None:
    prompt = build_prompt(REGISTRY)
    moods, topics = vocab.load_moods(), vocab.load_topics()
    for name, entry in (*moods.moods.items(), *moods.flavours.items()):
        assert f"`{name}`: {entry.meaning}" in prompt
    for name in topics.topics:
        assert f"`{name}`" in prompt
    for word in ("`build_up`", "`named_entity`", "`drop_to_silence`", "`text_pop`", "`soft`"):
        assert word in prompt
    assert "InventoryAnswerV2" in prompt and '"music_changes"' in prompt
    template = (REPO / "src/shortsmith/reference/prompts/inventory_v2.md").read_text("utf-8")
    for name in (*moods.moods, *moods.flavours, *topics.topics):
        assert f"`{name}`" not in template, f"{name} is copied into the prompt by hand"


def test_the_v2_prompt_follows_an_edited_moods_file(tmp_path: Path) -> None:
    edited = tmp_path / "moods.yaml"
    edited.write_text(
        vocab.MOODS_PATH.read_text(encoding="utf-8").replace(
            "flavours:", "  festive_brass:\n    meaning: bright brass fanfares\nflavours:"
        ),
        encoding="utf-8",
    )
    vocabulary = vocab.Vocabulary(vocab.load_moods(edited), vocab.load_topics())
    assert "`festive_brass`: bright brass fanfares" in build_prompt(
        REGISTRY, vocabulary=vocabulary
    )
    answer = _answer()
    answer["parts"][0]["music_mood"] = "festive_brass"
    assert parse_answer(_text(answer), registry=REGISTRY, vocabulary=vocabulary)
    with pytest.raises(AnswerInvalid):
        parse_answer(_text(answer), registry=REGISTRY)


def test_the_v2_prompt_matches_the_recorded_snapshot() -> None:
    text = build_prompt(
        SNAPSHOT_REGISTRY, components_md=FIXTURES / "reference" / "components.md"
    )
    path = FIXTURES / "reference" / f"inventory_{PROMPT_VERSION}.snapshot.md"
    if os.environ.get("SHORTSMITH_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.is_file(), f"no recorded rendering at {path}; record it deliberately"
    assert text == path.read_text(encoding="utf-8")


# --- the command line ----------------------------------------------------------------------


def test_the_cli_writes_a_v2_card_with_the_style_and_topic_flags(tmp_path: Path) -> None:
    from tests.test_reference import _settings  # pyright: ignore[reportPrivateUsage]

    code = cli.main(
        ["inventory", "https://youtu.be/AAAAAAAAAAA", "--out", str(tmp_path),
         "--style", "fastfacts", "--topic", "geopolitics"],
        analyser=_fake(_text()), settings=_settings(),
    )  # fmt: skip
    assert code == 0
    card = load_card((tmp_path / "AAAAAAAAAAA.json").read_text(encoding="utf-8"))
    assert isinstance(card, ReferenceInventoryV2)
    assert (card.styles, card.script.topic) == (["fastfacts"], "geopolitics")


def test_the_cli_refuses_an_unknown_style_or_topic_and_calls_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.test_reference import _settings  # pyright: ignore[reportPrivateUsage]

    fake = _fake(_text())
    for flag, value in (("--style", "noir"), ("--topic", "cooking")):
        code = cli.main(
            ["inventory", "https://youtu.be/AAAAAAAAAAA", "--out", str(tmp_path), flag, value],
            analyser=fake, settings=_settings(),
        )  # fmt: skip
        assert code == 1
        assert value in capsys.readouterr().err
    assert fake.calls == [] and list(tmp_path.iterdir()) == []


def test_the_cli_prompt_v1_writes_a_v1_card(tmp_path: Path) -> None:
    from tests.test_reference import _answer_text, _settings  # pyright: ignore[reportPrivateUsage]

    code = cli.main(
        ["inventory", "https://youtu.be/zXK42RMPKUY", "--out", str(tmp_path), "--prompt", "v1"],
        analyser=_fake(_answer_text()), settings=_settings(),
    )  # fmt: skip
    assert code == 0
    card = load_card((tmp_path / "zXK42RMPKUY.json").read_text(encoding="utf-8"))
    assert type(card) is ReferenceInventory and card.prompt_version == "v1"
    assert isinstance(card, InventoryAnswer)
