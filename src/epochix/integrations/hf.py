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
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from epochix.enums import TaskType


def _callback_base() -> type:
    """HuggingFace's ``TrainerCallback``, or ``object`` when it isn't installed.

    Subclassing matters twice over: the Trainer resolves every hook by bare
    ``getattr(callback, event)`` (so missing hooks raise), and inheriting gives
    us no-op defaults for the events we don't care about.
    """
    try:
        from transformers import TrainerCallback
    except ImportError:
        return object
    else:
        return cast("type", TrainerCallback)


# mypy runs in an env without transformers, so keep the base static for type
# checking and resolve it dynamically at runtime.
if TYPE_CHECKING:
    _Base = object
else:
    _Base = _callback_base()


class StoryCallback(_Base):
    """Report HuggingFace Trainer metrics to epochix.

    Parameters
    ----------
    task:
        Task type hint (e.g. ``"nlp"``, ``"classification"``).
    primary_metric:
        The key in the logged metrics dict to use for grading. When unset the
        task decides (e.g. ``eval_accuracy`` for classification) — do not
        default it to a loss, or a healthy classifier gets graded on its loss
        and lands at F.
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
        super().__init__()
        self._task = task
        self._primary_metric = primary_metric
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


# ── helpers ───────────────────────────────────────────────────────────────────


def _get_run_name(args: Any) -> str:  # noqa: ANN401
    return str(getattr(args, "run_name", None) or getattr(args, "output_dir", "hf-run"))


# HF logs throughput/timing bookkeeping alongside the real metrics. They are
# numbers, but they are not training signal — without this filter they land as
# a pile of "custom" metrics on the dashboard (and can muddy task detection for
# runs that don't pass an explicit task=).
_TELEMETRY_SUFFIXES = ("_runtime", "_samples_per_second", "_steps_per_second")
_TELEMETRY_KEYS = frozenset({"total_flos", "num_tokens"})


def _is_telemetry(key: str) -> bool:
    k = key.lower()
    return k in _TELEMETRY_KEYS or k.endswith(_TELEMETRY_SUFFIXES)


def _flat_floats(d: dict[str, Any]) -> dict[str, float]:  # noqa: ANN401
    result: dict[str, float] = {}
    for k, v in d.items():
        if _is_telemetry(k):
            continue
        with contextlib.suppress(TypeError, ValueError):
            result[k] = float(v)
    return result
