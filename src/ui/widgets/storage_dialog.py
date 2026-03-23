"""Storage configuration dialog.

Popup dialog shown when the user clicks 开始存储. Collects experiment
name, operator, and format selection before recording begins.
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

logger = logging.getLogger("gpy4.ui")

# Defaults
_DEFAULT_EXP_NAME = "exp"
_DEFAULT_OPERATOR = "user"


class StorageDialog(QDialog):
    """Dialog for configuring a new storage session.

    After ``exec()`` returns ``QDialog.Accepted``, the caller reads
    :pyattr:`result_info` to obtain session parameters.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("存储设置")
        self.setMinimumWidth(380)

        self.result_info: dict | None = None

        layout = QVBoxLayout(self)

        # --- Form fields ---
        form = QFormLayout()

        self._edit_exp_name = QLineEdit(_DEFAULT_EXP_NAME)
        self._edit_exp_name.setPlaceholderText(_DEFAULT_EXP_NAME)
        form.addRow("实验名称:", self._edit_exp_name)

        self._edit_operator = QLineEdit(_DEFAULT_OPERATOR)
        self._edit_operator.setPlaceholderText(_DEFAULT_OPERATOR)
        form.addRow("操作人员:", self._edit_operator)

        self._label_date = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        form.addRow("日期:", self._label_date)

        layout.addLayout(form)

        # --- Directory ---
        dir_layout = QHBoxLayout()
        self._edit_directory = QLineEdit()
        self._edit_directory.setPlaceholderText("选择存储目录...")
        self._edit_directory.setReadOnly(True)
        dir_layout.addWidget(self._edit_directory, 1)

        from PySide6.QtWidgets import QPushButton
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_directory)
        dir_layout.addWidget(btn_browse)

        form.addRow("存储目录:", dir_layout)

        # --- Checkboxes ---
        self._chk_raw = QCheckBox("存储原始数据 (.dat + .json)")
        self._chk_envi = QCheckBox("存储ENVI格式 (BIL)")
        layout.addWidget(self._chk_raw)
        layout.addWidget(self._chk_envi)

        # --- Buttons ---
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def _browse_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择存储目录")
        if directory:
            self._edit_directory.setText(directory)

    def _on_accept(self) -> None:
        if not self._chk_raw.isChecked() and not self._chk_envi.isChecked():
            QMessageBox.warning(
                self, "存储设置", "请至少选择一种存储格式！"
            )
            return

        directory = self._edit_directory.text().strip()
        if not directory:
            QMessageBox.warning(
                self, "存储设置", "请选择存储目录！"
            )
            return

        exp_name = self._edit_exp_name.text().strip() or _DEFAULT_EXP_NAME
        operator = self._edit_operator.text().strip() or _DEFAULT_OPERATOR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"{exp_name}-{operator}-{timestamp}"

        self.result_info = {
            "directory": directory,
            "session_name": session_name,
            "save_raw": self._chk_raw.isChecked(),
            "save_envi": self._chk_envi.isChecked(),
        }
        self.accept()
