"""MTF (Modulation Transfer Function) calculator for edge-contrast measurement.

Per-direction MTF formula:
    MTF = ((A - B) / (A + B)) * pi/4
where:
    A = dnCenter - blackLevel
    B = dnNeighbor - blackLevel

Supports 1/5/10 frame averaging. Returns averaged results once the
configured number of frames has been accumulated, then resets.
"""

from __future__ import annotations

import logging
import math
from typing import Final

import numpy as np

logger = logging.getLogger("gpy4.analysis")

_VALID_AVG_COUNTS: Final[frozenset[int]] = frozenset({1, 5, 10})
_PI_OVER_4: Final[float] = math.pi / 4.0

# Direction names used as dictionary keys
_DIRECTIONS: Final[tuple[str, ...]] = ("above", "below", "left", "right")


class MTFCalculator:
    """Compute per-direction MTF from a single pixel and its four neighbours.

    Usage::

        calc = MTFCalculator()
        calc.set_avg_count(5)
        calc.set_black_level(10.0)
        for frame in frames:
            result = calc.update(frame, x, y)
            if result is not None:
                print(result)  # {'above': ..., 'below': ..., ...}
    """

    def __init__(self) -> None:
        self._avg_count: int = 1
        self._black_level: float = 0.0

        # Accumulation state
        self._accum: dict[str, float] = {d: 0.0 for d in _DIRECTIONS}
        self._valid_counts: dict[str, int] = {d: 0 for d in _DIRECTIONS}
        self._frame_count: int = 0

        # Track pixel position so we can reset on change
        self._last_x: int | None = None
        self._last_y: int | None = None

        logger.debug("MTFCalculator initialised (avg_count=1, black_level=0)")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_avg_count(self, n: int) -> None:
        """Set the number of frames to average over (1, 5, or 10).

        Resets the accumulator immediately if the value changes.
        """
        if n not in _VALID_AVG_COUNTS:
            raise ValueError(
                f"avg_count must be one of {sorted(_VALID_AVG_COUNTS)}, got {n}"
            )
        if n != self._avg_count:
            logger.debug("MTF avg_count changed %d -> %d, resetting", self._avg_count, n)
            self._avg_count = n
            self.reset()

    def set_black_level(self, level: float) -> None:
        """Set the noise-floor black level subtracted before MTF computation."""
        if level != self._black_level:
            logger.debug("MTF black_level changed %.1f -> %.1f", self._black_level, level)
            self._black_level = level

    # ------------------------------------------------------------------
    # Accumulator management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear accumulated MTF sums and frame counter."""
        for d in _DIRECTIONS:
            self._accum[d] = 0.0
            self._valid_counts[d] = 0
        self._frame_count = 0
        self._last_x = None
        self._last_y = None
        logger.debug("MTF accumulator reset")

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    @staticmethod
    def _mtf_single(dn_center: float, dn_neighbor: float, black_level: float) -> float:
        """Compute MTF for one direction.

        Returns NaN when the computation is undefined (e.g. A+B == 0).
        """
        a = dn_center - black_level
        b = dn_neighbor - black_level
        denominator = a + b
        if denominator == 0.0:
            return float("nan")
        return ((a - b) / denominator) * _PI_OVER_4

    def update(self, frame: np.ndarray, x: int, y: int) -> dict[str, float] | None:
        """Feed one frame and return averaged MTF when ready.

        Parameters
        ----------
        frame:
            2-D numpy array, shape ``(rows, cols)`` — typically ``(1024, 1280)``.
        x:
            Spatial pixel index (column).
        y:
            Spectral band index (row).

        Returns
        -------
        dict or None
            ``{'above', 'below', 'left', 'right', 'mean'}`` when *avg_count*
            frames have been accumulated; ``None`` otherwise.
            Out-of-bounds directions are ``NaN``.
        """
        if frame.ndim != 2:
            logger.warning("MTF update received non-2D frame (shape=%s), ignoring", frame.shape)
            return None

        rows, cols = frame.shape

        # Validate coordinates
        if not (0 <= y < rows and 0 <= x < cols):
            logger.warning("MTF pixel (%d, %d) out of frame bounds (%d, %d)", x, y, cols, rows)
            return None

        # Reset if pixel position changed
        if x != self._last_x or y != self._last_y:
            if self._last_x is not None:
                logger.debug(
                    "MTF pixel changed (%s,%s)->(%d,%d), resetting",
                    self._last_x, self._last_y, x, y,
                )
            self._accum = {d: 0.0 for d in _DIRECTIONS}
            self._valid_counts = {d: 0 for d in _DIRECTIONS}
            self._frame_count = 0
            self._last_x = x
            self._last_y = y

        dn_center = float(frame[y, x])

        # Neighbour lookup: (direction_name, row_offset, col_offset, boundary_ok)
        neighbours: list[tuple[str, int, int, bool]] = [
            ("above", y - 1, x, y > 0),
            ("below", y + 1, x, y < rows - 1),
            ("left", y, x - 1, x > 0),
            ("right", y, x + 1, x < cols - 1),
        ]

        for direction, ny, nx, valid in neighbours:
            if valid:
                dn_neighbor = float(frame[ny, nx])
                mtf_val = self._mtf_single(dn_center, dn_neighbor, self._black_level)
                if not math.isnan(mtf_val):
                    self._accum[direction] += mtf_val
                    self._valid_counts[direction] += 1
            # If not valid, direction stays NaN (never accumulated)

        self._frame_count += 1

        # Not enough frames yet
        if self._frame_count < self._avg_count:
            return None

        # --- Build averaged result ---
        result: dict[str, float] = {}
        valid_mtf_values: list[float] = []

        for d in _DIRECTIONS:
            count = self._valid_counts[d]
            if count > 0:
                avg = self._accum[d] / count
                result[d] = avg
                valid_mtf_values.append(avg)
            else:
                result[d] = float("nan")

        # Mean over valid directions only
        if valid_mtf_values:
            result["mean"] = sum(valid_mtf_values) / len(valid_mtf_values)
        else:
            result["mean"] = float("nan")

        logger.debug(
            "MTF result at (%d,%d) over %d frame(s): above=%.3f below=%.3f "
            "left=%.3f right=%.3f mean=%.3f",
            x, y, self._avg_count,
            result["above"], result["below"],
            result["left"], result["right"],
            result["mean"],
        )

        # Reset accumulator for next batch
        self._accum = {d: 0.0 for d in _DIRECTIONS}
        self._valid_counts = {d: 0 for d in _DIRECTIONS}
        self._frame_count = 0
        # Keep _last_x/_last_y so we don't reset on the next call with same pixel

        return result
