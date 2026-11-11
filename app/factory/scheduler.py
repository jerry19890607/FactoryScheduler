"""M5 時間軸排程（stage 1）。

作法：時間前推的貪婪清單排程（list scheduling），同時決定『指派機台』與『時鐘時間』。
  • 排序：抽件/優先 → 交期(EDD) → 數量大者先。
  • 指派：每個任務選「完工時間最早」的合格機台（已考慮機台目前可用時間、
         最早開始、Machine_Calendar 挖空、抽件 setup）。
  • 凍結：狀態為處理中/已完成或已釘選(assigned_machine)者先固定排在該機台。
  • 指標：makespan、逾期任務數、最大逾期。
規模（數百任務、<10 機台）用貪婪即可秒出；之後要更佳可換 CP-SAT。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional

from .masterdata import MasterData
from .types import PackageTask

_FROZEN_STATUS = {"處理中", "已完成"}


@dataclass
class ScheduledTask:
    task: PackageTask
    machine: str
    seq: int
    start: datetime
    end: datetime
    setup_min: float
    proc_min: float
    late_min: float = 0.0

    @property
    def total_min(self) -> float:
        return self.setup_min + self.proc_min


@dataclass
class ScheduleResult:
    by_machine: dict[str, list[ScheduledTask]] = field(default_factory=dict)
    unassigned: list[tuple[str, str]] = field(default_factory=list)   # (package_id, 原因)
    horizon_start: Optional[datetime] = None
    makespan_min: float = 0.0
    late_tasks: int = 0
    max_late_min: float = 0.0


def _blackout_intervals(md: MasterData, machine_id: str) -> list[tuple[datetime, datetime]]:
    """該機台所有排空時段（含針對群組/ALL 的），轉成 datetime 區間並排序。"""
    m = md.machines.get(machine_id)
    group = m.group if m else ""
    out: list[tuple[datetime, datetime]] = []
    for b in md.calendar:
        tgt = (b.target or "").strip()
        if tgt not in (machine_id, group, "ALL", "all", ""):
            continue
        s = datetime.combine(b.day, b.start or time(0, 0))
        e = datetime.combine(b.day, b.end or time(23, 59))
        if e > s:
            out.append((s, e))
    out.sort()
    return out


def _advance(start: datetime, minutes: float,
             blackouts: list[tuple[datetime, datetime]]) -> datetime:
    """從 start 消耗 minutes 的工時，遇到排空時段就跳過（往後順延）。"""
    cur = start
    remaining = minutes
    # 若起點落在排空內，直接推到排空結束
    for bs, be in blackouts:
        if bs <= cur < be:
            cur = be
    guard = 0
    while remaining > 1e-9:
        guard += 1
        if guard > 10000:
            break
        nxt = None
        for bs, be in blackouts:
            if bs >= cur:
                nxt = (bs, be)
                break
            if bs <= cur < be:
                cur = be
                nxt = "restart"
                break
        if nxt == "restart":
            continue
        if nxt is None:
            return cur + timedelta(minutes=remaining)
        bs, be = nxt
        avail = (bs - cur).total_seconds() / 60.0
        if remaining <= avail:
            return cur + timedelta(minutes=remaining)
        remaining -= avail
        cur = be
    return cur


def _sort_key(t: PackageTask):
    return (
        0 if t.priority else 1,
        t.latest_finish or datetime.max,
        -t.total_qty,
        t.package_id,
    )


def schedule(md: MasterData, tasks: list[PackageTask], target_stage: int = 1,
             horizon_start: Optional[datetime] = None) -> ScheduleResult:
    res = ScheduleResult()
    stage_ids = [m.machine_id for m in md.stage_machines(target_stage)]
    blackouts = {mid: _blackout_intervals(md, mid) for mid in stage_ids}

    starts = [t.earliest_start for t in tasks if t.earliest_start]
    horizon = horizon_start or (min(starts) if starts else datetime.now())
    res.horizon_start = horizon
    avail: dict[str, datetime] = {mid: horizon for mid in stage_ids}
    res.by_machine = {mid: [] for mid in stage_ids}

    def place(t: PackageTask, mid: str) -> ScheduledTask:
        m = md.machines[mid]
        proc = t.duration_minutes(m)
        setup = float(t.setup_min or 0)
        begin = max(avail[mid], t.earliest_start or horizon)
        # setup + 加工 皆需避開排空
        after_setup = _advance(begin, setup, blackouts[mid]) if setup else begin
        end = _advance(after_setup, proc, blackouts[mid])
        avail[mid] = end
        late = 0.0
        if t.latest_finish and end > t.latest_finish:
            late = (end - t.latest_finish).total_seconds() / 60.0
        st = ScheduledTask(task=t, machine=mid, seq=0, start=begin, end=end,
                           setup_min=setup, proc_min=proc, late_min=late)
        res.by_machine[mid].append(st)
        return st

    # 1) 凍結任務（處理中/已完成/已釘選）先排在其機台
    frozen = [t for t in tasks
              if (t.status in _FROZEN_STATUS or t.assigned_machine) and t.assigned_machine in stage_ids]
    frozen_set = set(id(t) for t in frozen)
    for t in sorted(frozen, key=_sort_key):
        place(t, t.assigned_machine)

    # 2) 其餘任務：EDD/優先排序後，逐一指派到「完工最早」的合格機台
    free = [t for t in tasks if id(t) not in frozen_set]
    for t in sorted(free, key=_sort_key):
        elig = [mid for mid in t.eligible_machines if mid in avail]
        if not elig:
            reason = "需求模組/群組無合格機台" if t.required_modules else "需求模組未知"
            res.unassigned.append((t.package_id, reason))
            continue
        best_mid, best_end = None, None
        for mid in elig:
            m = md.machines[mid]
            proc = t.duration_minutes(m)
            setup = float(t.setup_min or 0)
            begin = max(avail[mid], t.earliest_start or horizon)
            after_setup = _advance(begin, setup, blackouts[mid]) if setup else begin
            end = _advance(after_setup, proc, blackouts[mid])
            if best_end is None or end < best_end:
                best_end, best_mid = end, mid
        st = place(t, best_mid)
        t.assigned_machine = best_mid

    # 3) 重編機台內序號 + 指標
    for mid, lst in res.by_machine.items():
        lst.sort(key=lambda s: s.start)
        for i, s in enumerate(lst, 1):
            s.seq = i
    all_sched = [s for lst in res.by_machine.values() for s in lst]
    if all_sched:
        res.makespan_min = round((max(s.end for s in all_sched) - horizon).total_seconds() / 60.0, 1)
        late = [s for s in all_sched if s.late_min > 0]
        res.late_tasks = len(late)
        res.max_late_min = round(max((s.late_min for s in late), default=0.0), 1)
    return res
