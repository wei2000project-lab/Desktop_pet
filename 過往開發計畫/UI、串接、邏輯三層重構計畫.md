# Dashboard 與設定功能：UI、串接、邏輯三層重構計畫

建立日期：2026-10-15  
狀態：六個階段已完成（2026-10-16）；最終介面驗收採離屏互動與截圖檢查，限制見第 13 節。
2026-10-15 依使用者「先本地提交，一次做兩步驟」指示開始實作，結果記錄於第 11 節。

## 1. 目標與範圍

將目前 Dashboard 與設定功能的責任明確分成 UI、串接、邏輯三層，讓未來新增不同視窗時，可以共用功能服務，而不必複製資料規則或直接操作其他視窗的元件。

本次重構範圍：

- Dashboard 共用框架及其承載的設定視窗。
- 設定頁面、API 群組編輯器、設定操作協調、設定草稿與連線測試。
- 設定視窗的建立入口、資料契約、相關測試與分層文件。

不納入本次範圍：

- Tavily 遺留內容及相關問題。
- 桌寵、聊天氣泡、動畫、應用程式控制的全面重構。
- 新增功能視窗、修改視覺設計、移除舊 API 設定相容功能。
- 改變現有設定檔格式、資料目錄、金鑰儲存位置或正式 AI 請求策略。
- 未經使用者指示提交、合併、推送或搬動過往計畫文件。本次使用者已授權先做本地提交，未授權推送。

既有非本次修改，例如 `tree.txt` 與其他文件的移動，應保持原狀。

## 2. 現況與需要修正的邊界

目前已有可沿用的基礎：

- `ui/dashboard` 只負責導覽、內容容器與視窗版面，沒有直接讀取設定或呼叫 API。
- `SettingsPresenter` 協調畫面操作，`SettingsSession` 管理草稿，`SettingsService` 負責驗證與保存。
- `ConnectionTestController` 已管理背景測試與過期結果，應保留這些行為。

目前需要調整的地方：

1. `APIGroupEditor.add_key()` 直接讀取 `os.environ`，讓 UI 承擔金鑰來源解析。
2. `APIGroupEditor.collect_settings()` 依 schema、原始來源與金鑰比較結果決定保存內容，超出原始輸入收集的責任。
3. UI 直接使用 `APIGroupSettings` 等含儲存版本的模型，畫面與儲存格式綁定。
4. `SettingsWindow.connection_inputs()` 直接讀取子元件的 `group_rows` 與金鑰列結構。
5. `AIPage.resizeEvent()` 呼叫子元件的私有排版方法。
6. Presenter、Qt 背景工作與資料規則都在 `app/settings`，目錄未明確表達串接層的角色。
7. 現有分層測試主要檢查匯入，未涵蓋 UI 讀取環境變數或處理保存語義。

前次檢視已執行 Dashboard 框架 10 項、設定架構 3 項測試，全部通過。這只代表該次局部驗證結果；正式實作前仍須建立當時版本的基準。

## 3. 三層責任與依賴規則

| 層級 | 責任 | 不應負責 |
| --- | --- | --- |
| UI | 版面、元件、焦點、捲動、頁面切換、顯示與遮蔽、收集原始輸入、發出操作事件 | 環境變數讀取、設定檔讀寫、API 呼叫、資料遷移、金鑰保存規則 |
| 串接 | 接收 UI 事件、協調使用流程、呼叫邏輯服務、轉交顯示資料、管理 Qt 工作排程與視窗生命週期 | 自行實作驗證與保存規則、深入查找子元件、直接處理 HTTP 或設定檔 |
| 邏輯 | 草稿、變更判斷、驗證、來源解析、保存、測試請求準備與執行、結果安全化 | 依賴具體視窗、建立 QWidget、操作按鈕或對話框 |

依賴規則：

- UI 僅依賴 Qt、其他 UI 元件與純資料契約。
- 串接層依賴邏輯服務與抽象 View 介面，不匯入具體 UI 類別。
- 邏輯層不匯入 `ui` 或串接層，也不使用 `QtWidgets`。
- 純資料契約不匯入 UI、串接、服務、設定單例或 Qt。
- 組裝入口可以同時知道具體 UI 與串接物件，以建立並連接兩者；這是明確的組裝例外。
- 現有 `event_bus`、設定管理器等基礎設施暫不全面重構。邏輯不得新增對視窗生命週期或 QWidget 的依賴；本計畫不宣稱消除整個專案的 Qt 依賴。

