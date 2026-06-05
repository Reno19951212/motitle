# 詞彙表 Review v2（output_lang）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 令 glossary 喺 output_lang 真正生效 —— 一個統一 post-derivation glossary stage（確定性 + LLM 精修），多表 ordered SET、全語對自動路由、校對頁 before/after 顯示。

**Architecture:** 新純模組 `backend/output_lang_glossary.py` 喺 derive + OpenCC 之後跑；dispatch load `entry["glossary_ids"]` 並 thread；前端 popup 多選 + 校對頁渲染 `glossary_changes`。

**Tech Stack:** Python 3.9 backend；pytest（`FLASK_SECRET_KEY=test-secret-only-for-pytest-do-not-deploy R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest`）；vanilla JS frontend；mlx-whisper large-v3 + Ollama qwen3.5:35b（integration）；Playwright。

**Spec:** [docs/superpowers/specs/2026-06-05-glossary-v2-design.md](../specs/2026-06-05-glossary-v2-design.md)
**Research:** [docs/superpowers/research/2026-06-05-glossary-v2-research.md](../research/2026-06-05-glossary-v2-research.md)

> ⚠️ **GATE：Phase 0（stress test）必須全綠先可以入 Phase 1+ 任何 production code。** Validation-First mandate（CLAUDE.md）。

---

## File Structure

- `backend/scripts/crosslang_prototype/diag_glossary_v2.py` — 擴成完整 stress test（Phase 0，gate）。
- `backend/output_lang_glossary.py`（新）— 純函數 glossary stage（index/route/filter+guard/deterministic/llm_review/glossary_stage）。
- `backend/output_lang_postprocess.py` — 加 `glossary_stage` thin wrapper（或直接喺 app/aligned call 新模組）。
- `backend/output_lang_aligned.py` — `derive_aligned_output` / `build_aligned_bilingual` 加 `glossaries` param。
- `backend/app.py` — transcribe handler 存 `glossary_ids`；`_run_output_lang*` load + thread；新 `POST /api/files/<id>/glossary-reapply`。
- `backend/output_lang_persist.py` — `build_output_translations` 帶 `glossary_changes`（若需要）。
- `frontend/index.html` — popup 多選 selector + `glossary_ids`。
- `frontend/proofread.html` — 詞彙對照 before/after + rail 📖 + 重新套用掣。
- Tests: `backend/tests/test_output_lang_glossary.py`（新，pure-fn）+ `test_glossary_v2_dispatch.py`（新，dispatch）+ Playwright `test_glossary_v2_proofread.spec.js`（新）。

---

## Phase 0 — Stress test（GATE，必須先過）

### Task 0.1：擴 diag_glossary_v2.py 成完整 stress harness

**Files:** Modify `backend/scripts/crosslang_prototype/diag_glossary_v2.py`

- [ ] **Step 1：加 metric helpers + matrix**

加 `--clip --glossary --side{source|target} --inject{full|filtered} --use-llm --cell --out` CLI（沿用現有 LLM binding + guard）。Metrics 函數：
```python
def metrics(changes, gold_applicable, all_segs_text):
    # FALSE-INJECTION: changed segs whose source has NO gold-applicable term
    false_inj = sum(1 for c in changes if c["i"] not in gold_applicable)
    # FOLLOW-RATE: of gold-applicable, how many got the canonical target
    # SUFFIX-LEAK: any '(H###)' in any output
    leak = sum(1 for t in all_segs_text if re.search(r"\([A-Z]\d{3}\)", t))
    return {"false_injection_pct": ..., "follow_rate_pct": ..., "suffix_leak": leak}
```

- [ ] **Step 2：gold_applicability**

寫 `gold_applicability.json`（人手，per clip：`{seg_index: [applicable_term_ids]}`）。**False-injection floor 免人手**：用一條「講騎師唔講馬名」嘅片（gold = 全 `[]`），任何 glossary 改動 = false-injection。

- [ ] **Step 3：跑 matrix + 寫 tracker**

Run cells（cheap→expensive）：deterministic-C(1350) → source-side(19) → source-side(1350,filtered,+LLM) → target-side(refine clip) → 多表（broadcast+racing）。結果寫 `docs/superpowers/specs/2026-06-05-glossary-v2-validation-tracker.md`。
Run: `cd backend && FLASK_SECRET_KEY=... PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/diag_glossary_v2.py --cell ...`

