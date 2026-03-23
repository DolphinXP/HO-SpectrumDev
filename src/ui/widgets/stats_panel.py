"""Stats panel (数据统计) — FPS, throughput, buffer statistics."""

from PySide6.QtWidgets import (QGroupBox, QLabel, QVBoxLayout, QHBoxLayout,
                                QWidget, QGridLayout)
from PySide6.QtCore import Qt


class StatsPanel(QGroupBox):
    """Right-side panel showing acquisition statistics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("数据统计", parent)
        layout = QGridLayout(self)
        layout.setSpacing(4)

        labels = [
            ("帧率 (FPS):", "_fps"),
            ("吞吐量 (MB/s):", "_mbps"),
            ("帧计数:", "_frame_count"),
            ("丢帧数:", "_drop_count"),
            ("缓冲区:", "_buffer"),
        ]

        for row, (text, attr) in enumerate(labels):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val = QLabel("--")
            val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            val.setStyleSheet("font-weight: bold;")
            layout.addWidget(lbl, row, 0)
            layout.addWidget(val, row, 1)
            setattr(self, attr, val)

    def update_stats(self, stats: dict) -> None:
        """Update displayed values from stats dict."""
        self._fps.setText(f"{stats.get('fps', 0):.1f}")
        self._mbps.setText(f"{stats.get('mbps', 0):.2f}")
        self._frame_count.setText(str(stats.get('frame_count', 0)))
        self._drop_count.setText(str(stats.get('dropped_count', 0)))
        self._buffer.setText(stats.get('buffer', '--'))
