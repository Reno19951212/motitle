# v3.18 Stage 2 — MT Prompt Override Design

**Status**: Draft → User review
**Date**: 2026-05-15
**Branch target**: `chore/v3.18-stage2-prompt-override` (new, off `main`)
**Predecessor**: v3.17 (`chore/v3.15-cleanup-2026-05-13`, merged 2026-05-15)
**Research basis**: [docs/superpowers/validation/mt-quality/mt-quality-research-2026-05-15.md](../validation/mt-quality/mt-quality-research-2026-05-15.md)

---

## Goal

Reduce MT formulaic phrase over-use (research found "傷病纏身" 15× / "就此而言" 14× / "儘管" 13× across 166 Video 1 segments — caused by hardcoded few-shot examples in the 3 system prompts) while opening a frontend override path so users can customize prompts per-file without touching code.

**Out of scope** for Stage 2 (explicitly deferred):
- (b) Domain context anchor (Stage 3)
- (c) Forbidden phrases list (Stage 3)
- User-self-service template publishing (Stage 3)
- Glossary stacking (Stage 4)
- Per-file retry strategy (Stage 4)
- ASR-side fragment merge / segment structural changes (Stage 1 — explicitly skipped per user direction)

**Three deliverables bundled** (A + B + C from brainstorming):
- **A** — Rewrite the 3 hardcoded default prompts to drop specific EN→ZH mappings & idiom lists (replace with anti-pattern guidance).
- **B** — Per-file prompt override via UI textarea, layered above existing profile-level override.
- **C** — Backend-managed prompt template library (3 starters: broadcast / sports / literal) used as textarea seed source.

---

## Architecture

### Runtime fallthrough (3 layers)

```
Per-file override (new schema: files registry, prompt_overrides field)
  ↓ if null / key missing
Profile-level override (existing: profile.translation.prompt_overrides, already wired in v3.x)
  ↓ if null / key missing
Hardcoded default constant (Stage 2 削減版, lives in source files)
```

### Template (UI seed, not a runtime layer)

```
Backend predefined templates (config/prompt_templates/*.json)
  → GET /api/prompt_templates
    → Frontend dropdown
      → User picks template + clicks "套用模板到 textarea"
        → Frontend writes template content into the 4 textareas
          → User clicks "重新翻譯此檔案"
            → PATCH /api/files/<id> with prompt_overrides
              → MT job runs with file-level override
```

Templates are **author-time seed**, not runtime fallback. Resolver does NOT consult templates.

### 4 prompt keys (unchanged from existing infrastructure)

Already validated by `profiles.py:433-452` and tested by `tests/test_prompt_overrides.py`:

| Key | Used by | Default constant location |
|---|---|---|
| `alignment_anchor_system` | `alignment_pipeline.build_anchor_prompt()` preamble (when `alignment_mode="llm-markers"` for multi-segment merged sentences) | `alignment_pipeline.py:91-99` |
| `single_segment_system` | `ollama_engine._translate_single()` (when `batch_size=1`) | `ollama_engine.py:173-194` |
| `pass2_enrich_system` | `ollama_engine._enrich_batch()` (when `translation_passes=2`) | `ollama_engine.py:197-220` |
| `pass1_system` | `ollama_engine._translate_batch()` (default batched path, `batch_size>1`) | `ollama_engine.py` SYSTEM_PROMPT_FORMAL / SYSTEM_PROMPT_CANTONESE |

---

## Backend changes

### A. Default constant rewrites

#### Prompt #1 — `alignment_anchor_system` (alignment_pipeline.py)

**Before** (10 lines, 4 hardcoded mappings + 3 connector examples, ~250 tokens):
```
你是香港電視廣播嘅資深字幕翻譯員。將下面英文句子翻譯成**完整、豐富、文學化**嘅繁體中文書面語。

【翻譯要求】
1. 保留原文所有修飾語、副詞、強調語（如 persistent → 傷病纏身、really → 真正、radical → 大刀闊斧、light → 嚴重告急）
2. 使用完整主謂結構；善用四字詞與結構連接詞（在…方面、就此而言、儘管…但）
3. 專有名詞依照指定譯名表；人名首次出現用完整譯名
4. **不要為咗簡短而省略修飾語** — broadcast 允許 2 行顯示，總長約 22–35 字
```

