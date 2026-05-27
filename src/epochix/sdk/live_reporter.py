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
    ) -> None:
        self._task: TaskType | None = (
            TaskType(task) if isinstance(task, str) else task
        )
        self._primary_metric = primary_metric
        self._name = name
        self._total_epochs = total_epochs
        self._port = port
        self._open_browser = open_browser
        self._locale = locale
        self._run_id = run_id or self._generate_run_id()
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
        if self._receiver is not None:
            from epochix.ingester.sdk_receiver import SDKReceiver

            assert isinstance(self._receiver, SDKReceiver)
            self._receiver.push_line(line)
        self._seq += 1

    def finish(self) -> None:
        """Signal end of training and wait for the pipeline to flush."""
        if not self._started:
            return
        if self._receiver is not None:
            from epochix.ingester.sdk_receiver import SDKReceiver

            assert isinstance(self._receiver, SDKReceiver)
            self._receiver.close()
        if self._thread is not None:
            self._thread.join(timeout=30)
        self._started = False

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

        port = self._port
        run_id = self._run_id
        task = self._task
        name = self._name
        primary_metric = self._primary_metric
        total_epochs = self._total_epochs
        locale = self._locale
        open_browser = self._open_browser

        async def _pipeline() -> None:
            import uvicorn

            config = uvicorn.Config(
                _app, host="127.0.0.1", port=port,
                log_level="warning", lifespan="off",
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

    @staticmethod
    def _generate_run_id() -> str:
        try:
            from ulid import ULID

            return str(ULID())
        except ImportError:
            import uuid

            return str(uuid.uuid4())
