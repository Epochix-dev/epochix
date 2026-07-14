"""LiveReporter — Python SDK for pushing metrics from training code.

Usage
-----
::

    from epochix import LiveReporter

    reporter = LiveReporter(
        task="gaze",
        primary_metric="mae",
        name="gazeformer_v7",
    )
    for epoch in range(100):
        loss, mae = train_epoch()
        reporter.log(epoch=epoch, train_loss=loss, mae=mae)
    reporter.finish()

Or as a context manager::

    with LiveReporter(task="classification", name="resnet50") as reporter:
        for epoch in range(30):
            reporter.log(epoch=epoch, val_accuracy=acc, val_loss=loss)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading

from epochix.config import get_settings
from epochix.enums import TaskType

logger = logging.getLogger(__name__)


class LiveReporter:
    """Push metrics from the training loop directly to epochix.

    Does NOT require log parsing — the caller supplies key-value metrics.
    Under the hood the reporter formats them as a log line, feeds them
    through the SDK receiver, and runs the full pipeline in a background
    asyncio event loop on a dedicated thread.

    Thread-safety: :meth:`log` and :meth:`finish` are safe to call from
    any thread (including the PyTorch DataLoader worker threads).
    """

    def __init__(
        self,
        *,
        task: str | TaskType | None = None,
        primary_metric: str | None = None,
        name: str | None = None,
        total_epochs: int | None = None,
        port: int = 7860,
        open_browser: bool = True,
        locale: str = "en",
        run_id: str | None = None,
        model: object | None = None,
        capture_activations: bool = False,
        activation_hz: float = 2.0,
        capture_gradients: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        task:
            Task type (``"gaze"``, ``"detection"``, ``"classification"``, …).
            Leave ``None`` to auto-detect from the metrics you log.
        primary_metric:
            Which logged metric drives the grade / phase / narrative. Pass the
            **same name you use in** :meth:`log` — any spelling works, it is
            normalised internally (``"val_mae_cm"``, ``"mae"`` and
            ``"MAE"`` all resolve to the same metric). Optional: when omitted,
            the task's standard metric is used (gaze/regression → MAE,
            classification → val_accuracy, detection → mAP50, …), which is the
            recommended default — only set this to override.
        name:
            Human-readable run name shown in the dashboard.
        total_epochs:
            Total planned epochs, used for the progress bar. Optional.
        port:
            Local dashboard port. Use a free port if you run several at once.
        open_browser:
            Open the dashboard in a browser tab on start (default True).
        locale:
            Dashboard language (``"en"`` / ``"fa"`` / ``"fr"``).
        run_id:
            Explicit run id; auto-generated when omitted.
        model:
            The model being trained (PyTorch ``nn.Module`` or Keras ``Model``).
            When given, its **real** architecture — actual layer names, types
            and parameter counts — is shown in the dashboard's Network State
            panel. Omitted → the panel honestly reports no architecture rather
            than showing a placeholder.
        capture_activations:
            When True (and a ``model`` is given), register forward hooks that
            capture **real** per-layer activation magnitudes and dead-unit
            fractions during training, so the Network State panel animates from
            measured values instead of a schematic. Default False — zero
            overhead unless you opt in. Requires PyTorch or Keras.
        activation_hz:
            Cap on how often each layer's activation is sampled (Hz). ``.item()``
            forces a GPU sync, so this wall-clock throttle keeps the overhead
            negligible. Default 2 Hz.
        capture_gradients:
            When capturing, also register backward hooks for mean ``|gradient|``
            per layer (PyTorch only). Default True; ignored unless
            ``capture_activations`` is on.
        """
        from epochix.sdk.architecture import architecture_from_model

        self._task: TaskType | None = TaskType(task) if isinstance(task, str) else task
        self._primary_metric = primary_metric
        self._name = name
        self._total_epochs = total_epochs
        self._port = port
        self._open_browser = open_browser
        self._locale = locale
        self._run_id = run_id or self._generate_run_id()
        self._architecture = architecture_from_model(model)
        self._model = model
        self._capture_activations = capture_activations
        self._activation_hz = activation_hz
        self._capture_gradients = capture_gradients
        self._capturer: object | None = None
        self._emit_activations: object | None = None
        self._store: object | None = None
        self._seq = 0

        self._receiver: object | None = None  # SDKReceiver, lazy
        self._pipeline_task: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, **metrics: float) -> None:
        """Push one epoch of metrics.

        All keyword arguments are treated as metric key-value pairs.
        The special key ``epoch`` is used to track training progress.

        Example::

            reporter.log(epoch=5, train_loss=0.312, val_accuracy=0.871)
        """
        if not self._started:
            self._start()

        line = "  ".join(f"{k}={v}" for k, v in metrics.items())
        self._push(line)
        self._flush_activations()
        self._seq += 1

    def log_line(self, text: str) -> None:
        """Feed one raw log line — exactly as a training script printed it —
        to the parser.

        Use this when you are relaying somebody else's stdout (a subprocess, a
        notebook cell) and the metrics are already formatted in the line. It is
        the same path ``epochix --live`` takes, so every parser applies.

        Example::

            reporter.log_line("Epoch 3/10 train_loss=0.42 val_accuracy=0.88")
        """
        if not self._started:
            self._start()
        self._push(text)
        self._seq += 1

    def _push(self, line: str) -> None:
        if self._receiver is not None:
            from epochix.ingester.sdk_receiver import SDKReceiver

            assert isinstance(self._receiver, SDKReceiver)
            self._receiver.push_line(line)

    def finish(self) -> None:
        """Signal end of training and wait for the pipeline to flush."""
        if not self._started:
            return
        final_snapshot: dict[str, dict[str, float]] = {}
        if self._capturer is not None:
            from epochix.sdk.activations import ActivationCapturer

            assert isinstance(self._capturer, ActivationCapturer)
            final_snapshot = self._capturer.snapshot()
            self._capturer.remove()
            self._capturer = None
        if self._receiver is not None:
            from epochix.ingester.sdk_receiver import SDKReceiver

            assert isinstance(self._receiver, SDKReceiver)
            self._receiver.close()
        if self._thread is not None:
            self._thread.join(timeout=30)
        # The pipeline has now created the run row and stopped its loop, so a
        # final synchronous persist guarantees the last real snapshot lands in
        # run.config even for runs that finish faster than the loop started
        # (where the per-epoch live emits raced ahead of run creation).
        self._persist_final_activations(final_snapshot)
        self._started = False

    def _persist_final_activations(self, snapshot: dict[str, dict[str, float]]) -> None:
        if not snapshot or self._store is None:
            return
        from epochix.store.sqlite_store import RunStore

        if not isinstance(self._store, RunStore):
            return
        try:
            existing = self._store.get_run(self._run_id)
            if existing is None:
                return  # run never materialised (nothing logged) — nothing to attach to
            cfg = existing.config
            self._store.update_run_config(self._run_id, {**cfg, "activations": snapshot})
        except Exception:  # noqa: BLE001 — teardown telemetry must never raise
            pass

    def _flush_activations(self) -> None:
        """Snapshot the latest activations and hand them to the pipeline loop.

        Runs on the *training* thread (from :meth:`log`); the store/hub writes
        are scheduled onto the background event loop so all persistence and
        broadcasting stays single-threaded. A no-op until capture is on and the
        loop is up (early ``log`` calls before the thread's loop exists are
        simply skipped — the next epoch's snapshot supersedes them anyway).
        """
        if self._capturer is None or self._loop is None or self._emit_activations is None:
            return
        from epochix.sdk.activations import ActivationCapturer

        assert isinstance(self._capturer, ActivationCapturer)
        snapshot = self._capturer.snapshot()
        if not snapshot:
            return
        emit = self._emit_activations
        # Loop already closed (finish in progress) → nothing to flush.
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(emit, snapshot)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> LiveReporter:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.finish()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start(self) -> None:
        """Lazy start: spin up the background event loop + pipeline."""
        self._started = True
        settings = get_settings()

        from epochix.ingester.sdk_receiver import SDKReceiver
        from epochix.pipeline import run_pipeline
        from epochix.server.app import create_app
        from epochix.server.hub import Hub
        from epochix.store.sqlite_store import RunStore

        receiver = SDKReceiver(run_id=self._run_id)
        self._receiver = receiver

        store = RunStore(db_path=settings.db)
        hub = Hub()
        _app = create_app(settings=settings)
        _app.state.store = store
        _app.state.hub = hub
        _app.state.engine_map = {}

        if self._capture_activations and self._model is not None:
            from epochix.sdk.activations import ActivationCapturer

            self._capturer = ActivationCapturer(
                self._model, hz=self._activation_hz, gradients=self._capture_gradients
            )
            self._store = store
            self._emit_activations = self._make_emit(store, hub, run_id=self._run_id)

        port = self._port
        run_id = self._run_id
        task = self._task
        name = self._name
        primary_metric = self._primary_metric
        total_epochs = self._total_epochs
        locale = self._locale
        open_browser = self._open_browser
        architecture = self._architecture

        async def _pipeline() -> None:
            import uvicorn

            config = uvicorn.Config(
                _app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                lifespan="off",
            )
            server = uvicorn.Server(config)
            server_task = asyncio.create_task(server.serve())
            await asyncio.sleep(0.5)
            if open_browser:
                import webbrowser

                webbrowser.open(f"http://127.0.0.1:{port}/v/{run_id}")
            try:
                await run_pipeline(
                    ingester=receiver,
                    run_id=run_id,
                    store=store,
                    hub=hub,
                    run_name=name,
                    task=task,
                    primary_metric=primary_metric,
                    total_epochs=total_epochs,
                    locale=locale,
                    architecture=architecture,
                )
            finally:
                server.should_exit = True
                await server_task

        def _thread_main() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_pipeline())
            loop.close()

        thread = threading.Thread(
            target=_thread_main, daemon=True, name=f"epochix-pipeline-{run_id[:8]}"
        )
        self._thread = thread
        thread.start()

    def _make_emit(self, store: object, hub: object, *, run_id: str) -> object:
        """Build the callback that persists + broadcasts an activation snapshot.

        The returned function runs on the background event loop (scheduled via
        ``call_soon_threadsafe``), so its store/hub access is single-threaded
        alongside the pipeline. Persisting the latest snapshot in
        ``run.config["activations"]`` means a dashboard opened mid/after-run
        still shows real values, not just live WS subscribers.
        """

        def emit(snapshot: dict[str, dict[str, float]]) -> None:
            try:
                existing = store.get_run(run_id)  # type: ignore[attr-defined]
                cfg = existing.config if existing else {}
                store.update_run_config(  # type: ignore[attr-defined]
                    run_id, {**cfg, "activations": snapshot}
                )
                hub.publish(  # type: ignore[attr-defined]
                    run_id,
                    hub.make_message(  # type: ignore[attr-defined]
                        msg_type="activations",
                        run_id=run_id,
                        seq=-1,
                        payload={"layers": snapshot},
                    ),
                )
            except Exception:  # noqa: BLE001 — telemetry must never break training
                pass

        return emit

    @staticmethod
    def _generate_run_id() -> str:
        try:
            from ulid import ULID

            return str(ULID())
        except ImportError:
            import uuid

            return str(uuid.uuid4())
