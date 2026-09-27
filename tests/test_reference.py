"""reference: the inventory tool (ticket 036; decision 10.3, user story 49).

URL normalisation, the recorded answer parsed into `ReferenceInventory` with unknown
component labels turned `unregistered`, the one retry then stop with no partial JSON,
`--all` moving past a failing video with its status logged, the token log line on every
request, the Gemini adapter's one request on a mock transport, the GAPS report on three
fixture inventories, and the links read from `docs/references.md`. No network, no key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from shortsmith import config, render
from shortsmith.reference import (
    PROMPT_VERSION,
    UNREGISTERED,
    AnswerInvalid,
    InventoryAnswer,
    ReferenceError,
    ReferenceInventory,
    ReferenceLink,
    build_prompt,
    gaps,
    gemini,
    inventory,
    inventory_all,
    link_for,
    links_in,
    normalise,
    parse_answer,
    video_id,
)
from shortsmith.reference import __main__ as cli
from shortsmith.reference.gemini import AnalyserError, FakeAnalyser, GeminiAnalyser

FIXTURES = Path(__file__).parent / "fixtures" / "gemini"
REPO = Path(__file__).resolve().parents[1]
KEY = "gemini-test-key-not-a-real-one"
REGISTRY = render.registry()

OPERATOR_LINKS = {
    "https://youtube.com/shorts/VSJzviqMO7k": "VSJzviqMO7k",
    "https://youtube.com/shorts/Q2pquJ2FlzA": "Q2pquJ2FlzA",
    "https://youtube.com/shorts/cKxkAjYHXbk": "cKxkAjYHXbk",
    "https://youtube.com/shorts/zXK42RMPKUY": "zXK42RMPKUY",
    "https://youtube.com/shorts/bL3rUtUPYsc": "bL3rUtUPYsc",
    "https://youtube.com/shorts/S5j-2CWYYwM": "S5j-2CWYYwM",
}


def _recorded(name: str = "inventory") -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _answer_text(name: str = "inventory") -> str:
    return _recorded(name)["candidates"][0]["content"]["parts"][0]["text"]


def _link(vid: str = "zXK42RMPKUY", **changes: Any) -> ReferenceLink:
    given: dict[str, Any] = {
        "url": f"https://www.youtube.com/watch?v={vid}",
        "video_id": vid,
        "category": "facts",
        "tier": "A",
        "creator": "FactTechz",
        "title": "CRAZY Facts About BRAIN and BODY!",
    }
    given.update(changes)
    return ReferenceLink(**given)


def _fake(*answers: str | AnalyserError) -> FakeAnalyser:
    return FakeAnalyser(list(answers), model="fake-video", fps=5.0)


# --- URL normalisation -------------------------------------------------------------------


@pytest.mark.parametrize(("url", "expected"), sorted(OPERATOR_LINKS.items()))
def test_the_six_operator_links_become_plain_watch_urls(url: str, expected: str) -> None:
    assert video_id(url) == expected
    assert normalise(url) == f"https://www.youtube.com/watch?v={expected}"


def test_a_youtu_be_link_and_a_watch_link_with_extra_parameters_normalise_too() -> None:
    assert normalise("https://youtu.be/id00R-3OmJ0?si=abcDEF123") == (
        "https://www.youtube.com/watch?v=id00R-3OmJ0"
    )
    assert normalise("https://www.youtube.com/watch?v=S5j-2CWYYwM&t=12s&feature=share") == (
        "https://www.youtube.com/watch?v=S5j-2CWYYwM"
    )
    assert normalise("https://youtube.com/shorts/VSJzviqMO7k?si=tracking") == (
        "https://www.youtube.com/watch?v=VSJzviqMO7k"
    )
    assert normalise("https://m.youtube.com/watch?feature=share&v=Q2pquJ2FlzA") == (
        "https://www.youtube.com/watch?v=Q2pquJ2FlzA"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=S5j-2CWYYwM",
        "https://www.youtube.com/channel/UCabc",
        "https://www.youtube.com/watch?v=short",
        "not a url",
    ],
)
def test_a_link_that_is_not_a_youtube_video_is_refused(url: str) -> None:
    with pytest.raises(ReferenceError):
        video_id(url)


# --- the prompt --------------------------------------------------------------------------


def test_the_prompt_lists_every_registry_name_with_its_meaning_and_the_schema() -> None:
    prompt = build_prompt(REGISTRY)
    assert PROMPT_VERSION in prompt
    for name in REGISTRY:
        assert f"`{name}`" in prompt
    # the one-line meaning comes from docs/components.md, not from code
    assert "Ken Burns" in prompt
    assert "InventoryAnswer" in prompt and '"duration_s"' in prompt
    assert prompt.rstrip().endswith("with no prose before\nor after it.")
    assert UNREGISTERED in prompt


# --- the answer --------------------------------------------------------------------------


def test_the_recorded_answer_parses_into_an_inventory_answer() -> None:
    answer = parse_answer(_answer_text(), registry=REGISTRY)
    assert isinstance(answer, InventoryAnswer)
    assert answer.duration_s == 30.0
    assert [s.layout for s in answer.shots] == ["presenter_full", "full_footage", "card",
                                                "full_footage"]  # fmt: skip
    assert answer.shots[1].footage_kind == "stock" and answer.shots[1].clip_s == 4.6
    assert answer.sound.bed and len(answer.sound.effects) == 3
    assert answer.hook.on_screen.startswith("presenter full frame")


def test_an_unknown_component_label_becomes_unregistered_and_a_known_one_stays() -> None:
    answer = parse_answer(_answer_text(), registry=REGISTRY)
    assert [e.component for e in answer.effects] == ["stamp", UNREGISTERED, UNREGISTERED]
    assert answer.effects[1].name == "glitch_text"  # the model's own name is kept
    assert [t.component for t in answer.transitions] == ["cut", "whip", UNREGISTERED]


def test_a_reply_that_is_not_json_or_not_the_schema_is_invalid_with_the_reasons() -> None:
    with pytest.raises(AnswerInvalid) as raised:
        parse_answer("I could not watch the video.", registry=REGISTRY)
    assert "no JSON object" in str(raised.value)
    with pytest.raises(AnswerInvalid) as bad:
        parse_answer('{"duration_s": "long"}', registry=REGISTRY)
    assert "duration_s" in str(bad.value)
    fenced = f"```json\n{_answer_text()}\n```"
    assert parse_answer(fenced, registry=REGISTRY).duration_s == 30.0


# --- inventory: the command --------------------------------------------------------------


def test_a_good_answer_writes_the_inventory_json_tagged_estimated(tmp_path: Path) -> None:
    fake = _fake(_answer_text())
    lines: list[str] = []
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lines.append)
    path = tmp_path / "zXK42RMPKUY.json"
    assert path.is_file()
    loaded = ReferenceInventory.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded == made
    assert loaded.tag == "ESTIMATED"
    assert (loaded.video_id, loaded.category, loaded.tier) == ("zXK42RMPKUY", "facts", "A")
    assert (loaded.model, loaded.fps, loaded.prompt_version) == ("fake-video", 5.0, PROMPT_VERSION)
    assert loaded.url == "https://www.youtube.com/watch?v=zXK42RMPKUY"
    # counts are code's arithmetic over the lists and the duration, per 10 s
    assert (loaded.counts.shots_per_10s, loaded.counts.effects_per_10s) == (1.3, 1.0)
    assert loaded.counts.sfx_per_10s == 1.0
    assert fake.calls[0][0] == loaded.url
    assert "no prose" in fake.calls[0][1]


def test_every_request_logs_the_tokens_it_used(tmp_path: Path) -> None:
    fake = _fake("not json", _answer_text())
    lines: list[str] = []
    made = inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lines.append)
    token_lines = [line for line in lines if "tokens" in line]
    assert len(token_lines) == 2  # the call and its retry each log their usage
    assert "zXK42RMPKUY" in token_lines[0] and "fake-video" in token_lines[0]
    assert made.usage.prompt_tokens > 0 and made.usage.total_tokens >= made.usage.prompt_tokens


def test_a_malformed_answer_is_retried_once_with_the_reasons_then_the_tool_stops(
    tmp_path: Path,
) -> None:
    fake = _fake("not json", '{"duration_s": 3}')
    lines: list[str] = []
    with pytest.raises(ReferenceError) as raised:
        inventory(_link(), fake, out_dir=tmp_path, registry=REGISTRY, log=lines.append)
    assert "zXK42RMPKUY" in str(raised.value)
    assert list(tmp_path.iterdir()) == []  # no partial JSON
    assert len(fake.calls) == 2
    retry_prompt = fake.calls[1][1]
    assert "previous reply was rejected" in retry_prompt
    assert "no JSON object" in retry_prompt and "not json" in retry_prompt


def test_a_private_or_failing_video_logs_its_status_and_all_moves_on(tmp_path: Path) -> None:
    fake = _fake(AnalyserError("video is private", status=403), _answer_text())
    lines: list[str] = []
    failed = inventory_all(
        [_link("VSJzviqMO7k"), _link("zXK42RMPKUY")],
        fake,
        out_dir=tmp_path,
        registry=REGISTRY,
        log=lines.append,
    )
    assert failed == 1
    assert not (tmp_path / "VSJzviqMO7k.json").exists()
    assert (tmp_path / "zXK42RMPKUY.json").is_file()
    assert any("VSJzviqMO7k" in line and "403" in line for line in lines)
    assert len(fake.calls) == 2  # a failing video is not retried


# --- the Gemini adapter ------------------------------------------------------------------


class Recorded:
    def __init__(self, body: object | None = None, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is None:
            return httpx.Response(self.status)
        return httpx.Response(self.status, json=self.body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def sent(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content.decode("utf-8"))


def _gemini(tape: Recorded, *, model: str = "gemini-test-video", fps: float = 5.0) -> GeminiAnalyser:  # noqa: E501
    return GeminiAnalyser(api_key=SecretStr(KEY), model=model, fps=fps, client=tape.client())


def test_gemini_posts_the_watch_url_at_the_configured_fps_and_reads_the_usage() -> None:
    tape = Recorded(_recorded())
    url = "https://www.youtube.com/watch?v=zXK42RMPKUY"
    answer = _gemini(tape).analyse(url, "watch this")
    request = tape.requests[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-test-video:generateContent"
    )
    assert request.headers["x-goog-api-key"] == KEY
    sent = tape.sent()
    parts = sent["contents"][0]["parts"]
    assert parts[0] == {"fileData": {"fileUri": url}, "videoMetadata": {"fps": 5.0}}
    assert parts[1] == {"text": "watch this"}
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert answer.text == _answer_text()
    assert answer.model == "gemini-test-video"  # the reply's modelVersion
    assert (answer.usage.prompt_tokens, answer.usage.video_tokens) == (12000, 10700)
    assert (answer.usage.output_tokens, answer.usage.total_tokens) == (900, 12950)
    assert answer.usage.thoughts_tokens == 50


def test_the_endpoint_is_one_config_string() -> None:
    tape = Recorded(_recorded())
    other = GeminiAnalyser(
        api_key=SecretStr(KEY),
        model="m1",
        fps=2.0,
        endpoint="https://video.example/v1/{model}:watch",
        client=tape.client(),
    )
    other.analyse("https://www.youtube.com/watch?v=zXK42RMPKUY", "p")
    assert str(tape.requests[0].url) == "https://video.example/v1/m1:watch"
    assert tape.sent()["contents"][0]["parts"][0]["videoMetadata"] == {"fps": 2.0}


def test_an_api_error_is_an_analyser_error_with_the_status_and_no_key() -> None:
    tape = Recorded({"error": {"code": 403, "message": "video is private"}}, status=403)
    with pytest.raises(AnalyserError) as raised:
        _gemini(tape).analyse("https://www.youtube.com/watch?v=zXK42RMPKUY", "p")
    assert raised.value.status == 403
    assert "video is private" in str(raised.value)
    assert KEY not in str(raised.value)


def test_a_reply_with_no_text_is_an_analyser_error() -> None:
    empty: dict[str, Any] = {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}
    tape = Recorded(empty)
    with pytest.raises(AnalyserError):
        _gemini(tape).analyse("https://www.youtube.com/watch?v=zXK42RMPKUY", "p")


def test_gemini_without_a_key_names_the_setting() -> None:
    with pytest.raises(AnalyserError, match="GEMINI_API_KEY"):
        GeminiAnalyser(api_key=None, model="m", fps=5.0).analyse("u", "p")


# --- gaps --------------------------------------------------------------------------------


def _inventory(
    vid: str, *, tier: str = "A", category: str = "facts", **changes: Any
) -> ReferenceInventory:
    answer = parse_answer(_answer_text(), registry=REGISTRY)
    data = answer.model_dump()
    data.update(changes)
    return ReferenceInventory.from_answer(
        InventoryAnswer.model_validate(data),
        link=_link(vid, tier=tier, category=category),
        model="fake-video",
        fps=5.0,
        usage=gemini.Usage(prompt_tokens=1, video_tokens=1, output_tokens=1, total_tokens=2),
        analysed_on="2026-09-27",
    )


def _three() -> list[ReferenceInventory]:
    first = _inventory("zXK42RMPKUY")
    second = _inventory("S5j-2CWYYwM")
    # the third is Tier B explainer, uses glitch_text too but not screen_shake
    third_answer = parse_answer(_answer_text(), registry=REGISTRY).model_dump()
    third_answer["effects"] = [e for e in third_answer["effects"] if e["name"] != "screen_shake"]
    third_answer["transitions"] = [
        t for t in third_answer["transitions"] if t["name"] != "flash_white"
    ]
    third = _inventory("nBihHUlYOQk", tier="B", category="explainer", **third_answer)
    return [first, second, third]


def test_gaps_ranks_unregistered_items_by_reference_count_with_timestamped_links() -> None:
    text = gaps.report(_three())
    effects = text.index("## Unregistered effects")
    transitions = text.index("## Unregistered transitions")
    glitch, shake = text.index("glitch_text"), text.index("screen_shake")
    assert effects < glitch < shake < transitions
    assert "| `glitch_text` | 3 |" in text
    assert "| `screen_shake` | 2 |" in text
    assert "https://www.youtube.com/watch?v=zXK42RMPKUY&t=12s" in text
    assert "https://www.youtube.com/watch?v=S5j-2CWYYwM&t=21s" in text
    assert "| `flash_white` | 2 |" in text
    assert "stamp" not in text[effects:transitions]  # registered effects are not gaps


def _section(text: str, heading: str) -> str:
    """The report from `## <heading>` up to the next `## ` heading."""
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_gaps_keeps_tier_a_tier_b_and_facts_in_separate_tables() -> None:
    text = gaps.report(_three())
    facts_table = _section(text, "facts / Tier A")
    explainer_b = _section(text, "explainer / Tier B")
    assert "zXK42RMPKUY" in facts_table and "S5j-2CWYYwM" in facts_table
    assert "nBihHUlYOQk" not in facts_table
    assert "nBihHUlYOQk" in explainer_b and "zXK42RMPKUY" not in explainer_b
    assert "## explainer / Tier A" not in text  # no pooled or empty tables
    # layout and background shares of runtime, moving footage split by kind
    assert "full_footage 64%" in facts_table
    assert "moving_footage 64% (ai_generated 33%, stock 31%)" in facts_table
    assert "still_photo 27%" in facts_table
    # median clip length, shots and sound effects per 10 s
    assert "| 4.8 |" in facts_table and "| 1.3 |" in facts_table and "| 1.0 |" in facts_table
    assert "ESTIMATED" in text


def test_gaps_write_reads_every_inventory_json_in_the_folder(tmp_path: Path) -> None:
    for made in _three():
        (tmp_path / f"{made.video_id}.json").write_text(made.model_dump_json(indent=2), "utf-8")
    (tmp_path / "notes.txt").write_text("not an inventory", encoding="utf-8")
    path = gaps.write(tmp_path)
    assert path == tmp_path / "GAPS.md"
    text = path.read_text(encoding="utf-8")
    assert "3 inventories" in text and "glitch_text" in text


def test_gaps_on_an_empty_folder_says_so(tmp_path: Path) -> None:
    assert "no inventories" in gaps.write(tmp_path).read_text(encoding="utf-8")


# --- docs/references.md ------------------------------------------------------------------


def test_links_in_the_references_files_carry_tier_category_creator_and_title() -> None:
    """The operator's file (`docs/references.md`, Tier A and B explainer) plus the facts
    companion (`docs/reference/references-facts.md`) until he pastes it in."""
    links = links_in()
    by_id = {link.video_id: link for link in links}
    for vid in OPERATOR_LINKS.values():
        assert by_id[vid].category == "facts" and by_id[vid].tier == "A", vid
    dhruv = by_id["S5j-2CWYYwM"]
    assert dhruv.creator == "Dhruv Rathee Shorts"
    assert dhruv.title == "What Would Happen If the Sun Disappeared?"
    assert by_id["zXK42RMPKUY"].creator == "FactTechz"
    assert by_id["nBihHUlYOQk"].tier == "B" and by_id["nBihHUlYOQk"].category == "explainer"
    assert by_id["ATkSnL_CdLg"].tier == "A" and by_id["ATkSnL_CdLg"].category == "explainer"
    assert by_id["id00R-3OmJ0"].url == "https://www.youtube.com/watch?v=id00R-3OmJ0"
    assert len(links) == len(by_id) == 13
    # the operator's file alone has the seven explainer links; a missing file is skipped
    assert len(links_in(REPO / "docs" / "references.md")) == 7
    assert links_in(REPO / "docs" / "no-such-file.md") == []


def test_link_for_looks_the_url_up_and_the_flags_override(tmp_path: Path) -> None:
    found = link_for("https://youtube.com/shorts/S5j-2CWYYwM?si=x")
    assert (found.category, found.tier, found.creator) == ("facts", "A", "Dhruv Rathee Shorts")
    forced = link_for("https://youtu.be/S5j-2CWYYwM", category="science", tier="B")
    assert (forced.category, forced.tier) == ("science", "B")
    unknown = link_for("https://youtu.be/AAAAAAAAAAA", tmp_path / "none.md")
    assert (unknown.category, unknown.tier, unknown.creator) == ("unknown", "A", "")


# --- the command line --------------------------------------------------------------------


def _settings(**env: str) -> config.Settings:
    return config.Settings(_env_file=None, **env)  # pyright: ignore[reportCallIssue]


def test_the_cli_inventory_writes_the_json_through_the_analyser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake(_answer_text())
    code = cli.main(
        ["inventory", "https://youtube.com/shorts/zXK42RMPKUY", "--out", str(tmp_path)],
        analyser=fake,
        settings=_settings(),
    )
    assert code == 0
    assert (tmp_path / "zXK42RMPKUY.json").is_file()
    out = capsys.readouterr().out
    assert "tokens" in out and "zXK42RMPKUY.json" in out


def test_the_cli_all_reads_the_references_file(tmp_path: Path) -> None:
    references = tmp_path / "references.md"
    references.write_text(
        "## Facts — category `facts`, Tier A\n"
        '- https://youtube.com/shorts/zXK42RMPKUY — FactTechz, "Brain"\n'
        '- https://youtube.com/shorts/S5j-2CWYYwM — Dhruv Rathee Shorts, "Sun"\n',
        encoding="utf-8",
    )
    fake = _fake(AnalyserError("private", status=403), _answer_text())
    out = tmp_path / "inventory"
    code = cli.main(
        ["inventory", "--all", "--references", str(references), "--out", str(out)],
        analyser=fake,
        settings=_settings(),
    )
    assert code == 1  # one link failed
    assert not (out / "zXK42RMPKUY.json").exists()
    assert (out / "S5j-2CWYYwM.json").is_file()


def test_the_cli_without_a_key_names_the_setting_and_calls_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["inventory", "https://youtu.be/zXK42RMPKUY", "--out", str(tmp_path)],
        settings=_settings(),
    )
    assert code == 1
    assert "GEMINI_API_KEY" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_the_cli_builds_the_gemini_analyser_from_config() -> None:
    settings = _settings(
        GEMINI_API_KEY="g_x", REFERENCE_MODEL="gemini-test-video", REFERENCE_FPS="4"
    )
    analyser = cli.analyser_from(settings)
    assert isinstance(analyser, GeminiAnalyser)
    assert (analyser.model, analyser.fps) == ("gemini-test-video", 4.0)


def test_the_cli_gaps_writes_the_report(tmp_path: Path) -> None:
    for made in _three():
        (tmp_path / f"{made.video_id}.json").write_text(made.model_dump_json(indent=2), "utf-8")
    assert cli.main(["gaps", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "GAPS.md").is_file()
