"""Replay control widget with progress bar and playback controls."""

import logging
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QSlider, QPushButton, QComboBox, QLabel, QCheckBox
)

logger = logging.getLogger("specdev.ui")


class ReplayControlWidget(QWidget):
    """Playback control bar with progress slider and buttons.

    Signals
    -------
    play_clicked : Signal()
        Emitted when play button is clicked.
    pause_clicked : Signal()
        Emitted when pause button is clicked.
    stop_clicked : Signal()
        Emitted when stop button is clicked.
    position_changed : Signal(int)
        Emitted when user drags the progress slider.
    speed_changed : Signal(float)
        Emitted when playback speed is changed.
    """

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    close_clicked = Signal()
    position_changed = Signal(int)
    speed_changed = Signal(float)
    loop_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._icon_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "assets", "images"
        )
        self._build_ui()
        self._is_playing = False

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        # Play/Pause button
        self._btn_play = QPushButton("播放")
        self._btn_play.setFixedWidth(80)
        self._btn_play.setProperty("class", "btn-green")
        self._btn_play.setIcon(QIcon(os.path.join(self._icon_dir, "play.svg")))
        self._btn_play.clicked.connect(self._on_play_pause)
        layout.addWidget(self._btn_play)

        # Stop button
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setFixedWidth(80)
        self._btn_stop.setProperty("class", "btn-red")
        self._btn_stop.setIcon(QIcon(os.path.join(self._icon_dir, "stop.svg")))
        self._btn_stop.clicked.connect(self._on_stop)
        layout.addWidget(self._btn_stop)

        # Progress slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(100)
        self._slider.setValue(0)
        self._slider.sliderReleased.connect(self._on_slider_released)
        layout.addWidget(self._slider, 1)

        # Position label
        self._lbl_position = QLabel("0 / 0")
        self._lbl_position.setMinimumWidth(80)
        layout.addWidget(self._lbl_position)

        # Speed rate combo
        layout.addWidget(QLabel("速度:"))
        self._combo_speed = QComboBox()
        self._combo_speed.addItems(["0.25x", "0.5x", "1x", "2x", "4x"])
        self._combo_speed.setCurrentText("1x")
        self._combo_speed.currentTextChanged.connect(self._on_speed_changed)
        layout.addWidget(self._combo_speed)

        self._chk_loop = QCheckBox("循环")
        self._chk_loop.toggled.connect(self.loop_changed.emit)
        layout.addWidget(self._chk_loop)

        self._btn_close = QPushButton("X")
        self._btn_close.setFixedWidth(32)
        self._btn_close.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self._btn_close)

    def _on_play_pause(self) -> None:
        """Toggle between play and pause."""
        if self._is_playing:
            self.pause_clicked.emit()
            self._btn_play.setText("播放")
            self._is_playing = False
        else:
            self.play_clicked.emit()
            self._btn_play.setText("暂停")
            self._is_playing = True

    def _on_stop(self) -> None:
        """Stop playback."""
        self.stop_clicked.emit()
        self._btn_play.setText("播放")
        self._is_playing = False
        self._slider.setValue(0)

    def _on_slider_released(self) -> None:
        """Emit position change when user releases slider."""
        self.position_changed.emit(self._slider.value())

    def _on_speed_changed(self, text: str) -> None:
        """Parse speed text and emit signal."""
        speed_map = {"0.25x": 0.25, "0.5x": 0.5,
                     "1x": 1.0, "2x": 2.0, "4x": 4.0}
        speed = speed_map.get(text, 1.0)
        self.speed_changed.emit(speed)

    def set_range(self, total: int) -> None:
        """Set the total number of frames."""
        self._slider.setMaximum(max(0, total - 1))
        self._update_position_label(0, total)

    def set_position(self, current: int, total: int) -> None:
        """Update progress slider and label."""
        self._slider.blockSignals(True)
        self._slider.setValue(current)
        self._slider.blockSignals(False)
        self._update_position_label(current, total)

    def _update_position_label(self, current: int, total: int) -> None:
        """Update position label text."""
        self._lbl_position.setText(f"{current} / {total}")

    def reset(self) -> None:
        """Reset to initial state."""
        self._is_playing = False
        self._btn_play.setText("播放")
        self._slider.setValue(0)
        self._lbl_position.setText("0 / 0")

    def set_playing(self, playing: bool) -> None:
        """Update play/pause button state from external events."""
        self._is_playing = playing
        self._btn_play.setText("暂停" if playing else "播放")
        icon_name = "pause.svg" if playing else "play.svg"
        self._btn_play.setIcon(QIcon(os.path.join(self._icon_dir, icon_name)))

    def is_loop_enabled(self) -> bool:
        """Return whether loop playback is enabled."""
        return self._chk_loop.isChecked()
