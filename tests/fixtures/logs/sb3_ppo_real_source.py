"""PPO on CartPole with Stable-Baselines3, console output kept.

Stable-Baselines3 prints a table per iteration at `verbose=1`: a rule of
dashes, a row naming a section (`| rollout/ |`), that section's rows indented
under it (`|    ep_rew_mean | 22.4 |`), and a closing rule. PPO's first table
has no `train/` section, because it is printed before the first update.

    Needs:  pip install stable-baselines3
    Run:    python sb3_ppo_real_source.py > sb3_ppo_real.log 2>&1

Run from a neutral folder. Gymnasium's bundled CartPole-v1, CPU.
"""

from __future__ import annotations

import warnings

# Python warnings print the path of the file that raised them.
warnings.filterwarnings("ignore")

from stable_baselines3 import PPO  # noqa: E402

model = PPO("MlpPolicy", "CartPole-v1", seed=3, device="cpu", verbose=1)
model.learn(total_timesteps=50_000)
