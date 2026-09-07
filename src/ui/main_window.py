"""Main window — full layout and signal wiring."""

import logging
import os
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QMainWindow,
    QToolBar,
    QSplitter,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QStatusBar,
    QMessageBox,
    QScrollArea,
    QFileDialog,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvg import QSvgRenderer

from src.device.device_interface import DeviceInterface
from src.data.acquisition import AcquisitionWorker
from src.data.storage import StorageManager
from src.data.replay_worker import ReplayWorker
from src.analysis.mtf import MTFCalculator
from src.analysis.spectral import SpectralAnalyzer
from src.ui.widgets.image_display import ImageDisplayWidget
from src.ui.widgets.stats_panel import StatsPanel
from src.ui.widgets.aux_data_panel import AuxDataPanel
from src.ui.widgets.optical_cal_panel import OpticalCalPanel
from src.ui.widgets.storage_dialog import StorageDialog
from src.ui.widgets.spectrum_graph import SpectrumGraphWidget
from src.ui.widgets.replay_control import ReplayControlWidget
from src.ui.widgets.device_control_panel import DeviceControlPanel
from src.ui.widgets.recording_indicator import RecordingIndicator
from src.ui.widgets.line_scan_display import LineScanDisplayWidget
from src.ui.widgets.nuc_panel import NucPanel
from src.utils.config import AppConfig

logger = logging.getLogger("specdev.ui")

_ICON_COLOR = QColor(224, 224, 224)  # #e0e0e0 — light color for dark toolbar
_ICON_COLOR_CHECKED = QColor(
    30, 30, 46
)  # #1e1e2e — dark color for checked/highlighted state


