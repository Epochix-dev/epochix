"""HuggingFace Transformers Trainer callback integration.

Usage::

    from epochix.integrations.hf import StoryCallback
    from transformers import Trainer, TrainingArguments

    trainer = Trainer(
        model=model,
        args=TrainingArguments(...),
        callbacks=[StoryCallback(task="nlp", primary_metric="eval_f1")],
    )
    trainer.train()

The callback wraps :class:`~epochix.sdk.live_reporter.LiveReporter`
and maps HuggingFace ``TrainerCallback`` hooks to ``reporter.log()``.

``transformers`` is an optional dependency — this module imports it lazily.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from epochix.enums import TaskType


class StoryCallback:
    """Report HuggingFace Trainer metrics to epochix.

    Parameters
    ----------
    task:
        Task type hint (e.g. ``"nlp"``, ``"classification"``).
    primary_metric:
        The key in the logged metrics dict to use for grading.
        Defaults to ``"eval_loss"`` if not set.
    name:
        Human-readable run name.
    port:
        Port for the embedded dashboard server.
    open_browser:
        Open the dashboard in a browser when training starts.
    locale:
        Dashboard locale (``"en"``, ``"fa"``, ``"fr"``).
    """

    def __init__(
        self,
        *,
        task: str | TaskType | None = None,
        primary_metric: str | None = None,
        name: str | None = None,
        port: int = 7860,
        open_browser: bool = True,
        locale: str = "en",
    ) -> None:
        self._task = task
        self._primary_metric = primary_metric or "eval_loss"
        self._name = name
        self._port = port
        self._open_browser = open_browser
        self._locale = locale
        self._reporter: Any = None  # noqa: ANN401

    # ------------------------------------------------------------------
    # HuggingFace TrainerCallback interface
    # ------------------------------------------------------------------

    def on_train_begin(  # noqa: ANN401
        self,
        args: Any,  # noqa: ANN401
        state: Any,  # noqa: ANN401
        control: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Start the reporter when training begins."""
        from epochix.sdk.live_reporter import LiveReporter

        name = self._name or _get_run_name(args)
        total_epochs: int | None = None
        if hasattr(args, "num_train_epochs"):
            with contextlib.suppress(TypeError, ValueError):
                total_epochs = int(args.num_train_epochs)

        self._reporter = LiveReporter(
            task=self._task,
            primary_metric=self._primary_metric,
            name=name,
            total_epochs=total_epochs,
            port=self._port,
            open_browser=self._open_browser,
            locale=self._locale,
        )

    def on_log(  # noqa: ANN401
        self,
        args: Any,  # noqa: ANN401
        state: Any,  # noqa: ANN401
        control: Any,  # noqa: ANN401
        logs: dict[str, Any] | None = None,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Push metrics on each ``trainer.log()`` call."""
        if self._reporter is None or not logs:
            return
        metrics = _flat_floats(logs)
        # Map HF epoch (float) to our integer epoch
        epoch = state.epoch if (state and hasattr(state, "epoch")) else None
        if epoch is not None:
            metrics["epoch"] = float(epoch)
        if metrics:
            self._reporter.log(**metrics)

    def on_train_end(  # noqa: ANN401
        self,
        args: Any,  # noqa: ANN401
        state: Any,  # noqa: ANN401
        control: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Flush the reporter when training finishes."""
        if self._reporter is not None:
            self._reporter.finish()
            self._reporter = None

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init_subclass__(**kwargs)


# ── helpers ───────────────────────────────────────────────────────────────────


def _get_run_name(args: Any) -> str:  # noqa: ANN401
    return str(getattr(args, "run_name", None) or getattr(args, "output_dir", "hf-run"))


def _flat_floats(d: dict[str, Any]) -> dict[str, float]:  # noqa: ANN401
    result: dict[str, float] = {}
    for k, v in d.items():
        with contextlib.suppress(TypeError, ValueError):
            result[k] = float(v)
    return result


# ── Make StoryCallback a proper HF TrainerCallback when transformers is available
# This is done at import time so `isinstance(cb, TrainerCallback)` works.

try:
    from transformers import TrainerCallback as _TC  # type: ignore[import-not-found]

    class StoryCallback(_TC, StoryCallback):  # type: ignore[no-redef,misc]
        """StoryCallback with HuggingFace TrainerCallback base class."""

except ImportError:
    pass  # StoryCallback remains a plain Python class
