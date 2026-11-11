"""抽件 (Pull) 載入與套用（單一筆抽件模型）。

模型（依最新 feedback）：
  • 每一筆抽件 = 單一張卡（並非整筆工單/整包），歸到對應 PACKAGE。
  • 不再拆成『抽件批 / 剩餘批』兩個任務；整包仍為一個不可拆分任務。
  • 抽件只是「把整包變急」：
      - 累計各等級抽件數量（EMER_1 / EMER_2 / Std），顯示在介面同一列的對應欄。
      - 標記整包為優先(priority=True)。
      - 交期收緊為「最緊的抽件等級結束時間」與原 SLA 取較早者。
      - 加上客戶 Pull_Setup_Min 前置時間。
  • 去重：以 (ID, FILE_NAME) 為鍵（檔案會疊加，已匯入過的略過）。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd

from . import normalize as nz
from .masterdata import MasterData
from .types import PackageTask, PullEvent

# 抽件等級排序（數字越小越急），顯示欄鍵
_LEVEL_ORDER = {"EMER_1": 0, "EMER_2": 1, "Std": 2}


def _level_key(pull_time: str) -> str:
    """PULL_TIME 文字 → 等級鍵 EMER_1 / EMER_2 / Std。"""
    k = nz.norm_key(pull_time)
    if "EMER_1" in k:
        return "EMER_1"
    if "EMER_2" in k:
        return "EMER_2"
    return "Std"


# PULL_TIME 文字 → Customer_Deadline 的結束時間欄位
def _pull_level_time(md: MasterData, customer: str, pull_time: str):
    dl = md.customers.get(customer)
    if dl is None:
        return None
    key = nz.norm_key(pull_time)
    if "EMER_1" in key:
        return dl.pull_emer1
    if "EMER_2" in key:
        return dl.pull_emer2
    if "STD" in key:
        return dl.pull_std
    return dl.pull_std


def pull_key(ev: PullEvent) -> str:
    """去重鍵：優先 (ID, FILE_NAME)；無 ID 時退回內容組合。"""
    base = ev.ext_id or f"{ev.workorder_id}:{ev.package_id}:{ev.pull_time}:{ev.pull_type}"
    return f"{base}|{ev.file_name}"


def _read_any(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return pd.read_csv(path, sep="|", dtype=str).fillna("")
    df = pd.read_excel(path, dtype=str)
    if "CUSTOMER_NAME" not in df.columns:
        xls = pd.ExcelFile(path)
        for s in xls.sheet_names:
            d = pd.read_excel(xls, s, dtype=str)
            if "CUSTOMER_NAME" in d.columns and len(d) > 0:
                df = d
                break
    return df.fillna("")


def _detect_source(path: str) -> str:
    name = os.path.basename(path).upper()
    return "APS" if "APS" in name else ("Legacy" if "LEGACY" in name else "Unknown")


def load_pull_events(md: MasterData, path: str, source: Optional[str] = None) -> list[PullEvent]:
    df = _read_any(path)
    src = source or _detect_source(path)
    events: list[PullEvent] = []
    for row in df.to_dict("records"):
        cust_raw = nz.text(row.get("CUSTOMER_NAME"))
        events.append(PullEvent(
            customer_raw=cust_raw,
            customer=md.standard_customer(cust_raw),
            file_name=nz.text(row.get("FILE_NAME")),
            workorder_id=nz.text(row.get("WORKORDER_ID")),
            package_id=nz.text(row.get("PACKAGE_ID")) or nz.text(row.get("WORKORDER_ID")),
            pull_type=nz.text(row.get("PULL_TYPE")),
            pull_time=nz.text(row.get("PULL_TIME")),
            status=nz.text(row.get("STATUS")),
            arrive_date=nz.parse_date(row.get("ARRIVER_DATE")),
            promise_date=nz.parse_date(row.get("PROMISE_DATE")),
            source=src,
            ext_id=nz.text(row.get("ID")),
        ))
    return events


def _find_task(tasks: list[PackageTask], ev: PullEvent) -> Optional[PackageTask]:
    """比對抽件歸屬的整包：先比 PACKAGE_ID，再比 WORKORDER_ID 所屬整包。"""
    pid = nz.text(ev.package_id)
    woid = nz.text(ev.workorder_id)
    for t in tasks:
        if t.package_id == pid:
            return t
    for t in tasks:
        if any(ln.workorder_id == woid for ln in t.lines):
            return t
    return None


def apply_pulls(md: MasterData, tasks: list[PackageTask], events: list[PullEvent],
                target_stage: int = 1) -> tuple[list[PackageTask], list[dict]]:
    """套用抽件（單一筆抽件模型）：就地更新所屬整包，回傳 (tasks, Pull_Log)。

    每筆抽件 = 1 張卡 → 累計到該包對應等級的 pull_qty，並把整包標為優先、收緊交期。
    不新增任務（整包仍為單一不可拆分任務）。
    """
    log: list[dict] = []

    for ev in events:
        t = _find_task(tasks, ev)
        if t is None:
            log.append({"package_id": ev.package_id, "workorder_id": ev.workorder_id,
                        "result": "SKIP_無對應訂單", "pull_time": ev.pull_time,
                        "file": ev.file_name})
            continue

        lvl = _level_key(ev.pull_time)                 # EMER_1 / EMER_2 / Std
        t.pull_qty[lvl] = t.pull_qty.get(lvl, 0) + 1   # 單一筆 = 1 張
        t.priority = True
        t.pull_status = ev.status or t.pull_status
        t.pull_type = t.pull_type or ev.pull_type
        # 顯示用「最緊等級」
        if (not t.pull_level) or _LEVEL_ORDER.get(lvl, 9) < _LEVEL_ORDER.get(
                _level_key(t.pull_level), 9):
            t.pull_level = ev.pull_time

        cust = ev.customer or t.customer
        dl = md.customers.get(cust)
        if dl:
            t.setup_min = max(t.setup_min or 0, dl.pull_setup_min or 0)

        # 交期收緊：取（抽件等級結束時間, 原 latest_finish）較早者
        lvl_time = _pull_level_time(md, cust, ev.pull_time)
        fin_date = ev.promise_date or t.promise_date
        if fin_date and lvl_time:
            cand = datetime.combine(fin_date, lvl_time)
            if t.latest_finish is None or cand < t.latest_finish:
                t.latest_finish = cand

        log.append({"package_id": t.package_id, "workorder_id": ev.workorder_id,
                    "result": "PULL", "pull_time": ev.pull_time, "level": lvl,
                    "file": ev.file_name})

    return tasks, log
