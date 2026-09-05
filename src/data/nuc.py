"""Non-uniformity correction (NUC) for camera frames.

Applies per-pixel linear correction: ``output = A * raw + B``. Coefficients
are calibrated for one camera output geometry and therefore must match the
active hardware-binning frame shape exactly.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from src.device.device_interface import SENSOR_FRAME_SHAPE, SUPPORTED_BINNING

logger = logging.getLogger("specdev.acquisition")

_SUPPORTED_SHAPES = tuple(
    (SENSOR_FRAME_SHAPE[0] // by, SENSOR_FRAME_SHAPE[1] // bx)
    for bx, by in SUPPORTED_BINNING
)


def _load_coefficients(path: str, expected_shape: tuple[int, int]) -> np.ndarray:
    """Load one float32 coefficient array for *expected_shape*.

    ``.npy`` and ``.csv`` retain their two-dimensional geometry and are
    validated directly. Flat ``.bin``/``.raw`` coefficients are reshaped with
    the active frame geometry, which disambiguates 1x2 and 2x1 files that
    contain the same number of samples.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Coefficient file not found: {path}")

    ext = p.suffix.lower()
    if ext == ".npy":
        arr = np.load(path)
    elif ext == ".csv":
        arr = np.loadtxt(path, delimiter=",")
    elif ext in (".bin", ".raw"):
        arr = np.fromfile(path, dtype=np.float32)
    else:
        raise ValueError(f"Unsupported coefficient file extension: {ext}")

    arr = arr.astype(np.float32, copy=False)
    if arr.shape != expected_shape:
        try:
            arr = arr.reshape(expected_shape)
        except ValueError as exc:
            raise ValueError(
                f"Coefficient array from {path} has shape {arr.shape} and {arr.size} samples; "
                f"expected active-frame shape {expected_shape}"
            ) from exc
    return arr


class NUCProcessor:
    """Per-pixel NUC coefficients tied to one active output frame geometry."""

    def __init__(self) -> None:
        self._a: np.ndarray | None = None
        self._b: np.ndarray | None = None
        self.enabled: bool = False
        self._last_shape_warning: tuple[tuple[int, ...], tuple[int, ...]] | None = None

    def load(
        self,
        a_path: str,
        b_path: str,
        expected_shape: tuple[int, int] = SENSOR_FRAME_SHAPE,
    ) -> None:
        """Load A/B coefficients calibrated for *expected_shape*.

        ``expected_shape`` should be read from the camera after configuring
        binning. Supported outputs are 1024x1280, 512x1280, 1024x640, and
        512x640 (expressed internally as rows x columns).
        """
        expected_shape = tuple(int(v) for v in expected_shape)
        if expected_shape not in _SUPPORTED_SHAPES:
            raise ValueError(
                f"Unsupported NUC frame shape {expected_shape}; "
                f"supported shapes: {_SUPPORTED_SHAPES}"
            )

        a = _load_coefficients(a_path, expected_shape)
        b = _load_coefficients(b_path, expected_shape)
        self._a = a
        self._b = b
        self._last_shape_warning = None
        logger.info("NUC loaded: A=%s B=%s shape=%s", a_path, b_path, a.shape)

    def unload(self) -> None:
        """Clear loaded coefficients."""
        self._a = None
        self._b = None
        self._last_shape_warning = None
        logger.info("NUC coefficients unloaded")

    def is_loaded(self) -> bool:
        return self._a is not None and self._b is not None

    def apply(self, frame: np.ndarray) -> np.ndarray:
        """Apply correction only when coefficient and frame shapes match."""
        if not self.enabled or not self.is_loaded():
            return frame

        coefficient_shape = self._a.shape  # type: ignore[union-attr]
        if coefficient_shape != frame.shape:
            warning_key = (coefficient_shape, frame.shape)
            if warning_key != self._last_shape_warning:
                logger.warning(
                    "Skipping NUC: coefficient shape %s does not match frame shape %s; "
                    "load coefficients calibrated for the active binning mode",
                    coefficient_shape,
                    frame.shape,
                )
                self._last_shape_warning = warning_key
            return frame

        self._last_shape_warning = None
        frame_f32 = frame.astype(np.float32, copy=False)
        return self._a * frame_f32 + self._b  # type: ignore[union-attr]
