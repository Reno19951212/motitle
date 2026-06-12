# 粵拼語音糾錯（Phonetic Correction P0+P1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 中文 ASR base 喺 derive 之前過三層糾錯（機械規則 → 粵拼 AUTO 替換 → 受限 LLM 判決），同音錯字（馬名/術語）自動修正，全 track 繼承。

**Architecture:** 新 pure module `backend/phonetic_correction.py`（演算法照 port 兩個已驗證 proto — `docs/superpowers/specs/2026-06-13-lang-quality-research/protos/{b1_phonetic.py,b4_pipeline.py}`，實驗實證 34/36=94.4% 修復 @ 1 FP）。app.py 兩個掛鈎位（bound_base + produce 嘅中文路徑）。糾正記錄入 rows 嘅 `glossary_changes`（proofread 詞彙對照 UI 零改動直接顯示）。

**Tech Stack:** ToJyutping（新依賴，純 Python）、Flask、pytest。

**Spec:** `docs/superpowers/specs/2026-06-13-phonetic-correction-design.md`（已批准）
**研究證據:** `docs/superpowers/specs/2026-06-13-lang-quality-research/`（B1/B4 md = 演算法行為基準；protos/ = 要 port 嘅實證代碼）

**事實基準（已讀 code 確認）：**
- 掛鈎位 1：app.py `_run_output_lang_bound_base` — base 建好＋clause_split 之後（~line 625），`llm = _make_ollama_llm_call()` / `cancel_check = _make_cancel_check(cancel_event)`（627）之後、`derived = {...}`（628）之前插入；rows merge 位喺 `rows = build_output_translations(...)`（632）之後
- 掛鈎位 2：app.py `_produce_output_lang` whisper-direct 路徑 — `base = (res or {}).get("segments") or []`（~463）之後；呢條 path 嘅 glossary_changes 係由 `olg.glossary_stage`（~495）寫上 seg dicts，phonetic 變更要喺嗰段之後 merge
- `content_lang = content_asr_lang(source_language)`：yue/zh 先行糾錯（en/ja no-op）；`_OL_FAMILY` map 喺 app.py module level
- glossary target 格式 `中文名 (編號)` — strip ` (XXX)` 先入索引；glossary dict shape：`{name, entries: [{source, target, aliases, ...}]}`
- rows 嘅 `glossary_changes` item shape（現有 UI 讀）：`{source, before, after, glossary}`
- LLM：`_make_ollama_llm_call()` 回 `(system, user) -> str`（Beta 模式自動 OpenRouter）；`_make_cancel_check(cancel_event)` 回 raise-JobCancelled callable
- 測試：`cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_phonetic_correction.py -v`（單獨跑 — full suite order 污染）
- **Proto port 映射**（function 名 → 新 module；行為唔准改，只准 adapt I/O）：
  | proto | functions | 用途 |
  |---|---|---|
  | b1_phonetic.py | `split_tone` `parse_onset` `fuzzy_norm` `toneless` `jyut_seq` `edit_le1` | 粵拼底層（lazy ToJyutping import） |
  | b1_phonetic.py | `build_index`（adapt：入參改 glossaries+lexicon list，唔好 hardcode 路徑） `match_segments` | 索引＋滑窗匹配（L1/L2/L3 分級照舊） |
  | b4_pipeline.py | `stage0_rules`（M(\d)→尾X） `in_auto_tier`（L1/L2/L3-d0 + target≥3字） `greedy_apply` | Stage 0 + AUTO tier |
  | b4_pipeline.py | `verbatim_name_ranges` `blocked_by_protection` `syl_near` `align_quality` `prune_candidates`（per_span_top=3, per_seg_cap=12） `llm_tier_filter` `build_judge_user` `parse_accepts` | Stage 2 五重 guardrail＋judge prompt＋解析 |

---

