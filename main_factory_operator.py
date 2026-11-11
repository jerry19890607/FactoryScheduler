"""FactoryScheduler 操作員 exe 進入點（直接開操作員視窗）。"""
from __future__ import annotations

import sys

from app import config
from run_factory_gui import run

if __name__ == "__main__":
    sys.exit(run(config.ROLE_OPERATOR))
