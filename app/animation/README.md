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

2026-10-16 完整測試 486 項通過；以真實 Qt 元件、假回覆與記憶體後端完成離屏視覺驗收，
確認三種表情、保留閱讀、純文字對話與完成後約 3.04 秒回 idle。
這不等同於 Windows 原生桌面 DPI／多螢幕驗收。

真實模型語境品質尚未通過最終驗收。抽查發現把翻譯引文當成自身情緒、混淆懷疑與驚訝，
以及安慰情境選到驚訝的情況。提示已補強客觀文字處理與懷疑的定義，但仍觀察到誤判；
服務回傳 HTTP 429 後停止外部測試。不能以自動測試通過推論任意模型都能穩定選對表情。

目前前綴協定要求回覆精確以 `[[emotion:名稱]]` 開始。前置空白、圍欄或超長畸形輸出
不保證完整清除控制碎片；解析器採有限緩衝，優先避免吞掉正常正文或令整則回答失敗。
詳細抽查紀錄與待辦見根目錄 `AI語境情緒動作實作計畫.md`。
