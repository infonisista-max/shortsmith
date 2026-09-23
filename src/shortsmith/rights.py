"""The rights log (PRD `rights`; decisions 5.4, 4.2; ticket 016).

`write(job_dir, manifest, plan)` writes `out/rights.json`, one row per unique asset
in the 5.4 shape with every beat that shows it (sourced beats, and the hook-card and
finale beats that point at it through the manifest's aliases), and derives
`out/credits.md`: one "Photo: <author or domain> via <page url>" line per asset that
is neither the owner's nor generated, the music and sound lines, then the AI-disclosure
line when any row is generated. Both files are regenerated on every run, never
hand-edited.

The renderer's music and SFX rows (022) are not in the manifest, so they are kept beside
it in `work/audio_rights.json` (`write_audio`) and appended by every later `write`: a
re-run of the asset step rebuilds the picture rows and carries the audio ones through.

`completeness` is the T9 rule set, a completeness check in code, not a licence check:
every beat's asset has a row; every row has a `source_url` or an `owner_supplied` /
`generated` origin; every generated row has a prompt; a generated named entity
rendered photoreal fails (4.2); a photoreal scene passes.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

from pydantic import TypeAdapter

from shortsmith.contracts import AssetManifest, AssetRecord, Beat, PicturePlan, RightsRow

RIGHTS_NAME = "rights.json"
CREDITS_NAME = "credits.md"
AUDIO_NAME = "audio_rights.json"  # under work/: the renderer's rows, carried by `write`
DISCLOSURE = "Some scenes are AI-generated illustrations"
UNCREDITED = frozenset({"owner_supplied", "generated"})
AUDIO_KINDS = ("music", "sfx")
CREDIT_LABELS = {"music": "Music", "sfx": "Sound"}

_ROWS = TypeAdapter(list[RightsRow])


def row(record: AssetRecord, beat_ids: Sequence[str]) -> RightsRow:
    return RightsRow(
        id=record.id,
        beat_ids=list(beat_ids),
        kind=record.kind,
        origin=record.origin,
        source_url=record.source_url,
        page_url=record.page_url,
        licence=record.licence,
        author=record.author,
        generated=record.generated,
        judge=record.judge,
        file=record.file,
        sha256=record.sha256,
        width=record.width,
        height=record.height,
        fetched_at=record.fetched_at,
    )


def _resolve(manifest: AssetManifest, asset_id: str) -> str | None:
    return manifest.aliases.get(asset_id, asset_id)


def shown(beat: Beat, manifest: AssetManifest, plan: PicturePlan) -> list[str]:
    """The asset ids a beat puts on screen, once each: its sourced asset, or the
    planned id resolved through the aliases; a hook-cards beat also shows the hook's
    cards, and a `list`, `split` or `wall` beat the assets of its items (027)."""
    decided = manifest.beat(beat.id)
    ids: list[str | None] = []
    if decided is not None:
        ids.append(decided.asset_id)
    elif beat.asset_id is not None:
        ids.append(_resolve(manifest, beat.asset_id))
    if beat.kind == "hook_cards":
        ids += [_resolve(manifest, card) for card in plan.hook.card_asset_ids]
    ids += [_resolve(manifest, i.asset_id) for i in beat.items if i.asset_id is not None]
    return list(dict.fromkeys(i for i in ids if i is not None))


def rows(manifest: AssetManifest, plan: PicturePlan) -> list[RightsRow]:
    """One row per unique asset, in manifest order, beat ids in plan order."""
    out: list[RightsRow] = []
    for record in manifest.assets:
        beat_ids = [b.id for b in plan.beats if record.id in shown(b, manifest, plan)]
        out.append(row(record, beat_ids))
    return out


def credit_line(r: RightsRow) -> str:
    via = r.page_url or r.source_url
    who = r.author or urlparse(r.source_url or r.page_url).netloc
    label = CREDIT_LABELS.get(r.kind, "Photo")
    return f"{label}: {who} via {via}"


def credits(rows: Sequence[RightsRow]) -> str:
    """`credits.md`: the picture credit lines, then the music and sound lines (5.4: the
    music line is the bed and the cue files the mix used, once each), then the disclosure
    line when one applies."""
    pictures = [
        credit_line(r)
        for r in rows
        if r.kind in ("image", "clip_frame") and r.origin not in UNCREDITED
    ]
    audio = [
        credit_line(r) for r in rows if r.kind in AUDIO_KINDS and r.origin not in UNCREDITED
    ]
    blocks = ["\n".join(lines) for lines in (pictures, audio) if lines]
    if any(r.generated is not None or r.origin == "generated" for r in rows):
        blocks.append(DISCLOSURE)
    return "\n\n".join(blocks) + "\n" if blocks else ""


def completeness(
    rows: Sequence[RightsRow], manifest: AssetManifest, plan: PicturePlan
) -> list[str]:
    """The T9 problems, one line each; empty when the log is complete."""
    problems: list[str] = []
    ids = {r.id for r in rows}
    for beat in plan.beats:
        for asset_id in shown(beat, manifest, plan):
            if asset_id not in ids:
                problems.append(f"{beat.id}: asset {asset_id} has no rights row")
    for r in rows:
        if not r.source_url and r.origin not in UNCREDITED:
            problems.append(
                f"{r.id}: no source_url and origin {r.origin} is not owner_supplied or generated"
            )
        if r.origin == "generated" or r.generated is not None:
            if r.generated is None or not r.generated.prompt.strip():
                problems.append(f"{r.id}: generated without a prompt")
            elif r.generated.depicts == "named_entity" and r.generated.render == "photoreal":
                problems.append(
                    f"{r.id}: a named entity rendered photoreal (4.2 requires illustration)"
                )
    return problems


def write_audio(job_dir: Path, audio: Sequence[RightsRow]) -> Path:
    """The renderer's music and SFX rows (022), kept under `work/` so the next run of the
    asset step carries them into `out/rights.json` instead of dropping them."""
    work = job_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    path = work / AUDIO_NAME
    path.write_text(_ROWS.dump_json(list(audio), indent=2).decode("utf-8"), encoding="utf-8")
    return path


def audio_rows(job_dir: Path) -> list[RightsRow]:
    """The rows `write_audio` left, or none when the renderer has not run yet."""
    path = job_dir / "work" / AUDIO_NAME
    if not path.is_file():
        return []
    return _ROWS.validate_json(path.read_text(encoding="utf-8"))


def write(job_dir: Path, manifest: AssetManifest, plan: PicturePlan) -> list[RightsRow]:
    """Regenerate `out/rights.json` and `out/credits.md`; return the rows.

    The asset rows are rebuilt from the manifest every time the asset step runs; the
    music and SFX rows the renderer wrote (5.4, 022) are appended after them, so they
    survive that rebuild."""
    out = job_dir / "out"
    out.mkdir(parents=True, exist_ok=True)
    logged = rows(manifest, plan) + audio_rows(job_dir)
    (out / RIGHTS_NAME).write_text(
        _ROWS.dump_json(logged, indent=2).decode("utf-8"), encoding="utf-8"
    )
    (out / CREDITS_NAME).write_text(credits(logged), encoding="utf-8")
    return logged


def load(job_dir: Path) -> list[RightsRow] | None:
    path = job_dir / "out" / RIGHTS_NAME
    if not path.is_file():
        return None
    return _ROWS.validate_json(path.read_text(encoding="utf-8"))
