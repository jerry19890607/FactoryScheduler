"""正規化工具：客戶別名、模組、產品代號、時間。"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

import pandas as pd

# 全形 → 半形 對照 (別名比對用)
_FULL2HALF = str.maketrans({
    "｜": "|", "：": ":", "＝": "=", "　": " ",
})


def text(v) -> str:
    """安全轉文字並去頭尾空白；NaN/None → ''。保留前導 0（呼叫端請以字串讀入）。"""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    # 避免數字型別變成 '123.0' 或科學記號
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def product_id(v) -> str:
    """產品代號轉文字，保留前導 0，排除科學記號/小數。"""
    s = text(v)
    if "e" in s.lower() or "E" in s:
        try:
            s = format(int(float(s)), "d")
        except (ValueError, OverflowError):
            pass
    return s


def norm_key(s: str) -> str:
    """別名/代碼比對用：去空白、轉半形、大寫。"""
    return text(s).translate(_FULL2HALF).replace(" ", "").upper()


def norm_module(m: str) -> str:
    """模組正規化：DUG 家族（DUG_白 等）一律視為 DUG；其餘原樣。"""
    s = text(m)
    if not s:
        return ""
    if s.upper().startswith("DUG"):
        return "DUG"
    return s


def norm_group(g: str) -> str:
    """產品群組比對用（大小寫不敏感）。"""
    return text(g).upper()


def parse_time(v) -> Optional[time]:
    """支援 datetime.time / Timestamp / 字串 'H:MM' / 'HH:MM'。"""
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "hour") and hasattr(v, "minute"):
        return time(int(v.hour), int(v.minute))
    s = text(v)
    if not s:
        return None
    for fmt in ("%H:%M:%S", "%H:%M", "%H.%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def parse_date(v) -> Optional[date]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()
