"""Spectral and spatial profile extraction for hyperspectral push-broom frames.

Frame convention:
    shape = (1024, 1280) — axis-0 = spectral bands (rows), axis-1 = spatial pixels (cols)

All extraction methods return ``(indices, values)`` tuples suitable for direct
plotting with pyqtgraph.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("gpy4.analysis")


class SpectralAnalyzer:
    """Extract 1-D spatial and spectral profiles from a 2-D frame."""

    # ------------------------------------------------------------------
    # Near-pixel profiles (windowed)
    # ------------------------------------------------------------------

    @staticmethod
    def near_spatial(
        frame: np.ndarray,
        x: int,
        y: int,
        half_width: int = 10,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Extract a spatial profile (along columns) centred at *x* on row *y*.

        Parameters
        ----------
        frame:
            2-D array, shape ``(bands, spatial_pixels)``.
        x:
            Centre column index.
        y:
            Row index (spectral band) to extract from.
        half_width:
            Number of pixels on each side of *x* to include.

        Returns
        -------
        indices:
            1-D int array of column indices.
        values:
            1-D array of DN values at those columns on row *y*.
        """
        if frame.ndim != 2:
            raise ValueError(f"Expected 2-D frame, got shape {frame.shape}")

        rows, cols = frame.shape
        if not (0 <= y < rows):
            raise IndexError(f"Row index y={y} out of range [0, {rows})")

        col_lo = max(0, x - half_width)
        col_hi = min(cols, x + half_width + 1)  # exclusive upper bound

        indices = np.arange(col_lo, col_hi, dtype=np.int32)
        values = frame[y, col_lo:col_hi].copy()

        logger.debug(
            "near_spatial: y=%d, x=%d, window=[%d, %d), %d pixels",
            y, x, col_lo, col_hi, len(indices),
        )
        return indices, values

    @staticmethod
    def near_spectral(
        frame: np.ndarray,
        x: int,
        y: int,
        half_width: int = 10,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Extract a spectral profile (along rows) centred at *y* on column *x*.

        Parameters
        ----------
        frame:
            2-D array, shape ``(bands, spatial_pixels)``.
        x:
            Column index (spatial pixel) to extract from.
        y:
            Centre row index.
        half_width:
            Number of rows on each side of *y* to include.

        Returns
        -------
        indices:
            1-D int array of row (band) indices.
        values:
            1-D array of DN values at those rows on column *x*.
        """
        if frame.ndim != 2:
            raise ValueError(f"Expected 2-D frame, got shape {frame.shape}")

        rows, cols = frame.shape
        if not (0 <= x < cols):
            raise IndexError(f"Column index x={x} out of range [0, {cols})")

        row_lo = max(0, y - half_width)
        row_hi = min(rows, y + half_width + 1)  # exclusive upper bound

        indices = np.arange(row_lo, row_hi, dtype=np.int32)
        values = frame[row_lo:row_hi, x].copy()

        logger.debug(
            "near_spectral: x=%d, y=%d, window=[%d, %d), %d bands",
            x, y, row_lo, row_hi, len(indices),
        )
        return indices, values

    # ------------------------------------------------------------------
    # Full-extent profiles
    # ------------------------------------------------------------------

    @staticmethod
    def full_spatial(
        frame: np.ndarray,
        y: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Extract the full spatial profile — all columns of row *y*.

        Parameters
        ----------
        frame:
            2-D array, shape ``(bands, spatial_pixels)``.
        y:
            Row index (spectral band).

        Returns
        -------
        indices:
            1-D int array ``[0, 1, ..., cols-1]``.
        values:
            1-D array of DN values across all spatial pixels.
        """
        if frame.ndim != 2:
            raise ValueError(f"Expected 2-D frame, got shape {frame.shape}")

        rows, cols = frame.shape
        if not (0 <= y < rows):
            raise IndexError(f"Row index y={y} out of range [0, {rows})")

        indices = np.arange(cols, dtype=np.int32)
        values = frame[y, :].copy()

        logger.debug("full_spatial: y=%d, %d pixels", y, cols)
        return indices, values

    @staticmethod
    def full_spectral(
        frame: np.ndarray,
        x: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Extract the full spectral profile — all rows of column *x*.

        Parameters
        ----------
        frame:
            2-D array, shape ``(bands, spatial_pixels)``.
        x:
            Column index (spatial pixel).

        Returns
        -------
        indices:
            1-D int array ``[0, 1, ..., rows-1]``.
        values:
            1-D array of DN values across all spectral bands.
        """
        if frame.ndim != 2:
            raise ValueError(f"Expected 2-D frame, got shape {frame.shape}")

        rows, cols = frame.shape
        if not (0 <= x < cols):
            raise IndexError(f"Column index x={x} out of range [0, {cols})")

        indices = np.arange(rows, dtype=np.int32)
        values = frame[:, x].copy()

        logger.debug("full_spectral: x=%d, %d bands", x, rows)
        return indices, values