**After** (4 rules, 0 hardcoded mappings, ~120 tokens):
```
你係香港電視廣播嘅字幕翻譯員。將英文句翻譯為繁體中文書面語，須完整、生動。

【規則】
1. 保留原文所有修飾語、副詞、限定詞，唔好為簡短而省略
2. 用完整主謂結構；專有名詞依指定譯名表，人名首次用完整譯名
3. 廣播書面語風格，2 行顯示空間，總長約 22–35 字
4. 避免過度套用相同四字詞或固定連接詞模板，每段按語境選詞
```

The marker insertion section (lines 102-110) is unchanged.

#### Prompt #2 — `SINGLE_SEGMENT_SYSTEM_PROMPT` (ollama_engine.py)

**Before** (22 lines, 6 demonstrations using Tchouameni / Como specific names, ~450 tokens):
- 5 rules
- 6 EN/ZH demonstration pairs

**After** (~10 lines, 2 generic demonstrations, ~200 tokens):
```
你係廣播電視中文字幕翻譯員，將英文片段翻譯做繁體中文書面語。

【規則】
1. 中文字數約等於英文字符數 × 0.4–0.7，目標 6–25 字
2. 譯文 ONLY 反映畀你嘅英文原文，禁止加任何外部資訊
3. 即使原文係不完整片段，譯文亦要係可朗讀嘅完整子句
4. 直接輸出譯文一行，唔加引號、編號、解釋、英文原文
5. 廣播書面語風格，避免重複套用相同表達

【示範】（用於確認格式，非詞彙映射）
英文：completed more per game since the start
譯文：自賽季初起每場完成更多。

英文：On paper, the player within the squad best
譯文：紙面上，陣容中最佳人選為
```

Kept 2 examples (rather than 0) because LLM still needs **output format anchoring** (one-line, no prefixes, no English echo). Picked examples that are content-neutral (no proper names that would lock vocabulary).

#### Prompt #3 — `ENRICH_SYSTEM_PROMPT` (ollama_engine.py)

**Before** (22 lines, 2 改寫示範 + 5-word idiom list 「傷病纏身/大刀闊斧/嚴重告急/巔峰年齡/飽受困擾」, ~500 tokens).

**After** (~14 lines, 1 example with explicit anti-mimic instruction, ~280 tokens):
```
你係香港電視廣播嘅資深字幕編輯。收到初譯後改寫增強，令譯稿達到專業廣播質素。

【核心心態】
初譯偏簡短。目標每行約 22–30 字，少於 20 字需加強。

【規則】
1. 保留原文所有形容詞、副詞、限定詞，譯出但毋須生硬套詞
2. 人名首次完整譯名（如 David Alaba → 大衛·阿拉巴）
3. 完整主謂結構，按語境加結構連接詞
4. 採用書面廣播筆觸：「表示」「指出」「透露」優於「稱」「說」
5. 事實層面忠於英文原文，不得新增信息
6. 短於 18 字嘅輸出需重寫更長版本
7. 僅輸出編號譯文（1. 2. ...），繁體中文
8. 避免每段套用相同四字詞或固定模板，按語境選詞

【範例】
英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.
初譯（13字）：阿拉巴盧迪加屢傷，皇馬薄弱。
改寫方向：補完整人名 + 持續性修飾 + 後防具體影響。選詞按語境，毋須照搬下方範例。
範例譯（37字）：後防方面，大衛·阿拉巴與安東尼奧·呂迪格嘅傷病持續，皇馬後防壓力加劇。
```

