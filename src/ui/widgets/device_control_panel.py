"""Spectrum device control panel (设备控制) — start/stop, exposure, gain, pixel format."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QDoubleSpinBox,
    QComboBox,
    QWidget,
    QSpinBox,
    QSizePolicy,
)
from PySide6.QtGui import QIcon
from src.utils.config import AppConfig

logger = logging.getLogger("specdev.ui")


class DeviceControlPanel(QWidget):
    """Right-side panel providing device start/stop and parameter controls.

    Signals
    -------
    start_requested : Signal()
        Emitted when the user clicks the Start button.
    stop_requested : Signal()
        Emitted when the user clicks the Stop button.
    exposure_changed : Signal(float)
        Emitted when the user changes the exposure value (µs).
    gain_changed : Signal(float)
        Emitted when the user changes the gain value (dB).
    pixel_format_changed : Signal(str)
        Emitted when the user changes the pixel format.
    """

    start_requested = Signal()
    stop_requested = Signal()
    exposure_changed = Signal(float)
    gain_changed = Signal(float)
    pixel_format_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._build_ui()
        self._config = AppConfig()
        self._load_settings()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # ── Acquisition control group ──────────────────────────────
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

        # ── Device parameters group ────────────────────────────────
        param_group = QGroupBox("设备参数")
        param_layout = QGridLayout(param_group)
        param_layout.setSpacing(6)

        row = 0

        # --- Exposure (µs) ---
        lbl_exp = QLabel("曝光时间 (µs):")
        lbl_exp.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._spin_exposure = QDoubleSpinBox()
        # CLAUDE.md: Min: 3µs–100µs (step 1µs); Standard: 13µs–1s (step 1 line period)
        # Using 1 µs step for full range to support both modes
        self._spin_exposure.setRange(3.0, 1_000_000.0)  # 3 µs – 1 s
        self._spin_exposure.setDecimals(1)
        self._spin_exposure.setSingleStep(1.0)  # 1 µs step per CLAUDE.md
        self._spin_exposure.setValue(10000.0)
        self._spin_exposure.setSuffix(" µs")
        self._spin_exposure.setKeyboardTracking(False)
        self._spin_exposure.valueChanged.connect(self._on_exposure_changed)
        param_layout.addWidget(lbl_exp, row, 0)
        param_layout.addWidget(self._spin_exposure, row, 1)
        row += 1

        # --- Gain (dB) ---
        lbl_gain = QLabel("增益 (dB):")
        lbl_gain.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._spin_gain = QDoubleSpinBox()
        self._spin_gain.setRange(0.0, 24.0)  # 0–24 dB
        self._spin_gain.setDecimals(1)
        self._spin_gain.setSingleStep(0.1)
        self._spin_gain.setValue(0.0)
        self._spin_gain.setSuffix(" dB")
        self._spin_gain.setKeyboardTracking(False)
        self._spin_gain.valueChanged.connect(self._on_gain_changed)
        param_layout.addWidget(lbl_gain, row, 0)
        param_layout.addWidget(self._spin_gain, row, 1)
        row += 1

        # --- Pixel Format ---
        lbl_pf = QLabel("像素格式:")
        lbl_pf.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._combo_pixel_format = QComboBox()
        self._combo_pixel_format.addItems(["Mono8", "Mono10", "Mono12"])
        self._combo_pixel_format.setCurrentText("Mono8")
        self._combo_pixel_format.currentTextChanged.connect(
            self._on_pixel_format_changed
        )
        param_layout.addWidget(lbl_pf, row, 0)
        param_layout.addWidget(self._combo_pixel_format, row, 1)
        row += 1

        # --- Resolution (read-only) ---
        lbl_res = QLabel("分辨率:")
        lbl_res.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_resolution = QLabel("1280 × 1024")
        self._lbl_resolution.setProperty("class", "value")
        param_layout.addWidget(lbl_res, row, 0)
        param_layout.addWidget(self._lbl_resolution, row, 1)
        row += 1

        # --- Sensor (read-only) ---
        lbl_sensor = QLabel("传感器:")
        lbl_sensor.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_sensor = QLabel("Sony IMX990")
        self._lbl_sensor.setProperty("class", "value")
        param_layout.addWidget(lbl_sensor, row, 0)
        param_layout.addWidget(self._lbl_sensor, row, 1)
        row += 1

        # --- Temperature (read-only, optional camera feature) ---
        lbl_temperature = QLabel("温度:")
        lbl_temperature.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_temperature = QLabel("--")
        self._lbl_temperature.setProperty("class", "value")
        param_layout.addWidget(lbl_temperature, row, 0)
        param_layout.addWidget(self._lbl_temperature, row, 1)
        row += 1

        # --- ADC Depth (read-only, follows pixel format) ---
        lbl_adc = QLabel("ADC 位深:")
        lbl_adc.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_adc = QLabel("8-bit")
        self._lbl_adc.setProperty("class", "value")
        param_layout.addWidget(lbl_adc, row, 0)
        param_layout.addWidget(self._lbl_adc, row, 1)
        row += 1

        # --- Frame Rate (read-only, informational) ---
        lbl_fps = QLabel("最大帧率:")
        lbl_fps.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_max_fps = QLabel("72.4 fps")
        self._lbl_max_fps.setProperty("class", "value")
        param_layout.addWidget(lbl_fps, row, 0)
        param_layout.addWidget(self._lbl_max_fps, row, 1)
        row += 1

        # --- Device Status ---
        lbl_status = QLabel("设备状态:")
        lbl_status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_status = QLabel("已停止")
        self._lbl_status.setProperty("class", "status-stopped")
        param_layout.addWidget(lbl_status, row, 0)
        param_layout.addWidget(self._lbl_status, row, 1)

        outer.addWidget(param_group)

    # ── Settings persistence ───────────────────────────────────────

    def _load_settings(self) -> None:
        """Load saved settings from QSettings and apply to controls."""
        # Load exposure (default 10000 µs)
        exposure = self._config.get_float("exposure_us", 10000.0)
        self._spin_exposure.blockSignals(True)
        self._spin_exposure.setValue(exposure)
        self._spin_exposure.blockSignals(False)

        # Load gain (default 0.0 dB)
        gain = self._config.get_float("gain_db", 0.0)
        self._spin_gain.blockSignals(True)
        self._spin_gain.setValue(gain)
        self._spin_gain.blockSignals(False)

        # Load pixel format (default Mono8)
        pixel_format = self._config.get_str("pixel_format", "Mono8")
        self._combo_pixel_format.blockSignals(True)
        self._combo_pixel_format.setCurrentText(pixel_format)
        self._combo_pixel_format.blockSignals(False)
        self._update_adc_label(pixel_format)

        logger.debug(
            "Loaded settings: exposure=%.1f µs, gain=%.1f dB, format=%s",
            exposure,
            gain,
            pixel_format,
        )

    def _save_settings(self) -> None:
        """Save current settings to QSettings."""
        self._config.set("exposure_us", self._spin_exposure.value())
        self._config.set("gain_db", self._spin_gain.value())
        self._config.set("pixel_format", self._combo_pixel_format.currentText())
        logger.debug(
            "Saved settings: exposure=%.1f µs, gain=%.1f dB, format=%s",
            self._spin_exposure.value(),
            self._spin_gain.value(),
            self._combo_pixel_format.currentText(),
        )

    # ── Public API ─────────────────────────────────────────────────

    def sync_from_device(self, device) -> None:
        """Read current device values and populate the controls.

        Note: This method only updates read-only device info fields.
        User-configurable settings (exposure, gain, pixel format) are
        loaded from QSettings in _load_settings() and should not be
        overwritten by device defaults.
        """
        # Update read-only device info only
        shape = device.get_frame_shape()
        self._lbl_resolution.setText(f"{shape[1]} × {shape[0]}")

        self.update_temperature_from_device(device)

        # Update ADC label based on current pixel format (from saved settings)
        self._update_adc_label(self._combo_pixel_format.currentText())

    def update_temperature_from_device(self, device) -> None:
        """Refresh the optional camera temperature display."""
        try:
            get_temperature = getattr(device, "get_temperature", None)
            temperature = get_temperature() if get_temperature else None
        except Exception as e:
            logger.debug("Could not update camera temperature display: %s", e)
            temperature = None

        if temperature is None:
            self._lbl_temperature.setText("--")
        else:
            self._lbl_temperature.setText(f"{float(temperature):.1f} °C")

    def set_running(self, running: bool) -> None:
        """Update UI state to reflect acquisition running/stopped."""
        self._running = running
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)

        # Disable parameter changes while running
        self._combo_pixel_format.setEnabled(not running)

        if running:
            self._lbl_status.setText("运行中")
            self._lbl_status.setProperty("class", "status-running")
        else:
            self._lbl_status.setText("已停止")
            self._lbl_status.setProperty("class", "status-stopped")
        # Force style refresh after property change
        self._lbl_status.style().unpolish(self._lbl_status)
        self._lbl_status.style().polish(self._lbl_status)

    def set_replaying(self, replaying: bool) -> None:
        """Disable controls during replay mode."""
        self._btn_start.setEnabled(not replaying)
        self._btn_stop.setEnabled(False)
        self._spin_exposure.setEnabled(not replaying)
        self._spin_gain.setEnabled(not replaying)
        self._combo_pixel_format.setEnabled(not replaying)

    # ── Private slots ──────────────────────────────────────────────

    def _on_start_clicked(self) -> None:
        self.start_requested.emit()

    def _on_stop_clicked(self) -> None:
        self.stop_requested.emit()

    def _on_exposure_changed(self, value: float) -> None:
        self.exposure_changed.emit(value)
        self._save_settings()
        logger.debug("Exposure control changed to %.1f µs", value)

    def _on_gain_changed(self, value: float) -> None:
        self.gain_changed.emit(value)
        self._save_settings()
        logger.debug("Gain control changed to %.1f dB", value)

    def _on_pixel_format_changed(self, fmt: str) -> None:
        self._update_adc_label(fmt)
        self.pixel_format_changed.emit(fmt)
        self._save_settings()
        logger.debug("Pixel format control changed to %s", fmt)

    def _update_adc_label(self, fmt: str) -> None:
        """Update ADC depth and max FPS labels based on pixel format."""
        adc_map = {"Mono8": "8-bit", "Mono10": "10-bit", "Mono12": "12-bit"}
        fps_map = {"Mono8": "135.54 fps", "Mono10": "72.4 fps", "Mono12": "72.4 fps"}
        self._lbl_adc.setText(adc_map.get(fmt, "?"))
        self._lbl_max_fps.setText(fps_map.get(fmt, "72.4 fps"))
