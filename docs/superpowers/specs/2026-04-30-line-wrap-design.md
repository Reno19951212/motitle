# v3.8 — Subtitle Line-Wrap Design

**日期：** 2026-04-30
**版本：** v3.8
**狀態：** 已驗證，準備落 plan

---

## 1. 背景

### 1.1 當前問題（V1.4 已驗證）
今日 production stack 出嘅中文字幕長度失控：
- 79% segment > 16 char（Netflix Originals cap）
- 42% > 23 char（Netflix general cap）
- 16% > 28 char（broadcast relaxed）
- Mean 32 char per cue（Real Madrid 7-segment demo）

### 1.2 已 reject 嘅方案

| 方案 | Reject 原因（empirical evidence）|
|---|---|
| `max_new_tokens` per-segment cap (V0.1) | 截斷 audio data，94% loss |
| 單純 prompt char cap (path A) | LLM 跟 ≤16 char STRONG 但 17% 仍 over，且短 prompt 出 fragment |
| Pre-segment EN + per-cue translate (path C-1) | V1.6 prove fragment 翻譯爆：譯名 drift、tense 錯、clause 斷裂 |
| Single-pass with `||` markers (path C-2) | Hallucination（Case 5 自由發揮 + 譯名統一） |
| Direct subtitle JSON (path C-3) | 切到極碎（19 cues / 7 segs，Case 7 切 5 行）+ knowledge hallucination（Athletic → 畢爾包）|
| jieba/pkuseg word boundary (V2.1) | 對繁體 + 廣東體育譯名失敗（"皇家馬德里" → 「皇家/馬/德里」）|

### 1.3 已 confirm 嘅 design constraint

| Constraint | Source | Value |
|---|---|---|
| Netflix Originals ZH 一行 cap | V1 research | 16 char |
| Netflix general ZH 一行 cap | V1 research | 23 char |
| Broadcast 廣東體育 cap | Industry baseline | 28 char |
| EN→ZH 實際 char ratio | V1.1 measure | 2.88:1（非 1.83）|
| LLM follow rate (qwen3.5-35b-a3b ≤ 16/23) | V1.3 | STRONG（83%）|
| ZH ASR raw 段長 | V_a measure | mean 8.5c, max 18c — 已夠短 |
| EN ASR 段長 | V3.1 measure | mean 9.9 word（80+ char）|
| jieba 對繁體切割可靠度 | V2.1 | ❌ 不可用 |

---

## 2. Chosen approach — Line-wrap render-time

### 2.1 核心理念
**唔改翻譯內容**，純後處理 layer 將長 ZH text 自動 wrap 到多行顯示。

```
┌─────────────────────────────────────────────────┐
│ Source language (EN / ZH / 其他)                 │
│   ↓                                             │
│ ASR (mlx-whisper medium)                        │
│   ↓ raw segments                                │
│ Translation (if non-ZH) — 自然譯，無 char cap     │
│   ↓ ZH text                                     │
│ ┌─────────────────────────────────┐            │
│ │ wrap_zh(text, cap, tail_tol)    │ ← 統一切行  │
│ │ → multi-line tspan / \\N        │            │
│ └─────────────────────────────────┘            │
│   ↓ display-ready ZH                            │
│ Render (SVG overlay / ASS burn-in)              │
└─────────────────────────────────────────────────┘
```

### 2.2 點解優於 path A/B/C

| 維度 | Line-wrap | C-2 (best of path C) |
|---|---|---|
| 翻譯內容 | **零改動** | 重新翻譯，可能 hallucinate |
| LLM call cost | **0 / segment** | 1 / segment |
| Hallucination 風險 | **✅ 零** | ⚠️ 有（Case 5）|
| 譯名 drift | **✅ 零** | ⚠️ Cross-cue drift |
| 字數 cap | 100% per-line | 100% per-cue |
| 失敗 case | 真 hard-cut 1.2-2.4% | 整段 hallucinate |

### 2.3 Algorithm 規格

#### Wrap function
```python
def wrap_zh(text: str, cap: int = 23, max_lines: int = 3, tail_tolerance: int = 3) -> Tuple[List[str], bool]:
    """
    Wrap ZH text to multi-line subtitle display.

    Returns: (lines, hard_cut_used)
    """
```

#### Break-point priority
| 優先級 | Breaks | Score |
|---|---|---|
| Hard | `。！？!?` | 100 |
| Soft | `，、；：,;:` | 50 |
| Paren close | `）」』）]` | 30 |
| Paren open lookahead | `（「『（[` | 25 |
| **Hard cut**（無自然 break）| Last resort at cap | -1 |

#### Tail-tolerance
- Last line 允許 cap + tolerance（default +3）
- 避免 trailing punctuation 孤行
- 例：23c text + 「。」(1c) = 24c 1-line 而非 23c + 1c 兩行

#### Look-ahead extension（hard-cut 救生圈）
- 當 [1, cap] 範圍內無 break：search [cap+1, cap+tail_tol] 看有冇 break
- 若有：line cap 延長到該位置

### 2.4 全 Real Madrid file 驗證結果（82 segs）