Kept 1 example (still need rewrite-direction reference) but added explicit "毋須照搬下方範例" warning.

Note: `pass1_system` (SYSTEM_PROMPT_FORMAL / SYSTEM_PROMPT_CANTONESE) is NOT rewritten in Stage 2 — those are used only in the batched path (`batch_size>1`), which the active production profile does NOT use. Validation re-run will confirm whether they need a separate削減 in Stage 2b.

### B. File-level override schema

**File registry change** (`backend/app.py`, `_register_file` + registry write/read):

```python
# file registry entry adds (optional, default null):
{
    ...,
    "prompt_overrides": null | {
        "pass1_system":            null | "string",
        "single_segment_system":   null | "string",
        "pass2_enrich_system":     null | "string",
        "alignment_anchor_system": null | "string",
    }
}
```

Backward-compat: entries missing `prompt_overrides` field treated as `null`.

**PATCH `/api/files/<id>`** accepts new field:
```
PATCH /api/files/<id>
Body: {"prompt_overrides": {...} | null}
Response: 200 OK with updated file dict
```

Validation reuses logic extracted from `profiles.py:433-452` into shared helper `backend/translation/prompt_override_validator.py`:
- Must be dict or null
- Only the 4 known keys allowed
- Each value: null or non-empty string
- Whitespace-only string rejected with clear error

**Resolver** `_resolve_prompt_override(key, file_entry, profile)`:
```python
def _resolve_prompt_override(key: str, file_entry: dict, profile: dict) -> str | None:
    file_po = (file_entry or {}).get("prompt_overrides") or {}
    if key in file_po and file_po[key]:
        return file_po[key]
    profile_po = (profile or {}).get("translation", {}).get("prompt_overrides") or {}
    if key in profile_po and profile_po[key]:
        return profile_po[key]
    return None  # caller falls back to hardcoded constant
```

**`_auto_translate` rewrite** (`app.py:2926-2937`):
- Pass file entry to translate path
- Replace direct `(translation_config.get("prompt_overrides") or {}).get("alignment_anchor_system")` with `_resolve_prompt_override("alignment_anchor_system", file_entry, profile)`
- For `engine.translate()` path (batched + single-mode + enrich), add `prompt_overrides=` kwarg holding the resolved 4-key dict; OllamaEngine reads from it instead of `self._config`

### C. Template library

