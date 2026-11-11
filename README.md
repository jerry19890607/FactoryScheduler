# FactoryScheduler — 工單自動排程系統

把每天來自不同系統（Legacy / APS）的工單，依機台能力與交期自動排到各機台的時序表；
支援抽件（Pull）優先、Machine_Calendar 停機避讓、管理員調整與操作員掃碼回報。
目標部署：Windows 封閉網路，交付為 `.exe` + GUI。

---

## 目錄結構

```
thales/
├── app/                         # 現行程式（唯一正式使用）
│   ├── config.py, settings.py   # 共用常數 / 設定
│   ├── factory/                 # 排程引擎 + 服務層 + 狀態庫
│   │   ├── normalize.py types.py masterdata.py   # 正規化 / 資料模型 / 主檔
│   │   ├── orders.py deadlines.py pulls.py        # 訂單轉譯 / 交期 / 抽件
│   │   ├── scheduler.py output.py barcode.py      # 時間軸排程 / 介面輸出 / 條碼
│   │   ├── ledger.py            # 抽件匯入去重台帳
│   │   ├── fservice.py fstore.py # GUI 服務層 / SQLite 狀態庫
│   └── ui/                      # role_dialog + factory_admin_window + factory_operator_window
├── FactoryScheduler/            # 執行資料
│   ├── Schema/   主檔（Factory_Scheduling_Schema_V4_3.2.xlsx）
│   ├── Orders/   日常訂單（Legacy .xls/.txt、APS .xlsx）
│   ├── Pulls/    抽件（.txt / .xls）
│   ├── Logs/     抽件去重台帳 pull_imported.json
│   └── Output/   排程結果_介面format.xlsx
├── docs/                        # 文件：說明.txt、介面 format.xlsx、進度/邏輯說明(HTML/MD)
├── run_factory.py               # CLI 全流程（無 GUI，除錯/批次用）
├── run_factory_gui.py           # GUI 啟動（選角色）
├── main_factory_admin.py / main_factory_operator.py   # 直接開管理員 / 操作員（供打包）
├── build_exe_factory.bat        # Windows 打包三支 exe
├── requirements.txt
├── factory_state.db             # 執行時狀態（可刪，會重建）
├── legacy_prototype/            # 封存：第一版雛形（已停用，僅參考）
└── archive_data/                # 封存：舊版主檔 / OEE 樣本 / zip 備份
```

---

## 在 Linux 用 venv 執行（開發 / 除錯）

```bash
cd /HDD/tools/git/thales
source .venv/bin/activate        # 或直接用 .venv/bin/python

# CLI 全流程
python run_factory.py \
  --master FactoryScheduler/Schema/Factory_Scheduling_Schema_V4_3.2.xlsx \
  --orders FactoryScheduler/Orders/Schedule_Legacy_20261106_1215.xls \
           FactoryScheduler/Orders/Schedule_APS_20261106_1210.xlsx \
  --pulls  FactoryScheduler/Pulls/Legacy_Pull_20261106_1100-2.txt \
  --horizon "2026-11-09 08:30"

# GUI（選角色 / 指定角色）
QT_QPA_PLATFORM=xcb python run_factory_gui.py
QT_QPA_PLATFORM=xcb python run_factory_gui.py --role admin
QT_QPA_PLATFORM=xcb python run_factory_gui.py --role operator
```

管理員與操作員共用同資料夾的 `factory_state.db`（單機共享狀態）。

### 重置狀態
```bash
pkill -f run_factory_gui                                          # 先關所有 GUI
rm -f factory_state.db FactoryScheduler/Logs/pull_imported.json   # 再砍狀態 + 抽件台帳
```
> 一定要先關視窗再砍，否則執行中的行程會把檔案寫回。

---

## Windows 封閉網路部署

1. 連網機器：`pip download -r requirements.txt -d wheels`
2. 封閉機器：`pip install --no-index --find-links wheels -r requirements.txt`
3. 打包：執行 `build_exe_factory.bat` → `dist\` 產出三支 exe：
   - `FactoryScheduler.exe`（啟動選角色）
   - `FactoryScheduler_管理員.exe`、`FactoryScheduler_操作員.exe`

---

## 流程摘要

主檔 → 訂單四段轉譯（客戶別名→產品代號→替代版面→群組/模組→合格機台）
→ 交期（最早開始 / 最晚完成，含 SLA_REF）→ 抽件（單一筆、整包一列顯示各等級量、優先+收緊交期）
→ 時間軸貪婪排程（避開停機、凍結已開工/鎖定）→ 介面格式輸出。

詳細邏輯見 `docs/輸入輸出與運算邏輯.html`，進度見 `docs/專案進度說明.html`。
