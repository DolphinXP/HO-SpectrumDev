"""NUC panel (非均匀性校正) — A/B file selection and apply toggle."""

import logging
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QCheckBox, QWidget, QFileDialog
)

logger = logging.getLogger("gpy4.ui")


class NucPanel(QGroupBox):
    """Right-side panel for Non-Uniformity Correction (NUC) control.

    Signals
    -------
    nuc_changed : Signal(str, str, bool)
        Emitted when files are loaded or toggle changes.
        (a_path: str, b_path: str, enabled: bool)
    """

    nuc_changed = Signal(str, str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("非均匀性校正 (NUC)", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setSpacing(6)

        # A Coefficient
        layout.addWidget(QLabel("A 系数 (Gain):"), 0, 0)
        self._edit_a = QLineEdit()
        self._edit_a.setReadOnly(True)
        self._edit_a.setPlaceholderText("未选择 A 文件...")
        layout.addWidget(self._edit_a, 0, 1)
        
        btn_browse_a = QPushButton("浏览...")
        btn_browse_a.setFixedWidth(60)
        btn_browse_a.clicked.connect(self._on_browse_a)
        layout.addWidget(btn_browse_a, 0, 2)

        # B Coefficient
        layout.addWidget(QLabel("B 系数 (Offset):"), 1, 0)
        self._edit_b = QLineEdit()
        self._edit_b.setReadOnly(True)
        self._edit_b.setPlaceholderText("未选择 B 文件...")
        layout.addWidget(self._edit_b, 1, 1)

        btn_browse_b = QPushButton("浏览...")
        btn_browse_b.setFixedWidth(60)
        btn_browse_b.clicked.connect(self._on_browse_b)
        layout.addWidget(btn_browse_b, 1, 2)

        # Enable checkbox
        lower_layout = QHBoxLayout()
        self._chk_enabled = QCheckBox("启用校正")
        self._chk_enabled.toggled.connect(self._on_toggled)
        lower_layout.addWidget(self._chk_enabled)
        
        self._btn_load = QPushButton("加载")
        self._btn_load.setFixedWidth(80)
        self._btn_load.setProperty("class", "btn-green")
        self._btn_load.clicked.connect(self._on_load_clicked)
        lower_layout.addStretch()
        lower_layout.addWidget(self._btn_load)

        layout.addLayout(lower_layout, 2, 0, 1, 3)

    def _on_browse_a(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 A 系数文件", "", "Coefficients (*.npy *.csv *.bin *.raw);;All Files (*)"
        )
        if path:
            self._edit_a.setText(path)

    def _on_browse_b(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 B 系数文件", "", "Coefficients (*.npy *.csv *.bin *.raw);;All Files (*)"
        )
        if path:
            self._edit_b.setText(path)

    def _on_load_clicked(self) -> None:
        a = self._edit_a.text()
        b = self._edit_b.text()
        if not a or not b:
            return
        self.nuc_changed.emit(a, b, self._chk_enabled.isChecked())

    def _on_toggled(self, checked: bool) -> None:
        a = self._edit_a.text()
        b = self._edit_b.text()
        self.nuc_changed.emit(a, b, checked)

    def set_nuc_status(self, loaded: bool) -> None:
        """Update UI based on whether NUC is successfully applied."""
        if loaded:
            self._chk_enabled.setEnabled(True)
            self._btn_load.setText("重新加载")
        else:
            # self._chk_enabled.setChecked(False)
            self._btn_load.setText("加载")

    def set_config(self, a_path: str, b_path: str, enabled: bool) -> None:
        """Set UI state from config."""
        self._edit_a.setText(a_path)
        self._edit_b.setText(b_path)
        self._chk_enabled.setChecked(enabled)
