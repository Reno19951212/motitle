# Multilingual Glossary Refactor — Design Spec

**Date:** 2026-05-12
**Branch:** `chore/roadmap-2026-may`
**Status:** Design — awaiting user review before plan + implementation
**Trigger:** User reported validation error `"en must contain at least one letter"` when adding a glossary entry; on follow-up explained the actual need is multilingual glossary support (EN↔EN, ZH↔ZH, JA→ZH, etc.) — current `{en, zh}` schema is hardcoded to English-source, Chinese-target.

---

## 1. Problem Statement

The current glossary subsystem is built around a fixed English-source / Chinese-target model:

- Entry schema is `{en, zh, zh_aliases?, id}`. `en` validation requires `[A-Za-z]`, `zh` requires CJK characters. This rejects legitimate use cases (Japanese source terms, pure-number proper nouns, etc.).
- LLM `glossary-apply` prompt hardcodes `"English subtitle"` / `"Corrected Chinese subtitle"` instructions.
- All 12+ UI labels say "EN" / "ZH" / "原文 (EN)" / "譯文 (ZH)".
- CSV import/export uses `en,zh` columns only.
- File translation registry stores `applied_terms: [{term_en, term_zh}]` and `baseline_zh` — these names couple to the EN→ZH assumption.

User needs glossaries that work for any of these directions: EN→ZH, EN→EN (normalization), ZH→ZH (style guide), JA→ZH (Japanese broadcast). Auto-translate stays EN→ZH for now; multilingual auto-translate is a separate phase.

## 2. Decisions Locked (User-approved)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Per-glossary language tags** (`source_lang` + `target_lang` at glossary level, not per-entry) | User-confirmed; matches actual use cases which are mono-directional per glossary |
| D2 | **Scope limited to manual scan/apply + find·replace + CSV** | Auto-translate stays EN→ZH; multilingual translation pipeline is a separate future spec |
| D3 | **Clean cutover** — no backward-compat alias reader; old glossary files deleted on deploy | User accepts loss of 23 existing entries; will manually export-CSV/edit-header/reimport for the 20 worth keeping |
| D4 | **No source aliases** (only `target_aliases`, same as current `zh_aliases` shape) | YAGNI |
| D5 | **Supported languages (hardcoded whitelist of 8)**: `en`, `zh`, `ja`, `ko`, `es`, `fr`, `de`, `th` | Initial set; add more by editing one const |
| D6 | **No per-language script validation** (drop `letter`/`CJK` rules); only non-empty + reject self-translation | Simpler; current rules cause the user's reported bug |
| D7 | **Two-stage scan UI for CJK/TH source languages** — strict (same-script boundary) + loose (substring with same-script wrap) | User explicitly chose stricter scan over false-positive permissive |
| D8 | **Glossary-apply LLM model**: hardcoded default `qwen3.5-35b-a3b` with optional `glossary_apply_model` profile override | Quality-critical, low-call-volume path; auto-translate remains unaffected |
| D9 | **Apply prompt language**: English (system prompt + user prompt template) | Better model recognition of language metadata labels than Chinese |
| D10 | **CSV format**: 3 columns `source, target, target_aliases`. No `*_lang` columns. Old `en,zh` CSV rejected with explicit error | Glossary metadata carries lang info; cutover principle |

## 3. Data Schema

### 3.1 Glossary (top-level file)

```json
{
  "id": "broadcast-news",
  "name": "Broadcast News",
  "description": "HK news broadcasting terms",
  "source_lang": "en",
  "target_lang": "zh",
  "entries": [/* Entry[] */],
  "created_at": 1712534400,
  "updated_at": 1712534400,
  "user_id": null
}
```

`source_lang`, `target_lang`: required strings, must be in language whitelist (D5). Equal values are allowed (EN→EN, ZH→ZH normalization) but combined with `source == target` per-entry, the entry is rejected.

### 3.2 Entry

```json
{
  "id": "uuid",
  "source": "Vinicius",
  "target": "雲尼素斯",
  "target_aliases": ["維尼修斯", "维尼修斯"]
}
```

- `source`, `target`: required non-empty strings (after `.strip()`).
- `target_aliases`: optional list of strings. Empty list and field-absent are equivalent.
- No `source_aliases` (D4).

### 3.3 File translation registry (downstream impact)

Existing field renames on each `_file_registry[file_id].translations[i]`:
- `baseline_zh` → `baseline_target`
- `applied_terms[*].term_en` → `applied_terms[*].term_source`
- `applied_terms[*].term_zh` → `applied_terms[*].term_target`