典型操作流程：

```text
使用者操作
  → UI 發出帶有識別碼與原始輸入的事件
  → Presenter 協調操作
  → Session／Service 執行規則與資料操作
  → 回傳結果及顯示資料
  → Presenter 呼叫 View 公開方法
  → UI 更新畫面
```

畫面邏輯仍留在 UI。例如側欄收合、金鑰遮蔽、啟用輸入欄位、響應式排版，不需要搬到邏輯層。

## 4. 目標目錄

採用增量調整，保留既有 `ui` 與 `app/settings`，新增具體的串接層。純資料契約是共用邊界，不另形成第四個執行層。

```text
ui/
  dashboard/                       # 通用視窗框架
  settings/                        # 設定畫面與輸入元件

app/
  contracts/
    __init__.py
    settings.py                    # 畫面輸入、顯示資料、結果等純資料契約
  presentation/
    __init__.py
    settings/
      __init__.py
      presenter.py                 # 由原 SettingsPresenter 搬入
      view_port.py                 # View 公開介面的型別契約
      connection_test_controller.py # Qt 排程、回呼與結果生命週期
      connection_test_worker.py     # Qt worker 包裝
  settings/
    session.py                     # 每個編輯視窗各自持有的草稿
    service.py                     # 驗證與保存
    editing.py                     # 輸入轉換、來源切換與編輯規則
    display.py                     # 將邏輯狀態轉成顯示資料
    connection_test.py             # 不依賴 Qt worker 的單次測試服務
    ...                            # 保留既有 API 模型、解析與儲存支援
  core/
    window_manager.py              # 保留現有組裝入口
```

不建立所有視窗共用的巨型 Presenter，也不要求所有未來視窗繼承 Dashboard。只有需要共用導覽框架的視窗才使用 `DashboardWindow`。

## 5. 資料與介面設計

### 5.1 畫面輸入與儲存模型分離

- UI 使用專用的輸入與顯示資料，不再直接建構含 schema 版本的 `APIGroupSettings`。
- 穩定的群組 ID、金鑰 ID 與原始欄位輸入可以跨層傳遞；schema、環境變數映射與保存規則留在邏輯層。
- UI 可以表示「使用者編輯過此欄位」或「刪除此列」等互動事實；邏輯層決定這代表保留、更換、清除或移除資料。
- 未變更金鑰、空白輸入、來源切換、刪除 Key 的既有行為必須先以測試記錄，再保持相容。不得藉重構新增清除按鈕或更改空白輸入語義。
- 金鑰顯示值由邏輯服務透過顯示契約提供。保留目前可顯示／遮蔽已保存金鑰的行為，但 UI 不自行讀取環境變數。
- 顯示用秘密欄位不出現在資料物件的預設 repr、日誌或測試失敗快照中；測試使用假值。
- 保留目前溫度顯示精度與未編輯時保留原始精度的行為，避免 UI 重建造成非預期資料變更。

### 5.2 View 公開介面

由 `view_port.py` 描述 Presenter 所需的事件與方法，例如載入顯示資料、提交尚未完成的輸入、顯示測試結果、取得關閉選擇。

- Presenter 不讀取 `group_rows`、`api_key_rows`、`QLineEdit` 或其他元件。
- `SettingsWindow` 呼叫子元件的公開資料收集方法，不拼裝其內部列字典。
- API 編輯器提供公開的測試目標資料與版面寬度入口，或自行管理尺寸事件；不得再從外部呼叫私有排版方法。
- 對話框由 UI 顯示，回傳選擇值；Presenter 依選擇決定繼續、取消或保存。
- 邏輯服務回傳結果，不主動彈出對話框。

### 5.3 背景測試與生命週期

- 單次連線測試服務負責執行請求與安全化結果。
- Qt worker 只包裝服務執行與 signal 回傳。
- Controller 負責工作排程、最多四個未完成測試、重複請求控制及畫面生命週期。
- 指定金鑰、免金鑰、停用金鑰手動測試、請求快照與一致性比較由邏輯層提供，不由 UI 或 Controller 重寫規則。
- 修改、刪除、關閉、重開或重建畫面後，舊結果不得覆蓋新狀態。
- 畫面關閉時失效的工作，尚未結束前仍須計入既有並行上限，不因移動程式而提前解除計數。

## 6. 檔案調整清單

### 6.1 必要新增、搬移與修改

