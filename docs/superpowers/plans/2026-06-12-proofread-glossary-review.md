# 校對頁 Glossary Review 重設計 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將舊 scan→preview→apply 骨架翻新成 output_lang 檔嘅主力詞彙表互動：panel 真多選（檔案 glossary_ids）→ 機械掃描雙軌 modal → 逐項剔選 → 逐項 AI 套用（keep_status、三庫同步），並升級段落級「詞彙對照」。

**Architecture:** 掃描邏輯做成 pure function 加喺 `output_lang_glossary.py`（同 pipeline 共用 `_filter_source_side`/`_filter_target_side`/`route_for_output`，保證掃描=pipeline 行為）；AI 套用 prompt/parse 做成 pure module `glossary_review.py`（仿 `ai_edit.py`）；兩條新 route（preview 純讀 / apply-item 逐項寫）+ PATCH 擴展；前端新 `js/glossary-review.js`（仿 `js/find-replace.js`）+ panel 改造。Spec：`docs/superpowers/specs/2026-06-12-proofread-glossary-review-design.md`。

**Tech Stack:** Python 3.9 (Flask) + vanilla JS。測試：pytest（單檔跑，suite 有已知 order-dependent 污染）+ Playwright python（E2E，隔離 :5002）。

---

## AI Model 分工（用戶要求）

| Model | 負責 | 理由 |
|---|---|---|
| **Fable 5**（主 session，orchestrator） | 任務派發、每 task 之間 review、Task 10 Validation-First 實證判讀、Task 11 E2E 執行判讀、Task 13 review findings 修正、最終整合/commit/merge | 判斷密集、要全局 context |
| **Opus**（subagent `model: "opus"`） | Task 1、2、4、5、6（後端核心：matching/路由/鎖/衝突/三庫同步）+ Task 13 adversarial review agents | 併發語義同雙軌路由係本 feature 最易出錯位 |
| **Sonnet**（subagent `model: "sonnet"`） | Task 3、7、8、9、12（pure prompt module、前端 panel/modal/detail、docs） | 規格已寫死、實施機械性高，Sonnet 性價比最好 |

派發方式：subagent-driven 模式下，dispatch 每個 task 嘅 Agent/Workflow call 帶 `model` 參數（`"opus"` / `"sonnet"`）；Fable 5 唔落 model override（主 loop 自身）。

---

## File Structure

| 檔案 | 動作 | 職責 |
|---|---|---|
| `backend/output_lang_glossary.py` | 修改 | ① 兩個 filter 候選 dict 加 `entry_id`/`glossary_id`（add-only）② `glossary_stage` 嘅 changes 加 `lang` ③ 新 pure function `scan_track()` |
| `backend/glossary_review.py` | 新增 | AI 套用嘅 prompt build / response parse / 結果驗證（pure，無 Flask/IO） |
| `backend/app.py` | 修改 | 新 route `glossary-preview` + `glossary-apply-item`；`patch_file` 加 `glossary_ids`/`glossary_llm`；`glossary-reapply` 補 render-409 |
| `frontend/js/glossary-review.js` | 新增 | 掃描 modal 全邏輯（render/tick/串行套用/跳段/重新掃描） |
| `frontend/proofread.html` | 修改 | panel 多選改造 + 掣改名/confirm + modal 容器 markup + 詞彙對照升級 + 引入新 js |
| `backend/tests/test_glossary_review_scan.py` | 新增 | `scan_track` 單元測試 |
| `backend/tests/test_glossary_review_module.py` | 新增 | `glossary_review.py` 單元測試 |
| `backend/tests/test_glossary_review_routes.py` | 新增 | preview / apply-item / PATCH 擴展 / reapply 補閘 route 測試 |
| `backend/tests/test_output_lang_glossary.py` | 修改 | T1 嘅 entry_id/lang 測試 |
| `docs/superpowers/specs/2026-06-12-glossary-apply-item-validation-tracker.md` | 新增（T10） | 套用 prompt 實證記錄 |

執行紀律（每個 task 嘅 subagent 都要遵守）：
- 喺 worktree `…/.claude/worktrees/grocery-fix` 工作，branch `worktree-glossary-fix`。
- 跑測試用主 checkout venv：`source "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/activate"`，並 `export FLASK_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')`。
- **單檔跑測試**（full suite 有已知 order-dependent 紅，唔好信）。
- 唔好 commit：`backend/data`（symlink）、`backend/data.e2e-bak/`、`backend/scripts/v5_prototype/venv_qwen`（symlink）、`backend/config/settings.json`、`backend/config/glossaries/*.json`、`backend/.env`、`backend/config/license.json`。

---

### Task 0: Baseline（Fable 5，1 分鐘）

- [ ] **Step 0.1**：確認 branch + 跑受影響測試檔 baseline

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/.claude/worktrees/grocery-fix/backend"
git branch --show-current   # 預期: worktree-glossary-fix
python -m pytest tests/test_output_lang_glossary.py tests/test_glossary.py -q
```
預期：全 PASS（33 + 41）。

---

### Task 1: filter 候選帶 id + glossary_stage changes 帶 lang　〔**執行 model：Opus**〕

**Files:**
- Modify: `backend/output_lang_glossary.py`（`_filter_source_side` :539-580、`_filter_target_side` :583-639、`glossary_stage` :533 一帶）
- Test: `backend/tests/test_output_lang_glossary.py`（append）

- [ ] **Step 1.1: 寫 failing tests**（append 落 `tests/test_output_lang_glossary.py`）

```python
def _gl(entries, name="測試表", gid="g-1", src="en", tgt="zh"):
    return {"id": gid, "name": name, "source_lang": src, "target_lang": tgt,
            "entries": entries}


def test_filter_candidates_carry_entry_and_glossary_ids():
    from output_lang_glossary import _filter_source_side, _filter_target_side
    g = _gl([{"id": "e-77", "source": "Happy Valley", "target": "跑馬地",
              "target_aliases": ["快活谷"]}])
    src_cands = _filter_source_side("Races at Happy Valley tonight.", [g],
                                    output_lang="zh", content_lang="en", derive_mode="mt")
    assert src_cands and src_cands[0]["entry_id"] == "e-77"
    assert src_cands[0]["glossary_id"] == "g-1"
    tgt_cands = _filter_target_side("快活谷今晚有賽事。", [g],
                                    output_lang="zh", content_lang="yue", derive_mode="refine")
    assert tgt_cands and tgt_cands[0]["entry_id"] == "e-77"
    assert tgt_cands[0]["glossary_id"] == "g-1"


def test_glossary_stage_changes_carry_lang():
    from output_lang_glossary import glossary_stage
    g = _gl([{"id": "e-1", "source": "Happy Valley", "target": "跑馬地",
              "target_aliases": ["快活谷"]}])
    segs = [{"text": "快活谷今晚有賽事。", "start": 0.0, "end": 2.0}]
    out = glossary_stage(segs, [g], output_lang="yue", content_lang="yue",
                         derive_mode="pass", llm_call=lambda s, u: "", use_llm=False)
    chs = out[0]["glossary_changes"]
    assert chs and chs[0]["lang"] == "yue"
    assert chs[0]["before"] == "快活谷" and chs[0]["after"] == "跑馬地"
