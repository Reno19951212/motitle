# Subtitle Source Mode — Per-File 字幕語言模式（含雙語）

**Date:** 2026-04-28
**Status:** Approved

---

## Problem

而家所有字幕 output（live preview、burn-in render、SRT/VTT/TXT 下載）都係硬寫優先用 ZH 譯文：

- [renderer.py:145](backend/renderer.py#L145) `seg.get("zh_text", "")` — burn-in 永遠係 ZH
- [index.html:3091](frontend/index.html#L3091) + [proofread.html:1922](frontend/proofread.html#L1922) — preview overlay 用 `zh || en`，譯文勝
- 後端 `/api/files/<id>/subtitle.{srt,vtt,txt}` 路由（`format_subtitle_*` family）— 未驗證但同樣只 emit ZH

用戶冇辦法揀：
- 想要英文原文交付（原語言廣播）— 撈唔到
- 想要雙語上下兩行（廣播 / 串流常見）— 冇 option
- 翻譯仲未跑、想睇住 EN 校對切句 — 要等 ZH 出嚟先有得睇

---

## Goal

**「字幕來源模式」（subtitle source mode）— per-file 設定**，default 跟 active Profile 嘅模式（亦可 per-file override）。共 4 個模式：

- **`auto`** — ZH-if-exists else EN（保持現狀行為作為 default）
- **`en`** — 永遠用 EN 原文（即使 ZH 已翻譯）
- **`zh`** — 永遠用 ZH 譯文；缺失段自動 fall back EN 並警告
- **`bilingual`** — 雙語：EN + ZH 兩行；上下次序 per-file 可揀

**統一影響範圍**（一致性原則 — 預覽 = 燒入 = 下載）：
- Dashboard live overlay
- Proofread editor video overlay
- Burn-in render（MP4 / MXF / XDCAM）
- SRT / VTT / TXT 下載

---

## Non-Goals

- 唔做「同一條片同時 render 多個版本」（option δ — 一鍵 EN-only + ZH-only + bilingual 三個版本）— 留俾日後
- 唔做 per-segment 混合語言 mode（即唔做 segment-level toggle —「呢段 EN、嗰段 ZH」）— 暫無用例
- 唔做 EN / ZH 字級 styling 分離（雙語兩行用同一 font config + size）— 廣播實踐通常都係同 size
- 唔做 source language ≠ EN 嘅情況（系統現時假設 ASR = EN；將來 multi-language ASR 一齊改）— 但 schema 設計時用 `source` / `translation` 概念名而唔係 `en` / `zh`，方便日後

---

## Design

### 1. 數據模型

#### Profile schema 加 default

```json
"font": {
  "family": "...", "size": 35, ...,
  "subtitle_source": "auto",       // NEW. enum: auto|en|zh|bilingual
  "bilingual_order": "en_top"      // NEW. enum: en_top|zh_top. 只喺 subtitle_source==bilingual 時生效
}
```

擺喺 `font` 而非新欄位 — 因為 subtitle source 同 font 渲染緊密相關（雙語會影響 line-height / margin），未來如要拆 styling 都喺同一個邏輯區。

預設值 backward-compat：缺欄位等同 `subtitle_source: "auto"` + `bilingual_order: "en_top"`。

#### File registry 加 per-file override

```python
{
  "id": "...",
  "subtitle_source": null,     // NEW. null = inherit from profile; otherwise enum
  "bilingual_order": null,     // NEW. null = inherit from profile
  ...
}
```

`null` 表示「跟 profile」。設值表示 override。

#### 解析優先級

```python
def resolve_subtitle_source(file_entry, active_profile):
    return (
        file_entry.get("subtitle_source")
        or active_profile.get("font", {}).get("subtitle_source")
        or "auto"
    )
```

### 2. Backend 改動

#### A. `renderer.py` `generate_ass()` 簽名擴展

```python
def generate_ass(
    self,
    segments: List[dict],
    font_config: dict,
    *,
    subtitle_source: str = "auto",   # NEW
    bilingual_order: str = "en_top", # NEW
) -> str:
```

加 helper：

```python
def _resolve_segment_text(seg: dict, mode: str, order: str) -> str:
    en = (seg.get("text") or seg.get("en_text") or "").strip()
    zh = strip_qa_prefixes(seg.get("zh_text", "")).strip()

    if mode == "en":
        return en
    if mode == "zh":
        return zh or en  # per-segment fallback
    if mode == "bilingual":
        # 缺一邊就單行；兩邊都有就上下排
        if not en: return zh
        if not zh: return en
        return f"{en}\\N{zh}" if order == "en_top" else f"{zh}\\N{en}"
    # auto
    return zh or en
```

`generate_ass()` Dialogue line 由：
```python
text = strip_qa_prefixes(seg.get("zh_text", "")).replace("\r","").replace("\n","\\N")
```
改為：
```python
text = _resolve_segment_text(seg, subtitle_source, bilingual_order).replace("\r","").replace("\n","\\N")
```

呢個改動同時 cover：
- `seg.zh_text` 為空時 EN 補位
- bilingual 嘅 `\\N` 換行
- mode == `en` 時完全唔睇 `zh_text`

#### B. `app.py` render handler 傳遞 mode

`/api/render` 端傳入 `subtitle_source` / `bilingual_order` 落 `RenderJob`，之後 `generate_ass()` 拎到。Resolve 順序：

```python
file_entry = _file_registry[file_id]
profile = _profile_manager.get_active() or {}
subtitle_source = (
    request_body.get("subtitle_source")            # 渲染 modal override
    or file_entry.get("subtitle_source")            # per-file
    or profile.get("font", {}).get("subtitle_source")  # profile default
    or "auto"
)
# bilingual_order resolve 同 pattern
```

警告 toast：post 之前 backend 計一次「ZH-mode 但 zh_text 缺失嘅 segment 數」回傳俾 frontend 確認，避免靜悄悄渲染缺失內容。

```python
missing_count = 0
if subtitle_source == "zh":
    for s in segments:
        if not (s.get("zh_text") or "").strip():
            missing_count += 1
return jsonify({"job_id": ..., "warning_missing_zh": missing_count})
```

Frontend 收到 `warning_missing_zh > 0` 即時 toast：「N 段缺少譯文，會用英文原文替代」。

#### C. `format_subtitle_*` 修改

`/api/files/<id>/subtitle.srt`、`.vtt`、`.txt` 三個 endpoint 共用 helper 取 segment text：

```python
def _segment_text_for_export(seg, mode, order):
    return _resolve_segment_text(seg, mode, order)  # 同 renderer 共用
```

每個 export route 同 render 一樣 resolve 出 mode（query param > file > profile > auto），然後逐 seg 呼叫 helper。

Helper **可以放喺 `renderer.py` export**（因為 ASS / SRT / VTT / TXT 都需要同樣 EN/ZH/bilingual 邏輯，只係 line break 同 timestamp 格式唔同）。或者 extract 去新 module `subtitle_text.py` — 由於 export 同 render 嘅依賴方向唔同（render → renderer 已經 import；route → 可能要繞），新 module 較乾淨。

**決定：放新 module `backend/subtitle_text.py`**：

```python
# backend/subtitle_text.py
def strip_qa_prefixes(text: str) -> str: ...
def resolve_segment_text(seg: dict, mode: str = "auto", order: str = "en_top") -> str: ...
```

`renderer.py` import 嗰兩個 helper（移走原本 `strip_qa_prefixes` 定義）。`app.py` 嘅 export route 都 import。一份 logic、三個 caller。

### 3. Frontend 改動

#### A. File card 加 mode dropdown

`renderFileCard()` 入面，喺 ▶ 渲染 button 旁邊加 mini selector：

```html
<select class="fc-source-mode" data-file-id="${f.id}" onchange="updateFileSubtitleSource(this)">
  <option value="">— 跟 Profile（${profileMode}）—</option>
  <option value="auto"      ${f.subtitle_source==='auto' ? 'selected':''}>Auto（智能切換）</option>
  <option value="en"        ${f.subtitle_source==='en' ? 'selected':''}>EN 原文</option>
  <option value="zh"        ${f.subtitle_source==='zh' ? 'selected':''}>ZH 譯文</option>
  <option value="bilingual" ${f.subtitle_source==='bilingual' ? 'selected':''}>雙語</option>
</select>
```

`onchange` PATCH `/api/files/<id>` body `{subtitle_source: value || null}` (null = clear override = inherit profile)。

如果揀 `bilingual`，dropdown 旁邊出多一個小 selector「上：EN / 上：ZH」：

```html
<select class="fc-bilingual-order" data-file-id="${f.id}" onchange="updateFileBilingualOrder(this)" 
        ${f.subtitle_source==='bilingual' ? '' : 'style="display:none;"'}>
  <option value="en_top">EN 上 / ZH 下</option>
  <option value="zh_top">ZH 上 / EN 下</option>
</select>
```

#### B. Proofread page header 加同款 dropdown

[proofread.html](frontend/proofread.html) 頂 bar 加：

```html
<div class="rv-header-source">
  <label>字幕來源</label>
  <select id="proofreadSourceMode" onchange="...">…</select>
  <select id="proofreadBilingualOrder" onchange="..." style="display:none;">…</select>
</div>
```

PATCH file 同 dashboard 一樣，後端為單一 source of truth。

#### C. Live overlay reflect mode

兩個 overlay 都改 helper：

```js
// 共用
function pickSubtitleText(seg, mode, order) {
  const en = (seg.en || seg._en_text || seg.text || '').trim();
  const zh = (seg.zh || seg.zh_text || '').trim();
  if (mode === 'en') return en;
  if (mode === 'zh') return zh || en;
  if (mode === 'bilingual') {
    if (!en) return zh;
    if (!zh) return en;
    return order === 'en_top' ? `${en}\n${zh}` : `${zh}\n${en}`;
  }
  return zh || en; // auto
}
```

`FontPreview.updateText()` 已經 split on `\n` + `\\N` 渲染兩行（看 [font-preview.js](frontend/js/font-preview.js) 嘅 `<tspan>` stack 邏輯）— 雙語直接 work。

Dashboard `updateSubtitleOverlay()` 同 proofread `setActiveSegment()` 都改用呢個 helper。

#### D. Profile 編輯器 field

Profile 表單嘅「字型」區塊加 2 個欄位：
- Subtitle source default（dropdown，4 個 mode + Auto）
- Bilingual order default（dropdown，2 個選項，只喺 source = bilingual 時可見）

PATCH `/api/profiles/<id>` body 寫入 `font.subtitle_source` / `font.bilingual_order`。

#### E. 渲染 modal 加 mode override

渲染 modal 嘅 format card 區塊上面加多一行「字幕來源」selector：

```
字幕來源    [ 跟 file（zh）▾ | EN | ZH | 雙語 ]   [ 上：EN / 上：ZH ]
```

揀「跟 file」就唔送 `subtitle_source` 落 backend，由 backend resolve；揀其他 mode 就 override per-render。

POST body 加 `subtitle_source` / `bilingual_order` optional fields。

#### F. ZH-mode 缺失警告 toast

如果 backend 返回 `warning_missing_zh > 0`，渲染中嘅 progress modal 開首彈個 amber toast：

```
⚠ 4 段未翻譯，會用英文原文替代渲染。
```

Toast 本身唔阻止渲染（背景已開始）— 純資訊性。

### 4. SRT / VTT / TXT export 一致性

Export route 加 query param `?source=auto|en|zh|bilingual`（optional override）+ `?order=en_top|zh_top`：

```
GET /api/files/<id>/subtitle.srt
GET /api/files/<id>/subtitle.srt?source=en
GET /api/files/<id>/subtitle.srt?source=bilingual&order=zh_top
```

冇 query param 就 fall through file → profile → auto。

Frontend 下載 link build 嗰陣加 query string：

```js
const mode = resolveSubtitleSource(file, activeProfile);
const order = resolveBilingualOrder(file, activeProfile);
const srtUrl = `${API_BASE}/api/files/${file.id}/subtitle.srt?source=${mode}&order=${order}`;
```

**SRT 雙語特殊處理**：SRT 用 raw newline 分行，VTT 一樣，TXT 用換行 — `_resolve_segment_text` 出 `\\N` 嘅 ASS 寫法要喺 caller 換成各自格式：

| Format | line break |
|---|---|
| ASS  | `\\N`（escape）|
| SRT  | `\n`（real newline）|
| VTT  | `\n` |
| TXT  | `\n` |

Helper 可以收 `line_break` 參數：

```python
def resolve_segment_text(seg, mode="auto", order="en_top", line_break="\n") -> str:
    ...
    return f"{en}{line_break}{zh}" if order == "en_top" else f"{zh}{line_break}{en}"
```

ASS caller 傳 `line_break="\\N"`，其他傳 `"\n"`。

### 5. CLAUDE.md 更新

加新 section 描述 subtitle source mode；REST endpoint table 加 query param 說明；Profile schema 加 `font.subtitle_source` + `font.bilingual_order`；File registry 加 `subtitle_source` + `bilingual_order` 欄位。

---

## Edge Cases

| 場景 | 行為 |
|---|---|
| File 冇 `subtitle_source` 欄位（legacy registry）| `null` 處理 → fall through profile → 默認 `auto` → 行 backward-compat 行為（ZH-or-EN） |
| Profile 冇 `font.subtitle_source` | 默認 `auto` |
| `bilingual` mode + segment 只有 EN 冇 ZH | 該 segment 顯示單行 EN（per-segment 容錯）|
| `bilingual` mode + segment 兩邊都空 | Skip（同 ASS 已有 zero-duration skip 邏輯一致）|
| `zh` mode + segment 缺 ZH | Per-segment fallback EN；render 前 toast 警告總缺失數 |
| `auto` mode 中段轉 `zh`（用戶撳 dropdown）| File registry 寫入新值；下次 fetch / render / export 即時生效；preview 即時 re-render |
| Active profile 切換（其他工作流動作）→ profile default subtitle_source 變 | 已有 file override 嘅唔受影響；冇 override 嘅 file 會跟新 profile 嘅 default |
| 渲染 modal override + per-file setting 衝突 | 渲染 modal 取代 per-file（per-render 嘅一次性 override）|
| 雙語但 font 太大溢出畫面（35pt × 2 行 + margin 40 = 約 110px）| 不阻止；用戶責任揀啱 size。Future enhancement: bilingual 自動縮 0.85x 比例，呢版本暫不實作 |
| Mid-transcription（ZH 仲未到）+ user 揀咗 `zh` mode | Per-segment fallback：每個只有 EN 嘅 segment 即時用 EN 渲染 preview。Toast 唔彈（warning 只喺 render 時 trigger，preview 容錯靜默）|
| 揀 `bilingual` 但 ZH 完全缺（譯文未跑）| 同上，所有 segment 顯示 EN 單行；render 時冇 zh_text → bilingual 出單行 EN（即等同 EN-mode）— 唔需要特別 case |
| 渲染中改 mode | 已渲染 job 唔受影響（已固化）；下次渲染用新 setting |

---

## API Changes Summary

| Endpoint | Change |
|---|---|
| `PATCH /api/profiles/<id>` | 接受 `font.subtitle_source` + `font.bilingual_order`，validate enum |
| `PATCH /api/files/<id>` | NEW behavior：接受 `subtitle_source` + `bilingual_order`（null 清 override） |
| `POST /api/render` | body 加 optional `subtitle_source` + `bilingual_order`；response 加 `warning_missing_zh: int` |
| `GET /api/files/<id>/subtitle.{srt,vtt,txt}` | 加 optional query param `?source=...&order=...`；冇就 resolve 由 file → profile → auto |
| `GET /api/files` | response 每個 file dict 加 `subtitle_source` + `bilingual_order` 欄位（null 表 inherit）|
| `GET /api/files/<id>` | 同上 |

---

## Testing

### Backend (pytest, `backend/tests/test_subtitle_source_mode.py`)

- `test_resolve_text_auto_with_zh` — `auto` mode + zh_text 存在 → 返 zh
- `test_resolve_text_auto_without_zh` — `auto` + 冇 zh_text → 返 en
- `test_resolve_text_en_mode` — `en` mode → 永遠返 en，即使有 zh_text
- `test_resolve_text_zh_mode_fallback` — `zh` mode + 段缺 zh_text → 返 en
- `test_resolve_text_bilingual_en_top` — 兩邊都有 → `en\\Nzh`
- `test_resolve_text_bilingual_zh_top` — order=zh_top → `zh\\Nen`
- `test_resolve_text_bilingual_partial` — 只有 en → 單行 en；只有 zh → 單行 zh
- `test_resolve_text_strips_qa_prefixes` — `[long]` / `[review]` flag prefixes 唔會洩入
- `test_resolve_text_line_break_param` — line_break=`\n` 出 raw newline；line_break=`\\N` 出 ASS escape
- `test_generate_ass_uses_subtitle_source` — `generate_ass(..., subtitle_source="en")` → ASS Dialogue line 全部 EN
- `test_generate_ass_bilingual` — bilingual 段含 `\\N`
- `test_render_endpoint_returns_warning_missing_zh` — POST `/api/render` ZH-mode 5 段中 2 段缺 ZH → response `warning_missing_zh: 2`
- `test_subtitle_export_srt_with_source_param` — GET `?source=en` → SRT 全 EN
- `test_subtitle_export_srt_bilingual_zh_top` — bilingual + zh_top → SRT 入面每 cue 兩行（zh\\nen）
- `test_resolve_priority_render_modal_overrides_file` — render body 有 source → 唔睇 file
- `test_resolve_priority_file_overrides_profile` — file 有 source → 唔睇 profile
- `test_resolve_priority_profile_default_auto` — 三層都冇 → `auto`
- `test_patch_file_subtitle_source` — PATCH file 寫入欄位
- `test_patch_file_clear_override` — PATCH file `subtitle_source: null` → 清空回 inherit

### Frontend (Playwright smoke `/tmp/check_subtitle_source_mode.py`)

- **Scenario A**: File card mini dropdown 揀 `en` → PATCH 觸發 + body 含 `subtitle_source: "en"`
- **Scenario B**: 揀 `bilingual` → bilingual order dropdown 即時可見；揀 `zh_top` → PATCH body 含兩個欄位
- **Scenario C**: 切換 mode 後 dashboard live overlay 即時反映（mock segment 投入 `_en_text` + `zh_text`，confirm overlay text 跟 mode 變）
- **Scenario D**: Proofread page mode dropdown PATCH file + overlay 即時更新
- **Scenario E**: 渲染 modal 揀 mode → POST body 含 override
- **Scenario F**: Profile 編輯器 PATCH `font.subtitle_source` → file card 入面顯示「跟 Profile（XX）」placeholder 變

---

## Out of Scope（將來可考慮）

- Multi-rendition 一鍵渲染多個版本（option δ）
- Per-segment EN/ZH 混合
- 雙語 EN/ZH 唔同 size / color 設定
- Bilingual 自動縮放（auto 0.85x）防溢出
- ASR source language ≠ EN 嘅 case
- Subtitle source 嘅 socket event 跨 tab 同步（profile_updated 已 cover Profile-level，per-file change 可改用新 event）

---

## Implementation Order Hint

逐步實施（每步可獨立 commit）：

1. Backend `subtitle_text.py` helper + pytest（無 UI 變化）
2. Backend `renderer.py` 接 helper、`generate_ass()` 加 mode
3. Backend `/api/render` 加 mode resolve + `warning_missing_zh`
4. Backend `/api/files/<id>/subtitle.{srt,vtt,txt}` 加 query param
5. Backend `PATCH /api/profiles/<id>` + `PATCH /api/files/<id>` 接受新欄位
6. Frontend file card mini dropdown
7. Frontend Proofread header dropdown + overlay helper
8. Frontend dashboard overlay 改用 helper
9. Frontend 渲染 modal 加 override row
10. Frontend Profile editor 加 default field
11. CLAUDE.md 更新
12. Playwright smoke + GREEN
