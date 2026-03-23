"""Abstract base class for camera devices."""

from abc import ABCMeta, abstractmethod

import numpy as np
from PySide6.QtCore import QObject, Signal


class _DeviceMeta(type(QObject), ABCMeta):
    """Resolve metaclass conflict between QObject and ABC."""
    pass


class DeviceInterface(QObject, metaclass=_DeviceMeta):
    """Abstract interface for hyperspectral camera devices.

    Subclasses must emit ``frame_acquired`` with a numpy array
    of shape (1024, 1280) and a metadata dict.
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
        """Set pixel format: 'Mono8', 'Mono10', or 'Mono12'."""
        ...

    @abstractmethod
    def get_frame_shape(self) -> tuple[int, int]:
        """Return (rows, cols) = (1024, 1280) for this sensor."""
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
