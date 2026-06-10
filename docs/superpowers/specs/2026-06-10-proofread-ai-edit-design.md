# 校對頁 AI 輔助修改（per-segment AI edit）— Design

日期：2026-06-10 ｜ 狀態：✅ 用戶已批准設計 ｜ Branch: `worktree-proofread-glossary-ai`

## 目標

校對頁右側 segment detail panel，每個語言欄（第一／第二語言）加一粒「✦ AI」掣。撳掣彈小型 popup：用戶可以用自由指令或快速選項（對照翻譯／改更書面／改更口語／精簡句子）叫 AI 修改**該段、該語言欄**嘅字幕文字；先預覽「修改前 → 修改後」，撳「套用」先真正寫入。

## 用戶決策（2026-06-10 brainstorming 確認）

| 決策點 | 揀咗 |
|---|---|
| 套用方式 | **先預覽後套用**（popup 內對照，撳「套用」先寫入；可「再生成」） |
| 目標範圍 | **一次只改撳掣嗰一欄**（另一語言做參考 context） |
| 語氣選項 | **兩個子選項：更書面 / 更口語** |
| 適用檔案 | **只做 `output_lang` 檔**（Profile/V6 唔出 AI 掣） |
| 快速選項行為 | **chips 先填入指令框（可修改）再撳生成** |
| 架構 | **方案 A**：suggest-only endpoint（唔寫 registry）+ 前端經現有 PATCH 套用 |

## 架構（方案 A）

```
[AI 掣 (per-language label row)]
        │ openAiEditModal(role)
        ▼
[ae-* popup] ──生成──▶ POST /api/files/<id>/ai-edit {pos, role, instruction}
        ▲                      │  (lock 內 snapshot → lock 外 LLM → 解析/驗證)
        │  {text, source_text} ◀┘  ＊唔寫 registry＊
        │
   撳「套用」──▶ 現有 PATCH /api/files/<id>/translations/<idx> {text, role}
                （by_lang + {lang}_text mirror + auto-approve + 新增 aligned_bilingual 同步）
```

## 組件

### 1. `backend/ai_edit.py`（新 pure module，獨立可測）

- `build_system_prompt(target_lang, other_lang) -> str` — 廣播字幕編輯助手 persona；規則：
  - 只輸出 JSON `{"text": "修改後字幕"}`，無 markdown／解釋／思考標籤
  - 保留專有名詞、數字、英文原樣（除非指令明確要求改）
  - 維持目標語言同書寫系統（繁／簡），唔好轉語言
  - 字幕要簡潔、適合廣播閱讀
- `build_user_prompt(target_lang, target_text, other_lang, other_text, instruction) -> str` — JSON 包目標語言／現有字幕／另一語言參考（有先俾）／用戶指令
- `parse_response(raw) -> Optional[str]` — 剝 `<think>…</think>`、markdown fence；接受 `{"text": …}` 或純文字；清洗：strip、collapse 內部換行做空格；驗證：非空、長度 ≤ 200 字符；任何失敗回 `None`

### 2. app.py route

`POST /api/files/<file_id>/ai-edit` ＋ `@require_file_owner`

Body：`{pos: int, role: "first"|"second", instruction: str}`
- preset 同自訂統一用 `instruction` 文字 — backend 唔分 action 類型（chips 只係前端文字模板）

流程（仿 split endpoint 但更簡單，因為唔寫嘢）：
1. 驗證 body：`instruction` 非空且 ≤500 字；`role` 有效
2. `_registry_lock` 內 snapshot：entry 存在（404）；`active_kind == 'output_lang'`（400）；`pos` 喺 `translations` 範圍（404）；`role=='second'` 而檔案只有一個輸出語言（400）；讀目標語言 text＋另一語言 text＋lang codes（`entry['output_languages']` + `languages` descriptor labels）
3. Lock 外：`llm = _make_ollama_llm_call()`（自動跟 Beta OpenRouter 路由）；`raw = llm(system, user)` 包 `try/except (ConnectionError, RuntimeError)` → **502** `{"error": "AI 服務暫時冇回應，請再試"}`
4. `parse_response` 回 `None` → **422** `{"error": "AI 輸出無法解析，請再試或修改指令"}`
5. 成功 → **200** `{"ok": true, "text": <修改後>, "source_text": <snapshot 時嘅修改前>, "pos": pos, "role": role}`

