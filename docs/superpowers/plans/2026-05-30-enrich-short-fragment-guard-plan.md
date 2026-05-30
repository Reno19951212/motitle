# Pass-2 Enrichment 短 fragment guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_enrich_pass` 只 enrich `len(source) >= K`（預設 10）嘅 segment，短 source 保留精準 Pass-1 輸出，消除短 fragment 7-10× bloat / 虛構。

**Architecture:** 喺 `backend/translation/ollama_engine.py::_enrich_pass` 加 source-length guard（config `enrich_min_src_chars`，預設常數 10）。只改 batching：eligible（src≥K）入 enrich batch，短 source 保 Pass-1。Immutable、batch-failure fallback 行為不變。Prompt / Pass-1 / 其他 path 唔郁。

**Tech Stack:** Python 3.9、pytest（stub LLM，無真 Ollama）。

**Spec:** [docs/superpowers/specs/2026-05-30-enrich-short-fragment-guard-design.md](../specs/2026-05-30-enrich-short-fragment-guard-design.md)

---

## File Structure
| 檔案 | 動作 |
|---|---|
| `backend/translation/ollama_engine.py` | **Modify** — 加 `DEFAULT_ENRICH_MIN_SRC_CHARS` 常數 + `_enrich_pass` eligible-filter batching |
| `backend/tests/test_enrich_guard.py` | **Create** — stub-LLM unit tests |
| `backend/scripts/profile_prototype/diag_enrich.py` | **Modify (optional)** — 加 guard 後 integration 對比（Task 2） |
| `CLAUDE.md` | **Modify** — 記錄 fix |

---

## Task 1: `_enrich_pass` source-length guard + unit tests

**Files:**
- Modify: `backend/translation/ollama_engine.py`
- Create: `backend/tests/test_enrich_guard.py`

- [ ] **Step 1: 加 module-level 常數**

喺 `backend/translation/ollama_engine.py`，喺 `ENRICH_SYSTEM_PROMPT = (` 定義（約 line 199）**之前**加：

```python
# 2026-05-30: Pass-2 enrich pads outputs to an unconditional ~18-char floor,
# which bloats/hallucinates minimal source fragments (粟米片→7-10×). Skip
# enrichment for sources shorter than this (configurable via profile
# translation.enrich_min_src_chars).
DEFAULT_ENRICH_MIN_SRC_CHARS = 10
```

- [ ] **Step 2: 改 `_enrich_pass` batching（加 eligible filter）**

喺 `_enrich_pass` 入面，將現有呢段（約 line 440-457）：

```python
        enriched_total = list(pass1_results)  # shallow copy
        batches_meta = []
        for i in range(0, len(segments), batch_size):
            batches_meta.append((i, segments[i:i + batch_size],
                                 pass1_results[i:i + batch_size]))

        for batch_start, batch_segs, batch_p1 in batches_meta:
            try:
                enriched_batch = self._enrich_batch(
                    batch_segs, batch_p1, glossary, temperature,
                    runtime_overrides=runtime_overrides,
                )
                for j, entry in enumerate(enriched_batch):
                    enriched_total[batch_start + j] = entry
            except Exception as e:
                print(f"[enrich] batch starting {batch_start} failed: {e}", file=sys.stderr)
                # Keep Pass 1 for this batch
                continue
```

替換為：

```python
        enriched_total = list(pass1_results)  # shallow copy
        # 2026-05-30: only enrich segments whose source is long enough; short
        # sources (minimal utterances) keep their accurate Pass-1 output —
        # the enrich prompt's 18-char floor otherwise pads/hallucinates them.
        min_chars = int(self._config.get("enrich_min_src_chars", DEFAULT_ENRICH_MIN_SRC_CHARS))
        eligible = [
            (i, segments[i], pass1_results[i])
            for i in range(len(segments))
            if len((segments[i].get("text") or "").strip()) >= min_chars
        ]

        for b in range(0, len(eligible), batch_size):
            chunk = eligible[b:b + batch_size]
            try:
                enriched_batch = self._enrich_batch(
                    [c[1] for c in chunk], [c[2] for c in chunk],
                    glossary, temperature, runtime_overrides=runtime_overrides,
                )
                for (orig_i, _seg, _p1), entry in zip(chunk, enriched_batch):
                    enriched_total[orig_i] = entry
            except Exception as e:
                print(f"[enrich] batch starting {b} failed: {e}", file=sys.stderr)
                # Keep Pass 1 for this batch's segments
                continue
```

