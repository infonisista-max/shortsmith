"""111e: a time budget per step, not one timer for the whole job.

Transcribing, planning, sourcing and qa each get a fixed budget; rendering gets
`base + seconds_per_frame * frames * margin`, scaled to the short being rendered. Every
number is a setting (`config.Settings`); the defaults are its defaults.

The job's one `subproc.Watchdog` (from `watchdog`) is `arm`ed as each step is entered,
so a retry (043) or a rescue rewind (097/111d) gets the full budget of the step it
enters no matter how long the last attempt took. A child that reports progress (the
render driver) is never killed by the step budget, only by the stall clock: `stall_s`
with no new frame. After such a child the rendering step keeps at least its `base`
(the net's next round, the mux). The backstop the watchdog also carries - the old
overall job cap - is computed from the step budgets: every step at the longest short
(`MAX_FRAMES`), `BACKSTOP_ROUNDS` times over, for the rewinds. Nothing re-arms it.

111g starts the plain reel's own fresh budget the same way:
`budgets.arm(watchdog, "rendering", frames=...)` on the current watchdog
(`subproc.current()`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from shortsmith import config, subproc
from shortsmith.jobs import Clock
from shortsmith.render import FPS

MAX_DURATION_S = 60.0  # pipeline.MAX_DURATION_S (3.1 / T3), the longest short
MAX_FRAMES = int(MAX_DURATION_S * FPS)
BACKSTOP_ROUNDS = 2  # every step may run twice (a rescue rewind) before the backstop

STEP_WORDS = {
    "transcribing": "transcribing",
    "planning": "planning",
    "sourcing": "sourcing",
    "rendering": "rendering",
    "qa": "quality check",
}


@dataclass(frozen=True)
class Budgets:
    transcribing_s: float
    planning_s: float
    sourcing_s: float
    qa_s: float
    render_base_s: float
    render_seconds_per_frame: float
    render_margin: float
    stall_s: float

    @classmethod
    def from_settings(cls, settings: config.Settings) -> Budgets:
        return cls(
            transcribing_s=settings.transcribing_minutes * 60,
            planning_s=settings.planning_minutes * 60,
            sourcing_s=settings.sourcing_minutes * 60,
            qa_s=settings.qa_minutes * 60,
            render_base_s=settings.render_base_minutes * 60,
            render_seconds_per_frame=settings.render_seconds_per_frame,
            render_margin=settings.render_margin,
            stall_s=settings.render_stall_minutes * 60,
        )

    def step_s(self, step: str, *, frames: int = 0) -> float:
        """The budget of `step`; rendering's scales with the short's `frames`."""
        if step == "rendering":
            return self.render_base_s + self.render_seconds_per_frame * frames * self.render_margin
        fixed = {
            "transcribing": self.transcribing_s,
            "planning": self.planning_s,
            "sourcing": self.sourcing_s,
            "qa": self.qa_s,
        }
        return fixed[step]

    def backstop_s(self) -> float:
        """The job's overall cap: every step's budget at the longest short, twice over."""
        one_pass = sum(self.step_s(step, frames=MAX_FRAMES) for step in STEP_WORDS)
        return BACKSTOP_ROUNDS * one_pass

    def watchdog(self, *, clock: Clock, interval_s: float = 1.0) -> subproc.Watchdog:
        """The job's watchdog: the backstop from now and the stall limit; unarmed (no
        step deadline) until `arm`."""
        return subproc.Watchdog(
            clock=clock, interval_s=interval_s, stall_s=self.stall_s,
            hard_deadline=clock() + timedelta(seconds=self.backstop_s()),
        )  # fmt: skip

    def arm(self, watchdog: subproc.Watchdog, step: str, *, frames: int = 0) -> None:
        """A fresh budget for `step` on `watchdog` (entering it, a retry, a rewind)."""
        tail = self.render_base_s if step == "rendering" else 0.0
        watchdog.arm(self.step_s(step, frames=frames), tail_s=tail)


def defaults() -> Budgets:
    """The settings' defaults, without reading the environment or `.env`."""
    return Budgets.from_settings(config.Settings.model_construct())


def _minutes(seconds: float) -> str:
    minutes = seconds / 60
    return str(int(minutes)) if float(minutes).is_integer() else f"{minutes:.1f}"


def timeout_message(
    step: str, reason: str | None, *, step_s: float, stall_s: float, backstop_s: float
) -> str:
    """The job page's sentence: which step ran out, how, and that Retry starts it fresh."""
    words = STEP_WORDS.get(step, step)
    retry = f"Retry starts {words} fresh, with its full budget."
    if reason == "stall":
        return f"{words.capitalize()} made no progress for {_minutes(stall_s)} minutes " \
            f"and was stopped. {retry}"  # fmt: skip
    if reason == "job":
        return f"The job ran past its overall cap of {_minutes(backstop_s)} minutes " \
            f"and was stopped. {retry}"  # fmt: skip
    return f"The {words} step ran out of its {_minutes(step_s)}-minute time budget " \
        f"and was stopped. {retry}"  # fmt: skip