- [ ] **Step 4：GATE 判定**

接受門檻（全部要 hold）：**false-injection ≤1%、follow-rate ≥85%、suffix-leak = 0**、19→1350 follow-rate 跌 ≤5pp。若 1350 false-injection >2% → 唔 ship racing-scale，回 candidate-gating 再驗。**未過唔可以入 Phase 1。** Commit tracker。

---

## Phase 1 — Backend glossary stage（純函數，gated by Phase 0）

### Task 1.1：`output_lang_glossary.py` 核心純函數

**Files:** Create `backend/output_lang_glossary.py`；Test `backend/tests/test_output_lang_glossary.py`

- [ ] **Step 1：failing tests**
```python
import output_lang_glossary as G

def test_strip_suffix():
    assert G.strip_horse_id("火悟空 (K335)") == "火悟空"
    assert G.strip_horse_id("活力拍檔") == "活力拍檔"

def test_build_merged_index_priority():
    g1 = {"id":"a","name":"A","source_lang":"en","target_lang":"zh","entries":[{"source":"X","target":"甲"}]}
    g2 = {"id":"b","name":"B","source_lang":"en","target_lang":"zh","entries":[{"source":"X","target":"乙"}]}
    idx = G.build_merged_index([g1, g2])           # ordered: a wins
    assert idx["source"]["X"]["target"] == "甲"     # first-wins

def test_route_for_output():
    g = {"source_lang":"en","target_lang":"zh"}
    assert G.route_for_output(g, output_lang="zh", content_lang="en", derive_mode="mt") == "source"
    g2 = {"source_lang":"yue","target_lang":"zh"}
    assert G.route_for_output(g2, output_lang="zh", content_lang="yue", derive_mode="refine") == "target"
    assert G.route_for_output(g, output_lang="ja", content_lang="en", derive_mode="mt") is None  # target_lang!=ja

def test_candidate_guard_rejects_common_single_word():
    assert G.is_name_candidate("AMAZING PARTNERS") is True     # multi-word
    assert G.is_name_candidate("HYMNBOOK") is True             # uncommon single
    assert G.is_name_candidate("CLASS") is False               # common single
    assert G.is_name_candidate("DASH") is False
```

- [ ] **Step 2：Run → FAIL**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_glossary.py -q` → FAIL (module missing).

- [ ] **Step 3：實現** `backend/output_lang_glossary.py`

```python
"""Unified post-derivation glossary stage for output_lang (2026-06-05).
Deterministic (suffix-strip + verbatim/canonical) + optional LLM review. Pure;
llm_call injected. See docs/superpowers/specs/2026-06-05-glossary-v2-design.md."""
import re
from typing import Callable, Dict, List, Optional

_SUFFIX = re.compile(r"\s*\([A-Z]\d{3}\)\s*$")
_FAMILY = {"yue": "zh", "zh": "zh", "cmn": "zh", "en": "en", "ja": "ja"}
_COMMON = set("""a an and the or but of to in on at for with by from as is are was were be
class dash draw time run won win race pace form gate field length head neck nose track turn
home back front lead led close open free easy good best top fast slow late early jump break
sprint stay strong soft hard fresh sharp clear ready set go map plan move push hold drop rail
box line meter mile up down out over under first second third last next one two three smart
victory winner champion star colour colours light delight jewel general partners avenue""".split())

def strip_horse_id(t: str) -> str:
    return _SUFFIX.sub("", t or "").strip()

def is_name_candidate(source: str) -> bool:
    words = (source or "").strip().split()
    if len(words) >= 2:
        return True
    return (source or "").strip().lower() not in _COMMON

def build_merged_index(glossaries: List[dict]) -> dict:
    """Ordered first-wins merge → {'source': {KEY: entry}, 'target': {TGT: entry}}."""
    src, tgt = {}, {}
    for g in glossaries:
        gname = g.get("name", "")
        for e in g.get("entries", []):
            s = (e.get("source") or "").strip()
            t = strip_horse_id(e.get("target") or "")
            if not t:
                continue
            rec = {"source": s, "target": t, "glossary": gname,
                   "source_lang": g.get("source_lang"), "target_lang": g.get("target_lang")}
            if s and s.upper() not in src:
                src[s.upper()] = rec
            if t not in tgt:
                tgt[t] = rec
    return {"source": src, "target": tgt}

