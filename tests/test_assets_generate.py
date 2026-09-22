"""assets.generate: the image generator, ladder rung 2 (5.5, 5.6, 4.2, 12.1, 13.1).

The two code-built prompt templates and the `depicts` that picks them; the fake that
writes a solid 1080x1920 PNG with the prompt burned in; the Gemini adapter's one
direct REST call on the recorded request/response in `tests/fixtures/gemini/`, its
ledger row and its hard-cap check; and `Generating`, the per-job bookkeeping: the
style's `gen_max_per_short` as the ceiling, the sha256(prompt + model) file cache and
one retry before "nothing generated". No network, no key.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr

from shortsmith import jobs, render, styles
from shortsmith.assets import generate as gen
from shortsmith.assets.generate import (
    FakeImageGenerator,
    GeminiImageGenerator,
    GeneratedImage,
    Generating,
    GeneratorError,
    ImageGenerator,
)
from shortsmith.contracts import Beat
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices

GEMINI = Path(__file__).parent / "fixtures" / "gemini"
KEY = "gemini-test-key-not-a-real-one"
PRICES = Prices({"gemini": {"images": 4.0}})
SPEC = styles.load_all(render.registry())["explainer"]
LOOK = SPEC.broll


def _beat(
    subject: str = "concept",
    *,
    query: str = "a vintage street at dusk",
    depicts: str | None = None,
) -> Beat:
    return Beat.model_validate(
        {
            "id": "b01", "start": 0.0, "end": 2.0, "mode": "pip", "kind": "photo",
            "motion": "ken_burns_in", "subject_kind": subject, "depicts": depicts,
            "query": query, "query_fallback": "street", "source_intent": "generate",
        }  # fmt: skip
    )


# --- the two prompt templates (5.5, 4.2) -------------------------------------------------


def test_the_scene_template_is_the_photoreal_archive_pattern() -> None:
    prompt = gen.build_prompt(_beat(depicts="scene"), SPEC)
    assert prompt.text == (
        f"{LOOK.photo_look} photograph, vertical 9:16: a vintage street at dusk, "
        f"{LOOK.scene_mood}, {LOOK.scene_lighting}, realistic, "
        f"{gen.NO_FACES}, {gen.TAIL}"
    )
    assert (prompt.render, prompt.depicts) == ("photoreal", "scene")


def test_a_scene_with_a_person_in_it_keeps_the_faces() -> None:
    """5.5: "no faces clearly visible" only when no person is intended (4.2 wants a
    photoreal generic child for "young Lincoln")."""
    prompt = gen.build_prompt(_beat(query="an old farmer walking home", depicts="scene"), SPEC)
    assert gen.NO_FACES not in prompt.text
    assert prompt.text.endswith(f"realistic, {gen.TAIL}")
    assert prompt.render == "photoreal"


def test_the_named_entity_template_is_illustration_only() -> None:
    """4.2: a named person or product is never generated as if it were a photograph."""
    prompt = gen.build_prompt(_beat("entity", query="Abraham Lincoln as a boy"), SPEC)
    assert prompt.text == (
        f"{LOOK.illustration_look}, vertical 9:16, illustration of Abraham Lincoln as a boy, "
        f"clearly stylised, not a photograph, {gen.TAIL}"
    )
    assert (prompt.render, prompt.depicts) == ("illustration", "named_entity")


def test_an_entity_beat_the_planner_did_not_label_is_a_named_entity() -> None:
    assert gen.build_prompt(_beat("entity"), SPEC).depicts == "named_entity"
    assert gen.build_prompt(_beat("concept"), SPEC).depicts == "scene"


def test_the_look_strings_come_from_the_style_front_matter() -> None:
    hitech = styles.load_all(render.registry())["hitech"]
    prompt = gen.build_prompt(_beat("entity"), hitech)
    assert prompt.text.startswith(hitech.broll.illustration_look)
    assert hitech.broll.illustration_look != LOOK.illustration_look


def test_every_prompt_forbids_text_watermarks_and_logos() -> None:
    for beat in (_beat("concept"), _beat("entity")):
        assert gen.build_prompt(beat, SPEC).text.endswith(gen.TAIL)


# --- the fake (12.1) ---------------------------------------------------------------------


def test_the_fake_writes_a_9_16_png_with_the_prompt_on_it(tmp_path: Path) -> None:
    made = FakeImageGenerator().generate("a vintage street at dusk", gen.SIZE)
    assert isinstance(made, GeneratedImage)
    path = tmp_path / "made.png"
    path.write_bytes(made.body)
    with Image.open(path) as image:
        assert image.size == (1080, 1920)
        assert image.format == "PNG"


def test_the_fake_can_answer_nothing_for_a_prompt() -> None:
    fake = FakeImageGenerator(nothing_for={"street"})
    with pytest.raises(GeneratorError):
        fake.generate("a vintage street at dusk", gen.SIZE)
    assert fake.calls == 1
    assert fake.generate("a red door", gen.SIZE).model == "fake"


# --- the Gemini adapter (5.5, 13.1) ------------------------------------------------------


class Recorded:
    """A transport answering one recorded body, recording every request it saw."""

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


def _png(size: tuple[int, int] = (1080, 1920)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (30, 40, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def _reply(name: str = "generate", *, body: bytes | None = None) -> dict[str, Any]:
    """The recorded reply with its image bytes filled in: no media file is committed,
    so the fixture carries the shape and the test supplies the PNG."""
    recorded: dict[str, Any] = json.loads((GEMINI / f"{name}.json").read_text(encoding="utf-8"))
    encoded = base64.b64encode(body if body is not None else _png()).decode("ascii")
    for part in recorded["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            part["inlineData"]["data"] = encoded
    return recorded


@pytest.fixture
def job(tmp_path: Path) -> jobs.Job:
    return jobs.create(tmp_path, style="explainer", style_note="explainer")


def _book(hard: float | None = None) -> Ledger:
    return Ledger(PRICES, Caps(per_job=None, hard=hard, per_day=500))


def _gemini(
    tape: Recorded, job: jobs.Job, *, book: Ledger | None = None, model: str = "gemini-test-image"
) -> ImageGenerator:
    ledger = book or _book()
    return GeminiImageGenerator(
        lambda: ledger, api_key=SecretStr(KEY), model=model, client=tape.client()
    ).bind(job)


def test_gemini_posts_the_prompt_to_the_configured_endpoint_and_model(job: jobs.Job) -> None:
    tape = Recorded(_reply())
    _gemini(tape, job).generate("a vintage street at dusk", gen.SIZE)
    request = tape.requests[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-test-image:generateContent"
    )
    assert request.headers["x-goog-api-key"] == KEY
    expected: dict[str, Any] = json.loads((GEMINI / "request.json").read_text(encoding="utf-8"))
    expected["contents"][0]["parts"][0]["text"] = "a vintage street at dusk"
    assert tape.sent() == expected


def test_gemini_asks_for_the_9_16_the_size_describes(job: jobs.Job) -> None:
    tape = Recorded(_reply())
    _gemini(tape, job).generate("p", (1080, 1920))
    assert tape.sent()["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"


def test_the_endpoint_is_one_config_string(job: jobs.Job) -> None:
    """5.5: switching providers is an `.env` edit, not code."""
    tape = Recorded(_reply())
    ledger = _book()
    other = GeminiImageGenerator(
        lambda: ledger,
        api_key=SecretStr(KEY),
        model="m1",
        endpoint="https://images.example/v1/{model}:make",
        client=tape.client(),
    ).bind(job)
    other.generate("p", gen.SIZE)
    assert str(tape.requests[0].url) == "https://images.example/v1/m1:make"


def test_gemini_returns_the_inline_image_bytes_and_the_model_that_made_them(
    job: jobs.Job,
) -> None:
    body = _png((1080, 1920))
    tape = Recorded(_reply(body=body))
    made = _gemini(tape, job).generate("p", gen.SIZE)
    assert made.body == body
    assert made.model == "gemini-test-image-001"  # the reply's `modelVersion`


def test_every_generated_image_is_one_gemini_ledger_row(job: jobs.Job) -> None:
    tape = Recorded(_reply())
    _gemini(tape, job).generate("p", gen.SIZE)
    (row,) = jobs.load(job.path).record.cost
    assert (row.step, row.provider, row.model) == ("sourcing", "gemini", "gemini-test-image-001")
    assert (row.units, row.inr) == ({"images": 1.0}, 4.0)


def test_the_hard_cap_is_checked_before_the_call_so_it_is_never_billed(job: jobs.Job) -> None:
    tape = Recorded(_reply())
    with pytest.raises(BudgetExceeded):
        _gemini(tape, job, book=_book(hard=2.0)).generate("p", gen.SIZE)
    assert tape.requests == []
    assert jobs.load(job.path).record.cost == []


def test_an_api_error_is_a_generator_error_with_the_api_words_and_no_key(
    job: jobs.Job,
) -> None:
    tape = Recorded({"error": {"code": 429, "message": "quota exhausted"}}, status=429)
    with pytest.raises(GeneratorError) as raised:
        _gemini(tape, job).generate("p", gen.SIZE)
    assert "429" in str(raised.value) and "quota exhausted" in str(raised.value)
    assert KEY not in str(raised.value)
    assert jobs.load(job.path).record.cost == []


def test_a_reply_with_no_image_in_it_is_a_generator_error(job: jobs.Job) -> None:
    tape = Recorded({"candidates": [{"content": {"parts": [{"text": "I cannot draw that"}]}}]})
    with pytest.raises(GeneratorError):
        _gemini(tape, job).generate("p", gen.SIZE)


def test_a_reply_whose_image_is_not_an_image_is_a_generator_error(job: jobs.Job) -> None:
    tape = Recorded(_reply(body=b"not a png at all"))
    with pytest.raises(GeneratorError):
        _gemini(tape, job).generate("p", gen.SIZE)


def test_gemini_without_a_key_says_which_setting_is_missing(job: jobs.Job) -> None:
    ledger = _book()
    generator = GeminiImageGenerator(lambda: ledger, api_key=None).bind(job)
    with pytest.raises(GeneratorError) as raised:
        generator.generate("p", gen.SIZE)
    assert "GEMINI_API_KEY" in str(raised.value)


# --- the per-job bookkeeping (5.5, 5.6, 11.3) --------------------------------------------


def _generating(cap: int = 8, **overrides: Any) -> Generating:
    return Generating(generator=FakeImageGenerator(**overrides), spec=SPEC, max_images=cap)


def test_a_generated_beat_carries_its_prompt_model_render_and_depicts(tmp_path: Path) -> None:
    made = _generating().make(_beat("entity"), tmp_path)
    assert made is not None
    assert made.path.is_file()
    assert (made.generated.model, made.generated.render) == ("fake", "illustration")
    assert made.generated.depicts == "named_entity"
    assert LOOK.illustration_look in made.generated.prompt


def test_generation_is_cached_by_prompt_and_model(tmp_path: Path) -> None:
    generating = _generating()
    first = generating.make(_beat(), tmp_path)
    second = generating.make(_beat(), tmp_path)
    assert first is not None and second is not None
    assert first.path == second.path
    assert generating.images == 1  # the second beat re-generated nothing
    digest = gen.gen_key(first.generated.prompt, "fake")
    assert first.path.parent.name == digest


def test_the_ninth_generation_in_a_short_is_refused_by_the_cap(tmp_path: Path) -> None:
    """5.5: `gen_max_per_short` hit means the ladder moves on to rung 3, not a failure."""
    generating = _generating(cap=8)
    made = [generating.make(_beat(query=f"scene {i}"), tmp_path) for i in range(1, 10)]
    assert [m is not None for m in made] == [True] * 8 + [False]
    assert generating.images == 8
    assert [n for n in generating.notes if "gen_max_per_short" in n]


def test_one_retry_on_an_error_then_nothing_generated(tmp_path: Path) -> None:
    generating = _generating(fail_times=1)
    assert generating.make(_beat(), tmp_path) is not None
    assert generating.notes == []

    giving_up = _generating(fail_times=5)
    assert giving_up.make(_beat(), tmp_path / "second") is None
    assert giving_up.images == 0
    assert [n for n in giving_up.notes if "nothing generated" in n]
    generator = giving_up.generator
    assert isinstance(generator, FakeImageGenerator) and generator.calls == 2


def test_no_generator_configured_generates_nothing(tmp_path: Path) -> None:
    assert Generating().make(_beat(), tmp_path) is None
