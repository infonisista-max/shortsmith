"""Ticket 049: `SHORTSMITH_SMOKE_KEEP=1` leaves the smoke work directory on disk under
`work/smoke/` and prints the absolute path of the surviving `picture.mp4` in the
summary line; unset (or any other value) the run is byte-identical to today. The
render is faked: these tests exercise the keep mechanics of `main`, not the engine."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from shortsmith import smoke

REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = "smoke ok: job j1 -> qa, 12 words"


def _fake_run_smoke(root: Path, **_: object) -> smoke.SmokeResult:
    work = root / "data" / "j1" / "work"
    work.mkdir(parents=True)
    picture = work / "picture.mp4"
    picture.write_bytes(b"not really a video")
    (work / "render.log").write_text("rendered\n", encoding="utf-8")
    return smoke.SmokeResult(job_dir=root / "data" / "j1", summary=SUMMARY, picture=picture)


@pytest.fixture
def faked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(smoke, "run_smoke", _fake_run_smoke)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHORTSMITH_SMOKE_KEEP", raising=False)
    return tmp_path


def test_keep_set_leaves_the_directory_and_prints_the_path(
    faked: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SHORTSMITH_SMOKE_KEEP", "1")
    assert smoke.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.startswith(SUMMARY)
    kept = Path(out.rsplit(" ", 1)[1].strip())
    assert kept.is_absolute() and kept.name == "picture.mp4" and kept.is_file()
    assert (kept.parent / "render.log").is_file()
    assert (faked / "work" / "smoke") in kept.parents


@pytest.mark.parametrize("value", [None, "0", "yes", "true", ""])
def test_keep_unset_or_other_removes_the_directory(
    faked: Path,
    value: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if value is not None:
        monkeypatch.setenv("SHORTSMITH_SMOKE_KEEP", value)
    assert smoke.main([]) == 0
    assert capsys.readouterr().out == SUMMARY + "\n"
    assert not (faked / "work").exists()
    assert not list(faked.iterdir())


def test_kept_location_is_git_ignored() -> None:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    proc = subprocess.run(
        ["git", "check-ignore", "-q", "work/smoke/shortsmith-smoke-x/data/j1/work/picture.mp4"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
