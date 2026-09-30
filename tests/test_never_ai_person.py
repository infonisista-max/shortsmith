"""100: never AI for a named real person, on every path.

The guard lives inside `Generating.make`, the single door every caller goes through: a
beat that depicts a named person (099's `named_person`, or today's `named_entity` on a
beat that is not a `concept`) is never generated, whatever the caller - the opening,
a concept beat asking to be generated, the still ladder's fallback, a replaced beat.
The refusal is a job-log note, never an error; the caller carries on down its ladder.
A named place, era or object (a `concept` beat depicting a `named_entity`) may still be
generated as the last rung.
"""

from __future__ import annotations

from pathlib import Path

from shortsmith import assets
from shortsmith.assets import clips
from shortsmith.assets import generate as gen
from shortsmith.contracts import Beat
from tests.test_assets import (
    EXPLAINER,
    SPEC,
    _beat,  # pyright: ignore[reportPrivateUsage]
    _run,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_sourcing_replacement import (
    _run as _run_replaced,  # pyright: ignore[reportPrivateUsage]
)


def _generating() -> tuple[assets.Generating, assets.FakeImageGenerator]:
    generator = assets.FakeImageGenerator()
    return assets.Generating(generator=generator, spec=SPEC, max_images=8), generator


def _person_099(beat: Beat) -> Beat:
    """099's split value, `named_person`, on a beat (no validation: 099 adds it to the
    contract; the guard already reads it)."""
    return beat.model_copy(update={"depicts": "named_person"})


def _refusals(generating: assets.Generating) -> list[str]:
    return [note for note in generating.notes if "named person" in note]


# --- the door ------------------------------------------------------------------------------


def test_an_entity_beat_depicting_a_named_entity_is_never_generated(tmp_path: Path) -> None:
    generating, generator = _generating()
    beat = _beat(1, "entity", query="Neem Karoli Baba portrait", depicts="named_entity")
    assert generating.make(beat, tmp_path) is None
    assert generating.make(beat, tmp_path, force=True) is None
    assert (generator.calls, generating.images) == (0, 0)
    assert _refusals(generating)  # logged, not raised


def test_099s_named_person_is_never_generated_whatever_its_subject_kind(
    tmp_path: Path,
) -> None:
    generating, generator = _generating()
    beat = _person_099(_beat(1, "concept", query="King Saud in 1953"))
    assert gen.names_a_person(beat)
    assert generating.make(beat, tmp_path, force=True) is None
    assert generator.calls == 0


def test_a_named_place_era_or_object_may_still_be_generated(tmp_path: Path) -> None:
    generating, generator = _generating()
    for i, query in enumerate(("Pangea, the supercontinent", "the 1950s oil boom"), 1):
        beat = _beat(i, "concept", query=query, depicts="named_entity")
        assert not gen.names_a_person(beat)
        assert generating.make(beat, tmp_path) is not None
    assert generating.make(_beat(3, "concept", depicts="scene"), tmp_path) is not None
    assert generator.calls == 3 and _refusals(generating) == []


# --- every caller ----------------------------------------------------------------------------


def test_an_opening_named_person_falls_to_the_gradient_not_ai(tmp_path: Path) -> None:
    """The opening forced generation past the cap (055); for a named person it now
    falls to the gradient, as 096 does."""
    generating, generator = _generating()
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(1, "entity", query="Neem Karoli Baba portrait", depicts="named_entity"),
             _beat(2, "concept")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": empty}, generating=generating,
                    spec=EXPLAINER)  # fmt: skip
    first = manifest.beats[0]
    assert (first.beat_id, first.treatment, first.asset_id) == ("b01", "gradient", None)
    assert generator.calls == 1  # b02, the concept, only
    assert _refusals(generating)


def test_a_concept_beat_asking_for_generation_of_a_named_person_is_searched(
    tmp_path: Path,
) -> None:
    generating, generator = _generating()
    web = assets.FakeImageSource("web")
    beat = _person_099(_beat(1, "concept", intent="generate", query="King Saud in 1953"))
    manifest = _run(tmp_path, [beat], sources={"web": web}, generating=generating)
    assert generator.calls == 0 and web.searches == 1
    assert manifest.assets[0].origin == "web"


def test_the_still_ladder_never_falls_to_ai_for_a_named_person(tmp_path: Path) -> None:
    """Nothing found: the real photo of that person already shown (rung 3), else the
    gradient; never rung 2."""
    generating, generator = _generating()
    web = assets.FakeImageSource("web", nothing_for={"Baba at the temple", "Baba 2"})
    beats = [_beat(1, "concept"), _beat(2, "concept"),
             _beat(3, "entity", query="Neem Karoli Baba portrait", depicts="named_entity"),
             _beat(4, "entity", query="Baba at the temple", fallback="Baba 2",
                   depicts="named_entity", asset="a4")]  # fmt: skip
    manifest = _run(tmp_path, beats, sources={"web": web}, generating=generating)
    fourth = manifest.beats[3]
    assert (fourth.fallback_rung, fourth.asset_id) == (3, "a3")  # Baba's real photo
    assert generator.calls == 0

    alone, alone_generator = _generating()
    empty = assets.FakeImageSource("web", nothing_found=True)
    beats = [_beat(1, "concept"), _beat(2, "concept"),
             _beat(3, "entity", query="Neem Karoli Baba portrait", depicts="named_entity")]
    manifest = _run(tmp_path / "second", beats, sources={"web": empty}, generating=alone)
    assert manifest.beats[2].treatment == "gradient"
    assert alone_generator.calls == 2  # the two concepts, never the person
    assert _refusals(alone)


def test_a_replaced_named_person_is_never_generated(tmp_path: Path) -> None:
    generating, generator = _generating()
    beat = _person_099(_beat(1, "concept", query="King Saud in 1953", depicts="scene"))
    no_clips = {"pexels": clips.FakeClipSource("pexels", nothing_found=True)}
    manifest = _run_replaced(tmp_path, [beat], replaced=frozenset({"b01"}),
                             generating=generating, clips_by_name=no_clips)  # fmt: skip
    assert manifest.beats[0].treatment == "gradient"
    assert generator.calls == 0 and _refusals(generating)
