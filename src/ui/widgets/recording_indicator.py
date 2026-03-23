"""Blinking recording indicator — a small red circle that blinks on/off."""

from PySide6.QtCore import QTimer, Qt, QSize
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget


class RecordingIndicator(QWidget):
    """A small blinking red circle used to indicate active recording.

    Call ``start()`` to begin blinking and ``stop()`` to hide the indicator.
    """

    def __init__(self, diameter: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._visible_dot = True
        self.setFixedSize(QSize(diameter + 4, diameter + 4))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle)
        self.hide()

    def start(self, interval_ms: int = 500) -> None:
        """Show the widget and start blinking."""
        self._visible_dot = True
        self.show()
        self._timer.start(interval_ms)
        self.update()

    def stop(self) -> None:
        """Stop blinking and hide the widget."""
        self._timer.stop()
        self.hide()

    def _toggle(self) -> None:
        self._visible_dot = not self._visible_dot
        self.update()

    def paintEvent(self, event) -> None:
        if not self._visible_dot:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#e74c3c"))
        painter.setPen(Qt.PenStyle.NoPen)
        x = (self.width() - self._diameter) // 2
        y = (self.height() - self._diameter) // 2
        painter.drawEllipse(x, y, self._diameter, self._diameter)
        painter.end()
