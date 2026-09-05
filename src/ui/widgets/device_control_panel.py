"""Spectrum device control panel — acquisition and camera parameters."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.device.device_interface import DEFAULT_PIXEL_FORMAT, SUPPORTED_BINNING
from src.utils.config import AppConfig

logger = logging.getLogger("specdev.ui")


class DeviceControlPanel(QWidget):
    """Right-side acquisition controls and immutable device information."""

    start_requested = Signal()
    stop_requested = Signal()
    exposure_changed = Signal(float)
    gain_changed = Signal(float)
    pixel_format_changed = Signal(str)
    binning_changed = Signal(int, int)  # X(horizontal), Y(vertical)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._replaying = False
        self._supported_binning: tuple[tuple[int, int], ...] = SUPPORTED_BINNING
        self._saved_binning: tuple[int, int] = (1, 1)
        self._build_ui()
        self._config = AppConfig()
        self._load_settings()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        acq_group = QGroupBox("采集控制")
        acq_layout = QHBoxLayout(acq_group)
        acq_layout.setSpacing(8)
        self._btn_start = QPushButton("▶  开始采集")
        self._btn_start.setProperty("class", "btn-primary")
        self._btn_start.clicked.connect(self._on_start_clicked)
        self._btn_stop = QPushButton("■  停止采集")
        self._btn_stop.setProperty("class", "btn-danger")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        acq_layout.addWidget(self._btn_start)
        acq_layout.addWidget(self._btn_stop)
        outer.addWidget(acq_group)

        param_group = QGroupBox("设备参数")
        param_layout = QGridLayout(param_group)
        param_layout.setSpacing(6)
        row = 0

        self._spin_exposure = QDoubleSpinBox()
        self._spin_exposure.setRange(3.0, 1_000_000.0)
        self._spin_exposure.setDecimals(1)
        self._spin_exposure.setSingleStep(1.0)
        self._spin_exposure.setValue(10000.0)
        self._spin_exposure.setSuffix(" µs")
        self._spin_exposure.setKeyboardTracking(False)
        self._spin_exposure.valueChanged.connect(self._on_exposure_changed)
        row = self._add_param(param_layout, row, "曝光时间 (µs):", self._spin_exposure)

        self._spin_gain = QDoubleSpinBox()
        self._spin_gain.setRange(0.0, 24.0)
        self._spin_gain.setDecimals(1)
        self._spin_gain.setSingleStep(0.1)
        self._spin_gain.setValue(0.0)
        self._spin_gain.setSuffix(" dB")
        self._spin_gain.setKeyboardTracking(False)
        self._spin_gain.valueChanged.connect(self._on_gain_changed)
        row = self._add_param(param_layout, row, "增益 (dB):", self._spin_gain)

        self._combo_pixel_format = QComboBox()
        self._combo_pixel_format.addItem(DEFAULT_PIXEL_FORMAT)
        self._combo_pixel_format.setEnabled(False)
        self._combo_pixel_format.currentTextChanged.connect(self._on_pixel_format_changed)
        row = self._add_param(param_layout, row, "像素格式:", self._combo_pixel_format)

        self._combo_binning = QComboBox()
        self._combo_binning.setToolTip(
            "X 为水平方向（图像宽度），Y 为垂直方向（图像高度）。"
            "切换仅允许在停止采集且未录制时进行。"
        )
        self._combo_binning.currentIndexChanged.connect(self._on_binning_changed)
        self._populate_binning_modes(self._supported_binning, current=(1, 1))
        row = self._add_param(param_layout, row, "像元 Binning (X×Y):", self._combo_binning)

        self._lbl_resolution = self._value_label("1280 × 1024")
        row = self._add_param(param_layout, row, "分辨率:", self._lbl_resolution)
        self._lbl_sensor = self._value_label("Sony IMX990")
        row = self._add_param(param_layout, row, "传感器:", self._lbl_sensor)
        self._lbl_temperature = self._value_label("--")
        row = self._add_param(param_layout, row, "温度:", self._lbl_temperature)
        self._lbl_adc = self._value_label("12-bit")
        row = self._add_param(param_layout, row, "ADC 位深:", self._lbl_adc)
        self._lbl_max_fps = self._value_label("72.4 fps")
        row = self._add_param(param_layout, row, "最大帧率:", self._lbl_max_fps)
        self._lbl_status = self._value_label("已停止")
        self._lbl_status.setProperty("class", "status-stopped")
        self._add_param(param_layout, row, "设备状态:", self._lbl_status)

        outer.addWidget(param_group)

    @staticmethod
    def _value_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("class", "value")
        return label

    @staticmethod
    def _add_param(layout: QGridLayout, row: int, text: str, widget: QWidget) -> int:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)
        return row + 1

    # ── Settings persistence ───────────────────────────────────────

    def _load_settings(self) -> None:
        exposure = self._config.get_float("exposure_us", 10000.0)
        self._spin_exposure.blockSignals(True)
        self._spin_exposure.setValue(exposure)
        self._spin_exposure.blockSignals(False)

        gain = self._config.get_float("gain_db", 0.0)
        self._spin_gain.blockSignals(True)
        self._spin_gain.setValue(gain)
        self._spin_gain.blockSignals(False)

        self._combo_pixel_format.blockSignals(True)
        self._combo_pixel_format.setCurrentText(DEFAULT_PIXEL_FORMAT)
        self._combo_pixel_format.blockSignals(False)
        self._update_adc_label(DEFAULT_PIXEL_FORMAT)
        self._config.set("pixel_format", DEFAULT_PIXEL_FORMAT)

        saved_binning = (
            self._config.get_int("binning_x", 1),
            self._config.get_int("binning_y", 1),
        )
        self._saved_binning = saved_binning if saved_binning in SUPPORTED_BINNING else (1, 1)
        self._populate_binning_modes(self._supported_binning, self._saved_binning)

    def _save_settings(self) -> None:
        self._config.set("exposure_us", self._spin_exposure.value())
        self._config.set("gain_db", self._spin_gain.value())
        self._config.set("pixel_format", self._combo_pixel_format.currentText())
        bx, by = self.current_binning()
        self._saved_binning = (bx, by)
        self._config.set("binning_x", bx)
        self._config.set("binning_y", by)

    # ── Public API ─────────────────────────────────────────────────

    def sync_from_device(self, device, restore_saved_binning: bool = False) -> None:
        """Synchronize device info and optionally restore saved binning."""
        supported = tuple(device.get_supported_binning())
        current = device.get_binning()
        self._supported_binning = supported or ((1, 1),)
        selected = (
            self._saved_binning
            if restore_saved_binning and self._saved_binning in self._supported_binning
            else current
        )
        self._populate_binning_modes(self._supported_binning, current=selected)
        self.update_frame_shape(device.get_frame_shape())
        self.update_temperature_from_device(device)

        pixel_format = device.get_pixel_format()
        if pixel_format != DEFAULT_PIXEL_FORMAT:
            logger.warning("Device reported %s; UI requires %s", pixel_format, DEFAULT_PIXEL_FORMAT)
        self._combo_pixel_format.blockSignals(True)
        self._combo_pixel_format.setCurrentText(DEFAULT_PIXEL_FORMAT)
        self._combo_pixel_format.blockSignals(False)
        self._update_adc_label(DEFAULT_PIXEL_FORMAT)
        self._update_enabled_state()

    def update_frame_shape(self, shape: tuple[int, int]) -> None:
        """Update the read-only output resolution shown to the operator."""
        rows, cols = shape
        self._lbl_resolution.setText(f"{cols} × {rows}")

    def current_binning(self) -> tuple[int, int]:
        data = self._combo_binning.currentData()
        return tuple(data) if data is not None else (1, 1)

    def persist_current_binning(self) -> None:
        """Persist the currently displayed, device-confirmed binning mode."""
        bx, by = self.current_binning()
        self._saved_binning = (bx, by)
        self._config.set("binning_x", bx)
        self._config.set("binning_y", by)

    def update_temperature_from_device(self, device) -> None:
        try:
            temperature = device.get_temperature()
        except Exception as exc:
            logger.debug("Could not update camera temperature display: %s", exc)
            temperature = None
        self._lbl_temperature.setText("--" if temperature is None else f"{float(temperature):.1f} °C")

    def set_running(self, running: bool) -> None:
        self._running = running
        self._update_enabled_state()
        if running:
            self._lbl_status.setText("运行中")
            self._lbl_status.setProperty("class", "status-running")
        else:
            self._lbl_status.setText("已停止")
            self._lbl_status.setProperty("class", "status-stopped")
        self._lbl_status.style().unpolish(self._lbl_status)
        self._lbl_status.style().polish(self._lbl_status)

    def set_replaying(self, replaying: bool) -> None:
        self._replaying = replaying
        self._update_enabled_state()

    # ── Internal ───────────────────────────────────────────────────

    def _populate_binning_modes(
        self,
        modes: tuple[tuple[int, int], ...],
        current: tuple[int, int],
    ) -> None:
        self._combo_binning.blockSignals(True)
        self._combo_binning.clear()
        for bx, by in modes:
            label = "1 × 1（不 Binning）" if (bx, by) == (1, 1) else f"{bx} × {by}"
            self._combo_binning.addItem(label, (bx, by))
        index = next(
            (
                i
                for i in range(self._combo_binning.count())
                if tuple(self._combo_binning.itemData(i)) == tuple(current)
            ),
            0,
        )
        self._combo_binning.setCurrentIndex(index)
        self._combo_binning.blockSignals(False)

    def _update_enabled_state(self) -> None:
        editable = not self._running and not self._replaying
        self._btn_start.setEnabled(editable)
        self._btn_stop.setEnabled(self._running and not self._replaying)
        self._spin_exposure.setEnabled(not self._replaying)
        self._spin_gain.setEnabled(not self._replaying)
        self._combo_pixel_format.setEnabled(False)
        self._combo_binning.setEnabled(editable and self._combo_binning.count() > 1)

    def _on_start_clicked(self) -> None:
        self.start_requested.emit()

    def _on_stop_clicked(self) -> None:
        self.stop_requested.emit()

    def _on_exposure_changed(self, value: float) -> None:
        self.exposure_changed.emit(value)
        self._save_settings()

    def _on_gain_changed(self, value: float) -> None:
        self.gain_changed.emit(value)
        self._save_settings()

    def _on_pixel_format_changed(self, fmt: str) -> None:
        self._update_adc_label(fmt)
        self.pixel_format_changed.emit(fmt)
        self._save_settings()

    def _on_binning_changed(self, _index: int) -> None:
        bx, by = self.current_binning()
        self._save_settings()
        self.binning_changed.emit(bx, by)
        logger.info("Binning control changed to %dx%d", bx, by)

    def _update_adc_label(self, fmt: str) -> None:
        self._lbl_adc.setText({DEFAULT_PIXEL_FORMAT: "12-bit"}.get(fmt, "?"))
        self._lbl_max_fps.setText({DEFAULT_PIXEL_FORMAT: "72.4 fps"}.get(fmt, "72.4 fps"))