| 現有／新增檔案 | 調整方式與責任 |
| --- | --- |
| `app/contracts/__init__.py`、`app/contracts/settings.py`（新增） | 純資料邊界；承接關閉選擇、測試目標，新增 UI 輸入與顯示契約，避免匯入服務時的副作用 |
| `app/presentation/__init__.py`、`app/presentation/settings/__init__.py`（新增） | 建立串接層套件；避免匯入套件就建立服務或視窗 |
| `app/settings/presenter.py` → `app/presentation/settings/presenter.py` | 搬移操作協調；改用專用契約與公開 View 介面；維持套用、取消、關閉與重開流程 |
| `app/presentation/settings/view_port.py`（新增） | 描述串接層所需的 View 介面，不依賴具體視窗 |
| `app/settings/connection_test_controller.py` → `app/presentation/settings/connection_test_controller.py` | 保留 Qt 排程與生命週期，將群組解析及測試輸入規則交給邏輯服務 |
| `app/presentation/settings/connection_test_worker.py`（新增） | 接收原 `ConnectionTestWorker`／signals 的 Qt 包裝職責 |
| `app/settings/connection_test.py` | 保留並整理單次測試執行、安全錯誤結果、測試請求準備；移出 QObject／QRunnable 包裝 |
| `app/settings/view_contracts.py` → `app/contracts/settings.py` | 整合純資料定義，更新所有引用；過渡匯出只在遷移期間存在，收尾移除 |
| `app/settings/display.py`（新增） | 從設定草稿產生畫面資料、金鑰顯示值及狀態資訊；不處理 Qt 排版 |
| `app/settings/editing.py` | 集中原始輸入轉換、金鑰保留／更換規則、來源切換與變更比較，避免與 UI 重複 |
| `app/settings/session.py` | 接收新輸入契約，管理原始快照、草稿及變更狀態；不依賴畫面內部資料 |
| `app/settings/model.py` | 明確定位為邏輯模型；UI 改用契約，必要的欄位轉換放在邏輯層 |
| `app/settings/__init__.py` | 配合責任與匯入變動整理匯出，保留現有正式呼叫需要的服務介面 |
| `ui/settings/settings_window.py` | 改用純資料契約；透過子元件公開方法取得輸入與測試目標；保留畫面及對話框行為 |
| `ui/settings/widgets/api_group_editor.py` | 移除環境讀取、schema 判斷與保存語義；使用輸入／顯示契約，提供公開方法 |
| `ui/settings/pages/ai_page.py` | 改用畫面契約；封裝舊金鑰列資料收集；停止呼叫編輯器私有方法 |
| `ui/settings/pages/general_page.py` | 改用顯示契約，保留畫面事件與狀態呈現 |
| `ui/settings/pages/appearance_page.py` | 改用顯示契約，保留尺寸輸入與提交行為 |
| `ui/settings/pages/behavior_page.py` | 改用顯示契約，保留閒置秒數輸入 |
| `ui/settings/pages/personality_page.py` | 改用顯示契約，維持人格切換與自訂內容保留 |
| `app/core/window_manager.py` | 更新 Presenter 路徑與組裝方式；保留可見視窗不重載、已關閉視窗重開時重載的行為 |
| `ui/README.md` | 更新三層責任、依賴規則、組裝例外與新增視窗範例流程 |

### 6.2 原則上保留，只做相容性核對

| 檔案／目錄 | 處理原則 |
| --- | --- |
| `ui/dashboard/dashboard_window.py`、`sidebar.py`、`page_registry.py`、`styles.py`、`__init__.py` | 已是通用 UI；不搬入設定功能或服務呼叫 |
| `ui/settings/page_registry.py`、`dialogs.py`、`styles.py`、`widgets/input_controls.py`、`widgets/number_input.py` | 維持 UI 責任；只有契約調整確有需要時才修改 |
| `app/settings/service.py`、`api_group_service.py`、`api_group_resolver.py`、`api_groups.py`、`env_group_storage.py` | 沿用既有驗證、解析與保存能力；必要時新增窄介面或調整呼叫，但不改資料格式及正式請求語義 |
| `app/core/config_manager.py`、`dotenv_file.py`、`paths.py` | 作為既有基礎設施沿用，不做資料遷移或目錄調整 |
| `app/core/application.py`、`main.py` | 核對啟動與匯入相容性；無必要不修改 |

### 6.3 測試檔案