### Task 1: 依賴 + 賽馬術語 lexicon

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/config/phonetic_lexicons/racing_terms.json`

- [ ] **Step 1: requirements.txt 加一行**（alphabetical 位置）：

```
ToJyutping
```

- [ ] **Step 2: 裝入 venv**

Run: `"/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pip install -q ToJyutping && "…venv…/python" -c "import ToJyutping; print(ToJyutping.get_jyutping_text('星際快車'))"`
Expected: `sing1 zai3 faai3 ce1`

- [ ] **Step 3: 術語 lexicon**（內容以研究 A1 catalog 嘅 racing_term 錯誤 + B1 supplement 為基礎 curate；shape 同 glossary target 一致無編號）：

```json
{
  "style": "racing",
  "comment": "賽馬評述常用術語 — 粵拼糾錯 supplement 索引（B1/B4 研究 curate；可隨時人手增補）",
  "terms": [
    "內欄位置", "大外檔", "馬位優勢", "留前鬥後", "包尾",
    "放頭", "外疊", "直路", "沙田銀瓶", "精算暴雪",
    "殿後", "尾二", "尾三", "尾四", "入直路",
    "鬥快", "起步", "衝刺", "騎師", "練馬師"
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/config/phonetic_lexicons/racing_terms.json
git commit -m "feat(phonetic): ToJyutping 依賴 + 賽馬術語 lexicon"
```

---

### Task 2: `backend/phonetic_correction.py` — Stage 0 + 索引 + AUTO tier（TDD）

**Files:**
- Create: `backend/phonetic_correction.py`
- Test: `backend/tests/test_phonetic_correction.py`

- [ ] **Step 1: failing tests（核心匹配）**

```python
# backend/tests/test_phonetic_correction.py
"""粵拼語音糾錯 — port 自 2026-06-13 lang-quality 研究 protos（B1/B4 實證行為基準）。"""
import json

import pytest

import phonetic_correction as pc


GLOSS = [{"name": "賽馬", "entries": [
    {"source": "STELLAR EXPRESS", "target": "星際快車 (E123)"},
    {"source": "BEST PAL", "target": "好友心得 (D456)"},
    {"source": "PATCH OF STARS", "target": "錶之星河 (J343)"},
    {"source": "MARK", "target": "飈誌 (X001)"},      # 同「標誌」L1 全同音 — ≥3字 gate 防線
]}]
LEX = ["內欄位置", "殿後"]


def _segs(*texts):
    return [{"start": float(i), "end": float(i + 1), "text": t} for i, t in enumerate(texts)]


def test_jyutping_utils():
    assert pc.jyut_seq("星際快車") == pc.jyut_seq("升制快車")      # L1 全同音（研究實證）
    assert pc.toneless("sing1") == "sing"
    assert pc.edit_le1(["sing1", "zai3"], ["sing1", "zai3"]) == 0


def test_build_index_strips_code_and_merges_lexicon():
    idx = pc.build_index(GLOSS, LEX)
    names = {e["name"] for e in idx["entries"]}
    assert "星際快車" in names and "(E123)" not in str(names)
    assert "內欄位置" in names                                     # lexicon merge
    assert all("syls" in e for e in idx["entries"])


def test_stage0_m_rule():
    out, ch = pc.stage0_rules("M2 橙衫笑傲江湖", "racing")
    assert out.startswith("尾二")
    assert ch and ch[0]["before"] == "M2" and ch[0]["after"] == "尾二"
    out2, ch2 = pc.stage0_rules("M2 橙衫", "generic")              # 非 racing 唔啟用
    assert out2 == "M2 橙衫" and ch2 == []


def test_auto_tier_l1_exact_replaces():
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("見到升制快車走上去"), idx)
    assert segs[0]["text"] == "見到星際快車走上去"
    assert changes[0][0]["before"] == "升制快車"
    assert changes[0][0]["after"] == "星際快車"
    assert changes[0][0]["glossary"] == "語音糾正"


def test_auto_tier_min_3char_gate():
    # 「標誌」↔「飈誌」L1 全同音但 target 2 字 → 唔准自動替換（防誤殺日常語）
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("路邊有個標誌"), idx)
    assert segs[0]["text"] == "路邊有個標誌"
    assert changes[0] == []


def test_auto_tier_verbatim_name_untouched():
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("星際快車保持領先"), idx)
    assert segs[0]["text"] == "星際快車保持領先"
    assert changes[0] == []


def test_english_content_noop():
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("the quick brown fox"), idx)
    assert segs[0]["text"] == "the quick brown fox"
```

