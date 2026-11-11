"""FactoryScheduler 服務層：串接引擎 (主檔/訂單/抽件/排程/輸出) 與狀態存檔。

供 GUI 使用：管理員載入與重排、調整優先/鎖定、匯出；操作員掃描與標完成。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from . import barcode, ledger, orders, output, pulls, scheduler
from .fstore import FactoryStore, LOCKED_STATUSES, STATUS_DONE, STATUS_PENDING
from .masterdata import MasterData, load_master
from .scheduler import ScheduleResult
from .types import PackageTask

TARGET_STAGE = 1


class FactoryService:
    def __init__(self, state_db: Optional[str] = None, ledger_path: Optional[str] = None):
        self.store = FactoryStore(state_db)
        self.ledger_path = ledger_path or "FactoryScheduler/Logs/pull_imported.json"
        self.md: Optional[MasterData] = None
        self.tasks: list[PackageTask] = []
        self.result: Optional[ScheduleResult] = None

    # ---- 載入 -------------------------------------------------------- #
    def load_master(self, path: str) -> MasterData:
        self.md = load_master(path)
        return self.md

    def stage_machines(self) -> list:
        return self.md.stage_machines(TARGET_STAGE) if self.md else []

    def load_orders(self, paths: list[str], append: bool = False) -> int:
        if self.md is None:
            raise RuntimeError("請先載入主檔")
        if not append:
            self.tasks = []
        n = 0
        for p in paths:
            t = orders.load_packages(self.md, p, target_stage=TARGET_STAGE)
            self.tasks += t
            n += len(t)
        return n

    def load_pulls(self, paths: list[str]) -> dict:
        if self.md is None:
            raise RuntimeError("請先載入主檔")
        seen = ledger.load_seen(self.ledger_path)
        applied = skipped_dup = unmatched = 0
        for p in paths:
            evs = pulls.load_pull_events(self.md, p)
            new = [e for e in evs if pulls.pull_key(e) not in seen]
            skipped_dup += len(evs) - len(new)
            for e in new:
                seen.add(pulls.pull_key(e))
            _, log = pulls.apply_pulls(self.md, self.tasks, new, target_stage=TARGET_STAGE)
            applied += sum(1 for l in log if l["result"] == "PULL")
            unmatched += sum(1 for l in log if str(l["result"]).startswith("SKIP"))
        ledger.save_seen(self.ledger_path, seen)
        return {"applied": applied, "duplicate": skipped_dup, "unmatched": unmatched}

    # ---- 重排 (套用存檔狀態 → 凍結 → 排程 → 存快照) ----------------- #
    def reschedule(self, horizon: Optional[datetime] = None) -> ScheduleResult:
        if self.md is None:
            raise RuntimeError("請先載入主檔")
        state = self.store.load_state()
        for t in self.tasks:
            s = state.get(t.package_id)
            if not s:
                continue
            t.status = s["status"] or STATUS_PENDING
            if s["priority"]:
                t.priority = True
            # 鎖定或已開工/完成 → 還原既有機台，排程時凍結
            if (s["locked"] or t.status in LOCKED_STATUSES) and s["assigned_machine"]:
                t.assigned_machine = s["assigned_machine"]
        self.result = scheduler.schedule(self.md, self.tasks, TARGET_STAGE, horizon)
        self._persist_snapshot()
        return self.result

    def _persist_snapshot(self) -> None:
        if self.result is None:
            return
        rows = []
        for mid, lst in self.result.by_machine.items():
            for s in lst:
                t = s.task
                pq = getattr(t, "pull_qty", {}) or {}
                rows.append({
                    "package_id": t.package_id,
                    "customer": t.customer,
                    "machine": mid,
                    "seq": s.seq,
                    "start_ts": s.start.isoformat(timespec="minutes") if s.start else "",
                    "end_ts": s.end.isoformat(timespec="minutes") if s.end else "",
                    "qty": t.total_qty,
                    "workorders": json.dumps(
                        sorted({ln.workorder_id for ln in t.lines}), ensure_ascii=False),
                    "pull_e1": pq.get("EMER_1", 0),
                    "pull_e2": pq.get("EMER_2", 0),
                    "pull_std": pq.get("Std", 0),
                    "priority": int(bool(t.priority)),
                    "late_min": s.late_min,
                })
                # 保存指派機台供下次凍結
                self.store.upsert_state(t.package_id, assigned_machine=mid)
        self.store.save_snapshot(rows)

    # ---- 管理員調整 -------------------------------------------------- #
    def set_status(self, package_id: str, status: str, operator: Optional[str] = None) -> None:
        self.store.set_status(package_id, status, operator)
        t = self._get(package_id)
        if t:
            t.status = status

    def set_priority(self, package_id: str, value: bool) -> None:
        self.store.upsert_state(package_id, priority=value)
        t = self._get(package_id)
        if t:
            t.priority = value

    def set_locked(self, package_id: str, value: bool) -> None:
        self.store.upsert_state(package_id, locked=value)

    # ---- 匯出 -------------------------------------------------------- #
    def export(self, path: str) -> None:
        if self.result is None:
            raise RuntimeError("尚未排程")
        output.write_schedule(path, self.result)

    # ---- 操作員 (掃描 / 完成) --------------------------------------- #
    def load_snapshot(self) -> list[dict]:
        """操作員免讀 Excel：回傳最近一次排程的快照 (含最新狀態)。"""
        return self.store.load_snapshot()

    def find_by_scan(self, code: str, snapshot: Optional[list[dict]] = None) -> list[dict]:
        """掃描條碼 → 轉換 → 比對 PACKAGE_ID 或其工單號所屬整包。回傳快照列。"""
        core = barcode.parse_scan(code)
        if not core:
            return []
        rows = snapshot if snapshot is not None else self.load_snapshot()
        hits = [r for r in rows if r["package_id"] == core]
        if hits:
            return hits
        return [r for r in rows if core in (r.get("workorders") or [])]

    def set_status_packages(self, package_ids: list[str], status: str,
                            operator: Optional[str] = None) -> None:
        for pid in package_ids:
            self.store.set_status(pid, status, operator)
            t = self._get(pid)
            if t:
                t.status = status

    def complete_packages(self, package_ids: list[str], operator: Optional[str] = None) -> None:
        self.set_status_packages(package_ids, STATUS_DONE, operator)

    # ---- 內部 -------------------------------------------------------- #
    def _get(self, package_id: str) -> Optional[PackageTask]:
        return next((t for t in self.tasks if t.package_id == package_id), None)
