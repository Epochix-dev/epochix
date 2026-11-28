"""DQN on CartPole with Stable-Baselines3, console output kept.

An off-policy algorithm prints its table every `log_interval` episodes, not
every rollout: `time/episodes` and `time/total_timesteps` are its counters,
and there is no `time/iterations`. Its `rollout/` section carries the
exploration rate beside the episode reward and length, and `train/` its loss
and update count.

The settings are the RL Zoo's for DQN on CartPole-v1, at 50,000 steps.

    Needs:  pip install stable-baselines3
    Run:    python sb3_dqn_real_source.py > sb3_dqn_real.log 2>&1

Run from a neutral folder. Gymnasium's bundled CartPole-v1, CPU.
"""

from __future__ import annotations

import warnings

# Python warnings print the path of the file that raised them.
warnings.filterwarnings("ignore")

from stable_baselines3 import DQN  # noqa: E402

model = DQN(
    "MlpPolicy",
    "CartPole-v1",
    learning_rate=2.3e-3,
    batch_size=64,
    buffer_size=100_000,
    learning_starts=1000,
    gamma=0.99,
    target_update_interval=10,
    train_freq=256,
    gradient_steps=128,
    exploration_fraction=0.16,
    exploration_final_eps=0.04,
    policy_kwargs={"net_arch": [256, 256]},
    seed=3,
    device="cpu",
    verbose=1,
)
model.learn(total_timesteps=50_000, log_interval=4)