| 檔案 | 調整與驗證重點 |
| --- | --- |
| `tests/settings_helpers.py` | 更新 Presenter、worker 與契約匯入；提供服務、View 的測試替身 |
| `tests/test_settings_architecture.py` | 擴充分層規則與動態隔離檢查，涵蓋環境讀取與服務初始化 |
| `tests/test_settings_workflow.py` | 使用不含 QWidget 的假 View 驗證協調流程 |
| `tests/test_settings_session.py`、`test_settings_service.py` | 驗證新輸入轉換、草稿、套用、取消及保存失敗時的狀態 |
| `tests/test_settings_api_groups.py`、`test_settings_api_keys.py` | 驗證顯示／遮蔽、來源切換、未變更金鑰、空白保留、刪除與測試流程 |
| `tests/test_settings_entry.py`、`test_settings_window.py`、`test_settings_dialogs.py` | 更新匯入與介面；驗證組裝、重開、確認及關閉 |
| `tests/test_settings_input_controls.py`、`test_settings_personality.py` | 驗證焦點、滾輪、數值輸入與人格內容保留 |
| `tests/test_dashboard_shell.py` | 保留並確認共用框架沒有引入功能依賴 |
| `tests/test_settings_display.py`（新增） | 使用假環境來源驗證顯示資料與秘密欄位處理 |
| `tests/test_settings_editing.py`（新增） | 不建立視窗即可驗證金鑰編輯與來源轉換規則 |
| `tests/test_settings_connection_test.py`（新增） | 分別驗證純測試服務、Qt 包裝及工作生命週期 |
| `tests/test_api_groups.py`、`test_api_group_resolver.py`、`test_api_group_runtime.py`、`test_env_data_format.py` | 作為既有格式與正式執行相容性的回歸檢查；不因重構放寬原有斷言 |

實作前搜尋所有舊模組匯入與 patch 路徑，一併更新實際引用者；不得以保留兩套實作的方式讓測試通過。

## 7. 執行步驟與階段驗收

### 第一階段：建立行為與依賴基準

1. 核對工作目錄變更，記錄非本次內容。
2. 搜尋上述模組的匯入、測試 patch 與呼叫位置。
3. 執行 Dashboard、設定相關測試並記錄通過、失敗及環境限制。
4. 明列既有金鑰輸入、溫度精度、套用／取消、關閉／重開與背景測試的行為。
5. 針對未被涵蓋且可能因搬移改變的行為補充必要測試。

驗收：有可重現的基準；既有失敗與新增回歸可區分。Tavily 問題只記錄，不修正。

### 第二階段：建立純資料契約與公開介面

1. 建立 `app/contracts/settings.py` 及 View 介面。
2. 定義顯示資料、原始輸入、操作與測試結果的邊界，避免暴露 schema 或元件。
3. 為子元件增加公開輸入收集、測試目標與版面方法。
4. 更新 `SettingsWindow` 與 `AIPage`，解除對內部列字典與私有方法的依賴。

驗收：單獨匯入契約不載入 Qt 或設定服務；元件內部結構改動不需要改 Presenter。

### 第三階段：將金鑰與編輯規則移至邏輯層

1. 建立顯示資料建構功能，集中解析金鑰顯示值與來源狀態。
2. 在 `editing.py`／Session 集中金鑰保留、更換、來源切換及原值比較。
3. UI 切換為新契約，移除 `os.environ`、schema 與儲存模型建構。
4. 保持輸入顯示、空白保留、金鑰遮蔽、自訂模型及溫度精度行為。
5. 以暫存資料驗證套用與重新載入，不讀寫使用者真實金鑰。

驗收：規則可在無視窗情況下驗證；相同畫面資料不因執行環境不同而自行改變；資料格式與保存效果維持相容。

### 第四階段：獨立串接層與背景工作包裝

1. 搬移 Presenter 與 Controller 到 `app/presentation/settings`。
2. 將 Qt worker 與單次連線測試服務拆開。
3. Controller 改向邏輯服務取得測試請求及一致性資料，保留排程與過期結果控制。
4. 更新 `WindowManager`、測試輔助與所有匯入／patch 路徑。
5. 確認畫面確認流程由 Presenter 協調，服務不操作視窗。

驗收：假 View 可以完整驗證流程；純測試服務不需要 QApplication；最多四個工作與過期結果行為未退化。

### 第五階段：建立防止再次混用的檢查