Existing files in registry will have their `applied_terms` and `baseline_zh` rendered moot when the schema changes (no reader migration per D3). Lazy-revert simply finds no matches and continues. `baseline_zh` becomes orphan data — harmless but takes disk space until file is deleted.

### 3.4 Language whitelist (one source of truth)

Hardcoded constant in `backend/glossary.py`:

```python
SUPPORTED_LANGS = {
    "en": ("English", "英文"),
    "zh": ("Chinese", "中文"),
    "ja": ("Japanese", "日本語"),
    "ko": ("Korean", "한국어"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "de": ("German", "Deutsch"),
    "th": ("Thai", "ภาษาไทย"),
}
```

Frontend reads via `GET /api/glossaries/languages` (new endpoint) so dropdowns stay in sync.

## 4. Validation Rules

### 4.1 Glossary-level
- `source_lang`: required, value ∈ `SUPPORTED_LANGS`. 400 if missing or unknown.
- `target_lang`: same.

### 4.2 Entry-level
- `source`: required, `.strip()` length > 0. 400 with msg `"source is required"` / `"source must be a non-empty string"`.
- `target`: same.
- **Self-translation reject**: if `source_lang == target_lang` AND `source.strip()` equals `target.strip()` OR equals any item in `target_aliases` (post-strip), 400 with msg `"source and target are identical — entry is a no-op"`. (Different-language identical strings allowed: `"USA" → "USA"` with source=en, target=ja is permitted — that pair is meaningful as a cross-language mapping.)
- `target_aliases`: optional list of non-empty strings (post-strip). Duplicates against `target` deduped silently. When `source_lang == target_lang`, no alias may equal `source` (covered by the rule above).

### 4.3 Dropped rules (vs current)
- ❌ `en must contain at least one letter`
- ❌ `zh must contain at least one CJK char`
- ❌ Per-language script heuristic (would force JA source to contain kana, etc. — false-negative-heavy)

### 4.4 Preserved rules
- Quote normalization (strip one layer of paired quotes: `「」 『』 《》 〈〉 "" '' "" ''` from `source`, `target`, each `target_aliases` item).
- Smart case sensitivity in scan (uppercase letters in term → case-sensitive match; all-lowercase → case-insensitive). No-op for CJK/JA/KO/TH (no case concept).

## 5. Scan Logic (Two-Stage for Boundary-less Scripts)

### 5.1 Per-script boundary character class

| `source_lang` | Boundary regex range |
|---|---|
| `en`, `es`, `fr`, `de` | `[A-Za-z0-9]` (current rule) |
| `zh` | `[一-鿿㐀-䶿]` (CJK Unified + Ext-A) |
| `ja` | `[぀-ゟ゠-ヿ一-鿿]` (Hiragana + Katakana + Kanji) |
| `ko` | `[가-힯]` (Hangul Syllables) |
| `th` | `[฀-๿]` (Thai) |

### 5.2 Strict match (all source languages)

Word-boundary regex with the script-specific character class:

```
(?<!<boundary_chars>) <escaped_term> (?!<boundary_chars>)
```

This is the existing rule generalized per-script.

### 5.3 Loose match (CJK / JA / KO / TH only)

Plain substring match (`term in segment_text`). Returns only matches that strict regex did NOT already cover, i.e., loose = (substring_hits − strict_hits).

For Latin scripts (en/es/fr/de) strict is already permissive enough; loose section is suppressed.

### 5.4 Apply-modal output shape

`GET /api/files/<file_id>/glossary-scan` response evolves from:

```json
{ "violations": [...], "matches": [...], "scanned_count": N, "violation_count": M, "match_count": K, "reverted_count": R }
```

to:

```json
{
  "strict_violations": [...],
  "loose_violations": [...],
  "matches": [...],
  "scanned_count": N,
  "strict_violation_count": ...,
  "loose_violation_count": ...,
  "match_count": ...,
  "reverted_count": ...,
  "glossary_source_lang": "ja",
  "glossary_target_lang": "zh"
}
```

Loose stays empty array for Latin source languages. Frontend renders sections conditionally.

## 6. LLM Glossary-Apply Path

### 6.1 Prompt template (parameterized on glossary lang pair)

**User prompt** (per-term call):

```
{Source_EN_name} subtitle: {source_text}
Current {Target_EN_name} subtitle: {current_target}
Correction: "{term_source}" must be translated as "{term_target}"

Corrected {Target_EN_name} subtitle:
```

Where `{Source_EN_name}` comes from `SUPPORTED_LANGS[glossary.source_lang][0]`. Example for JA→ZH glossary:

