# Beta 測試模式 — E2E 驗證 Runbook（LLM-only）

- **Date**: 2026-06-08
- **Feature**: Admin Beta 測試模式（`feat/admin-beta-openrouter-models`，PR #9）
- **目的**: 驗證開啟 Beta 後，output_lang pipeline 嘅 **LLM（翻譯 / 書面語 refiner）行 OpenRouter `qwen/qwen3.5-35b-a3b`**，而 **ASR 維持本地 mlx-whisper**。
- **相關**: [design](2026-06-07-beta-openrouter-mode-design.md) · [plan](../plans/2026-06-07-beta-openrouter-mode.md) · [validation tracker](2026-06-07-beta-openrouter-validation-tracker.md)

> **核心思路**：最決定性嘅證據係 **OpenRouter Activity 頁**。開 Beta 跑一條片之後，個頁應該見到 `qwen/qwen3.5-35b-a3b` 嘅 chat 請求（證 LLM 上雲），而且**完全冇** whisper / audio 請求（證 ASR 留本地）。

---

## 前置（重要 — 參考 ops 慣例）

1. **重啟 :5001 後端**，確保新 code + `.env` loader live：
   - 一定要帶 `FLASK_SECRET_KEY`（由 `backend/.env` 載入，否則啟動即 crash）。
   - 核實係**新 code** 喺度跑：唔好淨信 `health=200`；要核 PID + 行為（stale 大楷 "Python" process 會霸住 port 但跑緊舊 code）。
   - 行為 probe：`GET /api/admin/beta-mode` **回到 200 JSON**（舊 code 冇呢個 route → 404，即係未 live）。
2. 用 **admin** 帳號登入 `/user.html`。
3. 開住 **OpenRouter Activity 頁**：<https://openrouter.ai/activity>（全程睇呢度做證據）。

---

## A. 開啟 Beta + 確認 key

4. 我的帳戶 → **「Beta 測試模式」** 分頁。
5. 喺 **OpenRouter API Key** 欄輸入一個**有效**嘅 key → 剔 **啟用** → **儲存**。
6. 應見：狀態變「✓ API key 已設定」、toggle 維持開。
   - （可選 curl，需 admin cookie）：`GET /api/admin/beta-mode` → `{"enabled":true,"key_configured":true,"llm_model":"qwen/qwen3.5-35b-a3b"}`。

## B. 跑一條片（Beta ON）

7. Dashboard 揀一條**英文語音**片（建議 `馬會騎師訪問（英文語音）.mp4`）→ upload popup → 輸出語言揀 **中文書面語**（en→zh 行 cross-lang MT → 經 OpenRouter）。
8. 等佢跑：ASR（本地 mlx-whisper）→ 翻譯 → 完成，出中文字幕。

## C. 看證據（最關鍵）

9. **OpenRouter Activity 頁** 喺翻譯階段應該出現：
   - ✅ 一批 **`qwen/qwen3.5-35b-a3b`**（chat/completions）請求 → 證 **LLM 上咗雲**。
   - ✅ **冇任何** `whisper-large-v3` / audio 請求 → 證 **ASR 留咗本地**。
10. 字幕內容正常（功能正確性）。

## D. 對照（Beta OFF）

11. 返「Beta 測試模式」分頁 → **熄 toggle** → 儲存。
12. 同一條片再跑一次 → OpenRouter Activity **唔應該有新嘅 chat 請求**（LLM 行返本地 Ollama）。
    - 呢步證實個 toggle 真係喺度切換，唔係一直上雲。

## E. 硬失敗（無自動 fallback）

13. （可選）輸入一個**錯 / 失效**嘅 key → 啟用 → 跑片 → 預期 **job 標 failed**，前端顯示「OpenRouter 翻譯失敗：…401…」之類，**唔會靜默退回本地**。
14. 驗完即刻換返有效 key。

## F. 重啟持久化

15. **重啟後端**（唔再喺 UI 輸入 key）→ `GET /api/admin/beta-mode` 仍然 `enabled:true` + `key_configured:true` → 證 `_load_env_file` boot loader 令 key 跨重啟生效。

---

## ✅ 通過準則

| 步驟 | 準則 |
|---|---|
| C9 | OpenRouter 見到 qwen3.5 chat 請求、**零** whisper/audio 請求 |
| C10 | 出到正常中文字幕 |
| D12 | Beta OFF 後無新雲端請求（LLM 行返本地） |
| E13 | 壞 key → job failed（非靜默 fallback） |
| F15 | 重啟後 key 仍在（`.env` boot loader 生效） |

---

## 附錄：admin-cookie curl 序列（驗 A / F 可選）

```bash
BASE=http://localhost:5001
# 1) 登入攞 session cookie（換你嘅 admin 帳密）
curl -s -c /tmp/mo_cookies.txt -X POST "$BASE/api/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"<admin>","password":"<password>"}'

# 2) 讀 Beta 狀態
curl -s -b /tmp/mo_cookies.txt "$BASE/api/admin/beta-mode"

# 3) 開 Beta + 設 key（亦可用 UI）
curl -s -b /tmp/mo_cookies.txt -X PUT "$BASE/api/admin/beta-mode" \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true,"api_key":"sk-or-<your-key>"}'

# 4) 熄 Beta
curl -s -b /tmp/mo_cookies.txt -X PUT "$BASE/api/admin/beta-mode" \
  -H 'Content-Type: application/json' -d '{"enabled":false}'
```

> 注意：response 永遠**唔會**回顯 key 值，只回 `key_configured` boolean。Key 只存 `backend/.env`（gitignored）。