1. 限制 UI 僅匯入契約，禁止匯入設定服務、串接層與設定單例。
2. 檢查 UI 的環境讀取、檔案／網路操作，並用假環境來源確認顯示由外部資料驅動。
3. 限制邏輯層不得匯入 UI／串接層／QtWidgets。
4. 限制串接層不得匯入具體 UI 或存取元件；透過假 View 執行行為測試。
5. 為組裝入口保留精確例外，避免整個 `app/core` 都被視為可任意混用。
6. 使用兩個獨立 Session／假 View，確認草稿與測試回呼不會互相污染；不新增真實視窗功能。

驗收：能攔截此次發現的越界行為，測試不只檢查目錄名稱或特定字串。

### 第六階段：整合驗收與文件收尾

1. 執行相關測試，再執行完整測試套件一次；失敗須明列原因，不能宣稱全部通過。
2. 手動確認設定視窗的頁面、窄版、捲動、數字輸入、金鑰顯示、套用與取消。
3. 以模擬服務驗證背景連線、關閉後回傳、刪除後回傳及重開後過期結果。
4. 核對資料格式、正式 API 群組解析與既有使用者資料未被意外變更。
5. 移除遷移用重複契約／轉接匯出，更新 `ui/README.md` 及本計畫狀態。
6. 檢查最終 diff，只包含已規劃的程式、測試及文件修改。

驗收：三層責任可由依賴與測試共同證明；功能維持原樣；沒有遺留第二套保存或來源解析規則。

## 8. 未來新增視窗的規則

新增視窗時依序定義：使用者操作、邏輯服務、資料契約、Presenter、UI 與組裝入口。

- 每個編輯視窗持有自己的 Session 與 Presenter；服務可以共用。
- 跨視窗通知傳遞資料更新事件或識別碼，不傳遞 QWidget。
- 不將新增視窗的功能規則塞入 `DashboardWindow` 或 `WindowManager`。
- 新視窗需通過相同邊界測試；無導覽需求的視窗可採獨立 UI。

多視窗同時保存同一份設定的衝突處理列為後續擴充：現況只有一個設定編輯視窗，本次先確保草稿隔離與服務邊界。正式加入第二個設定寫入入口前，必須增加版本／修訂檢查，由服務拒絕覆蓋過期快照，再由 Presenter 協調重新載入；不可只依賴畫面提示避免覆蓋。

## 9. 實作與回退原則

- 按使用者指示每次執行兩個階段；目前六個階段均已完成，各批結果分別記錄於第 11 至 13 節。
- 各階段以可驗證的增量完成；階段未通過，不繼續疊加無關變動。
- 計畫若需要變更範圍、既有操作行為或資料格式，先說明差異與原因。
- 回退只針對本次修改，不使用會抹除使用者其他變更的整體還原方式。
- 遷移過程不建立新資料格式，因此不應需要回復使用者資料或執行資料降版。
- 真實 API 測試不作為自動驗收前提，不使用真實金鑰填入測試資料。

## 10. 最終完成條件

- [x] UI 不讀取環境變數、設定檔或呼叫 API。
- [x] UI 不處理 schema、金鑰保存映射與資料遷移。
- [x] Presenter 只透過 View 公開介面協調流程。
- [x] 邏輯服務可脫離具體視窗測試，沒有反向 UI 依賴。
- [x] 背景測試的並行限制、快照與過期結果處理維持正確。
- [x] Dashboard 保持可供其他功能使用的通用框架。
- [x] 設定檔格式、資料位置與現有操作行為維持相容。
- [x] 分層、行為及整合驗證結果均有記錄。
- [x] 文件、匯入與測試替身同步更新，沒有雙份實作。
- [x] Tavily 遺留問題及非本次工作目錄變更未被處理。

## 11. 第一、第二階段執行紀錄（2026-10-15）

### 執行前本地提交

- 提交：`25c8238`，`docs: plan settings three-layer refactor`。
- 僅提交本計畫的初始版本，未推送。
- 原有 `tree.txt` 修改，以及資料格式計畫由根目錄移到 `過往開發計畫/` 的變更，均未納入本次提交或改動。

### 第一階段結果：已完成

