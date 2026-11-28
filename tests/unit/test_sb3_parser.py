"""The Stable-Baselines3 table, line by line (parsers/stable_baselines3.py).

Every table here is copied from the two recordings
(tests/fixtures/logs/sb3_ppo_real.log, sb3_dqn_real.log). The lines are fed
to the parser directly, so they are recorded for the extension's replay
(parsers.golden.json): each test starts from an empty context.
"""

from __future__ import annotations

from pathlib import Path

from epochix.models import RawMetric
from epochix.parsers.base import COUNTED_BY, LINE_CLAIMED, ParserContext
from epochix.parsers.registry import detect_parser
from epochix.parsers.stable_baselines3 import StableBaselines3Parser

# PPO's first table: printed before the first update, so no train/ section.
PPO_FIRST = """\
---------------------------------
| rollout/           |          |
|    ep_len_mean     | 21.2     |
|    ep_rew_mean     | 21.2     |
| time/              |          |
|    fps             | 2746     |
|    iterations      | 1        |
|    time_elapsed    | 0        |
|    total_timesteps | 2048     |
---------------------------------"""

PPO_SECOND = """\
-----------------------------------------
| rollout/                |             |
|    ep_len_mean          | 25.8        |
|    ep_rew_mean          | 25.8        |
| time/                   |             |
|    fps                  | 1846        |
|    iterations           | 2           |
|    time_elapsed         | 2           |
|    total_timesteps      | 4096        |
| train/                  |             |
|    approx_kl            | 0.007685787 |
|    clip_fraction        | 0.0901      |
|    clip_range           | 0.2         |
|    entropy_loss         | -0.686      |
|    explained_variance   | 0.00255     |
|    learning_rate        | 0.0003      |
|    loss                 | 7.28        |
|    n_updates            | 10          |
|    policy_gradient_loss | -0.014      |
|    value_loss           | 49.1        |
-----------------------------------------"""

DQN_TABLE = """\
----------------------------------
| rollout/            |          |
|    ep_len_mean      | 249      |
|    ep_rew_mean      | 249      |
|    exploration_rate | 0.04     |
| time/               |          |
|    episodes         | 420      |
|    fps              | 1232     |
|    time_elapsed     | 39       |
|    total_timesteps  | 49105    |
| train/              |          |
|    learning_rate    | 0.0023   |
|    loss             | 0.525    |
|    n_updates        | 24064    |
----------------------------------"""


def _feed(text: str, ctx: ParserContext, parser: StableBaselines3Parser) -> list[list[RawMetric]]:
    """Each line's result, with what the line claimed and counted by."""
    out = []
    for line in text.splitlines():
        ctx.seq += 1
        got = parser.parse_line(line, ctx)
        assert got or ctx.extra.pop(LINE_CLAIMED, False), f"not claimed: {line!r}"
        ctx.extra.pop(LINE_CLAIMED, None)
        out.append(got)
    return out


def test_a_table_is_told_whole_on_its_closing_rule() -> None:
    parser, ctx = StableBaselines3Parser(), ParserContext(run_id="t")
    results = _feed(PPO_SECOND, ctx, parser)
    # Every line before the closing rule is claimed and reads nothing.
    assert all(r == [] for r in results[:-1])
    told = {m.key: m.value for m in results[-1]}
    assert told == {
        "rollout/ep_len_mean": 25.8,
        "rollout/ep_rew_mean": 25.8,
        "train/approx_kl": 0.007685787,
        "train/clip_fraction": 0.0901,
        "train/clip_range": 0.2,
        "train/entropy_loss": -0.686,
        "train/explained_variance": 0.00255,
        "train/learning_rate": 0.0003,
        "train/loss": 7.28,
        "train/policy_gradient_loss": -0.014,
        "train/value_loss": 49.1,
    }
    # The counters and timings are not readings, nor is the update count.
    assert not any(k.startswith("time/") for k in told)
    assert "train/n_updates" not in told


def test_an_on_policy_table_counts_by_iteration() -> None:
    """PPO runs ten epochs over each rollout: iteration 2 is not epoch 2."""
    parser, ctx = StableBaselines3Parser(), ParserContext(run_id="t")
    *_, last = _feed(PPO_SECOND, ctx, parser)
    assert {(m.epoch, m.step) for m in last} == {(2.0, 4096)}
    assert ctx.extra.get(COUNTED_BY) == "iteration"


def test_an_off_policy_table_counts_by_step() -> None:
    """DQN prints episodes and steps and no iterations: told by step."""
    parser, ctx = StableBaselines3Parser(), ParserContext(run_id="t")
    *_, last = _feed(DQN_TABLE, ctx, parser)
    assert {(m.epoch, m.step) for m in last} == {(49105.0, 49105)}
    assert ctx.extra.get(COUNTED_BY) == "step"
    assert {m.key for m in last} == {
        "rollout/ep_len_mean",
        "rollout/ep_rew_mean",
        "rollout/exploration_rate",
        "train/learning_rate",
        "train/loss",
    }


def test_tables_one_after_another_are_each_their_own() -> None:
    """The closing rule of one table is followed at once by the next one's
    opening rule; nothing of the first reaches the second."""
    parser, ctx = StableBaselines3Parser(), ParserContext(run_id="t")
    first = _feed(PPO_FIRST, ctx, parser)[-1]
    second = _feed(PPO_SECOND, ctx, parser)[-1]
    assert {m.key for m in first} == {"rollout/ep_len_mean", "rollout/ep_rew_mean"}
    assert {m.epoch for m in first} == {1.0}
    assert {m.epoch for m in second} == {2.0}
    assert len(second) == 11


def test_a_row_outside_a_table_is_not_its() -> None:
    parser, ctx = StableBaselines3Parser(), ParserContext(run_id="t")
    assert parser.parse_line("|    ep_rew_mean          | 35          |", ctx) == []
    assert LINE_CLAIMED not in ctx.extra
    assert parser.parse_line("Using cpu device", ctx) == []
    assert LINE_CLAIMED not in ctx.extra


def test_a_value_that_is_not_a_number_is_claimed_and_not_read() -> None:
    parser, ctx = StableBaselines3Parser(), ParserContext(run_id="t")
    table = "-------------------\n| rollout/ |      |\n|    env | Cart |\n|    ep_rew_mean | 9 |\n-------------------"
    *_, last = _feed(table, ctx, parser)
    assert [(m.key, m.value) for m in last] == [("rollout/ep_rew_mean", 9.0)]


def test_the_recordings_choose_this_parser() -> None:
    for name in ("sb3_ppo_real.log", "sb3_dqn_real.log"):
        log = Path(__file__).resolve().parents[1] / "fixtures" / "logs" / name
        lines = log.read_text(encoding="utf-8").splitlines()[:200]
        assert detect_parser(lines).name == "stable_baselines3", name


def test_a_markdown_table_is_not_a_run() -> None:
    """A table with no section rows is somebody's notes, not SB3's logger."""
    notes = ["| name | value |", "|------|-------|", "| lr | 0.1 |", "-----------", "| a | 1 |"]
    assert StableBaselines3Parser().sniff(notes) == 0.0