```

- [ ] **Step 1.2: 跑（RED）**

```bash
python -m pytest tests/test_output_lang_glossary.py -q -k "carry"
```
預期：2 FAILED（KeyError: 'entry_id' / 'lang'）。

- [ ] **Step 1.3: 實施**——兩個 filter 嘅 `candidates.append({...})`（四處：:572、:618、:630 同 source 嗰個）每個 dict 加兩個 key：

```python
                    "entry_id": e.get("id"),
                    "glossary_id": g.get("id"),
```

`glossary_stage` 喺 `new_seg` 之前（:532）將 lang 印落 changes：

```python
        all_changes = [{**c, "lang": output_lang} for c in all_changes]
        new_seg = {**seg, "text": current_text, "glossary_changes": all_changes}
```

注意：`deterministic_apply`/`llm_review` 唔使改（佢哋 produce 嘅 change dict 經上面一行統一補 lang；entry_id 喺 change 度由 cand 帶過嚟 — `deterministic_apply` 嘅 change dict 加 `"entry_id": cand.get("entry_id")`，`llm_review` 同樣（搵佢 build change dict 嘅位置照加））。

- [ ] **Step 1.4: 跑（GREEN）+ 受影響檔全跑**

```bash
python -m pytest tests/test_output_lang_glossary.py tests/test_glossary_apply.py tests/test_glossary_reapply.py -q
```
預期：全 PASS（changes 係 add-only，舊 assert 唔會爆；如有 exact-dict assert 爆咗，更新嗰啲 assert 加埋新 key）。

- [ ] **Step 1.5: Commit**

```bash
git add backend/output_lang_glossary.py backend/tests/test_output_lang_glossary.py
git commit -m "feat(glossary): 候選/changes 帶 entry_id+glossary_id+lang（add-only schema）"
```

---

### Task 2: pure 掃描函數 `scan_track`　〔**執行 model：Opus**〕

**Files:**
- Modify: `backend/output_lang_glossary.py`（file 尾 append）
- Test: Create `backend/tests/test_glossary_review_scan.py`

- [ ] **Step 2.1: 寫 failing tests**

```python
"""scan_track() — 校對頁詞彙掃描 pure function 測試。"""
import pytest
from output_lang_glossary import scan_track


def _gl(entries, name="賽馬", gid="g-1", src="en", tgt="zh"):
    return {"id": gid, "name": name, "source_lang": src, "target_lang": tgt,
            "entries": entries}

E1 = {"id": "e-1", "source": "Happy Valley", "target": "跑馬地", "target_aliases": ["快活谷"]}
E2 = {"id": "e-2", "source": "Zac Purton", "target": "潘頓", "target_aliases": ["帕頓"]}


def test_target_side_alias_hit_is_fix():
    trk = scan_track(texts=["快活谷今晚有賽事。"], src_texts=None,
                     glossaries=[_gl([E1])], output_lang="yue",
                     content_lang="yue", derive_mode="pass", approved=[False])
    assert trk["lang"] == "yue" and trk["side"] == "target"
    items = trk["items"]
    assert len(items) == 1 and items[0]["kind"] == "fix"
    assert items[0]["alias"] == "快活谷" and items[0]["canonical"] == "跑馬地"
    assert items[0]["idx"] == 0 and items[0]["entry_id"] == "e-1"
    assert items[0]["approved"] is False


def test_target_side_verbatim_is_ok():
    trk = scan_track(texts=["跑馬地今晚有賽事。"], src_texts=None,
                     glossaries=[_gl([E1])], output_lang="yue",
                     content_lang="yue", derive_mode="pass", approved=[False])
    assert [i["kind"] for i in trk["items"]] == ["ok"]


def test_source_side_fix_and_ok():
    g = _gl([E1])
    trk = scan_track(texts=["The races at Wong Nai Chung were thrilling."],
                     src_texts=["跑馬地今晚嘅賽事好刺激。"],   # content 命中 target 索引?
                     glossaries=[g], output_lang="en",
                     content_lang="en", derive_mode="mt", approved=[False])
    # mt gate: glossary.source_lang(en) == content_lang(en) → 用 source term 喺 src_texts 搵
    # 呢度 src_texts 係中文 — source term "Happy Valley" 唔喺入面 → 冇 item
    assert trk["items"] == []

    trk2 = scan_track(texts=["The races at Wong Nai Chung were thrilling."],
                      src_texts=["Races at Happy Valley were thrilling."],
                      glossaries=[g], output_lang="zh",
                      content_lang="en", derive_mode="mt", approved=[False])
    # source 命中 + 譯文(text)冇 canonical → fix
    assert len(trk2["items"]) == 1 and trk2["items"][0]["kind"] == "fix"
    assert trk2["items"][0]["alias"] == "Happy Valley"

    trk3 = scan_track(texts=["跑馬地賽事好刺激。"],
                      src_texts=["Races at Happy Valley were thrilling."],
                      glossaries=[g], output_lang="zh",
                      content_lang="en", derive_mode="mt", approved=[False])
    assert [i["kind"] for i in trk3["items"]] == ["ok"]


def test_approved_flag_passthrough_and_multi_rows():
    trk = scan_track(texts=["快活谷賽事。", "帕頓出賽。"], src_texts=None,
                     glossaries=[_gl([E1, E2])], output_lang="yue",
                     content_lang="yue", derive_mode="pass",
                     approved=[True, False])
    fixes = [(i["idx"], i["approved"]) for i in trk["items"] if i["kind"] == "fix"]
    assert fixes == [(0, True), (1, False)]


def test_inapplicable_glossary_listed():
    # EN→ZH 表對 mt 軌（content=yue）gate 唔過 → not_applicable
    trk = scan_track(texts=["Hello."], src_texts=["你好。"],
                     glossaries=[_gl([E1])], output_lang="en",
                     content_lang="yue", derive_mode="mt", approved=[False])
    assert trk["items"] == []
    assert trk["applicable_glossaries"] == []
    assert trk["inapplicable_glossaries"] == ["賽馬"]


def test_guards_respected():
    # target ≤2 字 skip（同 pipeline 一致）
    g = _gl([{"id": "e-3", "source": "club", "target": "馬會", "target_aliases": ["俱樂部"]}])
    trk = scan_track(texts=["俱樂部公佈措施。"], src_texts=None, glossaries=[g],
                     output_lang="yue", content_lang="yue", derive_mode="pass",
                     approved=[False])
    assert trk["items"] == []   # target「馬會」≤2 字 → guard skip
```

- [ ] **Step 2.2: 跑（RED）**：`python -m pytest tests/test_glossary_review_scan.py -q` → ImportError（scan_track 未存在）。

- [ ] **Step 2.3: 實施**（append 落 `output_lang_glossary.py` 檔尾）

```python
# ---------------------------------------------------------------------------
# Proofread-page review scan (pure, read-only — spec 2026-06-12 §4)
# ---------------------------------------------------------------------------