- [ ] **Step 2: 跑測試確認 fail**（`ModuleNotFoundError`）

- [ ] **Step 3: 實現 module 骨架＋port** — 開檔 `backend/phonetic_correction.py`，docstring 註明 port 來源；**逐個 function 由 proto 照搬**（映射表喺 plan 頭；`build_index` 改簽名 `build_index(glossaries, lexicon_terms)`，內部行為不變：strip ` (編號)`、≥2 字過濾、syls/toneless/fuzzy 三級索引）。公開 API：

```python
"""粵拼語音糾錯 — 三層 stage（pure module，無 Flask）。

Port 自已驗證研究 protos（docs/superpowers/specs/2026-06-13-lang-quality-research/protos/）：
B1 匹配器（AUTO tier precision 1.0 @ 27/34 recall）+ B4 組合 pipeline（34/36 修復 @ 1 FP）。
演算法行為以 B1-phonetic.md / B4-combined.md 為基準 — 改動任何 gate 要重跑驗證。
Spec: docs/superpowers/specs/2026-06-13-phonetic-correction-design.md
"""
from typing import Callable, List, Optional, Tuple

MIN_TARGET_LEN = 3          # 「飈誌/標誌」實證防線
AUTO_TAG = "語音糾正"
JUDGE_TAG = "語音糾正(AI判決)"


def load_lexicon(mt_style: str) -> List[str]:
    """config/phonetic_lexicons/<style>_terms.json 嘅 terms（冇就空 list）。"""


def build_index(glossaries: Optional[List[dict]], lexicon_terms: List[str]) -> dict: ...
def stage0_rules(text: str, mt_style: str) -> Tuple[str, List[dict]]: ...
def auto_tier(segments: List[dict], index: dict) -> Tuple[List[dict], List[List[dict]]]: ...
```

（`auto_tier` 內部 = proto `match_segments` 出候選 → `in_auto_tier` filter → `verbatim_name_ranges`+`blocked_by_protection` 保護 → `greedy_apply`；changes item 統一 `{source, before, after, glossary: AUTO_TAG}`，`source` 用「粵拼」字眼會同現有 glossary UI 撈亂 — 用 `before` 原字做 source。）

- [ ] **Step 4: 跑 Step 1 測試全 pass；Commit**

```bash
git add backend/phonetic_correction.py backend/tests/test_phonetic_correction.py
git commit -m "feat(phonetic): Stage0 M-rule + 粵拼索引 + AUTO tier（port 自 B1/B4 protos）"
```

---

### Task 3: LLM 判決 tier + orchestrator（TDD）

**Files:**
- Modify: `backend/phonetic_correction.py`
- Test: `backend/tests/test_phonetic_correction.py`（追加）

- [ ] **Step 1: 追加 failing tests**