```
Japanese subtitle: 朝のニュース
Current Chinese subtitle: 朝晨新聞
Correction: "ニュース" must be translated as "新聞"

Corrected Chinese subtitle:
```

### 6.2 System prompt template

```
You are a {Target_EN_name} subtitle editor specializing in {Source_EN_name}→{Target_EN_name} translation.
Apply the term correction below. Output ONLY the corrected {Target_EN_name} subtitle line.

Rules:
1. Keep the meaning, register, and length of the existing translation as close to the original as possible.
2. Replace only the specified term — do not rewrite unrelated parts.
3. Keep the same punctuation style as the input.
4. Output the corrected line only, no preamble, no quotes.
5. If the term is already correctly translated in the existing line, output the input unchanged.
```

(Existing 5-6 rules preserved; "Chinese" replaced with `{Target_EN_name}` token.)

### 6.3 Model selection

- Default: `qwen3.5-35b-a3b` (engine key in `translation/ollama_engine.py`)
- Override: optional `profile.translation.glossary_apply_model: <engine_key>` field. If set and valid (in engine registry), used instead of default.
- Implementation location: new helper `apply_glossary_term(source_text, current_target, term_source, term_target, source_lang, target_lang, model_override=None)` in `translation/ollama_engine.py` (or sibling module — discuss in plan).
- OpenRouter engine inherits same helper if user's profile uses OpenRouter model.

### 6.4 What stays unchanged
- Auto-translate batch pipeline (`OllamaTranslationEngine.translate`) — keeps current Chinese-output system prompt.
- Sentence pipeline, alignment pipeline, post-processor — unchanged.
- `_filter_glossary_for_batch` — still injects glossary terms into auto-translate prompt, but glossary's source must equal `en` and target must equal `zh` for this injection to apply (silently skip incompatible glossaries; log info on first call per file).

## 7. UI Changes

### 7.1 Files affected
- `frontend/Glossary.html` — main editor
- `frontend/proofread.html` — glossary panel + apply modal + find&replace
- `frontend/index.html` — dashboard glossary selector
- `frontend/admin.html` — admin glossary list (read-mostly)

### 7.2 Glossary editor (`Glossary.html`)

New metadata fields in header form:
- 原文語言 dropdown (8 options from `SUPPORTED_LANGS`)
- 譯文語言 dropdown (same)

Glossary list view shows language pair badge: `Broadcast News (EN→ZH) — 20 條`.

Entries table column header: 「原文 | 譯文 | actions」 (no language codes — implied by glossary header).

Entry input placeholder shows current `source_lang` / `target_lang` friendly name as hint, e.g., `placeholder="日本語"` when `source_lang=ja`.

### 7.3 Proofread panel (`proofread.html`)

Glossary dropdown items show pair: `Anime Terms (JA→ZH)`.

Apply modal title shows pair: `詞彙表套用 — Broadcast News (EN→ZH)`.

Modal body has up to 3 sections (collapse if empty):
1. **嚴格匹配 (3 處)** — auto-checked
2. **寬鬆匹配 (2 處) — 需檢視** — un-checked by default, with hint "可能因同 script 字符包夾誤中"; only renders when `loose_violation_count > 0`
3. **已符合 (8 處)** — un-checked, present for review

Independent "全選嚴格" / "全選寬鬆" buttons.

### 7.4 Dashboard (`index.html`)

Glossary dropdown labels include pair: `Broadcast News (EN→ZH) — 20 條`.

### 7.5 Admin (`admin.html`)

Glossary list table gets two columns: Source / Target (lang codes).

### 7.6 JS rename surface

~60 property accesses across the 4 files:
- `entry.en` → `entry.source`
- `entry.zh` → `entry.target`
- `entry.zh_aliases` → `entry.target_aliases`
- `row.term_en` → `row.term_source`
- `row.term_zh` → `row.term_target`
- POST/PATCH bodies: `{ en, zh }` → `{ source, target }`

API responses change shape — frontend must update at the same time as backend. Same commit.

### 7.7 Hardcoded labels removed

12 occurrences of literal 「EN」/「ZH」/「英文」/「中文」 in glossary-adjacent UI replaced with 「原文」/「譯文」 (lang-neutral) plus a separate display of the actual lang pair (from glossary metadata).

## 8. CSV Format

### 8.1 Format

```csv
source,target,target_aliases
broadcast,廣播,
anchor,主播,主持;新聞主播
Vinicius,雲尼素斯,維尼修斯;维尼修斯
```

