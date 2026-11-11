"""啟動角色選擇對話框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .. import config


class RoleDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.role: str | None = None
        self.setWindowTitle("選擇角色")
        self.setMinimumWidth(360)

        lay = QVBoxLayout(self)
        title = QLabel("工單機台指派系統")
        tf = QFont(); tf.setPointSize(16); tf.setBold(True)
        title.setFont(tf); title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        lay.addWidget(QLabel("請選擇操作角色："))

        btn_admin = QPushButton("管理員 (Leader)：分派工單")
        btn_oper = QPushButton("操作員 (Operator)：回報狀態")
        for b in (btn_admin, btn_oper):
            b.setMinimumHeight(56)
            bf = QFont(); bf.setPointSize(13); b.setFont(bf)
        btn_admin.clicked.connect(lambda: self._choose(config.ROLE_ADMIN))
        btn_oper.clicked.connect(lambda: self._choose(config.ROLE_OPERATOR))
        lay.addWidget(btn_admin)
        lay.addWidget(btn_oper)

    def _choose(self, role: str) -> None:
        self.role = role
        self.accept()
