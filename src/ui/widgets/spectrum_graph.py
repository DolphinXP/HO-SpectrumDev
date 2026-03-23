"""Reusable pyqtgraph line chart widget for displaying 1D DN profiles.

Modeled after the reference LineChart widget with:
- Top toolbar: title, save button, 列(X)/行(Y) coordinate spinboxes
- Chart: pyqtgraph PlotWidget with cursor tracking (crosshair + tracer)
- Bottom bar: Y-axis range spinboxes, reset button, DN value display
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QToolButton, QFileDialog,
)


class SpectrumGraphWidget(QWidget):
    """Line chart widget for displaying 1D DN profiles.

    Parameters
    ----------
    title : str
        Chart title shown in top-left.
    orientation : str
        ``"horizontal"`` — chart x-axis = spatial pixel index (sweeps along
        a row at fixed Y). DN display: ``(chart_x, y_spin)``.
        ``"vertical"`` — chart x-axis = spectral band index (sweeps along
        a column at fixed X). DN display: ``(x_spin, chart_x)``.
    show_x, show_y : bool
        Which coordinate spinboxes to show. Hidden spinboxes still hold a
        value set via ``set_position`` so signals always carry valid (x, y).
    x_range, y_range : tuple[int, int]
        Min/max for the coordinate spinboxes.
    dn_max : int
        Default Y-axis upper bound (255 for Mono8, 4095 for Mono10/12).
    """

    # x, y emitted when user changes spinbox
    coordinate_changed = Signal(int, int)

    def __init__(
        self,
        title: str = "",
        x_label: str = "",
        y_label: str = "DN",
        orientation: str = "horizontal",
        show_x: bool = True,
        show_y: bool = True,
        x_range: tuple[int, int] = (0, 1279),
        y_range: tuple[int, int] = (0, 1023),
        dn_max: int = 4095,
        step_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._orientation = orientation
        self._dn_max = dn_max
        self._step_mode = step_mode
        self._x_data: np.ndarray = np.array([])
        self._y_data: np.ndarray = np.array([])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Top toolbar ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(2, 2, 2, 2)
        top_bar.setSpacing(4)

        top_bar.addWidget(QLabel(f"<b>{title}</b>"))

        # X coordinate spinbox (always created, optionally hidden)
        self._x_label = QLabel("列(X)")
        self._x_spin = QSpinBox()
        self._x_spin.setRange(*x_range)
        self._x_spin.setValue(x_range[0] + (x_range[1] - x_range[0]) // 2)
        self._x_spin.valueChanged.connect(self._on_coord_changed)
        top_bar.addWidget(self._x_label)
        top_bar.addWidget(self._x_spin)
        if not show_x:
            self._x_label.hide()
            self._x_spin.hide()

        # Y coordinate spinbox (always created, optionally hidden)
        self._y_label = QLabel("行(Y)")
        self._y_spin = QSpinBox()
        self._y_spin.setRange(*y_range)
        self._y_spin.setValue(y_range[0] + (y_range[1] - y_range[0]) // 2)
        self._y_spin.valueChanged.connect(self._on_coord_changed)
        top_bar.addWidget(self._y_label)
        top_bar.addWidget(self._y_spin)
        if not show_y:
            self._y_label.hide()
            self._y_spin.hide()

        top_bar.addStretch()

        fit_btn = QToolButton()
        fit_btn.setText("适应视图")
        fit_btn.clicked.connect(self.fit_to_view)
        top_bar.addWidget(fit_btn)

        save_btn = QToolButton()
        save_btn.setText("保存图片")
        save_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        save_btn.clicked.connect(self._save_image)
        top_bar.addWidget(save_btn)

        layout.addLayout(top_bar)

        # --- Chart ---
        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", x_label)
        self._plot.setLabel("left", y_label)
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setBackground("w")
        self._plot.setYRange(0, dn_max, padding=0)
        self._plot.enableAutoRange(axis='x', enable=False)
        self._plot.enableAutoRange(axis='y', enable=False)

        self._curve = self._plot.plot(
            pen=pg.mkPen(color="b", width=1.5),
            clipToView=True,
            autoDownsample=True,  # downsample only when many points
            stepMode="center" if self._step_mode else None,
        )

        # Crosshair: vertical tracking line + tracer dot
        self._vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("orange", width=1))
        self._tracer = pg.ScatterPlotItem(
            size=8, pen=pg.mkPen("orange"), brush=pg.mkBrush("yellow"))
        self._plot.addItem(self._vline)
        self._plot.addItem(self._tracer)
        self._vline.hide()

        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        layout.addWidget(self._plot)

        # --- Bottom bar ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(2, 2, 2, 2)
        bottom_bar.setSpacing(4)

        bottom_bar.addWidget(QLabel("Y轴显示范围"))

        self._y_range_low = QSpinBox()
        self._y_range_low.setRange(0, dn_max)
        self._y_range_low.setValue(0)
        self._y_range_low.valueChanged.connect(self._on_y_range_changed)
        bottom_bar.addWidget(self._y_range_low)

        bottom_bar.addWidget(QLabel("-"))

        self._y_range_high = QSpinBox()
        self._y_range_high.setRange(0, dn_max)
        self._y_range_high.setValue(dn_max)
        self._y_range_high.valueChanged.connect(self._on_y_range_changed)
        bottom_bar.addWidget(self._y_range_high)

        reset_btn = QToolButton()
        reset_btn.setText("重置")
        reset_btn.clicked.connect(self._reset_y_range)
        bottom_bar.addWidget(reset_btn)

        self._dn_label = QLabel("DN: --")
        self._dn_label.setStyleSheet("font-family: monospace;")
        bottom_bar.addWidget(self._dn_label)

        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)
        self.setMinimumWidth(500)

    # -------------------------------------------------------------- public API

    def update_plot(self, x_data: np.ndarray, y_data: np.ndarray) -> None:
        """Update the curve data. Skips repaint if widget is not exposed."""
        if not self.isVisible():
            return
        # Update X range only when data extent changes
        if len(x_data) > 0:
            x_min, x_max = float(x_data[0]), float(x_data[-1])
            if (len(self._x_data) == 0
                    or x_min != float(self._x_data[0])
                    or x_max != float(self._x_data[-1])):
                self._plot.setXRange(x_min, x_max, padding=0.02)
        self._x_data = x_data
        self._y_data = y_data
        plot_x = self._build_step_edges(x_data) if self._step_mode else x_data
        self._curve.setData(plot_x, y_data)

    def fit_to_view(self) -> None:
        """Fit the current curve into view, matching the built-in auto-range."""
        if len(self._x_data) == 0 or len(self._y_data) == 0:
            return

        x_min = float(np.min(self._x_data))
        x_max = float(np.max(self._x_data))
        y_min = float(np.min(self._y_data))
        y_max = float(np.max(self._y_data))

        if x_min == x_max:
            x_min -= 0.5
            x_max += 0.5
        if y_min == y_max:
            y_min -= 0.5
            y_max += 0.5

        x_pad = (x_max - x_min) * 0.02
        y_pad = (y_max - y_min) * 0.05

        self._plot.setXRange(x_min - x_pad, x_max + x_pad, padding=0)
        self._plot.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

        low = max(0, int(np.floor(y_min - y_pad)))
        high = min(self._dn_max, int(np.ceil(y_max + y_pad)))
        if low >= high:
            low = max(0, int(np.floor(y_min)))
            high = min(self._dn_max, max(low + 1, int(np.ceil(y_max))))

        self._y_range_low.blockSignals(True)
        self._y_range_high.blockSignals(True)
        self._y_range_low.setValue(low)
        self._y_range_high.setValue(high)
        self._y_range_low.blockSignals(False)
        self._y_range_high.blockSignals(False)

    def set_position(self, x: int, y: int) -> None:
        """Set coordinate spinboxes without emitting signal."""
        self._x_spin.blockSignals(True)
        self._y_spin.blockSignals(True)
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)
        self._x_spin.blockSignals(False)
        self._y_spin.blockSignals(False)

    def clear_plot(self) -> None:
        """Clear the curve."""
        self._curve.setData([], [])
        self._x_data = np.array([])
        self._y_data = np.array([])

    @property
    def plot_widget(self) -> pg.PlotWidget:
        return self._plot

    # ----------------------------------------------------------- internal slots

    def _on_coord_changed(self) -> None:
        self.coordinate_changed.emit(
            self._x_spin.value(), self._y_spin.value())

    def _on_mouse_moved(self, pos) -> None:
        vb = self._plot.getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
            self._vline.hide()
            self._tracer.setData([], [])
            return

        if len(self._x_data) == 0:
            return

        mouse_point = vb.mapSceneToView(pos)
        mx = mouse_point.x()

        # Find nearest data point
        idx = int(np.clip(np.searchsorted(
            self._x_data, mx), 0, len(self._x_data) - 1))
        if idx > 0 and abs(self._x_data[idx - 1] - mx) < abs(self._x_data[idx] - mx):
            idx -= 1

        data_x = float(self._x_data[idx])
        data_y = float(self._y_data[idx])

        self._vline.setPos(data_x)
        self._vline.show()
        self._tracer.setData([data_x], [data_y])

        # Build DN label: "DN: {value} ({pixel_x}, {pixel_y})"
        if self._orientation == "horizontal":
            pixel_x = int(data_x)
            pixel_y = self._y_spin.value()
        else:  # vertical
            pixel_x = self._x_spin.value()
            pixel_y = int(data_x)

        self._dn_label.setText(f"DN:  {int(data_y)} ({pixel_x}, {pixel_y})")

    def _on_y_range_changed(self) -> None:
        low = self._y_range_low.value()
        high = self._y_range_high.value()
        if low < high:
            self._plot.setYRange(low, high, padding=0)

    def _reset_y_range(self) -> None:
        self._y_range_low.blockSignals(True)
        self._y_range_high.blockSignals(True)
        self._y_range_low.setValue(0)
        self._y_range_high.setValue(self._dn_max)
        self._y_range_low.blockSignals(False)
        self._y_range_high.blockSignals(False)
        self._plot.setYRange(0, self._dn_max, padding=0)

    def _save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "", "PNG (*.png);;All Files (*)")
        if path:
            exporter = ImageExporter(self._plot.plotItem)
            exporter.export(path)

    def _build_step_edges(self, x_data: np.ndarray) -> np.ndarray:
        """Convert sample-center x positions into step edges for pyqtgraph."""
        if len(x_data) == 0:
            return x_data
        if len(x_data) == 1:
            x0 = float(x_data[0])
            return np.array([x0 - 0.5, x0 + 0.5], dtype=float)

        x_float = np.asarray(x_data, dtype=float)
        midpoints = (x_float[:-1] + x_float[1:]) / 2.0
        left_edge = x_float[0] - (midpoints[0] - x_float[0])
        right_edge = x_float[-1] + (x_float[-1] - midpoints[-1])
        return np.concatenate(([left_edge], midpoints, [right_edge]))
