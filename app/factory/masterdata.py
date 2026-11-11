"""主檔載入：Machine_Info / Machine_Calendar / Customer_Deadline / Product_Master / Product_Setup。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from . import normalize as nz
from .types import CalendarBlock, CustomerDeadline, MachineInfo

# 產品群組 ↔ UPH 欄位對照（以大寫群組為 key）
_UPH_COLUMN_BY_GROUP = {
    "WAVE": "UPH Wave",
    "ECC": "UPH ECC",
    "IPASS": "UPH IPass",
    "ICASH": "UPH ICASH",
}


@dataclass
class MasterData:
    machines: dict[str, MachineInfo] = field(default_factory=dict)
    calendar: list[CalendarBlock] = field(default_factory=list)
    customers: dict[str, CustomerDeadline] = field(default_factory=dict)       # 標準名 -> deadline
    alias_to_standard: dict[str, str] = field(default_factory=dict)            # 正規化別名 -> 標準名
    product_master: dict[tuple[str, str], str] = field(default_factory=dict)   # (客戶,產品代號)->Actual
    product_setup: dict[tuple[str, str], tuple[str, set[str]]] = field(default_factory=dict)
    # product_setup: (客戶, Actual_ID) -> (群組, 必備模組set)

    # -- 查詢 --
    def standard_customer(self, raw: str) -> str:
        return self.alias_to_standard.get(nz.norm_key(raw), nz.text(raw))

    def stage_machines(self, stage: int = 1) -> list[MachineInfo]:
        return [m for m in self.machines.values() if m.stage == stage]


def _find_col(cols, *keywords: str) -> Optional[str]:
    # 先找完全相等（避免 'SLA_REF' 誤配到 'PULL EMER_2 (SLA_REF結束時間)'）
    if len(keywords) == 1:
        for c in cols:
            if str(c).strip() == keywords[0]:
                return c
    for c in cols:
        cs = str(c)
        if all(k in cs for k in keywords):
            return c
    return None


def load_master(path: str) -> MasterData:
    md = MasterData()
    xls = pd.ExcelFile(path)
    sheets = set(xls.sheet_names)

    # ---------------- Machine_Info ----------------
    mi = pd.read_excel(xls, "Machine_Info", dtype=str)
    module_cols = [c for c in mi.columns if str(c).startswith("模組")]
    uph_cols = {g: col for g, col in _UPH_COLUMN_BY_GROUP.items() if col in mi.columns}
    for _, r in mi.iterrows():
        mid = nz.text(r.get("機台代號"))
        if not mid:
            continue
        mods = {nz.norm_module(r[c]) for c in module_cols
                if nz.text(r[c]) and nz.text(r[c]).upper() != "NONE"}
        mods.discard("")
        try:
            stage = int(float(nz.text(r.get("製程階段")) or 0))
        except ValueError:
            stage = -1
        uph: dict[str, float] = {}
        for g, col in uph_cols.items():
            val = nz.text(r.get(col))
            if val:
                try:
                    uph[g] = float(val)
                except ValueError:
                    pass
        md.machines[mid] = MachineInfo(mid, nz.text(r.get("設備群組")), stage, mods, uph)

    # ---------------- Machine_Calendar ----------------
    if "Machine_Calendar" in sheets:
        mc = pd.read_excel(xls, "Machine_Calendar", dtype=str)
        c_day = _find_col(mc.columns, "日期")
        c_target = _find_col(mc.columns, "排空對象") or _find_col(mc.columns, "對象")
        c_start = _find_col(mc.columns, "自訂開始") or _find_col(mc.columns, "開始")
        c_end = _find_col(mc.columns, "自訂結束") or _find_col(mc.columns, "結束")
        c_reason = _find_col(mc.columns, "原因")
        for _, r in mc.iterrows():
            day = nz.parse_date(r.get(c_day)) if c_day else None
            if not day:
                continue
            md.calendar.append(CalendarBlock(
                day=day,
                target=nz.text(r.get(c_target)) if c_target else "ALL",
                start=nz.parse_time(r.get(c_start)) if c_start else None,
                end=nz.parse_time(r.get(c_end)) if c_end else None,
                reason=nz.text(r.get(c_reason)) if c_reason else "",
            ))

    # ---------------- Customer_Deadline ----------------
    if "Customer_Deadline" in sheets:
        cd = pd.read_excel(xls, "Customer_Deadline", dtype=str)
        cols = cd.columns
        c_name = _find_col(cols, "CUSTOMER_NAME")
        c_start = _find_col(cols, "Start Time") or _find_col(cols, "Start")
        c_setup = _find_col(cols, "Pull_Setup_Min") or _find_col(cols, "Pull_Setup")
        c_e1 = _find_col(cols, "PULL EMER_1")
        c_e2 = _find_col(cols, "PULL EMER_2")
        c_std = _find_col(cols, "PULL Std")
        c_sla_std = _find_col(cols, "SLA Std")
        c_sla_ref = _find_col(cols, "SLA_REF")
        for _, r in cd.iterrows():
            raw = nz.text(r.get(c_name))
            if not raw:
                continue
            aliases = [a.strip() for a in raw.replace("｜", "|").split("|") if a.strip()]
            std = aliases[0] if aliases else raw
            setup_min = 0
            sv = nz.text(r.get(c_setup)) if c_setup else ""
            if sv:
                try:
                    setup_min = int(float(sv))
                except ValueError:
                    setup_min = 0
            # SLA_REF 語法: 代碼=時間 { | 代碼=時間 }
            sla_ref_map: dict[str, "object"] = {}
            if c_sla_ref:
                for item in nz.text(r.get(c_sla_ref)).replace("｜", "|").split("|"):
                    if "=" in item:
                        code, t = item.split("=", 1)
                        tt = nz.parse_time(t)
                        if tt:
                            sla_ref_map[nz.norm_key(code)] = tt
            dl = CustomerDeadline(
                standard_name=std,
                aliases=aliases,
                start_time=nz.parse_time(r.get(c_start)) if c_start else None,
                pull_setup_min=setup_min,
                pull_emer1=nz.parse_time(r.get(c_e1)) if c_e1 else None,
                pull_emer2=nz.parse_time(r.get(c_e2)) if c_e2 else None,
                pull_std=nz.parse_time(r.get(c_std)) if c_std else None,
                sla_std=nz.parse_time(r.get(c_sla_std)) if c_sla_std else None,
                sla_ref=sla_ref_map,
            )
            md.customers[std] = dl
            for a in aliases:
                key = nz.norm_key(a)
                if key in md.alias_to_standard and md.alias_to_standard[key] != std:
                    raise ValueError(f"客戶別名重複衝突: {a}")
                md.alias_to_standard[key] = std

    # ---------------- Product_Master ----------------
    pm = pd.read_excel(xls, "Product_Master", dtype=str)
    c_cust = _find_col(pm.columns, "CUSTOMER_NAME")
    c_pid = _find_col(pm.columns, "產品代號")
    c_actual = _find_col(pm.columns, "替代版面")
    for _, r in pm.iterrows():
        cust = md.standard_customer(r.get(c_cust))
        pid = nz.product_id(r.get(c_pid))
        actual = nz.product_id(r.get(c_actual)) or pid
        if pid:
            md.product_master[(cust, pid)] = actual

    # ---------------- Product_Setup ----------------
    psx = pd.read_excel(xls, "Product_Setup", dtype=str)
    c_cust2 = _find_col(psx.columns, "CUSTOMER_NAME")
    c_actual2 = _find_col(psx.columns, "Actual_ID") or _find_col(psx.columns, "Actual")
    c_group = _find_col(psx.columns, "產品群組")
    mod_cols2 = [c for c in psx.columns if "必備模組" in str(c)]
    for _, r in psx.iterrows():
        cust = md.standard_customer(r.get(c_cust2))
        actual = nz.product_id(r.get(c_actual2))
        if not actual:
            continue
        group = nz.text(r.get(c_group)) if c_group else ""
        mods = {nz.norm_module(r[c]) for c in mod_cols2
                if nz.text(r[c]) and nz.text(r[c]).upper() != "NONE"}
        mods.discard("")
        key = (cust, actual)
        if key in md.product_setup:
            g0, m0 = md.product_setup[key]
            md.product_setup[key] = (g0 or group, m0 | mods)
        else:
            md.product_setup[key] = (group, mods)

    return md
