"""The image generator: ladder rung 2 (decisions 5.5, 4.2, 5.6, 12.1, 13.1).

When neither query found anything - or when the planner asked for generation on a
concept beat - the step makes the picture instead of finding it. What is generated is
never a free choice: the prompt is built by code from one of two templates, picked by
what the beat `depicts`, with the look words taken from the style's front matter
(`photo_look`, `illustration_look`, `scene_mood`, `scene_lighting`), never from here:

- `scene` - a scene, an environment, an unnamed person - is the photoreal pattern,
  with "no faces clearly visible" appended only when no person is intended, so a
  "vintage street" reads as a photograph and a generic child may have a face (4.2).
- `named_entity` - a specific named person, product or org - is the illustration
  pattern, `clearly stylised, not a photograph`, always. That is the one 4.2 ban, and
  gate T9 fails a generated named entity rendered photoreal (`rights.completeness`).

Both end in "no text, no watermarks, no logos": text inside a generated image is
never trusted (9.3 draws labels in code), and every image is asked for at 9:16.

`GeminiImageGenerator` is one direct REST call (13.1: no SDK, no n8n bridge) to
`IMAGE_GEN_ENDPOINT` with `IMAGE_GEN_MODEL`, so switching provider or model is an
`.env` edit. Each generated image is one `gemini` ledger row per image, checked
against the hard cap before the call so a refused call is never billed (11.3).
`FakeImageGenerator` (12.1) writes a solid 1080x1920 PNG with the prompt burned in.

`Generating` is the per-job bookkeeping around whichever generator is configured:
the style's `budget.gen_max_per_short` as the ceiling (the cap sends the beat on to
rung 3, it never fails the job), the generated file cached under `work/assets/` by
sha256(prompt + model) so a plan retry or a re-render generates nothing again (5.6),
and one retry on a generator error before "nothing generated". Nothing here trades
quality for cost: cost never skips a beat (11.3).
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import re
import textwrap
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from io import BytesIO
from math import gcd
from pathlib import Path
from typing import Self

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import SecretStr

from shortsmith.assets.base import media_type
from shortsmith.assets.http import SUFFIX, items
from shortsmith.assets.http import field as json_field
from shortsmith.assets.http import text as json_text
from shortsmith.contracts import Beat, Depicts, Generated, Render
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.styles import StyleSpec

PROVIDER = "gemini"
STEP = "sourcing"
DEFAULT_MODEL = "gemini-2.5-flash-image"
# 5.5: the endpoint is a config string; `{model}` is filled in with `IMAGE_GEN_MODEL`.
DEFAULT_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
TIMEOUT_S = 120.0
SIZE = (1080, 1920)  # 5.5: always 9:16, always the frame
MAX_BYTES = 15 * 1024 * 1024
ATTEMPTS = 2  # 5.5: the call, then one retry, then "nothing generated"

# 5.5: appended to every prompt - text in a generated image is never trusted (9.3).
TAIL = "no text, no watermarks, no logos"
NO_FACES = "no faces clearly visible"
# 021 / 9.3: a labelled diagram's base carries no labels either; `infographics` draws
# them in code over it, so the generator is told twice, in the words 5.5 asks for.
DIAGRAM_TAIL = "no text, no labels"
DIAGRAM_KIND = "infographic"

# 5.5 / 4.2: a person is intended when the scene says so, and then faces stay in.
PERSON_WORDS = frozenset(
    [
        "person", "people", "man", "men", "woman", "women", "boy", "boys", "girl", "girls",
        "child", "children", "kid", "kids", "baby", "family", "crowd", "worker", "workers",
        "farmer", "farmers", "student", "students", "teacher", "soldier", "soldiers",
        "doctor", "nurse", "villager", "villagers", "protester", "protesters", "portrait",
        "face", "faces", "he", "she", "his", "her", "him",
    ]
)  # fmt: skip
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


class GeneratorError(RuntimeError):
    """Nothing was generated (an API error, a reply with no image, a missing key).
    The step notes it and the ladder moves on to rung 3; the job never fails for it."""


@dataclass(frozen=True)
class GeneratedImage:
    """One generator call's answer: the image bytes and the model that made them."""

    body: bytes
    model: str


@dataclass(frozen=True)
class GeneratedAsset:
    """What the step stores for a generated beat: the file and its 5.4 record."""

    path: Path
    generated: Generated


class ImageGenerator(ABC):
    """One image per call at `size`, 9:16 (5.5). A generator that cannot answer raises
    `GeneratorError`; it never returns a placeholder."""

    model: str

    def bind(self, job: Job) -> Self:
        """The job a real generator writes its ledger row against; the fake ignores it."""
        return self

    @abstractmethod
    def generate(self, prompt: str, size: tuple[int, int]) -> GeneratedImage: ...


