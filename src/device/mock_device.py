"""Mock camera device for development and testing."""

import logging
import threading
import time

import numpy as np

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
        self._target_interval_s: float = 1.0 / 72.0
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Pre-compute base gradient pattern (1024×1280) to avoid recalculating each frame
        rows, cols = 1024, 1280
        row_grad = np.linspace(0, 200, rows, dtype=np.float32)[:, np.newaxis]
        col_grad = np.linspace(0, 50, cols, dtype=np.float32)[np.newaxis, :]
        self._base_pattern = row_grad + col_grad

        # Pre-compute spectral weights for generating line-scan patterns
        y_coords = np.arange(rows, dtype=np.float32)[:, np.newaxis]
        self._weight_r = np.exp(-((y_coords - 512) ** 2) / (2 * 50**2)) 
        self._weight_g = np.exp(-((y_coords - 400) ** 2) / (2 * 50**2))
        self._weight_b = np.exp(-((y_coords - 600) ** 2) / (2 * 50**2))
        
        # I've mapped R->512, G->400, B->600 matching default UI values.

        # Pre-render a 2D object for the line scan
        from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush
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
        logger.info("MockDevice exposure set to %.1f µs", us)

    def set_gain(self, db: float) -> None:
        with self._state_lock:
            self._gain_db = db
        logger.info("MockDevice gain set to %.1f dB", db)

    def set_pixel_format(self, fmt: str) -> None:
        with self._state_lock:
            self._pixel_format = fmt
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
        rows, cols = 1024, 1280
        with self._state_lock:
            if not self._running:
                return
            exposure_us = self._exposure_us
            gain_db = self._gain_db
            pixel_format = self._pixel_format
            frame_id = self._frame_id
            self._frame_id += 1

        dtype = np.uint8 if pixel_format == "Mono8" else np.uint16
        max_val = 255 if dtype == np.uint8 else 4095

        # Simulate exposure effect: linear scale relative to default 10000 µs
        exposure_factor = exposure_us / 10000.0

        # Simulate gain effect: standard dB amplification (0 dB=1x, 6 dB≈2x, 24 dB≈15.8x)
        gain_factor = 10.0 ** (gain_db / 20.0)

        # Generate noise (only part that changes each frame)
        noise = np.random.randint(0, 10, (rows, cols), dtype=np.int16)

        # Generate line-scan dynamic patterns from pre-rendered 2D object image
        t = frame_id
        y_idx = t % 1000 # Map frame time to the 1000-height 2D pattern
        
        pattern_r = self._obj_r[y_idx, :]
        pattern_g = self._obj_g[y_idx, :]
        pattern_b = self._obj_b[y_idx, :]
        
        # Combine patterns with their spectral weights and add them onto base pattern
        moving_obj = (self._weight_r * pattern_r) + (self._weight_g * pattern_g) + (self._weight_b * pattern_b)

        # Combine gradient + noise + moving object, then apply exposure & gain scaling
        raw = (self._base_pattern + moving_obj + noise) * exposure_factor * gain_factor
        frame = np.clip(raw, 0, max_val).astype(dtype)

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
