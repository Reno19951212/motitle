# v3.17 — Preset Trim + ASR Cleanup + Validation Design

**Status**: Draft 2026-05-15
**Branch**: `chore/v3.15-cleanup-2026-05-13`（接住 v3.16 commits）
**Predecessor**: v3.16 per-engine preset refactor

## Goal

縮減用戶可見 surface area，迫向 broadcast-quality 配置 + 確保 v3.17 改動唔負面影響現有工作流。

## Why

- v3.16 引入 5 個 ASR/MT preset，但部分（Speed、Fast Draft）係 quality-degrading 選項，用戶喺廣播 context 唔應該揀
- 後端有 6 個 ASR engine option，但 5 個唔係 `large-v3` 嘅 Whisper model 喺實際工作流冇用、淨係增加 confusion
- `qwen3_engine.py` + `flg_engine.py` 由 v2.0 起一直係 stub，從未 functionally 實裝過 — dead code
- 任何 trim 必須驗證 ASR/MT output quality 唔受負面影響 — Validation-First mode mandate

## Architecture

3 個 logical parts，1 個 branch，按次序執行：

```
Part A (frontend preset trim)
   ↓
Part B (backend engine schema narrow + stub delete + profile migration)
   ↓
Part C (validation: baseline → apply → re-run → diff report → user review)
```

每個 Part 內部用 SDD iteration（implementer + spec review + code quality review）。Part C 嘅 user review step 係 merge gate。

## Part A — Preset Trim（frontend only）

### Changes

| Target | Action |
|---|---|
| `ASR_PRESETS` in [frontend/index.html](frontend/index.html) | 刪 `speed` key。最終保留：`accuracy`, `debug`, `custom`（3 個 chip） |
| `MT_PRESETS` in [frontend/index.html](frontend/index.html) | 刪 `fast-draft` key。最終保留：`broadcast-quality`, `literal-ref`, `custom`（3 個 chip） |
| Playwright Test 2 | Reframe：用 Custom preset → JS direct-mutate `_pendingMtPreset = { config: { parallel_batches: 4 } }` → trigger `_scheduleDangerEval()` → verify `parallel-disables-context` warning chip render。Selector：`#ppsMtDangerWarnings .pps-warning-chip[data-combo-id="parallel-disables-context"]` |
| Playwright Test 4 | Reframe：用 Custom preset → JS direct-mutate `_pendingAsrPreset = { config: { word_timestamps: false } }` + 點 MT Broadcast Quality chip → verify `#ppsMtDangerWarnings` 出 cross-engine warning chip `data-combo-id="word-timestamps-needed-for-alignment"` |

Test 1（ASR Accuracy chip click）+ Test 3（mix-and-match Accuracy + ?）兩個 test 保留，但 Test 3 嘅 MT 由 Fast Draft 改 Broadcast Quality（揀剩落嘅 preset），確認 mix-and-match 仍 work。

### Out of scope

- 唔加新 preset（如將來要加 broadcast-streaming 之類，另開 v3.x）
- 唔改 ASR/MT engine 行為
- 唔改 `ASR_DANGERS` / `MT_DANGERS` warning list（v3.16 已 lock）

## Part B — ASR Cleanup（backend）

### B1：Engine schema narrow

| File | Change |
|---|---|
| [backend/asr/whisper_engine.py](backend/asr/whisper_engine.py) | `WhisperEngine.get_params_schema()` 嘅 `model_size` choices field 改為 `['large-v3']`（或者 enum 同 default 都用 `'large-v3'`） |
| [backend/asr/mlx_whisper_engine.py](backend/asr/mlx_whisper_engine.py) | 同上，`MlxWhisperEngine.get_params_schema()` 嘅 `model_size` enum 收窄 |

前端 dropdown 直接讀 schema 渲染，schema narrow 後 dropdown 自動跟。

### B2：Profile migration

寫 one-shot script `backend/scripts/migrate_v317_asr_models.py`：

