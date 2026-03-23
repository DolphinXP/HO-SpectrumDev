"""Main window — full layout and signal wiring."""

import logging
import os

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QSplitter, QWidget, QVBoxLayout, QLabel,
    QHBoxLayout, QStatusBar, QMessageBox, QFileDialog,
)

from src.device.device_interface import DeviceInterface
from src.data.acquisition import AcquisitionWorker
from src.data.storage import StorageManager
from src.analysis.mtf import MTFCalculator
from src.analysis.spectral import SpectralAnalyzer
from src.ui.widgets.image_display import ImageDisplayWidget
from src.ui.widgets.stats_panel import StatsPanel
from src.ui.widgets.aux_data_panel import AuxDataPanel
from src.ui.widgets.control_panel import ControlPanel
from src.ui.widgets.spectrum_graph import SpectrumGraphWidget

logger = logging.getLogger("gpy4.ui")


class MainWindow(QMainWindow):
    """Main application window with complete layout per CLAUDE.md spec."""

    def __init__(self, device: DeviceInterface, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("地检软件 — 高光谱相机地面测试")
        self.resize(1600, 900)

        self._device = device

        # --- Core modules ---
        self._mtf = MTFCalculator()
        self._spectral = SpectralAnalyzer()
        self._storage = StorageManager()
        self._acquisition = AcquisitionWorker(device)
        self._nuc = self._acquisition.nuc  # shared NUC instance

        # Current state
        self._selected_x: int = 640
        self._selected_y: int = 512
        self._current_frame: np.ndarray | None = None
        self._running: bool = False

        # Load stylesheet
        self._load_stylesheet()

        # Build UI
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        # Wire signals
        self._wire_signals()

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
        self.addToolBar(tb)

        self._act_start = QAction("开始", self)
        self._act_start.triggered.connect(self._on_start)
        tb.addAction(self._act_start)

        self._act_stop = QAction("停止", self)
        self._act_stop.setEnabled(False)
        self._act_stop.triggered.connect(self._on_stop)
        tb.addAction(self._act_stop)

        tb.addSeparator()

        self._act_browse = QAction("查看记录", self)
        self._act_browse.triggered.connect(self._on_browse_records)
        tb.addAction(self._act_browse)

        self._act_playback = QAction("开始回放", self)
        self._act_playback.triggered.connect(self._on_playback)
        tb.addAction(self._act_playback)

        tb.addSeparator()

        self._act_start_save = QAction("开始存储", self)
        self._act_start_save.triggered.connect(self._on_start_save)
        tb.addAction(self._act_start_save)

        self._act_stop_save = QAction("停止存储", self)
        self._act_stop_save.setEnabled(False)
        self._act_stop_save.triggered.connect(self._on_stop_save)
        tb.addAction(self._act_stop_save)

        tb.addSeparator()

        self._act_settings = QAction("设置", self)
        self._act_settings.triggered.connect(self._on_settings)
        tb.addAction(self._act_settings)

        self._act_about = QAction("关于", self)
        self._act_about.triggered.connect(self._on_about)
        tb.addAction(self._act_about)

        self._act_exit = QAction("Exit", self)
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

        # Left: Image display (handles image/DN/OC tab switching internally)
        self._image_display = ImageDisplayWidget()
        self._h_splitter_top.addWidget(self._image_display)

        # Right: stats + aux panels stacked vertically
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._stats_panel = StatsPanel()
        self._aux_panel = AuxDataPanel()
        right_layout.addWidget(self._stats_panel)
        right_layout.addWidget(self._aux_panel)
        right_layout.addStretch()
        self._h_splitter_top.addWidget(right_panel)

        self._h_splitter_top.setSizes([1200, 300])

        # ---- BOTTOM HALF: control panel + spectrum graphs ----
        self._h_splitter_bottom = QSplitter(Qt.Orientation.Horizontal)
        self._v_splitter.addWidget(self._h_splitter_bottom)

        # Bottom-left: 光校 control panel
        self._control_panel = ControlPanel()
        self._h_splitter_bottom.addWidget(self._control_panel)

        # Bottom-right: 3 spectrum graphs
        graphs_widget = QWidget()
        graphs_layout = QHBoxLayout(graphs_widget)
        graphs_layout.setContentsMargins(0, 0, 0, 0)

        self._graph_near_spatial = SpectrumGraphWidget(
            title="临近空间维(行)", x_label="空间像素", y_label="DN",
            orientation="horizontal", show_x=True, show_y=True)
        self._graph_near_spectral = SpectrumGraphWidget(
            title="临近光谱维(列)", x_label="光谱通道", y_label="DN",
            orientation="vertical", show_x=True, show_y=True)
        self._graph_full_spatial = SpectrumGraphWidget(
            title="全域空间维(行)", x_label="空间像素", y_label="DN",
            orientation="horizontal", show_x=False, show_y=True)

        graphs_layout.addWidget(self._graph_near_spatial)
        graphs_layout.addWidget(self._graph_near_spectral)
        graphs_layout.addWidget(self._graph_full_spatial)
        self._h_splitter_bottom.addWidget(graphs_widget)

        self._h_splitter_bottom.setSizes([350, 1150])
        self._v_splitter.setSizes([550, 350])

    # --------------------------------------------------------------- statusbar
    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_device = QLabel("设备: --")
        self._status_nuc = QLabel("NUC: 未加载")
        self._status_storage = QLabel("存储: 停止")
        sb.addWidget(self._status_device)
        sb.addPermanentWidget(self._status_nuc)
        sb.addPermanentWidget(self._status_storage)

        device_name = self._device.__class__.__name__
        self._status_device.setText(f"设备: {device_name}")

    # --------------------------------------------------------------- signals
    def _wire_signals(self) -> None:
        # Acquisition → UI
        self._acquisition.frame_ready.connect(self._on_frame_ready)
        self._acquisition.stats_updated.connect(self._on_stats_updated)

        # Image display
        self._image_display.pixel_clicked.connect(self._on_pixel_selected)

        # Spectrum graph coordinate spinboxes
        self._graph_near_spatial.coordinate_changed.connect(self._on_pixel_selected)
        self._graph_near_spectral.coordinate_changed.connect(self._on_pixel_selected)
        self._graph_full_spatial.coordinate_changed.connect(
            lambda x, y: self._on_pixel_selected(self._selected_x, y))

        # Control panel
        self._control_panel.pixel_changed.connect(self._on_pixel_selected)
        self._control_panel.locate_max_dn.connect(self._on_locate_max_dn)
        self._control_panel.avg_count_changed.connect(self._mtf.set_avg_count)
        self._control_panel.black_level_changed.connect(self._mtf.set_black_level)

    # --------------------------------------------------------------- slots
    def _on_frame_ready(self, frame: np.ndarray, metadata: dict) -> None:
        """Handle processed frame from acquisition worker."""
        self._current_frame = frame

        # Update image display
        display_frame = frame
        if frame.dtype == np.float32:
            # NUC output is float32, convert for display
            display_frame = np.clip(frame, 0, 4095).astype(np.uint16)
        self._image_display.update_image(display_frame)

        # Update aux data
        self._aux_panel.update_metadata(metadata)

        # Update MTF
        x, y = self._selected_x, self._selected_y
        mtf_result = self._mtf.update(frame, x, y)
        self._control_panel.update_mtf(mtf_result)

        # Update DN neighborhood
        self._control_panel.update_dn_neighborhood(display_frame, x, y)

        # Update spectral profiles
        self._update_spectral_plots(display_frame, x, y)

        # Write to storage if recording
        if self._storage.is_recording:
            self._storage.write_frame(frame, metadata)

    def _on_stats_updated(self, stats: dict) -> None:
        self._stats_panel.update_stats(stats)

    def _on_pixel_selected(self, x: int, y: int) -> None:
        """Handle pixel selection from any source."""
        self._selected_x = x
        self._selected_y = y
        self._control_panel.set_pixel(x, y)
        self._graph_near_spatial.set_position(x, y)
        self._graph_near_spectral.set_position(x, y)
        self._graph_full_spatial.set_position(x, y)
        self._mtf.reset()  # Reset MTF accumulator on pixel change

        if self._current_frame is not None:
            frame = self._current_frame
            if frame.dtype == np.float32:
                frame = np.clip(frame, 0, 4095).astype(np.uint16)
            self._update_spectral_plots(frame, x, y)
            self._control_panel.update_dn_neighborhood(frame, x, y)

    def _on_locate_max_dn(self) -> None:
        """Find and navigate to the pixel with maximum DN."""
        if self._current_frame is None:
            return
        frame = self._current_frame
        if frame.dtype == np.float32:
            frame = np.clip(frame, 0, 4095).astype(np.uint16)
        idx = np.unravel_index(np.argmax(frame), frame.shape)
        y, x = int(idx[0]), int(idx[1])
        self._on_pixel_selected(x, y)
        logger.info("Max DN located at X=%d, Y=%d, DN=%d", x, y, int(frame[y, x]))

    def _update_spectral_plots(self, frame: np.ndarray, x: int, y: int) -> None:
        """Update the three spectrum graph widgets."""
        # Near spatial: ±10 pixels along the row
        xs, vs = self._spectral.near_spatial(frame, x, y)
        self._graph_near_spatial.update_plot(xs, vs)

        # Near spectral: ±10 bands along the column
        xs2, vs2 = self._spectral.near_spectral(frame, x, y)
        self._graph_near_spectral.update_plot(xs2, vs2)

        # Full spatial: entire row
        xs3, vs3 = self._spectral.full_spatial(frame, y)
        self._graph_full_spatial.update_plot(xs3, vs3)

    # --------------------------------------------------------------- toolbar actions
    def _on_start(self) -> None:
        """Start acquisition."""
        self._device.start()
        self._acquisition.start()
        self._running = True
        self._act_start.setEnabled(False)
        self._act_stop.setEnabled(True)
        logger.info("Acquisition started")

    def _on_stop(self) -> None:
        """Stop acquisition."""
        self._acquisition.stop()
        self._device.stop()
        self._running = False
        self._act_start.setEnabled(True)
        self._act_stop.setEnabled(False)
        logger.info("Acquisition stopped")

    def _on_start_save(self) -> None:
        """Start recording to disk."""
        directory = QFileDialog.getExistingDirectory(self, "选择存储目录")
        if not directory:
            return
        pixel_format = self._device.get_pixel_format()
        self._storage.start_envi(directory, "session", pixel_format)
        self._act_start_save.setEnabled(False)
        self._act_stop_save.setEnabled(True)
        self._status_storage.setText("存储: 录制中")
        logger.info("Storage started: %s", directory)

    def _on_stop_save(self) -> None:
        """Stop recording."""
        self._storage.stop()
        self._act_start_save.setEnabled(True)
        self._act_stop_save.setEnabled(False)
        self._status_storage.setText("存储: 停止")
        logger.info("Storage stopped")

    def _on_browse_records(self) -> None:
        """Open file browser for saved data."""
        directory = QFileDialog.getExistingDirectory(self, "查看记录目录")
        if directory:
            import subprocess
            subprocess.Popen(["explorer", directory])

    def _on_playback(self) -> None:
        """Placeholder for playback functionality."""
        QMessageBox.information(self, "回放", "回放功能尚未实现")

    def _on_settings(self) -> None:
        """Placeholder for settings dialog."""
        QMessageBox.information(self, "设置", "设置功能尚未实现")

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "关于",
            "地检软件 — 高光谱相机地面测试应用\n\n"
            "相机型号: MER3-138-136G3M-P-SWIR\n"
            "传感器: Sony IMX990\n"
            "分辨率: 1280×1024\n"
        )

    def closeEvent(self, event) -> None:
        """Clean up on window close."""
        if self._running:
            self._on_stop()
        if self._storage.is_recording:
            self._storage.stop()
        self._device.close()
        logger.info("Application closing")
        event.accept()
