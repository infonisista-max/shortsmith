"""An off-list label lands as `other` with a log line instead of failing the card (092).

A closed list that already holds `other` (`SfxKind`, `SfxEvent`, `Entrance`, `Layout`)
takes a word the model invented as `other`; the card keeps the word in `off_list` and
`gaps` counts them. Lists without `other`, wrong types, broken JSON and a long `said` stay
strict and keep the one retry. Served by `FakeAnalyser`; no network, no key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shortsmith import render
from shortsmith.reference import (
    ReferenceInventory,
    ReferenceInventoryV2,
    ReferenceLink,
    gaps,
    inventory,
    load_card,
    v2_cards,
)
from shortsmith.reference.gemini import FakeAnalyser

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]
INVENTORY = REPO / "docs" / "reference" / "inventory"
INVENTORY_V1 = FIXTURES / "reference" / "inventory_v1"
REGISTRY = render.registry()
VIDEO = "S5j-2CWYYwM"


def _answer() -> dict[str, Any]:
    body = json.loads((FIXTURES / "gemini" / "inventory_v2.json").read_text(encoding="utf-8"))
    return json.loads(body["candidates"][0]["content"]["parts"][0]["text"])


def _text(answer: dict[str, Any] | None = None) -> str:
    return json.dumps(answer if answer is not None else _answer(), ensure_ascii=False)


def _link() -> ReferenceLink:
    return ReferenceLink(
        url=f"https://www.youtube.com/watch?v={VIDEO}", video_id=VIDEO, category="facts"
    )


def _fake(*answers: str) -> FakeAnalyser:
    return FakeAnalyser(list(answers), model="fake-video", fps=5.0)


def _off_list_answer() -> dict[str, Any]:
    answer = _answer()
    answer["sound"]["effects"][3]["kind"] = "swoosh"
    answer["beats"][2]["sound"] = "boom"
    return answer


def test_off_list_words_on_lists_with_other_are_stored_as_other_on_the_first_attempt(
    tmp_path: Path,
) -> None:
    fake = _fake(_text(_off_list_answer()))
    lines: list[str] = []
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lines.append)
    assert len(fake.calls) == 1  # no retry
    assert isinstance(made, ReferenceInventoryV2)
    assert made.sound.effects[3].kind == "other" and made.beats[2].sound == "other"
    assert [(row.field, row.said) for row in made.off_list] == [
        ("sound.effects.3.kind", "swoosh"),
        ("beats.2.sound", "boom"),
    ]
    assert f"{VIDEO}: sound.effects.3.kind 'swoosh' is not on the list; stored as other" in lines
    assert f"{VIDEO}: beats.2.sound 'boom' is not on the list; stored as other" in lines
    loaded = load_card((tmp_path / f"{VIDEO}.json").read_text(encoding="utf-8"))
    assert loaded == made and loaded.off_list == made.off_list


@pytest.mark.parametrize(
    ("path", "word"),
    [
        (("sound", "effects", 1, "event"), "explosion"),
        (("effects", 1, "motion", "entrance"), "spin"),
        (("shots", 0, "layout"), "collage"),
        (("beats", 0, "layout"), "collage"),
    ],
)
def test_every_list_that_holds_other_coerces(
    tmp_path: Path, path: tuple[str | int, ...], word: str
) -> None:
    answer = _answer()
    target: Any = answer
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = word
    made = inventory(
        _link(), _fake(_text(answer)), out_dir=tmp_path, registry=REGISTRY, log=lambda _: None
    )
    field = ".".join(str(p) for p in path)
    assert [(row.field, row.said) for row in made.off_list] == [(field, word)]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("beats", 5, "match"), "vibe"),  # Match has no `other`
        (("sound", "effects", 2, "loudness"), "deafening"),  # nor Loudness
        (("effects", 1, "motion", "region"), "corner"),  # nor Region
        (("sound", "effects", 3, "kind"), 7),  # a number where a word belongs
        (("sound", "effects", 3, "kind"), None),  # null where the schema forbids it
        (("beats", 3, "said"), "one two three four five six seven eight nine ten eleven 12 13"),
    ],
)
def test_what_stays_strict_takes_the_retry(
    tmp_path: Path, path: tuple[str | int, ...], value: object
) -> None:
    bad = _answer()
    target: Any = bad
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    fake = _fake(_text(bad), _text())
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert len(fake.calls) == 2
    assert ".".join(str(p) for p in path) in fake.calls[1][1]  # the retry names the field
    assert made.off_list == []


def test_broken_json_still_takes_the_retry(tmp_path: Path) -> None:
    fake = _fake(_text()[:-40], _text())
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert len(fake.calls) == 2 and made.off_list == []


def test_a_clean_card_writes_no_off_list_key(tmp_path: Path) -> None:
    inventory(_link(), _fake(_text()), out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert "off_list" not in json.loads((tmp_path / f"{VIDEO}.json").read_text("utf-8"))


def test_every_committed_card_still_loads_unchanged_and_v2_cards_keeps_them() -> None:
    for folder in (INVENTORY_V1, INVENTORY):
        for path in sorted(folder.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            card = load_card(text)
            assert card.off_list == [], path.name
            assert json.loads(card.model_dump_json()) == json.loads(text), path.name
    committed = gaps.load_all(INVENTORY)
    before = [c.video_id for c in v2_cards(committed, log=lambda _: None)]
    assert before and all(isinstance(c, ReferenceInventory) for c in committed)


def test_gaps_lists_off_list_words_with_counts(tmp_path: Path) -> None:
    first = _off_list_answer()
    second = _off_list_answer()
    second["sound"]["effects"][1]["kind"] = "Swoosh "
    for vid, answer in (("AAAAAAAAAAA", first), ("BBBBBBBBBBB", second)):
        link = ReferenceLink(url=f"https://www.youtube.com/watch?v={vid}", video_id=vid)
        inventory(
            link, _fake(_text(answer)), out_dir=tmp_path, registry=REGISTRY, log=lambda _: None
        )
    text = gaps.report(gaps.load_all(tmp_path))
    section = text[text.index("## Off-list labels") :].split("\n## ")[0]
    assert "| `sound.effects.N.kind` | `swoosh` | 3 | 2 |" in section
    assert "| `beats.N.sound` | `boom` | 2 | 2 |" in section
    assert section.index("swoosh") < section.index("boom")  # ranked by count


def test_gaps_without_off_list_words_has_no_off_list_section(tmp_path: Path) -> None:
    inventory(_link(), _fake(_text()), out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert "Off-list" not in gaps.report(gaps.load_all(tmp_path))
