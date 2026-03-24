"""ENVI BIL file writer for hyperspectral push-broom data.

Produces a file pair (``.hdr`` ASCII header + ``.dat`` raw binary) using
Band-Interleaved-by-Line (BIL) interleave. Each call to :meth:`write_line`
appends one camera frame (1024 bands x 1280 spatial samples) to the
``.dat`` file. On :meth:`close` the header is rewritten with the final
line count.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import numpy as np

logger = logging.getLogger("specdev.storage")

# Sensor geometry
_BANDS = 1024
_SAMPLES = 1280

# ENVI data-type codes
_ENVI_DTYPE_MAP: dict[str, tuple[int, np.dtype]] = {
    "Mono8":  (1, np.dtype(np.uint8)),
    "Mono10": (12, np.dtype(np.uint16)),
    "Mono12": (12, np.dtype(np.uint16)),
}


class EnviWriter:
    """Write hyperspectral data in ENVI BIL format.

    Usage::

        writer = EnviWriter()
        writer.open("session_001", pixel_format="Mono12")
        for frame, meta in frames:
            writer.write_line(frame)
        writer.close()

    Or as a context manager::

        with EnviWriter() as w:
            w.open(...)
            for frame, meta in frames:
                w.write_line(frame)
    """

    def __init__(self) -> None:
        self._dat_file: BinaryIO | None = None
        self._hdr_path: Path | None = None
        self._dat_path: Path | None = None
        self._pixel_format: str = ""
        self._envi_dtype_code: int = 1
        self._np_dtype: np.dtype = np.dtype(np.uint8)
        self._metadata: dict = {}
        self._lines_written: int = 0
        self._bytes_written: int = 0
        self._open_time: datetime | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "EnviWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def lines_written(self) -> int:
        """Number of push-broom lines written so far."""
        return self._lines_written

    @property
    def bytes_written(self) -> int:
        """Total bytes written to the ``.dat`` file."""
        return self._bytes_written

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(
        self,
        path: str,
        pixel_format: str,
        metadata: dict | None = None,
    ) -> None:
        """Open the ENVI file pair for writing.

        Parameters
        ----------
        path : str
            Base path **without** extension.  ``.hdr`` and ``.dat`` are
            appended automatically.
        pixel_format : str
            One of ``"Mono8"``, ``"Mono10"``, ``"Mono12"``.
        metadata : dict | None
            Optional extra metadata (``exposure_us``, ``gain_db``, etc.).
        """
        if self._dat_file is not None:
            raise RuntimeError(
                "EnviWriter is already open; call close() first")

        if pixel_format not in _ENVI_DTYPE_MAP:
            raise ValueError(f"Unsupported pixel format: {pixel_format}")

        self._pixel_format = pixel_format
        self._envi_dtype_code, self._np_dtype = _ENVI_DTYPE_MAP[pixel_format]

        self._metadata = metadata or {}
        self._lines_written = 0
        self._bytes_written = 0
        self._open_time = datetime.now()

        base = Path(path)
        base.parent.mkdir(parents=True, exist_ok=True)
        self._hdr_path = base.with_suffix(".hdr")
        self._dat_path = base.with_suffix(".dat")

        # Write initial header with lines = 0
        self._write_header(lines=0)

        # Open .dat for binary append
        self._dat_file = open(self._dat_path, "wb")  # noqa: SIM115

        logger.info(
            "ENVI writer opened: %s (format=%s, dtype_code=%d)",
            self._dat_path,
            pixel_format,
            self._envi_dtype_code,
        )

    def write_line(self, frame: np.ndarray) -> None:
        """Append one push-broom line to the ``.dat`` file.

        Parameters
        ----------
        frame : np.ndarray
            Frame of shape ``(1024, 1280)`` — rows are spectral bands,
            columns are spatial samples.  The frame is cast to the
            target dtype before writing.

        The data is written in BIL order: for each of the 1024 bands,
        the 1280 sample values are written contiguously.
        """
        if self._dat_file is None:
            raise RuntimeError("EnviWriter is not open")

        if frame.shape != (_BANDS, _SAMPLES):
            raise ValueError(
                f"Frame shape {frame.shape} != expected ({_BANDS}, {_SAMPLES})"
            )

        # Cast to target dtype and write in BIL order.
        # frame is already (bands, samples), so row-major tobytes() gives
        # band-interleaved-by-line layout directly.
        data = frame.astype(self._np_dtype, copy=False).tobytes()
        self._dat_file.write(data)
        self._lines_written += 1
        self._bytes_written += len(data)

    def close(self) -> None:
        """Flush the ``.dat`` file and rewrite ``.hdr`` with the final line count."""
        if self._dat_file is not None:
            self._dat_file.flush()
            self._dat_file.close()
            self._dat_file = None
            logger.info(
                "ENVI .dat closed: %s (%d lines, %d bytes)",
                self._dat_path,
                self._lines_written,
                self._bytes_written,
            )

        if self._hdr_path is not None:
            self._write_header(lines=self._lines_written)
            logger.info(
                "ENVI .hdr rewritten: %s (lines=%d)",
                self._hdr_path,
                self._lines_written,
            )
            self._hdr_path = None
            self._dat_path = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_header(self, lines: int) -> None:
        """Write (or rewrite) the ENVI ``.hdr`` file."""
        assert self._hdr_path is not None
        assert self._open_time is not None

        date_str = self._open_time.strftime("%Y-%m-%d")
        time_str = self._open_time.strftime("%H:%M:%S")

        exposure_us = self._metadata.get("exposure_us", "")
        gain_db = self._metadata.get("gain_db", "")

        buf = io.StringIO()
        buf.write("ENVI\n")
        buf.write(
            f"description = {{specdev hyperspectral acquisition "
            f"{date_str} {time_str}}}\n"
        )
        buf.write(f"samples = {_SAMPLES}\n")
        buf.write(f"lines = {lines}\n")
        buf.write(f"bands = {_BANDS}\n")
        buf.write("header offset = 0\n")
        buf.write("file type = ENVI Standard\n")
        buf.write(f"data type = {self._envi_dtype_code}\n")
        buf.write("interleave = bil\n")
        buf.write("byte order = 0\n")
        buf.write(f"acquisition date = {date_str}\n")
        buf.write(f"acquisition time = {time_str}\n")
        if exposure_us != "":
            buf.write(f"exposure time = {exposure_us}\n")
        if gain_db != "":
            buf.write(f"gain = {gain_db}\n")
        buf.write(f"pixel format = {self._pixel_format}\n")

        self._hdr_path.write_text(buf.getvalue(), encoding="utf-8")