```python
# Pseudocode
def migrate_profile(profile_path: Path) -> bool:
    """
    Read profile JSON, normalize asr.model_size → 'large-v3' if not already.
    Returns True if file was modified.
    """
    profile = json.loads(profile_path.read_text())
    if profile.get('asr', {}).get('model_size') and profile['asr']['model_size'] != 'large-v3':
        profile['asr']['model_size'] = 'large-v3'
        profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
        return True
    return False

def main():
    profiles_dir = Path('backend/config/profiles')
    modified = []
    for p in profiles_dir.glob('*.json'):
        if migrate_profile(p):
            modified.append(p.name)
    print(f"Migrated {len(modified)} profile(s): {modified}")
```

Script 跑一次就完成，commit 入 repo 作為 audit trail（將來如要查為何某 profile model 全部係 large-v3，可指返呢個 script）。

### B3：Delete stub engines

| File | Action |
|---|---|
| [backend/asr/qwen3_engine.py](backend/asr/qwen3_engine.py) | DELETE（git rm）|
| [backend/asr/flg_engine.py](backend/asr/flg_engine.py) | DELETE（git rm）|

### B4：Factory cleanup

[backend/asr/__init__.py](backend/asr/__init__.py) 嘅 ASR engine factory `create_asr_engine(config)` dict mapping 內：

- 移除 `'qwen3-asr'` → `Qwen3ASREngine` 嘅 mapping
- 移除 `'flg-asr'` → `FLGASREngine` 嘅 mapping
- 移除 `from .qwen3_engine import Qwen3ASREngine` import
- 移除 `from .flg_engine import FLGASREngine` import

未知 engine name 嘅 fallback 行為（raise `ValueError(f"Unknown ASR engine: {engine_name}")`）已存在；用戶 profile 用咗 qwen3-asr / flg-asr 嘅話會 hit 呢個 error。

### B5：Test cleanup

Grep `backend/tests/` 揾 `qwen3` 或 `flg` reference：

```bash
grep -rn "qwen3\|Qwen3\|flg\|FLG" backend/tests/
```

逐個 case 評估：
- 純 stub-existence test（`test_qwen3_engine_is_stub` 等）→ DELETE
- Factory tests（assert factory rejects unknown engine）→ KEEP 但更新 expected engine list
- Engine list tests（`test_list_asr_engines` 之類）→ 更新 expected count

### B6：Documentation

| File | Change |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 加 v3.17 entry，記錄 preset trim + ASR cleanup + validation results |
| 唔需要改 README.md（用戶 documentation 唔提 stub engine） |

## Part C — Validation（落手前 + 落手後對比）

### C1：Discover videos + profile audit

開 `/api/files` 列出當前 video。期待 2 條（per user spec）。捕捉每條：

- `file_id`, `original_name`, `duration_seconds`
- `profile_id` used at transcription time（從 segments metadata 或 registry 取）
- 該 profile 嘅 `asr.engine`, `asr.model_size`, `translation.engine`, `translation.batch_size`, `translation.parallel_batches`, `translation.alignment_mode`, `translation.glossary_id`

**Gate**：如果有 video 嘅 profile 用咗 `qwen3-asr` / `flg-asr` engine → STOP，提示用戶手動將 profile 改 mlx-whisper / whisper 之後先繼續。

**Gate**：如果有 video 嘅 profile 用咗 non-large-v3 model_size，記低 — C5 重跑會出現實際 output difference，要喺 report 內明確標示。

### C2：Baseline snapshot

寫 helper script `backend/scripts/v317_validation.py`，function `capture_snapshot(file_id) -> dict`：

```python
{
    'file': GET /api/files/<id>,
    'segments': GET /api/files/<id>/segments,
    'translations': GET /api/files/<id>/translations,
    'glossary_scan': POST /api/files/<id>/glossary-scan (if profile has glossary_id, else None),
    'timestamp': iso8601,
    'profile_snapshot': GET /api/profiles/<profile_id>,
}
```

Dump 兩條 video baseline 落：
- `docs/superpowers/validation/v3.17-baseline-{file_id_short}.json`（commit 入 repo — 將來 audit 用）

### C3：Apply v3.17 commits

按次序 commit Part A → Part B 全部改動（仍未 push）。

### C4：Re-run ASR + MT

**自動化**：script `backend/scripts/v317_validation.py` 嘅 `rerun_pipeline(file_id)`：

