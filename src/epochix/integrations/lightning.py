"""PyTorch Lightning callback integration.

Usage::

    from epochix.integrations.lightning import StoryCallback
    import lightning as pl

    trainer = pl.Trainer(callbacks=[StoryCallback(task="classification")])
    trainer.fit(model, datamodule=dm)

The callback wraps :class:`~epochix.sdk.live_reporter.LiveReporter`
and maps Lightning trainer hooks to ``reporter.log()`` / ``reporter.finish()``.

``pytorch_lightning`` (or ``lightning``) is an optional dependency — this
module imports it lazily so that importing ``epochix.integrations.lightning``
does not raise ``ImportError`` when Lightning is not installed.
"""
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from epochix.enums import TaskType


class StoryCallback:
    """Report training metrics to epochix via
    :class:`~epochix.sdk.live_reporter.LiveReporter`.

    Parameters
    ----------
    task:
        Task type hint (e.g. ``"classification"``, ``"detection"``).
        Passed directly to :class:`~epochix.sdk.live_reporter.LiveReporter`.
    primary_metric:
        The metric key to use for grading.  Defaults to ``"val_loss"`` for
        regression-like tasks, ``"val_accuracy"`` for classification.
    name:
        Human-readable run name.
    port:
        Port for the embedded dashboard server.
    open_browser:
        Open the dashboard in a browser when training starts.
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
        self._task           = task
        self._primary_metric = primary_metric
        self._name           = name
        self._port           = port
        self._open_browser   = open_browser
        self._locale         = locale
        self._reporter: Any  = None

    # ------------------------------------------------------------------
    # Lightning hooks
    # ------------------------------------------------------------------

    def on_train_start(self, trainer: Any, pl_module: Any) -> None:  # noqa: ANN401
        """Initialise the reporter when training begins."""
        from epochix.sdk.live_reporter import LiveReporter

        name = self._name or _get_model_name(pl_module)
        total_epochs: int | None = None
        if hasattr(trainer, "max_epochs") and trainer.max_epochs > 0:
            total_epochs = trainer.max_epochs

        self._reporter = LiveReporter(
            task=self._task,
            primary_metric=self._primary_metric,
            name=name,
            total_epochs=total_epochs,
            port=self._port,
            open_browser=self._open_browser,
            locale=self._locale,
        )

    def on_train_epoch_end(self, trainer: Any, pl_module: Any) -> None:  # noqa: ANN401
        """Log metrics at the end of each training epoch."""
        if self._reporter is None:
            return
        metrics = _collect_metrics(trainer)
        if metrics:
            self._reporter.log(**metrics)

    def on_validation_epoch_end(self, trainer: Any, pl_module: Any) -> None:  # noqa: ANN401
        """Also push validation metrics (same epoch slot)."""
        if self._reporter is None:
            return
        metrics = _collect_metrics(trainer)
        val_metrics = {k: v for k, v in metrics.items() if "val" in k.lower()}
        if val_metrics:
            self._reporter.log(**val_metrics)

    def on_train_end(self, trainer: Any, pl_module: Any) -> None:  # noqa: ANN401
        """Flush the reporter when training finishes."""
        if self._reporter is not None:
            self._reporter.finish()
            self._reporter = None

    def on_exception(self, trainer: Any, pl_module: Any, exception: BaseException) -> None:  # noqa: ANN401
        """Flush the reporter even if training crashed."""
        if self._reporter is not None:
            self._reporter.finish()
            self._reporter = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_model_name(pl_module: Any) -> str:  # noqa: ANN401
    return type(pl_module).__name__


def _collect_metrics(trainer: Any) -> dict[str, float]:  # noqa: ANN401
    """Extract a flat float dict from the trainer's logged metrics."""
    callback_metrics: dict[str, Any] = getattr(trainer, "callback_metrics", {})
    result: dict[str, float] = {}
    for k, v in callback_metrics.items():
        with contextlib.suppress(TypeError, ValueError):
            result[k] = float(v)
    # Always include the current epoch
    epoch: int | None = getattr(trainer, "current_epoch", None)
    if epoch is not None:
        result["epoch"] = float(epoch)
    return result
