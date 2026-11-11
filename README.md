# FactoryScheduler — 工單自動排程系統

把每天來自不同系統（Legacy / APS）的工單，依**機台能力**與**交期**自動排到各機台的時序表；
支援**抽件（Pull）優先**、**停機時段避讓**、**管理員調整**與**操作員掃碼回報**。

- 目標部署：**Windows 封閉網路**，交付為 `.exe` + GUI。
- 目前範圍：只排**製程 1（機台）**。
- 狀態：**初版**（引擎 + GUI 已完成，單機共享狀態）。

---

## 角色

| 角色 | 做什麼 | 進入點 |
|---|---|---|
| **Leader（管理員）** | 載入當天資料、檢視/調整各機台時序、匯出 | `FactoryScheduler_管理員.exe` |
| **Operator（操作員）** | 掃工單條碼、回報處理中 / 已完成 | `FactoryScheduler_操作員.exe` |
| **Maintainer（維運）** | 安裝、打包、部署、排錯、擴充 | — |

---

## 文件（docs/）

| 文件 | 對象 | 格式 |
|---|---|---|
| [維運指南](docs/Guide_1_Maintainer.md) | Maintainer | `.md` / `.pdf` |
| [管理員指南](docs/Guide_2_Leader.md) | Leader | `.md` / `.pdf` |
| [操作員指南](docs/Guide_3_Operator.md) | Operator | `.md` / `.pdf` |
| 專案進度說明 | 給委託方看成果 | `.html` / `.pdf` |
| 輸入輸出與運算邏輯 | 技術說明 | `.html` / `.pdf` |
| 說明.txt、介面 format.xlsx | 原始規格 | — |

---

## 目錄結構

```
thales/
├── app/                         # 現行程式
│   ├── config.py, settings.py
│   ├── factory/                 # 引擎 + 服務層 + 狀態庫
│   │   ├── normalize / types / masterdata        # 正規化 / 模型 / 主檔
│   │   ├── orders / deadlines / pulls            # 訂單轉譯 / 交期 / 抽件
│   │   ├── scheduler / output / barcode / ledger # 排程 / 輸出 / 條碼 / 去重
│   │   └── fservice / fstore                     # GUI 服務層 / SQLite 狀態庫
│   └── ui/                      # role_dialog + factory_admin/operator_window
├── FactoryScheduler/            # 執行資料
│   ├── Schema/  Orders/  Pulls/  Logs/  Output/
├── docs/                        # 指南 + 說明 + 規格（md / html / pdf）
├── run_factory.py               # CLI 全流程（除錯/批次）
├── run_factory_gui.py           # GUI（選角色）
├── main_factory_admin.py / main_factory_operator.py
├── build_exe_factory.bat        # 打包三支 exe
├── requirements.txt
├── factory_state.db             # 執行時狀態（可刪，會重建）
└── .venv/                       # 開發用虛擬環境（不隨程式交付）
```

---

## 快速開始（Linux / venv，開發與除錯）

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

> Linux 跑 GUI 需 X11，且 Qt6 需 `libxcb-cursor0`（`sudo apt install libxcb-cursor0`）。
> 正式交付是 Windows exe，無此前置需求。

### 重置狀態
```bash
pkill -f run_factory_gui                                          # 先關所有 GUI
rm -f factory_state.db FactoryScheduler/Logs/pull_imported.json   # 再砍狀態 + 抽件台帳
```
務必先關視窗再砍，否則執行中的行程會把檔案寫回。

---

## Windows 封閉網路部署

1. 連網機器：`pip download -r requirements.txt -d wheels`
2. 封閉機器：`pip install --no-index --find-links wheels -r requirements.txt`
3. 打包：執行 `build_exe_factory.bat` → `dist\` 產出三支 exe
   （單一檔選角色 / 管理員 / 操作員）。
4. 三支 exe 放同資料夾，共用 `factory_state.db`（單機共享狀態）。

---

## 流程摘要

主檔 → 訂單四段轉譯（客戶別名 → 產品代號 → 替代版面 → 群組/模組 → 合格機台）
→ 交期（最早開始 / 最晚完成，含 SLA_REF）→ 抽件（單一筆、整包一列顯示各等級量、優先 + 收緊交期）
→ 時間軸貪婪排程（避開停機、凍結已開工/鎖定）→ 介面格式輸出。

完整邏輯見 [`docs/輸入輸出與運算邏輯`](docs/輸入輸出與運算邏輯.html)，進度見 [`docs/專案進度說明`](docs/專案進度說明.html)。

---

## 初版限制

- 只排製程 1；Insert / Manual 階段未納入。
- 管理員「重新排程」為手動按鈕（操作員狀態變更只刷新顯示，不自動重排）。
- `FactoryScheduler.ini` 的資料夾監控 / 定時觸發尚未接入（目前手動選檔）。
- 排程用貪婪演算法；如需最佳化可改 CP-SAT（OR-Tools）。
- 待確認：訂單 `SLA_REF=D01` 是否應補進主檔 SLA_REF 清單（目前退回 SLA Std）。
