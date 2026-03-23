"""Application configuration using QSettings."""

from PySide6.QtCore import QSettings


class AppConfig:
    """Thin wrapper around QSettings for persistent configuration."""

    def __init__(self) -> None:
        self._settings = QSettings("gpy4", "HyperspectralApp")

    def get(self, key: str, default=None):
        """Get a config value by snake_case key."""
        return self._settings.value(key, default)

    def set(self, key: str, value) -> None:
        """Set a config value."""
        self._settings.setValue(key, value)

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self._settings.value(key, default))

    def get_float(self, key: str, default: float = 0.0) -> float:
        return float(self._settings.value(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._settings.value(key, default)
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def get_str(self, key: str, default: str = "") -> str:
        return str(self._settings.value(key, default))
