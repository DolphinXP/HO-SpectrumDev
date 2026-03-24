"""Line scan (waterfall) image display widget."""

import logging
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QFileDialog, QRadioButton, QButtonGroup
)

logger = logging.getLogger("specdev.ui")

_LINE_SCAN_RENDER_INTERVAL_MS = 66
_INTERACTION_DEFER_SECONDS = 0.18


class _ImageViewBox(pg.ViewBox):
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


class LineScanDisplayWidget(QWidget):
    """Main image view for line scan (waterfall) mode."""

    # Emitted when config changes so AcquisitionWorker can be updated
    config_changed = Signal(bool, list)  # enabled, [y_indices...]

    pixel_clicked = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Controls Bar ---
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        ctrl_layout.setSpacing(6)

        # Mode Selection
        self._mode_group = QButtonGroup(self)
        self._radio_single = QRadioButton("单光谱")
        self._radio_rgb = QRadioButton("三光谱 (伪彩)")
        self._radio_single.setChecked(True)
        self._mode_group.addButton(self._radio_single, 1)
        self._mode_group.addButton(self._radio_rgb, 3)
        self._mode_group.buttonToggled.connect(self._on_mode_toggled)

        mode_box = QHBoxLayout()
        mode_box.addWidget(self._radio_single)
        mode_box.addWidget(self._radio_rgb)
        ctrl_layout.addLayout(mode_box)

        # Indices Selection
        self._lbl_r = QLabel("R/灰度行:")
        self._spin_r = QSpinBox()
        self._spin_r.setRange(0, 2048)
        self._spin_r.setValue(512)

        self._lbl_g = QLabel("G行:")
        self._spin_g = QSpinBox()
        self._spin_g.setRange(0, 2048)
        self._spin_g.setValue(400)

        self._lbl_b = QLabel("B行:")
        self._spin_b = QSpinBox()
        self._spin_b.setRange(0, 2048)
        self._spin_b.setValue(600)

        for w in [self._spin_r, self._spin_g, self._spin_b]:
            w.valueChanged.connect(self._emit_config)

        ctrl_layout.addWidget(self._lbl_r)
        ctrl_layout.addWidget(self._spin_r)
        ctrl_layout.addWidget(self._lbl_g)
        ctrl_layout.addWidget(self._spin_g)
        ctrl_layout.addWidget(self._lbl_b)
        ctrl_layout.addWidget(self._spin_b)

        # Buffer Selection
        ctrl_layout.addWidget(QLabel("叠层高度:"))
        self._spin_lines = QSpinBox()
        self._spin_lines.setRange(1000, 10000)
        self._spin_lines.setValue(1000)
        self._spin_lines.setSingleStep(100)
        self._spin_lines.valueChanged.connect(self._resize_buffer)
        ctrl_layout.addWidget(self._spin_lines)

        ctrl_layout.addStretch()

        self._btn_save = QPushButton("保存图片")
        self._btn_save.clicked.connect(self._save_image)
        ctrl_layout.addWidget(self._btn_save)

        self._btn_reset = QPushButton("重置缩放")
        self._btn_reset.clicked.connect(self._reset_zoom)
        ctrl_layout.addWidget(self._btn_reset)

        layout.addLayout(ctrl_layout)

        # --- Image view ---
        self._image_view = pg.ImageView(view=_ImageViewBox(zoom_step=0.1))
        self._image_view.ui.roiBtn.hide()
        self._image_view.ui.menuBtn.hide()
        self._image_view.getView().setCursor(Qt.CursorShape.CrossCursor)
        layout.addWidget(self._image_view)

        # Buffer fields
        self._buffer: np.ndarray | None = None
        self._display_buffer: np.ndarray | None = None
        self._line_count = 0
        self._max_lines = 1000
        self._channels = 1
        self._write_index = 0
        self._render_pending = False
        self._interaction_until = 0.0

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_display)

        view_box = self._image_view.getView()
        view_box.sigRangeChanged.connect(self._mark_interacting)

        self._on_mode_toggled(None, False)

    def showEvent(self, event):
        super().showEvent(event)
        self._emit_config()

    def _on_mode_toggled(self, button, checked):
        is_rgb = self._radio_rgb.isChecked()
        self._lbl_r.setText("R行:" if is_rgb else "行索引:")
        self._lbl_g.setVisible(is_rgb)
        self._spin_g.setVisible(is_rgb)
        self._lbl_b.setVisible(is_rgb)
        self._spin_b.setVisible(is_rgb)
        self._channels = 3 if is_rgb else 1
        self._reset_buffer()
        self._emit_config()

    def _emit_config(self):
        if not self.isVisible():
            return
        is_rgb, indices = self.get_current_config()
        self.config_changed.emit(True, indices)

    def get_current_config(self) -> tuple[bool, list[int]]:
        is_rgb = self._radio_rgb.isChecked()
        if is_rgb:
            return True, [self._spin_r.value(), self._spin_g.value(), self._spin_b.value()]
        return False, [self._spin_r.value()]

    def _resize_buffer(self):
        self._max_lines = self._spin_lines.value()
        self._reset_buffer()

    def _reset_buffer(self):
        self._buffer = None
        self._display_buffer = None
        self._line_count = 0
        self._write_index = 0
        self._render_pending = False
        self._render_timer.stop()
        self._image_view.clear()

    def clear_display(self) -> None:
        """Clear buffered waterfall data and stop pending renders."""
        self._reset_buffer()

    def append_lines(self, lines_list: list[np.ndarray]):
        """Append a list of lines. 
        Each line in list is expected to be shape (channels, spatial_pixels).
        """
        if not lines_list:
            return

        c, w = lines_list[0].shape

        if c != self._channels:
            # Drop incoming lines if channel config doesn't match yet
            return

        h = self._max_lines

        if self._buffer is None or self._buffer.shape[1] != w:
            if c == 1:
                self._buffer = np.zeros((h, w), dtype=lines_list[0].dtype)
                self._display_buffer = np.zeros(
                    (h, w), dtype=lines_list[0].dtype)
            else:
                self._buffer = np.zeros((h, w, 3), dtype=lines_list[0].dtype)
                self._display_buffer = np.zeros(
                    (h, w, 3), dtype=lines_list[0].dtype)
            self._line_count = 0
            self._write_index = 0

        # Stack incoming list of lines
        if c == 1:
            # Vstack and drop the single channel dim: (N, w)
            new_lines = np.vstack(lines_list)
        else:
            # Lines are shape (3, w). Stack to (N, 3, w), then transpose to (N, w, 3)
            new_lines = np.stack(lines_list, axis=0).transpose(0, 2, 1)

        # Clip new lines to buffer height if too fast
        if new_lines.shape[0] > h:
            new_lines = new_lines[-h:]

        n = new_lines.shape[0]

        end = self._write_index + n
        if end <= h:
            self._buffer[self._write_index:end] = new_lines
        else:
            split = h - self._write_index
            self._buffer[self._write_index:] = new_lines[:split]
            self._buffer[:end - h] = new_lines[split:]

        self._write_index = end % h
        self._line_count = min(self._line_count + n, h)
        self._schedule_render()

    def _schedule_render(self):
        self._render_pending = True
        if not self._render_timer.isActive():
            self._render_timer.start(_LINE_SCAN_RENDER_INTERVAL_MS)

    def _mark_interacting(self, *args):
        self._interaction_until = time.perf_counter() + _INTERACTION_DEFER_SECONDS

    def _flush_display(self):
        if not self._render_pending:
            return

        if time.perf_counter() < self._interaction_until:
            self._render_timer.start(_LINE_SCAN_RENDER_INTERVAL_MS)
            return

        self._render_pending = False
        self._update_display()

    def _update_display(self):
        if self._buffer is None or self._display_buffer is None:
            return

        display_data = self._display_buffer
        display_data[...] = 0

        if self._line_count == 0:
            pass
        elif self._line_count < self._max_lines:
            display_data[-self._line_count:] = self._buffer[:self._line_count]
        elif self._write_index == 0:
            display_data[...] = self._buffer
        else:
            tail_len = self._max_lines - self._write_index
            display_data[:tail_len] = self._buffer[self._write_index:]
            display_data[tail_len:] = self._buffer[:self._write_index]

        if display_data.dtype in (np.float32, np.float64):
            display_data = np.clip(display_data, 0, 4095).astype(np.uint16)

        if display_data.ndim == 2:
            self._image_view.setImage(
                display_data.T, autoLevels=False, autoRange=False)
        else:
            img_8bit = (display_data.astype(np.float32) /
                        4095.0 * 255).astype(np.uint8)
            img_8bit = np.transpose(img_8bit, (1, 0, 2))
            self._image_view.setImage(img_8bit, autoRange=False)

    def _reset_zoom(self):
        self._image_view.autoRange()

    def _save_image(self):
        if self._buffer is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "", "PNG (*.png);;All Files (*)")
        if path:
            from PySide6.QtGui import QImage
            frame = self._buffer
            if frame.ndim == 3:
                # RGB
                img_8bit = (frame.astype(np.float32) /
                            4095.0 * 255).astype(np.uint8)
                h, w, c = img_8bit.shape
                qimg = QImage(img_8bit.data, w, h, w * c,
                              QImage.Format.Format_RGB888)
                qimg.save(path)
            else:
                # Grayscale
                img_8bit = (frame.astype(np.float32) /
                            4095.0 * 255).astype(np.uint8)
                h, w = img_8bit.shape
                qimg = QImage(img_8bit.data, w, h, w,
                              QImage.Format.Format_Grayscale8)
                qimg.save(path)
            logger.info("Line scan image saved to %s", path)
