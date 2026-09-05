"""Abstract base class and common geometry for camera devices."""

from abc import ABCMeta, abstractmethod

import numpy as np
from PySide6.QtCore import QObject, Signal


# The production camera pipeline is fixed to the sensor's 12-bit output.
DEFAULT_PIXEL_FORMAT = "Mono12"

# Sensor geometry expressed as numpy ``(rows, cols)`` = ``(height, width)``.
SENSOR_FRAME_SHAPE = (1024, 1280)

# (X, Y): X bins horizontal image columns; Y bins vertical image rows.
SUPPORTED_BINNING: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 2),
)


def validate_binning(x: int, y: int) -> tuple[int, int]:
    """Validate and return one of the supported hardware binning modes."""
    mode = (int(x), int(y))
    if mode not in SUPPORTED_BINNING:
        supported = ", ".join(f"{bx}x{by}" for bx, by in SUPPORTED_BINNING)
        raise ValueError(
            f"Unsupported binning {mode[0]}x{mode[1]}; supported modes: {supported}"
        )
    return mode


class _DeviceMeta(type(QObject), ABCMeta):
    """Resolve metaclass conflict between QObject and ABC."""


class DeviceInterface(QObject, metaclass=_DeviceMeta):
    """Abstract interface for hyperspectral camera devices.

    Subclasses emit ``frame_acquired`` with a 2-D numpy array and metadata.
    Its dimensions reflect the currently configured hardware binning mode.
    """

    frame_acquired = Signal(np.ndarray, dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @abstractmethod
    def initialize(self) -> bool:
        """Open and configure the device. Return True on success."""
        ...

    @abstractmethod
    def start(self) -> None:
        """Begin frame acquisition."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop frame acquisition."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release device resources."""
        ...

    @abstractmethod
    def set_exposure(self, us: float) -> None:
        """Set exposure time in microseconds."""
        ...

    @abstractmethod
    def set_gain(self, db: float) -> None:
        """Set gain in dB."""
        ...

    @abstractmethod
    def set_pixel_format(self, fmt: str) -> None:
        """Set the required Mono12 pixel format."""
        ...

    @abstractmethod
    def set_binning(self, x: int, y: int) -> None:
        """Set hardware binning, where X is horizontal and Y is vertical."""
        ...

    @abstractmethod
    def get_frame_shape(self) -> tuple[int, int]:
        """Return the current frame shape as ``(rows, cols)``."""
        ...

    @abstractmethod
    def get_exposure(self) -> float:
        """Return current exposure time in microseconds."""
        ...

    @abstractmethod
    def get_gain(self) -> float:
        """Return current gain in dB."""
        ...

    @abstractmethod
    def get_pixel_format(self) -> str:
        """Return current pixel format string."""
        ...

    @abstractmethod
    def get_binning(self) -> tuple[int, int]:
        """Return current ``(X, Y)`` hardware binning factors."""
        ...

    def get_supported_binning(self) -> tuple[tuple[int, int], ...]:
        """Return binning modes supported by the active device.

        A conservative ``1x1`` default keeps non-Daheng implementations
        functional if they do not expose binning capabilities.
        """
        return ((1, 1),)

    def get_temperature(self) -> float | None:
        """Return camera temperature in degrees Celsius when available.

        Temperature is an optional device feature. Devices that do not expose
        it should return ``None`` rather than raising an exception.
        """
        return None