- Header MUST include `source` and `target`. `target_aliases` column is OPTIONAL — omit entirely if no glossary entry has aliases. If present, individual rows may have empty value (= no aliases for that row).
- Accepted headers (exact, lowercase): `source,target` OR `source,target,target_aliases`. Any other header → 400.
- Multiple aliases in a single cell separated by `;` (semicolon), each item `.strip()`-ed; empty items dropped.
- All cells whitespace-trimmed.
- Per-row validation failure: silently skipped (matches current import behavior — backend logs warning to server stderr).

### 8.2 Old format handling

Import with header `en,zh` → 400 with body:
```json
{"error": "CSV must use columns: source, target, target_aliases (got: en, zh). Update the header row and re-import."}
```

No silent fallback. User responsibility to migrate (pre-deploy CSV export → edit header → re-import).

### 8.3 Language metadata

Not in CSV. Inherited from glossary metadata (`source_lang`, `target_lang`) at import time. This keeps CSV simple and ties entries to the glossary's lang pair (no chance of cross-language pollution within one glossary).

## 9. Cutover Plan

**Step 0 — User pre-deploy responsibility (manual)**
- Export each glossary worth keeping via `GET /api/glossaries/<id>/export` (current endpoint, returns old `en,zh` CSV).
- Edit CSV header `en,zh` → `source,target` (add `,target_aliases` if you have any).
- Save offline; will re-import after deploy.
- Estimated effort: 5 minutes for the 5 existing glossary files.

**Step 1 — Backend commit**
- `glossary.py` field/CRUD/validation/CSV rewrite.
- `app.py` routes (`glossary-scan` two-stage, `glossary-apply` parameterized).
- New helper `apply_glossary_term()` for the model-overridden path.
- Boot scan: ignore glossary files without `source_lang` (log warning, do not crash).
- `_filter_glossary_for_batch`: skip glossaries whose `source_lang != "en"` or `target_lang != "zh"` (auto-translate is EN→ZH only).
- New endpoint `GET /api/glossaries/languages` returning the whitelist.

**Step 2 — Frontend commit** (same PR; backend + frontend ship together since field rename breaks ABI)
- 60+ JS property renames.
- New dropdowns + labels + apply modal sections.
- Inline tests if any test_glossary*.spec.js exists — update field names.

**Step 3 — Delete old glossary files**
- `git rm backend/config/glossaries/*.json`.
- Backend already ignores them (Step 1); deletion is housekeeping.

**Step 4 — Tests** (in same PR)
- Update existing pytest cases (~15) for renamed fields.
- Add new pytest cases (Section 11).
- New Playwright spec `test_glossary_multilingual.spec.js`.

**Step 5 — Docs** (in same PR)
- CLAUDE.md new version entry.
- README.md 繁體中文 glossary section update.
- This design doc lives in `docs/superpowers/specs/`.

**Rollback**: single `git revert` of the merge commit. Old glossary files already deleted — rolled-back state has empty glossary list, no data corruption.

## 10. Out-of-Scope (Explicit)

- ❌ Multilingual auto-translate pipeline (JA→ZH ASR + translation): separate spec.
- ❌ Per-entry language tags (Option C from brainstorming): explicitly rejected.
- ❌ LLM auto-detect of glossary direction.
- ❌ Cross-glossary fallback (`if not found in EN→ZH glossary, try EN→JA glossary`).
- ❌ Source aliases (only target_aliases).
- ❌ Per-language script-set validation rules.
- ❌ Backward-compat read of old `en`/`zh` field names.
- ❌ Multi-user collaborative glossary editing.
- ❌ Auto-translate to non-Chinese targets.
- ❌ CSV with `source_lang`/`target_lang` columns (metadata stays at glossary level).
- ❌ Migration of in-memory `_file_registry.translations[*].baseline_zh` / `applied_terms` (orphan after rename; harmless).

## 11. Testing Strategy

### 11.1 Backend unit tests

**Updated**:
- `test_glossary.py` — rename fields across all cases (~30 cases).
- `test_glossary_apply.py` — rename `term_en`/`term_zh`/`baseline_zh` (~12 cases).

