"""111e: a time budget per step, the rendering one scaled to the short's frames, and the
job's backstop computed from them; every number a setting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shortsmith import budgets, config
from shortsmith.budgets import Budgets

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

SMALL = Budgets(
    transcribing_s=60, planning_s=120, sourcing_s=180, qa_s=240,
    render_base_s=300, render_seconds_per_frame=0.5, render_margin=2.0, stall_s=90,
)  # fmt: skip


def test_rendering_is_base_plus_seconds_per_frame_times_frames_times_margin() -> None:
    assert SMALL.step_s("rendering", frames=1000) == 300 + 0.5 * 1000 * 2.0
    assert SMALL.step_s("rendering", frames=0) == 300


@pytest.mark.parametrize(
    ("step", "seconds"),
    [("transcribing", 60), ("planning", 120), ("sourcing", 180), ("qa", 240)],
)
def test_the_other_steps_have_fixed_budgets(step: str, seconds: float) -> None:
    assert SMALL.step_s(step, frames=99_999) == seconds


def test_the_backstop_is_every_step_at_the_longest_short_times_the_rounds() -> None:
    longest = SMALL.step_s("rendering", frames=budgets.MAX_FRAMES)
    assert SMALL.backstop_s() == budgets.BACKSTOP_ROUNDS * (60 + 120 + 180 + 240 + longest)


def test_the_numbers_come_from_settings() -> None:
    s = config.Settings.model_construct(
        transcribing_minutes=1, planning_minutes=2, sourcing_minutes=3, qa_minutes=4,
        render_base_minutes=5, render_seconds_per_frame=0.25, render_margin=3.0,
        render_stall_minutes=6,
    )  # fmt: skip
    assert Budgets.from_settings(s) == Budgets(
        transcribing_s=60, planning_s=120, sourcing_s=180, qa_s=240,
        render_base_s=300, render_seconds_per_frame=0.25, render_margin=3.0, stall_s=360,
    )  # fmt: skip


def test_the_defaults_are_the_settings_defaults() -> None:
    assert budgets.defaults() == Budgets.from_settings(config.Settings.model_construct())


def test_arm_gives_the_step_its_budget_and_rendering_its_tail() -> None:
    now = T0
    watchdog = SMALL.watchdog(clock=lambda: now)
    SMALL.arm(watchdog, "rendering", frames=100)  # 300 + 100 s
    now = T0 + timedelta(seconds=399)
    assert not watchdog.check()
    watchdog.progress_started()
    now = T0 + timedelta(seconds=1000)
    watchdog.beat()
    watchdog.progress_ended()  # past the deadline: the base is left for the mux
    now = T0 + timedelta(seconds=1299)
    assert not watchdog.check()
    now = T0 + timedelta(seconds=1300)
    assert watchdog.check()
    assert watchdog.reason == "step"


def test_the_watchdog_carries_the_backstop_and_the_stall_limit() -> None:
    now = T0
    watchdog = SMALL.watchdog(clock=lambda: now)
    SMALL.arm(watchdog, "rendering", frames=0)
    watchdog.progress_started()
    now = T0 + timedelta(seconds=89)
    assert not watchdog.check()
    now = T0 + timedelta(seconds=90)
    assert watchdog.check() and watchdog.reason == "stall"
    SMALL.arm(watchdog, "rendering", frames=0)  # a retry: fresh
    now = T0 + timedelta(seconds=SMALL.backstop_s())
    assert watchdog.check() and watchdog.reason == "job"


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("step", "The rendering step ran out of its 25-minute time budget and was stopped. "
                 "Retry starts rendering fresh, with its full budget."),
        ("stall", "Rendering made no progress for 5 minutes and was stopped. "
                  "Retry starts rendering fresh, with its full budget."),
        ("job", "The job ran past its overall cap of 160 minutes and was stopped. "
                "Retry starts rendering fresh, with its full budget."),
    ],
)  # fmt: skip
def test_the_timeout_message_names_the_step_and_says_retry_starts_it_fresh(
    reason: str, expected: str
) -> None:
    assert budgets.timeout_message(
        "rendering", reason, step_s=1500, stall_s=300, backstop_s=9600
    ) == expected
