"""A reference card's music changes must match its story parts (ticket 086).

For every neighbouring pair of parts whose `music_mood` or `music_flavour` differs
(music starting or stopping included), `music_changes` holds a change from the earlier
part to the later one. The check (`uncovered_boundaries`) runs at write time as an
invalid answer with 073's one retry, and at read time in `v2_cards`, which skips a
failing card with a log line. Prompt v3 says it in the model's terms; v2 stays
possible and its text and snapshot are unchanged. No network, no key.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from shortsmith import render
from shortsmith.reference import (
    INVENTORY_DIR,
    PROMPT_VERSION,
    PROMPTS_DIR,
    AnswerInvalid,
    InventoryAnswerV2,
    ReferenceError,
    ReferenceInventory,
    ReferenceInventoryV2,
    ReferenceLink,
    build_prompt,
    inventory,
    load_card,
    music,
    parse_answer,
    uncovered_boundaries,
    v2_cards,
)
from shortsmith.reference.gemini import FakeAnalyser, Usage

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = render.registry()
SNAPSHOT_REGISTRY = ("cut", "flash", "stamp", "text_pop", "map", "whip")
FAILING = {"FbaBcWgMIEY", "ePTZVwipoAM"}


def _answer() -> dict[str, Any]:
    body = json.loads((FIXTURES / "gemini" / "inventory_v2.json").read_text(encoding="utf-8"))
    return json.loads(body["candidates"][0]["content"]["parts"][0]["text"])


def _text(answer: dict[str, Any]) -> str:
    return json.dumps(answer, ensure_ascii=False)


def _with(
    moods: Sequence[tuple[str | None, str | None]], changes: Sequence[tuple[str, str]]
) -> dict[str, Any]:
    """The recorded answer with its four parts' (mood, flavour) and the changes given."""
    answer = _answer()
    for part, (mood, flavour) in zip(answer["parts"], moods, strict=True):
        part["music_mood"], part["music_flavour"] = mood, flavour
    answer["music_changes"] = [
        {"at_s": 1.0, "from_part": a, "to_part": b, "how": "crossfade"} for a, b in changes
    ]
    return answer


def _model(answer: dict[str, Any]) -> InventoryAnswerV2:
    return InventoryAnswerV2.model_validate(answer)


def _link(vid: str = "S5j-2CWYYwM") -> ReferenceLink:
    return ReferenceLink(url=f"https://www.youtube.com/watch?v={vid}", video_id=vid)


def _fake(*answers: str) -> FakeAnalyser:
    return FakeAnalyser(list(answers), model="fake-video", fps=5.0)


PULSE = ("investigative_pulse", None)


# --- the check -----------------------------------------------------------------------------


def test_no_differing_boundary_and_no_change_passes() -> None:
    assert uncovered_boundaries(_model(_with([PULSE] * 4, []))) == []


def test_one_differing_flavour_and_no_change_fails_naming_it() -> None:
    answer = _with(
        [("investigative_pulse", "middle_east")] * 2 + [("investigative_pulse", "european")] * 2,
        [],
    )
    assert uncovered_boundaries(_model(answer)) == [("build_up", "reveal")]


def test_three_differing_moods_and_one_change_names_the_other_two() -> None:
    answer = _with(
        [("tense_dramatic", None), PULSE, ("mysterious_curiosity", None), ("tense_dramatic", None)],
        [("build_up", "reveal")],
    )
    assert uncovered_boundaries(_model(answer)) == [("hook", "build_up"), ("reveal", "ending")]


def test_music_starting_counts_as_a_difference() -> None:
    answer = _with([(None, None), PULSE, PULSE, PULSE], [])
    assert uncovered_boundaries(_model(answer)) == [("hook", "build_up")]
    stopping = _with([PULSE, PULSE, PULSE, (None, None)], [])
    assert uncovered_boundaries(_model(stopping)) == [("reveal", "ending")]


def test_an_extra_change_where_nothing_differs_passes() -> None:
    answer = _with([PULSE] * 4, [("build_up", "reveal")])
    assert uncovered_boundaries(_model(answer)) == []


def test_the_two_contradicting_committed_cards_fail_and_the_other_eleven_pass() -> None:
    failing: set[str] = set()
    paths = sorted(INVENTORY_DIR.glob("*.json"))
    assert len(paths) == 13
    for path in paths:
        card = load_card(path.read_text(encoding="utf-8"))
        assert isinstance(card, ReferenceInventoryV2), path.name
        if uncovered_boundaries(card):
            failing.add(card.video_id)
    assert failing == FAILING


# --- write time: 073's one retry ------------------------------------------------------------


def _flavour_miss() -> dict[str, Any]:
    return _with(
        [("investigative_pulse", "middle_east")] * 2 + [("investigative_pulse", "european")] * 2,
        [],
    )


def test_a_boundary_miss_is_an_invalid_answer_that_says_keep_the_parts() -> None:
    with pytest.raises(AnswerInvalid) as raised:
        parse_answer(_text(_flavour_miss()), registry=REGISTRY)
    reasons = "\n".join(raised.value.reasons)
    assert "build_up -> reveal" in reasons
    assert "keep `parts` as they are; add the missing `music_changes` entry" in reasons