def scan_track(
    texts: List[str],
    src_texts: Optional[List[str]],
    glossaries: List[dict],
    output_lang: str,
    content_lang: str,
    derive_mode: str,
    approved: List[bool],
) -> dict:
    """Dry-run glossary scan for ONE output-language track.

    Reuses the SAME matching filters as the pipeline's glossary_stage so a
    'fix' item here is exactly what the pipeline would have acted on. No LLM,
    no mutation — classification only.

    Returns {lang, mode, side, applicable_glossaries, inapplicable_glossaries,
             items:[{idx, kind: 'fix'|'ok', alias, canonical, source,
                     entry_id, glossary_id, glossary, approved}]}.
    """
    side = None
    applicable, inapplicable = [], []
    for g in glossaries:
        s = route_for_output(g, output_lang, content_lang, derive_mode)
        if s is None:
            inapplicable.append(g.get("name", ""))
        else:
            applicable.append(g.get("name", ""))
            side = side or s

    items: List[dict] = []
    for i, text in enumerate(texts):
        row_approved = bool(approved[i]) if i < len(approved) else False
        src_text = src_texts[i] if (src_texts is not None and i < len(src_texts)) else text

        for cand in _filter_source_side(src_text, glossaries, output_lang,
                                        content_lang, derive_mode):
            kind = "ok" if cand["target"] in text else "fix"
            items.append({
                "idx": i, "kind": kind,
                "alias": cand["source"],          # source term 係觸發詞
                "canonical": cand["target"],
                "source": cand["source"],
                "entry_id": cand.get("entry_id"),
                "glossary_id": cand.get("glossary_id"),
                "glossary": cand["glossary"],
                "approved": row_approved,
            })

        for cand in _filter_target_side(text, glossaries, output_lang,
                                        content_lang, derive_mode):
            hit_alias = next((a for a in cand.get("aliases", [])
                              if a and len(a) > 2 and a in text), None)
            if hit_alias:
                kind, alias = "fix", hit_alias
            elif cand["target"] in text:
                kind, alias = "ok", cand["target"]
            else:
                continue
            items.append({
                "idx": i, "kind": kind,
                "alias": alias,
                "canonical": cand["target"],
                "source": cand.get("source", ""),
                "entry_id": cand.get("entry_id"),
                "glossary_id": cand.get("glossary_id"),
                "glossary": cand["glossary"],
                "approved": row_approved,
            })

    return {
        "lang": output_lang, "mode": derive_mode, "side": side,
        "applicable_glossaries": applicable,
        "inapplicable_glossaries": inapplicable,
        "items": items,
    }
```

- [ ] **Step 2.4: 跑（GREEN）**：`python -m pytest tests/test_glossary_review_scan.py tests/test_output_lang_glossary.py -q` → 全 PASS。

- [ ] **Step 2.5: Commit**：`git add … && git commit -m "feat(glossary): scan_track pure dry-run 掃描（同 pipeline 共用 matching）"`

---

### Task 3: `glossary_review.py` pure module（AI 套用 prompt/parse/驗證）　〔**執行 model：Sonnet**〕

**Files:**
- Create: `backend/glossary_review.py`
- Test: Create `backend/tests/test_glossary_review_module.py`

- [ ] **Step 3.1: failing tests**

```python
"""glossary_review pure module 測試 — prompt build / parse / validate。"""
from glossary_review import (build_apply_system_prompt, build_apply_user_prompt,
                             parse_response, validate_applied)


def test_system_prompt_mentions_rules():
    sp = build_apply_system_prompt("口語廣東話", side="target")
    assert "只可以修改" in sp and "口語廣東話" in sp and "JSON" in sp


def test_user_prompt_contains_fields():
    up = build_apply_user_prompt(row_text="快活谷賽事。", src_text="",
                                 alias="快活谷", canonical="跑馬地")
    assert "快活谷" in up and "跑馬地" in up


def test_parse_response_plain_json():
    assert parse_response('{"text": "跑馬地賽事。"}') == "跑馬地賽事。"


def test_parse_response_code_fence_and_think():
    raw = "<think>blah</think>```json\n{\"text\": \"跑馬地賽事。\"}\n```"
    assert parse_response(raw) == "跑馬地賽事。"


def test_validate_applied_ok():
    assert validate_applied("跑馬地賽事。", canonical="跑馬地",
                            before_text="快活谷賽事。") is None


def test_validate_applied_missing_canonical():
    err = validate_applied("快活谷賽事。", canonical="跑馬地",
                           before_text="快活谷賽事。")
    assert err is not None


def test_validate_applied_excessive_rewrite():
    # 改動唔應該大幅重寫成句（>60% 字符變晒 → 拒絕）
    err = validate_applied("完全唔同嘅一句嘢跑馬地", canonical="跑馬地",
                           before_text="快活谷今晚有夜馬賽事直播")
    assert err is not None
```

- [ ] **Step 3.2: 跑（RED）** → ImportError。

- [ ] **Step 3.3: 實施** `backend/glossary_review.py`（parse 直接 reuse `ai_edit.parse_response` 嘅實現方式 — 抄佢嘅 lenient 邏輯，唔好 import ai_edit 造成隱性耦合）：

```python
"""校對頁逐項詞彙套用（glossary-apply-item）— pure prompt/parse/validate。

No I/O, no Flask, no registry access — the route in app.py owns those.
Spec: docs/superpowers/specs/2026-06-12-proofread-glossary-review-design.md §4
Prompt 改良自舊 GLOSSARY_APPLY_SYSTEM_PROMPT（app.py:3184-3237 嘅「只改一詞」原則）
+ ai-edit 嘅語體保持規則（validation 實證過 register-drift pattern）。
"""
import json
import re
from typing import Optional

