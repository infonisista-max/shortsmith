"""112b: the strict pre-render gate - how many b-roll beats settled for a gradient or a
generated image, from `assets.json`, the plan and the sourcing log."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import jobs, prerender, quality, render
from shortsmith.contracts import AssetManifest, AssetRecord, Beat, BeatAsset
from tests.test_render_check import (  # pyright: ignore[reportPrivateUsage]
    _base_spec,  # pyright: ignore[reportPrivateUsage]
    _clip,  # pyright: ignore[reportPrivateUsage]
    _render_picture_with,  # pyright: ignore[reportPrivateUsage]
    _visual,  # pyright: ignore[reportPrivateUsage]
)

GEN = "gen-1"


def _beat(i: int, *, query: str = "", intent: str | None = None) -> Beat:
    return Beat.model_validate({
        "id": f"b{i:02d}", "start": float(i), "end": float(i) + 1.0, "mode": "pip",
        "kind": "photo", "query": query or f"thing {i}", "source_intent": intent,
    })  # fmt: skip


def _record(asset_id: str, origin: str) -> AssetRecord:
    return AssetRecord.model_validate({
        "id": asset_id, "origin": origin, "file": f"work/assets/{asset_id}.jpg", "sha256": asset_id,
        "width": 1080, "height": 1920, "fetched_at": "2026-10-02T00:00:00Z",
    })  # fmt: skip


def _manifest(total: int, gradients: int, generated: int = 0) -> tuple[AssetManifest, list[Beat]]:
    """`total` sourced beats b01..: the first `gradients` over the gradient, the next
    `generated` a generated image, the rest found photos."""
    rows: list[BeatAsset] = []
    for i in range(1, total + 1):
        if i <= gradients:
            rows.append(BeatAsset(beat_id=f"b{i:02d}", asset_id=None, treatment="gradient",
                                  fallback_rung=4))  # fmt: skip
        elif i <= gradients + generated:
            rows.append(BeatAsset(beat_id=f"b{i:02d}", asset_id=GEN, treatment="photo",
                                  fallback_rung=2))  # fmt: skip
        else:
            rows.append(BeatAsset(beat_id=f"b{i:02d}", asset_id="found", treatment="photo",
                                  fallback_rung=0))  # fmt: skip
    manifest = AssetManifest(assets=[_record(GEN, "generated"), _record("found", "commons")],
                             beats=rows, runtime_s=30.0, rescued_max=3)  # fmt: skip
    return manifest, [_beat(i) for i in range(1, total + 1)]


def test_each_settled_beat_names_what_was_wanted_what_was_used_and_why() -> None:
    manifest, beats = _manifest(4, gradients=1, generated=1)
    log = (
        "2026-10-02T00:00:00Z sourcing: b01: an earlier line\n"
        "2026-10-02T00:00:01Z sourcing: b01: replacement ladder: nothing was found and "
        "nothing could be generated; shown over the gradient\n"
        "2026-10-02T00:00:02Z sourcing: b02: replacement ladder: generated\n"
    )

    found = prerender.settled(manifest, beats, log)

    assert found.broll == 4
    assert [f.beat for f in found.findings] == ["b01", "b02"]
    first, second = found.findings
    assert first.kind == "photo"
    assert "settled for the gradient" in first.cause
    assert "wanted 'thing 1'" in first.cause
    assert "nothing could be generated; shown over the gradient" in first.cause
    assert "an earlier line" not in first.cause
    assert "settled for a generated image" in second.cause
    assert found.headline() == (
        "stopped before rendering: 2 of 4 picture beats settled for a gradient or a "
        "generated image"
    )


def test_a_planned_generation_is_not_settled_and_a_beat_with_no_reason_says_so() -> None:
    manifest, beats = _manifest(3, gradients=1, generated=1)
    beats[1] = _beat(2, intent="generate")

    found = prerender.settled(manifest, beats, "")

    assert [f.beat for f in found.findings] == ["b01"]
    assert "no reason in the sourcing log" in found.findings[0].cause


def test_presenter_only_beats_are_not_counted() -> None:
    """Only the sourced beats (`assets.json`) wanted a picture; the plan's presenter
    beats never reach the manifest and never count."""
    manifest, beats = _manifest(2, gradients=1)
    beats.append(Beat.model_validate({"id": "b09", "start": 9.0, "end": 10.0, "mode": "full",
                                      "kind": "presenter_full"}))  # fmt: skip

    assert prerender.settled(manifest, beats, "").broll == 2


@pytest.mark.parametrize(
    ("total", "gradients", "stops"),
    [(19, 5, True), (16, 4, False)],  # 5/19 = 0.26 stops; 4/16 = 0.25 goes ahead
)
def test_the_line_is_a_share_above_the_setting(total: int, gradients: int, stops: bool) -> None:
    manifest, beats = _manifest(total, gradients=gradients)

    found = prerender.settled(manifest, beats, "")

    assert round(found.share, 2) == (0.26 if stops else 0.25)
    assert found.over(0.25) is stops


def test_no_manifest_settles_nothing() -> None:
    found = prerender.settled(None, [], "")
    assert found.broll == 0 and found.share == 0.0 and not found.over(0.25)


def _job_with(tmp_path: Path, total: int, gradients: int) -> jobs.Job:
    from shortsmith import assets

    job = jobs.create(tmp_path / "job")
    manifest, _ = _manifest(total, gradients=gradients)
    path = assets.manifest_path(job.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    return job


def test_under_the_line_the_list_goes_to_job_log_as_settled_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUALITY_MODE", "strict")
    job = _job_with(tmp_path, total=4, gradients=1)

    gate = prerender.gate(job)
    gate.note(job)

    log = (job.path / "job.log").read_text(encoding="utf-8")
    assert "settled: beat b01: settled for the gradient" in log
    rows = quality.log_path(job).read_text(encoding="utf-8").splitlines()[1:]
    assert [row.split("\t")[2] + "/" + row.split("\t")[4] for row in rows] == ["b01/settled"]


def test_the_gate_reads_the_line_from_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job_with(tmp_path, total=4, gradients=2)
    assert prerender.gate(job).over(prerender.max_share())
    monkeypatch.setenv("STRICT_SETTLED_MAX_SHARE", "0.5")
    assert not prerender.gate(job).over(prerender.max_share())


# --- the gate inside render_picture: one stop before node ----------------------------------


def test_strict_over_the_line_stops_once_with_the_gate_and_the_check_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setenv("QUALITY_MODE", "strict")
    job = _job_with(tmp_path, total=4, gradients=2)
    clip = _clip(job.path / "work" / "assets" / "h" / "clip.mp4")
    base = _base_spec()
    first = base.beats[0].model_copy(update={"mode": "off", "visual": _visual(clip)})
    seen = _render_picture_with(base.model_copy(update={"beats": [first, *base.beats[1:]]}),
                                monkeypatch)  # fmt: skip

    with pytest.raises(quality.QualityStop) as stop:
        render.render_picture(job)

    assert seen == []
    assert stop.value.headline == (
        "stopped before rendering: 2 of 4 picture beats settled for a gradient or a "
        "generated image"
    )
    beats = [f.beat for f in stop.value.findings]
    assert beats[:2] == ["b01", "b02"] and base.beats[0].id in beats[2:]


def test_strict_at_the_line_renders_and_writes_settled_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setenv("QUALITY_MODE", "strict")
    job = _job_with(tmp_path, total=4, gradients=1)
    seen = _render_picture_with(_base_spec(), monkeypatch)

    render.render_picture(job)

    assert len(seen) == 1
    assert "settled: beat b01: settled for the gradient" in (job.path / "job.log").read_text(
        encoding="utf-8"
    )


@pytest.mark.usefixtures("forgiving")
def test_forgiving_never_runs_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:

    job = _job_with(tmp_path, total=4, gradients=4)
    seen = _render_picture_with(_base_spec(), monkeypatch)

    render.render_picture(job)

    assert len(seen) == 1
    log = job.path / "job.log"
    assert "settled:" not in (log.read_text(encoding="utf-8") if log.is_file() else "")
