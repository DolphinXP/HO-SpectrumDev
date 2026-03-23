"""Thread-safe ping-pong double buffer for frame delivery.

Adapted from the DataPingPong pattern: the producer (acquisition thread)
writes via ``ping()`` only when the consumer (UI thread) has already
consumed the previous data.  The consumer calls ``pong()`` to retrieve
the latest frame.  At most one frame is ever buffered — if the UI is
slow, intermediate frames are silently dropped, keeping the UI responsive.
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np


class FramePingPong:
    """Lock-free-style double buffer for (frame, metadata) pairs.

    Thread safety is achieved with a single mutex; the critical section
    is kept tiny (pointer swap, flag flip) so contention is negligible.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._can_pong: bool = False
        # Ping side — written by producer
        self._ping_frame: np.ndarray | None = None
        self._ping_meta: dict | None = None
        # Pong side — read by consumer
        self._pong_frame: np.ndarray | None = None
        self._pong_meta: dict | None = None

    def ping(self, frame: np.ndarray, metadata: dict) -> bool:
        """Offer a new frame to the consumer.

        Returns ``True`` if the frame was accepted (consumer already
        consumed the previous one).  Returns ``False`` if the consumer
        hasn't picked up the last frame yet — the caller should drop
        this frame.
        """
        with self._lock:
            if not self._can_pong:
                self._ping_frame = frame
                self._ping_meta = metadata
                self._can_pong = True
                return True
            return False

    def pong(self) -> tuple[np.ndarray, dict] | None:
        """Retrieve the latest frame if one is available.

        Returns ``(frame, metadata)`` or ``None`` if no new frame has
        been written since the last ``pong()`` call.
        """
        with self._lock:
            if self._can_pong:
                self._pong_frame = self._ping_frame
                self._pong_meta = self._ping_meta
                self._can_pong = False
                return self._pong_frame, self._pong_meta
            return None
