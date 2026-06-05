# Segment Split / Merge — Design Spec

- **Date:** 2026-06-05
- **Branch:** `worktree-feat+segment-split` (based on `feat/glossary-v2`)
- **Scope:** Proofread editor (`frontend/proofread.html`) — `output_lang` pipeline only
- **Status:** Design — hardened by adversarial code-review (33-agent workflow, all findings code-verified) — pending user review

---

## 1. Goal

Let a proof-reader **split** one subtitle cue into two, or **merge** a cue with the
next one, directly from the proofread segment list — keeping the whole project
(段列表 / 時間軸 / Preview overlay / SRT export / burnt-in render) in sync, with no
index misalignment.

Two split modes, surfaced as **two buttons on the LEFT of each segment row**:

| | ① AI 切割 | ② 機械式硬切割 |
|---|---|---|
| **Time split** | by **content-language char ratio** `r` (clamped 0.15–0.85) | fixed midpoint `r = 0.5` |
| **Text split** | LLM splits **every** language (source + outputs) at one aligned semantic/punctuation boundary | **no split — both halves duplicate the full original text** (each language) |
| **LLM** | Ollama `qwen3.5:35b-a3b` via `_make_ollama_llm_call()` | none — instant |
| **Approval** | both halves reset to `pending` | both halves reset to `pending` |
| **Fallback** | on LLM error/invalid output → mechanical (duplicate) + toast | — |

A third action, **合併下一段 (merge-next)**, is a small button on the **RIGHT** of each
row (disabled on the last row).

### Decisions log (user-confirmed)

1. **Validation-First waived** — the user explicitly chose to skip the CLAUDE.md
   Validation-First empirical gate for the LLM split. Compensated with **runtime
   guards** (output reconstruction check + mechanical fallback) — defensive
   engineering, not empirical validation.
2. **Time split point:** by character-count ratio (mechanical = fixed midpoint).
3. **Bilingual:** 2 output languages → LLM splits **both** in one call, aligned.
4. **Mechanical text:** both halves duplicate the full original text.
5. **Merge button:** right side of each segment row.
6. **Time gap:** contiguous, no gap — `seg1 = [start, mid]`, `seg2 = [mid, end]`.
7. **Mode scope:** `output_lang` only. V6 / profile do not show the buttons.
8. **Approval after split/merge:** both resulting cues reset to `pending`.

---

## 2. Data model (verified against code)

Three parallel, positionally-aligned lists in the in-memory file registry
(`backend/app.py`, `_file_registry`, guarded by `_registry_lock`, persisted via
`_save_registry()`), plus the cached ASR base.

> **POSITIONAL INVARIANT:** index `i` across `segments` / `translations` /
> `aligned_bilingual` / `content_asr_segments` (when present) is the **same logical
> cue**. §4 maintains this on every split/merge. Re-derive ops gate on a length check
> (`len(base) == len(live)`, app.py:601) and fall back if violated — so the invariant
> is load-bearing, not cosmetic.

### `entry["segments"]` — timing/source authority
```python
{"id": int,       # POSITIONAL — equals 0-indexed list position, assigned at transcription
 "start": float,  # seconds
 "end": float,
 "text": str,     # source/content-language text
 "words": [{"word","start","end","probability"}, ...]}  # may be []
```
- `PATCH /segments/<seg_id>` looks segments up by **`s["id"] == seg_id`** (linear scan,
  `app.py:5147`). **Mandatory:** any insertion must renumber `id` to match position.
- That PATCH branch also propagates the edit to `translations[*]["en_text"]` gated by
  `t.get('seg_idx', i) == seg_position` (app.py:5156-5161). This touches **`en_text`
  only** — an EN-mode field — so it is **inert for output_lang** (whose text lives in
  `by_lang`/`{lang}_text`). Positional enumeration is the real segment↔translation key,
  kept valid by the §4 renumber; the `idx`/`seg_idx` lookup is not a correctness concern
  for this feature's scope.

