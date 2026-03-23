"""Storage manager for hyperspectral data recording.

Coordinates :class:`EnviWriter` and :class:`RawWriter` instances, handles
session naming, and delegates incoming frames to whichever writers are
currently active.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from src.data.envi_writer import EnviWriter
from src.data.raw_writer import RawWriter

logger = logging.getLogger("gpy4.storage")


def _session_path(directory: str, session_name: str) -> str:
    """Build a base file path: ``<directory>/<session_name>_YYYYMMDD_HHMMSS``."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{session_name}_{timestamp}" if session_name else timestamp
    return str(Path(directory) / name)


class StorageManager:
    """High-level recording manager.

    Supports two independent recording modes that may run concurrently:

    * **ENVI** — hyperspectral cube (BIL ``.hdr`` + ``.dat``)
    * **Raw** — concatenated binary frames (``.raw`` + ``.json`` sidecar)

    Usage::

        mgr = StorageManager()
        mgr.start_envi("data/", "calibration", "Mono12", wavelengths=wl)
        mgr.start_raw("data/", "calibration", "Mono12", metadata={...})
        for frame, meta in acquisition:
            mgr.write_frame(frame, meta)
        mgr.stop()
    """

    def __init__(self) -> None:
        self._envi_writer: EnviWriter | None = None
        self._raw_writer: RawWriter | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        """``True`` if any writer is currently active."""
        return self._envi_writer is not None or self._raw_writer is not None

    @property
    def envi_writer(self) -> EnviWriter | None:
        """The active ENVI writer, or ``None``."""
        return self._envi_writer

    @property
    def raw_writer(self) -> RawWriter | None:
        """The active raw writer, or ``None``."""
        return self._raw_writer

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start_envi(
        self,
        directory: str,
        session_name: str,
        pixel_format: str,
        wavelengths: np.ndarray | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Open an ENVI writer for a new recording session.

        Parameters
        ----------
        directory : str
            Output directory (created if needed).
        session_name : str
            Human-readable session prefix.
        pixel_format : str
            ``"Mono8"``, ``"Mono10"``, or ``"Mono12"``.
        wavelengths : np.ndarray | None
            1024-element wavelength array (nm).
        metadata : dict | None
            Optional metadata (``exposure_us``, ``gain_db``, etc.).
        """
        if self._envi_writer is not None:
            logger.warning("ENVI writer already active; closing previous session")
            self._envi_writer.close()

        path = _session_path(directory, session_name)
        writer = EnviWriter()
        writer.open(path, pixel_format, wavelengths=wavelengths, metadata=metadata)
        self._envi_writer = writer
        logger.info("ENVI recording started: %s", path)

    def start_raw(
        self,
        directory: str,
        session_name: str,
        pixel_format: str,
        metadata: dict | None = None,
    ) -> None:
        """Open a raw binary writer for a new recording session.

        Parameters
        ----------
        directory : str
            Output directory (created if needed).
        session_name : str
            Human-readable session prefix.
        pixel_format : str
            ``"Mono8"``, ``"Mono10"``, or ``"Mono12"``.
        metadata : dict | None
            Optional metadata forwarded to the JSON sidecar.
        """
        if self._raw_writer is not None:
            logger.warning("Raw writer already active; closing previous session")
            self._raw_writer.close()

        path = _session_path(directory, session_name)
        writer = RawWriter()
        writer.open(path, pixel_format, metadata=metadata)
        self._raw_writer = writer
        logger.info("Raw recording started: %s", path)

    def write_frame(self, frame: np.ndarray, metadata: dict | None = None) -> None:
        """Write a frame to all active writers.

        Parameters
        ----------
        frame : np.ndarray
            Camera frame, shape ``(1024, 1280)``.
        metadata : dict | None
            Frame metadata (currently unused by writers but reserved for
            future per-frame sidecar data).
        """
        if self._envi_writer is not None:
            try:
                self._envi_writer.write_line(frame)
            except Exception:
                logger.exception("Error writing ENVI line")

        if self._raw_writer is not None:
            try:
                self._raw_writer.write_frame(frame)
            except Exception:
                logger.exception("Error writing raw frame")

    def stop(self) -> None:
        """Close all active writers and finalise files."""
        if self._envi_writer is not None:
            try:
                self._envi_writer.close()
            except Exception:
                logger.exception("Error closing ENVI writer")
            self._envi_writer = None

        if self._raw_writer is not None:
            try:
                self._raw_writer.close()
            except Exception:
                logger.exception("Error closing raw writer")
            self._raw_writer = None

        logger.info("Storage manager stopped; all writers closed")
