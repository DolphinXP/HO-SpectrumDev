"""Mock camera device for development and testing."""

import logging
import threading
import time

import numpy as np

from src.device.device_interface import DeviceInterface

logger = logging.getLogger("specdev.device")

_ROWS = 1024
_COLS = 1280
_LINE_SCAN_R = 512
_LINE_SCAN_G = 400
_LINE_SCAN_B = 600


class MockDevice(DeviceInterface):
    """Simulated hyperspectral camera generating synthetic frames."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._exposure_us: float = 10000.0
        self._gain_db: float = 0.0
        self._pixel_format: str = "Mono12"
        self._running: bool = False
        self._frame_id: int = 0
        self._target_interval_s: float = 1.0 / 120.0
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._template_dirty: bool = True
        self._template_frame: np.ndarray | None = None

        # Pre-compute base gradient pattern (1024×1280) to avoid recalculating each frame
        rows, cols = _ROWS, _COLS
        row_grad = np.linspace(0, 200, rows, dtype=np.float32)[:, np.newaxis]
        col_grad = np.linspace(0, 50, cols, dtype=np.float32)[np.newaxis, :]
        self._base_pattern = row_grad + col_grad

        # Pre-render a 2D object for the line scan
        from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen
        from PySide6.QtCore import Qt

        img = QImage(cols, 1000, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.black)

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw Square (Red)
        p.setPen(QPen(QColor(255, 0, 0), 10))
        p.drawRect(150, 150, 300, 300)

        # Draw Circle (Green)
        p.setPen(QPen(QColor(0, 255, 0), 10))
        p.drawEllipse(750, 150, 300, 300)

        # Draw Text (Blue)
        p.setPen(QPen(QColor(0, 50, 255), 5))
        font = QFont("Arial", 90)
        font.setBold(True)
        p.setFont(font)
        p.drawText(150, 800, "Hello, world!")
        p.end()

        # Convert QImage (Format_RGB32 is BGRA in memory) to numpy array
        ptr = img.bits()
        arr = np.array(ptr).reshape((1000, cols, 4))
        self._obj_b = arr[:, :, 0].astype(np.float32)
        self._obj_g = arr[:, :, 1].astype(np.float32)
        self._obj_r = arr[:, :, 2].astype(np.float32)

    def initialize(self) -> bool:
        logger.info("MockDevice initialized (1024×1280, %s)",
                    self._pixel_format)
        return True

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        with self._state_lock:
            self._running = True
            self._frame_id = 0

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="MockDeviceThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("MockDevice acquisition started")

    def stop(self) -> None:
        with self._state_lock:
            self._running = False

        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        logger.info("MockDevice acquisition stopped")

    def close(self) -> None:
        self.stop()
        logger.info("MockDevice closed")

    def set_exposure(self, us: float) -> None:
        with self._state_lock:
            self._exposure_us = us
            self._template_dirty = True
        logger.info("MockDevice exposure set to %.1f µs", us)

    def set_gain(self, db: float) -> None:
        with self._state_lock:
            self._gain_db = db
            self._template_dirty = True
        logger.info("MockDevice gain set to %.1f dB", db)

    def set_pixel_format(self, fmt: str) -> None:
        with self._state_lock:
            self._pixel_format = fmt
            self._template_dirty = True
        logger.info("MockDevice pixel format set to %s", fmt)

    def get_frame_shape(self) -> tuple[int, int]:
        return (1024, 1280)

    def get_exposure(self) -> float:
        with self._state_lock:
            return self._exposure_us

    def get_gain(self) -> float:
        with self._state_lock:
            return self._gain_db

    def get_pixel_format(self) -> str:
        with self._state_lock:
            return self._pixel_format

    def _run_loop(self) -> None:
        next_deadline = time.perf_counter()
        while not self._stop_event.is_set():
            self._generate_frame()
            next_deadline += self._target_interval_s
            sleep_s = next_deadline - time.perf_counter()
            if sleep_s > 0:
                self._stop_event.wait(sleep_s)
            else:
                next_deadline = time.perf_counter()

    def _generate_frame(self) -> None:
        """Generate a synthetic frame and emit frame_acquired."""
        rows, cols = _ROWS, _COLS
        with self._state_lock:
            if not self._running:
                return
            exposure_us = self._exposure_us
            gain_db = self._gain_db
            pixel_format = self._pixel_format
            frame_id = self._frame_id
            self._frame_id += 1
            if self._template_dirty or self._template_frame is None:
                self._template_frame = self._build_template(
                    pixel_format,
                    exposure_us,
                    gain_db,
                )
                self._template_dirty = False
            template = self._template_frame

        dtype, max_val = self._get_dtype_and_max_value(pixel_format)
        frame = template.copy()

        t = frame_id
        y_idx = t % self._obj_r.shape[0]
        line_scale = max(1.0, max_val / 255.0)
        self._overlay_line_pattern(
            frame, _LINE_SCAN_R, self._obj_r[y_idx], line_scale, max_val)
        self._overlay_line_pattern(
            frame, _LINE_SCAN_G, self._obj_g[y_idx], line_scale, max_val)
        self._overlay_line_pattern(
            frame, _LINE_SCAN_B, self._obj_b[y_idx], line_scale, max_val)

        # A lightweight flicker stripe makes motion obvious in both display modes.
        stripe_x = (t * 11) % cols
        stripe_value = max_val // 3
        frame[:, stripe_x:stripe_x + 2] = np.clip(
            frame[:, stripe_x:stripe_x + 2].astype(np.int32) + stripe_value,
            0,
            max_val,
        ).astype(dtype, copy=False)

        # Moving bright spots — helps verify live area display
        cy = (t * 3) % rows
        cx = cols // 2
        y_lo, y_hi = max(0, cy - 5), min(rows, cy + 5)
        x_lo, x_hi = max(0, cx - 5), min(cols, cx + 5)
        frame[y_lo:y_hi, x_lo:x_hi] = max_val

        cx2 = (t * 3) % cols
        cy2 = rows // 2
        y_lo2, y_hi2 = max(0, cy2 - 5), min(rows, cy2 + 5)
        x_lo2, x_hi2 = max(0, cx2 - 5), min(cols, cx2 + 5)
        frame[y_lo2:y_hi2, x_lo2:x_hi2] = max_val

        metadata = {
            "frame_id": frame_id,
            "timestamp": time.time(),
            "pixel_format": pixel_format,
            "exposure_us": exposure_us,
            "gain_db": gain_db,
            "width": cols,
            "height": rows,
        }
        self.frame_acquired.emit(frame, metadata)

    @staticmethod
    def _get_dtype_and_max_value(pixel_format: str) -> tuple[type, int]:
        """Get numpy dtype and max value based on pixel format.

        Args:
            pixel_format: The pixel format string (e.g., "Mono8", "Mono10", "Mono12", "Mono16")

        Returns:
            A tuple of (numpy_dtype, max_value) where max_value is 2^bits - 1
        """
        # Extract the bit depth from the pixel format string
        # Format is "Mono{bits}" where bits is 8, 10, 12, or 16
        bits = int(pixel_format[4:])  # Extract number after "Mono"
        max_val = (1 << bits) - 1  # 2^bits - 1

        # Mono8 uses uint8, all others use uint16
        dtype = np.uint8 if bits == 8 else np.uint16

        return dtype, max_val

    def _build_template(
        self,
        pixel_format: str,
        exposure_us: float,
        gain_db: float,
    ) -> np.ndarray:
        dtype, max_val = self._get_dtype_and_max_value(pixel_format)
        exposure_factor = exposure_us / 10000.0
        gain_factor = 10.0 ** (gain_db / 20.0)
        scale = exposure_factor * gain_factor

        # Normalize base pattern to [0, 1] range, then scale to [0, max_val]
        # This ensures the full pixel format range is used
        base_max = np.max(self._base_pattern)
        normalized_pattern = self._base_pattern / base_max
        template = np.clip(normalized_pattern * max_val * scale,
                           0, max_val).astype(dtype)
        return template

    @staticmethod
    def _overlay_line_pattern(
        frame: np.ndarray,
        center_row: int,
        pattern: np.ndarray,
        scale: float,
        max_val: int,
    ) -> None:
        pattern_scaled = np.clip(
            pattern * scale, 0, max_val).astype(frame.dtype, copy=False)
        row_lo = max(0, center_row - 1)
        row_hi = min(frame.shape[0], center_row + 2)
        for row in range(row_lo, row_hi):
            frame[row, :] = np.maximum(frame[row, :], pattern_scaled)