```python
def rerun_pipeline(file_id):
    # 1. Delete existing segments + translations (POST /api/files/<id>/transcribe will overwrite anyway)
    # 2. POST /api/files/<id>/transcribe → 等 transcription_complete event 或 polling status
    # 3. Auto-translate 跟住 trigger (existing behavior)；poll translation_status until done
    # 4. Capture asr_seconds + translation_seconds from registry / pipeline_timing event
```

**Caveat**：ASR overwrite 不可逆 — 必須先確認 C2 baseline snapshot 完整。

### C5：Post snapshot

`capture_snapshot(file_id)` 再叫一次，dump 落：
- `docs/superpowers/validation/v3.17-post-{file_id_short}.json`

### C6：Compute diff metrics（Tier 1+2+3 全部）

Helper script 新增 functions：

#### Tier 1 — Core

```python
def latency_delta(baseline, post) -> dict:
    """ASR seconds, MT seconds, sec-per-min ratios"""

def segmentation_delta(baseline, post) -> dict:
    """count, avg/min/max duration, avg word count"""

def asr_text_delta(baseline, post) -> dict:
    """Pair segments by start_time (±0.5s); count identical/changed/new/dropped; top 10 changes"""

def mt_text_delta(baseline, post) -> dict:
    """Pair translations by index; count identical/changed; top 10 changes"""

def glossary_scan_delta(baseline, post) -> dict:
    """strict_violations + loose_violations count; top 5 examples per category"""
```

#### Tier 2 — Broadcast Quality

```python
def subtitle_length_distribution(translations) -> dict:
    """ZH char-count histogram: 0-10, 11-15, 16-20, 21-28, 29-40, >40"""

def reading_speed_cps(translations) -> dict:
    """chars per (end-start) seconds per segment; flag <8 (slow) + >20 (fast); broadcast band 12-17"""

def language_consistency(segments, translations) -> dict:
    """
    Returns:
      en_with_cjk_count: EN segments containing chars in [一-鿿]
      zh_with_latin_count: ZH segments containing [a-zA-Z]{3,} not in brand whitelist
      simplified_leak_count: ZH segments where OpenCC s2hk conversion produces different output (= contains simplified chars)
    """

def repetition_detect(translations, min_ratio=0.7) -> list:
    """Adjacent translation pairs where ZH text overlap >= min_ratio (cascade signal). Return list of (i, j, overlap_pct, zh_text)."""
```

#### Tier 3 — Diagnostic

```python
def segment_timing_health(segments) -> dict:
    """Count: <0.3s, >7s, gap distribution (silences between segments)"""

def flag_rates(translations) -> dict:
    """Counts of [LONG], [NEEDS REVIEW] flags; hallucination % (>40 chars heuristic)"""

def batch_boundary_check(translations, batch_size) -> dict:
    """If batch_size > 1, check indices [batch_size, 2*batch_size, ...]: report repetition + context shift across boundary"""

def word_level_alignment(segments) -> dict:
    """% segments with words[] populated; avg word count per segment"""

def approval_state(translations_baseline, translations_post) -> dict:
    """Baseline approved/pending counts vs post (post is all pending - flag clearly as expected reset)"""
```

### C7：Render markdown report

`docs/superpowers/validation/v3.17-diff-report.md`，structure：

```markdown
# v3.17 Validation Diff Report

## Executive Summary
- Verdict: ✅ / ⚠️ / ❌
- Date, branch, videos tested
- Key findings (3 bullets)

## Methodology
- ASR model, MT engine, glossaries

## Video 1: <name>
### Identity + Latency [Tier 1]
### Segmentation [Tier 1]
### ASR text delta [Tier 1]
### MT text delta [Tier 1]
### Glossary scan [Tier 1]
### Subtitle length distribution [Tier 2]
### Reading speed CPS [Tier 2]
### Language consistency [Tier 2]
### Repetition detection [Tier 2]
### Segment timing health [Tier 3 - collapsible / appendix]
### Flag rates [Tier 3]
### Batch boundary check [Tier 3]
### Word-level alignment [Tier 3]
### Approval state [Tier 3]

## Video 2: <name>
[same structure]

## Cross-video aggregate
- Combined latency delta
- Combined text change ratio
- Combined glossary violation delta

## Conclusion
- Recommendation: merge / rollback / further investigation
- Specific concerns + suggested follow-up
```