| Metric | Value |
|---|---|
| 1 line | 56% |
| 2 lines | 43% |
| 3 lines | 1% |
| > 3 lines overflow | 0% |
| **Hard-cut（真切散名詞）**| **2.4%** |

ZH ASR file（警察學院 47 segs）：100% 1 line，0 hard-cut。

---

## 3. Implementation scope

### 3.1 Backend
| 檔案 | 動作 |
|---|---|
| **`backend/subtitle_wrap.py`**（新）| `wrap_zh()` + helper functions |
| `backend/asr/segment_utils.py` | 唔改（line-wrap 唔影響 ASR layer）|
| `backend/translation/post_processor.py` | 加 wrap pre-check（informational flag 而非強制切短）|
| `backend/renderer.py` `generate_ass()` | 將 wrap 結果 join with `\\N` 寫入 ASS dialogue line |
| `backend/profiles.py` | Profile schema 加 `font.line_wrap` block |
| `backend/config/languages/{en,zh}.json` | 加 `subtitle.line_cap` field |
| `backend/app.py` | `/api/files/<id>/subtitle.{srt,vtt,txt}` 加 `?wrap=` query param |

### 3.2 Frontend
| 檔案 | 動作 |
|---|---|
| **`frontend/js/subtitle-wrap.js`**（新）| JS 版 `wrapZh()`，algorithm 跟 backend 1:1 |
| `frontend/js/font-preview.js` | SVG `<text>` → 多 `<tspan>` 渲染 wrapped lines（共用 dashboard + proofread） |
| `frontend/index.html` | 直接攞 wrapped lines 出 SVG overlay |
| `frontend/proofread.html` | 同上 + segment table 顯示 wrapped preview |

### 3.3 Profile schema
```json
"font": {
  "...": "...",
  "line_wrap": {
    "enabled": true,
    "line_cap": 23,
    "max_lines": 3,
    "tail_tolerance": 3
  }
}
```

Backward-compat: 舊 profile 無 `line_wrap` block → fallback `enabled=false`（單 line 顯示，原 behavior）。

### 3.4 Subtitle preset
Profile field `subtitle_standard` enum 對應 line_wrap defaults：
- `netflix_originals`: cap=16, max=2, tol=2
- `netflix_general`: cap=23, max=2, tol=3
- `broadcast`: cap=28, max=3, tol=3 (default)

---

## 4. 邊際情況處理

### 4.1 Hard-cut（2.4% real Madrid case）
**Action**：寫入 segment metadata `wrap.hard_cut: true`，前端 proofread page 標 ⚠️ 提示用戶手動調整。

### 4.2 Trailing 標點孤行
**Action**：tail-tolerance algorithm 已解決（V_a 改前 7.3% → 改後 0%）。

### 4.3 ZH ASR raw segment 已短
**Action**：算法自然 short-circuit（`len(text) <= cap+tol` → return single line）。Zero overhead。

### 4.4 Reading speed
**Action**：v3.8 不 enforce reading speed（屬下個 phase，要 audio cue duration validation）。Plan 文檔提及將來可加 cps cap。

---

## 5. Tests

### 5.1 Backend pytest（`tests/test_subtitle_wrap.py`）
- 純 wrap algorithm 單元測試 × 15 case
  - 空字串、單行 ≤cap、單行 cap+tol 邊界、雙行普通、3 行普通
  - Hard-cut case [1] 重現
  - Tail-tolerance trailing 標點 case
  - Look-ahead cap+3 case
  - Max-lines overflow case
- ASS render integration test：wrap → `\\N` 注入 verification
- Profile validation test：`line_wrap` block schema

### 5.2 Frontend Playwright（`tests/e2e/test_line_wrap.spec.ts`）
- Dashboard overlay 顯示 2-line cue
- Proofread overlay 顯示 3-line cue
- 改 profile cap = 16 → overlay 即時 re-wrap
- 改 max_lines=2 → 3-line content overflow handling
- ZH ASR file 顯示單行（無 wrap 觸發）

### 5.3 Render fixture
`tests/fixtures/render_line_wrap_check.py`：用 7 demo segments 跑 burn-in，產生 reference video，比對 ASS 輸出 line-break。

---

## 6. Roll-out

### 6.1 Migration
- 新 Profile 預設 `line_wrap.enabled = true`
- 舊 Profile 自動 PATCH 加 default block（`line_wrap.enabled = false` 保留 1-line behavior）
- 用戶可喺 Profile editor 開關 + 調整 cap

### 6.2 Documentation
- CLAUDE.md：v3.8 section 描述 architecture + per-line cap
- README.md（繁中）：用戶介面說明
- PRD.md：feature status 📋 → ✅

---

## 7. Out of scope

- ✗ EN ASR segment 切短（保留現狀，long EN 無問題）
- ✗ Translation engine 改動（無 char cap 注入到 prompt）
- ✗ Reading speed (cps) enforcement
- ✗ Profile-level glossary 改動
- ✗ Render dynamic line-break（FFmpeg subtitle filter 動態 wrap，不可行）

呢啲全部留俾 v3.9+ 處理。