def test_a_miss_takes_one_retry_naming_the_boundary_and_a_good_answer_is_written(
    tmp_path: Path,
) -> None:
    fake = _fake(_text(_flavour_miss()), _text(_answer()))
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lambda _: None)
    assert isinstance(made, ReferenceInventoryV2)
    assert len(fake.calls) == 2
    assert "build_up -> reveal" in fake.calls[1][1]
    assert "keep `parts` as they are" in fake.calls[1][1]


def test_a_second_miss_writes_no_card_and_names_the_video_and_boundary(tmp_path: Path) -> None:
    lines: list[str] = []
    fake = _fake(_text(_flavour_miss()), _text(_flavour_miss()))
    with pytest.raises(ReferenceError) as raised:
        inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lines.append)
    assert "S5j-2CWYYwM" in str(raised.value) and "build_up -> reveal" in str(raised.value)
    assert list(tmp_path.iterdir()) == []
    assert len(fake.calls) == 2


# --- read time: v2_cards ------------------------------------------------------------------------


def _card_file(folder: Path, vid: str, answer: dict[str, Any]) -> ReferenceInventoryV2:
    parsed = InventoryAnswerV2.model_validate(answer)
    made = ReferenceInventory.from_answer(
        parsed, link=_link(vid), model="fake-video", fps=5.0,
        usage=Usage(prompt_tokens=0, output_tokens=0, total_tokens=0), analysed_on="2026-09-29",
    )  # fmt: skip
    assert isinstance(made, ReferenceInventoryV2)
    (folder / f"{vid}.json").write_text(made.model_dump_json(indent=2), encoding="utf-8")
    return made


def test_v2_cards_skips_a_failing_card_with_the_log_line(tmp_path: Path) -> None:
    good = _card_file(tmp_path, "aaaaaaaaaaa", _answer())
    bad = _card_file(
        tmp_path,
        "bbbbbbbbbbb",
        _with(
            [("tense_dramatic", None), PULSE, ("mysterious_curiosity", None),
             ("tense_dramatic", None)],
            [("build_up", "reveal")],
        ),
    )  # fmt: skip
    lines: list[str] = []
    assert v2_cards([good, bad], log=lines.append) == [good]
    assert lines == [
        "bbbbbbbbbbb: music_changes misses hook -> build_up, reveal -> ending; skipped"
    ]


def test_pairing_never_sees_a_failing_card(tmp_path: Path) -> None:
    _card_file(tmp_path, "aaaaaaaaaaa", _answer())
    _card_file(tmp_path, "bbbbbbbbbbb", _flavour_miss())
    lines = music.for_job(tmp_path)
    assert len(lines) == 1 and "aaaaaaaaaaa" in lines[0]


def test_the_committed_failing_cards_never_reach_pairing() -> None:
    joined = "\n".join(music.for_job())
    for vid in FAILING:
        assert vid not in joined


# --- prompt v3 ------------------------------------------------------------------------------------


def test_v3_is_the_default_and_v2_stays_possible() -> None:
    assert PROMPT_VERSION == "v3"
    v3, v2 = build_prompt(REGISTRY), build_prompt(REGISTRY, version="v2")
    assert "# Reference inventory (v3)" in v3 and "# Reference inventory (v2)" in v2
    assert "boundary" in v3 and "boundary" not in v2


def test_a_default_card_carries_v3_and_loads_beside_a_v2_card(tmp_path: Path) -> None:
    made = inventory(
        _link("aaaaaaaaaaa"), _fake(_text(_answer())), out_dir=tmp_path, registry=REGISTRY,
        log=lambda _: None,
    )  # fmt: skip
    old = inventory(
        _link("bbbbbbbbbbb"), _fake(_text(_answer())), out_dir=tmp_path, registry=REGISTRY,
        log=lambda _: None, version="v2",
    )  # fmt: skip
    assert made.prompt_version == "v3" and old.prompt_version == "v2"
    for vid, version in (("aaaaaaaaaaa", "v3"), ("bbbbbbbbbbb", "v2")):
        text = (tmp_path / f"{vid}.json").read_text(encoding="utf-8")
        assert json.loads(text)["prompt_version"] == version
        card = load_card(text)
        assert isinstance(card, ReferenceInventoryV2) and card.prompt_version == version
    lines = music.for_job(tmp_path)
    assert [line.split(" ")[1] for line in lines] == ["aaaaaaaaaaa", "bbbbbbbbbbb"]


def test_the_v2_prompt_file_is_unchanged_and_v3_is_a_new_file() -> None:
    assert (PROMPTS_DIR / "inventory_v3.md").is_file()
    assert (FIXTURES / "reference" / "inventory_v2.snapshot.md").is_file()
    text = build_prompt(SNAPSHOT_REGISTRY, components_md=FIXTURES / "reference" / "components.md",
                        version="v2")  # fmt: skip
    pinned = (FIXTURES / "reference" / "inventory_v2.snapshot.md").read_text(encoding="utf-8")
    assert text == pinned


def test_the_v3_prompt_matches_the_recorded_snapshot() -> None:
    text = build_prompt(
        SNAPSHOT_REGISTRY, components_md=FIXTURES / "reference" / "components.md", version="v3"
    )
    path = FIXTURES / "reference" / "inventory_v3.snapshot.md"
    if os.environ.get("SHORTSMITH_UPDATE_SNAPSHOTS") == "1":
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.is_file(), f"no recorded rendering at {path}; record it deliberately"
    assert text == path.read_text(encoding="utf-8")