**New** (`test_glossary_multilingual.py`):
1. Glossary create missing `source_lang` → 400.
2. `source_lang: "xx"` → 400 with whitelist in error.
3. Entry rejected when `source_lang == target_lang AND source == target`.
4. Entry accepted when `source_lang == target_lang AND source ≠ target` (EN normalization).
5. Strict scan `source_lang=zh`, term `源`, segment `資源充足` → 0 strict, 1 loose.
6. Strict scan `source_lang=zh`, term `「廣播」`, segment `他講「廣播」` → 1 strict, 0 loose.
7. Strict scan `source_lang=ja`, term `ニュース`, segment `朝のニュース` → 0 strict, 1 loose.
8. Strict scan `source_lang=en`, term `broadcast`, segment `he made a broadcast` → 1 strict, 0 loose.
9. Apply prompt has `"Japanese subtitle:"` when glossary source_lang=ja.
10. Apply uses `qwen3.5:35b-a3b-mlx-bf16` model regardless of active profile (default).
11. Apply uses overridden model when `profile.translation.glossary_apply_model` is set and valid.
12. Boot ignores glossary file lacking `source_lang` + logs warning + does not crash.

### 11.2 Backend API tests
- POST glossary missing `source_lang` → 400.
- POST entry with `{source: "中文", target: "Chinese"}` to `source_lang=ja` glossary → 200 (no script check).
- POST `/import` with `en,zh` header CSV → 400 with helpful error.
- POST `/import` with 3-col CSV including aliases → 200 + correct entry count.
- GET `/api/glossaries/languages` returns the 8-lang whitelist.
- GET `/glossary-scan` response shape includes `strict_violations`, `loose_violations`, `glossary_source_lang`, `glossary_target_lang`.

### 11.3 Playwright E2E (`test_glossary_multilingual.spec.js`)
1. Create ZH→ZH glossary via UI, add entry, scan file: only strict matches checked by default.
2. Create JA→ZH glossary: header displays `Japanese → 中文`.
3. Apply modal shows 「嚴格匹配」 + 「寬鬆匹配」 sections only when source_lang ∈ {zh, ja, ko, th}.
4. Import old `en,zh` CSV → error toast.
5. Import new 3-col CSV with aliases → success + correct count.

### 11.4 Regression
- Existing ~286 backend pytest cases: re-run; cases touching glossary fields must be updated in same commit.
- Existing Playwright specs (especially `test_user_features.spec.js` glossary scenarios) — update.
- Ralph ×10 on new specs.

### 11.5 Not tested (YAGNI)
- Full 8-language × edge-case matrix for boundary regex — sample 3 representative langs (en, zh, ja).
- Auto-translate behavior — unchanged, no test needed.
- Migration script — no migration exists.

## 12. Implementation Sequencing (preview — not the plan)

The actual implementation plan will be generated via `writing-plans` skill in a follow-up step. High-level order:

1. Backend schema + validation + CSV (least risk, no UI dependency).
2. Backend scan two-stage + API response shape.
3. Backend apply prompt + model override.
4. Backend boot ignore-old-files + `/api/glossaries/languages` endpoint.
5. Frontend Glossary.html refactor.
6. Frontend proofread.html (panel + apply modal).
7. Frontend index.html + admin.html.
8. Tests + ralph stability.
9. Docs.
10. Delete old glossary files.

Each phase is independently testable (backend + frontend ship in one PR but commits stay atomic).

## 13. Open Questions / Notes

- **Qwen 3.6**: User mentioned this but codebase only registers up to `qwen3.5-35b-a3b`. Default uses 3.5 until user confirms a newer model ID exists in Ollama. Override path supports any future engine key without code change.
- **`glossary_apply_model` validation**: when profile sets this to an unknown engine, fall back to default with warning toast (don't 400 on every apply call).
- **Loose match perf**: `term in segment` is O(N*M) per segment per term. For typical broadcast files (≤200 segments × ≤50 terms) this is sub-ms. Don't optimize.

## 14. Acceptance Criteria

This refactor is "done" when:

- [ ] All glossary entries on disk use `{source, target, target_aliases?}` schema with glossary-level `source_lang`/`target_lang`.
- [ ] Adding glossary entry with `source="2024"` (pure number) succeeds.
- [ ] Adding glossary entry with `source_lang=ja, source="ニュース", target="新聞"` succeeds.
- [ ] Scanning a ZH-source glossary on a file shows 嚴格匹配 separately from 寬鬆匹配 in the apply modal.
- [ ] Glossary-apply on a JA→ZH glossary calls LLM with `"Japanese subtitle:"` in the prompt.
- [ ] Glossary-apply always uses `qwen3.5-35b-a3b` unless overridden via profile.
- [ ] Old `en,zh` CSV import returns 400 with actionable error.
- [ ] All existing pytest + Playwright specs (after field renames) pass.
- [ ] New `test_glossary_multilingual.py` + `test_glossary_multilingual.spec.js` pass.
- [ ] CLAUDE.md and README.md updated.
- [ ] Ralph ×10 on new specs.
