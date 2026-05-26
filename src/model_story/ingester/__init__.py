from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model_story.models import RawLogLine


class BaseIngester(ABC):
    """Abstract base for all log ingesters.

    Concrete implementations cover: stdin (live pipe), file tail, SDK push.
    Each implementation is an async generator of :class:`RawLogLine` objects.
    """

    @abstractmethod
    def lines(self) -> AsyncIterator[RawLogLine]:
        """Yield :class:`RawLogLine` objects as they arrive."""
        ...


def make_ingester(
    *,
    source: str = "stdin",
    run_id: str,
    path: str | None = None,
    poll_interval: float = 0.1,
    ssh_target: str | None = None,
    ssh_port: int | None = None,
    ssh_identity: str | None = None,
    ssh_opts: tuple[str, ...] = (),
) -> BaseIngester:
    """Factory: return the right ingester for *source*.

    Parameters
    ----------
    source:
        One of ``"stdin"``, ``"file"`` (batch — reads once and stops),
        ``"file_tail"`` (live tail — polls indefinitely), ``"sdk"``,
        ``"ssh"`` (remote tail over ssh).
    run_id:
        The run identifier stamped on every :class:`RawLogLine`.
    path:
        Required when *source* is ``"file"``, ``"file_tail"`` or ``"ssh"``
        (for ``"ssh"`` it's the **remote** path).
    poll_interval:
        Polling interval in seconds used by ``"file_tail"`` (default 0.1 s).
    ssh_target / ssh_port / ssh_identity / ssh_opts:
        Used only when *source* is ``"ssh"``. ``ssh_target`` is ``user@host``
        (or just ``host``); ``ssh_opts`` is a tuple of ``key=value`` strings
        passed to ``ssh -o``.
    """
    if source == "stdin":
        from model_story.ingester.stdin import StdinIngester

        return StdinIngester(run_id=run_id)
    if source == "file":
        # Batch mode: read the file once and stop.
        if path is None:
            raise ValueError("path is required for the file ingester")
        from model_story.ingester.file_batch import FileBatchIngester

        return FileBatchIngester(run_id=run_id, path=path)
    if source == "file_tail":
        # Live/tail mode: poll the file indefinitely.
        if path is None:
            raise ValueError("path is required for the file_tail ingester")
        from model_story.ingester.file_tail import FileTailIngester

        return FileTailIngester(run_id=run_id, path=path, poll_interval=poll_interval)
    if source == "sdk":
        from model_story.ingester.sdk_receiver import SDKReceiver

        return SDKReceiver(run_id=run_id)
    if source == "ssh":
        if ssh_target is None or path is None:
            raise ValueError("ssh_target and path are required for the ssh ingester")
        from model_story.ingester.ssh import SSHIngester

        return SSHIngester(
            run_id=run_id,
            target=ssh_target,
            remote_path=path,
            port=ssh_port,
            identity=ssh_identity,
            extra_opts=ssh_opts,
        )
    raise ValueError(f"Unknown ingester source: {source!r}")
