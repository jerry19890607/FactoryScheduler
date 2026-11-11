"""FactoryScheduler 狀態存檔 (SQLite)，以 PACKAGE_ID 為鍵。

保存三類資料，讓管理員 / 操作員在單機共用本機 DB：
  • pkg_state  ：每包的狀態 / 手動優先 / 鎖定 / 指派機台（重排凍結用）
  • status_log ：狀態變更歷程（誰、何時）
  • sched_task ：最近一次排程的快照（供操作員免讀 Excel 直接掃描 / 標完成）
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

DB_FILENAME = "factory_state.db"
STATUS_PENDING = "未處理"
STATUS_PROCESSING = "處理中"
STATUS_DONE = "已完成"
STATUSES = [STATUS_PENDING, STATUS_PROCESSING, STATUS_DONE]
LOCKED_STATUSES = {STATUS_PROCESSING, STATUS_DONE}


class FactoryStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.getcwd(), DB_FILENAME)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS pkg_state (
                    package_id       TEXT PRIMARY KEY,
                    status           TEXT NOT NULL DEFAULT '未處理',
                    priority         INTEGER NOT NULL DEFAULT 0,
                    locked           INTEGER NOT NULL DEFAULT 0,
                    assigned_machine TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS status_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id TEXT NOT NULL,
                    status     TEXT NOT NULL,
                    operator   TEXT,
                    ts         TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS sched_task (
                    package_id  TEXT PRIMARY KEY,
                    customer    TEXT,
                    machine     TEXT,
                    seq         INTEGER,
                    start_ts    TEXT,
                    end_ts      TEXT,
                    qty         INTEGER,
                    workorders  TEXT,
                    pull_e1     INTEGER,
                    pull_e2     INTEGER,
                    pull_std    INTEGER,
                    priority    INTEGER,
                    late_min    REAL
                )
                """
            )

    # ---- pkg_state -------------------------------------------------- #
    def load_state(self) -> dict[str, dict]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT package_id, status, priority, locked, assigned_machine "
                "FROM pkg_state"
            ).fetchall()
        return {
            r["package_id"]: {
                "status": r["status"],
                "priority": bool(r["priority"]),
                "locked": bool(r["locked"]),
                "assigned_machine": r["assigned_machine"],
            }
            for r in rows
        }

    def upsert_state(self, package_id: str, *, status: Optional[str] = None,
                     priority: Optional[bool] = None, locked: Optional[bool] = None,
                     assigned_machine: Optional[str] = None) -> None:
        cur = self.load_state().get(package_id, {})
        status = status if status is not None else cur.get("status", STATUS_PENDING)
        priority = priority if priority is not None else cur.get("priority", False)
        locked = locked if locked is not None else cur.get("locked", False)
        if assigned_machine is None:
            assigned_machine = cur.get("assigned_machine")
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT INTO pkg_state (package_id, status, priority, locked, assigned_machine)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(package_id) DO UPDATE SET
                    status=excluded.status, priority=excluded.priority,
                    locked=excluded.locked, assigned_machine=excluded.assigned_machine
                """,
                (package_id, status, int(priority), int(locked), assigned_machine),
            )

    def set_status(self, package_id: str, status: str, operator: Optional[str]) -> None:
        self.upsert_state(package_id, status=status)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO status_log (package_id, status, operator, ts) VALUES (?, ?, ?, ?)",
                (package_id, status, operator, datetime.now().isoformat(timespec="seconds")),
            )

    def history(self, package_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT status, operator, ts FROM status_log WHERE package_id=? ORDER BY id",
                (package_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- sched_task 快照 -------------------------------------------- #
    def save_snapshot(self, rows: list[dict]) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM sched_task")
            con.executemany(
                """
                INSERT INTO sched_task
                    (package_id, customer, machine, seq, start_ts, end_ts, qty,
                     workorders, pull_e1, pull_e2, pull_std, priority, late_min)
                VALUES (:package_id, :customer, :machine, :seq, :start_ts, :end_ts, :qty,
                        :workorders, :pull_e1, :pull_e2, :pull_std, :priority, :late_min)
                """,
                rows,
            )

    def load_snapshot(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT * FROM sched_task ORDER BY machine, seq").fetchall()
        state = self.load_state()
        out = []
        for r in rows:
            d = dict(r)
            d["workorders"] = json.loads(d.get("workorders") or "[]")
            d["status"] = state.get(d["package_id"], {}).get("status", STATUS_PENDING)
            out.append(d)
        return out
