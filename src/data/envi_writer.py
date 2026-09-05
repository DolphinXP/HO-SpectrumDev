"""ENVI BIL file writer for hyperspectral push-broom data."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import numpy as np

logger = logging.getLogger("specdev.storage")

_ENVI_DTYPE_MAP: dict[str, tuple[int, np.dtype]] = {
    "Mono8": (1, np.dtype(np.uint8)),
    "Mono10": (12, np.dtype(np.uint16)),
    "Mono12": (12, np.dtype(np.uint16)),
}


class EnviWriter:
    """Write same-shape camera frames in ENVI BIL format.

    The first frame establishes ``bands`` (image rows) and ``samples``
    (image columns). This lets a recording preserve the output geometry of
    the active hardware binning mode.
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
        self._frame_shape: tuple[int, int] | None = None

    def __enter__(self) -> "EnviWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def lines_written(self) -> int:
        return self._lines_written

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def frame_shape(self) -> tuple[int, int] | None:
        """The ``(bands, samples)`` geometry established by the first frame."""
        return self._frame_shape

    def open(self, path: str, pixel_format: str, metadata: dict | None = None) -> None:
        """Open the ENVI pair.

        ``metadata`` may contain ``width``/``height`` to establish geometry
        before the first frame, plus binning and acquisition provenance.
        """
        if self._dat_file is not None:
            raise RuntimeError("EnviWriter is already open; call close() first")
        if pixel_format not in _ENVI_DTYPE_MAP:
            raise ValueError(f"Unsupported pixel format: {pixel_format}")

        self._pixel_format = pixel_format
        self._envi_dtype_code, self._np_dtype = _ENVI_DTYPE_MAP[pixel_format]
        self._metadata = dict(metadata or {})
        self._lines_written = 0
        self._bytes_written = 0
        self._open_time = datetime.now()
        self._frame_shape = self._shape_from_metadata(self._metadata)

        base = Path(path)
        base.parent.mkdir(parents=True, exist_ok=True)
        self._hdr_path = base.with_suffix(".hdr")
        self._dat_path = base.with_suffix(".dat")
        self._write_header(lines=0)
        self._dat_file = open(self._dat_path, "wb")  # noqa: SIM115
        logger.info(
            "ENVI writer opened: %s (format=%s, shape=%s)",
            self._dat_path,
            pixel_format,
            self._frame_shape,
        )

    def write_line(self, frame: np.ndarray) -> None:
        """Append one output frame, enforcing a stable geometry per file."""
        if self._dat_file is None:
            raise RuntimeError("EnviWriter is not open")
        if frame.ndim != 2:
            raise ValueError(f"ENVI frame must be 2-D, got shape {frame.shape}")

        shape = tuple(int(v) for v in frame.shape)
        if self._frame_shape is None:
            self._frame_shape = shape
            self._metadata.setdefault("height", shape[0])
            self._metadata.setdefault("width", shape[1])
            # Rewrite promptly so an interrupted acquisition still identifies
            # the correct binned geometry.
            self._write_header(lines=self._lines_written)
        elif shape != self._frame_shape:
            raise ValueError(
                f"Frame shape {shape} != recording shape {self._frame_shape}; "
                "stop recording before changing binning"
            )

        data = frame.astype(self._np_dtype, copy=False).tobytes()
        self._dat_file.write(data)
        self._lines_written += 1
        self._bytes_written += len(data)

    def close(self) -> None:
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
            logger.info("ENVI .hdr rewritten: %s (lines=%d)", self._hdr_path, self._lines_written)
            self._hdr_path = None
            self._dat_path = None

    @staticmethod
    def _shape_from_metadata(metadata: dict) -> tuple[int, int] | None:
        width = metadata.get("width")
        height = metadata.get("height")
        if width is None or height is None:
            return None
        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid ENVI metadata dimensions: {width}x{height}")
        return (height, width)

    def _write_header(self, lines: int) -> None:
        assert self._hdr_path is not None
        assert self._open_time is not None
        bands, samples = self._frame_shape or (0, 0)
        date_str = self._open_time.strftime("%Y-%m-%d")
        time_str = self._open_time.strftime("%H:%M:%S")

        buf = io.StringIO()
        buf.write("ENVI\n")
        buf.write(f"description = {{specdev hyperspectral acquisition {date_str} {time_str}}}\n")
        buf.write(f"samples = {samples}\n")
        buf.write(f"lines = {lines}\n")
        buf.write(f"bands = {bands}\n")
        buf.write("header offset = 0\n")
        buf.write("file type = ENVI Standard\n")
        buf.write(f"data type = {self._envi_dtype_code}\n")
        buf.write("interleave = bil\n")
        buf.write("byte order = 0\n")
        buf.write(f"acquisition date = {date_str}\n")
        buf.write(f"acquisition time = {time_str}\n")

        for header_key, metadata_key in (
            ("exposure time", "exposure_us"),
            ("gain", "gain_db"),
            ("pixel format", "pixel_format"),
            ("binning horizontal", "binning_x"),
            ("binning vertical", "binning_y"),
            ("binning", "binning"),
            ("original samples", "original_width"),
            ("original bands", "original_height"),
        ):
            value = self._metadata.get(metadata_key)
            if value is not None and value != "":
                buf.write(f"{header_key} = {value}\n")

        # Always advertise the writer's target pixel format even when it was
        # not duplicated in the caller-provided metadata.
        if "pixel_format" not in self._metadata:
            buf.write(f"pixel format = {self._pixel_format}\n")

        self._hdr_path.write_text(buf.getvalue(), encoding="utf-8")
