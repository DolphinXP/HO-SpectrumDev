"""Raw frame writer with JSON sidecar metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import numpy as np

logger = logging.getLogger("specdev.storage")

_DTYPE_MAP: dict[str, str] = {
    "Mono8": "uint8",
    "Mono10": "uint16",
    "Mono12": "uint16",
}


class RawWriter:
    """Write same-shape camera frames as a binary stream with JSON metadata."""

    def __init__(self) -> None:
        self._data_file: BinaryIO | None = None
        self._data_path: Path | None = None
        self._json_path: Path | None = None
        self._pixel_format: str = ""
        self._np_dtype: np.dtype = np.dtype(np.uint8)
        self._metadata: dict = {}
        self._frame_count: int = 0
        self._bytes_written: int = 0
        self._width: int = 0
        self._height: int = 0
        self._write_binary: bool = True

    def __enter__(self) -> "RawWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    def open(
        self,
        path: str,
        pixel_format: str,
        metadata: dict | None = None,
        data_extension: str = ".dat",
        write_binary: bool = True,
    ) -> None:
        if self._data_file is not None or self._json_path is not None:
            raise RuntimeError("RawWriter is already open; call close() first")
        if pixel_format not in _DTYPE_MAP:
            raise ValueError(f"Unsupported pixel format: {pixel_format}")

        self._pixel_format = pixel_format
        self._np_dtype = np.dtype(_DTYPE_MAP[pixel_format])
        self._metadata = dict(metadata or {})
        self._frame_count = 0
        self._bytes_written = 0
        self._width = int(self._metadata.get("width", 0) or 0)
        self._height = int(self._metadata.get("height", 0) or 0)
        self._write_binary = write_binary

        base = Path(path)
        base.parent.mkdir(parents=True, exist_ok=True)
        self._data_path = base.with_suffix(data_extension)
        self._json_path = base.with_suffix(".json")
        if self._write_binary:
            self._data_file = open(self._data_path, "wb")  # noqa: SIM115
        logger.info("Raw writer opened: %s (format=%s, write_binary=%s)", self._data_path, pixel_format, write_binary)

    def write_frame(self, frame: np.ndarray) -> None:
        if not self._write_binary and self._json_path is None:
            raise RuntimeError("RawWriter is not open")
        if self._write_binary and self._data_file is None:
            raise RuntimeError("RawWriter is not open")
        if frame.ndim != 2:
            raise ValueError(f"Raw frame must be 2-D, got shape {frame.shape}")

        height, width = (int(v) for v in frame.shape)
        if self._frame_count == 0:
            if self._width and self._height and (width, height) != (self._width, self._height):
                raise ValueError(
                    f"Frame shape {frame.shape} != recording shape ({self._height}, {self._width})"
                )
            self._height, self._width = height, width
        elif (width, height) != (self._width, self._height):
            raise ValueError(
                f"Frame shape {frame.shape} != recording shape ({self._height}, {self._width}); "
                "stop recording before changing binning"
            )

        data = frame.astype(self._np_dtype, copy=False).tobytes()
        if self._write_binary:
            self._data_file.write(data)
            self._bytes_written += len(data)
        self._frame_count += 1

    def close(self) -> None:
        if self._data_file is not None:
            self._data_file.flush()
            self._data_file.close()
            self._data_file = None
            logger.info("Raw data file closed: %s (%d frames, %d bytes)", self._data_path, self._frame_count, self._bytes_written)

        if self._json_path is not None:
            sidecar = {
                "frame_count": self._frame_count,
                "width": self._width,
                "height": self._height,
                "pixel_format": self._pixel_format,
                "dtype": str(self._np_dtype),
                "data_file": self._data_path.name if self._data_path is not None else None,
                "exposure_us": self._metadata.get("exposure_us"),
                "gain_db": self._metadata.get("gain_db"),
                "fps": self._metadata.get("fps"),
                "binning_x": self._metadata.get("binning_x", 1),
                "binning_y": self._metadata.get("binning_y", 1),
                "binning": self._metadata.get("binning", "1x1"),
                "original_width": self._metadata.get("original_width"),
                "original_height": self._metadata.get("original_height"),
            }
            self._json_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("JSON sidecar written: %s", self._json_path)
            self._data_path = None
            self._json_path = None
