# UI 與設定功能分層

`ui/dashboard` 是共用視窗框架，`ui/settings` 是設定畫面。
設定草稿、驗證、儲存與背景連線測試全部位於 `app/settings`。

| 路徑 | 責任 |
| --- | --- |
| `ui/dashboard/dashboard_window.py` | 視窗尺寸、內容容器、頁面切換、側欄收合、附加頁尾 |
| `ui/dashboard/page_registry.py` | 通用 `PageDefinition` 資料結構 |
| `ui/dashboard/sidebar.py`、`styles.py` | 導覽列及框架樣式 |
| `ui/settings/settings_window.py` | 組裝畫面、轉送輸入與按鈕事件、顯示結果與確認對話框 |
| `ui/settings/page_registry.py`、`pages/` | 設定頁面的順序、呈現與原始輸入值 |
| `ui/settings/widgets/` | 輸入元件、數字輸入、API 群組表單、版面切換 |
| `ui/settings/dialogs.py`、`styles.py` | 對話框與設定畫面樣式 |
| `app/settings/presenter.py` | 串接操作事件、決定套用／取消／關閉流程、處理結果與錯誤 |
| `app/settings/session.py` | 設定草稿與原始快照、變更判斷、重新載入、套用、還原及遷移預覽 |
| `app/settings/editing.py` | 金鑰與群組輸入整理、預設值、URL 驗證及環境來源狀態 |
| `app/settings/connection_test_controller.py` | 連線測試排程、同時執行上限、過期結果與生命週期 |
| `app/contracts/settings.py` | 畫面與應用層交換的純資料與操作結果；新群組輸入／顯示契約將於第三階段接入正式流程 |
| `app/presentation/settings/view_port.py` | Presenter 使用的公開 View 介面，不匯入具體視窗 |
| `app/settings/service.py`、`api_group_service.py` | 設定驗證與儲存服務，委由 `app/core/config_manager.py` 讀寫檔案 |

`app/core/window_manager.py` 是組裝入口：收到 `show_settings` 事件後，建立
`SettingsWindow` 和 `SettingsPresenter`，後者使用 `SettingsSession` 管理設定。
重新喚回已顯示的視窗會保留草稿；重新開啟已關閉的視窗由 presenter 重新載入資料。

直接建立 `SettingsWindow()` 只建立畫面，不讀取設定檔，也不會儲存。
畫面透過 signals 發出操作請求，presenter 透過畫面方法送回資料、提示或關閉結果。
UI 只匯入應用層的資料契約，不匯入設定服務；應用層設定模組不匯入 `ui` 或
`QtWidgets`，也不查找輸入元件。`app.settings` 的服務採延遲匯入，避免單純使用
資料契約就初始化設定讀寫服務。

API 群組表單與金鑰列表回傳的是原始輸入。空白列過濾、名稱補值、金鑰來源整理、
環境變數讀取、URL 與群組有效性判斷由應用層負責。畫面只依結果呈現狀態。
人格選項也由 presenter 提供；捲動、焦點、遮蔽金鑰及響應式版面仍屬 UI 行為。

框架測試位於 `tests/test_dashboard_shell.py`；設定頁面及整合測試位於
`tests/test_settings_*.py`。`test_settings_session.py` 與 `test_settings_workflow.py`
不需實際視窗即可測試設定操作，`test_settings_architecture.py` 以獨立程序驗證分層。

## 三層重構進度（2026-10-15）

第一、第二階段已完成：建立行為基準、純資料契約與元件公開入口。
`SettingsWindow.connection_inputs()` 透過 `AIPage.connection_inputs()` 取得資料；
頁面向編輯器取得 `GroupTestInputs`，不跨元件讀取列字典。父頁面透過
`set_available_width()` 提供排版寬度。

`APIGroupEditor.collect_input()` 提供不含儲存版本與環境變數名稱的原始輸入。
目前正式變更訊號仍使用舊 `collect_settings()`；上文「畫面只回傳原始輸入、
環境讀取由應用層負責」是目標邊界，API 編輯器尚有環境金鑰讀取與保存轉換，
第三階段才會移出。一般頁面仍接收原有 `SettingsSnapshot`。

Presenter／Controller／worker 的搬移與拆分安排在第四階段。
舊 `app/settings/view_contracts.py` 暫時保留同一組類別的相容匯出，第六階段清理。
新增視窗應使用獨立 Presenter／Session、共享服務，並遵守公開介面；
不向 Dashboard 加入保存規則，也不直接操作其他視窗的元件。
