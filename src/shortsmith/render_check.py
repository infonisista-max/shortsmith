"""The pre-render check (111c): every asset fits its component before node starts.

Run once on the finished `RenderSpec`, after `render.build_spec` and before the driver.
It walks every `src` the composition draws - the beat's visual, the wall's cells, the
finale's cards, the split's panes and badge, the list's row icons, the stickers and the
diagram's base - and checks it with `media.probe` (by content, never by name) against
what its slot draws: a clip only where the visual's treatment is `clip`, a still
everywhere else. The repairs, in order, each one `check: bNN: <what> -> <repair>` line
and never a failure:

1. A wrong type: a clip in a still's slot becomes its frame grab (`<stem>-frame.jpg`,
   111b's name, so a grab already made is reused); a still in a clip's slot is drawn as
   a photo with the beat's own camera move (the push numbers stay, `speed`/`start_s`
   reset, the real size read).
2. A browser-unsafe format (GIF, BMP, TIFF, AVIF, HEIC, a mislabelled WebP, a non-H.264
   video) becomes a real JPG/PNG (`media.as_still`) or an H.264 mp4 (`media.as_clip`),
   cached as `<stem>-safe.*`.
3. Missing or unreadable: a base visual takes the beat's next asset in `assets.json` that
   probes good (its own record, then any record of the same picture by `sha256`), else
   the gradient (096 rung 4: no visual, the beat drawn `pip`). A wall cell, finale card,
   sticker, row icon or badge is dropped; a split whose pane fails, or a diagram whose
   base fails, is left out (the beat keeps its own visual).

Conversions are cached next to the asset, or in `cache_dir` when one is given (a
read-only job folder checked from a script). Apart from them it is pure over (spec,
files); `warning` is the one plain-words line the job page carries for the repairs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from shortsmith import ffmpeg, media
from shortsmith.contracts import (
    AssetManifest,
    BeatSpec,
    ListRow,
    RenderSpec,
    SplitPane,
    VisualSpec,
)

Slot = Literal["image", "video"]
_CONVERT_ERRORS = (media.MediaError, ffmpeg.FFmpegError, OSError, ValueError)


@dataclass
class Checked:
    """The repaired spec and one `check:` line per repair."""

    spec: RenderSpec
    lines: list[str] = field(default_factory=lambda: [])

    @property
    def repairs(self) -> int:
        return len(self.lines)


def warning(repairs: int) -> str | None:
    """The job page's one line for `repairs` repairs; None when there were none."""
    if repairs <= 0:
        return None
    if repairs == 1:
        return "1 picture was swapped for a safe version or left out before rendering"
    return f"{repairs} pictures were swapped for safe versions or left out before rendering"


@dataclass
class _Fixed:
    src: str
    kind: Slot
    changed: bool