def _make_pixmap(svg_path: str, color: QColor, size: QSize) -> QPixmap:
    renderer = QSvgRenderer(svg_path)
    if size.isEmpty():
        size = renderer.defaultSize()
        if size.isEmpty():
            size = QSize(24, 24)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def _icon(name: str) -> QIcon:
    """Load an SVG icon and tint it — light for normal, dark for checked/selected."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "images", name)
    icon = QIcon()
    # Normal state (unchecked) — light icon
    icon.addPixmap(
        _make_pixmap(path, _ICON_COLOR, QSize()), QIcon.Mode.Normal, QIcon.State.Off
    )
    icon.addPixmap(
        _make_pixmap(path, _ICON_COLOR, QSize()), QIcon.Mode.Active, QIcon.State.Off
    )
    # Checked state — dark icon (for when button is highlighted/checked with blue bg)
    icon.addPixmap(
        _make_pixmap(path, _ICON_COLOR_CHECKED, QSize()),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    icon.addPixmap(
        _make_pixmap(path, _ICON_COLOR_CHECKED, QSize()),
        QIcon.Mode.Active,
        QIcon.State.On,
    )
    icon.addPixmap(
        _make_pixmap(path, _ICON_COLOR_CHECKED, QSize()),
        QIcon.Mode.Selected,
        QIcon.State.On,
    )
    return icon


# UI refresh interval (ms).  The QTimer fires at this rate and picks up
# whatever frame the acquisition thread last wrote into the ping-pong
# buffer.  33 ms ≈ 30 Hz — fast enough for smooth display, light enough
# to leave the event loop responsive for user input.
_UI_REFRESH_MS = 16

# Camera temperature changes slowly and does not need frame-rate polling.
_TEMPERATURE_REFRESH_MS = 2000

# Heavy analysis (MTF / spectral plots / DN neighborhood) runs at a
# lower cadence to avoid saturating the main thread.
_HEAVY_UPDATE_INTERVAL = 0.10  # seconds → ~10 Hz


class MainWindow(QMainWindow):
    """Main application window with complete layout per CLAUDE.md spec."""

    def __init__(self, device: DeviceInterface, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("高光谱相机控制软件")
        self.resize(1600, 900)
        _ico = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "app.ico")
        self.setWindowIcon(QIcon(_ico))

        self._device = device

        # --- Core modules ---
        self._mtf = MTFCalculator()
        self._spectral = SpectralAnalyzer()
        self._storage = StorageManager()
        self._acquisition = AcquisitionWorker(device)
        self._nuc = self._acquisition.nuc  # shared NUC instance
        self._config = AppConfig()

        # Current state
        self._selected_x: int = 640
        self._selected_y: int = 512
        self._current_frame: np.ndarray | None = None
        self._active_frame_shape: tuple[int, int] = device.get_frame_shape()
        self._running: bool = False
        self._replaying: bool = False
        self._line_scan_active: bool = False

        # Replay worker
        self._replay_worker: ReplayWorker | None = None

        # Throttle control for heavy UI updates
        self._last_heavy_update: float = 0.0

        # Load stylesheet
        self._load_stylesheet()

        # Build UI
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        # Initialize widgets with current pixel format
        initial_fmt = self._device.get_pixel_format()
        self._update_widgets_for_pixel_format(initial_fmt)

        # Wire signals
        self._wire_signals()
        self._apply_frame_shape(self._device.get_frame_shape())

        # --- UI refresh timer (ping-pong consumer) ---
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._refresh_timer.timeout.connect(self._poll_frame)

        self._temperature_timer = QTimer(self)
        self._temperature_timer.timeout.connect(self._refresh_temperature)
        self._temperature_timer.start(_TEMPERATURE_REFRESH_MS)

        self._apply_display_mode()
        logger.info("MainWindow initialized")

    def _load_stylesheet(self) -> None:
        qss_path = os.path.join(os.path.dirname(__file__), "styles.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ------------------------------------------------------------------ toolbar
    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)

        # Start/Stop buttons are now in DeviceControlPanel (right panel)

        # Modes toggle (exclusive)
        from PySide6.QtGui import QActionGroup

        act_group = QActionGroup(self)

        self._act_mode_area = QAction(_icon("full-area.svg"), "面阵", self)
        self._act_mode_area.setCheckable(True)
        self._act_mode_area.setChecked(True)
        self._act_mode_area.toggled.connect(self._on_mode_toggled)
        act_group.addAction(self._act_mode_area)
        tb.addAction(self._act_mode_area)

        self._act_mode_line = QAction(_icon("line-scan.svg"), "线扫", self)
        self._act_mode_line.setCheckable(True)
        self._act_mode_line.toggled.connect(self._on_mode_toggled)
        act_group.addAction(self._act_mode_line)
        tb.addAction(self._act_mode_line)

        tb.addSeparator()

        self._act_playback = QAction(_icon("replay.svg"), "开始回放", self)
        self._act_playback.triggered.connect(self._on_playback)
        tb.addAction(self._act_playback)

        self._act_stop_playback = QAction(_icon("stop.svg"), "停止回放", self)
        self._act_stop_playback.setEnabled(False)
        self._act_stop_playback.triggered.connect(self._teardown_replay)
        tb.addAction(self._act_stop_playback)

        tb.addSeparator()

        self._act_start_save = QAction(_icon("save.svg"), "开始存储", self)
        self._act_start_save.triggered.connect(self._on_start_save)
        tb.addAction(self._act_start_save)

        self._act_stop_save = QAction(_icon("stop-save.svg"), "停止存储", self)
        self._act_stop_save.setEnabled(False)
        self._act_stop_save.triggered.connect(self._on_stop_save)
        tb.addAction(self._act_stop_save)

        tb.addSeparator()

        # 光校 toggle — show/hide optical calibration bottom panel
        self._act_optical_cal = QAction(_icon("calibration.svg"), "光校", self)
        self._act_optical_cal.setCheckable(True)
        self._act_optical_cal.setChecked(True)
        self._act_optical_cal.toggled.connect(self._on_optical_cal_toggled)
        tb.addAction(self._act_optical_cal)

        tb.addSeparator()

        self._act_settings = QAction(_icon("setting.svg"), "设置", self)
        self._act_settings.triggered.connect(self._on_settings)
        tb.addAction(self._act_settings)

        self._act_about = QAction(_icon("about.svg"), "关于", self)
        self._act_about.triggered.connect(self._on_about)
        tb.addAction(self._act_about)

        self._act_exit = QAction(_icon("exit.svg"), "Exit", self)
        self._act_exit.triggered.connect(self.close)
        tb.addAction(self._act_exit)

    # --------------------------------------------------------------- central
    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(2, 2, 2, 2)

        # Top/bottom vertical splitter
        self._v_splitter = QSplitter(Qt.Orientation.Vertical)
        root_layout.addWidget(self._v_splitter)

        # ---- TOP HALF: image + right panels ----
        self._h_splitter_top = QSplitter(Qt.Orientation.Horizontal)
        self._v_splitter.addWidget(self._h_splitter_top)

        # Left: Image display with replay control
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        from PySide6.QtWidgets import QStackedWidget

        self._display_stack = QStackedWidget()

        self._image_display = ImageDisplayWidget()
        self._line_scan_display = LineScanDisplayWidget()
        self._line_scan_display.config_changed.connect(
            lambda en, idxs: self._acquisition.set_line_scan_mode(
                en and self._act_mode_line.isChecked(), idxs
            )
        )

        self._display_stack.addWidget(self._image_display)
        self._display_stack.addWidget(self._line_scan_display)

        image_layout.addWidget(self._display_stack)

        # Replay control (initially hidden)
        self._replay_control = ReplayControlWidget()
        self._replay_control.setVisible(False)
        self._replay_control.play_clicked.connect(self._on_replay_play)
        self._replay_control.pause_clicked.connect(self._on_replay_pause)
        self._replay_control.stop_clicked.connect(self._on_replay_stop)
        self._replay_control.close_clicked.connect(self._on_replay_close)
        self._replay_control.position_changed.connect(self._on_replay_position_changed)
        self._replay_control.speed_changed.connect(self._on_replay_speed_changed)
        self._replay_control.loop_changed.connect(self._on_replay_loop_changed)
        image_layout.addWidget(self._replay_control)

        self._h_splitter_top.addWidget(image_container)

        # Right: device control + stats + aux panels in a scroll area
        right_inner = QWidget()
        right_layout = QVBoxLayout(right_inner)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)

        self._device_control = DeviceControlPanel()
        self._nuc_panel = NucPanel()
        self._stats_panel = StatsPanel()
        self._aux_panel = AuxDataPanel()

        right_layout.addWidget(self._device_control)
        right_layout.addWidget(self._nuc_panel)
        right_layout.addWidget(self._stats_panel)
        right_layout.addWidget(self._aux_panel)
        right_layout.addStretch()

        # Wrap in scroll area for vertical overflow
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setWidget(right_inner)
        right_scroll.setMinimumWidth(260)

        self._h_splitter_top.addWidget(right_scroll)

        self._h_splitter_top.setSizes([1200, 300])
        self._h_splitter_top.setCollapsible(1, False)  # prevent right panel collapse

        # ---- BOTTOM HALF: optical cal panel + spectrum graphs ----
        self._bottom_container = QWidget()
        bottom_container_layout = QHBoxLayout(self._bottom_container)
        bottom_container_layout.setContentsMargins(0, 0, 0, 0)
        bottom_container_layout.setSpacing(0)

        # Bottom-left: 光校 optical calibration panel
        self._optical_cal_panel = OpticalCalPanel()
        self._optical_cal_scroll = QScrollArea()
        self._optical_cal_scroll.setWidgetResizable(False)
        self._optical_cal_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._optical_cal_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._optical_cal_scroll.setWidget(self._optical_cal_panel)
        self._optical_cal_scroll.setMinimumSize(300, 250)
        bottom_container_layout.addWidget(self._optical_cal_scroll)

        # Scrollable area for the 4 spectrum graphs
        charts_scroll = QScrollArea()
        charts_scroll.setWidgetResizable(True)
        charts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        charts_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        charts_widget = QWidget()
        charts_layout = QHBoxLayout(charts_widget)
        charts_layout.setContentsMargins(0, 0, 0, 0)

        # 4 spectrum graphs
        self._graph_near_spatial = SpectrumGraphWidget(
            title="临近空间维(行)",
            x_label="空间像素",
            y_label="DN",
            orientation="horizontal",
            show_x=True,
            show_y=True,
            step_mode=True,
        )
        self._graph_near_spectral = SpectrumGraphWidget(
            title="临近光谱维(列)",
            x_label="光谱通道",
            y_label="DN",
            orientation="vertical",
            show_x=True,
            show_y=True,
            step_mode=True,
        )
        self._graph_full_spatial = SpectrumGraphWidget(
            title="全域空间维(行)",
            x_label="空间像素",
            y_label="DN",
            orientation="horizontal",
            show_x=False,
            show_y=True,
        )
        self._graph_full_spectral = SpectrumGraphWidget(
            title="全域光谱维(列)",
            x_label="光谱通道",
            y_label="DN",
            orientation="vertical",
            show_x=True,
            show_y=False,
        )

        for g in (
            self._graph_near_spatial,
            self._graph_near_spectral,
            self._graph_full_spatial,
            self._graph_full_spectral,
        ):
            g.setMinimumWidth(560)
            g.setMinimumHeight(220)
            charts_layout.addWidget(g)

        charts_scroll.setWidget(charts_widget)
        bottom_container_layout.addWidget(charts_scroll, 1)

        self._v_splitter.addWidget(self._bottom_container)
        self._v_splitter.setSizes([550, 350])

    # --------------------------------------------------------------- statusbar
    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_device = QLabel("设备: --")
        self._status_nuc = QLabel("NUC: 未加载")
        self._recording_indicator = RecordingIndicator(diameter=10)
        self._status_storage = QLabel("存储: 停止")
        sb.addWidget(self._status_device)
        sb.addPermanentWidget(self._status_nuc)
        sb.addPermanentWidget(self._recording_indicator)
        sb.addPermanentWidget(self._status_storage)

        device_name = self._device.__class__.__name__
        self._status_device.setText(f"设备: {device_name}")

    # --------------------------------------------------------------- signals
    def _wire_signals(self) -> None:
        # Stats signal (already throttled to ~4 Hz in acquisition worker)
        self._acquisition.stats_updated.connect(self._on_stats_updated)

        # Image display
        self._image_display.pixel_clicked.connect(self._on_pixel_selected)

        # Device control panel
        self._device_control.sync_from_device(self._device, restore_saved_binning=True)
        self._device_control.start_requested.connect(self._on_start)
        self._device_control.stop_requested.connect(self._on_stop)
        self._device_control.exposure_changed.connect(self._on_exposure_changed)
        self._device_control.gain_changed.connect(self._on_gain_changed)
        self._device_control.frame_rate_changed.connect(self._on_frame_rate_changed)
        self._device_control.pixel_format_changed.connect(self._on_pixel_format_changed)
        self._device_control.binning_changed.connect(self._on_binning_changed)
        self._on_binning_changed(*self._device_control.current_binning())

        # NUC panel
        self._nuc_panel.nuc_changed.connect(self._on_nuc_changed)
        # Restore NUC config
        a = self._config.get_str("nuc.a_path", "")
        b = self._config.get_str("nuc.b_path", "")
        en = self._config.get_bool("nuc.enabled", False)
        if a and b:
            self._nuc_panel.set_config(a, b, en)
            self._on_nuc_changed(a, b, en)

        # Spectrum graph coordinate spinboxes
        self._graph_near_spatial.coordinate_changed.connect(self._on_pixel_selected)
        self._graph_near_spectral.coordinate_changed.connect(self._on_pixel_selected)
        self._graph_full_spatial.coordinate_changed.connect(
            lambda x, y: self._on_pixel_selected(self._selected_x, y)
        )
        self._graph_full_spectral.coordinate_changed.connect(
            lambda x, y: self._on_pixel_selected(x, self._selected_y)
        )

        # Optical calibration panel
        self._optical_cal_panel.pixel_changed.connect(self._on_pixel_selected)
        self._optical_cal_panel.locate_max_dn.connect(self._on_locate_max_dn)
        self._optical_cal_panel.avg_count_changed.connect(self._mtf.set_avg_count)
        self._optical_cal_panel.black_level_changed.connect(self._mtf.set_black_level)

    # --------------------------------------------------------------- frame polling
    def _poll_frame(self) -> None:
        """Called by QTimer — pull the latest frame from the ping-pong buffer.

        This is the *only* path that delivers frames to the UI.  Because
        it runs inside the main-thread timer, it naturally yields to user
        input events between ticks, keeping the UI responsive.
        """
        result = self._acquisition.frame_buffer.pong()
        if result is None:
            return  # no new frame since last poll

        frame, metadata = result
        if frame.shape != self._active_frame_shape:
            self._current_frame = None
            self._apply_frame_shape(frame.shape)
        self._current_frame = frame
        # Prepare display frame for area scan mode & stats
        display_frame = frame
        if frame.dtype == np.float32:
            max_dn = self._get_max_dn_from_format(
                metadata.get("pixel_format", "Mono12")
            )
            display_frame = np.clip(frame, 0, max_dn).astype(np.uint16)

        if self._line_scan_active:
            lines = self._acquisition.pull_line_scan_data()
            if lines:
                self._line_scan_display.append_lines(lines)
        else:
            self._image_display.update_image(display_frame, metadata)

        # Aux data labels (lightweight)
        self._aux_panel.update_metadata(metadata)

        # Throttle heavy UI updates (MTF, DN neighborhood, spectral plots)
        now = time.perf_counter()
        if now - self._last_heavy_update < _HEAVY_UPDATE_INTERVAL:
            return
        self._last_heavy_update = now

        x, y = self._selected_x, self._selected_y

        if self._bottom_container.isVisible():
            mtf_result = self._mtf.update(frame, x, y)
            self._optical_cal_panel.update_mtf(mtf_result)
            self._optical_cal_panel.update_dn_neighborhood(display_frame, x, y)
            self._update_spectral_plots(display_frame, x, y)

    def _refresh_temperature(self) -> None:
        """Refresh slow-changing camera state without coupling it to frames."""
        self._device_control.update_temperature_from_device(self._device)

    # --------------------------------------------------------------- slots
    def _on_stats_updated(self, stats: dict) -> None:
        self._stats_panel.update_stats(stats)

    def _on_pixel_selected(self, x: int, y: int) -> None:
        """Handle pixel selection from any source."""
        self._selected_x = x
        self._selected_y = y
        self._optical_cal_panel.set_pixel(x, y)
        self._graph_near_spatial.set_position(x, y)
        self._graph_near_spectral.set_position(x, y)
        self._graph_full_spatial.set_position(x, y)
        self._graph_full_spectral.set_position(x, y)
        self._mtf.reset()  # Reset MTF accumulator on pixel change

        if self._current_frame is not None:
            frame = self._current_frame
            if frame.dtype == np.float32:
                pixel_format = self._device.get_pixel_format()
                max_dn = self._get_max_dn_from_format(pixel_format)
                frame = np.clip(frame, 0, max_dn).astype(np.uint16)
            self._update_spectral_plots(frame, x, y)
            self._optical_cal_panel.update_dn_neighborhood(frame, x, y)

    def _on_locate_max_dn(self) -> None:
        """Find and navigate to the pixel with maximum DN."""
        if self._current_frame is None:
            return
        frame = self._current_frame
        if frame.dtype == np.float32:
            pixel_format = self._device.get_pixel_format()
            max_dn = self._get_max_dn_from_format(pixel_format)
            frame = np.clip(frame, 0, max_dn).astype(np.uint16)
        idx = np.unravel_index(np.argmax(frame), frame.shape)
        y, x = int(idx[0]), int(idx[1])
        self._on_pixel_selected(x, y)
        logger.info("Max DN located at X=%d, Y=%d, DN=%d", x, y, int(frame[y, x]))

    def _on_mode_toggled(self, checked: bool) -> None:
        """Switch between area array (面阵) and line scan (线扫)."""
        self._apply_display_mode()

    def _apply_display_mode(self) -> None:
        """Activate exactly one display pipeline and disable the inactive one."""
        is_line_scan = self._act_mode_line.isChecked()
        self._line_scan_active = is_line_scan
        if is_line_scan:
            self._image_display.hide()
            self._display_stack.setCurrentWidget(self._line_scan_display)
            self._line_scan_display.show()
            self._line_scan_display._emit_config()
        else:
            self._acquisition.set_line_scan_mode(False)
            self._acquisition.pull_line_scan_data()
            self._line_scan_display.clear_display()
            self._line_scan_display.hide()
            self._display_stack.setCurrentWidget(self._image_display)
            self._image_display.show()

    def _on_optical_cal_toggled(self, checked: bool) -> None:
        """Show/hide the bottom optical calibration panel."""
        self._bottom_container.setVisible(checked)
        if checked:
            # Restore default vertical splitter sizes so the bottom panel
            # reappears at a usable height even if the user had collapsed it.
            self._v_splitter.setSizes([550, 350])

    def _update_spectral_plots(self, frame: np.ndarray, x: int, y: int) -> None:
        """Update the four spectrum graph widgets (only if visible)."""
        if self._graph_near_spatial.isVisible():
            xs, vs = self._spectral.near_spatial(frame, x, y)
            self._graph_near_spatial.update_plot(xs, vs)

        if self._graph_near_spectral.isVisible():
            xs2, vs2 = self._spectral.near_spectral(frame, x, y)
            self._graph_near_spectral.update_plot(xs2, vs2)

        if self._graph_full_spatial.isVisible():
            xs3, vs3 = self._spectral.full_spatial(frame, y)
            self._graph_full_spatial.update_plot(xs3, vs3)

        if self._graph_full_spectral.isVisible():
            xs4, vs4 = self._spectral.full_spectral(frame, x)
            self._graph_full_spectral.update_plot(xs4, vs4)

    # --------------------------------------------------------------- toolbar actions
    def _on_start(self) -> None:
        """Start acquisition."""
        self._acquisition.start()
        self._device.start()
        self._refresh_timer.start(_UI_REFRESH_MS)
        self._running = True
        self._device_control.set_running(True)
        logger.info("Acquisition started")

    def _on_stop(self) -> None:
        """Stop acquisition."""
        if self._storage.is_recording:
            self._on_stop_save()
        self._refresh_timer.stop()
        self._acquisition.stop()
        self._device.stop()
        self._running = False
        self._device_control.set_running(False)
        logger.info("Acquisition stopped")

    def _on_exposure_changed(self, value: float) -> None:
        """Apply exposure change to device."""
        self._device.set_exposure(value)
        logger.info("Exposure set to %.1f µs", value)

    def _on_gain_changed(self, value: float) -> None:
        """Apply gain change to device."""
        self._device.set_gain(value)
        logger.info("Gain set to %.1f dB", value)

    def _on_frame_rate_changed(self, value: float) -> None:
        """Apply frame-rate change to device (only when acquisition is stopped)."""
        if self._running:
            logger.warning("Cannot change frame rate while acquisition is running")
            return
        try:
            self._device.set_frame_rate(value)
            actual = self._device.get_frame_rate()
            logger.info("Frame rate set to %.2f fps", actual)
        except Exception as exc:
            logger.exception("Failed to set frame rate to %.2f fps", value)
            QMessageBox.critical(self, "帧率设置失败", f"无法设置采集帧率：{exc}")
            # Re-sync the spinbox with the device's last known good value.
            self._device_control.sync_from_device(self._device)

    def _on_pixel_format_changed(self, fmt: str) -> None:
        """Apply pixel format change to device (only when stopped)."""
        if self._running:
            logger.warning("Cannot change pixel format while running")
            return
        self._device.set_pixel_format(fmt)
        self._update_widgets_for_pixel_format(fmt)
        logger.info("Pixel format set to %s", fmt)

    def _on_binning_changed(self, binning_x: int, binning_y: int) -> None:
        """Apply a stopped-state hardware binning change and retarget all UI."""
        if self._running or self._storage.is_recording:
            logger.warning("Cannot change binning while acquiring or recording")
            return

        previous_shape = self._device.get_frame_shape()
        previous_binning = self._device.get_binning()
        try:
            self._device.set_binning(binning_x, binning_y)
            actual_binning = self._device.get_binning()
            shape = self._device.get_frame_shape()
        except Exception as exc:
            logger.exception("Failed to set binning to %dx%d", binning_x, binning_y)
            QMessageBox.critical(self, "Binning 设置失败", f"无法设置像元 Binning：{exc}")
            self._device_control.sync_from_device(self._device)
            self._device_control.persist_current_binning()
            return

        self._current_frame = None
        self._apply_frame_shape(shape)
        self._acquisition.frame_buffer.clear()
        self._mtf.reset()
        self._line_scan_display.clear_display()
        if self._nuc.is_loaded():
            logger.warning(
                "NUC coefficients remain loaded after binning change; they are skipped "
                "until their shape matches the new %s frame", shape,
            )
        logger.info(
            "Binning changed %dx%d -> %dx%d; frame shape %s -> %s",
            *previous_binning,
            *actual_binning,
            previous_shape,
            shape,
        )

    def _apply_frame_shape(self, shape: tuple[int, int]) -> None:
        """Update all coordinate-driven widgets for a binned output shape."""
        rows, cols = shape
        self._active_frame_shape = shape
        self._device_control.update_frame_shape(shape)
        self._optical_cal_panel.set_frame_shape(shape)
        for graph in (
            self._graph_near_spatial,
            self._graph_near_spectral,
            self._graph_full_spatial,
            self._graph_full_spectral,
        ):
            graph.set_frame_shape(shape)
        self._line_scan_display.set_spectral_rows(rows)

        self._selected_x = min(max(0, self._selected_x), cols - 1)
        self._selected_y = min(max(0, self._selected_y), rows - 1)
        self._on_pixel_selected(self._selected_x, self._selected_y)

    def _update_widgets_for_pixel_format(self, fmt: str) -> None:
        """Update all widgets' max DN values based on pixel format.

        Args:
            fmt: The pixel format string (e.g., "Mono8", "Mono10", "Mono12")
        """
        # Calculate max value from pixel format
        bits = int(fmt[4:])  # Extract number after "Mono"
        max_dn = (1 << bits) - 1  # 2^bits - 1

        # Update spectrum graphs
        self._graph_near_spatial.set_dn_max(max_dn)
        self._graph_near_spectral.set_dn_max(max_dn)
        self._graph_full_spatial.set_dn_max(max_dn)
        self._graph_full_spectral.set_dn_max(max_dn)

        # Update optical calibration panel
        self._optical_cal_panel.set_max_dn(max_dn)

        # Update line scan display
        self._line_scan_display.set_max_dn(max_dn)

        logger.debug("Updated widgets for pixel format %s: max_dn=%d", fmt, max_dn)

    @staticmethod
    def _get_max_dn_from_format(fmt: str) -> int:
        """Get max DN value from pixel format.

        Args:
            fmt: The pixel format string (e.g., "Mono8", "Mono10", "Mono12")

        Returns:
            The maximum DN value (2^bits - 1)
        """
        bits = int(fmt[4:])  # Extract number after "Mono"
        return (1 << bits) - 1  # 2^bits - 1

    def _on_nuc_changed(self, a_path: str, b_path: str, enabled: bool) -> None:
        """Handle NUC parameter changes from the NUCPanel."""
        try:
            # Only reload if files changed or not loaded
            current_a = self._config.get_str("nuc.a_path")
            current_b = self._config.get_str("nuc.b_path")

            if a_path and b_path:
                if (
                    a_path != current_a
                    or b_path != current_b
                    or not self._nuc.is_loaded()
                ):
                    self._nuc.load(a_path, b_path, self._device.get_frame_shape())
                    self._config.set("nuc.a_path", a_path)
                    self._config.set("nuc.b_path", b_path)

            self._nuc.enabled = enabled
            self._config.set("nuc.enabled", enabled)

            # Update UI
            loaded = self._nuc.is_loaded()
            self._nuc_panel.set_nuc_status(loaded)

            if loaded and enabled:
                self._status_nuc.setText("NUC: 启用")
                self._status_nuc.setStyleSheet("color: #27ae60; font-weight: bold;")
            elif loaded:
                self._status_nuc.setText("NUC: 已加载")
                self._status_nuc.setStyleSheet("color: #2980b9; font-weight: bold;")
            else:
                self._status_nuc.setText("NUC: 未加载")
                self._status_nuc.setStyleSheet("color: #e74c3c; font-weight: bold;")

            logger.info("NUC state changed: loaded=%s, enabled=%s", loaded, enabled)

        except Exception as e:
            logger.error("Failed to load NUC: %s", e)
            QMessageBox.critical(self, "NUC 错误", f"加载 NUC 数据失败: {e}")
            self._nuc.unload()
            self._status_nuc.setText("NUC: 错误")
            self._status_nuc.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _recording_metadata(self, pixel_format: str) -> dict:
        """Build immutable recording provenance for the active camera mode."""
        rows, cols = self._device.get_frame_shape()
        binning_x, binning_y = self._device.get_binning()
        return {
            "width": cols,
            "height": rows,
            "pixel_format": pixel_format,
            "binning_x": binning_x,
            "binning_y": binning_y,
            "binning": f"{binning_x}x{binning_y}",
            "original_width": 1280,
            "original_height": 1024,
            "exposure_us": self._device.get_exposure(),
            "gain_db": self._device.get_gain(),
        }

    def _on_start_save(self) -> None:
        """Show storage dialog and start recording to disk."""
        dlg = StorageDialog(
            self,
            initial_directory=self._config.get_str("storage.last_directory", ""),
        )
        if dlg.exec() != StorageDialog.DialogCode.Accepted or dlg.result_info is None:
            return

        info = dlg.result_info
        directory = info["directory"]
        session_name = info["session_name"]
        pixel_format = self._device.get_pixel_format()
        metadata = self._recording_metadata(pixel_format)
        suffix = f"Bin{metadata['binning']}_{metadata['width']}x{metadata['height']}"
        session_name = f"{session_name}_{suffix}"

        if info["save_envi"]:
            self._storage.start_envi(directory, session_name, pixel_format, metadata=metadata)
        if info["save_raw"]:
            self._storage.start_raw(directory, session_name, pixel_format, metadata=metadata)

        self._config.set("storage.last_directory", directory)

        # Let acquisition thread write every frame directly
        self._acquisition.storage = self._storage

        self._act_start_save.setEnabled(False)
        self._act_stop_save.setEnabled(True)
        self._status_storage.setText("存储: 录制中")
        self._recording_indicator.start()
        logger.info("Storage started: %s/%s", directory, session_name)

    def _on_stop_save(self) -> None:
        """Stop recording."""
        self._acquisition.storage = None
        self._storage.stop()
        self._act_start_save.setEnabled(True)
        self._act_stop_save.setEnabled(False)
        self._status_storage.setText("存储: 停止")
        self._recording_indicator.stop()
        logger.info("Storage stopped")

    def _on_playback(self) -> None:
        """Start playback mode - load saved data file."""
        # Check if acquisition is running
        if self._running:
            reply = QMessageBox.question(
                self,
                "确认",
                "回放需要停止当前采集。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_stop()
            else:
                return

        self._teardown_replay()

        # Open file dialog to select .dat file
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择数据文件",
            self._config.get_str("replay.last_directory", ""),
            "数据文件 (*.dat);;所有文件 (*.*)",
        )

        if not file_path:
            return

        # Validate that .hdr or .json exists
        from pathlib import Path

        dat_path = Path(file_path)
        hdr_path = dat_path.with_suffix(".hdr")
        json_path = dat_path.with_suffix(".json")

        if not hdr_path.exists() and not json_path.exists():
            QMessageBox.warning(
                self, "文件错误", "缺少配套文件：需要 .hdr 或 .json 文件"
            )
            return

        # Create and start replay worker
        self._replay_worker = ReplayWorker()
        self._replay_worker.frame_ready.connect(self._on_replay_frame)
        self._replay_worker.progress_changed.connect(self._on_replay_progress)
        self._replay_worker.playback_finished.connect(self._on_replay_finished)
        self._replay_worker.error_occurred.connect(self._on_replay_error)

        # Load file
        if not self._replay_worker.load_file(file_path):
            self._replay_worker = None
            return

        self._config.set("replay.last_directory", str(dat_path.parent))

        # Show replay control and start worker thread
        self._replay_control.setVisible(True)
        self._replay_control.set_range(self._replay_worker._total_frames)
        self._replay_worker.set_loop_enabled(self._replay_control.is_loop_enabled())
        self._replay_worker.start()
        self._replay_worker.stop_playback()
        self._replaying = True

        # Disable acquisition controls during replay
        self._device_control.set_replaying(True)
        self._act_start_save.setEnabled(False)
        self._act_stop_playback.setEnabled(True)

        logger.info("Replay mode started: %s", file_path)

    def _on_replay_frame(self, frame: np.ndarray, metadata: dict) -> None:
        """Handle frame from replay worker."""
        if frame.shape != self._active_frame_shape:
            self._current_frame = None
            self._apply_frame_shape(frame.shape)
        self._current_frame = frame

        # Prepare display frame
        display_frame = frame
        if frame.dtype == np.float32:
            max_dn = self._get_max_dn_from_format(
                metadata.get("pixel_format", "Mono12")
            )
            display_frame = np.clip(frame, 0, max_dn).astype(np.uint16)

        if self._act_mode_line.isChecked():
            # Apply same line scan logic directly for replay frames (happens on main thread)
            _, indices = self._line_scan_display.get_current_config()
            max_y = frame.shape[0] - 1
            valid_indices = [min(max(0, y), max_y) for y in indices]
            try:
                line_data = frame[valid_indices, :].copy()
                self._line_scan_display.append_lines([line_data])
            except IndexError:
                pass
        else:
            # Update image display
            self._image_display.update_image(display_frame, metadata)

        # Update aux data
        self._aux_panel.update_metadata(metadata)

        # Throttle heavy UI updates
        now = time.perf_counter()
        if now - self._last_heavy_update < _HEAVY_UPDATE_INTERVAL:
            return
        self._last_heavy_update = now

        x, y = self._selected_x, self._selected_y

        if self._bottom_container.isVisible():
            mtf_result = self._mtf.update(frame, x, y)
            self._optical_cal_panel.update_mtf(mtf_result)
            self._optical_cal_panel.update_dn_neighborhood(display_frame, x, y)
            self._update_spectral_plots(display_frame, x, y)

    def _on_replay_progress(self, current: int, total: int) -> None:
        """Update replay progress bar."""
        self._replay_control.set_position(current, total)

    def _on_replay_finished(self) -> None:
        """Handle playback finished."""
        self._replay_control.set_playing(False)
        logger.info("Replay finished")

    def _on_replay_error(self, error_msg: str) -> None:
        """Handle replay error."""
        QMessageBox.critical(self, "回放错误", error_msg)
        self._on_replay_stop()

    def _on_replay_play(self) -> None:
        """Resume playback."""
        if self._replay_worker:
            self._replay_worker.play()
            self._replay_control.set_playing(True)

    def _on_replay_pause(self) -> None:
        """Pause playback."""
        if self._replay_worker:
            self._replay_worker.pause()
            self._replay_control.set_playing(False)

    def _on_replay_stop(self) -> None:
        """Stop playback and seek back to the start of the file."""
        if self._replay_worker:
            self._replay_worker.stop_playback()
            self._replay_control.set_playing(False)
            logger.info("Replay playback stopped and reset to start")

    def _on_replay_position_changed(self, position: int) -> None:
        """Handle user dragging progress slider."""
        if self._replay_worker:
            self._replay_worker.set_position(position)

    def _on_replay_speed_changed(self, speed: float) -> None:
        """Handle speed rate change."""
        if self._replay_worker:
            self._replay_worker.set_speed_rate(speed)

    def _on_replay_loop_changed(self, enabled: bool) -> None:
        """Handle replay loop toggle."""
        if self._replay_worker:
            self._replay_worker.set_loop_enabled(enabled)

    def _on_replay_close(self) -> None:
        """Close replay mode and restore acquisition controls."""
        self._teardown_replay()

    def _teardown_replay(self) -> None:
        """Close the current replay session and restore acquisition controls."""
        if self._replay_worker:
            self._replay_worker.shutdown()
            self._replay_worker.wait()
            self._replay_worker = None

        self._replay_control.reset()
        self._replay_control.setVisible(False)
        self._replaying = False
        self._device_control.set_replaying(False)
        self._apply_frame_shape(self._device.get_frame_shape())
        self._device_control.set_running(False)
        self._act_start_save.setEnabled(True)
        self._act_stop_playback.setEnabled(False)

    def _on_settings(self) -> None:
        """Placeholder for settings dialog."""
        QMessageBox.information(self, "设置", "设置功能尚未实现")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "高光谱相机控制软件\n\n"
            "相机型号: MER3-138-136G3M-P-SWIR\n"
            "传感器: Sony IMX990\n"
            "分辨率: 1280×1024\n"
            "\n"
            "Copyright © 2026 XL@HO\n"
            "All rights reserved",
        )

    def closeEvent(self, event) -> None:
        """Clean up on window close."""
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            event.ignore()
            return

        if self._running:
            self._on_stop()
        if self._replaying:
            self._teardown_replay()
        if self._storage.is_recording:
            self._acquisition.storage = None
            self._storage.stop()
        self._temperature_timer.stop()
        self._device.close()
        logger.info("Application closing")
        event.accept()