MAX_OUTPUT_CHARS = 200

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TEXT_KEY_RE = re.compile(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"')


def build_apply_system_prompt(lang_label: str, side: str) -> str:
    direction = (
        "字幕入面有一個寫法唔啱嘅詞，你要將佢改成標準寫法"
        if side == "target" else
        "原文入面有一個專有名詞，你要確保字幕用咗佢嘅標準譯名"
    )
    return (
        "你係廣播字幕詞彙審核員。" + direction + "。\n"
        "規則：\n"
        f"1. 你只可以修改同個詞相關嘅嗰幾隻字 — 句子其他部分必須逐字保留。\n"
        f"2. 輸出必須係「{lang_label}」，維持原句嘅書寫系統（繁／簡）同語體"
        "（書面語定口語）— 絕對唔可以改語氣。\n"
        "3. 修改後句子必須包含標準寫法。\n"
        "4. 如果個詞喺句中有屈折變化／前後接字，照語法自然咁接駁。\n"
        '5. 只輸出 JSON：{"text": "修改後字幕"}。冇 markdown、冇解釋、冇思考標籤。'
    )


def build_apply_user_prompt(row_text: str, src_text: str,
                            alias: str, canonical: str) -> str:
    payload = {
        "現有字幕": row_text,
        "要修改嘅詞": alias,
        "標準寫法": canonical,
    }
    if (src_text or "").strip():
        payload["原文參考"] = src_text
    return json.dumps(payload, ensure_ascii=False)


def parse_response(raw) -> Optional[str]:
    """Lenient LLM-output parse → cleaned subtitle text, or None on failure."""
    if not isinstance(raw, str):
        return None
    txt = _THINK_RE.sub("", raw).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```\s*$", "", txt).strip()
    if txt.startswith("{"):
        try:
            obj = json.loads(txt, strict=False)
            txt = obj.get("text", "")
        except ValueError:
            m = _TEXT_KEY_RE.search(txt)
            if not m:
                return None
            try:
                txt = json.loads('"' + m.group(1) + '"', strict=False)
            except ValueError:
                return None
    if not isinstance(txt, str):
        return None
    txt = " ".join(txt.split())
    if not txt or len(txt) > MAX_OUTPUT_CHARS:
        return None
    return txt


def validate_applied(new_text: str, canonical: str, before_text: str) -> Optional[str]:
    """套用結果驗證。Return None=合格，否則錯誤描述（route 回 422 用）。"""
    if canonical not in new_text:
        return "輸出唔包含標準寫法"
    if new_text == before_text:
        return "輸出同原句一樣（冇修改）"
    # 防大幅重寫：剔除 canonical 之後，新舊句嘅共同字符比例要 >= 40%
    base = before_text.replace(canonical, "")
    kept = sum(1 for ch in base if ch in new_text)
    if base and kept / len(base) < 0.4:
        return "改動超出單一詞範圍（疑似重寫成句）"
    return None
```

- [ ] **Step 3.4: 跑（GREEN）**：`python -m pytest tests/test_glossary_review_module.py -q`
- [ ] **Step 3.5: Commit**：`git commit -m "feat(glossary): glossary_review pure module（apply prompt/parse/validate）"`

---

### Task 4: route `POST /api/files/<id>/glossary-preview`　〔**執行 model：Opus**〕

**Files:**
- Modify: `backend/app.py`（加喺 `api_glossary_reapply` 附近；實施前**讀 reapply route app.py:4942-5045** 抄佢嘅 content_lang/derive_mode/語言軌 setup — 兩條 route 必須同一套路由計算）
- Test: Create `backend/tests/test_glossary_review_routes.py`

- [ ] **Step 4.1: failing tests**（fixture 仿 `tests/test_glossary_reapply.py` — 實施前讀佢嘅 output_lang entry 構造方式，照搬一個 helper `_make_output_lang_entry()` 包含 `output_languages=["yue","en"]`、`source_language="yue"`、`content_asr_segments`、`translations`（by_lang+mirror）、`aligned_bilingual`、`glossary_ids`）

```python
def test_preview_returns_tracks_and_is_pure(client_with_entry):
    client, fid, app_module = client_with_entry
    import json as _json
    before = _json.dumps(app_module._file_registry[fid], sort_keys=True, ensure_ascii=False)
    r = client.post(f"/api/files/{fid}/glossary-preview", json={})
    assert r.status_code == 200
    body = r.get_json()
    assert {t["lang"] for t in body["tracks"]} == {"yue", "en"}
    yue = next(t for t in body["tracks"] if t["lang"] == "yue")
    fixes = [i for i in yue["items"] if i["kind"] == "fix"]
    assert fixes and fixes[0]["alias"] == "快活谷" and fixes[0]["canonical"] == "跑馬地"
    assert "totals" in body
    after = _json.dumps(app_module._file_registry[fid], sort_keys=True, ensure_ascii=False)
    assert before == after   # 零副作用


def test_preview_rejects_non_output_lang(client_with_profile_entry):
    client, fid = client_with_profile_entry
    assert client.post(f"/api/files/{fid}/glossary-preview", json={}).status_code == 400


def test_preview_unknown_glossary_override_400(client_with_entry):
    client, fid, _ = client_with_entry
    r = client.post(f"/api/files/{fid}/glossary-preview",
                    json={"glossary_ids": ["no-such-id"]})
    assert r.status_code == 400
```

- [ ] **Step 4.2: 跑（RED）** → 404（route 未存在）。

- [ ] **Step 4.3: 實施**（核心邏輯；setup 抄 reapply）

```python
@app.route('/api/files/<file_id>/glossary-preview', methods=['POST'])
@require_file_owner
def api_glossary_preview(file_id):
    """機械詞彙掃描（dry-run，零寫入）— spec 2026-06-12 §4。
    對每條輸出語言軌行同 pipeline 一致嘅 route_for_output + filter 規則。"""
    from output_lang_glossary import scan_track
    data = request.get_json(silent=True) or {}

    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "glossary-preview 只支援 output_lang 檔"}), 400
        # snapshot（鎖內淺 copy 夠 — 之後只讀）
        rows = list(entry.get("translations") or [])
        content_segs = list(entry.get("content_asr_segments") or [])
        output_langs = list(entry.get("output_languages") or [])
        source_language = entry.get("source_language")
        glossary_ids = data.get("glossary_ids", entry.get("glossary_ids") or [])

    glossaries = _load_glossaries(glossary_ids)
    if len(glossaries) != len(glossary_ids):
        return jsonify({"error": "包含未知詞彙表 id"}), 400

    # content_lang / derive_mode：同 glossary-reapply 同一套計法（睇嗰條 route）
    from output_lang_router import content_asr_lang
    from output_lang_aligned import derive_mode as _derive_mode
    content_lang = content_asr_lang(source_language)
    src_texts = [s.get("text", "") for s in content_segs]
    approved = [(r.get("status") == "approved") for r in rows]

    tracks = []
    for lang in output_langs:
        texts = [((r.get("by_lang") or {}).get(lang) or {}).get("text")
                 or r.get(f"{lang}_text") or "" for r in rows]
        mode = _derive_mode(content_lang, lang)
        trk = scan_track(texts=texts,
                         src_texts=src_texts if mode == "mt" else None,
                         glossaries=glossaries, output_lang=lang,
                         content_lang=content_lang, derive_mode=mode,
                         approved=approved)
        # 加 start time（前端跳段顯示用）
        for it in trk["items"]:
            i = it["idx"]
            it["start"] = rows[i].get("start") if i < len(rows) else None
        tracks.append(trk)

    totals = {
        "fix": sum(1 for t in tracks for i in t["items"] if i["kind"] == "fix"),
        "ok": sum(1 for t in tracks for i in t["items"] if i["kind"] == "ok"),
        "rows": len(rows),
    }
    return jsonify({"tracks": tracks, "totals": totals})
```

⚠ 實施註：`content_asr_lang`/`derive_mode` 嘅實際 import 路徑同簽名以 reapply route 現有用法為準（佢已經做緊同樣嘢）— 以上係按研究紀錄寫，落地時對齊。

- [ ] **Step 4.4: 跑（GREEN）**：`python -m pytest tests/test_glossary_review_routes.py -q`
- [ ] **Step 4.5: Commit**：`git commit -m "feat(glossary): POST glossary-preview 機械掃描 route（純讀零副作用）"`

---

### Task 5: route `POST /api/files/<id>/glossary-apply-item`　〔**執行 model：Opus**〕

**Files:**
- Modify: `backend/app.py`（preview route 下面；實施前讀 ai-edit route 嘅 LLM 注入 + segment-split AI path 嘅「鎖外 LLM、鎖內衝突檢查」pattern，同 PATCH /translations 嘅三庫同步 :3649-3656）
- Test: `backend/tests/test_glossary_review_routes.py`（append）

- [ ] **Step 5.1: failing tests**（mock LLM：`monkeypatch.setattr(app_module, "_make_ollama_llm_call", lambda: (lambda s, u: '{"text": "跑馬地今晚有賽事。"}'))` — 實際簽名以 ai-edit route 用法為準）

```python
def test_apply_item_writes_three_stores_keep_status(client_with_entry, monkeypatch):
    client, fid, app_module = client_with_entry
    monkeypatch.setattr(app_module, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "跑馬地今晚有賽事。"}'))
    entry = app_module._file_registry[fid]
    row = entry["translations"][0]
    row["status"] = "approved"          # keep_status 驗證
    before_text = row["by_lang"]["yue"]["text"]
    r = client.post(f"/api/files/{fid}/glossary-apply-item", json={
        "idx": 0, "lang": "yue", "alias": "快活谷", "canonical": "跑馬地",
        "glossary_id": "g-1", "entry_id": "e-1", "glossary": "賽馬",
        "expected_text": before_text,
    })
    assert r.status_code == 200
    body = r.get_json()
    assert "跑馬地" in body["text"]
    row = app_module._file_registry[fid]["translations"][0]
    assert row["by_lang"]["yue"]["text"] == body["text"]
    assert row["yue_text"] == body["text"]                       # mirror
    assert app_module._file_registry[fid]["aligned_bilingual"][0]["by_lang"]["yue"] == body["text"]
    assert row["status"] == "approved"                            # keep_status
    ch = row["glossary_changes"][-1]
    assert ch["lang"] == "yue" and ch["entry_id"] == "e-1" and ch["after"] == "跑馬地"


def test_apply_item_conflict_409(client_with_entry, monkeypatch):
    client, fid, app_module = client_with_entry
    monkeypatch.setattr(app_module, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "跑馬地今晚有賽事。"}'))
    r = client.post(f"/api/files/{fid}/glossary-apply-item", json={
        "idx": 0, "lang": "yue", "alias": "快活谷", "canonical": "跑馬地",
        "glossary_id": "g-1", "entry_id": "e-1", "glossary": "賽馬",
        "expected_text": "已經被人改咗嘅文字",
    })
    assert r.status_code == 409


def test_apply_item_bad_llm_output_422(client_with_entry, monkeypatch):
    client, fid, app_module = client_with_entry
    monkeypatch.setattr(app_module, "_make_ollama_llm_call",
                        lambda: (lambda s, u: 'not json at all'))
    entry = app_module._file_registry[fid]
    before = entry["translations"][0]["by_lang"]["yue"]["text"]
    r = client.post(f"/api/files/{fid}/glossary-apply-item", json={
        "idx": 0, "lang": "yue", "alias": "快活谷", "canonical": "跑馬地",
        "glossary_id": "g-1", "entry_id": "e-1", "glossary": "賽馬",
        "expected_text": before,
    })
    assert r.status_code == 422
    assert app_module._file_registry[fid]["translations"][0]["by_lang"]["yue"]["text"] == before


def test_apply_item_validations(client_with_entry):
    client, fid, _ = client_with_entry
    # 壞 body
    assert client.post(f"/api/files/{fid}/glossary-apply-item", json={}).status_code == 400
    # idx 出界
    r = client.post(f"/api/files/{fid}/glossary-apply-item", json={
        "idx": 999, "lang": "yue", "alias": "x", "canonical": "y",
        "expected_text": "z"})
    assert r.status_code == 400
```

- [ ] **Step 5.2: 跑（RED）** → 404。

- [ ] **Step 5.3: 實施**

```python
@app.route('/api/files/<file_id>/glossary-apply-item', methods=['POST'])
@require_file_owner
def api_glossary_apply_item(file_id):
    """逐項 AI 詞彙套用 — spec 2026-06-12 §4。
    鎖內驗證 snapshot → 鎖外 LLM → 重新攞鎖 + expected_text 衝突檢查 → 三庫同步寫入。
    keep_status：批核狀態唔郁。"""
    import glossary_review as gr
    data = request.get_json(silent=True) or {}
    try:
        idx = int(data["idx"])
        lang = str(data["lang"])
        alias = str(data["alias"])
        canonical = str(data["canonical"])
        expected_text = str(data["expected_text"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "需要 idx/lang/alias/canonical/expected_text"}), 400

    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "只支援 output_lang 檔"}), 400
        if _file_has_active_rerun(file_id):     # 同 reapply 嘅 rerun 檢查同一個 helper（讀 app.py:4967 現有寫法）
            return jsonify({"error": "AI Rerun 進行中"}), 409
        rows = entry.get("translations") or []
        if not (0 <= idx < len(rows)):
            return jsonify({"error": "idx 出界"}), 400
        row = rows[idx]
        current = ((row.get("by_lang") or {}).get(lang) or {}).get("text") \
                  or row.get(f"{lang}_text") or ""
        if current != expected_text:
            return jsonify({"error": "段落已被修改 — 請重新掃描"}), 409
        # mt 軌參考原文（有就攞）
        segs = entry.get("content_asr_segments") or []
        src_text = segs[idx].get("text", "") if idx < len(segs) else ""
        lang_label = lang   # 前端顯示 label 由前端處理；prompt 用 code 已夠（或接 subtitle_text label helper）

    # ── 鎖外 LLM ──
    side = "source" if src_text and alias not in current else "target"
    llm = _make_ollama_llm_call()
    raw = llm(gr.build_apply_system_prompt(lang_label, side=side),
              gr.build_apply_user_prompt(current, src_text, alias, canonical))
    new_text = gr.parse_response(raw)
    if new_text is None:
        return jsonify({"error": "AI 輸出無法解析"}), 422
    err = gr.validate_applied(new_text, canonical, current)
    if err:
        return jsonify({"error": f"AI 輸出唔合格：{err}"}), 422

    # ── 重新攞鎖 + 衝突檢查 + 原子寫入 ──
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        rows = entry.get("translations") or []
        if not (0 <= idx < len(rows)):
            return jsonify({"error": "段落已被修改 — 請重新掃描"}), 409
        row = rows[idx]
        current2 = ((row.get("by_lang") or {}).get(lang) or {}).get("text") \
                   or row.get(f"{lang}_text") or ""
        if current2 != expected_text:
            return jsonify({"error": "段落已被修改 — 請重新掃描"}), 409

        bl = row.setdefault("by_lang", {}).setdefault(lang, {})
        bl["text"] = new_text
        row[f"{lang}_text"] = new_text
        ab = entry.get("aligned_bilingual")
        if isinstance(ab, list) and idx < len(ab):
            ab[idx].setdefault("by_lang", {})[lang] = new_text
        change = {"source": data.get("source", alias), "before": alias,
                  "after": canonical, "glossary": data.get("glossary", ""),
                  "lang": lang, "entry_id": data.get("entry_id"),
                  "glossary_id": data.get("glossary_id")}
        row.setdefault("glossary_changes", []).append(change)
        # keep_status：唔掂 row["status"] / bl["status"] / flags
        _save_registry()

    return jsonify({"text": new_text, "change": change})
```

⚠ 實施註：①rerun 檢查 helper 名以 reapply route 實際代碼為準（可能係 inline 檢查 `_rerun_jobs`）— 照抄佢。②`_make_ollama_llm_call` 簽名以 ai-edit route 用法為準。③`expected_text` 比較故意喺鎖外 LLM 前後**各做一次**（早 fail 慳 LLM + 寫前最終檢查）。

- [ ] **Step 5.4: 跑（GREEN）**：`python -m pytest tests/test_glossary_review_routes.py -q`
- [ ] **Step 5.5: Commit**：`git commit -m "feat(glossary): POST glossary-apply-item 逐項 AI 套用（keep_status、三庫同步、衝突 409）"`

---

### Task 6: PATCH `glossary_ids` 擴展 + reapply 補 render-409　〔**執行 model：Opus**〕

**Files:**
- Modify: `backend/app.py`（`patch_file` :5969-6005；`api_glossary_reapply` gate 區 :4967 附近）
- Test: `backend/tests/test_glossary_review_routes.py`（append）

- [ ] **Step 6.1: failing tests**

```python
def test_patch_file_glossary_ids(client_with_entry):
    client, fid, app_module = client_with_entry
    r = client.patch(f"/api/files/{fid}", json={"glossary_ids": ["g-1"], "glossary_llm": False})
    assert r.status_code == 200
    e = app_module._file_registry[fid]
    assert e["glossary_ids"] == ["g-1"] and e["glossary_llm"] is False


def test_patch_file_glossary_ids_unknown_400(client_with_entry):
    client, fid, _ = client_with_entry
    assert client.patch(f"/api/files/{fid}",
                        json={"glossary_ids": ["nope"]}).status_code == 400


def test_reapply_blocked_during_render(client_with_entry, monkeypatch):
    client, fid, app_module = client_with_entry
    # 模擬 render 進行中 — 用 split/merge route 同一個檢查途徑（實施時對齊佢哋嘅寫法）
    monkeypatch.setitem(app_module._render_jobs, "rj-1",
                        {"file_id": fid, "status": "running"})
    assert client.post(f"/api/files/{fid}/glossary-reapply", json={}).status_code == 409
```

- [ ] **Step 6.2: 跑（RED）**。

- [ ] **Step 6.3: 實施** — `patch_file` 加（validation 喺鎖外、寫入喺鎖內，跟現有結構）：

```python
    if "glossary_ids" in data:
        v = data["glossary_ids"]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return jsonify({"error": "glossary_ids 必須係 id list"}), 400
        for gid in v:
            if _glossary_manager.get(gid) is None:
                return jsonify({"error": f"未知詞彙表 id: {gid}"}), 400
    if "glossary_llm" in data and not isinstance(data["glossary_llm"], bool):
        return jsonify({"error": "glossary_llm 必須係 boolean"}), 400
```

鎖內 write 區加：

```python
        if "glossary_ids" in data:
            entry["glossary_ids"] = list(data["glossary_ids"])
        if "glossary_llm" in data:
            entry["glossary_llm"] = data["glossary_llm"]
```

reapply gate（rerun 409 隔離）加 render 檢查 — **照抄 split/merge route 嘅 render-in-progress 檢查寫法**（app.py:5511 一帶，搵 `_render_jobs` 嘅現有判斷句）。

- [ ] **Step 6.4: 跑（GREEN）**：`python -m pytest tests/test_glossary_review_routes.py tests/test_glossary_reapply.py -q`
- [ ] **Step 6.5: Commit**：`git commit -m "feat(glossary): PATCH glossary_ids/glossary_llm + reapply 補 render-409"`

---

### Task 7: 前端 — 詞彙表 panel 改造　〔**執行 model：Sonnet**〕

**Files:**
- Modify: `frontend/proofread.html`（panel 區 :992-1008、`loadGlossaryList`/auto-select 區 :1580-1608、reapply 掣 handler :1849-1871、kind-gating :2331-2340）

設計依據：spec §3.1 + mockup `new-glossary-review-design.html`。互動組件照搬 index.html 上載 popup 嘅 tick-order pattern（`_olGlossaryOrder` index.html:1997, 4515-4570）。

- [ ] **Step 7.1**：panel header 區（output_lang 檔）改成：標題「詞彙表 — 此檔案使用中（剔選即儲存）」+ checkbox 清單（所有 `GET /api/glossaries` 可見表；剔選狀態 = `fileInfo.glossary_ids`，剔選順序 = 優先，數字 badge）+「🔍 掃描詞彙表」primary 掣 +「⟳ 全部重新生成」ghost 掣。核心 JS（新函數，放 panel 區附近）：

```javascript
let _glPanelOrder = [];   // 剔選順序 = glossary_ids 優先次序

async function renderGlossaryPanelList() {
  const box = document.getElementById('glPanelList');
  if (!box) return;
  const r = await fetch(`${API_BASE}/api/glossaries`);
  const all = (await r.json()).glossaries || [];
  _glPanelOrder = (fileInfo.glossary_ids || []).filter(id => all.some(g => g.id === id));
  box.innerHTML = all.map(g => {
    const pair = (g.source_lang && g.target_lang)
      ? ` ${g.source_lang.toUpperCase()}→${g.target_lang.toUpperCase()} · ${g.entry_count} 條` : '';
    return `<label class="glp-row">
      <input type="checkbox" value="${g.id}" ${_glPanelOrder.includes(g.id) ? 'checked' : ''}>
      <span class="glp-name">${escapeHtml(g.name)}</span>
      <span class="glp-pair">${escapeHtml(pair)}</span>
      <span class="glp-prio" style="display:none;"></span>
    </label>`;
  }).join('');
  if (!box._wired) { box.addEventListener('change', _onGlPanelToggle); box._wired = true; }
  _refreshGlPanelBadges();
}

async function _onGlPanelToggle(e) {
  const cb = e.target;
  if (!cb || cb.type !== 'checkbox') return;
  if (cb.checked) { if (!_glPanelOrder.includes(cb.value)) _glPanelOrder.push(cb.value); }
  else { _glPanelOrder = _glPanelOrder.filter(id => id !== cb.value); }
  _refreshGlPanelBadges();
  try {
    const r = await fetch(`${API_BASE}/api/files/${fileId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ glossary_ids: _glPanelOrder }),
    });
    if (!r.ok) throw new Error((await r.json()).error || `HTTP ${r.status}`);
    fileInfo.glossary_ids = _glPanelOrder.slice();
    showToast('詞彙表設定已儲存', 'success');
  } catch (err) {
    showToast(`儲存失敗: ${err.message}`, 'error');
    renderGlossaryPanelList();   // 還原 UI 到後端真相
  }
}