Report 文件 commit 入 repo（作為 PR evidence）。

### C8：User review gate

Report 寫好之後，**STOP** 等用戶睇 report，決定：

- ✅ **Accept**：push branch + 開 PR
- ⚠️ **Accept with notes**：push + PR + 開 follow-up issue 改 noted concerns
- ❌ **Rollback**：reset Part B 嘅實質改動，留 Part A，重新 design

呢個係 v3.17 merge gate。SDD pipeline 唔越過呢個 gate 自動 merge。

## Risk audit

| Risk | Mitigation |
|---|---|
| Migration script 改錯 profile，將自定義 model 改返做 large-v3，但用戶其實想用 small | Backed by user explicit confirm（Q2 答案）+ baseline snapshot 可 restore + git history 可 revert |
| 既有 backend test 引用 qwen3/flg 散落多個 file | Part B5 嘅 grep audit 全 covers |
| C5 re-run ASR 中途 fail → 文件 segments 被部分 overwrite | Per-video transactional：完整 baseline snapshot 喺 C2 dump；fail 可 restore via direct registry edit |
| Re-run 期間用戶手動 cancel job | 加 retry mechanism + 明確 log；最壞情況回 baseline 重試 |
| 2 條 video 都係 large-v3 baseline → C6 diff 顯示 zero delta | 正面結果，confirm v3.17 zero impact，照常 merge |

## Scope guardrails

**唔做**：
- 加新 ASR engine（之後 v3.x 再諗）
- 改 MT engine factory 或 prompt template
- 加 MT `prompt_overrides` UI（Q3 衍生，留 v3.x 再做）
- 加 ASR `initial_prompt` UI textbox（用戶仍可手 edit Profile JSON）
- Backwards-compat shim（user 已 confirm 全 force large-v3）

**Part C 唔做**：
- Re-train model（純 inference comparison）
- A/B test 唔同 prompt template（fix 住現有）
- 1 條以上 sample 嘅 statistical significance test（單純 before/after 對比）

## Files touched 預估

| File | Part | Action |
|---|---|---|
| [frontend/index.html](frontend/index.html) | A | Modify |
| [frontend/tests/test_profile_ui_guidance.spec.js](frontend/tests/test_profile_ui_guidance.spec.js) | A | Modify |
| [backend/asr/whisper_engine.py](backend/asr/whisper_engine.py) | B1 | Modify |
| [backend/asr/mlx_whisper_engine.py](backend/asr/mlx_whisper_engine.py) | B1 | Modify |
| [backend/asr/__init__.py](backend/asr/__init__.py) | B4 | Modify |
| [backend/asr/qwen3_engine.py](backend/asr/qwen3_engine.py) | B3 | Delete |
| [backend/asr/flg_engine.py](backend/asr/flg_engine.py) | B3 | Delete |
| `backend/scripts/migrate_v317_asr_models.py` | B2 | Create |
| `backend/scripts/v317_validation.py` | C | Create |
| `backend/config/profiles/*.json` | B2 | Migrate（每個內部 `asr.model_size` field）|
| [backend/tests/test_asr.py](backend/tests/test_asr.py) + 相關 | B5 | Modify / delete cases |
| [CLAUDE.md](CLAUDE.md) | B6 | Modify |
| `docs/superpowers/validation/v3.17-baseline-{file_id}.json` × 2 | C2 | Create |
| `docs/superpowers/validation/v3.17-post-{file_id}.json` × 2 | C5 | Create |
| `docs/superpowers/validation/v3.17-diff-report.md` | C7 | Create |

## Testing strategy

- **Part A**：4 個 Playwright tests（2 reframe + 2 keep）。Test must pass before commit
- **Part B**：existing backend pytest suite must pass after B1+B4+B5；migration script idempotency tested via manual run twice
- **Part C**：validation script self-tests（dummy snapshot pair → expected diff output），plus end-to-end smoke run on 1 video before doing 2