**New dir** `backend/config/prompt_templates/`:
- `broadcast.json` — Stage 2 削減版 default content (same as #1/#2/#3 削減版 above). Exact byte-equivalence to the new default constants is required (verified by test).
- `sports.json` — sports commentary register. Final text **drafted during implementation** per these constraints: keeps the 4-rule broadcast scaffold from broadcast.json, but adds sport-domain register cues (e.g. "形容比賽動作要傳神但唔煽情"), strengthens athlete-name first-translation rule, keeps 22-35 字 target. NO hardcoded EN→ZH mapping examples.
- `literal.json` — minimal-fluff register. Final text **drafted during implementation** per these constraints: drops the 22-35 字 length target (allow 8-25 字), drops broadcast-筆觸 rule (#4 in pass2_enrich version), keeps fact-fidelity (#5) and anti-formulaic (#8) rules. Suitable for documentary subtitles where economy matters more than rhetorical register.

JSON shape:
```json
{
  "id": "broadcast",
  "label": "新聞廣播",
  "description": "正式廣播風格，重視結構完整",
  "overrides": {
    "alignment_anchor_system": "...",
    "single_segment_system": "...",
    "pass2_enrich_system": "...",
    "pass1_system": "..."
  }
}
```

**New route** `GET /api/prompt_templates`:
```json
{
  "templates": [
    {"id": "broadcast", "label": "新聞廣播", "description": "...", "overrides": {...}},
    {"id": "sports", "label": "體育評論", "description": "...", "overrides": {...}},
    {"id": "literal", "label": "字面直譯", "description": "...", "overrides": {...}}
  ]
}
```

No auth gate on GET (templates are non-sensitive). Admin-only POST/PATCH/DELETE deferred to Stage 3 (when self-service template publishing lands).

### Engine wiring

`OllamaTranslationEngine`:
- `translate()` accepts new optional kwarg `prompt_overrides: dict | None = None`
- `_translate_batch`, `_translate_single`, `_enrich_batch` read from `prompt_overrides` if not None, else fall back to `self._config.get("prompt_overrides")`, else fall back to default constant
- This 2-stage internal fallback is needed because `_auto_translate` passes file-resolved overrides, but legacy direct callers may not pass `prompt_overrides=` kwarg

`translate_with_alignment` (already accepts `custom_system_prompt=` for alignment_anchor) — Stage 2 keeps the signature, just adds resolver upstream.

---

## Frontend changes

### Proofread page sidebar — new panel `自訂 Prompt`

Location: after Glossary panel, after Subtitle Settings panel (existing).

```
┌─ 自訂 Prompt（呢個檔案專用）────────────────────┐
│                                                  │
│ 模板：[新聞廣播 ▼]  [套用模板到 textarea]        │
│       (新聞廣播 / 體育評論 / 字面直譯 /          │
│        Profile 預設 / 系統預設)                  │
│                                                  │
│ ▾ 對齊 anchor (alignment_anchor_system)         │
│   ┌────────────────────────────────────────┐   │
│   │ <textarea 6 行>                        │   │
│   └────────────────────────────────────────┘   │
│                                                  │
│ ▾ 單段翻譯 (single_segment_system)              │
│   ┌────────────────────────────────────────┐   │
│   │ <textarea 6 行>                        │   │
│   └────────────────────────────────────────┘   │
│                                                  │
│ ▾ Pass 2 加強 (pass2_enrich_system)             │
│   ┌────────────────────────────────────────┐   │
│   │ <textarea 6 行>                        │   │
│   └────────────────────────────────────────┘   │
│                                                  │
│ ▸ 批次翻譯 (pass1_system) [展開]                │
│                                                  │
│ [清空]  [重新翻譯此檔案]                          │
└──────────────────────────────────────────────────┘
```

Default expansion: alignment / single / enrich (active profile uses all 3). Pass1 folded.

### JS flow

1. **Page load**:
   - `GET /api/prompt_templates` → cache in state
   - `GET /api/files/<id>` → read `prompt_overrides` field → fill textareas (or leave blank if null)
   - Populate template dropdown with predefined entries + 2 special: "Profile 預設" (=loads profile-level override), "系統預設" (=clears all textareas, falls back to hardcoded constants)

2. **Template select + apply**:
   - User picks template from dropdown
   - Clicks "套用模板到 textarea" → JS writes template's 4 prompt strings into the 4 textareas
   - **No auto-PATCH** — user can edit textareas after, must click "重新翻譯此檔案" to commit

3. **Commit changes**:
   - User clicks "重新翻譯此檔案"
   - Build `prompt_overrides` dict from textareas (empty textarea → null for that key)
   - `PATCH /api/files/<id>` with `prompt_overrides`
   - Trigger MT job: `POST /api/translate` (re-translate flow, existing endpoint)

4. **Clear**:
   - User clicks "清空" → all textareas cleared → PATCH with `prompt_overrides: null`
   - Effect: file falls through to profile / default

### File card on dashboard

Add small indicator chip when file has non-null `prompt_overrides`:
```
[檔案名] [📝 自訂 Prompt]
```

Click chip → open Proofread page directly to the Prompt panel.

---

## Validation strategy

### Unit tests (~10 new)

1. `_resolve_prompt_override` — file > profile > None fallthrough (3 layers × 4 keys = 12 case)
2. `validate_prompt_override` shared helper — null / valid / unknown key / whitespace / non-dict
3. Template JSON loader — all 3 templates load with all 4 keys
4. `OllamaTranslationEngine` — new `prompt_overrides` kwarg overrides `self._config`, and falls back when kwarg is None

### Integration tests (~5 new)

1. `PATCH /api/files/<id>` with valid `prompt_overrides` → 200 + `GET /api/files/<id>` returns same dict
2. `PATCH /api/files/<id>` with invalid override (non-dict / unknown key / whitespace) → 400 + clear error
3. `GET /api/prompt_templates` returns 3 entries each with 4 keys
4. `_auto_translate` resolver — file override beats profile, profile beats default, all null → default
5. End-to-end: PATCH file with `prompt_overrides` → trigger MT → mock OllamaEngine captures system_prompt → assert override content was used

### Playwright (~2 new)

1. **Template apply + re-translate**: Open Proofread page → select template → click apply → textareas populated → click re-translate → verify network shows PATCH + POST /api/translate
2. **Clear override**: Open Proofread with file having override → click 清空 → PATCH null → textareas empty

### Validation re-run

Run **v317_validation.py** Stage 2 vs v3.17 post-state:
- Subject: Video 1 (166 segments, baseline JSON already in repo)
- Method: re-run MT after merging Stage 2 to dev branch (no per-file override, just削減 default)
- Metrics to watch:
  - **Hallucination spot-check**: 5 known bad segments from research report (#36 leader, #41 Solihull, #59 Como, #163 grinds out)
  - **Formulaic frequency**: 「傷病纏身」 count (was 15× → target ≤3×), 「就此而言」 (was 14× → target ≤3×), 「儘管」 (was 13× → target ≤3×), 「真正」 (was 24× → target ≤8×)
  - **ZH/EN ratio distribution**: confirm削減 didn't shrink output (target 0.4-0.7 unchanged)
  - **Empty rate**: should stay ≤6% (was 5.4%)

Acceptance threshold: formulaic frequencies drop by ≥60% AND empty rate stays ≤6% AND no new hallucination class introduced.

Report to `docs/superpowers/validation/v3.18-stage2-diff-report.md`.

---

## Data flow summary

```
User (Proofread page) 
   │
   │ types in textarea + click 重新翻譯
   ▼
PATCH /api/files/<id> {prompt_overrides: {...}}
   │
   │ stored in file registry
   ▼
POST /api/translate (existing endpoint)
   │
   ▼
_auto_translate(file_id)
   │
   │ loads file_entry, profile
   │
   │ for each key in [alignment_anchor, single_segment, pass2_enrich, pass1]:
   │    _resolve_prompt_override(key, file_entry, profile)
   │
   ▼
translate_with_alignment / engine.translate(prompt_overrides=resolved_dict)
   │
   ▼
_call_ollama(system=resolved_or_default, user=prompt)
```

---

## File touch list

### Modified
- `backend/translation/alignment_pipeline.py` — A: rewrite `build_anchor_prompt` default preamble (lines 91-99)
- `backend/translation/ollama_engine.py` — A: rewrite `SINGLE_SEGMENT_SYSTEM_PROMPT` + `ENRICH_SYSTEM_PROMPT`; B: add `prompt_overrides` kwarg to `translate()` + thread to `_translate_batch` / `_translate_single` / `_enrich_batch`
- `backend/app.py` — B: file registry schema field, PATCH route accepts `prompt_overrides`, resolver, `_auto_translate` uses resolver; C: GET /api/prompt_templates route
- `frontend/proofread.html` — new sidebar panel + JS state for prompt_overrides + template dropdown + textareas + actions
- `frontend/index.html` — file card "📝 自訂 Prompt" indicator chip when override present
- `CLAUDE.md` — v3.18 entry summarizing Stage 2 changes

### New
- `backend/config/prompt_templates/broadcast.json`
- `backend/config/prompt_templates/sports.json`
- `backend/config/prompt_templates/literal.json`
- `backend/translation/prompt_override_validator.py` — shared validation (extract from `profiles.py:433-452`)
- `backend/tests/test_prompt_override_resolver.py` — fallthrough tests
- `backend/tests/test_prompt_template_api.py` — GET endpoint tests
- `backend/tests/test_file_prompt_overrides.py` — PATCH + integration tests
- `frontend/tests/test_prompt_panel.spec.js` — Playwright scenarios
- `docs/superpowers/plans/2026-05-15-stage2-prompt-override-plan.md` — implementation plan (via writing-plans skill after this spec approved)
- `docs/superpowers/validation/v3.18-stage2-diff-report.md` — post-merge validation report

### Deleted
None.

### Schema-only changes
- `backend/profiles.py:433-452` — refactor `prompt_overrides` validation to import from new shared module (no behavior change)
- File registry JSON — backward-compat optional field (no migration needed; null on read for old entries)

---

## Risks / known constraints

1. **`pass1_system` not rewritten in Stage 2** — only matters if a user activates `batch_size>1` (Profile's batched path). Active production profile uses `batch_size=1` (single-segment mode), so this is dormant. If validation re-run shows batched profiles regressing, do quick follow-up Stage 2b.

2. **削減 may slightly reduce output richness** — by dropping the iconic vocabulary examples (傷病纏身 etc.), the LLM may default to plainer choices. This is intentional (the iconic over-use was the original problem), but watch for "too plain" complaints. Anti-pattern rule #3 / #8 in削減版 explicitly says "按語境選詞" which still permits richness when situationally appropriate.

3. **Per-file override can reintroduce formulaic** — if a user writes "persistent → 傷病纏身" in their own textarea, Stage 2 A's reduction is locally bypassed. Mitigation: inline UI hint above each textarea: "⚠️ 避免具體 EN→ZH 映射範例，會令 LLM 過度套用該詞。建議用 anti-pattern 表達。" — documented in spec but actual hint text finalized in implementation.

4. **Template dropdown does NOT auto-PATCH** — explicit "套用 + 重新翻譯" two-click flow to prevent accidental override commits. Tradeoff: slightly more friction, but matches Profile Save modal UX pattern from v3.16.

5. **Validation needs Backend running on a specific file** — V317_validation.py harness expects backend at localhost:5001 + a file_id baseline. Stage 2 reuses Video 1's baseline JSON (166 segments) for diff base. No new validation infrastructure needed.

---

## Out-of-scope explicit list (for reviewer clarity)

These are NOT in Stage 2 — do NOT add during implementation:

- **Domain context anchor**: per-file textarea for video subject (1-2 sentences). Stage 3.
- **Forbidden phrases list**: user-defined vocabulary blacklist injected as negative constraint. Stage 3.
- **Template self-service**: user can save personal templates to backend with admin review queue. Stage 3.
- **Profile UI integration**: Profile Save modal also exposes prompt textareas. Stage 4 (currently profile-level edit via API + JSON only).
- **Glossary stacking**: support multiple active glossaries. Stage 4.
- **Per-file retry strategy**: empty/over-cap retry policy configuration. Stage 4.
- **A/B prompt comparison**: run same file with 2 prompts side-by-side. Stage 5.
- **Prompt version history / rollback**: track changes to a profile's prompt_overrides over time. Stage 5.

---

## Acceptance criteria

Stage 2 is "done" when:

- ✅ 3 default constants rewritten per spec section "A" (verified by reading the 3 source files)
- ✅ File registry has `prompt_overrides` field; PATCH accepts it; resolver works (verified by unit tests passing)
- ✅ 3 template JSON files exist; GET endpoint returns all 3 (verified by integration test)
- ✅ Proofread page has working Prompt panel (verified by Playwright test)
- ✅ Validation re-run shows formulaic frequencies dropped ≥60% on Video 1 (verified by diff report)
- ✅ No regression in empty rate (≤6%) or hallucination class (manual spot-check 5 known segments)
- ✅ CLAUDE.md v3.18 entry written
- ✅ All existing tests still pass (~770 backend + Playwright suite)
