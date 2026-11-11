"""日常訂單載入與轉譯：APS(.xlsx) / Legacy(.xls, .txt) → OrderLine → PackageTask。"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from . import deadlines, normalize as nz
from .masterdata import MasterData
from .types import OrderLine, PackageTask

# 日常訂單標準欄位
REQUIRED_COLS = [
    "CUSTOMER_NAME", "ARRIVER_DATE", "PROMISE_DATE", "WORKORDER_ID",
    "PACKAGE_ID", "PRODUCT_REF", "SLA_REF", "SLA", "QTY",
]


def _read_any(path: str) -> pd.DataFrame:
    """讀 .txt(以 | 分隔) 或 .xls/.xlsx；全部以字串讀入以保留前導 0。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return pd.read_csv(path, sep="|", dtype=str).fillna("")
    df = pd.read_excel(path, dtype=str)
    # APS 檔資料可能在非第一分頁 → 若第一分頁沒有必要欄位，掃描其他分頁
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
    if "APS" in name:
        return "APS"
    if "LEGACY" in name:
        return "Legacy"
    return "Unknown"


def translate_line(md: MasterData, row: dict, source: str) -> OrderLine:
    cust_raw = nz.text(row.get("CUSTOMER_NAME"))
    cust = md.standard_customer(cust_raw)
    product_ref = nz.product_id(row.get("PRODUCT_REF"))
    qty = 0
    try:
        qty = int(float(nz.text(row.get("QTY")) or 0))
    except ValueError:
        qty = 0

    line = OrderLine(
        source=source,
        customer_raw=cust_raw,
        customer=cust,
        workorder_id=nz.text(row.get("WORKORDER_ID")),
        package_id=nz.text(row.get("PACKAGE_ID")) or nz.text(row.get("WORKORDER_ID")),
        product_ref=product_ref,
        qty=qty,
        arrive_date=nz.parse_date(row.get("ARRIVER_DATE")),
        promise_date=nz.parse_date(row.get("PROMISE_DATE")),
        sla_ref=nz.text(row.get("SLA_REF")),
        sla=nz.text(row.get("SLA")),
    )

    # 四段轉譯：產品代號 → 替代版面 → 群組/模組
    actual = md.product_master.get((cust, product_ref))
    if actual is None:
        line.unmapped = True
        line.unmap_reason = f"Product_Master 查無 ({cust},{product_ref})"
        return line
    line.actual_id = actual
    setup = md.product_setup.get((cust, actual))
    if setup is None:
        line.unmapped = True
        line.unmap_reason = f"Product_Setup 查無 ({cust},{actual})"
        return line
    line.product_group, line.required_modules = setup[0], set(setup[1])
    return line


def load_order_lines(md: MasterData, path: str, source: Optional[str] = None) -> list[OrderLine]:
    df = _read_any(path)
    src = source or _detect_source(path)
    return [translate_line(md, row, src) for row in df.to_dict("records")]


def derive_fields(md: MasterData, lines: list[OrderLine], target_stage: int = 1):
    """由一組訂單行推導：模組聯集 / 群組 / 總量 / 合格機台 / 查無產品。"""
    required: set[str] = set()
    groups: set[str] = set()
    unmapped: list[str] = []
    for ln in lines:
        required |= ln.required_modules
        if ln.product_group:
            groups.add(ln.product_group)
        if ln.unmapped:
            unmapped.append(ln.product_ref)
    eligible = []
    for m in md.stage_machines(target_stage):
        if not required or not m.can_cover(required):
            continue
        if groups and any(m.uph_for(g) <= 0 for g in groups):
            continue
        eligible.append(m.machine_id)
    return required, groups, sum(ln.qty for ln in lines), eligible, sorted(set(unmapped))


def build_packages(md: MasterData, lines: list[OrderLine],
                   target_stage: int = 1) -> list[PackageTask]:
    stage_machines = md.stage_machines(target_stage)
    by_pkg: dict[str, list[OrderLine]] = {}
    for ln in lines:
        by_pkg.setdefault(ln.package_id, []).append(ln)

    tasks: list[PackageTask] = []
    for pkg, plines in by_pkg.items():
        customers = {ln.customer for ln in plines}
        customer = next(iter(customers)) if len(customers) == 1 else "/".join(sorted(customers))
        required: set[str] = set()
        groups: set[str] = set()
        unmapped: list[str] = []
        for ln in plines:
            required |= ln.required_modules
            if ln.product_group:
                groups.add(ln.product_group)
            if ln.unmapped:
                unmapped.append(ln.product_ref)

        arrive = min((ln.arrive_date for ln in plines if ln.arrive_date), default=None)
        promise = min((ln.promise_date for ln in plines if ln.promise_date), default=None)

        # 合格機台：模組涵蓋聯集 且 對所有出現群組都有 UPH
        eligible = []
        for m in stage_machines:
            if not required or not m.can_cover(required):
                continue
            if groups and any(m.uph_for(g) <= 0 for g in groups):
                continue
            eligible.append(m.machine_id)

        # 交期：整包取最早開始、最緊的最晚完成
        es = max((deadlines.earliest_start(md, ln.customer, ln.arrive_date)
                  for ln in plines if ln.arrive_date), default=None)
        lf_candidates = [deadlines.latest_finish(md, ln.customer, ln.promise_date, ln.sla_ref)
                         for ln in plines]
        lf_candidates = [x for x in lf_candidates if x]
        lf = min(lf_candidates) if lf_candidates else None

        tasks.append(PackageTask(
            package_id=pkg,
            customer=customer,
            source=plines[0].source,
            lines=plines,
            required_modules=required,
            groups=groups,
            total_qty=sum(ln.qty for ln in plines),
            arrive_date=arrive,
            promise_date=promise,
            eligible_machines=eligible,
            earliest_start=es,
            latest_finish=lf,
            unmapped_products=sorted(set(unmapped)),
        ))
    return tasks


def load_packages(md: MasterData, path: str, source: Optional[str] = None,
                  target_stage: int = 1) -> list[PackageTask]:
    return build_packages(md, load_order_lines(md, path, source), target_stage)
