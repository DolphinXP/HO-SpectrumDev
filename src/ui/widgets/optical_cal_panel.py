"""Optical calibration panel (光校) — MTF display, pixel coordinates, DN neighborhood."""

import logging
import math

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem,
)

logger = logging.getLogger("gpy4.ui")


class OpticalCalPanel(QWidget):
    """Bottom-left 光校 panel with MTF display and DN neighborhood table.

    Contains:
    - 列(X) / 行(Y) spinboxes for pixel coordinate selection
    - 定位最大DN button
    - MTF cross display (above/below/left/right) with bordered boxes
    - Mean value, black level spinbox, averaging count combo
    - 9×9 DN neighborhood table
    """

    pixel_changed = Signal(int, int)  # x, y
    locate_max_dn = Signal()  # request to find max DN in frame
    avg_count_changed = Signal(int)  # 1, 5, or 10
    black_level_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # --- Pixel coordinate row ---
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel("列(X):"))
        self._x_spin = QSpinBox()
        self._x_spin.setRange(0, 1279)
        self._x_spin.setValue(640)
        self._x_spin.valueChanged.connect(self._on_coord_changed)
        coord_layout.addWidget(self._x_spin)

        coord_layout.addWidget(QLabel("行(Y):"))
        self._y_spin = QSpinBox()
        self._y_spin.setRange(0, 1023)
        self._y_spin.setValue(512)
        self._y_spin.valueChanged.connect(self._on_coord_changed)
        coord_layout.addWidget(self._y_spin)

        self._max_btn = QPushButton("定位最大DN")
        self._max_btn.clicked.connect(self.locate_max_dn.emit)
        coord_layout.addWidget(self._max_btn)
        coord_layout.addStretch()
        main_layout.addLayout(coord_layout)

        # --- MTF group (cross display + mean + settings) ---
        mtf_group = QGroupBox("MTF")
        mtf_main = QVBoxLayout(mtf_group)
        mtf_main.setSpacing(6)

        # Bordered value labels in cross layout
        mtf_grid = QGridLayout()
        mtf_grid.setSpacing(4)

        border_style = (
            "border: 1px solid #999; padding: 2px 8px; min-width: 40px;"
            " font-size: 14px; background: white;"
        )
        self._mtf_above = QLabel("0")
        self._mtf_below = QLabel("0")
        self._mtf_left = QLabel("0")
        self._mtf_right = QLabel("0")

        for lbl in (self._mtf_above, self._mtf_below,
                    self._mtf_left, self._mtf_right):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(border_style)

        #          [above]
        # [left]           [right]
        #          [below]
        mtf_grid.addWidget(self._mtf_above, 0, 1, Qt.AlignmentFlag.AlignCenter)
        mtf_grid.addWidget(self._mtf_left, 1, 0, Qt.AlignmentFlag.AlignCenter)
        mtf_grid.addWidget(self._mtf_right, 1, 2, Qt.AlignmentFlag.AlignCenter)
        mtf_grid.addWidget(self._mtf_below, 2, 1, Qt.AlignmentFlag.AlignCenter)
        mtf_main.addLayout(mtf_grid)

        # Mean value
        self._mtf_mean_label = QLabel("均值: 0")
        mtf_main.addWidget(self._mtf_mean_label)

        # Settings row (combo + black level) inside MTF group
        mtf_settings = QHBoxLayout()
        self._avg_combo = QComboBox()
        self._avg_combo.addItems(["每1帧计算", "每5帧计算", "每10帧计算"])
        self._avg_combo.currentIndexChanged.connect(self._on_avg_changed)
        mtf_settings.addWidget(self._avg_combo)

        mtf_settings.addWidget(QLabel("暗电平:"))
        self._bl_spin = QDoubleSpinBox()
        self._bl_spin.setRange(0, 4095)
        self._bl_spin.setDecimals(1)
        self._bl_spin.setValue(0.0)
        self._bl_spin.valueChanged.connect(self.black_level_changed.emit)
        mtf_settings.addWidget(self._bl_spin)
        mtf_settings.addStretch()
        mtf_main.addLayout(mtf_settings)

        mtf_group.setMinimumHeight(150)
        main_layout.addWidget(mtf_group)

        # --- 9×9 DN Neighborhood Table ---
        dn_group = QGroupBox("DN邻域 (9×9)")
        dn_layout = QVBoxLayout(dn_group)
        self._dn_table = QTableWidget(9, 9)
        self._dn_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dn_table.horizontalHeader().setDefaultSectionSize(48)
        self._dn_table.verticalHeader().setDefaultSectionSize(24)
        dn_group.setMinimumHeight(150)
        dn_layout.addWidget(self._dn_table)
        main_layout.addWidget(dn_group)

        self.setMinimumWidth(300)
        self.setMinimumHeight(250)
        main_layout.addStretch()

    def set_pixel(self, x: int, y: int) -> None:
        """Set pixel coordinates without emitting signal."""
        self._x_spin.blockSignals(True)
        self._y_spin.blockSignals(True)
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)
        self._x_spin.blockSignals(False)
        self._y_spin.blockSignals(False)

    def get_pixel(self) -> tuple[int, int]:
        return self._x_spin.value(), self._y_spin.value()

    def update_dn_neighborhood(self, frame: np.ndarray, x: int, y: int) -> None:
        """Populate the 9×9 DN table centered on (x, y)."""
        rows, cols = frame.shape

        # Update headers
        row_labels = [str(y - 4 + r) for r in range(9)]
        col_labels = [str(x - 4 + c) for c in range(9)]
        self._dn_table.setVerticalHeaderLabels(row_labels)
        self._dn_table.setHorizontalHeaderLabels(col_labels)

        for r in range(9):
            for c in range(9):
                dy = y - 4 + r
                dx = x - 4 + c
                if 0 <= dy < rows and 0 <= dx < cols:
                    val = str(int(frame[dy, dx]))
                else:
                    val = "-"
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # Highlight center cell
                if r == 4 and c == 4:
                    item.setBackground(Qt.GlobalColor.yellow)
                self._dn_table.setItem(r, c, item)

    def update_mtf(self, result: dict | None) -> None:
        """Update MTF cross display from MTFCalculator result."""
        if result is None:
            return

        def fmt(val: float) -> str:
            if math.isnan(val):
                return "无效值"
            return f"{val:.3f}"

        self._mtf_above.setText(fmt(result.get("above", float("nan"))))
        self._mtf_below.setText(fmt(result.get("below", float("nan"))))
        self._mtf_left.setText(fmt(result.get("left", float("nan"))))
        self._mtf_right.setText(fmt(result.get("right", float("nan"))))
        mean_val = result.get("mean", float("nan"))
        self._mtf_mean_label.setText(f"均值: {fmt(mean_val)}")

    def _on_coord_changed(self) -> None:
        self.pixel_changed.emit(self._x_spin.value(), self._y_spin.value())

    def _on_avg_changed(self, index: int) -> None:
        count = [1, 5, 10][index]
        self.avg_count_changed.emit(count)
