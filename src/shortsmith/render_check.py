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
   base fails, is left out (the beat keeps its own visual). A drop's line names its true
   cause (112b): missing or unreadable with no other asset, a failed frame grab, or a
   failed conversion.

112b: a repair that draws something worse - a clip's frame grab in a still's slot, a
still in a clip's slot, another picture in a missing file's place, anything dropped -
is also a `QualityFinding` on `Checked.findings` (the caller hands them to
`quality.downgrade_all`: strict stops, forgiving keeps the repair). The true fixes are
not findings: a format conversion and a replacement by the same picture (same
`sha256`). `record_only` returns the findings without applying them: every such item
is left as it is and has no `check:` line, while the true fixes are still applied.

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
from shortsmith.jobs import QualityFinding

Slot = Literal["image", "video"]
_CONVERT_ERRORS = (media.MediaError, ffmpeg.FFmpegError, OSError, ValueError)


@dataclass
class Checked:
    """The repaired spec, one `check:` line per repair, and (112b) every repair that
    draws something worse as a finding."""

    spec: RenderSpec
    lines: list[str] = field(default_factory=lambda: [])
    findings: list[QualityFinding] = field(default_factory=lambda: [])

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
                 cache_dir: Path | None, *, kinds: dict[str, str],
                 record_only: bool) -> None:  # fmt: skip
        self.manifest = manifest
        self.job_dir = job_dir
        self.cache_dir = cache_dir
        self.kinds = kinds
        self.record_only = record_only
        self.lines: list[str] = []
        self.findings: list[QualityFinding] = []

    def note(self, beat_id: str, what: str, repair: str) -> None:
        self.lines.append(f"check: {beat_id}: {what} -> {repair}")

    def downgrade(self, beat_id: str, cause: str, repair: str) -> bool:
        """112b: a repair that draws something worse, as a finding; noted as a repair
        unless record-only. True when record-only (the caller keeps the item as it is)."""
        self.findings.append(QualityFinding(beat=beat_id, kind=self.kinds.get(beat_id, ""),
                                            cause=cause, detail=f"repair: {repair}"))  # fmt: skip
        if not self.record_only:
            self.note(beat_id, cause, repair)
        return self.record_only

    def failed(self, beat_id: str, cause: str, dropped: str, keep: _Fixed) -> _Fixed | None:
        """Nothing usable is left: `cause` is the true reason, `dropped` what the caller
        does about it (None tells it to); record-only keeps the item as it is."""
        return keep if self.downgrade(beat_id, cause, dropped) else None

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

    def _sha256(self, path: Path) -> str | None:
        """The sha256 of the manifest record whose file is `path`, if one is."""
        if self.manifest is None or self.job_dir is None:
            return None
        target = path.resolve()
        return next((a.sha256 for a in self.manifest.assets
                     if (self.job_dir / a.file).resolve() == target), None)  # fmt: skip

    def fix(self, beat_id: str, what: str, src: str, slot: Slot,
            dropped: str) -> _Fixed | None:  # fmt: skip
        """`src` as a file its slot can draw, or None when nothing usable is left (the
        caller then does what `dropped` says)."""
        path = Path(src)
        keep = _Fixed(src, slot, False)
        kind = media.probe(path)
        changed = False
        if kind is None:
            state = "unreadable" if path.is_file() else "missing"
            found = next((p for p in self._alternates(beat_id, path) if media.probe(p)), None)
            if found is None:
                return self.failed(beat_id, f"{what} {path.name}: {state} and no other "
                                   "asset for this beat", dropped, keep)  # fmt: skip
            repair = f"the beat's next asset {found.name}"
            sha = self._sha256(path)
            if sha is not None and sha == self._sha256(found):  # the same picture: a true fix
                self.note(beat_id, f"{what} {path.name} is {state}", repair)
            elif self.downgrade(beat_id, f"{what} {path.name} is {state}", repair):
                return keep
            path, kind, changed = found, media.probe(found), True
        if kind == "video" and slot == "image":
            cause = f"{what} {path.name} is a clip in a still's place"
            if self.record_only:
                return keep if self.downgrade(beat_id, cause, "its frame grab") else None
            grab = self._dest(path, "frame").with_suffix(".jpg")
            if media.probe(grab) != "image":
                try:
                    grab = media.as_still(path, grab)
                except _CONVERT_ERRORS as exc:
                    return self.failed(beat_id, f"{what} {path.name}: frame grab failed: {exc}",
                                       dropped, keep)  # fmt: skip
            self.downgrade(beat_id, cause, f"its frame grab {grab.name}")
            path, kind, changed = grab, "image", True
        elif kind == "image" and slot == "video":
            if self.downgrade(beat_id, f"{what} {path.name} is a still in a clip's place",
                              "drawn as a photo with the beat's camera move"):  # fmt: skip
                return keep
        if not media.is_browser_safe(path):
            try:
                if kind == "image":
                    safe = media.as_still(path, self._dest(path, "safe"))
                else:
                    safe = media.as_clip(path, self._dest(path, "safe"))
            except _CONVERT_ERRORS as exc:
                target = "a JPG/PNG" if kind == "image" else "H.264"
                return self.failed(beat_id, f"{what} {path.name}: conversion to {target} "
                                   f"failed: {exc}", dropped, keep)  # fmt: skip
            self.note(beat_id, f"{what} {path.name} is a format the browser cannot draw",
                      f"converted to {safe.name}")  # fmt: skip
            path, changed = safe, True
        assert kind is not None
        return _Fixed(str(path), kind, changed)

    def visual(self, beat: BeatSpec, visual: VisualSpec) -> BeatSpec:
        slot: Slot = "video" if visual.treatment == "clip" else "image"
        fixed = self.fix(beat.id, "visual", visual.src, slot, "the gradient")
        if fixed is None:
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

    def item[T: BaseModel](self, beat_id: str, what: str, item: T, src: str,
                           dropped: str) -> T | None:  # fmt: skip
        """An image item with its src (and real size, where it has one) repaired; None
        when it is to be dropped (`dropped` says how)."""
        fixed = self.fix(beat_id, what, src, "image", dropped)
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
                fixed = (self.fix(b, "row icon", row.icon_src, "image", "the row drawn without it")
                         if row.icon_src else None)  # fmt: skip
                if fixed is not None:
                    row = row.model_copy(update={"icon_src": fixed.src}) if fixed.changed else row
                elif row.icon_src:
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
            diagram = self.item(b, "diagram base", beat.infographic, src, "the diagram left out")
            if diagram is not beat.infographic:
                update["infographic"] = diagram
        return beat.model_copy(update=update) if update else beat

    def _items[T: BaseModel](self, beat_id: str, what: str, items: list[T]) -> list[T]:
        kept: list[T] = []
        for item in items:
            src = str(item.model_dump(include={"src"})["src"])
            fixed = self.item(beat_id, what, item, src, f"the {what} dropped")
            if fixed is not None:
                kept.append(fixed)
        return kept

    def _split(self, beat: BeatSpec) -> dict[str, object]:
        split = beat.split
        assert split is not None
        panes: list[SplitPane] = []
        for pane in split.panes:
            fixed = self.item(beat.id, "split pane", pane, pane.src, "the split left out")
            if fixed is None:
                return {"split": None}
            panes.append(fixed)
        badge = split.badge
        if badge is not None:
            badge = self.item(beat.id, "badge", badge, badge.src, "the badge dropped")
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
    record_only: bool = False,
) -> Checked:
    """`spec` with every asset repaired to fit its slot, the `check:` lines (each also
    handed to `log`) and (112b) the findings. `manifest` and `job_dir` let a missing base
    visual take the beat's next good asset; `cache_dir` takes the conversions instead of
    the asset's own folder; `record_only` applies only the true fixes."""
    kinds = {beat.id: str(beat.kind) for beat in spec.beats}
    checker = _Checker(manifest, job_dir, cache_dir, kinds=kinds, record_only=record_only)
    beats = [checker.beat(beat) for beat in spec.beats]
    if log is not None:
        for line in checker.lines:
            log(line)
    if not checker.lines:
        return Checked(spec, findings=checker.findings)
    return Checked(spec.model_copy(update={"beats": beats}), checker.lines, checker.findings)