# --- the two prompt templates (5.5, 4.2) -------------------------------------------------


@dataclass(frozen=True)
class Prompt:
    """The built prompt with what it will produce, for the rights row (5.4)."""

    text: str
    render: Render
    depicts: Depicts


def wants_person(scene: str) -> bool:
    """Whether the scene asks for a person, so the faces stay in (5.5)."""
    return bool({w.lower() for w in _WORD.findall(scene)} & PERSON_WORDS)


def depicts_of(beat: Beat) -> Depicts:
    """What the beat depicts: the planner's own label, else a named entity on an
    `entity` beat and a scene on any other (4.2)."""
    if beat.depicts is not None:
        return beat.depicts
    return "named_entity" if beat.subject_kind == "entity" else "scene"


def is_diagram_base(beat: Beat) -> bool:
    """Whether the beat's asset is the base of a labelled diagram (9.3, ticket 021):
    generated label-free, shown only under the code-rendered labels."""
    return beat.kind == DIAGRAM_KIND


def build_prompt(beat: Beat, spec: StyleSpec) -> Prompt:
    """The 5.5 template the beat's `depicts` picks, in the style's own look words."""
    scene = beat.query.strip()
    look = spec.broll
    tail = f"{TAIL}, {DIAGRAM_TAIL}" if is_diagram_base(beat) else TAIL
    if depicts_of(beat) == "named_entity":
        return Prompt(
            f"{look.illustration_look}, vertical 9:16, illustration of {scene}, "
            f"clearly stylised, not a photograph, {tail}",
            "illustration",
            "named_entity",
        )
    faces = "" if wants_person(scene) else f"{NO_FACES}, "
    return Prompt(
        f"{look.photo_look} photograph, vertical 9:16: {scene}, "
        f"{look.scene_mood}, {look.scene_lighting}, realistic, {faces}{tail}",
        "photoreal",
        "scene",
    )


# --- the fake (12.1) ---------------------------------------------------------------------


class FakeImageGenerator(ImageGenerator):
    """A solid 1080x1920 PNG with the prompt burned in, so a local run and the smoke
    exercise rung 2 with no key and no network. `nothing_for` refuses any prompt
    containing one of those words and `fail_times` the first N calls, for the retry
    and ladder tests; `calls` counts them."""

    def __init__(
        self,
        *,
        model: str = "fake",
        nothing_for: Iterable[str] = (),
        fail_times: int = 0,
    ) -> None:
        self.model = model
        self.nothing_for = frozenset(nothing_for)
        self.fail_times = fail_times
        self.calls = 0

    def generate(self, prompt: str, size: tuple[int, int]) -> GeneratedImage:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise GeneratorError(f"the fake generator was asked to fail (call {self.calls})")
        if any(word in prompt for word in self.nothing_for):
            raise GeneratorError(f"the fake generator has nothing for {prompt[:60]!r}")
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        image = Image.new("RGB", size, tuple(digest[:3]))
        font = ImageFont.load_default(size=max(16, size[0] // 24))
        drawn = "\n".join(textwrap.wrap(prompt, width=28)[:12])
        ImageDraw.Draw(image).text((40, 40), drawn, fill=(255, 255, 255), font=font)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return GeneratedImage(buffer.getvalue(), self.model)


# --- the Gemini adapter (5.5, 13.1) ------------------------------------------------------


def aspect(size: tuple[int, int]) -> str:
    """`(1080, 1920)` as the API's `"9:16"`."""
    width, height = size
    divisor = gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


def request_body(prompt: str, size: tuple[int, int]) -> dict[str, object]:
    """The one JSON body: the prompt, an image answer and the asked-for aspect."""
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect(size)},
        },
    }


def parse_reply(body: object, model: str) -> GeneratedImage:
    """The first inline image of the first candidate, decoded and checked to be one."""
    for candidate in items(body, "candidates"):
        for part in items(json_field(candidate, "content"), "parts"):
            inline = json_field(part, "inlineData") or json_field(part, "inline_data")
            data = json_text(json_field(inline, "data"))
            if not data:
                continue
            try:
                image = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                raise GeneratorError("the generated image is not base64") from None
            if media_type(image) is None:
                raise GeneratorError("what came back is not an image")
            return GeneratedImage(image, json_text(json_field(body, "modelVersion")) or model)
    raise GeneratorError("the reply carried no image")


