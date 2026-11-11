"""FactoryScheduler 操作員視窗：掃 barcode（自動轉換）→ 累積清單 → 複選整包完成。

掃描槍 = 鍵盤輸入 + Enter。支援一次掃多張，累積到清單後一鍵全部標記已完成。
"""
from __future__ import annotations

import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..factory import barcode
from ..factory.fservice import FactoryService
from ..factory.fstore import STATUS_DONE, STATUS_PROCESSING

COLS = ["勾選", "PACKAGE_ID", "客戶", "機台", "卡量", "狀態"]
COLOR_DONE = QColor("#C6EFCE")
COLOR_PROCESSING = QColor("#FFE699")
STATUS_COLOR = {STATUS_PROCESSING: COLOR_PROCESSING, STATUS_DONE: COLOR_DONE}


class FactoryOperatorWindow(QMainWindow):
    def __init__(self, state_db: str | None = None):
        super().__init__()
        self.svc = FactoryService(state_db=state_db)
        self._rows: dict[str, int] = {}   # package_id -> table row
        self.setWindowTitle("FactoryScheduler — 操作員｜掃描回報")
        self.resize(760, 640)
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(QLabel("操作員編號："))
        self.ed_operator = QLineEdit()
        self.ed_operator.setPlaceholderText("選填，例如 EMP_001")
        self.ed_operator.setMaximumWidth(200)
        top.addWidget(self.ed_operator)
        top.addStretch(1)
        root.addLayout(top)

        scan_box = QGroupBox("掃描工單條碼（例 W_271B4A-1 → 271B4A；可連續掃多張）")
        sl = QVBoxLayout(scan_box)
        self.ed_scan = QLineEdit()
        self.ed_scan.setPlaceholderText("游標停在此處並掃描…")
        f = QFont(); f.setPointSize(16); self.ed_scan.setFont(f)
        self.ed_scan.setMinimumHeight(44)
        self.ed_scan.returnPressed.connect(self.on_scan)
        sl.addWidget(self.ed_scan)
        self.lb_last = QLabel("尚未掃描")
        self.lb_last.setFont(f)
        sl.addWidget(self.lb_last)
        root.addWidget(scan_box)

        root.addWidget(QLabel("待回報清單（勾選後一鍵標記已完成）"))
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)

        top_btns = QHBoxLayout()
        self.btn_all = QPushButton("全部勾選")
        self.btn_none = QPushButton("全部取消")
        self.btn_clear = QPushButton("清空清單")
        self.btn_all.clicked.connect(lambda: self._check_all(True))
        self.btn_none.clicked.connect(lambda: self._check_all(False))
        self.btn_clear.clicked.connect(self._clear)
        for b in (self.btn_all, self.btn_none, self.btn_clear):
            top_btns.addWidget(b)
        top_btns.addStretch(1)
        root.addLayout(top_btns)

        btns = QHBoxLayout()
        self.btn_proc = QPushButton("標記勾選為處理中")
        self.btn_done = QPushButton("標記勾選為已完成")
        self.btn_proc.clicked.connect(lambda: self.on_mark(STATUS_PROCESSING))
        self.btn_done.clicked.connect(lambda: self.on_mark(STATUS_DONE))
        df = QFont(); df.setPointSize(14); df.setBold(True)
        for b, color, fg in ((self.btn_proc, "#FFC000", "#000000"),
                             (self.btn_done, "#548235", "#FFFFFF")):
            b.setMinimumHeight(60); b.setFont(df)
            b.setStyleSheet(f"background-color:{color}; color:{fg}; border-radius:8px;")
            btns.addWidget(b, 1)
        root.addLayout(btns)

        self.setCentralWidget(central)
        self.statusBar().showMessage("就緒，請掃描工單條碼。")
        self.ed_scan.setFocus()

    # ------------------------------------------------------------------ #
    def on_scan(self) -> None:
        raw = self.ed_scan.text().strip()
        self.ed_scan.clear()
        if not raw:
            return
        core = barcode.parse_scan(raw)
        snap = self.svc.load_snapshot()       # 每次掃描取最新快照
        hits = self.svc.find_by_scan(raw, snapshot=snap)
        if not hits:
            self.lb_last.setText(f"✗ {raw} → {core}：查無工單")
            self.lb_last.setStyleSheet("color:#C00000;")
            self.statusBar().showMessage(f"找不到：{raw}（轉換後 {core}）")
            return
        added = 0
        for r in hits:
            if self._add_row(r):
                added += 1
        self.lb_last.setText(f"✓ {raw} → {core}（{len(hits)} 包，新增 {added}）")
        self.lb_last.setStyleSheet("color:#2e7d32;")
        self.statusBar().showMessage(f"已帶出 {len(hits)} 包，清單共 {len(self._rows)} 筆。")
        self.ed_scan.setFocus()

    def _add_row(self, r: dict) -> bool:
        pid = r["package_id"]
        if pid in self._rows:
            return False
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._rows[pid] = row

        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked)
        self.table.setItem(row, 0, chk)
        for ci, val in enumerate([pid, r.get("customer", ""), r.get("machine", ""),
                                  str(r.get("qty", "")), r.get("status", "")], 1):
            self.table.setItem(row, ci, QTableWidgetItem(str(val)))
        if r.get("status") == STATUS_DONE:
            self._paint(row, COLOR_DONE)
        return True

    def _paint(self, row: int, color: QColor) -> None:
        for c in range(len(COLS)):
            it = self.table.item(row, c)
            if it:
                it.setBackground(color)

    def _check_all(self, checked: bool) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _clear(self) -> None:
        self.table.setRowCount(0)
        self._rows.clear()
        self.statusBar().showMessage("已清空清單。")

    def on_mark(self, status: str) -> None:
        ids = []
        for pid, row in self._rows.items():
            if self.table.item(row, 0).checkState() == Qt.Checked:
                ids.append(pid)
        if not ids:
            self.statusBar().showMessage("沒有勾選任何工單。")
            return
        try:
            op = self.ed_operator.text().strip() or None
            self.svc.set_status_packages(ids, status, operator=op)
            for pid in ids:
                row = self._rows[pid]
                self.table.item(row, len(COLS) - 1).setText(status)
                self._paint(row, STATUS_COLOR.get(status, QColor("#FFFFFF")))
            self.statusBar().showMessage(f"已將 {len(ids)} 包標記為「{status}」。")
            self.ed_scan.setFocus()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "更新失敗", f"{e}\n\n{traceback.format_exc()}")
