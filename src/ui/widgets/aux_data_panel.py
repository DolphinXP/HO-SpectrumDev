"""Auxiliary data panel (辅助数据) — frame metadata display."""

from PySide6.QtWidgets import QGroupBox, QLabel, QGridLayout, QWidget
from PySide6.QtCore import Qt


class AuxDataPanel(QGroupBox):
    """Right-side panel showing frame header / metadata fields."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("辅助数据", parent)
        layout = QGridLayout(self)
        layout.setSpacing(4)

        labels = [
            ("帧 ID:", "_frame_id"),
            ("时间戳:", "_timestamp"),
            ("曝光 (µs):", "_exposure"),
            ("增益 (dB):", "_gain"),
            ("像素格式:", "_pixel_format"),
            ("分辨率:", "_resolution"),
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

    def update_metadata(self, meta: dict) -> None:
        """Update displayed values from frame metadata dict."""
        self._frame_id.setText(str(meta.get("frame_id", "--")))
        ts = meta.get("timestamp")
        if ts is not None:
            import datetime
            dt = datetime.datetime.fromtimestamp(ts)
            self._timestamp.setText(dt.strftime("%H:%M:%S.%f")[:-3])
        self._exposure.setText(f"{meta.get('exposure_us', '--')}")
        self._gain.setText(f"{meta.get('gain_db', '--')}")
        self._pixel_format.setText(str(meta.get("pixel_format", "--")))
        w = meta.get("width", "?")
        h = meta.get("height", "?")
        self._resolution.setText(f"{w} × {h}")