```python
# ---------- Stage 2 受限 LLM 判決 ----------

def _fake_llm_accept_all(system, user):
    # build_judge_user 會喺 user prompt 逐行列 candidates「[N] …」；fake 全 accept
    import re
    ids = re.findall(r'^\[(\d+)\]', user, flags=re.M)
    return json.dumps({"accepts": [int(i) for i in ids]})


def _fake_llm_reject_all(system, user):
    return json.dumps({"accepts": []})


def test_judge_tier_accepts_d1_candidate():
    idx = pc.build_index(GLOSS, LEX)
    # 內藍米字 vs 內欄位置：d=1 fuzzy（研究實證 case）→ AUTO 唔郁，判決 tier 接手
    segs = _segs("內藍米字錶之星河")
    segs1, ch1 = pc.auto_tier(segs, idx)
    segs2, ch2 = pc.judge_tier(segs1, idx, _fake_llm_accept_all, votes=1)
    assert "內欄位置" in segs2[0]["text"]
    assert any(c["glossary"] == pc.JUDGE_TAG for c in ch2[0])


def test_judge_tier_reject_keeps_text():
    idx = pc.build_index(GLOSS, LEX)
    segs, ch = pc.judge_tier(_segs("內藍米字錶之星河"), idx, _fake_llm_reject_all, votes=1)
    assert segs[0]["text"] == "內藍米字錶之星河"
    assert ch[0] == []


def test_judge_majority_vote():
    idx = pc.build_index(GLOSS, LEX)
    calls = {"n": 0}

    def flaky(system, user):
        calls["n"] += 1
        return _fake_llm_accept_all(system, user) if calls["n"] != 2 else _fake_llm_reject_all(system, user)
    segs, ch = pc.judge_tier(_segs("內藍米字錶之星河"), idx, flaky, votes=3)
    assert "內欄位置" in segs[0]["text"]       # 2/3 票 accept（≥3 字候選）


def test_judge_two_char_needs_unanimous():
    idx = pc.build_index(GLOSS, LEX)
    calls = {"n": 0}

    def two_of_three(system, user):
        calls["n"] += 1
        return _fake_llm_accept_all(system, user) if calls["n"] != 2 else _fake_llm_reject_all(system, user)
    # 電流→殿後（2 字候選）2/3 票 → 唔准（seg17 FP 教訓：2 字要全票）
    segs, ch = pc.judge_tier(_segs("暫時電流精算暴雪"), idx, two_of_three, votes=3)
    assert "電流" in segs[0]["text"]


def test_judge_cancel_check_raises():
    class _C(Exception):
        pass

    def boom():
        raise _C()
    idx = pc.build_index(GLOSS, LEX)
    with pytest.raises(_C):
        pc.judge_tier(_segs("內藍米字錶之星河"), idx, _fake_llm_accept_all, votes=1, cancel_check=boom)


# ---------- orchestrator ----------

def test_correct_segments_end_to_end():
    segs = _segs("M2 升制快車內藍米字")
    out, changes = pc.correct_segments(segs, glossaries=GLOSS, mt_style="racing",
                                       llm_call=_fake_llm_accept_all, use_llm=True, votes=1)
    t = out[0]["text"]
    assert t.startswith("尾二") and "星際快車" in t and "內欄位置" in t
    assert len(changes) == len(segs)
    tags = {c["glossary"] for c in changes[0]}
    assert pc.AUTO_TAG in tags                       # stage0+auto 都記做 AUTO_TAG 或 stage0 自己 tag


def test_correct_segments_no_glossary_only_stage0():
    out, changes = pc.correct_segments(_segs("M3 升制快車"), glossaries=None, mt_style="racing",
                                       llm_call=None, use_llm=False)
    assert out[0]["text"].startswith("尾三")
    assert "升制快車" in out[0]["text"]              # 無 glossary → 馬名層唔行（lexicon 照行）
    assert isinstance(changes, list) and len(changes) == 1


def test_correct_segments_immutable():
    segs = _segs("升制快車")
    pc.correct_segments(segs, glossaries=GLOSS, mt_style="racing", use_llm=False)
    assert segs[0]["text"] == "升制快車"             # 入參唔准 mutate
```

- [ ] **Step 2: fail 確認** → **Step 3: 實現**：

