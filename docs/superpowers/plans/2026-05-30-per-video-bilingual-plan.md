# Subsystem B1 — per-video 雙語(第一/第二語言)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 role-based(第一/第二)語言抽象 + per-file `languages` descriptor + 統一選擇器,令 Profile（ASR原文/MT譯文）同 V6（refiner + 可選第二）用同一套語言選擇模型;`resolve_segment_text` 由硬編碼 EN/ZH 改 role-aware。零新 MT（B2 deferred）、零強制 storage migration。

**Architecture:** `subtitle_text.py` 加 `first`/`second` mode + `first_field`/`second_field` 參數（caller 按 kind 供應）+ `resolve_language_descriptor()`。`app.py` /api/files 加 `languages`、render/export/PATCH 接 role。frontend dropdown 由 descriptor 動態 render。legacy `en`/`zh`/`auto`/`bilingual` 全部保留（en→first / zh→second alias）。

**Tech Stack:** Python 3.9 / pytest；Vanilla JS / Playwright。後端 :5001。

**Spec:** [docs/superpowers/specs/2026-05-30-per-video-bilingual-design.md](../specs/2026-05-30-per-video-bilingual-design.md)

---

## File Structure
| 檔案 | 動作 |
|---|---|
| `backend/subtitle_text.py` | **Modify** — first/second mode + first_field/second_field params + `resolve_language_descriptor()` |
| `backend/tests/test_subtitle_text.py` | **Modify/Create** — first/second + legacy alias + descriptor tests |
| `backend/app.py` | **Modify** — /api/files `languages`、`GET /api/files/<id>/languages`、render/export/PATCH role-aware |
| `backend/tests/test_bilingual_api.py` | **Create** — descriptor + role-aware endpoint tests |
| `frontend/index.html` | **Modify** — file-card 語言 dropdown 由 descriptor 動態 render；pickSubtitleText role-based |
| `frontend/proofread.html` | **Modify** — `#proofreadSourceMode` 同樣 descriptor-driven |
| `frontend/tests/test_bilingual_selector.spec.js` | **Create** — 兩 kind selector |

---

## Task 1: subtitle_text — role-based resolver + descriptor

**Files:** Modify `backend/subtitle_text.py` + `backend/tests/test_subtitle_text.py`

- [ ] **Step 1: 讀現有 subtitle_text.py 全文**（理解 resolve_segment_text / VALID_SUBTITLE_SOURCES / resolve_subtitle_source / resolve_bilingual_order 現行為，~97 行）。

- [ ] **Step 2: 擴 VALID + generalize resolver**

(a) `VALID_SUBTITLE_SOURCES` 加 `"first"`, `"second"`（保留 `auto`/`en`/`zh`/`bilingual`）。

(b) `resolve_segment_text` 加 keyword-only 參數 `first_field` / `second_field`（預設 None → legacy）。內部：
```python
def _txt(seg, field, legacy_fallbacks):
    if field:
        return (seg.get(field) or "").strip()
    for f in legacy_fallbacks:
        v = seg.get(f)
        if v: return v.strip()
    return ""

def resolve_segment_text(seg, mode, order="en_top", line_break="\n", *,
                         first_field=None, second_field=None):
    first  = _txt(seg, first_field,  ["text", "en_text"])
    second = _txt(seg, second_field, ["zh_text"])
    second = strip_qa_prefixes(second)
    m = (mode or "auto").lower()
    if m == "en":  m = "first"
    if m == "zh":  m = "second"
    if m == "first":  return first or second
    if m == "second": return second or first
    if m == "bilingual":
        a, b = (first, second) if order == "en_top" else (second, first)
        if a and b: return a + line_break + b
        return a or b
    # auto: second(譯文)-if-present else first
    return second or first
```
（保留 `strip_qa_prefixes` import / 既有 helper。legacy en→first / zh→second 確保現有 caller 行為不變。）

(c) 加 descriptor helper：
```python
def resolve_language_descriptor(file_entry, active_cfg=None):
    """Return ordered [{role,lang,label}] for a file. Kind from active_kind.
    Profile: first=ASR source lang(原文), second=zh(譯文).
    V6: first=source_lang(原文); second only if a 2nd by_lang key exists."""
    kind = (file_entry or {}).get("active_kind", "profile")
    tr = (file_entry or {}).get("translations") or []
    if kind == "pipeline_v6":
        src = (tr[0].get("source_lang") if tr else None) or "zh"
        langs = [{"role": "first", "lang": src, "label": "原文"}]
        # second = any by_lang key != src (B2 populates; absent today)
        extra = []
        for row in tr:
            for k in (row.get("by_lang") or {}):
                if k != src and k not in extra:
                    extra.append(k)
        if extra:
            langs.append({"role": "second", "lang": extra[0], "label": "譯文"})
        return langs
    # profile
    src = "en"
    if active_cfg and active_cfg.get("asr"):
        src = active_cfg["asr"].get("language", "en")
    return [
        {"role": "first", "lang": src, "label": "原文"},
        {"role": "second", "lang": "zh", "label": "譯文"},
    ]
```

