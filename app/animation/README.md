# 情緒與動畫

`Animator` 統一發布 `update_pet_image`，桌寵 UI 只顯示圖片。
眨眼、左右看與閱讀沿用原有動畫；情緒是 `assets/pet/emotions/` 中的靜態圖片。

## 採用規則

- AI 可以選擇 `happy`（開心）、`surprised`（意外）、`squint`（懷疑）或 `none`。
- 每個請求最多抽樣一次，預設採用機率 0.3。
- 採用前檢查素材可用且能解碼，採用後立即停止舊動畫並顯示情緒。
- none、機率未命中或素材不可用時不改圖、不停動畫，也不重設既有情緒期限。
- 回覆期間保持情緒；該請求完成、取消或失敗後保留 3 秒再回 idle，不續播被中止的舊動畫。
- 聊天事件只記錄活動時間；拖曳、開啟設定等非聊天互動仍可中斷情緒。

## 調整機率

預設值在 `data/config/app.defaults.ini`。使用者可在 `data/config/app.ini` 既有的
`[General]` 區段設定 `EmotionRate`，例如：

```ini
[General]
EmotionRate = 0.3
```

手動編輯後重新啟動程式。不要在同一檔案重複建立 `[General]` 區段。
目前設定視窗尚未提供此欄位。

0 表示不採用情緒，1 表示合法且有可用素材時必定採用；非法值回退 0.3。
這是條件採用機率，不保證每十則訊息出現三次，也沒有冷卻時間。

設定讀取優先順序為 `data/config/app.ini` → `data/config/app.defaults.ini` →
Python 的 `DEFAULT_EMOTION_RATE` 備援值。因此只修改 Python 常數，不會覆蓋 INI 中已有的值。

## 日誌

正常圖片切換與情緒解析、採用、略過、到期不再寫入診斷 log。
保留圖片不存在／無法解碼、未知動畫及原有 API 等錯誤或警告紀錄。
圖片繪製通知與解析狀態仍供回歸測試使用，不寫入日誌。

`rate=1` 仍不會將 `none` 或無效標記強制變成表情。調整設定檔後須重啟程式。

## 模組與事件

| 模組 | 責任 |
| --- | --- |
| `app/contracts/emotion.py` | 白名單與請求事件資料 |
| `app/ai/prompt_builder.py` | 提示模型依 Nova 自身反應選擇表情 |
| `app/ai/emotion_response.py` | 每請求獨立解析開頭標記，輸出正文 |
| `app/ai/conversation_manager.py` | 串流／歷史清理與請求生命週期 |
| `app/animation/emotion.py` | 素材映射、rate 與一次性採用決策 |
| `app/animation/animator.py` | Qt 主執行緒的中斷、播放與到期管理 |

事件依序為 `emotion_request_started`、最多一次 `emotion_requested`、
`emotion_request_finished`，全部攜帶 request ID。Animator 以請求識別、目前擁有者與
單調時間期限排除舊候選、重複結束與舊 timeout。

## 驗證與目前限制

2026-10-17 重新執行完整測試 486 項通過；先前以真實 Qt 元件、假回覆與記憶體後端完成離屏視覺驗收，
確認三種表情、保留閱讀與純文字對話；在提交 `751da13` 上重新執行離屏驗收，
再次檢查 12 張截圖，回覆完成後約 3.02 秒回 idle，資料檔案內容未變。
這不等同於 Windows 原生桌面 DPI／多螢幕驗收。

先前抽查發現引文、懷疑與安慰情境誤判。2026-10-17 將提示改為有優先順序的判斷規則，
加入不同於驗收案例的語意示例；固定 8 則合成案例的情緒選擇全部符合預期，且正文均無控制標記。
其中 1 則在標記後多出空白，解析正常但不符合「立即換行」格式，嚴格格式與語意合計為 7/8。
此次有限語境抽查通過，嚴格格式仍有偏差；不代表任意模型、人格或長對話都能穩定選對表情。

案例與原始結果保存在 `tests/fixtures/emotion_context_cases.json` 及
`tests/fixtures/emotion_context_report_20261017.json`。可從根目錄手動執行：

```powershell
python -B tests/manual_emotion_context.py --run-live --output .pytest_cache/emotion/new-report.json
```

此指令會使用目前設定的服務發送最多 8 次真實 API 請求，可能產生費用；只傳合成案例，
不讀取聊天歷史或長期記憶，不保存正式對話。每案最多一次 HTTP 嘗試，第一個服務錯誤即停止。
輸出路徑必須尚不存在；退出碼 0 為全部嚴格通過，1 為語意或格式不符，2 為請求失敗。
它不隨 unittest 自動執行。報告中的 `passed` 包含嚴格格式檢查，不能單憑此欄判斷語意正確率。

目前前綴協定要求回覆精確以 `[[emotion:名稱]]` 開始。前置空白、圍欄或超長畸形輸出
不保證完整清除控制碎片；解析器採有限緩衝，優先避免吞掉正常正文或令整則回答失敗。
詳細抽查紀錄與待辦見根目錄 `AI語境情緒動作實作計畫.md`。
