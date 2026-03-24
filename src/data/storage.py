"""Storage manager for hyperspectral data recording.

Coordinates :class:`EnviWriter` and :class:`RawWriter` instances, handles
session naming, and delegates incoming frames to whichever writers are
currently active.
"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from src.data.envi_writer import EnviWriter
from src.data.raw_writer import RawWriter

logger = logging.getLogger("specdev.storage")


def _session_path(directory: str, session_name: str) -> str:
    """Build a base file path: ``<directory>/<session_name>``."""
    return str(Path(directory) / session_name) if session_name else str(
        Path(directory) / datetime.now().strftime("%Y%m%d_%H%M%S")
    )


class StorageManager:
    """High-level recording manager.

    Supports ENVI and raw metadata recording modes:

    * **ENVI** — hyperspectral cube (BIL ``.hdr`` + ``.dat``)
    * **Raw** — concatenated binary frames (``.dat`` + ``.json`` sidecar)

    Usage::

        mgr = StorageManager()
        mgr.start_envi("data/", "calibration", "Mono12")
        mgr.start_raw("data/", "calibration", "Mono12", metadata={...})
        for frame, meta in acquisition:
            mgr.write_frame(frame, meta)
        mgr.stop()
    """

    def __init__(self, max_pending_frames: int = 32) -> None:
        self._envi_writer: EnviWriter | None = None
        self._raw_writer: RawWriter | None = None
        self._max_pending_frames = max_pending_frames
        self._write_queue: queue.Queue[np.ndarray | object] = queue.Queue(
            maxsize=max_pending_frames
        )
        self._writer_thread: threading.Thread | None = None
        self._writer_error: BaseException | None = None
        self._stop_sentinel = object()
        self._dropped_frames: int = 0
        self._drop_warning_emitted: bool = False

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

    @property
    def dropped_frames(self) -> int:
        """Number of frames discarded because the async queue was full."""
        return self._dropped_frames

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start_envi(
        self,
        directory: str,
        session_name: str,
        pixel_format: str,
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
        metadata : dict | None
            Optional metadata (``exposure_us``, ``gain_db``, etc.).
        """
        if self._envi_writer is not None:
            logger.warning(
                "ENVI writer already active; closing previous session")
            self._envi_writer.close()

        path = _session_path(directory, session_name)
        writer = EnviWriter()
        writer.open(path, pixel_format, metadata=metadata)
        self._envi_writer = writer
        self._ensure_writer_thread()
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
            logger.warning(
                "Raw writer already active; closing previous session")
            self._raw_writer.close()

        path = _session_path(directory, session_name)
        writer = RawWriter()
        write_binary = self._envi_writer is None
        writer.open(
            path,
            pixel_format,
            metadata=metadata,
            data_extension=".dat",
            write_binary=write_binary,
        )
        self._raw_writer = writer
        self._ensure_writer_thread()
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
        if not self.is_recording:
            return
        self._raise_writer_error()
        try:
            self._write_queue.put_nowait(frame.copy())
        except queue.Full:
            self._dropped_frames += 1
            if not self._drop_warning_emitted:
                logger.warning(
                    "Storage queue is full (%d frames); dropping frames to cap memory usage",
                    self._max_pending_frames,
                )
                self._drop_warning_emitted = True

    def stop(self) -> None:
        """Close all active writers and finalise files."""
        self._stop_writer_thread()
        self._raise_writer_error()

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

        if self._dropped_frames > 0:
            logger.warning(
                "Storage manager dropped %d frame(s) because the writer queue was full",
                self._dropped_frames,
            )

        logger.info("Storage manager stopped; all writers closed")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_writer_thread(self) -> None:
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return

        self._writer_error = None
        self._dropped_frames = 0
        self._drop_warning_emitted = False
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="StorageWriter",
            daemon=True,
        )
        self._writer_thread.start()

    def _stop_writer_thread(self) -> None:
        thread = self._writer_thread
        if thread is None:
            return

        while thread.is_alive():
            try:
                self._write_queue.put(self._stop_sentinel, timeout=0.1)
                break
            except queue.Full:
                continue
        thread.join()
        self._writer_thread = None

    def _writer_loop(self) -> None:
        while True:
            frame = self._write_queue.get()
            if frame is self._stop_sentinel:
                break

            try:
                self._write_frame_sync(frame)
            except Exception as exc:  # pragma: no cover - surfaced to caller
                self._writer_error = exc
                logger.exception("Error writing frame to storage")
                break

    def _write_frame_sync(self, frame: np.ndarray) -> None:
        if self._envi_writer is not None:
            self._envi_writer.write_line(frame)

        if self._raw_writer is not None:
            self._raw_writer.write_frame(frame)

    def _raise_writer_error(self) -> None:
        if self._writer_error is None:
            return
        err = self._writer_error
        self._writer_error = None
        raise RuntimeError("Background storage writer failed") from err
