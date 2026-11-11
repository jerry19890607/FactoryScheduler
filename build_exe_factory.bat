@echo off
REM ============================================================
REM  FactoryScheduler Windows 打包腳本
REM  產出 3 支 exe 到 dist\：
REM    FactoryScheduler.exe          單一檔，啟動時選角色
REM    FactoryScheduler_管理員.exe    直接開管理員（每機台時序）
REM    FactoryScheduler_操作員.exe    直接開操作員（掃描回報）
REM  需先安裝 requirements.txt（含 pyinstaller / pandas / openpyxl / xlrd / PySide6）
REM ============================================================
chcp 65001 >nul
echo [1/4] 清除舊的 build / dist ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 貪婪排程不需 ortools；需帶齊 PySide6 與 Excel 讀寫相依
set COMMON=--noconfirm --onefile --windowed --collect-submodules PySide6 --collect-all openpyxl --hidden-import xlrd

echo [2/4] 打包：單一檔（啟動選角色）...
pyinstaller %COMMON% --name FactoryScheduler run_factory_gui.py

echo [3/4] 打包：管理員 ...
pyinstaller %COMMON% --name FactoryScheduler_管理員 main_factory_admin.py

echo [4/4] 打包：操作員 ...
pyinstaller %COMMON% --name FactoryScheduler_操作員 main_factory_operator.py

echo.
echo 完成！dist\ 下有三支 exe。部署建議：
echo   A) 只發「FactoryScheduler.exe」，每次啟動選角色
echo   B) 分別發「FactoryScheduler_管理員.exe」「FactoryScheduler_操作員.exe」
echo   C) 只用「FactoryScheduler.exe」，建兩個捷徑分別加 --role admin / --role operator
echo 註：三支共用同一資料夾下的 factory_state.db（單機共享狀態）。
pause