```python
def judge_tier(segments, index, llm_call, votes: int = 3,
               cancel_check: Optional[Callable[[], None]] = None
               ) -> Tuple[List[dict], List[List[dict]]]:
    """L3 d=1 候選 → 受限 LLM 判決（accept/reject only）→ 機械 apply。

    五重 guardrail（B4 原樣）：①輸出限 {"accepts":[id…]} ②正名保護
    ③near-substitution onset/rim gate ④votes-run majority（2 字候選要全票）
    ⑤音節對齊 tie-break。每段判決前 call cancel_check。"""


def correct_segments(segments, glossaries=None, mt_style="generic", llm_call=None,
                     cancel_check=None, use_llm=True, votes: int = 3
                     ) -> Tuple[List[dict], List[List[dict]]]:
    """三層 orchestrator。回 (new_segments, per_seg_changes)，changes 同 segments 等長。
    中文判定由 caller 負責（呢度唔 gate 語言）。"""
    lexicon = load_lexicon(mt_style)
    index = build_index(glossaries, lexicon)
    out, all_changes = [], []
    for s in segments:
        t, ch = stage0_rules(s.get("text") or "", mt_style)
        out.append({**s, "text": t})
        all_changes.append(ch)
    out, auto_ch = auto_tier(out, index)
    all_changes = [a + b for a, b in zip(all_changes, auto_ch)]
    if use_llm and llm_call is not None and index["entries"]:
        out, judge_ch = judge_tier(out, index, llm_call, votes=votes, cancel_check=cancel_check)
        all_changes = [a + b for a, b in zip(all_changes, judge_ch)]
    return out, all_changes
```

（judge_tier 內部 port：`llm_tier_filter`→`prune_candidates`→`build_judge_user`（candidate 行格式 `[N] 原句span → 候選名（粵拼證據）`）→ votes 次 `llm_call`→`parse_accepts`→2字全票 knob→`blocked_by_protection`+`align_quality`+`greedy_apply`。judge 失敗（JSON 爆/LLM 異常）→ 該段保留原文、changes 空 — **fail-open 唔 fail-job**，但 cancel_check raise 要照傳。）

- [ ] **Step 4: 全檔 pass + commit**

```bash
git add backend/phonetic_correction.py backend/tests/test_phonetic_correction.py
git commit -m "feat(phonetic): 受限 LLM 判決 tier（五重 guardrail+majority vote）+ correct_segments orchestrator"
```

---

### Task 4: app.py 掛鈎（兩個位）+ 整合測試

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_phonetic_hook.py`（新）

- [ ] **Step 1: failing 整合測試**

```python
# backend/tests/test_phonetic_hook.py
"""bound_base 掛鈎：base 糾正 + glossary_changes 記錄落 rows。"""
import pytest

pytest.importorskip("flask")
import app as appmod


GLOSS = {"id": "g1", "name": "賽馬", "entries": [
    {"source": "STELLAR EXPRESS", "target": "星際快車 (E123)"}]}


def test_bound_base_corrects_and_records(monkeypatch, tmp_path):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "transcribe_with_segments", lambda *a, **k: {
        "segments": [{"start": 0.0, "end": 2.0, "text": "見到升制快車走上去"}]})
    monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    fid = "f-pc-hook"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "user_id": "u1", "status": "transcribing",
                                      "active_kind": "output_lang", "output_languages": ["yue"],
                                      "source_language": "yue", "script": "trad"}
    appmod._run_output_lang_bound_base(fid, {"id": "j1"}, "/fake/audio.wav", None, ["yue"],
                                       "yue", "trad", mt_style="racing",
                                       do_clause_split=False, glossaries=[GLOSS], glossary_llm=False)
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        assert e["translations"][0]["yue_text"] == "見到星際快車走上去"      # 口語 track 繼承
        assert e["segments"][0]["text"] == "見到星際快車走上去"             # base persist
        gc = e["translations"][0].get("glossary_changes") or []
        assert any(c.get("after") == "星際快車" and "語音糾正" in c.get("glossary", "") for c in gc)
```

注意：`use_llm` 喺 hook 度傳 `glossary_llm`（檔案現有設定 — 用戶剔咗「AI 判詞彙」先行 judge tier，行為一致直觀）。`bound_base` 簽名要核對實際 kwargs（mt_style/do_clause_split/glossaries/glossary_llm）— 上面照 app.py 現況寫，執行時 verify。

- [ ] **Step 2: fail 確認** → **Step 3: hook 實現**

(a) `_run_output_lang_bound_base`（`cancel_check = _make_cancel_check(cancel_event)` 之後、`derived = {...}` 之前）：

```python
        # 粵拼語音糾錯（P0+P1）：derive 之前修正 base 同音錯字 — 口語/書面語/MT 全 track 繼承。
        # 研究：docs/superpowers/specs/2026-06-13-lang-quality-research/（34/36 修復 @ 1 FP）
        _pc_changes = None
        if content_lang in ("yue", "zh"):
            from phonetic_correction import correct_segments as _pc_correct
            base, _pc_changes = _pc_correct(base, glossaries=glossaries, mt_style=mt_style,
                                            llm_call=llm, cancel_check=cancel_check,
                                            use_llm=glossary_llm)
