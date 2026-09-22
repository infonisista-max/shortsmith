"""rights: `out/rights.json` in the 5.4 shape, the derived `out/credits.md` with the
AI-disclosure line, and the T9 completeness rules (5.4, 4.2; ticket 016)."""

from __future__ import annotations

import json
from pathlib import Path

from shortsmith import rights
from shortsmith.contracts import (
    AssetManifest,
    AssetRecord,
    Beat,
    BeatAsset,
    CutPlan,
    Finale,
    Generated,
    Hook,
    PicturePlan,
    RightsRow,
    Span,
)

STAMP = "2026-09-22T12:00:00+00:00"


def _record(asset_id: str, origin: str = "web", **extra: object) -> AssetRecord:
    data: dict[str, object] = {
        "id": asset_id,
        "origin": origin,
        "source_url": f"https://images.example.org/{asset_id}.jpg" if origin != "owner_supplied"
        and origin != "generated" else "",
        "page_url": f"https://www.example.org/wiki/{asset_id}" if origin == "web" else "",
        "licence": "owner" if origin == "owner_supplied" else "unknown",
        "author": None,
        "file": f"work/assets/{asset_id}.png",
        "sha256": "0" * 64,
        "width": 1600,
        "height": 900,
        "fetched_at": STAMP,
    }
    data.update(extra)
    return AssetRecord.model_validate(data)


def _beat_asset(beat_id: str, asset_id: str | None, rung: int = 0) -> BeatAsset:
    return BeatAsset(
        beat_id=beat_id,
        asset_id=asset_id,
        treatment="card" if asset_id else "gradient",
        fallback_rung=rung,
    )


def _plan(*beats: tuple[str, str, str | None], cards: tuple[str, ...] = ()) -> PicturePlan:
    built = [
        Beat.model_validate({"id": bid, "start": float(i), "end": float(i + 1), "mode": "off",
                             "kind": kind, "asset_id": asset})  # fmt: skip
        for i, (bid, kind, asset) in enumerate(beats)
    ]
    return PicturePlan(
        prompt_version="t",
        cut=CutPlan(keep=[Span(start=0.0, end=float(len(built)))]),
        beats=built,
        hook=Hook(title="t", cold_open_span=Span(start=0.0, end=1.0), original_position="drop",
                  card_asset_ids=list(cards)),  # fmt: skip
        finale=Finale(beat_id=built[-1].id, text="t"),
        title="t",
        description="t",
    )


def _manifest(records: list[AssetRecord], beats: list[BeatAsset],
              aliases: dict[str, str | None] | None = None) -> AssetManifest:  # fmt: skip
    return AssetManifest(assets=records, beats=beats, aliases=aliases or {}, runtime_s=3.0,
                         rescued_max=1)  # fmt: skip


GEN_SCENE = Generated(model="gen", prompt="a street at dusk", render="photoreal", depicts="scene")


# --- rows ---------------------------------------------------------------------------------


def test_one_row_per_unique_asset_with_every_beat_that_shows_it() -> None:
    plan = _plan(("b01", "hook_cards", "a1"), ("b02", "photo", "a1"), ("b03", "card", "a2"),
                 ("b04", "photo", "a9"), ("b05", "finale", "a1"), cards=("a1", "a2"))  # fmt: skip
    manifest = _manifest(
        [_record("a1", "commons"), _record("a2")],
        [_beat_asset("b02", "a1"), _beat_asset("b03", "a2"), _beat_asset("b04", "a1", 3)],
        {"a1": "a1", "a2": "a2", "a9": "a1"},
    )
    rows = rights.rows(manifest, plan)
    assert [r.id for r in rows] == ["a1", "a2"]
    assert rows[0].beat_ids == ["b01", "b02", "b04", "b05"]
    assert rows[1].beat_ids == ["b03"]


def test_rows_carry_the_5_4_shape() -> None:
    plan = _plan(("b01", "photo", "a1"))
    manifest = _manifest([_record("a1")], [_beat_asset("b01", "a1")])
    (row,) = rights.rows(manifest, plan)
    assert set(RightsRow.model_fields) == {
        "id", "beat_ids", "kind", "origin", "source_url", "page_url", "licence", "author",
        "generated", "judge", "file", "sha256", "width", "height", "fetched_at",
    }  # fmt: skip
    assert (row.kind, row.origin, row.licence) == ("image", "web", "unknown")


