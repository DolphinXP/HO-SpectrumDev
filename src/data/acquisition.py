"""Acquisition worker thread.

Receives raw frames from a :class:`DeviceInterface`, applies optional NUC
correction, computes live statistics, and re-emits the processed frame for
downstream consumers (UI, storage).
"""

from __future__ import annotations

import logging
import time
from collections import deque

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from src.data.nuc import NUCProcessor
from src.device.device_interface import DeviceInterface

logger = logging.getLogger("gpy4.acquisition")

# Rolling window size for FPS / throughput averaging
_FPS_WINDOW = 30


class AcquisitionWorker(QThread):
    """QThread that sits between a camera device and the rest of the app.

    Signals
    -------
    frame_ready : Signal(np.ndarray, dict)
        Emitted after optional NUC processing with the corrected frame
        (float32 if NUC is loaded, otherwise original dtype) and
        metadata dict.
    stats_updated : Signal(dict)
        Periodic statistics: ``fps``, ``frame_count``, ``dropped_count``,
        ``mbps``.
    """

    frame_ready = Signal(np.ndarray, dict)
    stats_updated = Signal(dict)

    def __init__(
        self,
        device: DeviceInterface,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._device = device
        self._nuc = NUCProcessor()

        # Statistics bookkeeping
        self._frame_count: int = 0
        self._dropped_count: int = 0
        self._last_frame_id: int = -1
        self._timestamps: deque[float] = deque(maxlen=_FPS_WINDOW)
        self._byte_sizes: deque[int] = deque(maxlen=_FPS_WINDOW)
        self._running: bool = False

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
        """Start the thread event loop.

        Frame processing happens in :meth:`_on_frame_acquired` which is
        invoked via the signal/slot connection.  The thread's event loop
        must be running for queued connections to be dispatched.
        """
        self._running = True
        self._frame_count = 0
        self._dropped_count = 0
        self._last_frame_id = -1
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
            "Acquisition worker stopped: %d frames, %d dropped",
            self._frame_count,
            self._dropped_count,
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

        # Compute rolling statistics
        stats = self._compute_stats()

        # Emit signals
        self.frame_ready.emit(processed, metadata)
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
            "mbps": round(mbps, 2),
        }