```

(b) `rows = build_output_translations(...)` 之後：

```python
        if _pc_changes:
            rows = [({**r, "glossary_changes": (_pc_changes[i] + (r.get("glossary_changes") or []))}
                     if i < len(_pc_changes) and _pc_changes[i] else r)
                    for i, r in enumerate(rows)]
```

(c) `_produce_output_lang` whisper-direct 路徑（`base = (res or {}).get("segments") or []` 之後）：

```python
        if base and content_lang in ("yue", "zh"):
            from phonetic_correction import correct_segments as _pc_correct
            base, _pc2 = _pc_correct(base, glossaries=glossaries, mt_style=mt_style,
                                     llm_call=_make_ollama_llm_call(),
                                     cancel_check=_make_cancel_check(cancel_event),
                                     use_llm=glossary_llm)
            if any(_pc2):
                base = [({**s, "glossary_changes": (_pc2[i] + (s.get("glossary_changes") or []))}
                         if _pc2[i] else s) for i, s in enumerate(base)]
```

（(c) 段 glossary_changes 之後仲會被 `olg.glossary_stage` 處理 — 執行時核對 glossary_stage 係 overwrite 定 preserve `glossary_changes`；如 overwrite，將 (c) 嘅 merge 移去 glossary_stage block 之後。）

- [ ] **Step 4: 跑 test_phonetic_hook + test_phonetic_correction + regression（test_output_lang_aligned / test_output_lang_glossary / test_crosslang_mt）+ `FLASK_SECRET_KEY=test python -c "import app"`**

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_phonetic_hook.py
git commit -m "feat(phonetic): bound_base + produce 掛鈎 — base 糾正 + glossary_changes 記錄"
```

---

### Task 5: P1.5 多 clip 離線驗證（GATING — orchestrator 親自做）

- [ ] 寫離線 runner `/tmp/pc_validate.py`：對 registry 兩條其他賽馬片（揀 active_kind=output_lang、yue 源 — 例如 48c1657e7ec1 同 賽後兩點晚/袁幸堯 任一）：攞 `content_asr_segments` → `correct_segments`（真 glossary + 真 qwen3.5 llm）→ 列晒每個替換（AUTO/JUDGE 分開）
- [ ] 逐個替換人工/LLM-judge 覆核：正確/錯誤/不確定。**AUTO tier 出現任何誤改 → 收緊 gate 再跑**
- [ ] 寫 `docs/superpowers/specs/2026-06-13-phonetic-correction-validation-tracker.md`（✅/⚠️/❌ per 假設 + 數字）

### Task 6: E2E + 文檔

- [ ] dev ff + 重啟 :5001 → 對 09e0e3679f35 撳「重新處理」（保留設定）→ 完成後 API 攞 translations 對研究預期核對（升制快車→星際快車、內藍米字→內欄位置、M2→尾二…；proofread 詞彙對照見「語音糾正」記錄）
- [ ] CLAUDE.md：Current State 加「粵拼語音糾錯 (P0+P1, 2026-06-13)」段 + 架構段一句；README：輸出語言章節加用戶說明（繁中）
- [ ] Commit `docs: 粵拼語音糾錯功能`

---

## 驗收清單

- [ ] test_phonetic_correction.py + test_phonetic_hook.py 全 PASS（單獨跑）；regression 三檔 PASS；import app OK
- [ ] P1.5 兩 clip 驗證：AUTO tier 零誤改（或收緊後零誤改）；tracker 寫好
- [ ] E2E：09e0e3679f35 重新處理後修復可見 + proofread 記錄可見
- [ ] CLAUDE.md + README 更新
