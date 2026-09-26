"""The copyable publishing text (decisions 10.4, 8.2, 5.4; ticket 035).

Once a job has a short, its page offers three blocks to copy into YouTube: the plan's
`title` (8.2: at most 100 characters, the grammar's clamp), the description - the
plan's own text, then the credits and the AI-disclosure line exactly as `credits.md`
carries them (5.4: every third-party asset credited, generated scenes disclosed) - and
the hashtags, at most five (8.2), each with its `#`. `assemble` is pure over the plan
and the credits text; `load(job)` reads both from the job's files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shortsmith import rights
from shortsmith.contracts import PicturePlan
from shortsmith.grammar import HASHTAGS_MAX
from shortsmith.jobs import Job


@dataclass(frozen=True)
class Publishing:
    title: str
    description: str
    hashtags: list[str]

    @property
    def hashtag_line(self) -> str:
        return " ".join(self.hashtags)


def hashtag(tag: str) -> str:
    tag = tag.strip()
    return tag if tag.startswith("#") else f"#{tag}"


def assemble(plan: PicturePlan, credits: str) -> Publishing:
    """The three blocks: the credits (with the disclosure line when the rights log has
    one) follow the plan's description after a blank line; nothing when there are none."""
    credits = credits.strip()
    description = plan.description.strip()
    if credits:
        description = f"{description}\n\n{credits}"
    tags = [hashtag(t) for t in plan.hashtags if t.strip()][:HASHTAGS_MAX]
    return Publishing(title=plan.title.strip(), description=description, hashtags=tags)


def load(job: Job) -> Publishing | None:
    """From `work/plan.json` and `out/credits.md`; None until the job has a plan."""
    plan_path = job.work_dir / "plan.json"
    if not plan_path.is_file():
        return None
    plan = PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    credits_path: Path = job.out_dir / rights.CREDITS_NAME
    credits = credits_path.read_text(encoding="utf-8") if credits_path.is_file() else ""
    return assemble(plan, credits)