- [ ] **Step 3: 寫 unit tests**

建立 `backend/tests/test_enrich_guard.py`：

```python
from translation.ollama_engine import (
    OllamaTranslationEngine, DEFAULT_ENRICH_MIN_SRC_CHARS,
)


def _seg(text):
    return {"start": 0.0, "end": 1.0, "text": text}


def _ts(zh):
    return {"start": 0.0, "end": 1.0, "en_text": "", "zh_text": zh}


def _engine(cfg=None):
    return OllamaTranslationEngine(dict(cfg or {}))


def _stub_enrich(received):
    def fake(batch_segs, batch_p1, glossary, temperature, runtime_overrides=None):
        received.extend(s["text"] for s in batch_segs)
        return [{**p, "zh_text": p["zh_text"] + "（加長）"} for p in batch_p1]
    return fake


def test_short_source_skips_enrich(monkeypatch):
    e = _engine()
    received = []
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich(received))
    segs = [_seg("粟米片"), _seg("兩位是剛剛星期二都有現身試習")]  # 3, 14 chars
    p1 = [_ts("玉米片"), _ts("兩人上週二現身試習")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert "粟米片" not in received                      # short skipped
    assert "兩位是剛剛星期二都有現身試習" in received      # long enriched
    assert out[0]["zh_text"] == "玉米片"                  # short kept Pass-1
    assert out[1]["zh_text"].endswith("（加長）")          # long enriched


def test_mixed_batch_index_alignment(monkeypatch):
    e = _engine()
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich([]))
    segs = [_seg("粟米片"), _seg("這是一個足夠長的中文句子內容"), _seg("豆腐花")]  # short, long, short
    p1 = [_ts("玉米片"), _ts("呢個係一個夠長句子"), _ts("豆花")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert len(out) == 3
    assert out[0]["zh_text"] == "玉米片"        # short, kept
    assert out[1]["zh_text"].endswith("（加長）")  # long, enriched at index 1
    assert out[2]["zh_text"] == "豆花"          # short, kept


def test_config_override_zero_enriches_all(monkeypatch):
    e = _engine({"enrich_min_src_chars": 0})
    received = []
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich(received))
    segs = [_seg("粟米片"), _seg("豆腐花")]
    p1 = [_ts("玉米片"), _ts("豆花")]
    e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert received == ["粟米片", "豆腐花"]      # all enriched when K=0


def test_config_override_high_skips_all(monkeypatch):
    e = _engine({"enrich_min_src_chars": 999})
    received = []
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich(received))
    segs = [_seg("這是一個足夠長的中文句子內容")]
    p1 = [_ts("呢個係一個夠長句子")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert received == []                       # none enriched when K huge
    assert out[0]["zh_text"] == "呢個係一個夠長句子"


def test_input_not_mutated(monkeypatch):
    import copy
    e = _engine()
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich([]))
    segs = [_seg("這是一個足夠長的中文句子內容")]
    p1 = [_ts("呢個係一個夠長句子")]
    p1_snap = copy.deepcopy(p1)
    e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert p1 == p1_snap                         # input pass1_results untouched


def test_batch_failure_keeps_pass1(monkeypatch):
    e = _engine()

    def boom(*a, **k):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(e, "_enrich_batch", boom)
    segs = [_seg("這是一個足夠長的中文句子內容")]
    p1 = [_ts("呢個係一個夠長句子")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert out[0]["zh_text"] == "呢個係一個夠長句子"   # fallback to Pass-1, no crash


def test_default_threshold_is_ten():
    assert DEFAULT_ENRICH_MIN_SRC_CHARS == 10
```

- [ ] **Step 4: 跑 + 確認 PASS**

Run: `cd backend && source venv/bin/activate && pytest tests/test_enrich_guard.py -v`
Expected: 7 passed。若 `OllamaTranslationEngine({})` 構造失敗（缺 config key），檢查 __init__ 需要嘅最小 config，喺 `_engine()` 補返（但盡量唔好改 production；engine 應該接受任意 config dict）。

- [ ] **Step 5: 跑現有 translation 測試確認無 regression**

