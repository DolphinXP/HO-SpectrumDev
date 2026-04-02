"""Image display widget with toolbar."""

import logging
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCursor, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QToolBar,
    QLabel,
    QFileDialog,
    QPushButton,
    QSpinBox,
)

logger = logging.getLogger("specdev.ui")


class _ImageViewBox(pg.ViewBox):
    """ViewBox with a smaller wheel zoom step for image inspection."""

    def __init__(self, *args, zoom_step: float = 0.1, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._zoom_step = zoom_step

    def wheelEvent(self, ev, axis=None):
        delta = ev.delta()
        if delta == 0:
            ev.accept()
            return

        factor = 1.0 - self._zoom_step if delta > 0 else 1.0 + self._zoom_step
        self.scaleBy((factor, factor), center=ev.pos())
        ev.accept()


class ImageDisplayWidget(QWidget):
    """Main image view with sub-toolbar and cursor display.

    Sub-toolbar: 保存图片 | 重置缩放
    Shows X, Y, DN values at cursor position.
    Emits pixel_clicked when user clicks on the image.
    """

    pixel_clicked = Signal(int, int)  # x (spatial), y (spectral)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Button bar (replaces toolbar) ---
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(6, 6, 6, 6)
        button_layout.setSpacing(6)

        self._save_button = QPushButton("保存图片")
        self._save_button.clicked.connect(self._save_image)
        button_layout.addWidget(self._save_button)

        self._reset_button = QPushButton("重置缩放")
        self._reset_button.clicked.connect(self._reset_zoom)
        button_layout.addWidget(self._reset_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # --- Cursor info bar ---
        self._cursor_label = QLabel("X: --  Y: --  DN: --  Zoom: --")
        self._cursor_label.setStyleSheet(
            "background: #252535; color: #e0e0e0; padding: 4px 12px; "
            "font-family: 'Consolas', monospace; font-size: 12px; "
            "border: 1px solid #3a3a4a; border-radius: 3px;"
        )
        layout.addWidget(self._cursor_label)

        # --- Image view (pyqtgraph) ---
        self._image_view = pg.ImageView(view=_ImageViewBox(zoom_step=0.1))
        self._image_view.ui.roiBtn.hide()
        self._image_view.ui.menuBtn.hide()
        self._image_view.getView().scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._image_view.getView().scene().sigMouseClicked.connect(
            self._on_mouse_clicked
        )
        self._image_view.getView().sigRangeChanged.connect(self._update_zoom_label)
        layout.addWidget(self._image_view)

        self._current_frame: np.ndarray | None = None
        self._level_low = 0
        self._level_high = 4095
        self._level_max = 4095
        self._frame_shape: tuple[int, int] | None = None

        button_layout.addWidget(QLabel("显示范围"))

        self._level_low_spin = QSpinBox()
        self._level_low_spin.setRange(0, self._level_max)
        self._level_low_spin.setValue(self._level_low)
        button_layout.addWidget(self._level_low_spin)

        button_layout.addWidget(QLabel("-"))

        self._level_high_spin = QSpinBox()
        self._level_high_spin.setRange(0, self._level_max)
        self._level_high_spin.setValue(self._level_high)
        button_layout.addWidget(self._level_high_spin)

        self._apply_levels_button = QPushButton("应用范围")
        self._apply_levels_button.clicked.connect(self._apply_levels)
        button_layout.addWidget(self._apply_levels_button)

        self._original_levels_button = QPushButton("原始范围")
        self._original_levels_button.clicked.connect(self._reset_levels_to_original)
        button_layout.addWidget(self._original_levels_button)

        # Set cross cursor on the image view
        self._image_view.getView().setCursor(Qt.CursorShape.CrossCursor)

    def update_image(self, frame: np.ndarray, metadata: dict | None = None) -> None:
        """Display a new frame. frame shape: (1024, 1280)."""
        self._current_frame = frame
        self._frame_shape = frame.shape

        # Calculate max value based on pixel format from metadata
        pixel_format = metadata.get("pixel_format") if metadata else None
        max_val = self._get_max_value_from_format(pixel_format, frame.dtype)
        if max_val != self._level_max:
            self._level_max = max_val
            self._reset_levels_to_original()

        levels = (self._level_low, self._level_high)

        # pyqtgraph ImageView expects (cols, rows) or we transpose
        self._image_view.setImage(
            frame.T,
            autoLevels=False,
            levels=levels,
            autoRange=False,
            autoHistogramRange=False,
        )
        self._update_zoom_label()

    @staticmethod
    def _get_max_value_from_format(pixel_format: str | None, dtype: np.dtype) -> int:
        """Get max value based on pixel format or dtype.

        Args:
            pixel_format: The pixel format string (e.g., "Mono8", "Mono10", "Mono12", "Mono16")
            dtype: The numpy dtype of the frame

        Returns:
            The maximum value for the pixel format
        """
        if pixel_format:
            # Extract bit depth from pixel format string
            bits = int(pixel_format[4:])  # Extract number after "Mono"
            return (1 << bits) - 1  # 2^bits - 1
        else:
            # Fallback to dtype-based detection
            return 255 if dtype == np.uint8 else 4095

    def _on_mouse_moved(self, pos) -> None:
        """Update cursor info on mouse move."""
        if self._current_frame is None:
            return
        vb = self._image_view.getView()
        mouse_point = vb.mapSceneToView(pos)
        x = int(mouse_point.x())
        y = int(mouse_point.y())
        rows, cols = self._current_frame.shape
        if 0 <= x < cols and 0 <= y < rows:
            dn = int(self._current_frame[y, x])
            self._cursor_label.setText(
                f"X: {x}  Y: {y}  DN: {dn}  Zoom: {self._get_zoom_text()}"
            )
        else:
            self._cursor_label.setText(
                f"X: -- Y: -- DN: --  Zoom: {self._get_zoom_text()}"
            )

    def _on_mouse_clicked(self, event) -> None:
        """Emit pixel_clicked on left click."""
        if self._current_frame is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.scenePos()
        vb = self._image_view.getView()
        mouse_point = vb.mapSceneToView(pos)
        x = int(mouse_point.x())
        y = int(mouse_point.y())
        rows, cols = self._current_frame.shape
        if 0 <= x < cols and 0 <= y < rows:
            self.pixel_clicked.emit(x, y)
            logger.debug(
                "Pixel clicked: X=%d, Y=%d, DN=%d", x, y, int(self._current_frame[y, x])
            )

    def _save_image(self) -> None:
        """Save current frame as PNG."""
        if self._current_frame is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "", "PNG (*.png);;All Files (*)"
        )
        if path:
            from PySide6.QtGui import QImage, QPixmap

            frame = self._current_frame
            if frame.dtype != np.uint8:
                frame = (frame / frame.max() * 255).astype(np.uint8)
            h, w = frame.shape
            img = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
            img.save(path)
            logger.info("Image saved to %s", path)

    def _reset_zoom(self) -> None:
        """Reset image view to auto-range."""
        self._image_view.autoRange()
        self._update_zoom_label()

    def _apply_levels(self) -> None:
        """Apply the selected display DN range."""
        low = self._level_low_spin.value()
        high = self._level_high_spin.value()
        if low >= high:
            return

        self._level_low = low
        self._level_high = high
        if self._current_frame is not None:
            self._image_view.setLevels(min=self._level_low, max=self._level_high)

    def _reset_levels_to_original(self) -> None:
        """Reset display DN range to the full original dtype range."""
        self._level_low = 0
        self._level_high = self._level_max
        self._level_low_spin.setRange(0, self._level_max)
        self._level_high_spin.setRange(0, self._level_max)
        self._level_low_spin.setValue(self._level_low)
        self._level_high_spin.setValue(self._level_high)
        if self._current_frame is not None:
            self._image_view.setLevels(min=self._level_low, max=self._level_high)

    def get_current_frame(self) -> np.ndarray | None:
        return self._current_frame

    def _update_zoom_label(self, *args) -> None:
        """Refresh the zoom ratio text in the status line."""
        current = self._cursor_label.text()
        if "Zoom:" in current:
            prefix = current.split("Zoom:")[0].rstrip()
            self._cursor_label.setText(f"{prefix}  Zoom: {self._get_zoom_text()}")
        else:
            self._cursor_label.setText(
                f"X: -- Y: -- DN: --  Zoom: {self._get_zoom_text()}"
            )

    def _get_zoom_text(self) -> str:
        """Return the current horizontal zoom ratio relative to full-frame view."""
        if self._frame_shape is None:
            return "--"

        _, cols = self._frame_shape
        if cols <= 0:
            return "--"

        x_range, _ = self._image_view.getView().viewRange()
        visible_width = abs(float(x_range[1]) - float(x_range[0]))
        if visible_width <= 0:
            return "--"

        zoom = cols / visible_width
        return f"{zoom:.2f}x"
