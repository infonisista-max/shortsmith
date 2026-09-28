"""The smoke walk under each recipe style of ticket 059 (`python -m shortsmith.smoke
--style footage|vishva|fastfacts`): each passes T1-T13 and its render spec shows its
recipe. In its own file so the smoke test files each stay a short foreground chunk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shortsmith import smoke


@pytest.mark.parametrize(
    ("style", "shows"),
    [
        ("footage", ["recipe flash b03, whoosh b03", "clip b04"]),
        ("vishva", ["text pops 1, bubbles 2, stickers 1", "stacked split"]),
        ("fastfacts", ["title strip 'Twelve words of nothing'"]),
    ],
)
def test_run_smoke_renders_each_recipe_end_to_end(
    tmp_path: Path, style: str, shows: list[str]
) -> None:
    result = smoke.run_smoke(tmp_path, style=style)
    assert f"style {style}," in result.summary
    for fragment in shows:
        assert fragment in result.summary, fragment
    qa = json.loads((result.job_dir / "out" / "qa.json").read_text(encoding="utf-8"))
    assert [c["passed"] for c in qa["checks"]] == [True] * 13
    spec = json.loads((result.job_dir / "work" / "render_spec.json").read_text(encoding="utf-8"))
    means = [b["end_frame"] - b["start_frame"] for b in spec["beats"]]
    assert sum(means) / len(means) / spec["fps"] <= 1.5
    assert (spec["title_strip"] is not None) == (style == "fastfacts")