class _Checker:
    def __init__(self, manifest: AssetManifest | None, job_dir: Path | None,
                 cache_dir: Path | None) -> None:  # fmt: skip
        self.manifest = manifest
        self.job_dir = job_dir
        self.cache_dir = cache_dir
        self.lines: list[str] = []

    def note(self, beat_id: str, what: str, repair: str) -> None:
        self.lines.append(f"check: {beat_id}: {what} -> {repair}")

    def _dest(self, path: Path, tag: str) -> Path:
        if self.cache_dir is None:
            return path.parent / f"{path.stem}-{tag}{path.suffix}"
        # One shared folder: the asset's own folder name keeps two `image.webp` apart.
        return self.cache_dir / f"{path.parent.name[:16]}-{path.stem}-{tag}{path.suffix}"

    def _alternates(self, beat_id: str, bad: Path) -> Iterator[Path]:
        """The beat's own asset, then every record of the same picture, as files."""
        if self.manifest is None or self.job_dir is None:
            return
        decided = next((b for b in self.manifest.beats if b.beat_id == beat_id), None)
        if decided is None or decided.asset_id is None:
            return
        own = next((a for a in self.manifest.assets if a.id == decided.asset_id), None)
        if own is None:
            return
        records = [own, *(a for a in self.manifest.assets
                          if a.sha256 == own.sha256 and a.id != own.id)]  # fmt: skip
        for record in records:
            path = (self.job_dir / record.file).resolve()
            if path != bad.resolve():
                yield path

    def fix(self, beat_id: str, what: str, src: str, slot: Slot) -> _Fixed | None:
        """`src` as a file its slot can draw, or None when nothing usable is left."""
        path = Path(src)
        kind = media.probe(path)
        changed = False
        if kind is None:
            found = next((p for p in self._alternates(beat_id, path) if media.probe(p)), None)
            if found is None:
                return None
            self.note(beat_id, f"{what} {path.name} is missing or unreadable",
                      f"the beat's next asset {found.name}")  # fmt: skip
            path, kind, changed = found, media.probe(found), True
        if kind == "video" and slot == "image":
            grab = self._dest(path, "frame").with_suffix(".jpg")
            if media.probe(grab) != "image":
                try:
                    grab = media.as_still(path, grab)
                except _CONVERT_ERRORS:
                    return None
            self.note(beat_id, f"{what} {path.name} is a clip in a still's place",
                      f"its frame grab {grab.name}")  # fmt: skip
            path, kind, changed = grab, "image", True
        elif kind == "image" and slot == "video":
            self.note(beat_id, f"{what} {path.name} is a still in a clip's place",
                      "drawn as a photo with the beat's camera move")  # fmt: skip
        if not media.is_browser_safe(path):
            try:
                if kind == "image":
                    safe = media.as_still(path, self._dest(path, "safe"))
                else:
                    safe = media.as_clip(path, self._dest(path, "safe"))
            except _CONVERT_ERRORS:
                return None
            self.note(beat_id, f"{what} {path.name} is a format the browser cannot draw",
                      f"converted to {safe.name}")  # fmt: skip
            path, changed = safe, True
        assert kind is not None
        return _Fixed(str(path), kind, changed)

    def dropped(self, beat_id: str, what: str, src: str, repair: str) -> None:
        self.note(beat_id, f"{what} {Path(src).name} is missing or unreadable", repair)

    def visual(self, beat: BeatSpec, visual: VisualSpec) -> BeatSpec:
        slot: Slot = "video" if visual.treatment == "clip" else "image"
        fixed = self.fix(beat.id, "visual", visual.src, slot)
        if fixed is None:
            self.dropped(beat.id, "visual", visual.src, "the gradient")
            mode = "pip" if beat.mode == "off" else beat.mode
            return beat.model_copy(update={"visual": None, "mode": mode})
        update: dict[str, object] = {}
        if fixed.changed:
            update["src"] = fixed.src
        if fixed.kind == "image" and slot == "video":
            update.update(treatment="photo", speed=1.0, start_s=0.0)
        if fixed.kind == "image" and update:
            update["width"], update["height"] = _size(Path(fixed.src))
        if not update:
            return beat
        return beat.model_copy(update={"visual": visual.model_copy(update=update)})

    def item[T: BaseModel](self, beat_id: str, what: str, item: T, src: str) -> T | None:
        """An image item with its src (and real size, where it has one) repaired."""
        fixed = self.fix(beat_id, what, src, "image")
        if fixed is None:
            return None
        if not fixed.changed:
            return item
        update: dict[str, object] = {"src": fixed.src}
        if hasattr(item, "width") and hasattr(item, "height"):
            update["width"], update["height"] = _size(Path(fixed.src))
        return item.model_copy(update=update)

    def beat(self, beat: BeatSpec) -> BeatSpec:
        b = beat.id
        if beat.visual is not None:
            beat = self.visual(beat, beat.visual)
        update: dict[str, object] = {}
        if beat.wall is not None:
            cells = self._items(b, "wall cell", beat.wall.cells)
            if cells != beat.wall.cells:
                update["wall"] = beat.wall.model_copy(update={"cells": cells}) if cells else None
        if beat.finale is not None:
            cards = self._items(b, "finale card", beat.finale.cards)
            if cards != beat.finale.cards:
                update["finale"] = beat.finale.model_copy(update={"cards": cards})
        if beat.stickers:
            stickers = tuple(self._items(b, "sticker", list(beat.stickers)))
            if stickers != beat.stickers:
                update["stickers"] = stickers
        if beat.split is not None:
            update.update(self._split(beat))
        if beat.list is not None:
            rows: list[ListRow] = []
            for row in beat.list.rows:
                if row.icon_src and (fixed := self.fix(b, "row icon", row.icon_src, "image")):
                    row = row.model_copy(update={"icon_src": fixed.src}) if fixed.changed else row
                elif row.icon_src:
                    self.dropped(b, "row icon", row.icon_src, "the row drawn without it")
                    # 111f: no icon box either (an empty <Img> src throws); the text
                    # takes the icon's place.
                    row = row.model_copy(update={
                        "icon_src": "", "icon_size": 0.0, "icon_width": 0, "icon_height": 0,
                        "text_left": row.icon_left if row.icon_size else row.text_left,
                        "icon_left": 0.0,
                    })  # fmt: skip
                rows.append(row)
            if rows != beat.list.rows:
                update["list"] = beat.list.model_copy(update={"rows": rows})
        if beat.infographic is not None:
            src = beat.infographic.src
            diagram = self.item(b, "diagram base", beat.infographic, src)
            if diagram is None:
                self.dropped(b, "diagram base", src, "the diagram left out")
            if diagram is not beat.infographic:
                update["infographic"] = diagram
        return beat.model_copy(update=update) if update else beat

    def _items[T: BaseModel](self, beat_id: str, what: str, items: list[T]) -> list[T]:
        kept: list[T] = []
        for item in items:
            src = str(item.model_dump(include={"src"})["src"])
            fixed = self.item(beat_id, what, item, src)
            if fixed is None:
                self.dropped(beat_id, what, src, f"the {what} dropped")
            else:
                kept.append(fixed)
        return kept

    def _split(self, beat: BeatSpec) -> dict[str, object]:
        split = beat.split
        assert split is not None
        panes: list[SplitPane] = []
        for pane in split.panes:
            fixed = self.item(beat.id, "split pane", pane, pane.src)
            if fixed is None:
                self.dropped(beat.id, "split pane", pane.src, "the split left out")
                return {"split": None}
            panes.append(fixed)
        badge = split.badge
        if badge is not None:
            badge = self.item(beat.id, "badge", badge, badge.src)
            if badge is None:
                self.dropped(beat.id, "badge", split.badge.src if split.badge else "",
                             "the badge dropped")  # fmt: skip
        if panes == split.panes and badge is split.badge:
            return {}
        return {"split": split.model_copy(update={"panes": panes, "badge": badge})}


def _size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.size
    except (OSError, ValueError):
        return ffmpeg.video_size(path)


def check(
    spec: RenderSpec,
    *,
    manifest: AssetManifest | None = None,
    job_dir: Path | None = None,
    cache_dir: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> Checked:
    """`spec` with every asset repaired to fit its slot, and the `check:` lines (each
    also handed to `log`). `manifest` and `job_dir` let a missing base visual take the
    beat's next good asset; `cache_dir` takes the conversions instead of the asset's
    own folder."""
    checker = _Checker(manifest, job_dir, cache_dir)
    beats = [checker.beat(beat) for beat in spec.beats]
    if log is not None:
        for line in checker.lines:
            log(line)
    if not checker.lines:
        return Checked(spec)
    return Checked(spec.model_copy(update={"beats": beats}), checker.lines)