### `entry["translations"]` — output-language rows (verified `output_lang_persist.py`)
```python
{"idx": int,                       # explicit 0-indexed position
 "start": float, "end": float,
 "status": "pending" | "approved",
 "by_lang": {"<lang>": {"text": str, "status": "pending", "flags": []}, ...},
 "<lang>_text": str,               # top-level mirror, one per language
 "glossary_changes": [{"before": str, "after": str, "glossary": str, "source": str}, ...]}
```
- Renderer + SRT export read `start`/`end` + the text mirrors directly from rows.
- `glossary_changes` is always a list (may be `[]`); the frontend already coerces
  defensively (`Array.isArray(...) ? ... : []`, proofread.html:1958).

### `entry["aligned_bilingual"]` — O1 paired grid (verified `app.py:693-707`)
```python
{"start": float, "end": float,
 "by_lang": {"<lang>": "<text string>", ...}}   # NB: values are STRINGS, not dicts
```
- Present only for bilingual files (best-effort for legacy single-pass files).

### `entry["content_asr_segments"]` — cached ASR base (re-derive source)
- Same shape as `segments`. Used by `glossary-reapply` (app.py:4700) and
  add-second-language (`_run_output_lang_second_cross`, app.py:663-708) to **1:1
  re-derive** outputs; both `raise`/fall through when it is absent or length-mismatched.
- **CRITICAL:** if the proofread grid is split/merged but this base is not, re-derive
  rebuilds from the stale N-row base → misalignment / loss of the split. **Split/merge
  MUST keep `content_asr_segments` in sync** (§4) when it is present.

### Route `seg_id` semantics (frontend↔backend contract)
`seg_id` in the route equals the segment's **`id` field = its 0-indexed list position**.
The frontend MUST send `seg.id` derived from the **same 0-indexed scheme**. (Today
`loadSegments` sets `id: i + 1`; §6 changes the reconstruction to carry the backend's
0-indexed `id` verbatim so `/segments/${seg.id}/split` hits the right cue.)

### Downstream that needs **no change** (verified)
- **SRT/VTT export** re-emits cue numbers sequentially; reads `start`/`end`. Export
  tolerates length divergence by falling back to empty dicts (app.py:5013-5051) — which
  would *silently lose data*, so §4/§8 add an explicit `len(segments)==len(translations)`
  assertion to catch any cascade bug loudly.
- **Renderer** (`generate_ass`) reads `start`/`end` + text mirrors from translation rows.
- **Preview overlay** (`onVideoTime`) recomputes the active cue each tick from `segs[]`.

> "後面 segment 嘅時間自動調整" clarified: subsequent cues keep their real start/end.
> Only their **index/`id`/`idx`** shift; the renumber cascade prevents the
> segment↔translation "時間段錯位".

---

## 3. Backend API

### Endpoints
```
POST /api/files/<file_id>/segments/<int:seg_id>/split   body: {"mode": "ai" | "mechanical"}
POST /api/files/<file_id>/segments/<int:seg_id>/merge-next
```
`@require_file_owner` (consistent with existing segment routes). Both return the
**full updated arrays** `{ "segments": [...], "translations": [...] }`. The frontend
rebuilds `segs[]` from **`translations`** alone (segments is backend bookkeeping; see §6).

### Concurrency model (M1 — do NOT hold the lock across the LLM call)
- **mechanical split** and **merge-next** run fully inside `with _registry_lock:`,
  end with `_save_registry()`.