def route_for_output(glossary: dict, output_lang: str, content_lang: str, derive_mode: str) -> Optional[str]:
    if derive_mode == "mt" and glossary.get("source_lang") == content_lang \
            and _FAMILY.get(glossary.get("target_lang")) == _FAMILY.get(output_lang):
        return "source"
    if derive_mode in ("refine", "pass") and _FAMILY.get(glossary.get("target_lang")) == _FAMILY.get(output_lang):
        return "target"
    return None
```
（再加 `filter_candidates(text, index, side)`、`deterministic_apply`、`llm_review(seg, cands, llm_call)`、`glossary_stage(segments, glossaries, output_lang, content_lang, derive_mode, llm_call, *, use_llm)` — 後者 per-seg：route 適用表 → filter+guard → deterministic（剝 suffix + verbatim/alias）→ 若 use_llm 且有未解 candidate → llm_review；每段記 `glossary_changes`。回 `(new_segments, changes_per_seg)`。LLM prompt 對齊 spec §A。）

- [ ] **Step 4：Run → PASS**；**Step 5：Commit**

### Task 1.2：`glossary_stage` 完整行為 + changes 記錄

**Files:** `backend/output_lang_glossary.py`；test 同上

- [ ] failing test：`glossary_stage` 對「Blazing Wukong」段（mock llm 回 {"text":"火悟空..."}）→ 輸出含火悟空 + `changes=[{source,before,after,glossary}]`；「class 3」段 → guard reject、無 change。
- [ ] 實現 `glossary_stage`（deterministic + llm_review + 記 changes，immutable）。
- [ ] Run → PASS；Commit。

---

## Phase 2 — Wire into derive + dispatch（gated）

### Task 2.1：`derive_aligned_output` / `_produce_output_lang` 加 glossary stage

**Files:** `backend/output_lang_aligned.py`、`backend/app.py`；Test `backend/tests/test_glossary_v2_dispatch.py`

- [ ] **failing test**：`derive_aligned_output(base, 'en', 'zh', 'trad', llm, glossaries=[racing])` → zh 段含 canonical 名 + 結果帶 changes（或經 out-param）。
- [ ] **實現**：
  - `derive_aligned_output(..., glossaries=None)`：`apply_script` 之後 `if glossaries: out, ch = output_lang_glossary.glossary_stage(out, glossaries, output_lang, content_lang, mode, llm_call, use_llm=...)`。回 changes 經 segment dict（`seg["glossary_changes"]`）。
  - `build_aligned_bilingual(..., glossaries=None)` thread。
  - `_produce_output_lang(..., glossaries=None)`：L390 `apply_script` 後同樣 call。
  - 向後兼容：`glossaries=None` → 行為逐 byte 不變（regression test）。
- [ ] Run + 既有 `test_output_lang_aligned` / `test_produce_output_lang` 全綠；Commit。

### Task 2.2：Dispatch load glossaries + entry 欄

**Files:** `backend/app.py`；test 同上

- [ ] **failing test**：file entry 有 `glossary_ids=['db323...']` → `_run_output_lang*` load glossary、thread；transcribe handler 存 `glossary_ids`（+ 驗證未知 id → 400）。
- [ ] **實現**：
  - transcribe handler（讀 source_language 嗰度）：`glossary_ids = json.loads(request.form.get('glossary_ids') or '[]')`；逐個 `_glossary_manager.get` 驗證（未知 → 400）；`entry["glossary_ids"]=...`、`entry["glossary_llm"]=request.form.get('glossary_llm')!='0'`（default ON）。
  - `_run_output_lang` / `_run_output_lang_bound_base` / `_run_output_lang_cross` / `_run_output_lang_second*`：lock 內讀 `glossary_ids` → `[_glossary_manager.get(g) for g in ids if ...]` → thread 入 derive。
  - persist `glossary_changes` 入 translation row（`build_output_translations` 帶過，或 dispatch 後補）。
- [ ] Run + 既有 dispatch suite 全綠；Commit。

### Task 2.3：`POST /api/files/<id>/glossary-reapply`

**Files:** `backend/app.py`；test 同上

- [ ] **failing test**：output_lang file POST reapply `{glossary_ids:[...], use_llm:true}` → re-run glossary stage on 現有 translations（唔重 ASR/MT）→ 更新 zh + glossary_changes，回 202/200。
- [ ] **實現**：`@require_file_owner`，讀現有 translations 嘅 zh/source text → 對每輸出語言 re-run `glossary_stage`（用 cached 內容語言 + derive mode）→ immutable 更新 rows + by_lang + aligned。
- [ ] Run；Commit。

---

## Phase 3 — Frontend（gated）

### Task 3.1：上傳 popup 多選 glossary selector

**Files:** `frontend/index.html`；Test `frontend/tests/test_glossary_v2_proofread.spec.js`

- [ ] **failing Playwright**：popup 有 `#olGlossary`（multi）+ `#olGlossaryLlm`（checked）；揀 2 個 glossary + confirm → `POST /api/transcribe` 帶 `glossary_ids` JSON（順序）+ `glossary_llm`。
- [ ] **實現**：`olOverlay` 加 multi-select（由 `GET /api/glossaries` populate，顯示 `name (src→tgt)`）+ LLM checkbox（default checked）；confirm handler 收集 ordered ids；`startTranscription` append。
- [ ] Run；Commit。