License：同 split endpoint 一致，靠 licensing HTTP gate（`gate.py` before_request）；唔額外加 `_license_guard_or_raise()`。
Render conflict：suggest 唔寫數據，唔使 409 guard（套用行 PATCH，PATCH 今日都容許 render 中文字編輯 — render job 開始時已 snapshot translations）。

### 3. PATCH `aligned_bilingual` 同步修正（現有 bug，順手修）

`api_update_translation`（app.py:3491-3596）output_lang branch 而家只同步 `by_lang` + `{lang}_text` mirror，**唔掂 `aligned_bilingual`** — 但雙語匯出（app.py:5175-5182）同雙語 render（app.py:4070-4076）直接讀 `aligned_bilingual`，所以單欄文字編輯（手動或 AI）會 silently 同雙語輸出分歧。

修法：喺同一個 `_registry_lock` 寫入段，當 `entry.get('aligned_bilingual')` 且 `idx` 喺範圍：immutable 重建 `aligned_bilingual[idx]['by_lang'][lang] = new_text`（注意 aligned 嘅 by_lang 值係**字串**，唔係 dict）。

### 4. 前端（proofread.html）

- `renderDetail()` template：兩個 `.rv-b-detail-label` 行各加 `✦ AI` 細掣（inline `onclick="openAiEditModal('first'|'second')"`）；條件：`isOutputLang`，second 欄另要 `s._hasSecond`；V6/profile 檔完全唔出
- 新 modal（class `ae-*`，照抄 `ga-overlay`/`ga-modal` 樣式 pattern，z-index 同層）：
  - 開 modal 時**鎖定** `{idx: s.idx, role, beforeText}` — 套用永遠落喺呢個 idx，唔跟 cursor
  - chips：`對照翻譯`（要有兩個語言先顯示）→ 填入「根據{另一語言label}嘅意思，重新翻譯做{目標語言label}」；`改更書面`→「將語氣改得更書面正式」；`改更口語`→「將語氣改得更口語自然」；`精簡句子`→「喺唔改變意思嘅前提下精簡呢句字幕」
  - 「生成」：disable 掣＋spinner → POST ai-edit → 「修改後」preview；錯誤 toast＋modal 留低可重試
  - 「套用」：PATCH `/translations/<idx>` `{text, role}` → 更新 `segs[]`（`.en`/`.zh`＋CPS）→ `renderDetail()` + `renderSegList()` → toast「已套用 AI 修改」→ 閂 modal
  - Esc 閂 modal（擴展現有 keydown listener，跳過生成中？生成中閂 = 放棄結果，無妨）

## 錯誤處理

| 情況 | 行為 |
|---|---|
| LLM 冇回應／retry 耗盡 | 502 → toast 顯示後端 error，modal 留低可重試 |
| LLM 輸出垃圾 | 422 → 同上 |
| 指令空／超長、role 無效、非 output_lang、pos 越界 | 400（前端 chips/disable 已預防大部分） |
| 套用時 PATCH 失敗 | 現有 save 錯誤 toast 模式 |

## 測試計劃

1. **pytest `tests/test_ai_edit.py`**（mock `appmod._make_ollama_llm_call`，照 `test_segment_split_routes.py` seeding pattern）：
   - happy path（建議回傳正確；**registry 完全冇變**）
   - 解析：`<think>` 標籤／markdown fence／`{"text":…}`／純文字
   - 垃圾輸出→422；ConnectionError→502；400 系（缺指令、壞 role、profile 檔、pos 越界、單語言檔 role=second）
2. **pytest PATCH 同步**：PATCH 後 `aligned_bilingual[idx].by_lang[lang]` 已更新；無 aligned_bilingual 嘅檔唔爆
3. **Playwright E2E**（真 Chrome＋本機 Ollama）：AI 掣出現→popup→chip 填指令→生成→預覽→套用→textarea/seg list 更新
4. **Validation-First live 驗證**：幾段真字幕 × 4 種指令 × production model `qwen3.5:35b-a3b`，結果記入 `docs/superpowers/specs/2026-06-10-proofread-ai-edit-validation-tracker.md`

## Out of scope（YAGNI）

Profile/V6 檔支援、批量多段修改、undo 歷史、詞彙表整合、自訂 temperature/model。
