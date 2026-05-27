"""epochix framework integrations.

Available integrations
----------------------
- :mod:`epochix.integrations.lightning` — PyTorch Lightning callback
- :mod:`epochix.integrations.hf` — HuggingFace Trainer callback
- :mod:`epochix.integrations.jupyter` — ``%epochix`` cell magic
- :mod:`epochix.integrations.tensorboard_import` — import TensorBoard logdirs
- :mod:`epochix.integrations.wandb_import` — import W&B run history

All integrations are lazily imported so that missing optional dependencies
(``lightning``, ``transformers``, ``IPython``, ``tensorboard``, ``wandb``)
do not cause import errors.
"""