class GeminiImageGenerator(ImageGenerator):
    """One direct REST call per image (13.1), `{model}` filled into the endpoint."""

    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        api_key: SecretStr | None,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self._ledger = ledger
        self._api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self._client = client
        self._timeout_s = timeout_s
        self._job: Job | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        return bound

    def generate(self, prompt: str, size: tuple[int, int]) -> GeneratedImage:
        job = self._job
        if job is None:
            raise GeneratorError("GeminiImageGenerator has no job: bind(job) before calling")
        if self._api_key is None:
            raise GeneratorError("IMAGE_GEN=gemini needs GEMINI_API_KEY in .env")
        book = self._ledger()
        book.check_before_call(job, STEP, book.estimate(PROVIDER, {"images": 1}))
        response = self._post(request_body(prompt, size))
        if response.status_code >= 400:
            raise GeneratorError(
                f"the image generator answered {response.status_code}: {_error_text(response)}"
            )
        if len(response.content) > MAX_BYTES:
            raise GeneratorError(
                f"the generated image is {len(response.content) / 1024 / 1024:.1f} MB, "
                f"over the {MAX_BYTES // 1024 // 1024} MB limit"
            )
        try:
            body: object = response.json()
        except ValueError:
            raise GeneratorError("the image generator did not answer with JSON") from None
        made = parse_reply(body, self.model)
        book.record(job, STEP, PROVIDER, made.model, {"images": 1})
        return made

    def _post(self, body: Mapping[str, object]) -> httpx.Response:
        url = self.endpoint.format(model=self.model)
        headers = {"x-goog-api-key": self._api_key.get_secret_value() if self._api_key else ""}
        try:
            client = self._client
            if client is not None:
                return client.post(url, json=body, headers=headers)
            with httpx.Client(timeout=self._timeout_s) as owned:
                return owned.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise GeneratorError(f"the image generator could not be reached: {exc}") from None


def _error_text(response: httpx.Response) -> str:
    """The API's own words from its error body; never the key, never a stack."""
    try:
        body: object = response.json()
    except ValueError:
        return response.text[:500]
    message = json_field(json_field(body, "error"), "message")
    return str(message)[:500] if message is not None else response.text[:500]


# --- the per-job bookkeeping (5.5, 5.6, 11.3) --------------------------------------------


def gen_key(prompt: str, model: str) -> str:
    """5.6: the generated file's cache name, sha256 of the prompt and the model."""
    return hashlib.sha256(prompt.encode("utf-8") + model.encode("utf-8")).hexdigest()


@dataclass
class Generating:
    """The generator as the step uses it: the file cache, the cap and the one retry.

    `make` returns the beat's generated asset, or None when nothing was generated -
    no generator configured (`IMAGE_GEN=none`), the style's `gen_max_per_short` spent,
    or the generator could not answer. The step then carries on down the ladder to
    rung 3; a beat is never left blank and the job never fails for a generator."""

    generator: ImageGenerator | None = None
    spec: StyleSpec | None = None
    max_images: int = 0
    images: int = 0
    capped: bool = False
    notes: list[str] = field(default_factory=lambda: [])

    @property
    def model(self) -> str:
        return self.generator.model if self.generator is not None else ""

    def make(self, beat: Beat, cache: Path) -> GeneratedAsset | None:
        generator, spec = self.generator, self.spec
        if generator is None or spec is None:
            return None
        prompt = build_prompt(beat, spec)
        record = Generated(
            model=generator.model,
            prompt=prompt.text,
            render=prompt.render,
            depicts=prompt.depicts,
        )
        folder = cache / gen_key(prompt.text, generator.model)
        cached = _cached(folder)
        if cached is not None:  # 5.6: a retry or a re-render generates nothing again
            return GeneratedAsset(cached, record)
        if self.max_images and self.images >= self.max_images:
            if not self.capped:
                self.capped = True
                self.notes.append(
                    f"generation: the style's gen_max_per_short ({self.max_images}) is spent; "
                    "the remaining beats fall to the ladder"
                )
            return None
        made = self._call(beat, prompt.text)
        if made is None:
            return None
        self.images += 1
        folder.mkdir(parents=True, exist_ok=True)
        kind = media_type(made.body)
        path = folder / f"image{SUFFIX.get(kind or '', '.png')}"
        path.write_bytes(made.body)
        return GeneratedAsset(path, record.model_copy(update={"model": made.model}))

    def _call(self, beat: Beat, prompt: str) -> GeneratedImage | None:
        """The call and its one retry (5.5); the last error is a job-log note."""
        assert self.generator is not None
        last: GeneratorError | None = None
        for _ in range(ATTEMPTS):
            try:
                return self.generator.generate(prompt, SIZE)
            except GeneratorError as exc:
                last = exc
        self.notes.append(f"generation: {last}; nothing generated for {beat.id}")
        return None


def _cached(folder: Path) -> Path | None:
    return next((path for path in sorted(folder.glob("image.*")) if path.is_file()), None)
