"""Abstract interfaces for peripheral devices (future extension)."""

from abc import ABC, abstractmethod


class ConveyorController(ABC):
    """Abstract conveyor belt controller — connect via serial/GPIO."""

    @abstractmethod
    def connect(self, port: str) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def set_speed(self, speed: float) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


class LightController(ABC):
    """Abstract light source controller — connect via serial/GPIO."""

    @abstractmethod
    def connect(self, port: str) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def set_intensity(self, percent: float) -> None: ...

    @abstractmethod
    def on(self) -> None: ...

    @abstractmethod
    def off(self) -> None: ...