function _refreshGlPanelBadges() {
  document.querySelectorAll('#glPanelList .glp-row').forEach(row => {
    const cb = row.querySelector('input'); const b = row.querySelector('.glp-prio');
    const i = _glPanelOrder.indexOf(cb.value);
    if (cb.checked && i >= 0) { b.textContent = String(i + 1); b.style.display = 'inline-flex'; }
    else b.style.display = 'none';
  });
}
```

- [ ] **Step 7.2**：「全部重新生成」掣 handler — 包住現有 `reapplyGlossary()` 加 confirm：

```javascript
document.getElementById('glossaryReapplyBtn').addEventListener('click', () => {
  if (!confirm('會由原文重新生成所有字幕：\n• 你嘅人手修改會被覆寫\n• 批核狀態全部重設\n\n確定繼續？')) return;
  reapplyGlossary();
});
```
（掣文案改「⟳ 全部重新生成」；舊 listener 移除，邏輯不變。）

- [ ] **Step 7.3**：kind-gating 更新（:2331-2340）— output_lang 顯示新 panel + 兩掣；profile/V6 維持舊樣（dropdown+套用）不變。舊 auto-select Profile glossary 邏輯只留返 profile/V6 branch 用。

- [ ] **Step 7.4**：手動 smoke（:5001 hard refresh — 後端今次冇改唔使重啟）：開 output_lang 檔 → panel 顯示檔案詞彙表剔選狀態 → 剔/取消 → toast + `/api/files` 反映。

- [ ] **Step 7.5: Commit**：`git commit -m "feat(proofread): 詞彙表 panel 真多選（檔案 glossary_ids、剔選即儲存）+ 重新生成改名加警告"`

---

### Task 8: 前端 — 掃描 modal `js/glossary-review.js`　〔**執行 model：Sonnet**〕

**Files:**
- Create: `frontend/js/glossary-review.js`（IIFE module，仿 `frontend/js/find-replace.js` 嘅結構/暴露方式 — 實施前讀佢）
- Modify: `frontend/proofread.html`（`<script src="js/glossary-review.js">` + modal 容器 markup + 「掃描詞彙表」掣 wire-up）

視覺：spec §3.2 + mockup（ga-* 風格 class 沿用，新增 trk-* track 區樣式照 mockup CSS）。

- [ ] **Step 8.1**：modal markup（加喺 proofread.html body 尾，照 mockup 結構：overlay > modal > header/body/footer；body 由 JS 填）。

- [ ] **Step 8.2**：核心 JS（完整骨架 — 實施時按 mockup 補 CSS class）：

```javascript
/* glossary-review.js — 詞彙表掃描→剔選→逐項套用 modal（spec 2026-06-12 §3.2）
   依賴 proofread.html 全局：API_BASE, fileId, fileInfo, escapeHtml, showToast,
   setCursor, loadSegments, _outputLangLabel */
