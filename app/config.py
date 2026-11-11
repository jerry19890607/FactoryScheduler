"""全域共用常數（現行 FactoryScheduler 使用）。

備註：工單狀態（未處理/處理中/已完成）、鎖定狀態等定義在 app/factory/fstore.py。
"""
from __future__ import annotations

# ---- 角色 ----
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
