"""FactoryScheduler 全流程 CLI：載入主檔 → 轉譯訂單 → 套用抽件 → 時間軸排程 → 介面輸出。

範例：
  python run_factory.py \
    --master FactoryScheduler/Schema/Factory_Scheduling_Schema_V4_3.2.xlsx \
    --orders FactoryScheduler/Orders/Schedule_Legacy_20261106_1215.xls \
             FactoryScheduler/Orders/Schedule_APS_20261106_1210.xlsx \
    --pulls  FactoryScheduler/Pulls/Legacy_Pull_20261106_1100.txt \
    --out FactoryScheduler/Output/排程結果_介面format.xlsx
"""
from __future__ import annotations

import argparse
from datetime import datetime

from app.factory import ledger, orders, output, pulls, scheduler
from app.factory.masterdata import load_master


def main() -> None:
    ap = argparse.ArgumentParser(description="FactoryScheduler 全流程")
    ap.add_argument("--master", required=True)
    ap.add_argument("--orders", nargs="+", default=[])
    ap.add_argument("--pulls", nargs="*", default=[])
    ap.add_argument("--out", default="FactoryScheduler/Output/排程結果_介面format.xlsx")
    ap.add_argument("--horizon", default=None, help="排程起點 YYYY-MM-DD HH:MM")
    ap.add_argument("--ledger", default="FactoryScheduler/Logs/pull_imported.json",
                    help="抽件匯入台帳（以 ID+FILE_NAME 去重），設為空字串可停用")
    args = ap.parse_args()

    md = load_master(args.master)
    print(f"主檔: 機台 {len(md.machines)}、產品 {len(md.product_master)}、客戶 {len(md.customers)}")

    tasks = []
    for f in args.orders:
        t = orders.load_packages(md, f)
        print(f"  訂單 {f} → {len(t)} 包")
        tasks += t

    seen = ledger.load_seen(args.ledger)
    for f in args.pulls:
        evs = pulls.load_pull_events(md, f)
        new = [e for e in evs if pulls.pull_key(e) not in seen]
        dup = len(evs) - len(new)
        for e in new:
            seen.add(pulls.pull_key(e))
        tasks, log = pulls.apply_pulls(md, tasks, new)
        applied = sum(1 for l in log if l["result"] == "PULL")
        skip = sum(1 for l in log if str(l["result"]).startswith("SKIP"))
        print(f"  抽件 {f} → 事件 {len(evs)}（新 {len(new)}、重複略過 {dup}）、"
              f"套用 {applied}、無對應 {skip}")
    ledger.save_seen(args.ledger, seen)

    horizon = datetime.strptime(args.horizon, "%Y-%m-%d %H:%M") if args.horizon else None
    res = scheduler.schedule(md, tasks, horizon_start=horizon)
    print(f"排程: makespan {res.makespan_min} 分、逾期 {res.late_tasks}、未分配 {len(res.unassigned)}")

    output.write_schedule(args.out, res)
    print(f"已輸出介面格式: {args.out}")


if __name__ == "__main__":
    main()