def test_write_regenerates_rights_and_credits(tmp_path: Path) -> None:
    plan = _plan(("b01", "photo", "a1"), ("b02", "card", "u1"), ("b03", "photo", "g1"))
    manifest = _manifest(
        [_record("a1", author="Jane Doe"), _record("u1", "owner_supplied"),
         _record("g1", "generated", generated=GEN_SCENE)],
        [_beat_asset("b01", "a1"), _beat_asset("b02", "u1"), _beat_asset("b03", "g1", 2)],
    )  # fmt: skip
    out = tmp_path / "out"
    (out).mkdir()
    (out / "credits.md").write_text("hand edit", encoding="utf-8")
    rights.write(tmp_path, manifest, plan)
    rows = json.loads((out / "rights.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == ["a1", "u1", "g1"]
    credits = (out / "credits.md").read_text(encoding="utf-8")
    assert credits == (
        "Photo: Jane Doe via https://www.example.org/wiki/a1\n"
        "\n"
        "Some scenes are AI-generated illustrations\n"
    )


# --- credits and disclosure (5.4) -----------------------------------------------------------


def test_credit_line_names_the_domain_when_the_author_is_unknown() -> None:
    row = rights.row(_record("a1", "commons", page_url=""), ["b01"])
    assert rights.credit_line(row) == "Photo: images.example.org via https://images.example.org/a1.jpg"


def test_owner_and_generated_assets_get_no_credit_line() -> None:
    rows = [
        rights.row(_record("u1", "owner_supplied"), ["b01"]),
        rights.row(_record("g1", "generated", generated=GEN_SCENE), ["b02"]),
    ]
    assert rights.credits(rows) == "Some scenes are AI-generated illustrations\n"


def test_no_disclosure_without_a_generated_row() -> None:
    rows = [rights.row(_record("a1"), ["b01"])]
    assert rights.DISCLOSURE not in rights.credits(rows)


def test_credits_are_empty_when_everything_is_the_owners() -> None:
    assert rights.credits([rights.row(_record("u1", "owner_supplied"), ["b01"])]) == ""


# --- T9 completeness (5.4) -------------------------------------------------------------------


def _problems(records: list[AssetRecord], beats: list[BeatAsset], plan: PicturePlan,
              aliases: dict[str, str | None] | None = None) -> list[str]:  # fmt: skip
    manifest = _manifest(records, beats, aliases)
    return rights.completeness(rights.rows(manifest, plan), manifest, plan)


def test_complete_log_passes() -> None:
    plan = _plan(("b01", "photo", "a1"), ("b02", "card", "u1"), ("b03", "photo", "g1"))
    records = [_record("a1"), _record("u1", "owner_supplied"),
               _record("g1", "generated", generated=GEN_SCENE)]  # fmt: skip
    beats = [_beat_asset("b01", "a1"), _beat_asset("b02", "u1"), _beat_asset("b03", "g1", 2)]
    assert _problems(records, beats, plan) == []


def test_a_beat_whose_asset_has_no_row_fails() -> None:
    plan = _plan(("b01", "photo", "a1"), ("b02", "hook_cards", "a7"), cards=("a7",))
    manifest = _manifest([_record("a1")], [_beat_asset("b01", "a1")])
    problems = rights.completeness(rights.rows(manifest, plan), manifest, plan)
    assert problems == ["b02: asset a7 has no rights row"]


def test_a_rung_4_beat_needs_no_row() -> None:
    plan = _plan(("b01", "photo", "a1"), ("b02", "photo", "a2"))
    assert _problems([_record("a1")], [_beat_asset("b01", "a1"), _beat_asset("b02", None, 4)],
                     plan, {"a1": "a1", "a2": None}) == []  # fmt: skip


def test_a_row_without_source_url_or_owner_origin_fails() -> None:
    plan = _plan(("b01", "photo", "a1"))
    problems = _problems([_record("a1", source_url="")], [_beat_asset("b01", "a1")], plan)
    assert problems == ["a1: no source_url and origin web is not owner_supplied or generated"]


def test_missing_prompt_on_a_generated_row_fails() -> None:
    plan = _plan(("b01", "photo", "g1"))
    blank = GEN_SCENE.model_copy(update={"prompt": " "})
    problems = _problems([_record("g1", "generated", generated=blank)],
                         [_beat_asset("b01", "g1", 2)], plan)  # fmt: skip
    assert problems == ["g1: generated without a prompt"]
    assert _problems([_record("g1", "generated")], [_beat_asset("b01", "g1", 2)], plan) == [
        "g1: generated without a prompt"
    ]


def test_named_entity_plus_photoreal_fails() -> None:
    plan = _plan(("b01", "photo", "g1"))
    fake_photo = Generated(model="gen", prompt="the CEO", render="photoreal",
                           depicts="named_entity")  # fmt: skip
    problems = _problems([_record("g1", "generated", generated=fake_photo)],
                         [_beat_asset("b01", "g1", 2)], plan)  # fmt: skip
    assert problems == ["g1: a named entity rendered photoreal (4.2 requires illustration)"]


def test_named_entity_as_illustration_passes() -> None:
    plan = _plan(("b01", "photo", "g1"))
    drawn = Generated(model="gen", prompt="the CEO", render="illustration", depicts="named_entity")
    assert _problems([_record("g1", "generated", generated=drawn)],
                     [_beat_asset("b01", "g1", 2)], plan) == []  # fmt: skip


def test_scene_plus_photoreal_passes() -> None:
    plan = _plan(("b01", "photo", "g1"))
    assert _problems([_record("g1", "generated", generated=GEN_SCENE)],
                     [_beat_asset("b01", "g1", 2)], plan) == []  # fmt: skip


def test_load_reads_back_what_write_wrote(tmp_path: Path) -> None:
    plan = _plan(("b01", "photo", "a1"))
    manifest = _manifest([_record("a1")], [_beat_asset("b01", "a1")])
    rights.write(tmp_path, manifest, plan)
    assert rights.load(tmp_path) == rights.rows(manifest, plan)
    assert rights.load(tmp_path / "nowhere") is None
