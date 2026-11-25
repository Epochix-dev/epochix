"""Two recorded Stable-Baselines3 runs, through the whole pipeline.

Both were read as nothing at all: parser `universal`, task `custom`, no
frames. A PPO run (on-policy, a table every rollout) and a DQN run
(off-policy, a table every four episodes), both on CartPole, recorded from a
neutral folder with their scripts beside them.

What is checked here is read from the log's own text, not from the engine:
the story is the mean episode reward the tables print, in the order they
print it, at the counter each table states.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path

import pytest

from epochix.enums import TaskType
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.grade import metric_lower_better

LOGS = Path(__file__).resolve().parents[1] / "fixtures" / "logs"

_ROW = re.compile(r"^\|    (ep_rew_mean|iterations|total_timesteps) +\| (\S{1,40}) +\|", re.M)


def _printed(log: Path) -> list[tuple[float, float | None, float]]:
    """(reward, iterations, total_timesteps) of every table, from the text."""
    tables = log.read_text(encoding="utf-8").split("\n-")
    out = []
    for table in tables:
        rows = dict(_ROW.findall(table))
        if "ep_rew_mean" in rows:
            iterations = float(rows["iterations"]) if "iterations" in rows else None
            out.append((float(rows["ep_rew_mean"]), iterations, float(rows["total_timesteps"])))
    return out


def _run(log: Path) -> tuple[object, RunStore]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester("rl", str(log)), run_id="rl", store=store, hub=Hub()
        )
    )
    return run, store


@pytest.mark.parametrize(
    ("name", "counter", "tables"),
    [("sb3_ppo_real.log", "iteration", 25), ("sb3_dqn_real.log", "step", 105)],
)
def test_the_run_is_told_by_its_reward(name: str, counter: str, tables: int) -> None:
    log = LOGS / name
    printed = _printed(log)
    assert len(printed) == tables, "the recording is not the one these numbers describe"

    run, store = _run(log)
    frames = store.get_story_frames("rl")
    assert run.parser_used == "stable_baselines3"
    assert run.task_type is TaskType.REINFORCEMENT
    assert run.primary_metric == "ep_rew_mean"

    # One frame per table, each the reward that table printed, at its counter.
    assert [f.primary_metric_value for f in frames] == [reward for reward, _, _ in printed]
    expected_at = [it if counter == "iteration" else steps for _, it, steps in printed]
    assert [f.epoch for f in frames] == expected_at
    assert {f.counter for f in frames} == {counter}

    # Graded on its rise: a reward has no fixed scale.
    assert frames[-1].grade_basis == "improvement"
    assert metric_lower_better("ep_rew_mean") is False

    # The time/ section and the update count are counters, never charted.
    keys = {e.raw_key for e in store.get_metric_events("rl")}
    assert "rollout/ep_rew_mean" in keys
    assert not any(k.startswith("time/") for k in keys), keys
    assert "train/n_updates" not in keys


def test_a_rising_reward_is_never_told_it_has_not_moved() -> None:
    """Measured against 1.0, a reward from 21.2 had "not moved" at 395."""
    _, store = _run(LOGS / "sb3_ppo_real.log")
    frames = store.get_story_frames("rl")
    assert frames[-1].phase.value == "polishing"
    for frame in frames:
        assert not re.search(r"barely|where it started|no meaningful", frame.narrative, re.I), (
            frame.narrative
        )


def test_epochix_check_reads_the_run() -> None:
    """The command a user runs on a log names what the run counts by."""
    out = subprocess.run(
        [sys.executable, "-m", "epochix", "check", str(LOGS / "sb3_ppo_real.log")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=True,
    ).stdout
    assert re.search(r"parser\s+stable_baselines3", out), out
    assert re.search(r"task\s+reinforcement", out), out
    assert re.search(r"iterations seen\s+25", out), out
    assert re.search(r"ep_rew_mean +25 values +21.2 -> 395", out), out
