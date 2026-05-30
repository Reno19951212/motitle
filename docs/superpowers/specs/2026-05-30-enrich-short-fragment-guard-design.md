# Pass-2 Enrichment 短 fragment guard

**日期**：2026-05-30
**Branch**：`fix/profile-and-v6`
**範圍**：`backend/translation/ollama_engine.py::_enrich_pass`（+ tests）
**狀態**：Design — 待 user review

---

## 1. 問題（已實證）

`translation_passes: 2` 嘅 Pass-2 enrichment 對**短 source fragment** 過度膨脹兼虛構內容。診斷（[backend/scripts/profile_prototype/diag_enrich.py](../../../backend/scripts/profile_prototype/diag_enrich.py)，真 qwen3.5:35b，passes=1 vs 2）：

| Source | Pass-1（passes=1） | Pass-2（passes=2） |
|---|---|---|
| 粟米片(3) | 玉米片(3，1.0×)✅ | 呢款食品係由穀物壓製而成…(21，**7×**) |
| 豆腐花(3) | 豆花(2，1.0×)✅ | 用大豆磨成嘅豆漿經凝固劑點製…(30，**10×**，虛構) |
| 貓,超喜歡貓(6) | 我超級愛貓(6，1.0×)✅ | 佢對貓咪鍾情到極點…(28，4.7×) |
| …試習(14) | (13，0.9×) | (27，1.9×) |

短句(≤6字)平均 bloat：**passes=1 = 1.0× / passes=2 = 6.8×**。

## 2. Root cause（隔離確定）

bloat **唔關 single-segment prompt 事**（Pass-1 ratio ~1.0、精準）。係 **Pass-2 `ENRICH_SYSTEM_PROMPT`**（[ollama_engine.py:199](../../../backend/translation/ollama_engine.py)）有條**無條件硬規則**「短於 18 字嘅輸出需重寫更長版本」+「少於 20 字需加強」 —— prompt **完全唔知 source 長度**，3 字 source 都谷到 ≥18 字 → minimal noun-fragment 被迫虛構描述。`_enrich_pass`（[ollama_engine.py:420](../../../backend/translation/ollama_engine.py)）對每個 batch 一律 enrich，冇短句豁免。

## 3. 目標 / 決策（Option 1：source-length guard）

`_enrich_pass` 只 enrich `len(source) >= K` 嘅 segment；短 source（minimal utterance，enrich 必虛構）保留 Pass-1 嘅精準輸出。`K` 可 config，預設 **10**（由數據：enrich 輸出 floor=18，src≥10 → post-enrich ratio ≤1.8× 可接受；src<10 排除虛構-prone fragment）。

rejected：source-length-aware prompt（靠 LLM 跟，唔可靠）。

## 4. 設計

### 4.1 `_enrich_pass` 加 source-length guard（`backend/translation/ollama_engine.py`）

- 新常數 `DEFAULT_ENRICH_MIN_SRC_CHARS = 10`（module-level）。
- `_enrich_pass` 開頭讀 `min_chars = self._config.get("enrich_min_src_chars", DEFAULT_ENRICH_MIN_SRC_CHARS)`。
- 改 batching：只將 `len((seg.get("text") or "").strip()) >= min_chars` 嘅 segment 放入 enrich batch（記住原 index）；短 segment 直接保留 `pass1_results[i]`（已喺 `enriched_total` copy 入面）。enrich 完寫返原 index。
- 行為（immutable）：`enriched_total = list(pass1_results)`；只覆寫 eligible 嘅；短句完全唔經 LLM enrich。
- Batch-failure fallback（保留 Pass-1）行為不變。

實作骨架：
```python
DEFAULT_ENRICH_MIN_SRC_CHARS = 10  # module-level

def _enrich_pass(self, segments, pass1_results, batch_size, glossary,
                 temperature, progress_callback=None, total=0, runtime_overrides=None):
    if not pass1_results or len(pass1_results) != len(segments):
        return pass1_results
    enriched_total = list(pass1_results)
    min_chars = int(self._config.get("enrich_min_src_chars", DEFAULT_ENRICH_MIN_SRC_CHARS))
    # 2026-05-30: skip enrichment for short source fragments — the enrich prompt's
    # unconditional 18-char floor pads/hallucinates minimal utterances (粟米片→7-10×).
    eligible = [(i, segments[i], pass1_results[i]) for i in range(len(segments))
                if len((segments[i].get("text") or "").strip()) >= min_chars]
    for b in range(0, len(eligible), batch_size):
        chunk = eligible[b:b + batch_size]
        try:
            enriched_batch = self._enrich_batch(
                [c[1] for c in chunk], [c[2] for c in chunk],
                glossary, temperature, runtime_overrides=runtime_overrides)
            for (orig_i, _, _), entry in zip(chunk, enriched_batch):
                enriched_total[orig_i] = entry
        except Exception as e:
            print(f"[enrich] batch starting {b} failed: {e}", file=sys.stderr)
            continue
    if progress_callback is not None and total:
        try:
            progress_callback(total, total)
        except Exception:
            pass
    return enriched_total
```

## 5. 測試

**Unit（`backend/tests/test_enrich_guard.py`，用 fake/stub LLM，無真 Ollama）** — 用一個 stub engine（monkeypatch `_enrich_batch` 記錄收到邊啲 segment + 返加長文字）：
- 短 source（`粟米片` 3 字 < 10）→ `_enrich_batch` **冇收到**佢，輸出 == Pass-1。
- 長 source（14 字 ≥ 10）→ `_enrich_batch` **收到**，輸出 == enriched。
- 混合 batch：只長嘅入 enrich，短嘅保 Pass-1，最終 list 長度 + index 對齊正確。
- `enrich_min_src_chars` config override（set 0 → 全部 enrich；set 999 → 全部 skip）。
- Immutability：`pass1_results` 輸入唔被 mutate。
- batch fallback（`_enrich_batch` raise）→ eligible 嗰段保 Pass-1，唔崩。

**Integration（非破壞性，真 Ollama，sample harness）** — reuse diag_enrich，跑 passes=2 **加 guard**：短 fragment（粟米片/豆腐花/貓）ratio 回到 ~1.0（== Pass-1）；中長句（≥10 字）仍 enrich（ratio ~1.5-1.9）。

## 6. 範圍外
- `ENRICH_SYSTEM_PROMPT` 文字本身唔改（保留中長句 enrichment 行為）。
- single-segment / Pass-1 prompt 唔改（已精準）。
- 其他 translation_passes=1 profile 不受影響（根本唔行 enrich）。
- alignment / V6 唔涉及。

## 7. 風險
| 風險 | 緩解 |
|---|---|
| K 太高 → 連正當中句都唔 enrich | K=10 由數據 bracketing（6 bad / 14 ok）；config 可調；integration 確認中長句仍 enrich |
| 影響 EN→ZH broadcast | guard 係通用改善（短 fragment 任何語言都唔應虛構）；EN→ZH 短 fragment 同樣受惠；integration 可加 EN sample 確認 |
| index 對齊錯 | unit test 鎖死混合 batch 嘅 index 對齊 |

## 8. 驗收標準
1. Unit test 全綠（短 skip / 長 enrich / 混合對齊 / config / immutability / fallback）。
2. Integration：短 fragment(<10) ratio ~1.0（保 Pass-1）、中長句(≥10) 仍 enrich。
3. `pytest` 無新 regression（現有 translation tests 不受影響）。
4. `enrich_min_src_chars=0` 可完全還原舊行為（全部 enrich）。
