"""交期規則引擎：由 Start Time / SLA_REF / PROMISE_DATE 推出最早開始、最晚完成。

規則（日常訂單）：
  最早開始 = ARRIVER_DATE 當天的客戶 Start Time
  最晚完成 = PROMISE_DATE 當天的結束時間；結束時間取法：
             1) 訂單 SLA_REF 代碼能在 Customer_Deadline.SLA_REF 清單命中 → 用該時間
             2) 否則用 SLA Std
             3) 再否則 當日 23:59
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from . import normalize as nz
from .masterdata import MasterData

_END_OF_DAY = time(23, 59)


def resolve_finish_time(md: MasterData, customer_std: str, sla_ref_code: str) -> time:
    dl = md.customers.get(customer_std)
    if dl is None:
        return _END_OF_DAY
    code = nz.norm_key(sla_ref_code)
    if code and code in dl.sla_ref:
        return dl.sla_ref[code]
    if dl.sla_std:
        return dl.sla_std
    return _END_OF_DAY


def earliest_start(md: MasterData, customer_std: str, arrive: Optional[date]) -> Optional[datetime]:
    if arrive is None:
        return None
    dl = md.customers.get(customer_std)
    st = dl.start_time if (dl and dl.start_time) else time(0, 0)
    return datetime.combine(arrive, st)


def latest_finish(md: MasterData, customer_std: str, promise: Optional[date],
                  sla_ref_code: str) -> Optional[datetime]:
    if promise is None:
        return None
    return datetime.combine(promise, resolve_finish_time(md, customer_std, sla_ref_code))