- 搜尋 Presenter、連線測試與舊契約的正式匯入及測試 patch 位置。
- 原始設定測試：151 項通過；Dashboard 框架：10 項通過。
- 環境資料格式測試：9 項通過，包含已保存金鑰顯示、空白保留、更換及刪除的既有覆蓋。
- 新增 `tests/test_settings_baseline.py` 的 2 項行為基準，確認已保存金鑰切換來源再切回，以及外部環境來源改為儲存金鑰時的引用處理，均通過。
- 記錄的既有行為：選中群組與目前使用群組分離；展開、遮蔽不造成 dirty；空白新列不保存；未編輯的溫度保留原值；套用失敗保留草稿；可見視窗喚回不重載；關閉／重開失效舊結果；未完成測試上限維持四個。
- 初次測試遇到沙箱預設暫存目錄清除時的 `PermissionError`。將該次測試程序的 `TEMP`／`TMP` 指向專案內受忽略的 `.pytest_cache/refactor_tmp` 後通過；未改動系統環境設定或測試產品邏輯。

### 第二階段結果：已完成

- 建立 `app/contracts/settings.py`：關閉操作、連線測試目標、原始輸入與顯示資料的純資料契約，不含 schema、環境變數映射或元件。
- 舊 `view_contracts.py` 暫時只重匯出同一組類別，不保留重複定義；正式使用點改由新路徑匯入，轉接檔於第六階段移除。
- 建立 `app/presentation/settings/view_port.py`，描述 Presenter 使用的事件與公開方法。資料參數暫以泛型描述現有介面，待第三階段接入顯示契約；Presenter 實體仍依第四階段安排留在原路徑。
- `APIGroupEditor` 新增 `collect_input()`、`connection_inputs()`、`set_available_width()`。原始輸入保留欄位內容，並表示是否與初始顯示值不同，不解讀保存動作。
- `AIPage` 公開封裝金鑰列輸入及群組測試目標；`SettingsWindow` 不再直接讀取 `group_rows`／`api_key_rows`，`AIPage` 不再呼叫編輯器私有排版方法。
- 新增元件替身測試，確認父元件只需要公開方法，不需要子元件列結構；涵蓋目標刪除／重建、輸入快照、秘密欄位 repr 與寬窄版行為。
- 增加隔離匯入測試，確認新契約與 View 介面不載入 Qt、UI 或設定服務；確認新舊關閉選擇仍是同一個 Enum 類別。

### 本次驗證與後續邊界

- 設定測試 162 項、Dashboard 10 項、環境資料格式 9 項，共 181 項通過。
- 本次未執行全專案測試或人工操作驗收；完整驗收仍屬第六階段。
- 新群組輸入／顯示契約已建立，`collect_input()` 已可用，但正式 `groups_changed` 訊號仍走既有 `collect_settings()`。第三階段才切換正式資料流並移除 UI 中的環境讀取與保存規則。
- `SettingsDisplay`、群組顯示與測試結果資料契約目前是後續轉換的邊界定義，尚未取代全部既有畫面載入／worker 回傳。
- 未搬移 Presenter／Controller／worker，未修改資料格式與使用者設定，未處理 Tavily 遺留問題。

重現本次測試的 PowerShell 指令：

```powershell
New-Item -ItemType Directory -Force -Path '.pytest_cache/refactor_tmp' | Out-Null
$env:TEMP = Join-Path (Get-Location) '.pytest_cache/refactor_tmp'
$env:TMP = $env:TEMP
python -B -m unittest discover -s tests -p 'test_settings_*.py'
python -B -m unittest discover -s tests -p test_dashboard_shell.py
python -B -m unittest discover -s tests -p test_env_data_format.py
```

## 12. 第三、第四階段執行紀錄（2026-10-15）

第 11 節為上一批的歷史紀錄，當時尚未接入的契約與搬移已於本批完成。

### 執行前本地提交

- 提交：`d87a63f`，`refactor: establish settings contracts and public view ports`。
- 保存第一、第二階段的程式、測試與文件；未推送。
- 仍排除原有 `tree.txt` 與資料格式計畫的移動。

### 第三階段結果：已完成

- 新增 `app/settings/display.py`，由邏輯層準備一般設定、API 群組與金鑰顯示資料，金鑰來源可以注入以便隔離測試。
- 設定頁面改用 `SettingsDisplay`／`LegacyKeyInput`，群組編輯器改用 `APIGroupsDisplay`／`APIGroupsInput`；UI 不再匯入設定領域模型。
- 正式 `groups_changed` 訊號已切換至原始輸入契約；移除舊 `collect_settings()`。
- 編輯器不再讀取環境變數，不保存 schema 或金鑰環境引用，也不決定空白輸入的保存語義。
- `groups_from_input()` 在邏輯層處理已保存金鑰保留、更換、來源切換、原始引用與溫度精度。
- Session 分開保存畫面載入基準與正規化草稿；新增群組／Key 先在邏輯層登記，避免空白列或連續切換來源後遺失原始資料。
- 欄位狀態文字由邏輯層產生，UI 僅依識別碼呈現。金鑰顯示／遮蔽與排版行為保留。
- 新增顯示、編輯規則測試及暫存資料整合測試：來源切換再切回不產生變更；改名與空白輸入保留原金鑰；明確更換後只更新對應環境值，JSON 仍不含金鑰。