- [ ] **Step 3: tests**

`backend/tests/test_subtitle_text.py`（更新/新增）：
```python
from subtitle_text import resolve_segment_text, resolve_language_descriptor

def test_legacy_en_zh_unchanged():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "en") == "Hello"
    assert resolve_segment_text(seg, "zh") == "你好"

def test_first_second_modes():
    seg = {"text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "first") == "Hello"
    assert resolve_segment_text(seg, "second") == "你好"

def test_bilingual_order():
    seg = {"text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "bilingual", "en_top", "\n") == "Hello\n你好"
    assert resolve_segment_text(seg, "bilingual", "zh_top", "\n") == "你好\nHello"

def test_custom_fields_v6_like():
    seg = {"zh_text": "粵語", "by_lang": {}}
    # V6: first_field=zh_text mirror (refiner output)
    assert resolve_segment_text(seg, "first", first_field="zh_text") == "粵語"

def test_descriptor_profile():
    d = resolve_language_descriptor({"active_kind": "profile"}, {"asr": {"language": "en"}})
    assert [x["role"] for x in d] == ["first", "second"]
    assert d[0]["lang"] == "en" and d[1]["lang"] == "zh"

def test_descriptor_v6_single():
    entry = {"active_kind": "pipeline_v6", "translations": [{"source_lang": "zh", "by_lang": {"zh": {}}}]}
    d = resolve_language_descriptor(entry)
    assert len(d) == 1 and d[0]["lang"] == "zh"

def test_descriptor_v6_with_second():
    entry = {"active_kind": "pipeline_v6", "translations": [{"source_lang": "zh", "by_lang": {"zh": {}, "en": {}}}]}
    d = resolve_language_descriptor(entry)
    assert len(d) == 2 and d[1]["lang"] == "en"
```

Run: `cd backend && source venv/bin/activate && pytest tests/test_subtitle_text.py -v` → expect 全綠（含既有）。

- [ ] **Step 4: Commit**
```bash
git add backend/subtitle_text.py backend/tests/test_subtitle_text.py
git commit -m "feat(lang): role-based (first/second) resolver + per-file language descriptor"
```

---

## Task 2: app.py — /api/files languages + role-aware render/export/PATCH

**Files:** Modify `backend/app.py` + Create `backend/tests/test_bilingual_api.py`

- [ ] **Step 1: /api/files 加 `languages` + 新 GET /api/files/<id>/languages**

喺 `GET /api/files` 每 file dict（~line 3596-3615）加 `"languages": resolve_language_descriptor(entry, _active_cfg_for(entry))`（`_active_cfg_for` = 取該 file 嘅 profile/pipeline config:Profile 由 active_id 查 profile;V6 由 active_pipeline_snapshot。若難取就傳 None，descriptor 對 Profile 用預設 en/zh）。新增 `GET /api/files/<id>/languages` 返 `{languages: [...]}`（login_required + owner check，跟既有 pattern）。

- [ ] **Step 2: render/export/PATCH role-aware**

- `_resolve_subtitle_source` / `resolve_subtitle_source`：接受 first/second（已喺 VALID）。
- `POST /api/render`（~2820）+ `GET /api/files/<id>/subtitle.<fmt>`（~3703）：解析該 file 嘅 descriptor → 計 `first_field`/`second_field`（Profile: first_field=None[legacy text/en_text]、second_field='zh_text'；V6: first_field='zh_text'[refiner mirror]或 `{source_lang}_text`、second_field= 第二 by_lang 對應 mirror，今日無）→ 傳入 `resolve_segment_text(..., first_field=, second_field=)`。把現有「V6 zh-source 拒絕 subtitle_source=en」guard 改為「descriptor 無對應 role → warning/跳過」（唔再硬 en/zh）。
- `PATCH /api/files/<id>/translations/<idx>`（~2549）：接 optional body `role`（'first'|'second'，預設按 kind:Profile 'second'=zh_text 向後兼容、V6 'first'=refiner）→ 寫對應 field（V6 仍 dual-write by_lang[lang]）。

- [ ] **Step 3: tests**

`backend/tests/test_bilingual_api.py`：descriptor 喺 /api/files 出現（Profile 2、V6 1）;`GET /languages` 回正確;render with subtitle_source='first'/'second' 解析正確 text;PATCH role='first'/'second' 寫對 field;legacy en/zh 仍 work。

