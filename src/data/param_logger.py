"""Per-second camera parameter CSV logger.

Appends one row per second while recording so operators can correlate
environmental drift (temperature) and acquisition settings with the saved
frame data.  The CSV shares its base filename with the recording session.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import IO, Callable

logger = logging.getLogger("specdev.storage")

_DEFAULT_INTERVAL_S = 1.0

_HEADER = (
    "时间戳",
    "录制时长 (s)",
    "曝光时间 (µs)",
    "帧率 (fps)",
    "增益 (dB)",
    "ADC 位深 (bit)",
    "探测器温度 (°C)",
)


class CsvParamLogger:
    """Background thread that samples device parameters at a fixed cadence.

    Parameters
    ----------
    path : str
        Base file path (extension is replaced with ``.csv``).
    sampler : callable
        Zero-argument callable returning a mapping with keys
        ``exposure_us``, ``frame_rate_fps``, ``gain_db``, ``adc_bit_depth``
        and ``temperature_c``.  Missing keys are logged as empty cells.
    interval_s : float
        Sampling period in seconds (default 1.0).
    """

    def __init__(
        self,
        path: str,
        sampler: Callable[[], dict],
        interval_s: float = _DEFAULT_INTERVAL_S,
        logger_name: str = "CsvParamLogger",
    ) -> None:
        if interval_s <= 0:
            raise ValueError(f"interval_s must be positive; got {interval_s}")
        self._csv_path = Path(path).with_suffix(".csv")
        self._sampler = sampler
        self._interval_s = float(interval_s)
        self._logger_name = logger_name

        self._file: IO[str] | None = None
        self._writer: csv.writer | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._start_monotonic: float = 0.0
        self._rows_written: int = 0

    @property
    def csv_path(self) -> Path:
        return self._csv_path

    @property
    def rows_written(self) -> int:
        return self._rows_written

    def start(self) -> None:
        """Open the CSV file and start the sampling thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("CsvParamLogger already running: %s", self._csv_path)
            return

        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._csv_path, "w", newline="", encoding="utf-8")  # noqa: SIM115
        self._writer = csv.writer(self._file)
        self._writer.writerow(_HEADER)
        self._file.flush()

        self._rows_written = 0
        self._stop_event.clear()
        self._start_monotonic = time.perf_counter()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=self._logger_name,
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Parameter CSV logging started: %s (interval=%.2f s)",
            self._csv_path,
            self._interval_s,
        )

    def stop(self) -> None:
        """Stop the sampling thread and close the file."""
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._interval_s + 1.0)

        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                logger.exception("Error closing parameter CSV %s", self._csv_path)
            self._file = None
            self._writer = None

        logger.info(
            "Parameter CSV logging stopped: %s (%d rows)",
            self._csv_path,
            self._rows_written,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        # First sample immediately so the file always has at least one row.
        next_deadline = time.perf_counter()
        while not self._stop_event.is_set():
            now = time.perf_counter()
            if now >= next_deadline:
                self._write_row(now - self._start_monotonic)
                next_deadline = now + self._interval_s
            remaining = next_deadline - time.perf_counter()
            if remaining > 0:
                self._stop_event.wait(min(remaining, 0.1))

    def _write_row(self, elapsed_s: float) -> None:
        if self._writer is None:
            return

        try:
            params = dict(self._sampler())
        except Exception:
            logger.exception("Parameter sampler failed; writing empty row")
            params = {}

        row = [
            datetime.now().isoformat(timespec="milliseconds"),
            f"{elapsed_s:.3f}",
            params.get("exposure_us", ""),
            params.get("frame_rate_fps", ""),
            params.get("gain_db", ""),
            params.get("adc_bit_depth", ""),
            params.get("temperature_c", ""),
        ]
        try:
            self._writer.writerow(row)
            self._rows_written += 1
            # Flush every row — one flush per second is cheap and keeps the
            # CSV usable if the application or the camera crashes mid-recording.
            if self._file is not None:
                self._file.flush()
        except Exception:
            logger.exception("Failed to write parameter CSV row")