(function () {
  let scanData = null;          // 最近一次 preview response
  let applying = false;

  async function openScan() {
    const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-preview`,
                          { method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: '{}' });
    if (!r.ok) {
      showToast((await r.json().catch(() => ({}))).error || '掃描失敗', 'error');
      return;
    }
    scanData = await r.json();
    renderModal();
    document.getElementById('grOverlay').classList.add('open');
  }

  function renderModal() {
    const body = document.getElementById('grBody');
    body.innerHTML = scanData.tracks.map((t, ti) => {
      const dir = t.side === 'source'
        ? `按原文命中詞條，檢查${_outputLangLabel(t.lang)}字幕有冇用標準譯名`
        : '將字幕入面嘅別名統一做標準名';
      const fixes = t.items.map((it, ii) => ({ it, ii })).filter(x => x.it.kind === 'fix');
      const oks = t.items.filter(it => it.kind === 'ok');
      const inapp = (t.inapplicable_glossaries || []).length
        ? `<div class="trk-inapp">⚠ ${t.inapplicable_glossaries.map(escapeHtml).join('、')} 唔適用於呢條軌（原文語言唔對應）</div>` : '';
      return `<div class="trk" data-ti="${ti}">
        <div class="trk-head"><span class="trk-lang">${escapeHtml(_outputLangLabel(t.lang))}</span>
          <span class="trk-dir">${escapeHtml(dir)}</span>
          <span class="trk-count">${fixes.length} 待修正 · ${oks.length} 已符合</span></div>
        ${inapp}
        ${fixes.length ? `<div class="ga-section-head"><label class="ga-select-all">
            <input type="checkbox" data-sa="${ti}"><span>待修正 (${fixes.length}) — 全選</span></label></div>` : ''}
        ${fixes.map(({ it, ii }) => _rowHtml(t, ti, ii, it)).join('')}
        ${oks.length ? `<div class="ga-section-head">已符合 (${oks.length}) — 純顯示</div>` : ''}
        ${oks.map(it => _okRowHtml(t, it)).join('')}
      </div>`;
    }).join('');
    _wire();
    _updateCount();
  }

  function _rowHtml(t, ti, ii, it) {
    const rowText = _rowTextFor(t.lang, it.idx);
    const checked = it.approved ? '' : 'checked';
    const badge = it.approved ? '<span class="ga-row-badge">已批核 — 唔會自動剔</span>' : '';
    return `<div class="ga-row" data-ti="${ti}" data-ii="${ii}">
      <input type="checkbox" class="gr-ck" ${checked} data-ti="${ti}">
      <div class="ga-row-body">
        <div class="ga-row-term">${escapeHtml(it.alias)} → ${escapeHtml(it.canonical)}
          <span class="gl-src-tag">${escapeHtml(it.glossary)}</span> ${badge}
          <span class="seg-link" data-idx="${it.idx}">#${it.idx + 1} ${_fmtTc(it.start)}</span>
          <span class="gr-state"></span></div>
        <div class="ga-row-line">字幕：${_hl(rowText, it.alias)}</div>
        <div class="ga-row-line ga-hint">⚠ AI 將判斷修改位置 · 套用唔會改批核狀態</div>
      </div></div>`;
  }

  async function applySelected() {
    if (applying) return;
    applying = true;
    const rows = Array.from(document.querySelectorAll('#grBody .ga-row'))
      .filter(r => r.querySelector('.gr-ck') && r.querySelector('.gr-ck').checked);
    let ok = 0, fail = 0;
    for (const rowEl of rows) {                       // 串行（find-replace pattern）
      const t = scanData.tracks[+rowEl.dataset.ti];
      const fixes = t.items.filter(i => i.kind === 'fix');
      const it = fixes[+rowEl.dataset.ii];
      const st = rowEl.querySelector('.gr-state');
      st.textContent = '…';
      try {
        const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-apply-item`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            idx: it.idx, lang: t.lang, alias: it.alias, canonical: it.canonical,
            source: it.source, glossary_id: it.glossary_id, entry_id: it.entry_id,
            glossary: it.glossary, expected_text: _rowTextFor(t.lang, it.idx),
          }),
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
        _setRowText(t.lang, it.idx, body.text);       // 更新本地 cache，後續 expected_text 啱
        st.textContent = '✓'; st.className = 'gr-state ok';
        rowEl.querySelector('.gr-ck').checked = false;
        rowEl.classList.add('applied-ok');
        ok++;
      } catch (e) {
        st.textContent = `✗ ${e.message}`; st.className = 'gr-state err';
        fail++;
      }
      _updateCount();
    }
    applying = false;
    showToast(`已套用 ${ok} 項${fail ? `，${fail} 項失敗` : ''}`, fail ? 'error' : 'success');
    await loadSegments();        // 同步段落表 + 詞彙對照
  }

  /* _rowTextFor/_setRowText 讀寫 proofread 嘅 segs cache（by_lang）；
     _hl 黃 highlight alias；_fmtTc 秒→MM:SS；_wire 綁 select-all/seg-link/footer；
     _updateCount 計「套用選中 (N)」+ indeterminate — 全部照 mockup/舊 ga 邏輯實作 */

  window.GlossaryReview = { openScan };
})();
```

- [ ] **Step 8.3**：seg-link click → `setCursor(idx, true)`（跳段+seek，同 ⌘F 一致）；「重新掃描」掣 → `openScan()` 重入；Esc/✕/取消 閂 modal（套用中 disable 閂）。

- [ ] **Step 8.4**：手動 smoke：掃描 → 兩軌渲染 → 剔選計數 → 套用（:5001 有 Ollama 就真套；冇就睇 ✗ 錯誤回報路徑）。

- [ ] **Step 8.5: Commit**：`git commit -m "feat(proofread): 詞彙表掃描 modal（雙軌分區、逐項剔選、串行 AI 套用）"`

---

### Task 9: 前端 — 詞彙對照升級　〔**執行 model：Sonnet**〕

**Files:**
- Modify: `frontend/proofread.html`（detail 詞彙對照 render :2618-2635）

- [ ] **Step 9.1**：render 改成（容忍舊記錄缺 `lang`/`source`）：

```javascript
function _renderGlossaryChanges(seg) {
  const chs = seg.glossary_changes || [];
  if (!chs.length) {
    const noGl = !(fileInfo.glossary_ids || []).length;
    return `<div class="rv-gc-empty">${noGl ? '— 未設定詞彙表 —' : '— 此段冇命中詞條 —'}</div>`;
  }
  return chs.map(gc => {
    const langChip = gc.lang
      ? `<span class="gc-lang">${escapeHtml(_outputLangLabel(gc.lang))}</span>` : '';
    const src = gc.source && gc.source !== gc.before
      ? `<span class="gc-src">"${escapeHtml(gc.source)}"</span> ` : '';
    return `<div class="rv-gc-row">${langChip}${src}${escapeHtml(gc.before)} → ${escapeHtml(gc.after)}
      <span class="gc-gl">· ${escapeHtml(gc.glossary || '')}</span></div>`;
  }).join('');
}
```
（實際function名/結構以現有 :2618-2635 代碼為準 — 喺原位重構，唔好另起爐灶。）

- [ ] **Step 9.2**：smoke + Commit：`git commit -m "feat(proofread): 詞彙對照加語言chip+觸發詞，空狀態分流"`

---

### Task 10: Validation-First — apply prompt 實證　〔**執行 model：Fable 5（主 loop）**〕

**Files:**
- Create: `docs/superpowers/specs/2026-06-12-glossary-apply-item-validation-tracker.md`

- [ ] **Step 10.1**：寫 12-call 實證 script（真 LLM `qwen3.5:35b-a3b` @0.3，production 對齊）：4 個 target-side case（口語/書面語 × 簡單替換/接駁變化）× 2 + 4 個 source-side case。每 call 檢查：①包含 canonical ②除目標詞外逐字保留 ③語體冇 drift（書面語句唔可以變口語 — ai-edit tracker 嘅已知 pattern）。
- [ ] **Step 10.2**：跑 → 記錄 ✅/❌/⚠ 落 tracker。**任何 ❌ → 改 prompt → 重驗**（prompt 喺 `glossary_review.py`，改完跑返 Task 3 測試）。
- [ ] **Step 10.3**：Commit tracker：`git commit -m "docs(validation): glossary-apply-item prompt 12-call 實證"`

---

### Task 11: E2E　〔**執行 model：Fable 5（主 loop）**〕

- [ ] **Step 11.1**：起隔離 server（本 session 現成方法：`/tmp/gl_e2e_server.py` pattern — worktree app + temp glossary dir + LOGIN_DISABLED/R5_AUTH_BYPASS/R5_LICENSE_BYPASS，:5002）。Seed：一個 output_lang 測試 entry（直接寫 registry fixture 或用真檔 `97ce36e85e97` 嘅複本）+ 詞彙表（快活谷→跑馬地 alias case）。
- [ ] **Step 11.2**：Playwright script（真 Chrome）：panel 剔表 → PATCH 落檔（驗 `/api/files`）→ 掃描 → modal 兩軌渲染 + 計數 → 剔選 → 套用（真 LLM）→ 行內 ✓ → 段落文字更新 + 詞彙對照有新行（lang chip）→ 批核狀態不變 → 重新掃描該項變「已符合」。
- [ ] **Step 11.3**：全 PASS 先過關；fail → 跟 systematic-debugging 查根因。

---

### Task 12: Docs　〔**執行 model：Sonnet**〕

- [ ] CLAUDE.md：REST 表加 `glossary-preview`/`glossary-apply-item`/PATCH 擴展/reapply 補閘；Current State 加「Proofread Glossary Review」段。
- [ ] README.md（繁中用戶向）：詞彙表掃描/套用使用說明 + 「全部重新生成」警告語義；修正「幾秒內」失實描述。
- [ ] Commit：`git commit -m "docs: glossary review feature（CLAUDE.md REST/Current State + README）"`

---

### Task 13: Adversarial review + 收尾　〔**執行 model：Opus agents，Fable 5 判讀修正**〕

- [ ] **Step 13.1**：Workflow 三 lens review（diff-correctness／同類掃描 sweep／invariants-regression — 重點：三庫同步、鎖窗口、expected_text 衝突語義、approve 鏡像唔受影響、glossary_ids 保序）。
- [ ] **Step 13.2**：Fable 5 修正 medium+ findings（重大架構問題先返 spec 層討論）。
- [ ] **Step 13.3**：受影響測試檔逐檔重跑 + E2E 重跑 → 全 GREEN → 報告用戶驗收（:5001 行 worktree，hard refresh + 重啟後端先見新 route）。

---

## Self-review 紀錄

- **Spec coverage**：§3.1→T7、§3.2→T8、§3.3→T9、§4 四 endpoint→T4/T5/T6（reapply 改名喺 T7 前端）、§5 數據模型→T1（lang/entry_id）+T5（寫入）、§6 invariants→T5 實施+T13 review 重點、§7 errors→T4/T5/T6 測試、§9 測試→T0-T11、Validation-First→T10。✅
- **Placeholder scan**：「實施註」係指向現有代碼對齊位（讀後照抄），唔係 TBD。✅
- **Type consistency**：`scan_track` 回傳 schema（T2）== preview route 組裝（T4）== 前端 `scanData.tracks` 用法（T8）；`glossary_changes` 新欄（T1/T5）== T9 render。✅
