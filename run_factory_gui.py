"""FactoryScheduler GUI 進入點。

角色判定優先序：參數 > 對話框
  1. 無參數           → 跳「選擇角色」對話框
  2. --role admin     → 管理員（每機台時序）
  3. --role operator  → 操作員（掃描回報）

共用本機 SQLite 狀態庫（預設 factory_state.db），單機切換角色即可共享。
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from app import config


def run(role: Optional[str] = None) -> int:
    from PySide6.QtWidgets import QApplication, QDialog

    from app.ui.role_dialog import RoleDialog
    from app.ui.factory_admin_window import FactoryAdminWindow
    from app.ui.factory_operator_window import FactoryOperatorWindow

    app = QApplication(sys.argv)

    if role not in (config.ROLE_ADMIN, config.ROLE_OPERATOR):
        dlg = RoleDialog()
        if dlg.exec() != QDialog.Accepted or not dlg.role:
            return 0
        role = dlg.role

    win = (FactoryAdminWindow() if role == config.ROLE_ADMIN
           else FactoryOperatorWindow())
    win.show()
    return app.exec()


def _parse_role(argv: list[str]) -> Optional[str]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=[config.ROLE_ADMIN, config.ROLE_OPERATOR])
    args, _ = ap.parse_known_args(argv)
    return args.role


if __name__ == "__main__":
    sys.exit(run(_parse_role(sys.argv[1:])))