### 第四階段結果：已完成

- Presenter 與 Controller 已搬至 `app/presentation/settings/`，原檔移除，沒有雙份實作。
- `connection_test_worker.py` 只負責 Qt 工作包裝、signal 回傳及完成後清除自己持有的金鑰。
- `app/settings/connection_test.py` 負責單次同步連線、錯誤安全化、舊設定驗證及群組測試快照準備；不含 QObject／QRunnable。
- Controller 保留工作排程、四個未完成工作上限、重複測試控制與過期結果判斷；指定 Key、停用 Key 手動測試及免金鑰規則改呼叫邏輯服務。
- 更新 `WindowManager` 組裝、測試 helper、正式匯入與 patch 位置。
- View 介面已使用具體顯示契約，移除第二階段的泛型過渡；假 View 的保存、取消與確認流程測試維持通過。
- 隔離程序證明單次連線測試服務可以在不載入 PySide6／UI、不建立 QApplication 的情況下執行；使用模擬客戶端，沒有實際網路請求。

### 本批驗證

| 測試範圍 | 通過數量 |
| --- | --- |
| `test_settings_*.py` | 172 |
| `test_env_data_format.py` | 10 |
| `test_api_group*.py` | 59 |
| `test_ai_errors.py` | 10 |
| `test_dashboard_shell.py` | 10 |
| `test_main_entrypoint.py` | 1 |
| 合計 | 262 |

- 延用專案內測試暫存目錄，保存流程只使用暫存資料與假金鑰。
- 既有背景測試上限、關閉／刪除／重建後結果失效、環境金鑰與免金鑰測試均通過。
- 未改動正式 AI 請求策略、設定檔格式、使用者資料位置或 Tavily 遺留邏輯。
- 本批變更保留在工作目錄，尚未另行提交；第五、第六階段尚未開始。
- 本次是相關範圍回歸，未宣稱全專案測試或人工操作驗收完成。

## 13. 第五、第六階段執行紀錄（2026-10-16）

第 11、12 節保留當時的狀態；本節記錄最終收尾結果。

### 執行前本地提交

- 提交：`2d6ad63`，`refactor: separate settings presentation and application logic`。
- 保存第三、第四階段程式、測試與文件；未推送。
- 排除原有 `tree.txt` 與資料格式計畫搬移，未改寫這些內容。

### 第五階段結果：已完成

- 新增 `tests/settings_boundaries.py` 與 `tests/test_settings_boundaries.py`，檢查實際 AST 與依賴，而非只以檔名判斷責任。
- UI 檢查限制應用層依賴至契約；攔截環境／檔案／網路相關匯入、常見外部操作與動態匯入。
- 邏輯層不得匯入 UI、串接層或 QtWidgets；支援一般別名與相對匯入辨識。
- 串接層不得匯入具體 UI 或直接使用檔案／網路／設定管理器；View 存取必須在公開介面內。
- 組裝例外精確限定在 `app.core.window_manager.WindowManager.show_settings()` 的串接層匯入，不放行整個 `app/core`。
- 增加故意越界的測試樣本，涵蓋匯入別名、檔案讀取、環境變數、Qt 設定存取、反向依賴、相對匯入與元件存取，確認檢查會報錯。
- 使用共用假後端、兩個獨立 Session／假 View 驗證草稿與取消隔離；相同 request ID 的結果只回到原始 View，關閉／重開一方不影響另一方。
- 群組載入基準、來源切換與新增列登記也驗證為 Session 各自持有。

### 第六階段結果：已完成

- 移除 `app/settings/view_contracts.py` 相容重匯出；所有正式使用點採用 canonical 契約。
- 移除未被使用的 `ConnectionTestResult` 過渡定義。現行同步測試服務仍回傳其實際使用的 `ConnectionCheckResult`。
- 更新 `ui/README.md`，說明最終依賴、驗收方式與新增視窗限制。
- 設定相關測試 179 項通過，隨後完整測試套件一次執行，**441 項全數通過**。
- 測試輸出中的模擬錯誤訊息來自既有失敗路徑測試，最終 unittest 結果為 `OK`。
- 模擬連線及既有整合測試涵蓋四個未完成工作上限、指定／停用／環境／免金鑰、修改／刪除／關閉／重建後結果失效等行為。

