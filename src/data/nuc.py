"""Non-Uniformity Correction (NUC) processor.

Applies per-pixel linear correction: ``output = A * raw + B`` where A and B
are float32 coefficient arrays of shape (1024, 1280).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger("gpy4.acquisition")

_EXPECTED_SHAPE = (1024, 1280)


def _load_coefficients(path: str) -> np.ndarray:
    """Load a coefficient array from *path*, auto-detecting format by extension.

    Supported formats:
        .npy        -- numpy binary (``np.load``)
        .csv        -- comma-separated, 1024 rows x 1280 cols
        .bin / .raw -- flat float32 binary, row-major

    Returns
    -------
    np.ndarray
        Array of shape (1024, 1280), dtype float32.

    Raises
    ------
    ValueError
        If the loaded data cannot be reshaped to the expected shape.
    FileNotFoundError
        If *path* does not exist.
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

    if arr.shape != _EXPECTED_SHAPE:
        try:
            arr = arr.reshape(_EXPECTED_SHAPE)
        except ValueError:
            raise ValueError(
                f"Coefficient array from {path} has {arr.size} elements; "
                f"expected {_EXPECTED_SHAPE[0] * _EXPECTED_SHAPE[1]}"
            )

    return arr


class NUCProcessor:
    """Per-pixel non-uniformity correction.

    When coefficients are loaded, :meth:`apply` computes
    ``A * frame + B`` element-wise.  When no coefficients are loaded the
    frame is simply cast to float32 (identity transform).
    """

    def __init__(self) -> None:
        self._a: np.ndarray | None = None
        self._b: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, a_path: str, b_path: str) -> None:
        """Load gain (A) and offset (B) coefficient files.

        Parameters
        ----------
        a_path : str
            Path to the gain coefficient file.
        b_path : str
            Path to the offset coefficient file.

        Raises
        ------
        ValueError
            If either file has the wrong shape.
        FileNotFoundError
            If either path does not exist.
        """
        a = _load_coefficients(a_path)
        b = _load_coefficients(b_path)

        if a.shape != _EXPECTED_SHAPE:
            raise ValueError(
                f"A coefficient shape {a.shape} != expected {_EXPECTED_SHAPE}"
            )
        if b.shape != _EXPECTED_SHAPE:
            raise ValueError(
                f"B coefficient shape {b.shape} != expected {_EXPECTED_SHAPE}"
            )

        self._a = a
        self._b = b
        logger.info(
            "NUC loaded: A=%s B=%s shape=%s", a_path, b_path, a.shape
        )

    def unload(self) -> None:
        """Clear loaded coefficients."""
        self._a = None
        self._b = None
        logger.info("NUC coefficients unloaded")

    def is_loaded(self) -> bool:
        """Return ``True`` if both A and B are loaded and shape-validated."""
        return self._a is not None and self._b is not None

    def apply(self, frame: np.ndarray) -> np.ndarray:
        """Apply NUC correction to *frame*.

        Parameters
        ----------
        frame : np.ndarray
            Raw camera frame, shape (1024, 1280), dtype uint8 or uint16.

        Returns
        -------
        np.ndarray
            Corrected frame, shape (1024, 1280), dtype float32.
            If coefficients are not loaded the frame is returned as
            ``frame.astype(np.float32)`` (identity).
        """
        if not self.is_loaded():
            return frame.astype(np.float32, copy=False)

        logger.debug("Applying NUC correction")
        return self._a * frame.astype(np.float32) + self._b  # type: ignore[union-attr]
