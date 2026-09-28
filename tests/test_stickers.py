"""Ticket 062: the sticker catalogue (Microsoft Fluent Emoji, MIT), validated at startup,
and the fetch-on-first-use cache the asset step fills. Tests use the fake fetcher; the
one live fetch was a throwaway spike (the done note carries its status and size)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from shortsmith import stickers
from shortsmith.contracts import Beat, Event, PicturePlan, Sticker
from shortsmith.stickers import (
    FakeStickerFetcher,
    StickerCatalogue,
    StickerError,
    StickerShelf,
)

ROOT = Path(__file__).resolve().parents[1]


def _catalogue(rows: str) -> str:
    return "entries:\n" + rows


LIGHT_BULB = "  - {name: Light bulb, path: Light bulb/3D/light_bulb_3d.png, tags: [idea]}\n"
SKULL = "  - {name: Skull, path: Skull/3D/skull_3d.png, tags: [death, danger]}\n"
THUMBS = (
    "  - {name: Thumbs up, path: Thumbs up/Default/3D/thumbs_up_3d_default.png, tags: [agree]}\n"
)


# --- the catalogue -----------------------------------------------------------------------


def test_the_shipped_catalogue_holds_40_to_60_curated_emoji() -> None:
    """062 (1): 40-60 rows, unique names, non-empty intent tags, every path the 3D
    pattern, and the ticket's own intents all present."""
    shipped = stickers.load_catalogue()
    assert 40 <= len(shipped.entries) <= 60
    names = [e.name for e in shipped.entries]
    assert len(set(names)) == len(names)
    assert all(e.tags for e in shipped.entries)
    for tag in ("idea", "danger", "death", "shock", "money", "fire", "question", "yes", "no",
                "time", "win", "love", "food", "science", "space", "sport"):  # fmt: skip
        assert shipped.with_tag(tag), tag
    bulb = shipped.pick("idea", "Light bulb")
    assert bulb is not None
    assert bulb.url == (
        "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"
        "Light%20bulb/3D/light_bulb_3d.png"
    )
    assert stickers.shipped() is stickers.shipped(), "loaded once per process"


def test_a_row_with_a_skin_tone_sits_one_folder_deeper_under_default() -> None:
    parsed = stickers.parse_catalogue(_catalogue(THUMBS), name="t.yaml")
    assert parsed.entries[0].path == "Thumbs up/Default/3D/thumbs_up_3d_default.png"


@pytest.mark.parametrize(
    ("rows", "named"),
    [
        (LIGHT_BULB + LIGHT_BULB, r"Light bulb.*twice"),
        ("  - {name: Fire, path: Fire/3D/fire_3d.png, tags: []}\n", r"Fire.*tag"),
        ("  - {name: Fire, path: Fire/fire.png, tags: [fire]}\n", r"Fire.*3D"),
        ("  - {name: Fire, path: Fire/3D/flame_3d.png, tags: [fire]}\n", r"Fire.*3D"),
        ("  - {name: Fire, path: Fire/Color/fire_color.svg, tags: [fire]}\n", r"Fire.*3D"),
        ("  - {name: Fire, tags: [fire]}\n", r"row 1"),
    ],
)
def test_a_broken_row_is_refused_naming_it(rows: str, named: str) -> None:
    """062 AC: unique names, non-empty tags, every path matching the 3D pattern; a
    broken row stops the load naming it."""
    with pytest.raises(StickerError, match=named):
        stickers.parse_catalogue(_catalogue(rows), name="catalog.yaml")


def test_a_catalogue_that_is_not_an_entry_list_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(StickerError, match="catalog.yaml"):
        stickers.load_catalogue(path)


def test_the_planner_picks_by_intent_and_code_resolves_the_name() -> None:
    """062 (4): the planner names an intent tag, and may name one of that tag's rows;
    never a free file name. No name is the tag's first row."""
    cat = stickers.parse_catalogue(_catalogue(LIGHT_BULB + SKULL), name="t.yaml")
    assert cat.tags() == ["danger", "death", "idea"]
    first = cat.pick("danger")
    assert first is not None and first.name == "Skull"
    assert cat.pick("danger", "Light bulb") is None, "the row does not carry the intent"
    assert cat.pick("money") is None
    assert cat.pick("idea", "light_bulb_3d.png") is None


# --- fetched on first use, cached after -----------------------------------------------------


def _shelf(tmp_path: Path, fetcher: FakeStickerFetcher) -> StickerShelf:
    cat = stickers.parse_catalogue(_catalogue(LIGHT_BULB + SKULL), name="t.yaml")
    return StickerShelf(catalogue=cat, fetcher=fetcher, cache_dir=tmp_path / "cache")


def test_the_first_use_fetches_and_the_second_is_a_cache_hit(tmp_path: Path) -> None:
    fetcher = FakeStickerFetcher()
    shelf = _shelf(tmp_path, fetcher)
    entry = shelf.catalogue.pick("idea")
    assert entry is not None
    first = shelf.ensure(entry)
    assert first.is_file() and first.read_bytes().startswith(b"\x89PNG")
    assert first.parent == tmp_path / "cache"
    again = shelf.ensure(entry)
    assert again == first
    assert fetcher.calls == [entry.url], "the second use never reaches the network"


