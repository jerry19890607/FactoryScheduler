"""條碼掃描轉換與工單比對。

擷取規則（已確認）：
  1) 去除前綴到第一個 '_'（含）：   W_271B4A-1 → 271B4A-1
  2) 去除第一個 '-' 之後（含）：    271B4A-1 → 271B4A
  3) 若無 '_' 與 '-' 則原樣使用：   3783C4 → 3783C4
  回傳核心碼（WORKORDER_ID / PACKAGE_ID 候選）。
"""
from __future__ import annotations

from typing import Optional


def parse_scan(code: str) -> str:
    s = (code or "").strip()
    if not s:
        return ""
    if "_" in s:
        s = s.split("_", 1)[1]
    if "-" in s:
        s = s.split("-", 1)[0]
    return s.strip()


def match_packages(core: str, packages) -> list:
    """以核心碼比對：優先比 PACKAGE_ID，其次 WORKORDER_ID（含該工單的整包）。

    packages: 具有 .package_id / .lines(含 .workorder_id) 的物件清單。
    回傳符合的 package 物件清單（可能多個）。
    """
    core = (core or "").strip()
    if not core:
        return []
    hits = [p for p in packages if getattr(p, "package_id", None) == core]
    if hits:
        return hits
    # 比對工單號 → 回傳其所屬整包
    out = []
    for p in packages:
        for ln in getattr(p, "lines", []):
            if getattr(ln, "workorder_id", None) == core:
                out.append(p)
                break
    return out
