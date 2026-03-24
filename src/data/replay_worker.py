"""Replay worker for playing back saved hyperspectral data.

Loads ENVI BIL or raw binary files and emits frames at a controlled rate.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("specdev.replay")


class ReplayWorker(QThread):
    """Thread worker for replaying saved hyperspectral data.

    Signals
    -------
    frame_ready : Signal(np.ndarray, dict)
        Emitted when a frame is ready for display.
    progress_changed : Signal(int, int)
        Emitted when playback position changes (current, total).
    playback_finished : Signal()
        Emitted when playback reaches the end.
    error_occurred : Signal(str)
        Emitted when an error occurs during playback.
    """

    frame_ready = Signal(np.ndarray, dict)
    progress_changed = Signal(int, int)
    playback_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._file_path: Path | None = None
        self._file_type: str = ""  # "envi" or "raw"
        self._frames: np.ndarray | None = None
        self._metadata: dict = {}
        self._total_frames: int = 0
        self._current_position: int = 0
        self._is_playing: bool = False
        self._is_paused: bool = False
        self._should_stop: bool = False
        self._speed_rate: float = 1.0
        self._frame_interval: float = 1.0 / 30.0  # Default 30 FPS
        self._loop_enabled: bool = False

    def load_file(self, file_path: str) -> bool:
        """Load a saved data file (ENVI or raw).

        Parameters
        ----------
        file_path : str
            Path to .dat file. Must have corresponding .hdr or .json.

        Returns
        -------
        bool
            True if loaded successfully, False otherwise.
        """
        try:
            dat_path = Path(file_path)
            if not dat_path.exists():
                self.error_occurred.emit(f"文件不存在: {file_path}")
                return False

            # Check for .hdr or .json sidecar
            hdr_path = dat_path.with_suffix(".hdr")
            json_path = dat_path.with_suffix(".json")

            if hdr_path.exists():
                return self._load_envi(dat_path, hdr_path)
            elif json_path.exists():
                return self._load_raw(dat_path, json_path)
            else:
                self.error_occurred.emit("缺少配套文件: 需要 .hdr 或 .json 文件")
                return False

        except Exception as e:
            logger.exception("Failed to load file")
            self.error_occurred.emit(f"加载失败: {str(e)}")
            return False

    def _load_envi(self, dat_path: Path, hdr_path: Path) -> bool:
        """Load ENVI BIL format data."""
        # Parse header
        hdr_text = hdr_path.read_text(encoding="utf-8")
        lines = int(self._parse_hdr_value(hdr_text, "lines"))
        samples = int(self._parse_hdr_value(hdr_text, "samples"))
        bands = int(self._parse_hdr_value(hdr_text, "bands"))
        data_type = int(self._parse_hdr_value(hdr_text, "data type"))

        # Map ENVI data type to numpy dtype
        dtype_map = {1: np.uint8, 12: np.uint16}
        if data_type not in dtype_map:
            self.error_occurred.emit(f"不支持的数据类型: {data_type}")
            return False

        dtype = dtype_map[data_type]

        # Load binary data
        raw_data = np.fromfile(dat_path, dtype=dtype)
        expected_size = lines * bands * samples
        if raw_data.size != expected_size:
            self.error_occurred.emit(
                f"数据大小不匹配: 期望 {expected_size}, 实际 {raw_data.size}"
            )
            return False

        # Reshape to (lines, bands, samples) then transpose to (lines, bands, samples)
        self._frames = raw_data.reshape(lines, bands, samples)
        self._total_frames = lines
        self._file_type = "envi"
        self._metadata = {
            "width": samples,
            "height": bands,
            "pixel_format": "Mono8" if data_type == 1 else "Mono12",
        }

        logger.info("ENVI file loaded: %d frames, %dx%d",
                    lines, samples, bands)
        return True

    def _load_raw(self, dat_path: Path, json_path: Path) -> bool:
        """Load raw binary format data."""
        # Parse JSON sidecar
        sidecar = json.loads(json_path.read_text(encoding="utf-8"))
        frame_count = sidecar["frame_count"]
        width = sidecar["width"]
        height = sidecar["height"]
        dtype_str = sidecar["dtype"]

        # Load binary data
        dtype = np.dtype(dtype_str)
        raw_data = np.fromfile(dat_path, dtype=dtype)
        expected_size = frame_count * height * width
        if raw_data.size != expected_size:
            self.error_occurred.emit(
                f"数据大小不匹配: 期望 {expected_size}, 实际 {raw_data.size}"
            )
            return False

        # Reshape to (frame_count, height, width)
        self._frames = raw_data.reshape(frame_count, height, width)
        self._total_frames = frame_count
        self._file_type = "raw"
        self._metadata = {
            "width": width,
            "height": height,
            "pixel_format": sidecar.get("pixel_format", "Mono12"),
        }

        logger.info("Raw file loaded: %d frames, %dx%d",
                    frame_count, width, height)
        return True

    @staticmethod
    def _parse_hdr_value(hdr_text: str, key: str) -> str:
        """Parse a value from ENVI header text."""
        for line in hdr_text.splitlines():
            if line.strip().startswith(key):
                return line.split("=", 1)[1].strip()
        return ""

    def set_speed_rate(self, rate: float) -> None:
        """Set playback speed rate (1.0 = normal, 2.0 = 2x, etc.)."""
        self._speed_rate = max(0.1, min(rate, 10.0))

    def set_loop_enabled(self, enabled: bool) -> None:
        """Enable or disable looping playback."""
        self._loop_enabled = enabled

    def set_position(self, position: int) -> None:
        """Jump to a specific frame position."""
        if 0 <= position < self._total_frames:
            self._current_position = position
            self._emit_current_frame()

    def play(self) -> None:
        """Start or resume playback."""
        if self._current_position >= self._total_frames and self._total_frames > 0:
            self._current_position = 0
        self._is_playing = True
        self._is_paused = False

    def pause(self) -> None:
        """Pause playback."""
        self._is_paused = True

    def stop_playback(self) -> None:
        """Stop playback and seek back to the first frame."""
        self._is_playing = False
        self._is_paused = False
        self._current_position = 0
        self._emit_current_frame()

    def shutdown(self) -> None:
        """Terminate the replay thread."""
        self._should_stop = True
        self._is_playing = False
        self._is_paused = False

    def _emit_current_frame(self) -> None:
        """Emit the currently selected frame and its position."""
        if self._frames is None or self._total_frames <= 0:
            self.progress_changed.emit(0, 0)
            return

        position = max(0, min(self._current_position, self._total_frames - 1))
        frame = self._frames[position]
        metadata = {
            "frame_id": position,
            "timestamp": time.time(),
            **self._metadata,
        }
        self.frame_ready.emit(frame, metadata)
        self.progress_changed.emit(position, self._total_frames)

    def run(self) -> None:
        """Main playback loop."""
        while not self._should_stop:
            if not self._is_playing or self._is_paused:
                self.msleep(50)
                continue

            if self._current_position >= self._total_frames:
                if self._loop_enabled and self._total_frames > 0:
                    self._current_position = 0
                    continue
                self.playback_finished.emit()
                self._is_playing = False
                continue

            # Emit current frame
            self._emit_current_frame()

            # Advance position
            self._current_position += 1

            # Sleep based on speed rate
            sleep_ms = int(self._frame_interval * 1000 / self._speed_rate)
            self.msleep(max(1, sleep_ms))

        logger.info("Replay worker stopped")