Run: `cd backend && source venv/bin/activate && pytest tests/test_translation.py -q 2>&1 | tail -8`
（用 `ls tests/ | grep -iE "translat|ollama|enrich"` 確認檔名。）
Expected: 全綠（guard 對 src≥K 行為不變；現有 enrich tests 嘅 segment 多數 ≥10 字，若有用短 segment 測 enrich 嘅 case 可能要 set `enrich_min_src_chars=0` — 如遇此情況，report，由 controller 判斷）。

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/translation/ollama_engine.py backend/tests/test_enrich_guard.py
git commit -m "fix(mt): skip Pass-2 enrichment for short source fragments (anti-bloat guard)"
```

---

## Task 2: Integration 驗證（真 Ollama）+ 文檔

**Files:**
- Modify: `backend/scripts/profile_prototype/diag_enrich.py`（加 guard 後對比）
- Modify: `CLAUDE.md`

- [ ] **Step 1: 加 guard-on 對比到 diag_enrich.py**

喺 `backend/scripts/profile_prototype/diag_enrich.py` 末加一個第三欄：用 passes=2 **加** `enrich_min_src_chars=10`（即 production 新行為）跑同一組 test segment，print「passes=2+guard」嘅 zh + len + ratio。（engine config 加 `"enrich_min_src_chars": 10"`。）

Run: `cd backend && source venv/bin/activate && python3 scripts/profile_prototype/diag_enrich.py 2>&1 | grep -v "NotOpenSSL\|warnings.warn"`
Expected：短 fragment（粟米片/豆腐花/貓 <10 字）喺「passes=2+guard」欄 ratio 回到 ~1.0（== Pass-1，無虛構）；中長句（≥10 字，如 14/16 字嗰兩條）仍 enrich（ratio ~1.5-1.9）。記錄輸出。

- [ ] **Step 2: 更新 CLAUDE.md**

喺「Completed Features」最上插入：

```markdown
### Pass-2 Enrichment 短 fragment guard（2026-05-30）
- **問題**：`translation_passes: 2` 嘅 Pass-2 enrichment 對短 source fragment 過度膨脹兼虛構（粟米片→「呢款食品係由穀物壓製而成…」7-10×）。
- **Root cause**：`ENRICH_SYSTEM_PROMPT` 有無條件硬規則「短於 18 字嘅輸出需重寫更長」，唔知 source 長度 → minimal utterance 被迫虛構描述。隔離驗證（diag_enrich.py passes=1 vs 2）：短句(≤6字) passes=1 ratio 1.0、passes=2 ratio 6.8×。
- **修復**：`ollama_engine.py::_enrich_pass` 加 source-length guard — 只 enrich `len(source) >= enrich_min_src_chars`（預設 10）嘅 segment，短 source 保留精準 Pass-1 輸出。Config `translation.enrich_min_src_chars`（0 = 還原舊行為全 enrich）。
- **範圍**：只 `_enrich_pass` batching。ENRICH prompt 文字 / Pass-1 / single-segment / 其他 path 唔郁。通用改善（任何語言短 fragment 受惠）。
- **Validation-First**：隔離診斷（[diag_enrich.py]）定位 Pass-2 為 bloat 源；7 unit test（stub LLM）+ integration 對比驗證短句保 Pass-1、中長句仍 enrich。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-enrich-short-fragment-guard-design.md) / [plan](docs/superpowers/plans/2026-05-30-enrich-short-fragment-guard-plan.md)。
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/scripts/profile_prototype/diag_enrich.py CLAUDE.md
git commit -m "docs+verify: enrich short-fragment guard — integration compare + CLAUDE.md"
```

---

## 驗收標準（對應 spec §8）
1. ✅ 7 unit test 全綠（短 skip / 長 enrich / 混合 index 對齊 / config 0 / config 999 / immutability / batch fallback）。
2. ✅ Integration：短 fragment(<10) ratio ~1.0（保 Pass-1）、中長句(≥10) 仍 enrich（Task 2）。
3. ✅ `pytest` 無新 regression。
4. ✅ `enrich_min_src_chars=0` 還原舊行為（test 覆蓋）。

## Self-Review notes
- **Spec coverage**：§4.1 guard→Task 1；§5 unit→Task 1 Step 3、integration→Task 2 Step 1；§8→上表。全覆蓋。
- **Consistency**：常數 `DEFAULT_ENRICH_MIN_SRC_CHARS=10`、config key `enrich_min_src_chars` 喺 spec / 實作 / tests 一致。
- **No placeholders**：所有 step 有實際 code / 指令 / 預期輸出。
