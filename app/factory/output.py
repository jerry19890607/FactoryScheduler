"""M6 介面 format 輸出：每台機台一張時序表，欄位對齊『介面 format.xlsx』。

欄位：選擇 / 優先順序 / CUSTOMER_NAME / WORKORDER_ID / PACKAGE_ID /
      PACKAGE_ID Qty / PULL EMER_1 Qty / PULL EMER_2 Qty / PULL Std Qty /
      ARRIVER_DATE / PROMISE_DATE / 開始日期時間 / 結束日期時間 / Total time (Min)

每個整包（PACKAGE_ID）一列；若該包有抽件，則在同一列對應等級欄顯示各等級
抽件數量（每筆抽件 = 1 張），整列以橘色標示，其下列出成員工單。
"""
from __future__ import annotations

import os
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .scheduler import ScheduleResult

COLUMNS = ["選擇", "優先順序", "CUSTOMER_NAME", "WORKORDER_ID", "PACKAGE_ID",
           "PACKAGE_ID Qty", "PULL EMER_1 Qty", "PULL EMER_2 Qty", "PULL Std Qty",
           "ARRIVER_DATE", "PROMISE_DATE", "開始日期時間", "結束日期時間", "Total time (Min)"]

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(color="FFFFFF", bold=True)
PULL_FILL = PatternFill("solid", fgColor="F8CBAD")
TITLE_FONT = Font(bold=True, size=12)


def _fmt_dt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt, datetime) else ""


def _fmt_d(d) -> str:
    return d.isoformat() if d else ""


def write_schedule(path: str, result: ScheduleResult) -> None:
    wb = Workbook()
    wb.remove(wb.active)

    for mid, lst in result.by_machine.items():
        if not lst:
            continue
        ws = wb.create_sheet(title=mid[:31])
        # 機台標題列
        ws.cell(row=1, column=3, value=f"{mid} (機器名稱)").font = TITLE_FONT
        # 欄位表頭在第 2 列
        for ci, name in enumerate(COLUMNS, 1):
            c = ws.cell(row=2, column=ci, value=name)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.alignment = Alignment(horizontal="center")

        r = 3
        for s in lst:
            t = s.task
            has_pull = bool(getattr(t, "pull_qty", None))
            pq = t.pull_qty if has_pull else {}
            row = {
                "選擇": "☐",
                "優先順序": s.seq,
                "CUSTOMER_NAME": t.customer,
                "WORKORDER_ID": t.lines[0].workorder_id if t.lines else "",
                "PACKAGE_ID": t.package_id,
                "PACKAGE_ID Qty": t.total_qty,
                "PULL EMER_1 Qty": pq.get("EMER_1", "") or "",
                "PULL EMER_2 Qty": pq.get("EMER_2", "") or "",
                "PULL Std Qty": pq.get("Std", "") or "",
                "ARRIVER_DATE": _fmt_d(t.arrive_date),
                "PROMISE_DATE": _fmt_d(t.promise_date),
                "開始日期時間": _fmt_dt(s.start),
                "結束日期時間": _fmt_dt(s.end),
                "Total time (Min)": round(s.total_min, 1),
            }
            for ci, name in enumerate(COLUMNS, 1):
                cell = ws.cell(row=r, column=ci, value=row.get(name, ""))
                if has_pull:
                    cell.fill = PULL_FILL
            r += 1
            # 成員工單（第二行起，數量留白）
            for ln in t.lines[1:]:
                ws.cell(row=r, column=4, value=ln.workorder_id)
                ws.cell(row=r, column=5, value=t.package_id)
                r += 1

        for ci, name in enumerate(COLUMNS, 1):
            ws.column_dimensions[get_column_letter(ci)].width = max(12, len(name) + 2)

    # 摘要頁
    summ = wb.create_sheet(title="摘要", index=0)
    summ.append(["指標", "值"])
    summ.append(["排程起點", _fmt_dt(result.horizon_start)])
    summ.append(["makespan (分)", result.makespan_min])
    summ.append(["逾期任務數", result.late_tasks])
    summ.append(["最大逾期 (分)", result.max_late_min])
    summ.append(["未分配任務數", len(result.unassigned)])
    for uid, why in result.unassigned:
        summ.append([uid, why])

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
