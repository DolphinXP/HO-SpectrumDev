"""Raw binary frame writer with JSON sidecar metadata.

Writes concatenated raw numpy frames to a ``.raw`` file and produces a
``.json`` sidecar on :meth:`close` containing frame count, dimensions,
pixel format, and other acquisition parameters.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import numpy as np

logger = logging.getLogger("gpy4.storage")

_DTYPE_MAP: dict[str, str] = {
    "Mono8": "uint8",
    "Mono10": "uint16",
    "Mono12": "uint16",
}


class RawWriter:
    """Write raw camera frames as a flat binary stream with JSON sidecar.

    Usage::

        writer = RawWriter()
        writer.open("session_001", pixel_format="Mono12", metadata={...})
        for frame in frames:
            writer.write_frame(frame)
        writer.close()

    Or as a context manager::

        with RawWriter() as w:
            w.open(...)
            for frame in frames:
                w.write_frame(frame)
    """

    def __init__(self) -> None:
        self._raw_file: BinaryIO | None = None
        self._raw_path: Path | None = None
        self._json_path: Path | None = None
        self._pixel_format: str = ""
        self._np_dtype: np.dtype = np.dtype(np.uint8)
        self._metadata: dict = {}
        self._frame_count: int = 0
        self._bytes_written: int = 0
        self._width: int = 0
        self._height: int = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "RawWriter":
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
    def frame_count(self) -> int:
        """Number of frames written so far."""
        return self._frame_count

    @property
    def bytes_written(self) -> int:
        """Total bytes written to the ``.raw`` file."""
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
        """Open the raw file pair for writing.

        Parameters
        ----------
        path : str
            Base path **without** extension.  ``.raw`` and ``.json``
            are appended automatically.
        pixel_format : str
            One of ``"Mono8"``, ``"Mono10"``, ``"Mono12"``.
        metadata : dict | None
            Optional metadata forwarded to the JSON sidecar
            (``exposure_us``, ``gain_db``, ``fps``, etc.).
        """
        if self._raw_file is not None:
            raise RuntimeError("RawWriter is already open; call close() first")

        if pixel_format not in _DTYPE_MAP:
            raise ValueError(f"Unsupported pixel format: {pixel_format}")

        self._pixel_format = pixel_format
        self._np_dtype = np.dtype(_DTYPE_MAP[pixel_format])
        self._metadata = metadata or {}
        self._frame_count = 0
        self._bytes_written = 0
        self._width = 0
        self._height = 0

        base = Path(path)
        base.parent.mkdir(parents=True, exist_ok=True)
        self._raw_path = base.with_suffix(".raw")
        self._json_path = base.with_suffix(".json")

        self._raw_file = open(self._raw_path, "wb")  # noqa: SIM115

        logger.info(
            "Raw writer opened: %s (format=%s)", self._raw_path, pixel_format
        )

    def write_frame(self, frame: np.ndarray) -> None:
        """Append one frame to the ``.raw`` file.

        Parameters
        ----------
        frame : np.ndarray
            Camera frame (typically shape ``(1024, 1280)``).  Cast to
            the target dtype before writing.
        """
        if self._raw_file is None:
            raise RuntimeError("RawWriter is not open")

        # Record dimensions from first frame
        if self._frame_count == 0:
            self._height, self._width = frame.shape[:2]

        data = frame.astype(self._np_dtype, copy=False).tobytes()
        self._raw_file.write(data)
        self._frame_count += 1
        self._bytes_written += len(data)

    def close(self) -> None:
        """Flush the ``.raw`` file and write the JSON sidecar."""
        if self._raw_file is not None:
            self._raw_file.flush()
            self._raw_file.close()
            self._raw_file = None
            logger.info(
                "Raw file closed: %s (%d frames, %d bytes)",
                self._raw_path,
                self._frame_count,
                self._bytes_written,
            )

        if self._json_path is not None:
            sidecar = {
                "frame_count": self._frame_count,
                "width": self._width,
                "height": self._height,
                "pixel_format": self._pixel_format,
                "dtype": str(self._np_dtype),
                "exposure_us": self._metadata.get("exposure_us"),
                "gain_db": self._metadata.get("gain_db"),
                "fps": self._metadata.get("fps"),
            }
            self._json_path.write_text(
                json.dumps(sidecar, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("JSON sidecar written: %s", self._json_path)
            self._raw_path = None
            self._json_path = None
