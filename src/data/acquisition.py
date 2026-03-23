"""Acquisition worker thread.

Receives raw frames from a :class:`DeviceInterface`, applies optional NUC
correction, computes live statistics, and delivers processed frames via a
:class:`FramePingPong` double buffer.

The ping-pong pattern ensures the UI thread is never flooded with queued
frame signals.  The UI polls via QTimer at its own pace; if it can't keep
up, intermediate frames are silently dropped instead of queueing.
"""

from __future__ import annotations

import logging
import time
from collections import deque

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from src.data.frame_ping_pong import FramePingPong
from src.data.nuc import NUCProcessor
from src.device.device_interface import DeviceInterface

logger = logging.getLogger("gpy4.acquisition")

# Rolling window size for FPS / throughput averaging
_FPS_WINDOW = 30


class AcquisitionWorker(QThread):
    """QThread that sits between a camera device and the rest of the app.

    Attributes
    ----------
    frame_buffer : FramePingPong
        Shared double buffer.  The worker ``ping()``s processed frames
        into it; the UI ``pong()``s them out at its own refresh rate.

    Signals
    -------
    stats_updated : Signal(dict)
        Periodic statistics: ``fps``, ``frame_count``, ``dropped_count``,
        ``mbps``, ``display_dropped``.
    """

    stats_updated = Signal(dict)

    def __init__(
        self,
        device: DeviceInterface,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._device = device
        self._nuc = NUCProcessor()

        # Ping-pong double buffer — shared with UI
        self.frame_buffer = FramePingPong()

        # Statistics bookkeeping
        self._frame_count: int = 0
        self._dropped_count: int = 0
        self._display_dropped: int = 0
        self._last_frame_id: int = -1
        self._timestamps: deque[float] = deque(maxlen=_FPS_WINDOW)
        self._byte_sizes: deque[int] = deque(maxlen=_FPS_WINDOW)
        self._running: bool = False

        # Throttle stats signal to ~4 Hz
        self._last_stats_time: float = 0.0

    # ------------------------------------------------------------------
    # NUC access
    # ------------------------------------------------------------------

    @property
    def nuc(self) -> NUCProcessor:
        """Access the NUC processor to load / unload coefficients."""
        return self._nuc

    # ------------------------------------------------------------------
    # QThread lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the thread event loop."""
        self._running = True
        self._frame_count = 0
        self._dropped_count = 0
        self._display_dropped = 0
        self._last_frame_id = -1
        self._last_stats_time = 0.0
        self._timestamps.clear()
        self._byte_sizes.clear()

        # Connect device signal to our slot (queued across threads)
        self._device.frame_acquired.connect(
            self._on_frame_acquired
        )
        logger.info("Acquisition worker started")
        self.exec()  # enter Qt event loop

    def stop(self) -> None:
        """Request the worker to stop and wait for the thread to finish."""
        self._running = False
        try:
            self._device.frame_acquired.disconnect(self._on_frame_acquired)
        except RuntimeError:
            pass  # already disconnected
        self.quit()
        self.wait()
        logger.info(
            "Acquisition worker stopped: %d frames, %d dropped, %d display-dropped",
            self._frame_count,
            self._dropped_count,
            self._display_dropped,
        )

    # ------------------------------------------------------------------
    # Frame processing slot
    # ------------------------------------------------------------------

    @Slot(np.ndarray, dict)
    def _on_frame_acquired(
        self, frame: np.ndarray, metadata: dict
    ) -> None:
        """Process an incoming raw frame from the device."""
        if not self._running:
            return

        now = time.perf_counter()

        # Detect dropped frames via frame_id gap
        frame_id = metadata.get("frame_id", self._last_frame_id + 1)
        if self._last_frame_id >= 0:
            gap = frame_id - self._last_frame_id - 1
            if gap > 0:
                self._dropped_count += gap
                logger.warning("Dropped %d frame(s) (id %d -> %d)",
                               gap, self._last_frame_id, frame_id)
        self._last_frame_id = frame_id

        # Apply NUC
        processed = self._nuc.apply(frame)

        self._frame_count += 1
        frame_bytes = frame.nbytes
        self._timestamps.append(now)
        self._byte_sizes.append(frame_bytes)

        # Write to ping-pong buffer — if UI hasn't consumed the last
        # frame yet, this frame is dropped (back-pressure).
        if not self.frame_buffer.ping(processed, metadata):
            self._display_dropped += 1

        # Throttle stats signal to ~4 Hz to avoid event queue pressure
        if now - self._last_stats_time >= 0.25:
            self._last_stats_time = now
            stats = self._compute_stats()
            self.stats_updated.emit(stats)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _compute_stats(self) -> dict:
        """Compute FPS and throughput from the rolling window."""
        fps = 0.0
        mbps = 0.0

        if len(self._timestamps) >= 2:
            dt = self._timestamps[-1] - self._timestamps[0]
            if dt > 0:
                n = len(self._timestamps) - 1
                fps = n / dt
                total_bytes = sum(
                    list(self._byte_sizes)[1:]
                )  # bytes in the window excluding first
                mbps = (total_bytes / dt) / (1024 * 1024)

        return {
            "fps": round(fps, 1),
            "frame_count": self._frame_count,
            "dropped_count": self._dropped_count,
            "display_dropped": self._display_dropped,
            "mbps": round(mbps, 2),
        }
