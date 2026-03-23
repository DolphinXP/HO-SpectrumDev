"""Image display widget with toolbar."""

import logging
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCursor, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel,
    QFileDialog,
)

logger = logging.getLogger("gpy4.ui")


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

        # --- Sub-toolbar ---
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)

        save_action = QAction("保存图片", self)
        save_action.triggered.connect(self._save_image)
        self._toolbar.addAction(save_action)

        reset_action = QAction("重置缩放", self)
        reset_action.triggered.connect(self._reset_zoom)
        self._toolbar.addAction(reset_action)

        layout.addWidget(self._toolbar)

        # --- Cursor info bar ---
        self._cursor_label = QLabel("X: -- Y: -- DN: --")
        self._cursor_label.setStyleSheet(
            "background: #e8e8e8; padding: 2px 8px; font-family: monospace;")
        layout.addWidget(self._cursor_label)

        # --- Image view (pyqtgraph) ---
        self._image_view = pg.ImageView()
        self._image_view.ui.roiBtn.hide()
        self._image_view.ui.menuBtn.hide()
        self._image_view.getView().scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._image_view.getView().scene().sigMouseClicked.connect(self._on_mouse_clicked)
        layout.addWidget(self._image_view)

        self._current_frame: np.ndarray | None = None

        # Set cross cursor on the image view
        self._image_view.getView().setCursor(Qt.CursorShape.CrossCursor)

    def update_image(self, frame: np.ndarray) -> None:
        """Display a new frame. frame shape: (1024, 1280)."""
        self._current_frame = frame

        max_val = 255 if frame.dtype == np.uint8 else 4095
        levels = (0, max_val)

        # pyqtgraph ImageView expects (cols, rows) or we transpose
        self._image_view.setImage(
            frame.T, autoLevels=False, levels=levels, autoRange=False,
            autoHistogramRange=False,
        )

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
            self._cursor_label.setText(f"X: {x}  Y: {y}  DN: {dn}")
        else:
            self._cursor_label.setText("X: -- Y: -- DN: --")

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
            logger.debug("Pixel clicked: X=%d, Y=%d, DN=%d",
                        x, y, int(self._current_frame[y, x]))

    def _save_image(self) -> None:
        """Save current frame as PNG."""
        if self._current_frame is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "", "PNG (*.png);;All Files (*)")
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

    def get_current_frame(self) -> np.ndarray | None:
        return self._current_frame
