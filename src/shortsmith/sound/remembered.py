"""The remembered music level (ticket 091; operator, 30 Sep 2026): the slider "remembers my
setting so the next job's default moves toward what I chose" - exactly the last setting,
one for all styles.

`<data_dir>/music_level.json` (`FILE`) holds the offset of the last delivered slider
remix (090), the level measure it was set on, the job and the time. It sits beside
`calibration.json` in the job's own data directory, so the path comes from config
(`SHORTSMITH_DATA_DIR`) and the smoke, whose data directory is a fresh temp one, never
reads the operator's file. The sweeper never touches it; `data/` is git-ignored.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

FILE = "music_level.json"


class Remembered(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset_db: float
    measure: str
    job_id: str
    set_at: datetime


def path(data_dir: Path) -> Path:
    return data_dir / FILE


def load(data_dir: Path) -> Remembered | None:
    """The last slider setting, or None when there is none (or the file is unreadable:
    a job never fails for want of a remembered level; it starts at 0)."""
    file = path(data_dir)
    if not file.is_file():
        return None
    try:
        return Remembered.model_validate_json(file.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def save(data_dir: Path, remembered: Remembered) -> Path:
    file = path(data_dir)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".json.tmp")
    tmp.write_text(remembered.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(file)
    return file
