"""FactoryScheduler 領域資料模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional


@dataclass
class MachineInfo:
    machine_id: str
    group: str
    stage: int
    modules: set[str] = field(default_factory=set)      # 已正規化
    uph: dict[str, float] = field(default_factory=dict)  # 群組(大寫) -> 每小時產能

    def uph_for(self, product_group: str, default: float = 0.0) -> float:
        return self.uph.get((product_group or "").upper(), default)

    def can_cover(self, required: set[str]) -> bool:
        return required.issubset(self.modules)


@dataclass
class CalendarBlock:
    day: date
    target: str          # 機台代號 / 群組 / ALL
    start: Optional[time]
    end: Optional[time]
    reason: str = ""


@dataclass
class CustomerDeadline:
    standard_name: str
    aliases: list[str]
    start_time: Optional[time]
    pull_setup_min: int
    pull_emer1: Optional[time]
    pull_emer2: Optional[time]
    pull_std: Optional[time]
    sla_std: Optional[time]
    sla_ref: dict[str, time] = field(default_factory=dict)  # 代碼(大寫) -> 結束時間


@dataclass
class OrderLine:
    source: str                  # APS / Legacy
    customer_raw: str
    customer: str                # 標準客戶名
    workorder_id: str
    package_id: str
    product_ref: str             # 原始
    actual_id: str = ""          # 替代版面
    product_group: str = ""      # 產品群組
    required_modules: set[str] = field(default_factory=set)
    qty: int = 0
    arrive_date: Optional[date] = None
    promise_date: Optional[date] = None
    sla_ref: str = ""
    sla: str = ""
    unmapped: bool = False       # 轉譯查無
    unmap_reason: str = ""


@dataclass
class PullEvent:
    """抽件事件：一張工單 + 一個抽件檔。"""
    customer_raw: str
    customer: str
    file_name: str
    workorder_id: str
    package_id: str
    pull_type: str          # 例 1_Pull Combo / 0_Prioritize Request / 3_Pull by Destroy Card
    pull_time: str          # 例 PULL EMER_1 / PULL EMER_2 / PULL Std
    status: str             # 例 Card is shipped / Card is not shipped yet
    arrive_date: Optional[date] = None
    promise_date: Optional[date] = None
    source: str = ""        # APS / Legacy
    ext_id: str = ""        # APS 的 ID


# 任務種類
KIND_NORMAL = "normal"
KIND_PULL = "pull"
KIND_REMAINING = "remaining"


@dataclass
class PackageTask:
    """排程基本單位：整個 PACKAGE_ID（整包同機、不可拆分）。

    經抽件拆分後會衍生 kind='pull'（抽件批）與 kind='remaining'（剩餘批）。
    """
    package_id: str
    customer: str
    source: str
    lines: list[OrderLine] = field(default_factory=list)
    required_modules: set[str] = field(default_factory=set)  # 聯集(正規化)
    groups: set[str] = field(default_factory=set)
    total_qty: int = 0
    arrive_date: Optional[date] = None
    promise_date: Optional[date] = None
    eligible_machines: list[str] = field(default_factory=list)
    earliest_start: Optional[datetime] = None
    latest_finish: Optional[datetime] = None
    unmapped_products: list[str] = field(default_factory=list)

    # 抽件相關
    kind: str = KIND_NORMAL
    parent_package: Optional[str] = None
    pull_level: str = ""        # PULL EMER_1 / EMER_2 / Std（最緊等級，顯示用）
    pull_type: str = ""
    pull_status: str = ""
    setup_min: int = 0          # 抽件前置(setup)時間（分）
    # 各等級抽件數量（每筆抽件 = 1 張）：鍵 EMER_1 / EMER_2 / Std
    pull_qty: dict[str, int] = field(default_factory=dict)

    @property
    def has_pull(self) -> bool:
        return bool(self.pull_qty)

    @property
    def pulled_total(self) -> int:
        return sum(self.pull_qty.values())

    # 排程/狀態（後續里程碑使用）
    priority: bool = False
    status: str = "未處理"
    assigned_machine: Optional[str] = None

    @property
    def modules_label(self) -> str:
        return ",".join(sorted(self.required_modules)) if self.required_modules else "-"

    def duration_minutes(self, machine: MachineInfo) -> float:
        """整包在該機台的加工分鐘數 = Σ(各行 qty / UPH[該行群組]) × 60。"""
        total = 0.0
        for ln in self.lines:
            uph = machine.uph_for(ln.product_group)
            if uph <= 0:
                return float("inf")
            total += ln.qty / uph * 60.0
        return total
