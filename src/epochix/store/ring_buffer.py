from __future__ import annotations

import threading
from collections import deque
from typing import Generic, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    """Thread-safe bounded ring buffer for live stream replay."""

    def __init__(self, maxlen: int = 2048) -> None:
        self._buf: deque[T] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, item: T) -> None:
        with self._lock:
            self._buf.append(item)

    def since(self, seq: int) -> list[T]:
        """Return all items whose .seq attribute is > seq."""
        with self._lock:
            items = list(self._buf)
        return [i for i in items if getattr(i, "seq", 0) > seq]

    def latest(self, n: int = 1) -> list[T]:
        with self._lock:
            return list(self._buf)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)