### 介面驗收方式與結果

本環境採用假資料、暫存後端的離屏 Qt 視窗，以 QTest 模擬點擊與鍵盤、Qt 滾輪事件驗證互動，並逐張人工式視覺檢查產生的 13 張截圖。這是原計畫「手動確認介面」在本次環境的具體替代方式，已在執行前說明。

- 900×650：一般、外觀、行為、人格與 AI 五頁，內容及頁尾可讀。
- 650×600：側欄自動收合、API 列表與詳情改為上下排列，底部內容可捲動到達。
- 金鑰預設遮蔽，顯示／再次遮蔽正常；截圖只含明確的示範假金鑰。
- 模擬背景連線完成後顯示成功文字。
- 鍵盤輸入寬度 420 後套用，暫存後端確實保存；改為 430 後取消，重開仍為 420。
- 初次離屏渲染缺少字型，僅在驗收工具載入本機 Segoe UI／Microsoft JhengHei 後重新檢查；沒有修改產品字型設定。
- 此驗收未覆蓋 Windows 原生桌面的 DPI、視窗管理、不同螢幕或字型回退行為，不宣稱完成這些環境的實機手動驗證。

### 資料與變更範圍核對

- 驗收前建立內容雜湊，驗收後比對 `data/` 與既有使用者參考檔，共 14 個檔案逐位元組一致；無新增或刪除。
- 對話、記憶、設定、API 引用與 `.env` 沒有因測試改寫；測試寫入限於暫存後端。
- Tavily 遺留內容、資料格式與正式 AI 請求策略維持原狀。
- `git diff --check` 通過；最後一批尚未另行提交，未推送。

### 重現與驗收產物

```powershell
$env:TEMP = Join-Path (Get-Location) '.pytest_cache/refactor_tmp'
$env:TMP = $env:TEMP
python -B -m unittest discover -s tests -p 'test_settings_*.py'
python -B -m unittest discover -s tests
```

本機驗收輔助檔位於受 Git 忽略的 `.pytest_cache/refactor_final/`：完整測試輸出 `full-suite.log`、離屏操作腳本 `visual_check.py`、截圖與資料雜湊紀錄。這些是可清除的驗收暫存，不是程式執行依賴。

分層檢查旨在防止一般開發回歸，不是可阻擋所有動態 Python 寫法的安全沙箱。未來新增第二個設定寫入入口時，仍須按第 8 節加入保存衝突控制；這次僅驗證工作階段隔離。

## 14. 收尾與測試複查（2026-10-16）

- 發現架構檢查工具將整份檔案的別名存進同一份映射；不同函式的同名變數會互相覆蓋，導致漏報與誤報。已重現兩種情況，改為按來源順序、隔離作用域解析，並加入函式參數遮蔽與重新賦值案例。
- 收緊組裝例外：`WindowManager.show_settings()` 內另宣告的巢狀函式不享有例外。
- 補強雙 Session 測試：使用實際新增 Key 的回傳 ID 建立輸入、檢查新增資料，再取消草稿，確認另一個 Session 不受影響。
- 本次僅修改測試與文件；未新增產品行為變更。

| 複查方式 | 結果 |
| --- | --- |
| 完整 `unittest discover -s tests` | 444 項通過 |
| 每個設定測試檔分開啟動 Python | 17 個檔案全部通過 |
| 設定測試按反向順序執行 | 182 項通過 |
| `git diff --check` | 通過 |
| 正式資料與原有參考檔雜湊核對 | 14 個檔案一致，data 無新增／刪除 |

未發現上述測試範圍內的執行順序依賴或測試失敗。測試輸出的模擬錯誤日誌不代表 unittest 失敗。
架構檢查處理一般靜態匯入與別名，不模擬分支合併或完整 Python 執行語義。
Windows 原生桌面 DPI／多螢幕仍未實機驗證；Tavily 遺留問題維持不處理。

本機紀錄位於受 Git 忽略的 `.pytest_cache/refactor_final/`：
`closeout-full-suite.log`、`isolated-test_settings_*.log` 與 `closeout-reverse-settings.log`。
最後一批及本次收尾修改保留在工作目錄，尚未提交或推送。
