# Dashboard 與設定功能三層架構

`ui/dashboard` 提供共用視窗框架；`ui/settings` 呈現設定頁面。
操作協調位於 `app/presentation/settings`，資料規則與儲存位於 `app/settings`。

| 層級／路徑 | 責任 |
| --- | --- |
| `ui/dashboard/` | 視窗尺寸、導覽、側欄收合、內容容器與頁尾 |
| `ui/settings/settings_window.py` | 組裝頁面、轉送事件、顯示狀態及確認對話框 |
| `ui/settings/pages/`、`widgets/` | 呈現資料、收集原始輸入、管理焦點／捲動／遮蔽／版面 |
| `app/contracts/settings.py` | UI 與應用層共用的純資料契約，不含 Qt、schema 或檔案位置 |
| `app/presentation/settings/view_port.py` | Presenter 使用的 View 公開介面 |
| `app/presentation/settings/presenter.py` | 協調套用、取消、關閉、測試與重新載入 |
| `app/presentation/settings/connection_test_controller.py` | Qt 工作排程、四個未完成測試上限、過期結果與生命週期 |
| `app/presentation/settings/connection_test_worker.py` | 包裝單次測試服務並以 Qt signal 回傳結果 |
| `app/settings/session.py` | 每個編輯工作階段的草稿、原始快照與畫面載入基準 |
| `app/settings/display.py` | 從邏輯狀態準備顯示資料，解析可顯示的已保存金鑰 |
| `app/settings/editing.py` | 輸入轉換、名稱補值、來源切換、金鑰保留／更換及驗證回饋 |
| `app/settings/connection_test.py` | 測試請求準備、單次連線、結果安全化，不含 Qt worker |
| `app/settings/service.py`、`api_group_service.py` | 驗證與保存，沿用既有 config manager 與環境變數儲存支援 |

`app/core/window_manager.py` 是組裝入口：收到 `show_settings` 事件後建立
`SettingsWindow` 與 `SettingsPresenter`。已顯示的視窗重新喚回時保留草稿；
已關閉的視窗重新開啟時由 Presenter 載入資料。

直接建立 `SettingsWindow()` 只建立畫面，不載入設定服務或儲存資料。
UI 只匯入 `app/contracts` 的資料契約。Presenter 透過 View 公開方法操作畫面，
邏輯層不匯入 UI、串接層或 QtWidgets；既有事件匯流排等基礎設施仍可使用 QtCore。

群組資料流：

1. Session 以 `display_groups()` 記錄本次畫面載入基準，產生 `APIGroupsDisplay`。
2. 編輯器發出 `APIGroupsInput`，包含原始欄位與是否不同於初始顯示值。
3. Presenter 將輸入交給 Session；`groups_from_input()` 按載入基準判斷來源與保存規則。
4. Session 正規化草稿，Presenter 將狀態與驗證回饋送回畫面。
5. 套用成功後重新建立基準與顯示資料。

載入基準與已正規化的草稿分開，避免空白列被忽略或來源連續切換後，遺失原始引用。
新增群組／Key 的 ID 與預設值由邏輯層提供。金鑰解析、空白保留及儲存版本不進入 UI；
顯示／遮蔽按鈕仍屬 UI 責任。所有顯示／輸入契約的金鑰欄位排除於預設 repr。

`SettingsWindow.connection_inputs()` 透過 AI 頁公開方法取得連線輸入；
AI 頁再向編輯器取得 `GroupTestInputs`，不跨元件讀取列字典。
父頁面使用 `set_available_width()` 傳入可用排版寬度。

連線測試服務可同步呼叫，不需要 QApplication。Qt Controller 只排程與協調結果；
指定 Key、免金鑰、來源解析及快照準備在服務中處理。關閉或重新載入會使舊結果失效，
但未結束工作仍計入並行上限。worker 結束時清除自己持有的金鑰。

新增視窗應建立自己的 Presenter／Session，透過共享服務使用功能；
不向 Dashboard 加入保存規則，也不直接操作其他視窗的元件。
新增第二個設定寫入入口前，仍須依根目錄計畫實作保存衝突檢查。

## 驗證與進度

六個階段已完成（2026-10-16）。收尾複查後完整測試套件 444 項通過；
17 個設定測試檔各自在獨立程序執行通過，182 項設定測試以反向順序執行也通過。
分層測試配合新匯入更新，UI 的應用層依賴只允許 `app.contracts`。
`tests/test_settings_display.py`、`test_settings_editing.py` 驗證顯示與輸入規則；
`test_settings_connection_test.py` 驗證無 Qt 的單次服務與 worker 包裝。
`test_settings_workflow.py` 使用假 View 驗證流程，其餘 UI／資料測試維持既有行為驗證。

`tests/settings_boundaries.py` 提供 AST 架構檢查，搭配
`test_settings_boundaries.py` 掃描 Dashboard、設定 UI、契約、邏輯、串接及組裝入口。
檢查涵蓋匯入別名、相對匯入、常見檔案／環境／網路操作與公開 View 介面；
組裝例外限於 `WindowManager.show_settings()` 對串接層的匯入。
測試也刻意輸入越界程式片段，驗證檢查確實會拒絕它們。
一般別名按來源順序與函式作用域解析，避免其他函式的同名變數造成漏報或誤報；
組裝例外也不延伸至入口內的巢狀函式。
這是防止一般開發回歸的架構規則，不是阻擋任意動態 Python 的安全沙箱。
檢查不模擬分支合併或完整 Python 執行語義。

雙 Session／假 View 測試驗證共享服務時草稿互不污染，關閉其中一個視窗後，
另一個視窗仍能收到自己的背景結果；保存衝突控制仍屬新增第二個寫入入口前的後續需求。

視覺驗收使用假資料的離屏 Qt 視窗，模擬點擊、鍵盤與滾輪後檢查截圖，
涵蓋 900×650 與 650×600 版面、各頁、金鑰顯示／遮蔽、測試結果、套用／取消／重開。
此方式未驗證 Windows 原生桌面上的 DPI、視窗管理或不同螢幕配置。

舊契約重匯出與未使用的測試結果契約已移除；
舊 Presenter／Controller 檔案已搬移，沒有保留雙份實作。