def test_a_fetch_that_is_not_a_png_is_refused(tmp_path: Path) -> None:
    shelf = _shelf(tmp_path, FakeStickerFetcher(body=b"<html>rate limited</html>"))
    entry = shelf.catalogue.pick("idea")
    assert entry is not None
    with pytest.raises(StickerError, match="not a PNG"):
        shelf.ensure(entry)
    assert not list((tmp_path / "cache").glob("*.png")), "nothing half-written is cached"


def _plan(*stuck: tuple[str, Sticker]) -> PicturePlan:
    beats = [
        Beat(id="b01", start=0.0, end=1.0, mode="pip", kind="photo", event=Event()),
        Beat(id="b02", start=1.0, end=2.0, mode="pip", kind="photo", event=Event()),
    ]
    by_id = dict(stuck)
    beats = [b.model_copy(update={"stickers": [by_id[b.id]]}) if b.id in by_id else b
             for b in beats]  # fmt: skip
    return PicturePlan.model_validate(
        {"prompt_version": "t", "cut": {"keep": [{"start": 0.0, "end": 2.0}]},
         "beats": [b.model_dump() for b in beats], "finale": {"beat_id": "b02", "text": "x"},
         "keywords": [], "title": "t", "description": "d", "hashtags": []}  # fmt: skip
    )


def test_the_asset_step_copies_each_sticker_into_the_job_once(tmp_path: Path) -> None:
    """062 (2): fetched at job time into the cache, then copied into the job folder so
    the renderer reads only the job's files; one record per sticker however many beats
    show it."""
    fetcher = FakeStickerFetcher()
    shelf = _shelf(tmp_path, fetcher)
    bulb = Sticker(intent="idea", name="Light bulb", word=0)
    plan = _plan(("b01", bulb), ("b02", bulb))
    lines: list[str] = []
    job = tmp_path / "job"
    records = shelf.source(plan, job_dir=job, log=lines.append, fetched_at="2026-09-28T10:00:00")
    assert [r.name for r in records] == ["Light bulb"]
    (record,) = records
    assert (job / record.file).is_file() and record.file.startswith("assets/stickers/")
    assert record.source_url == shelf.catalogue.entries[0].url
    assert (record.width, record.height) == (stickers.FAKE_SIZE_PX, stickers.FAKE_SIZE_PX)
    assert len(record.sha256) == 64 and record.fetched_at == "2026-09-28T10:00:00"
    assert len(fetcher.calls) == 1
    assert lines == []


class _Offline(FakeStickerFetcher):
    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        raise StickerError(f"GET {url}: connection refused")


def test_a_network_failure_drops_that_sticker_logged_and_the_step_goes_on(tmp_path: Path) -> None:
    """062 (2): a failed fetch drops that sticker, logs why, and the job goes on."""
    shelf = _shelf(tmp_path, _Offline())
    plan = _plan(("b01", Sticker(intent="idea", name="Light bulb", word=0)))
    lines: list[str] = []
    records = shelf.source(plan, job_dir=tmp_path / "job", log=lines.append, fetched_at="t")
    assert records == []
    assert len(lines) == 1
    assert lines[0].startswith("sticker: b01: 'Light bulb' dropped") and "refused" in lines[0]


def test_a_sticker_the_catalogue_does_not_carry_is_dropped_and_logged(tmp_path: Path) -> None:
    shelf = _shelf(tmp_path, FakeStickerFetcher())
    plan = _plan(("b01", Sticker(intent="idea", name="Ghost", word=0)))
    lines: list[str] = []
    assert shelf.source(plan, job_dir=tmp_path / "job", log=lines.append, fetched_at="t") == []
    assert "not in the sticker catalogue" in lines[0]


def test_the_fetched_cache_is_git_ignored() -> None:
    """062 AC: the fetched cache (`<data dir>/cache/stickers/`, the default data dir
    `data/`) never reaches the repository; the catalogue itself is tracked."""
    probe = (Path("data") / stickers.CACHE_SUBDIR / "light_bulb_3d.png").as_posix()
    done = subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT, check=False)
    assert done.returncode == 0, f"{probe} is not git-ignored"
    tracked = subprocess.run(["git", "check-ignore", "-q", "assets/stickers/catalog.yaml"],
                             cwd=ROOT, check=False)  # fmt: skip
    assert tracked.returncode == 1, "the catalogue itself is tracked"


def test_the_live_shelf_uses_the_shipped_catalogue_and_the_data_dir_cache(tmp_path: Path) -> None:
    shelf = stickers.live_shelf(tmp_path)
    assert isinstance(shelf.catalogue, StickerCatalogue)
    assert shelf.cache_dir == tmp_path / "cache" / "stickers"
    assert isinstance(shelf.fetcher, stickers.HttpStickerFetcher)
