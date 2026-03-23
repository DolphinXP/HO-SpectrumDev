"""Mock camera device for development and testing."""

import logging
import time

import numpy as np
from PySide6.QtCore import QTimer

from src.device.device_interface import DeviceInterface

logger = logging.getLogger("gpy4.device")


class MockDevice(DeviceInterface):
    """Simulated hyperspectral camera generating synthetic frames."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._exposure_us: float = 10000.0
        self._gain_db: float = 0.0
        self._pixel_format: str = "Mono8"
        self._running: bool = False
        self._frame_id: int = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._generate_frame)

        # Pre-compute base gradient pattern (1024×1280) to avoid recalculating each frame
        rows, cols = 1024, 1280
        row_grad = np.linspace(0, 200, rows, dtype=np.float32)[:, np.newaxis]
        col_grad = np.linspace(0, 50, cols, dtype=np.float32)[np.newaxis, :]
        self._base_pattern = row_grad + col_grad

    def initialize(self) -> bool:
        logger.info("MockDevice initialized (1024×1280, %s)", self._pixel_format)
        return True

    def start(self) -> None:
        self._running = True
        self._frame_id = 0
        self._timer.start(14)  # ~70 fps (14ms interval)
        logger.info("MockDevice acquisition started")

    def stop(self) -> None:
        self._running = False
        self._timer.stop()
        logger.info("MockDevice acquisition stopped")

    def close(self) -> None:
        self.stop()
        logger.info("MockDevice closed")

    def set_exposure(self, us: float) -> None:
        self._exposure_us = us
        logger.info("MockDevice exposure set to %.1f µs", us)

    def set_gain(self, db: float) -> None:
        self._gain_db = db
        logger.info("MockDevice gain set to %.1f dB", db)

    def set_pixel_format(self, fmt: str) -> None:
        self._pixel_format = fmt
        logger.info("MockDevice pixel format set to %s", fmt)

    def get_frame_shape(self) -> tuple[int, int]:
        return (1024, 1280)

    def get_exposure(self) -> float:
        return self._exposure_us

    def get_gain(self) -> float:
        return self._gain_db

    def get_pixel_format(self) -> str:
        return self._pixel_format

    def _generate_frame(self) -> None:
        """Generate a synthetic frame and emit frame_acquired."""
        rows, cols = 1024, 1280
        dtype = np.uint8 if self._pixel_format == "Mono8" else np.uint16

        # Generate noise (only part that changes each frame)
        noise = np.random.randint(0, 10, (rows, cols), dtype=np.int16)

        # Combine pre-computed gradient with noise
        frame = np.clip(self._base_pattern + noise, 0,
                        255 if dtype == np.uint8 else 4095).astype(dtype)

        # Add a bright spot that moves — helps verify live display
        cy = (self._frame_id * 3) % rows
        cx = cols // 2
        y_lo, y_hi = max(0, cy - 5), min(rows, cy + 5)
        x_lo, x_hi = max(0, cx - 5), min(cols, cx + 5)
        max_val = 255 if dtype == np.uint8 else 4095
        frame[y_lo:y_hi, x_lo:x_hi] = max_val

        metadata = {
            "frame_id": self._frame_id,
            "timestamp": time.time(),
            "pixel_format": self._pixel_format,
            "exposure_us": self._exposure_us,
            "gain_db": self._gain_db,
            "width": cols,
            "height": rows,
        }

        self._frame_id += 1
        self.frame_acquired.emit(frame, metadata)
