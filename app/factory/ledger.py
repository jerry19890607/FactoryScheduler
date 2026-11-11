"""抽件匯入台帳：記住已匯入過的抽件（以 (ID, FILE_NAME) 為鍵）。

抽件檔會持續疊加，同一列可能在多次匯入時重複出現；用這份台帳跨次比對，
已匯入過的就略過，避免重複套用。
"""
from __future__ import annotations

import json
import os


def load_seen(path: str | None) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_seen(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=0)
