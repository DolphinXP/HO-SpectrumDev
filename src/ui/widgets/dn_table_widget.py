"""DN table widget — per-pixel value grid with color coding."""

import logging
import time

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout, QLabel

logger = logging.getLogger("gpy4.ui")


class DNTableWidget(QWidget):
    """Per-pixel DN value grid (DN tab).

    Columns = spectral band indices (0..1023)
    Rows = spatial pixel indices (0..1279)
    Throttled to ~5 FPS for rendering performance.
    """

    pixel_selected = Signal(int, int)  # x (col/spatial), y (row/spectral)

    # Display a viewport rather than the full 1024×1280 table
    VIEWPORT_SIZE = 50  # show 50×50 cells around current position

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._info_label = QLabel("选择像素查看DN值")
        layout.addWidget(self._info_label)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

        self._frame: np.ndarray | None = None
        self._center_x: int = 640
        self._center_y: int = 512
        self._last_update: float = 0.0
        self._max_val: int = 255

    def update_frame(self, frame: np.ndarray) -> None:
        """Update with new frame data, throttled to ~5 FPS."""
        now = time.time()
        if now - self._last_update < 0.2:
            return
        self._last_update = now

        self._frame = frame
        self._max_val = 255 if frame.dtype == np.uint8 else 4095
        self._refresh_table()

    def set_center(self, x: int, y: int) -> None:
        """Set the viewport center position."""
        self._center_x = x
        self._center_y = y
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Rebuild the visible table cells around the center."""
        if self._frame is None:
            return

        rows, cols = self._frame.shape
        half = self.VIEWPORT_SIZE // 2

        y_start = max(0, self._center_y - half)
        y_end = min(rows, self._center_y + half)
        x_start = max(0, self._center_x - half)
        x_end = min(cols, self._center_x + half)

        n_rows = y_end - y_start
        n_cols = x_end - x_start

        self._table.setRowCount(n_rows)
        self._table.setColumnCount(n_cols)

        # Headers show absolute indices
        self._table.setHorizontalHeaderLabels(
            [str(x_start + c) for c in range(n_cols)])
        self._table.setVerticalHeaderLabels(
            [str(y_start + r) for r in range(n_rows)])

        block = self._frame[y_start:y_end, x_start:x_end]

        self._table.blockSignals(True)
        for r in range(n_rows):
            for c in range(n_cols):
                val = int(block[r, c])
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Color-code: dark=low DN, bright=high DN
                brightness = int(val / self._max_val * 200) + 30
                brightness = min(brightness, 255)
                item.setBackground(QColor(brightness, brightness, brightness))
                if brightness < 128:
                    item.setForeground(QColor(255, 255, 255))

                self._table.setItem(r, c, item)
        self._table.blockSignals(False)

        self._info_label.setText(
            f"视窗: 行 {y_start}-{y_end-1}, 列 {x_start}-{x_end-1}  "
            f"(中心 X={self._center_x}, Y={self._center_y})")

        # Resize columns to content
        self._table.resizeColumnsToContents()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Emit absolute pixel coordinates on cell click."""
        if self._frame is None:
            return
        half = self.VIEWPORT_SIZE // 2
        abs_y = max(0, self._center_y - half) + row
        abs_x = max(0, self._center_x - half) + col
        self.pixel_selected.emit(abs_x, abs_y)
