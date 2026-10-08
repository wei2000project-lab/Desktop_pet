# Nova 資料讀寫清單（第一階段）

日期：2026-10-08。此清單記錄目前行為；本階段尚未搬移資料或改變檔案格式。路徑定義集中於 `app/core/paths.py` 的 `ProjectPaths`，預設執行路徑仍在專案內。

| 資料 | 分類 | 主要讀取者 | 主要寫入者與時機 | 目前位置 |
| --- | --- | --- | --- | --- |
| 預設一般設定 | 隨程式提供、唯讀 | `ConfigManager` | 開發者更新版本時提交 | `data/config/app.defaults.ini` |
| 預設人格 | 隨程式提供、唯讀 | `ConfigManager` | 開發者更新版本時提交 | `data/config/prompt.json` |
| App 別名 | 隨程式提供、唯讀 | `app.control.resolution.aliases` | 開發者更新版本時提交 | `data/app_control/aliases.json` |
| 一般設定 | 使用者設定 | `ConfigManager` | 設定套用；寵物移動或尺寸變更 | `data/runtime/app.ini` |
| 人格覆寫 | 使用者設定 | `ConfigManager` | 設定套用 | `data/runtime/prompt.json` |
| API 群組 | 使用者設定、含明文秘密 | `APIGroupService` → `ConfigManager` | 群組套用；首次舊版 API 遷移 | `data/runtime/api_groups.json` |
| 舊版 API 設定 | 舊版設定、含明文秘密 | `ConfigManager`；`APIGroupService` 遷移 | 舊版設定保存路徑；群組模式不改寫 | `data/runtime/api.ini` |
| 工具設定 | 使用者設定、含明文秘密 | `SettingsService`、`WebToolService` → `ConfigManager` | 設定套用 | `data/runtime/tools.json` |
| 對話歷史 | 私人持久狀態 | `ConversationManager` → `ConfigManager` | 回覆完成；使用者清除歷史 | `data/runtime/history.json` |
| 長期記憶 | 私人持久狀態 | `ConversationManager` → `ConfigManager` | `ConfigManager.save_memory` | `data/runtime/memory.json` |
| App 偏好 | 使用者持久狀態 | `AppPreferenceStore` | 使用者選定偏好 | `data/runtime/preferences.json` |
| App 索引 | 可重建快取 | `AppIndex`、`AppOpenService` | 啟動背景掃描；索引缺失時重掃 | `data/runtime/apps.json` |
| 程式日誌 | 診斷資料 | 開發者或使用者 | logger 執行時寫入與輪替 | `logs/app.log` |
| `.env` | 舊版環境輸入、可能含秘密 | `ConfigManager.load_env` | 程式不寫入 | 專案根目錄 `.env` |

`ConfigManager` 初始化時會把舊 `config/` 中的 `api.ini`、`config.ini`、`apps.json`、`app_preferences.json`、`history.json`、`memory.json`、`prompt.json` 複製至 `data/runtime/` 中對應路徑。它不覆寫已存在的目的檔，也不刪除來源。新目錄中的 `api_groups.json` 與 `tools.json` 是較新的格式，沒有這條舊目錄複製規則。

## 目前讀寫契約與第二階段切換點

- `ProjectPaths` 只計算路徑，不建立目錄、不讀檔、不寫檔；測試可注入專案根目錄與 runtime 根目錄。
- 靜態預設資料只讀；使用者設定在讀取時疊加預設值，保存時只寫 runtime。API 群組與工具設定以獨立檔案讀寫；`tools.json` 現在有明確路徑，不再由 `app.ini` 名稱推算。
- App 索引屬快取，可重掃；偏好、歷史、記憶與設定屬持久資料，後續遷移不可因檔案損毀而用空資料覆蓋。
- 第二階段修改預設 runtime 根目錄之前，需以此清單逐一替換讀寫者，並保留讀取舊 `data/runtime/` 以供一次性遷移。這一階段的實作未改變任何現有檔案位置或格式。

後續位置、格式與金鑰遷移方案見 `docs/data-storage-reorganization-plan-2026-10-08.md`。