### Task 3.2：校對頁 詞彙對照 before/after + rail 📖 + 重新套用

**Files:** `frontend/proofread.html`；test 同上

- [ ] **failing Playwright**：output_lang file with `glossary_changes` → detail panel 「詞彙對照」顯示 `before → after`（火悟空）；無 changes 段顯示「無詞彙表詞條」；rail 行有 📖；「重新套用詞彙表」掣 POST glossary-reapply。
- [ ] **實現**：
  - `loadSegments` output_lang 分支：`glossary_changes: t.glossary_changes || []` 帶入 `segs[i]`。
  - `renderDetail` 「詞彙對照」stub（~L2255）：渲染 `s.glossary_changes`（`<span class=gl-before>before</span> → <span class=gl-after>after</span> · glossary`）/ 空時「— 此段無詞彙表詞條（未涉及）—」。
  - `_renderSegListBase` rail-flags：`s.glossary_changes.length` → 加 `<span class=qa-flag>📖</span>`。
  - 詞彙表 panel 「套用」掣 output_lang 改顯示「重新套用詞彙表」→ POST `/api/files/<id>/glossary-reapply` → reload segments。
  - 加 `.gl-before{text-decoration:line-through;color:var(--text-dim)} .gl-after{color:var(--accent-2);font-weight:600}` CSS。
- [ ] Run；Commit。

---

## Phase 4 — Integration + docs

### Task 4.1：Live integration

- [ ] 真 mlx + Ollama re-run（via live :5002 或 reapply endpoint）：Winning Factor（en→zh 源側,多表 broadcast+racing）+ 一條粵→書面（目標側）。確認 before/after 喺校對頁正確、false-injection 對齊 tracker、口語/其他輸出不變。記入 tracker。

### Task 4.2：Docs

- [ ] CLAUDE.md（新 endpoint glossary-reapply + glossary-in-output_lang current-state + glossary_ids/glossary_changes 欄）、README（上傳 popup 詞彙表 + 校對 before/after + CSV aliases 建議）、history.md。Commit。

---

## Self-Review

- **Spec coverage**：A 架構(Task 1.1-2.1)、B 多表優先(Task 1.1 first-wins test)、C 路由+guard(Task 1.1)、D UX(popup 3.1 / 校對 before-after 3.2 / reapply 2.3)、before/after 顯示(3.2)、Validation-First gate(Phase 0)、CSV/aliases(Task 4.2 doc)。全覆蓋。
- **Placeholder**：核心純函數 + dispatch + 校對渲染有具體 code/test；UI 機械部分有明確 anchor（file:line）。
- **Type consistency**：`glossary_stage(...)` 回 `(segments, changes)`；`derive_aligned_output(..., glossaries=None)`；`build_merged_index → {'source','target'}`；entry `glossary_ids`/`glossary_llm`、row `glossary_changes` 全程一致。
- **Gate**：Phase 0 明確 block Phase 1+。

## Execution Handoff

採 **subagent-driven-development**：Phase 0（stress test）+ Task 2.x（app.py dispatch 整合）+ 全 review = Opus；Task 1.x 純函數 + 3.x 前端 = Sonnet。每 task two-stage review。**Phase 0 未綠燈,唔起 Phase 1。**
