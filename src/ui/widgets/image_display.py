"""Image display widget with toolbar and tab switching."""

import logging
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel,
    QStackedWidget, QFileDialog,
)

logger = logging.getLogger("gpy4.ui")


class ImageDisplayWidget(QWidget):
    """Main image view with sub-toolbar and cursor display.

    Sub-toolbar: 图像 | DN | 光校 | 保存图片 | 重置缩放 | 三标尺 | 框选 | 拉伸
    Shows X, Y, DN values at cursor position.
    Emits pixel_clicked when user clicks on the image.
    """

    pixel_clicked = Signal(int, int)  # x (spatial), y (spectral)
    tab_changed = Signal(str)  # "image", "dn", "oc"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Sub-toolbar ---
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)

        self._tab_actions: dict[str, QAction] = {}
        for key, label in [("image", "图像"), ("dn", "DN"), ("oc", "光校")]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, k=key: self._switch_tab(k))
            self._toolbar.addAction(action)
            self._tab_actions[key] = action
        self._tab_actions["image"].setChecked(True)

        self._toolbar.addSeparator()

        save_action = QAction("保存图片", self)
        save_action.triggered.connect(self._save_image)
        self._toolbar.addAction(save_action)

        reset_action = QAction("重置缩放", self)
        reset_action.triggered.connect(self._reset_zoom)
        self._toolbar.addAction(reset_action)

        self._ruler_action = QAction("三标尺", self)
        self._ruler_action.setCheckable(True)
        self._toolbar.addAction(self._ruler_action)

        self._roi_action = QAction("框选", self)
        self._roi_action.setCheckable(True)
        self._toolbar.addAction(self._roi_action)

        self._stretch_action = QAction("拉伸", self)
        self._stretch_action.setCheckable(True)
        self._stretch_action.toggled.connect(self._on_stretch_toggled)
        self._toolbar.addAction(self._stretch_action)

        layout.addWidget(self._toolbar)

        # --- Cursor info bar ---
        self._cursor_label = QLabel("X: -- Y: -- DN: --")
        self._cursor_label.setStyleSheet(
            "background: #e8e8e8; padding: 2px 8px; font-family: monospace;")
        layout.addWidget(self._cursor_label)

        # --- Stacked widget for switching between views ---
        self._stacked_widget = QStackedWidget()

        # --- Image view (pyqtgraph) ---
        self._image_view = pg.ImageView()
        self._image_view.ui.roiBtn.hide()
        self._image_view.ui.menuBtn.hide()
        self._image_view.getView().scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._image_view.getView().scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self._stacked_widget.addWidget(self._image_view)  # index 0

        # --- DN table view ---
        from .dn_table_widget import DNTableWidget
        self._dn_table = DNTableWidget()
        self._dn_table.pixel_selected.connect(self._on_dn_pixel_selected)
        self._stacked_widget.addWidget(self._dn_table)  # index 1

        # --- Placeholder for optical calibration view ---
        oc_placeholder = QLabel("光校视图 (待实现)")
        oc_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stacked_widget.addWidget(oc_placeholder)  # index 2

        layout.addWidget(self._stacked_widget)

        self._current_frame: np.ndarray | None = None
        self._auto_stretch: bool = False

        # Crosshair lines
        self._vline = pg.InfiniteLine(angle=90, movable=False,
                                       pen=pg.mkPen("r", width=1, style=Qt.PenStyle.DashLine))
        self._hline = pg.InfiniteLine(angle=0, movable=False,
                                       pen=pg.mkPen("r", width=1, style=Qt.PenStyle.DashLine))
        self._image_view.getView().addItem(self._vline)
        self._image_view.getView().addItem(self._hline)
        self._vline.hide()
        self._hline.hide()

    def update_image(self, frame: np.ndarray) -> None:
        """Display a new frame. frame shape: (1024, 1280)."""
        self._current_frame = frame

        if self._auto_stretch:
            levels = (float(frame.min()), float(frame.max()))
        else:
            max_val = 255 if frame.dtype == np.uint8 else 4095
            levels = (0, max_val)

        # pyqtgraph ImageView expects (cols, rows) or we transpose
        self._image_view.setImage(
            frame.T, autoLevels=False, levels=levels, autoRange=False,
            autoHistogramRange=False,
        )

        # Update DN table if it's visible
        self._dn_table.update_frame(frame)

    def _switch_tab(self, key: str) -> None:
        """Handle tab button clicks and switch views."""
        for k, action in self._tab_actions.items():
            action.setChecked(k == key)

        # Switch to the appropriate view
        if key == "image":
            self._stacked_widget.setCurrentIndex(0)
        elif key == "dn":
            self._stacked_widget.setCurrentIndex(1)
        elif key == "oc":
            self._stacked_widget.setCurrentIndex(2)

        self.tab_changed.emit(key)

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
            self._vline.setPos(x)
            self._hline.setPos(y)
            self._vline.show()
            self._hline.show()
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

    def _on_dn_pixel_selected(self, x: int, y: int) -> None:
        """Handle pixel selection from DN table."""
        self._dn_table.set_center(x, y)
        self.pixel_clicked.emit(x, y)

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

    def _on_stretch_toggled(self, checked: bool) -> None:
        """Toggle auto-stretch (min-max contrast)."""
        self._auto_stretch = checked
        if self._current_frame is not None:
            self.update_image(self._current_frame)

    def get_current_frame(self) -> np.ndarray | None:
        return self._current_frame