Run: `cd backend && source venv/bin/activate && pytest tests/test_bilingual_api.py tests/test_subtitle_text.py -v` → 全綠。再跑既有 render/export test 確認無 regression（`ls tests/ | grep -iE "render|subtitle|export"` 後跑）。

- [ ] **Step 4: Commit**
```bash
git add backend/app.py backend/tests/test_bilingual_api.py
git commit -m "feat(lang): /api/files languages descriptor + role-aware render/export/PATCH"
```

---

## Task 3: Frontend — descriptor-driven 語言選擇器（兩個 surface）

**Files:** Modify `frontend/index.html`, `frontend/proofread.html` + Create `frontend/tests/test_bilingual_selector.spec.js`

- [ ] **Step 1: index.html file-card dropdown + pickSubtitleText**

(a) file-card 語言 dropdown（~2125-2166，現「原文 EN / 譯文 ZH / 雙語 / 跟 Profile」）改為由 `file.languages` descriptor 動態 render：`第一語言:<label/lang> | 第二語言:<label/lang>（僅當 descriptor 有 second）| 雙語（僅當有 second）| 跟 Profile`。揀「第一」PATCH `subtitle_source='first'`、「第二」='second'、雙語='bilingual'。
(b) `pickSubtitleText(seg, mode, order)` JS mirror：加 first/second（legacy en→first/zh→second），mirror backend resolver。

- [ ] **Step 2: proofread.html `#proofreadSourceMode`**

同樣由該 file 嘅 descriptor（fetch `/api/files/<id>/languages` 或用已 load 嘅 fileInfo.languages）動態 render 選項;V6 無第二語言時隱藏第二/雙語選項。

- [ ] **Step 3: Playwright**

`frontend/tests/test_bilingual_selector.spec.js`@1512×982 兩 kind:Profile file-card dropdown 有「第一語言 / 第二語言 / 雙語」;V6 file-card dropdown 只有「第一語言」（無第二/雙語）。揀「第二語言」PATCH subtitle_source='second'（Profile）。

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_bilingual_selector.spec.js --reporter=line`

- [ ] **Step 4: Commit**
```bash
git add frontend/index.html frontend/proofread.html frontend/tests/test_bilingual_selector.spec.js
git commit -m "feat(ui): descriptor-driven first/second language selector (both surfaces)"
```

---

## Task 4: 整合驗證 + 文檔 [Opus 判讀]

- [ ] **Step 1: 重啟 backend + 截圖兩 kind 選擇器 + 渲染 smoke**

重啟 backend。截圖 Profile + V6 file-card 語言 dropdown（controller 判讀:Profile 有第一/第二/雙語、V6 只第一）。curl render 一條 Profile file subtitle_source='first' vs 'second' 確認輸出對應 原文/譯文。

- [ ] **Step 2: regression**

`cd backend && pytest tests/test_subtitle_text.py tests/test_bilingual_api.py -q` + 既有 render/export tests。Playwright bilingual selector。

- [ ] **Step 3: 清理 + CLAUDE.md + README**

刪 diag artifact。CLAUDE.md 加 Subsystem B1 entry（role-based 語言模型 / descriptor / 統一選擇器 / legacy 兼容 / B2 deferred / Spec+Plan 連結）。README 加一句（繁中）video 可揀第一/第二語言字幕。

- [ ] **Step 4: Commit**
```bash
git add CLAUDE.md README.md && git commit -m "docs: record Subsystem B1 per-video bilingual language model"
```

---

## 驗收標準（對應 spec §8）
1. /api/files `languages` descriptor:Profile=[first原文, second譯文]、V6=[first原文]。
2. 選擇器顯示實際語言;V6 無第二時唔出第二/雙語。
3. resolve_segment_text role-based 正確;legacy en/zh 不變（既有 test 綠）。
4. render/export/PATCH 接 first/second;Profile zh 輸出不變。
5. 兩 kind regression 綠 + 新 test 綠。
6. B2（V6 產生第二語言）deferred,by_lang multi-key + translators key 結構預留。

## Self-Review notes
- **Spec coverage**：§3.1 descriptor→T1+T2；§3.2 role→field→T1(resolver)+T2(caller 供 field)；§3.3 選擇器→T1(VALID)+T3(UI)；§4 backend→T1+T2、frontend→T3；§8→上表。全覆蓋。
- **Consistency**：`resolve_segment_text(... first_field, second_field)`、`resolve_language_descriptor`、subtitle_source ∈ {auto,en,zh,bilingual,first,second}、role 'first'/'second' 喺 spec/resolver/api/frontend/tests 一致。
- **No placeholders**：resolver + descriptor 全 code;app.py/frontend 因龐大故描述 transformation + anchor + grep-before-change。
- **B2 明確 deferred**：此 plan 唔 build V6 第二語言產生（translator stage），只預留結構。
