"""簡易設定檔 (記住上次用的 Excel 路徑等)，存成 settings.json。"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

SETTINGS_FILENAME = "settings.json"


def _path() -> str:
    return os.path.join(os.getcwd(), SETTINGS_FILENAME)


def load() -> dict[str, Any]:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save(data: dict[str, Any]) -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def set_value(key: str, value: Any) -> None:
    d = load()
    d[key] = value
    save(d)


def get_value(key: str, default: Optional[Any] = None) -> Any:
    return load().get(key, default)