- **AI split** is **three-phase** (mirrors glossary-reapply's snapshot→LLM→write):
  1. **Phase 1 (lock held):** look up the segment by `id`; snapshot its texts
     (`segments[p].text` + each `translations[p].by_lang[lang].text`) + `start`/`end`;
     release lock.
  2. **Phase 2 (NO lock):** call the LLM on the snapshot (~2–5 s).
  3. **Phase 3 (lock held):** re-locate the segment by `id` (it may have moved);
     if its `id`/`start`/`end` changed since phase 1 → discard, return **409**
     `{"error": "段落已被其他操作修改，請重試"}`. Else apply the split, renumber,
     assert `len(segments)==len(translations)`, `_save_registry()`, return arrays.

### Render-in-progress guard (S5)
Before phase-1, check render state using the existing pattern (app.py:4054-4057):
acquire `_render_jobs_lock`, scan `_render_jobs` for any job with
`job.get('status')=='processing'` and `job.get('file_id')==file_id`, release. If found
→ **409** `{"error":"正在渲染中，無法修改段落"}`. To avoid TOCTOU / nested-lock hazards,
acquire `_render_jobs_lock` strictly **before** `_registry_lock` if both are ever held,
or use an in-registry `_pending_render` flag (mirrors `_pending_second_lang`,
app.py:819/4648). Do not read `_file_registry` while holding only `_render_jobs_lock`.

### Validation / error responses
| Condition | Status | Body |
|---|---|---|
| File not found | 404 | `{"error": "文件不存在"}` |
| Segment id not found | 404 | `{"error": "段落不存在"}` |
| `active_kind != "output_lang"` | 400 | `{"error": "分割只支援輸出語言流程"}` |
| split: `(end-start) < 0.4` s | 400 | `{"error": "段落太短，無法分割（最少 0.4 秒）"}` |
| merge-next: seg is the last cue | 400 | `{"error": "已經係最後一段，無法合併下一段"}` |
| render job in progress | 409 | `{"error": "正在渲染中，無法修改段落"}` |
| AI concurrent-edit conflict (phase 3) | 409 | `{"error": "段落已被其他操作修改，請重試"}` |
| `mode` not in {ai, mechanical} | 400 | `{"error": "未知分割模式"}` |

---

## 4. Cascade algorithm (the core)

All present lists stay positionally aligned. `p` = list index of the segment whose
`id == seg_id`.

### SPLIT
1. **Compute the two text halves per language:**
   - **mechanical:** `part1 = part2 = full_text` for source + every output language;
     `r = 0.5`.
   - **ai:** call the LLM split (§5) over the texts present.
     - **Single-language file** (source ∈ outputs, no other output): call the LLM with
       the **single** source text only (not a pseudo-pair); response
       `{"parts":[{src:p1},{src:p2}]}`; reconstruction guard runs once.
     - **Bilingual:** the LLM splits both, aligned.
   - **Ratio:** `content_text` = the source/content-language text. For passthrough
     files (e.g. `yue→yue`) source == output; ratio comes from source length.
     `r = len(part1_content) / len(content_text)`, clamped `[0.15, 0.85]`. If
     `content_text` empty → first output language; if still empty → `r = 0.5`.
2. `mid = round(start + (end - start) * r, 3)`. `seg1 = [start, mid]`, `seg2 = [mid, end]`.
3. **`segments`:** replace `segments[p]` with two dicts (`seg1` text = source part1,
   `seg2` text = source part2; partition `words` by `w["start"] < mid`).
4. **`content_asr_segments`** (if present): apply the **same** split at `mid` with the
   same source parts → keeps re-derive ops correct.
5. **`translations`:** replace row `p` with two rows. Per language L:
   `by_lang[L] = {"text": partN_L, "status": "pending", "flags": []}`, mirror
   `{L}_text = partN_L`. Row `status = "pending"`, `glossary_changes = []`,
   `start`/`end` set to `seg1`/`seg2`.
6. **`aligned_bilingual`** (if present): replace row `p` with two rows
   (`by_lang[L]` = partN_L **string**; `start`/`end` set).
7. **Renumber** (mandatory — PATCH at app.py:5147 looks up by `id`):
   `segments[i]["id"] = i` and `translations[i]["idx"] = i` for all `i`.
8. Assert `len(segments) == len(translations)`. Rebuild
   `entry["text"] = " ".join(s["text"] for s in segments)`; `_save_registry()`.

### MERGE-NEXT
1. `a = segments[p]`, `b = segments[p+1]`.
2. `merge_text(x, y) = (x.strip() + " " + y.strip()).strip()` (works CJK + Latin; user
   edits afterwards). Time `[a.start, b.end]`. `words = a.words + b.words`.
3. **`translations`:** for each language L in `union(a.by_lang, b.by_lang)`:
   `merged.by_lang[L] = {"text": merge_text(a[L].text, b[L].text), "status":"pending", "flags":[]}`,
   mirror `{L}_text` = merged text. `glossary_changes` = both rows' lists concatenated
   (pattern app.py:622-623). Row `status = "pending"`. **`aligned_bilingual`** (if
   present): `by_lang[L]` values are **strings** → `merge_text(...)`.
4. Apply the merge to `segments`, `content_asr_segments` (if present), `translations`,
   `aligned_bilingual` (if present); time `[a.start, b.end]`.
5. **Renumber** `id` / `idx` (mandatory — PATCH lookup invariant); assert
   `len(segments)==len(translations)`; rebuild `entry["text"]`; `_save_registry()`.

### Absent `content_asr_segments` (legacy files)
Split/merge skip the base sync (`if present` guard) and are still safe. Downstream
asymmetry, by design:
- **glossary-reapply** → 400 「此檔案無內容語音快取，請重新處理」 (cannot fall back).
- **add-second-language** → gracefully falls back to legacy re-transcribe + index-merge
  (app.py:611).

Split/merge on such files is permitted (§7), but glossary-reapply will then fail.

### New module — `backend/segment_split.py` (pure, no Flask import)
Per "many small files". Pure, immutable (return new lists):
- `compute_split_ratio(content_text, mode, ai_parts) -> float`
- `split_segments_list(segments, p, mid, src_part1, src_part2) -> list`
- `split_translations_list(translations, p, parts_by_lang, seg1, seg2) -> list`
- `split_aligned_list(aligned, p, parts_by_lang, seg1, seg2) -> list`
- `merge_*` counterparts
- `renumber(segments, translations) -> (segments, translations)`
- `build_split_prompt_system(langs: List[str]) -> str` — stable system prompt
- `build_split_prompt_user(texts_by_lang: Dict[str,str]) -> str` — the cue texts
- `parse_split_response(raw: str, texts_by_lang) -> Dict[str, Tuple[str,str]] | None`
  — strip ```fences, regex-extract `{...}` if needed, `json.loads`, validate, transpose
  `{"parts":[{lang:p1}...]}` → `{lang:(p1,p2)}`; return `None` on any failure.
- `normalize(text: str) -> str` (see §5)
- `mechanical_fallback(texts_by_lang) -> Dict[str, Tuple[str,str]]` (duplicate)

`app.py` owns only the route + lock orchestration (the three phases) + LLM-call
injection + registry write, calling into this module.

---

## 5. LLM split (AI mode)

- **Model / signature:** the shared `_make_ollama_llm_call()` (Ollama `qwen3.5:35b-a3b`,
  temp 0.3). Signature is `Callable[[str, str], str]` — `(system_prompt, user_message) → text`.
- **Call sequence:**
  1. `sys = build_split_prompt_system(list(texts_by_lang))`
  2. `user = build_split_prompt_user(texts_by_lang)`
  3. `raw = llm_call(sys, user)`
  4. `parts = parse_split_response(raw, texts_by_lang)` → on `None`, `mechanical_fallback(...)`.
- **Task:** find ONE semantic boundary, **prioritising punctuation**, split **each**
  text into exactly two parts at the aligned point. Prompt instructs: output ONLY JSON,
  no markdown, no thinking tags, preserve the input script (do not convert trad↔simp).
- **Output JSON:**
  ```json
  {"parts": [{"en": "part1", "yue": "粵語part1"},
             {"en": "part2", "yue": "粵語part2"}]}
  ```
- **Parse + repair (S1):** strip ```json fences; `json.loads`; on failure regex-extract
  `\{.*\}` (DOTALL) and retry. `None` on unparseable.
- **`normalize(text)` (S1 + S2):** (1) remove all whitespace; (2) remove punctuation
  (`set("。，、！？；：）（「」『』【】…—\"") | string.punctuation`); (3) lowercase Latin
  only; (4) **OpenCC `t2s` both sides** before comparing, so trad↔simp drift from the
  LLM does not cause a false rejection.
- **Reconstruction guard (not Validation-First):** for each language verify
  `normalize(part1 + part2) == normalize(original)`. **Reject** (→ mechanical fallback +
  toast 「AI 切割失敗，已改用機械式切割」) if: any language fails reconstruction, JSON
  unparseable, or the **source/content-language** part is empty for a non-empty source.
  For non-source output languages an empty part is allowed — it inherits the empty state.
  - *Bilingual example:* source `yue='你好世界'`, out `zh='你好世界'`; LLM returns
    `part1={yue:'你好', zh:''}, part2={yue:'', zh:'世界'}` → REJECT (source `yue` part2
    empty) → mechanical fallback (duplicate both).
- **Empty-text cue:** skip the LLM entirely; time-only split; empty both halves.
- **Telemetry (optional, post-launch):** log fallback rate; if >10% over 20+ diverse
  splits, add a retry with a stricter prompt.

---

## 6. Frontend (`proofread.html`)

### Row layout
Grid `24px 56px 1fr auto` (`.rv-b-rail-item`, line 555) → `38px 24px 56px 1fr auto 24px`:
- **col 1 (38px, NEW):** split-cluster — two hover-reveal icon buttons (AI ✨/wand,
  mechanical ✂/half). `event.stopPropagation()`; both `disabled` when
  `(s.out - s.in) < 400`; AI shows a row spinner while running.
- cols 2–5: existing num / ts / text / flags.
- **col 6 (24px, NEW):** merge-next button (hover-reveal); `disabled` on last row.
- The find-bar overlay re-render (`renderSegList` ~2902) must keep the same 6-child
  template — verify no 4-column assumption remains.

Icons follow codebase convention: inline SVG, `viewBox="0 0 16 16"`,
`stroke="currentColor"`, `stroke-width="1.75"`, rounded caps. Hover-reveal mirrors
`.qi-del` (opacity 0 → 1 on `:hover` / `.cur`).

### `_rebuildSegsFromArrays(translations, languages) → segs[]` (M4 — exact contract)
Input is **`translations`** (NOT a `segments` array — matches `loadSegments`, which maps
from `translations`, proofread.html:1930-1965) + language descriptors. Per row, replicate
lines 1930-1965 exactly:
- `firstL = languages[0]?.lang || 'yue'`; `secondL = languages[1]?.lang`.
- `firstText = t[`${firstL}_text`] || t.by_lang?.[firstL]?.text || ''` (same for second).
- **seconds→ms:** `inMs = Math.round((t.start||0)*1000)`, `outMs` likewise,
  `durSec = (outMs-inMs)/1000`.
- `cps = durSec>0 ? round(firstText.length/durSec,1) : 0`; `_cpsSecond` similarly.
- `tsIn/tsOut = fmtMs(inMs/outMs)`; `duration = durSec.toFixed(1)`; `_hasSecond = !!secondL`.
- `id` = backend `t`/segment 0-indexed id carried verbatim (NOT `i+1`); `idx = t.idx ?? i`.
- `approved = t.status === 'approved'`; `edited = t.edited === true`;
  `flags` = rebuilt via the existing helper (+ CPS flag); `glossary_changes =
  Array.isArray(t.glossary_changes) ? t.glossary_changes : []`.
- stub `speaker/candidates/glossary/asr/mt`.

> **id scheme (M3):** drop `loadSegments`'s `id: i+1` for output_lang and carry the
> backend 0-indexed `id`; the split/merge buttons call `/segments/${seg.id}/...` so the
> server's `s["id"] == seg_id` scan matches. This is an intentional change to the current
> line 1946.

### New JS
- `splitSegment(i, mode)` → `POST .../segments/${segs[i].id}/split {mode}`.
- `mergeNext(i)` → `POST .../segments/${segs[i].id}/merge-next`.
- Both: `try { spinner on; r = await fetch(...); if (!r.ok) throw new Error((await r.json()).error || 'HTTP '+r.status); const {translations}=await r.json(); segs = _rebuildSegsFromArrays(translations, langs); renderSegList(); renderWaveformRegions(); setCursor(mode split ? i+1 : i, false); flash(...); showToast('段落已分割'/'已合併','success'); } catch(e){ showToast(e.message,'error'); } finally { spinner off; re-enable buttons; }`
  — mirrors `reapplyGlossary` / `saveEditEntry` error handling (S8).

### Keyboard (S7)
- `Ctrl+Shift+S` = AI split current, `Ctrl+Shift+D` = mechanical, `Ctrl+Shift+M` = merge-next.
- Register **before** the `if (inInput) return;` guard at line 2965 (like the existing
  Cmd+F branch) so they fire while editing; each `preventDefault()`.
- Note: `Ctrl+Shift+D` (Chrome devtools) / `Ctrl+Shift+M` (private window) may be shadowed
  on some browsers/platforms — document in user help; the row buttons are the primary path.

---

## 7. Edge cases

| Case | Handling |
|---|---|
| duration < 0.4 s | both split buttons `disabled` + tooltip; server 400 double-guard |
| LLM fail/timeout/invalid/JSON-unparseable | mechanical fallback (duplicate) + toast |
| LLM trad↔simp drift | `normalize()` t2s both sides → not a false reject |
| empty-text cue | time-only split, empty halves |
| source-language part empty (non-empty source) | reject LLM → mechanical fallback |
| non-source output part empty | allowed; inherits empty state |
| single-language file (source == only output) | LLM called once with one text; guard runs once; base mirrors segments |
| last cue | merge-next disabled (button + server 400) |
| `aligned_bilingual` absent | skip that list (single-language / legacy) |
| `content_asr_segments` absent | skip base sync; glossary-reapply later 400s; add-2nd-lang falls back |
| `glossary_changes` null/missing | frontend coerces to `[]` in `_rebuildSegsFromArrays` |
| split during playback | no pause; next `timeupdate` re-resolves active cue from rebuilt `segs[]` |
| render in progress | server 409 + toast |
| concurrent edit during AI phase 2 | phase-3 conflict check → 409 + toast |
| glossary-reapply / add-2nd-lang after split | correct because `content_asr_segments` synced (§4) |

---

## 8. Testing plan

**Backend unit (`backend/tests/test_segment_split.py`):**
- pure `segment_split.py`: ratio (mechanical=0.5, ai clamp 0.15–0.85), list splits keep
  length+1 + correct renumber, merge keeps length-1, words partition by `mid`.
- `normalize()` + reconstruction guard: EN multi-space/punct/case; CJK no-space + punct
  movement + trailing ellipsis; trad↔simp via t2s passes; content-changed fails →
  fallback; bilingual one-lang-fail → whole split rejected; single-char splits.
- `parse_split_response`: markdown-fenced JSON, preamble+JSON, single-quote/garbage → None.
- route tests (Flask): split single-lang + bilingual; **assert `len(segments)==len(translations)`**
  after every split/merge; idx/id renumber; 400 too-short; 400 last-cue merge; 409
  render-in-progress; 409 phase-3 conflict; `content_asr_segments` synced (len matches).

**Manual smoke:**
1. Single-language output_lang: AI split → rail + timeline update; SRT cue count +1,
   timings contiguous; render uses new timing.
2. Bilingual: AI split → both languages split + aligned; bilingual SRT pairs not shifted.
3. Mechanical split → both halves duplicate text; midpoint timing.
4. Merge-next → text concatenated, timing union, idx renumbered.
5. After a split, run **glossary-reapply** → grid stays N+1, no misalignment.
6. After a split, run **add-second-language** → the new split row's derived text is
   **non-empty** (confirms `content_asr_segments` synced, not deriving from a stale base).

---

## 9. Implementation phasing

1. **Backend** — `segment_split.py` (pure) + 2 routes (3-phase AI) + render-guard +
   `content_asr_segments` sync + post-cascade assertion + unit/route tests.
2. **Frontend** — row grid + 3 buttons + CSS + spinner/flash + `splitSegment`/`mergeNext`
   (try/catch/finally) + `_rebuildSegsFromArrays(translations, languages)` + 0-indexed `id`
   change + keyboard (before inInput guard).
3. **Verification** — manual smoke (1–6 above), `pytest`, curl.
4. **Docs** — CLAUDE.md (REST table + feature), README.md (繁中), PRD status.

## 10. Out of scope (future)
- Split at arbitrary playhead position (endpoint may later accept `{"split_at": <sec>}`).
- Undo stack (merge-next is the practical inverse for now).
- V6 / profile mode support.
