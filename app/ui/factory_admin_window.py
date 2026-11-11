"""FactoryScheduler 管理員 (Leader) 視窗：每機台時序視圖 + 載入/重排/調整/匯出。"""
from __future__ import annotations

import os
import traceback
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStatusBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import settings
from ..factory.fservice import FactoryService
from ..factory.fstore import STATUS_DONE, STATUS_PENDING, STATUS_PROCESSING

COLOR_PULL = QColor("#F8CBAD")
COLOR_PROCESSING = QColor("#FFE699")
COLOR_DONE = QColor("#C6EFCE")
COLOR_LATE = QColor("#FFC7CE")

COLS = ["順序/機台", "PACKAGE_ID", "客戶", "卡量", "EMER_1", "EMER_2", "Std",
        "開始", "結束", "狀態", "優先", "鎖定", "逾期(分)"]


class FactoryAdminWindow(QMainWindow):
    def __init__(self, state_db: str | None = None):
        super().__init__()
        self.svc = FactoryService(state_db=state_db)
        self._row_meta: dict = {}   # package_id -> (task, late_bool)
        self.setWindowTitle("FactoryScheduler — 管理員 (Leader)｜每機台時序")
        self.resize(1400, 780)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sync_status)
        self.timer.start(5000)

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        bar = QHBoxLayout()
        self.btn_master = QPushButton("1. 載入主檔")
        self.btn_orders = QPushButton("2. 載入訂單")
        self.btn_pulls = QPushButton("＋ 載入抽件")
        self.btn_sched = QPushButton("重新排程 ▶")
        self.btn_export = QPushButton("匯出介面格式")
        self.btn_master.clicked.connect(self.on_load_master)
        self.btn_orders.clicked.connect(self.on_load_orders)
        self.btn_pulls.clicked.connect(self.on_load_pulls)
        self.btn_sched.clicked.connect(self.on_reschedule)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_sched.setStyleSheet("font-weight:bold;")
        for b in (self.btn_orders, self.btn_pulls, self.btn_sched, self.btn_export):
            b.setEnabled(False)
        for b in (self.btn_master, self.btn_orders, self.btn_pulls, self.btn_sched,
                  self.btn_export):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        root.addWidget(QLabel("選取一或多個工單，再用下方按鈕調整；調整後按『重新排程』套用"))
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLS))
        self.tree.setHeaderLabels(COLS)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        root.addWidget(self.tree, 1)

        adj = QHBoxLayout()
        self.btn_pri_on = QPushButton("設為優先")
        self.btn_pri_off = QPushButton("取消優先")
        self.btn_lock = QPushButton("鎖定(不重排)")
        self.btn_unlock = QPushButton("解鎖")
        self.btn_proc = QPushButton("標記處理中")
        self.btn_done = QPushButton("標記已完成")
        self.btn_pri_on.clicked.connect(lambda: self._adjust("priority", True))
        self.btn_pri_off.clicked.connect(lambda: self._adjust("priority", False))
        self.btn_lock.clicked.connect(lambda: self._adjust("locked", True))
        self.btn_unlock.clicked.connect(lambda: self._adjust("locked", False))
        self.btn_proc.clicked.connect(lambda: self._adjust("status", STATUS_PROCESSING))
        self.btn_done.clicked.connect(lambda: self._adjust("status", STATUS_DONE))
        for b in (self.btn_pri_on, self.btn_pri_off, self.btn_lock, self.btn_unlock,
                  self.btn_proc, self.btn_done):
            adj.addWidget(b)
        adj.addStretch(1)
        root.addLayout(adj)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self._msg("請先載入主檔與訂單。")

    # ------------------------------------------------------------------ #
    def _msg(self, m: str) -> None:
        self.statusBar().showMessage(m)

    def _error(self, title: str, exc: Exception) -> None:
        QMessageBox.critical(self, title, f"{exc}\n\n{traceback.format_exc()}")

    # ---- 載入 --------------------------------------------------------- #
    def on_load_master(self) -> None:
        start = settings.get_value("factory_master", "")
        path, _ = QFileDialog.getOpenFileName(self, "選擇主檔", start, "Excel (*.xlsx *.xls)")
        if not path:
            return
        try:
            self.svc.load_master(path)
            settings.set_value("factory_master", path)
            for b in (self.btn_orders, self.btn_pulls):
                b.setEnabled(True)
            self._msg(f"已載入主檔：{os.path.basename(path)}（stage 1 機台 "
                      f"{len(self.svc.stage_machines())} 台）")
        except Exception as e:  # noqa: BLE001
            self._error("載入主檔失敗", e)

    def on_load_orders(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇訂單（可多檔）", "", "訂單 (*.xls *.xlsx *.txt)")
        if not paths:
            return
        try:
            n = self.svc.load_orders(paths, append=False)
            for b in (self.btn_sched, self.btn_export):
                b.setEnabled(True)
            self._msg(f"已載入 {n} 包訂單 → 可載入抽件或直接『重新排程』")
            self.on_reschedule()
        except Exception as e:  # noqa: BLE001
            self._error("載入訂單失敗", e)

    def on_load_pulls(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇抽件（可多檔）", "", "抽件 (*.txt *.xls *.xlsx)")
        if not paths:
            return
        try:
            r = self.svc.load_pulls(paths)
            self._msg(f"抽件：套用 {r['applied']}、重複略過 {r['duplicate']}、"
                      f"無對應 {r['unmatched']} → 重新排程中…")
            self.on_reschedule()
        except Exception as e:  # noqa: BLE001
            self._error("載入抽件失敗", e)

    def on_reschedule(self) -> None:
        try:
            res = self.svc.reschedule()
            self._refresh_tree()
            self._msg(f"排程完成：makespan {res.makespan_min} 分、逾期 {res.late_tasks}、"
                      f"未分配 {len(res.unassigned)}")
            if res.unassigned:
                QMessageBox.warning(self, "有工單無法分配",
                                    "\n".join(f"・{p}：{why}" for p, why in res.unassigned))
        except Exception as e:  # noqa: BLE001
            self._error("排程失敗", e)

    def on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出介面格式", "排程結果_介面format.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            self.svc.export(path)
            QMessageBox.information(self, "完成", f"已匯出：\n{path}")
        except Exception as e:  # noqa: BLE001
            self._error("匯出失敗", e)

    # ---- 樹 ----------------------------------------------------------- #
    def _refresh_tree(self) -> None:
        res = self.svc.result
        if res is None:
            return
        # 保留使用者目前的展開/收合與選取狀態（避免 5 秒自動同步時被重置）
        expanded = {}
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            mid = it.data(0, Qt.UserRole)
            if mid:
                expanded[mid] = it.isExpanded()
        selected = set(self._selected_ids())

        self.tree.clear()
        self._row_meta = {}
        state = self.svc.store.load_state()
        bold = QFont(); bold.setBold(True)
        for mid, lst in sorted(res.by_machine.items()):
            if not lst:
                continue
            top = QTreeWidgetItem([f"{mid}（{len(lst)} 包）"])
            top.setFont(0, bold)
            top.setData(0, Qt.UserRole, mid)
            self.tree.addTopLevelItem(top)
            for s in lst:
                t = s.task
                st = state.get(t.package_id, {})
                status = st.get("status", STATUS_PENDING)
                pq = getattr(t, "pull_qty", {}) or {}
                vals = [
                    str(s.seq), t.package_id, t.customer, str(t.total_qty),
                    str(pq.get("EMER_1", "") or ""), str(pq.get("EMER_2", "") or ""),
                    str(pq.get("Std", "") or ""),
                    s.start.strftime("%m/%d %H:%M") if s.start else "",
                    s.end.strftime("%m/%d %H:%M") if s.end else "",
                    status, "★" if t.priority else "", "🔒" if st.get("locked") else "",
                    f"{s.late_min:.0f}" if s.late_min > 0 else "",
                ]
                child = QTreeWidgetItem(vals)
                child.setData(0, Qt.UserRole, t.package_id)
                self._row_meta[t.package_id] = (t, s.late_min > 0)
                self._style(child, t, status, s.late_min > 0)
                top.addChild(child)
                if t.package_id in selected:
                    child.setSelected(True)   # 必須在 addChild 後設定才會進選取模型
            # 新節點預設展開；既有節點沿用先前展開/收合狀態
            top.setExpanded(expanded.get(mid, True))
        for i in range(len(COLS)):
            self.tree.resizeColumnToContents(i)

    def _style(self, item: QTreeWidgetItem, t, status: str, late: bool) -> None:
        if getattr(t, "has_pull", False) or t.priority:
            bg = COLOR_PULL
        elif status == STATUS_DONE:
            bg = COLOR_DONE
        elif status == STATUS_PROCESSING:
            bg = COLOR_PROCESSING
        elif late:
            bg = COLOR_LATE
        else:
            bg = QColor(Qt.white)
        for c in range(len(COLS)):
            item.setBackground(c, bg)

    # ---- 調整 --------------------------------------------------------- #
    def _selected_ids(self) -> list[str]:
        ids = []
        for it in self.tree.selectedItems():
            pid = it.data(0, Qt.UserRole)
            if pid:
                ids.append(pid)
        return ids

    def _adjust(self, kind: str, value) -> None:
        ids = self._selected_ids()
        if not ids:
            self._msg("請先選取工單列。")
            return
        try:
            for pid in ids:
                if kind == "priority":
                    self.svc.set_priority(pid, value)
                elif kind == "locked":
                    self.svc.set_locked(pid, value)
                elif kind == "status":
                    self.svc.set_status(pid, value, operator="admin")
            self._refresh_tree()
            self._msg(f"已更新 {len(ids)} 筆（{kind}={value}）。狀態/優先/鎖定會在"
                      f"『重新排程』時套用。")
        except Exception as e:  # noqa: BLE001
            self._error("調整失敗", e)

    def _sync_status(self) -> None:
        """定時反映操作員在 DB 的狀態更新：就地更新『狀態欄＋顏色』，
        不重建整棵樹，因此捲動 / 選取 / 展開都不受影響。"""
        if self.svc.result is None:
            return
        state = self.svc.store.load_state()
        status_col = COLS.index("狀態")
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                ch = top.child(j)
                pid = ch.data(0, Qt.UserRole)
                meta = self._row_meta.get(pid)
                if meta is None:
                    continue
                t, late = meta
                status = state.get(pid, {}).get("status", STATUS_PENDING)
                if ch.text(status_col) != status:
                    ch.setText(status_col, status)
                self._style(ch, t, status, late)
