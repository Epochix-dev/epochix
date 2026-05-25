"""model-story framework integrations.

Available integrations
----------------------
- :mod:`model_story.integrations.lightning` — PyTorch Lightning callback
- :mod:`model_story.integrations.hf` — HuggingFace Trainer callback
- :mod:`model_story.integrations.jupyter` — ``%model_story`` cell magic
- :mod:`model_story.integrations.tensorboard_import` — import TensorBoard logdirs
- :mod:`model_story.integrations.wandb_import` — import W&B run history

All integrations are lazily imported so that missing optional dependencies
(``lightning``, ``transformers``, ``IPython``, ``tensorboard``, ``wandb``)
do not cause import errors.
"""
