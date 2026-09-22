"""The rights log (PRD `rights`; decisions 5.4, 4.2; ticket 016).

`write(job_dir, manifest, plan)` writes `out/rights.json`, one row per unique asset
in the 5.4 shape with every beat that shows it (sourced beats, and the hook-card and
finale beats that point at it through the manifest's aliases), and derives
`out/credits.md`: one "Photo: <author or domain> via <page url>" line per asset that
is neither the owner's nor generated, then the AI-disclosure line when any row is
generated. Both files are regenerated on every run, never hand-edited. The renderer
appends music and SFX rows (022).

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
DISCLOSURE = "Some scenes are AI-generated illustrations"
UNCREDITED = frozenset({"owner_supplied", "generated"})

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


def shown(beat: Beat, manifest: AssetManifest) -> list[str]:
    """The asset ids a beat puts on screen: its sourced asset, or the planned id
    resolved through the aliases; a hook-cards beat also shows the hook's cards."""
    decided = manifest.beat(beat.id)
    ids: list[str | None] = []
    if decided is not None:
        ids.append(decided.asset_id)
    elif beat.asset_id is not None:
        ids.append(_resolve(manifest, beat.asset_id))
    return [i for i in ids if i is not None]


def _hook_cards(plan: PicturePlan, manifest: AssetManifest) -> list[str]:
    resolved = (_resolve(manifest, card) for card in plan.hook.card_asset_ids)
    return [i for i in resolved if i is not None]


def rows(manifest: AssetManifest, plan: PicturePlan) -> list[RightsRow]:
    """One row per unique asset, in manifest order, beat ids in plan order."""
    out: list[RightsRow] = []
    for record in manifest.assets:
        beat_ids = [b.id for b in plan.beats if record.id in shown(b, manifest)]
        out.append(row(record, beat_ids))
    return out


def credit_line(r: RightsRow) -> str:
    via = r.page_url or r.source_url
    who = r.author or urlparse(r.source_url or r.page_url).netloc
    return f"Photo: {who} via {via}"


def credits(rows: Sequence[RightsRow]) -> str:
    """`credits.md`: the credit lines, then the disclosure line when one applies."""
    lines = [
        credit_line(r)
        for r in rows
        if r.kind in ("image", "clip_frame") and r.origin not in UNCREDITED
    ]
    blocks = ["\n".join(lines)] if lines else []
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
        wanted = shown(beat, manifest)
        if beat.kind == "hook_cards":
            wanted += _hook_cards(plan, manifest)
        for asset_id in dict.fromkeys(wanted):
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


def write(job_dir: Path, manifest: AssetManifest, plan: PicturePlan) -> list[RightsRow]:
    """Regenerate `out/rights.json` and `out/credits.md`; return the rows."""
    out = job_dir / "out"
    out.mkdir(parents=True, exist_ok=True)
    logged = rows(manifest, plan)
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
