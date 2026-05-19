---
version: 5.0
status: Draft (pending implementation plan)
date: 2026-05-19
parent: 2026-05-16-asr-mt-emergent-pipeline-design.md (v4.0)
validation_evidence: backend/scripts/v5_prototype/
---

# V5 Dual-ASR + Refiner-Translator Separation — Design Spec

## §1. Goals + Non-goals

### Goals

1. **One video → multi-language subtitle output**. The pipeline produces subtitles in N target languages from a single transcription pass. Targets defined at pipeline level (fixed superset).
2. **Refiner stage ≠ Translation stage**. The "MT" concept used in v3.x / v4.x is split into two stages with disjoint responsibilities:
   - **TranslatorEngine** (cross-lingual): source-lang text → target-lang text
   - **RefinerEngine** (same-lingual): lang_X text → polished lang_X text (register, glossary, disfluency)
3. **Optional dual-ASR cross-validation**. A second ASR can run in parallel; an LLM-as-judge VerifierEngine reconciles disagreements. Critical for weak-source-language scenarios (e.g., Cantonese, where Whisper alone hallucinates).

### Non-goals

- Web SaaS / mobile deployment — desktop/LAN multi-user only (continues v4 R5 posture).
- Streaming ASR (live captioning) — file-based pipeline only.
- Replacing the v4 R5 backend infrastructure (Flask + JobQueue + SQLite + SocketIO) — v5 is a stage-layer + schema-layer evolution.
- New non-MLX dependencies — all components must run on Apple Silicon via MLX or HTTP-served Ollama/OpenRouter.
- Re-segmentation algorithm refactor — long Whisper segments (e.g., the 28-second hallucination window) get the verifier's full text in one segment; downstream re-splitting is future work.

### Context references

- **v3.18 stage-2 prompt削減** ([2026-05-15-stage2-prompt-override-design.md](../specs/2026-05-15-stage2-prompt-override-design.md)) — partial fix for formulaic-phrase contamination caused by mixed "polish + translate" prompts; v5 separates the two roles to address the root cause.
- **v4.0 pipeline runner** ([pipeline_runner.py](../../../backend/pipeline_runner.py), [2026-05-16-asr-mt-emergent-pipeline-design.md](../specs/2026-05-16-asr-mt-emergent-pipeline-design.md)) — linear stage executor with per-segment 1:1 contract; v5 extends to fan-out semantics for multi-target translation.
- **Validation-First mode** (CLAUDE.md) — required for ASR/MT changes. V5 satisfied by the prototype runs documented in §10.

---

## §2. Mental Model + 3-Engine Architecture

### Why Refiner and Translator are different

Earlier versions conflated "make the subtitle better" with "translate to another language" in one LLM call. This led to two recurring problems:

- **Formulaic-phrase contamination** — the translator system prompt carried examples that mapped EN→ZH word patterns. The LLM over-used those patterns ("真正" 24×, "儘管" 13× in Video 1 baseline). v3.18 reduced the prompt but the problem recurred whenever the prompt grew.
- **Loss of register polish opportunity for source-language output** — if the source is Cantonese and the user wants a Cantonese subtitle, a "translate" stage is wrong (no language change needed), but a "polish" stage is needed (broadcast register, glossary, disfluency removal).

V5 separates these into distinct stages with distinct prompts and distinct LLM calls.

### Engine layering

```
┌──────────────────────────────────────────────────────────────────┐
│ Low-level (shared infrastructure)                                │
│   LLMEngine ABC                                                  │
│     .call(system_prompt, user_prompt, **opts) → str              │
│   Concrete: OllamaLLM / OpenRouterLLM / ClaudeLLM                │
└──────────────────────────────────────────────────────────────────┘
                              │
        ┌──────────┬──────────┴──────────┬──────────┐
        ▼          ▼                     ▼          ▼
  ┌─────────┐ ┌─────────────┐    ┌────────────┐ ┌────────────┐
  │Transcribe│ │ Translator │    │  Refiner   │ │  Verifier  │
  │  Engine  │ │   Engine   │    │   Engine   │ │   Engine   │
  └─────────┘ └─────────────┘    └────────────┘ └────────────┘
  (audio→text  (LX→LY)            (LX→LX polish)  (judge 2 ASR
   per lang)                                       outputs)
```

`LLMTranslator` and `LLMRefiner` share the same backend (e.g., Qwen3.5-A35B via Ollama) but use distinct system prompts. The ABC boundary keeps prompts and roles from leaking into each other.

### Stage layering on top of engines

5 stage types, three required, two optional:

| Stage | Required | Purpose | Engine |
|---|---|---|---|
| `asr_primary` | ✅ | Source-lang transcript with timestamps | TranscribeEngine |
| `asr_secondary` | optional | Second transcript for cross-validation | TranscribeEngine |
| `asr_verifier` | optional (requires secondary) | LLM-as-judge reconciliation | VerifierEngine |
| `refiner` (per lang) | optional | Same-lingual polish (register, disfluency, glossary) | RefinerEngine |
| `translator` (per non-source lang) | required for non-source targets | Cross-lingual conversion | TranslatorEngine |

---

## §3. Pipeline Schema v5

```jsonc
{
  "id": "uuid",
  "name": "HK broadcast (ZH+EN)",
  "version": 5,                                    // schema versioning
  "user_id": 123,                                  // v4 P1 ownership
  "shared": true,
  "created_at": "2026-05-19T00:00:00Z",
  "updated_at": "2026-05-19T00:00:00Z",

  "asr_primary": {                                 // required
    "transcribe_profile_id": "uuid",               // → TranscribeProfile
    "source_lang": "zh"                            // ISO-639-1; "auto" allowed but discouraged
  },

  "asr_secondary": {                               // null = skip dual-ASR
    "transcribe_profile_id": "uuid",
    "source_lang": "zh"                            // must equal asr_primary.source_lang
  } | null,

  "asr_verifier": {                                // null when asr_secondary is null
    "llm_profile_id": "uuid",                      // points at an LLMProfile
    "prompt_template_id": "default-verifier-v1"    // resolves to template text
  } | null,

  "target_languages": ["zh", "en"],                // pipeline-level fixed; includes source if user wants source-lang subtitle output

  "refinements": {                                 // dict keyed by lang; chain order matters
    "zh": [
      { "refiner_profile_id": "uuid" }
    ],
    "en": []                                       // empty = no refinement for that lang
  },

  "translators": {                                 // only required for non-source-lang targets
    "en": { "translator_profile_id": "uuid" }      // source→target prompt baked into profile
    // zh entry omitted because zh is source_lang (no translation needed)
  },

  "glossary_stages": {                             // optional, keyed by direction
    "zh_to_en": ["glossary-uuid"],                 // cross-lingual lock applied inside Translator
    "en": ["glossary-uuid"]                        // same-lingual lock applied inside Refiner
  },

  "font_config": { ... }                           // v4 pattern unchanged
}
```

### Field rules

- **`target_languages`** — must include each language that appears as a key in `refinements`. If `target_languages` contains a language equal to `asr_primary.source_lang`, no translator entry needed (source-language output is direct from Refiner or raw Verifier).
- **`asr_secondary.source_lang`** — must equal `asr_primary.source_lang`. Cross-language secondary ASR is out of scope.
- **`asr_verifier`** — auto-disabled when `asr_secondary` is null. UI should hide the toggle in that state.
- **`refinements[lang]`** — ordered list; runner applies in order. Empty list = skip refinement entirely for that lang.
- **`translators[lang]`** — only required for `lang != asr_primary.source_lang`. Missing translator for non-source target = validation error.
- **`glossary_stages`** — key format: `<lang>` for same-lingual, `<src>_to_<tgt>` for cross-lingual. The runner injects glossary into the appropriate stage's prompt as few-shot examples or post-correction.

### Version semantics

| Pipeline JSON `version` | Treatment |
|---|---|
| absent or `4` | v4 schema; runtime auto-promotes to v5 minimal (single ASR + single target lang inferred from `asr_profile_id` + `mt_stages`) |
| `5` | parse natively |
| `>5` | reject with explicit error (forward-compat blocked until newer client) |

---

## §4. Engine ABCs

### LLMEngine (low-level)

```python
class LLMEngine(ABC):
    """Stateless HTTP wrapper for any LLM backend."""

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_sec: float = 120.0,
        think: bool = False,        # disable Qwen3-style reasoning chain when not needed
    ) -> str:
        """Single-turn completion. Returns trimmed content. Raises RuntimeError on failure."""
```

Concrete: `OllamaLLM` (HTTP `/api/chat`), `OpenRouterLLM` (Bearer auth), `ClaudeLLM` (Anthropic Messages API). All share retry/timeout/error semantics.

### TranscribeEngine

```python
class TranscribeEngine(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        source_lang: str,
        *,
        word_timestamps: bool = False,
        context: str = "",          # domain-specific bias (e.g., "Hong Kong racing")
        progress: Optional[Callable] = None,
    ) -> list[Segment]:
        """Audio → list of {start, end, text, words?} in source_lang."""
```

Concrete: `WhisperTranscribeEngine` (mlx-whisper via existing v4 code), `Qwen3AsrTranscribeEngine` (mlx-qwen3-asr, py3.11). Future: `SenseVoiceTranscribeEngine`.

### TranslatorEngine

```python
class TranslatorEngine(ABC):
    @abstractmethod
    def translate(
        self,
        segments: list[Segment],
        *,
        source_lang: str,
        target_lang: str,
        glossary: list[GlossaryEntry] = (),
        custom_system_prompt: Optional[str] = None,    # file-level override
        progress: Optional[Callable] = None,
    ) -> list[Segment]:
        """Per-segment 1:1; preserves timestamps; outputs target_lang text."""
```

Concrete: `LLMTranslator(llm: LLMEngine)`. Prompt selected from a registry keyed by `(source_lang, target_lang)`. Custom prompt overrides default.

### RefinerEngine

```python
class RefinerEngine(ABC):
    @abstractmethod
    def refine(
        self,
        segments: list[Segment],
        *,
        lang: str,
        style: str = "broadcast",                       # e.g., "broadcast-hk", "newscast-jp"
        glossary: list[GlossaryEntry] = (),
        custom_system_prompt: Optional[str] = None,
        progress: Optional[Callable] = None,
    ) -> list[Segment]:
        """Per-segment 1:1; same lang in/out; preserves timestamps."""
```

Concrete: `LLMRefiner(llm: LLMEngine)`. Prompt registry keyed by `(lang, style)`.

### VerifierEngine

```python
class VerifierEngine(ABC):
    @abstractmethod
    def verify(
        self,
        primary_segments: list[Segment],
        secondary_words: list[Word],                    # secondary may give word-level instead of segment
        *,
        source_lang: str,
        custom_system_prompt: Optional[str] = None,
        progress: Optional[Callable] = None,
    ) -> list[Segment]:
        """Returns canonical source-lang segments aligned to primary's time boundaries."""
```

Concrete: `LLMVerifier(llm: LLMEngine)`. Alignment helper inside the class: for each primary segment time range, collect secondary words whose midpoint falls inside; concatenate; send both to LLM judge.

---

## §5. Stage Classes

All stages implement a common `PipelineStage` ABC (carried over from v4):

```python
class PipelineStage(ABC):
    stage_type: str
    @abstractmethod
    def run(self, ctx: PipelineContext) -> StageOutput: ...
```

### ASRPrimaryStage / ASRSecondaryStage

Both delegate to a `TranscribeEngine` instance loaded from the profile.

```python
class ASRPrimaryStage(PipelineStage):
    stage_type = "asr_primary"

    def run(self, ctx):
        engine = create_transcribe_engine(self.profile)
        segments = engine.transcribe(
            ctx.audio_path,
            source_lang=ctx.pipeline.asr_primary.source_lang,
            word_timestamps=True,
            progress=ctx.progress_callback,
        )
        return StageOutput(segments=segments, language=ctx.source_lang)
```

`ASRSecondaryStage` differs only in profile source and stage_type name. Both stages can run in parallel via `concurrent.futures.ThreadPoolExecutor` when CPU/GPU resources allow.

### ASRVerifierStage

```python
class ASRVerifierStage(PipelineStage):
    stage_type = "asr_verifier"

    def run(self, ctx):
        primary = ctx.stage_outputs["asr_primary"].segments
        secondary = ctx.stage_outputs["asr_secondary"].words
        engine = create_verifier_engine(self.profile)
        verified = engine.verify(
            primary, secondary,
            source_lang=ctx.source_lang,
            custom_system_prompt=ctx.file_overrides.get("verifier"),
            progress=ctx.progress_callback,
        )
        return StageOutput(segments=verified)
```

When `asr_secondary` is null, this stage is skipped and `asr_primary` output flows directly into the next stage.

### RefinerStage (per lang)

```python
class RefinerStage(PipelineStage):
    stage_type = "refiner"
    lang: str            # e.g., "zh"

    def run(self, ctx):
        source_segs = ctx.by_lang.get(self.lang) or ctx.canonical_source_segments
        engine = create_refiner_engine(self.profile)
        refined = engine.refine(
            source_segs,
            lang=self.lang,
            style=self.profile.style,
            glossary=ctx.glossary_for_lang(self.lang),
            custom_system_prompt=ctx.file_overrides.get("refiners", {}).get(self.lang),
            progress=ctx.progress_callback,
        )
        ctx.by_lang[self.lang] = refined
        return StageOutput(segments=refined, lang=self.lang)
```

### TranslatorStage (per target lang)

```python
class TranslatorStage(PipelineStage):
    stage_type = "translator"
    source_lang: str     # from pipeline.asr_primary.source_lang
    target_lang: str

    def run(self, ctx):
        source_segs = ctx.by_lang.get(self.source_lang) or ctx.canonical_source_segments
        engine = create_translator_engine(self.profile)
        translated = engine.translate(
            source_segs,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            glossary=ctx.glossary_for_pair(self.source_lang, self.target_lang),
            custom_system_prompt=(
                ctx.file_overrides
                   .get("translators", {})
                   .get(f"{self.source_lang}_to_{self.target_lang}")
            ),
            progress=ctx.progress_callback,
        )
        ctx.by_lang[self.target_lang] = translated
        return StageOutput(segments=translated, lang=self.target_lang)
```

### Stage executor changes vs v4

| Aspect | v4 | v5 |
|---|---|---|
| Stage iteration | Strict linear: `for stage in stages: ctx = stage.run(ctx)` | Topological DAG: ASR stages can run parallel; Translators per target lang fan out from canonical source |
| Output state | Single `segments` list mutated | `ctx.by_lang: Dict[str, list[Segment]]` keyed by language |
| Cancel propagation | `cancel_event` through stage.run kwargs | Unchanged |
| Progress reporting | 5% granularity per stage | Per-stage + per-lang sub-progress |

---

## §6. Prompt Override Resolution

Three layers, evaluated in order:

```
1. File-level override (per upload, transient)
   file_registry[fid].prompt_overrides = {
     refiners:    { zh: "...", en: "..." }
     translators: { "zh_to_en": "...", "zh_to_ja": "..." }
     verifier:    "..."
   }

2. Profile-level prompt (durable, reusable)
   refiner_profile.system_prompt
   translator_profile.system_prompt
   verifier_profile.prompt_template_id → resolves to template text

3. Engine default (hardcoded fallback)
   backend/translation/prompts/refiner_<lang>_<style>_default.txt
   backend/translation/prompts/translator_<src>_to_<tgt>_default.txt
   backend/translation/prompts/verifier_<lang>_default.txt
```

The Stage's `run()` method passes `custom_system_prompt=` to the engine. The engine resolves: `kwarg → profile config → default constant`.

### v3.18 backward compat

v3.18 introduced `prompt_overrides` on the file registry with 4 keys (`anchor`, `single`, `pass1`, `enrich`) targeting Ollama's MT pipeline. v5 expands the field shape:

```python
# v3.18 (legacy)
file.prompt_overrides = {
  "anchor": "...", "single": "...", "pass1": "...", "enrich": "..."
}

# v5
file.prompt_overrides = {
  # v5 keys
  "refiners":    Dict[lang, str],
  "translators": Dict[f"{src}_to_{tgt}", str],
  "verifier":    Optional[str],
  # v3.18 keys retained for backward compat during migration
  "anchor": str | None, "single": str | None,
  "pass1":  str | None, "enrich": str | None,
}
```

v3.18 keys are honored only when the pipeline is v4 (auto-promoted). v5 pipelines use only the new keys.

---

## §7. API Surface

### New + renamed endpoints

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/transcribe_profiles` | List/create (rename of `/api/asr_profiles` with backward-compat alias) |
| GET/PATCH/DELETE | `/api/transcribe_profiles/<id>` | Single CRUD |
| GET/POST | `/api/translator_profiles` | **NEW** — translator (cross-lingual) profiles |
| GET/PATCH/DELETE | `/api/translator_profiles/<id>` | Single CRUD |
| GET/POST | `/api/refiner_profiles` | **Rename of** `/api/mt_profiles`; semantic narrows to same-lingual polish |
| GET/PATCH/DELETE | `/api/refiner_profiles/<id>` | Single CRUD |
| GET/POST | `/api/verifier_profiles` | **NEW** — LLM-as-judge profile; mostly prompt template + model |
| GET/PATCH/DELETE | `/api/verifier_profiles/<id>` | Single CRUD |
| GET/POST | `/api/pipelines` | v4 P1 unchanged shape, runtime accepts both v4 and v5 schemas |
| GET/PATCH/DELETE | `/api/pipelines/<id>` | Single CRUD; PATCH validates v5 schema |
| POST | `/api/pipelines/<id>/run` | v4 unchanged trigger; runtime branches by schema version |

### Backward-compat aliases

To avoid breaking existing clients, the following aliases route to the new endpoints during the v5 migration window (single sub-phase, deprecated after v5-A3):

```
GET /api/asr_profiles      → GET /api/transcribe_profiles
GET /api/mt_profiles       → GET /api/refiner_profiles
```

POST/PATCH on the legacy path returns a 410 Gone with the new path in `error.suggest`.

### `/api/files/<id>/translations` response shape (multi-lang)

```jsonc
// v4 (current)
[{
  "idx": 0,
  "en_text": "...",
  "zh_text": "...",
  "status": "pending",
  "flags": ["long"]
}]

// v5
[{
  "idx": 0,
  "start": 0.0,
  "end": 4.5,
  "source_lang": "zh",
  "source_text": "...",                  // canonical (post-verifier) source
  "by_lang": {
    "zh": { "text": "...", "status": "pending", "flags": [] },
    "en": { "text": "...", "status": "approved", "flags": [] }
  }
}]
```

API also accepts an optional `?lang=<code>` query parameter that returns a v4-shaped response with the requested lang in `zh_text` slot — for clients not yet aware of multi-lang.

### `/api/files/<id>/subtitle.<fmt>?lang=<code>` (multi-lang export)

`lang` query param required when pipeline has multiple target languages; backend 400 with explicit error if missing in that case.

---

## §8. Frontend Changes

### Pipelines page — editor mockup

```
┌────────────────────────────────────────────────────────────────────┐
│ Pipeline: HK Broadcast (ZH + EN)                          [Save]   │
├────────────────────────────────────────────────────────────────────┤
│ ▼ ASR                                                              │
│   Primary:  Whisper large-v3   [profile dropdown ▼]               │
│   ☑ Secondary: Qwen3-ASR-1.7B  [profile dropdown ▼]               │
│   ☑ Verifier (LLM-as-judge)                                       │
│       Model: Ollama Qwen3.5-A35B  [LLM profile ▼]                 │
│       [Edit verifier prompt]                                      │
├────────────────────────────────────────────────────────────────────┤
│ ▼ Target Languages                                                 │
│                                                                    │
│   ┌─────────────────────────────────────────────────────┐        │
│   │ 🇨🇳 ZH 輸出 (source-lang)                           │        │
│   │   ☑ Refiner: broadcast-hk-v3   [profile ▼]         │        │
│   │       [Edit refiner prompt]                         │        │
│   │   ─ Translator: (source = target, skip)             │        │
│   │   Glossary: [zh-broadcast-v3 ▼] [+ add]            │        │
│   └─────────────────────────────────────────────────────┘        │
│                                                                    │
│   ┌─────────────────────────────────────────────────────┐        │
│   │ 🇬🇧 EN 輸出                                         │        │
│   │   ☐ Refiner (skip)                                  │        │
│   │   ☑ Translator: news-formal-v2  [profile ▼]        │        │
│   │       [Edit translator prompt]                      │        │
│   │   Cross-lingual glossary: [zh→en-jockey-names ▼]   │        │
│   └─────────────────────────────────────────────────────┘        │
│                                                                    │
│   [+ Add target language]                                          │
├────────────────────────────────────────────────────────────────────┤
│ ▼ Font Config (subtitle render)                                    │
│   [unchanged from v4]                                              │
└────────────────────────────────────────────────────────────────────┘
```

Implementation: replace v4's flat stage list (drag-sort @dnd-kit) with grouped sections. ASR section single-card, target-lang section multi-card. Backend schema serializes to the v5 shape.

### Proofread page — per-file override drawer

Extend v3.18's "自訂 Prompt" panel:

```
┌─ Per-file 自訂 Prompt ─────────────────────────────────────────┐
│  ASR:                                                          │
│   Verifier override     [textarea, default empty = use profile]│
│                                                                │
│  Refiner override per lang:                                    │
│   ZH (broadcast-hk)     [textarea]                            │
│                                                                │
│  Translator override per pair:                                 │
│   zh → en              [textarea]                             │
│                                                                │
│  Glossary apply for [target lang ▼] [Scan + Apply]            │
│                                                                │
│  [Save overrides]  [Clear all]  [Re-run pipeline]             │
└────────────────────────────────────────────────────────────────┘
```

### Render modal — target lang picker

```
Output language:  [ZH ▼]  (defaults to source_lang)
Format:           [MP4 ▼]
...
```

If user picks a `target_lang` that has zero approved translations, modal shows warning toast.

### Out of scope (frontend)

- Storybook for new components
- i18n of UI labels (English/Chinese mixed labels acceptable in v5)
- Responsive mobile layout for new pages (existing v4 responsive carries)

---

## §9. Migration Plan v4 → v5

### Backend auto-promote at pipeline read time

```python
def load_pipeline(data: dict) -> Pipeline:
    version = data.get("version", 4)
    if version == 4:
        data = promote_v4_to_v5(data)
    if data["version"] != 5:
        raise SchemaError(f"unsupported version {data['version']}")
    return Pipeline.from_dict(data)

def promote_v4_to_v5(v4: dict) -> dict:
    return {
        "id": v4["id"],
        "name": v4["name"],
        "version": 5,
        "user_id": v4.get("user_id"),
        "shared": v4.get("shared", False),
        "asr_primary": {
            "transcribe_profile_id": v4["asr_profile_id"],
            "source_lang": resolve_source_lang(v4),
        },
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": [resolve_target_lang(v4)],
        "refinements": {
            resolve_target_lang(v4): [
                {"refiner_profile_id": mt_profile_id}
                for mt_profile_id in v4.get("mt_stages", [])
            ],
        },
        "translators": {},               # legacy v4 conflated translation into mt_stages; treated as refiner only after promote
        "glossary_stages": {
            resolve_target_lang(v4): v4.get("glossary_stage", {}).get("glossary_ids", []),
        },
        "font_config": v4.get("font_config", {}),
    }
```

**Important caveat**: v4 `mt_stages` collapsed translator + refiner roles. The auto-promote routes them all to `refinements`, which keeps semantic safety (no info loss) but means v4 pipelines won't gain dual-ASR or true cross-lingual translation until a human edits them through the v5 UI. This is intentional — no automatic guess about which v4 mt_stage was "translation" vs "polish".

### File registry promote

The translations field is rewritten lazily at read time:

```python
def normalize_translations_for_v5(raw: list[dict]) -> list[dict]:
    """v4 [{en_text, zh_text}] → v5 [{by_lang: {...}}]"""
    if raw and "by_lang" in raw[0]:
        return raw            # already v5
    return [
        {
            "idx": t["idx"],
            "start": t.get("start"),
            "end": t.get("end"),
            "source_lang": "en",                     # v4 assumed EN source
            "source_text": t.get("en_text", ""),
            "by_lang": {
                "zh": {
                    "text": t.get("zh_text", ""),
                    "status": t.get("status", "pending"),
                    "flags": t.get("flags", []),
                },
            },
        }
        for t in raw
    ]
```

### Sub-phase rollout (recommended split)

**v5-A1** — Schema + engine ABCs + tests
- New profile manager classes (TranscribeProfileManager, TranslatorProfileManager, RefinerProfileManager, VerifierProfileManager)
- New REST endpoints + validators
- Engine ABCs + concrete classes (LLMEngine, LLMTranslator, LLMRefiner, LLMVerifier)
- TranscribeEngine refactor (factor out from app.py's existing Whisper code)
- Qwen3AsrTranscribeEngine adapter (wraps mlx-qwen3-asr; runs in subprocess due to py3.11 vs py3.9 split)
- Pipeline schema validator with promote logic
- Backend tests: ~80 new tests across profile managers, engines, schema migration

**v5-A2** — Stage executor refactor + pipeline runner integration
- PipelineRunner: linear → DAG executor
- New stage classes (ASRPrimaryStage, ASRSecondaryStage, ASRVerifierStage, RefinerStage, TranslatorStage)
- File registry translations multi-lang shape + lazy normalize
- Socket.IO events: per-lang sub-progress, stage type metadata
- Backend tests: ~40 new tests for stages + runner + integration

**v5-A3** — Frontend redesign + cleanup
- Pipelines page editor rewrite (target-lang card layout)
- Proofread page override drawer extension
- Render modal target-lang picker
- Multi-lang translations API client + UI
- Frontend tests: Vitest unit + Playwright E2E
- Legacy `/api/asr_profiles` + `/api/mt_profiles` alias removal at end of A3

---

## §10. Validation Evidence (from prototype)

### Prototype location

```
backend/scripts/v5_prototype/
├── llm_engine.py              # LLMEngine prototype
├── translator.py              # TranslatorEngine prototype
├── refiner.py                 # RefinerEngine prototype
├── prompts.py                 # Default prompts for all engine roles
├── verifier_prompt.py         # ASR Verifier system prompts (ZH + EN)
├── align_qwen_to_whisper.py   # Word-timestamp alignment helper
├── run_verifier.py            # Verifier runner (HK clip)
├── run_full_pipeline_v5.py    # End-to-end (HK clip)
├── winfactor_whisper.py       # Whisper EN transcribe (Winning Factor)
├── winfactor_qwen.py          # Qwen3-ASR EN transcribe
├── winfactor_e2e.py           # End-to-end (Winning Factor)
└── out/                       # HK clip outputs
└── out_winfactor/             # Winning Factor outputs
```

### Empirical results

**HK Cantonese clip** (`b9b9e4fad18c.mp4`, 261s, 97 Whisper segments):

| Metric | Single-ASR baseline | Dual-ASR + Verifier |
|---|---|---|
| First 28s coverage | 6 chars hallucination ("中文字幕提供") | 80+ chars real broadcast intro |
| Names correctly identified | 袁幸瑤 (wrong char), 美朗王 (wrong) | 袁幸堯 ✅, 美狼王 ✅, +鮑浩勇/姚本輝/賈西迪/Highland Bling newly recovered |
| ASR mistranscriptions fixed | 推期, 若瀚 untouched | 推騎 ✅, 弱項 ✅ |
| Race terminology | 大杯賽 (wrong) | 打比 (Derby) ✅ |
| Total LLM time (after dual ASR) | ~50s (single MT) | ~97s (verifier 47s + refine 23s + xlate 27s) |

**English Winning Factor clip** (`Jveoy3HsYMk.mp4`, 577s, 134 Whisper segments):

| Metric | v4 SRT (pre-v5) | V5 output |
|---|---|---|
| v3.18 black-list formulaic phrases | 7+ occurrences ("率先檢視", "致力尋找", "強勢回歸", "就此而言", "實為", "此乃", "真正") | 0 |
| Race-class naming | 「第三集」(error) | 「第三班」(HKJC standard) ✅ |
| Distance unit | 公尺 (Taiwan) | 米 (HK) ✅ |
| Show name recognition | dropped "The Winning Factor" | rendered 《致勝因素》 ✅ |
| Total wall time | n/a | 228s (4 min) |

**Refiner + Translator separation hypothesis (H1)**: confirmed — both clips show cleaner output with role separation than v4's combined-prompt baseline.

**Multi-target fan-out viability (H2)**: confirmed — second translator instance added ~25s for the same source segments (HK ZH→EN), well within "wait time isn't the concern" boundary.

**Dual-ASR cross-validation value (H3)**: confirmed for weak source languages (Cantonese), marginal for strong source languages (English). The architecture makes dual-ASR optional per pipeline so users pay only when needed.

### Known limitations surfaced by the prototype

1. **Long Whisper segments get long verifier output** — the 30-second first segment yields 80+ char verifier text, too long for one subtitle. Future: re-segmentation step using Qwen3 word timestamps.
2. **Translator hallucinates race-specific terminology** — "肯德百利" → "Kentucky Derby" (wrong race). Fix: cross-lingual glossary anchoring in v5-A1.
3. **Person names not anchored across translation** — "Alan Aitken" → "艾登" (drops surname). Fix: same glossary mechanism.
4. **Qwen3 English word tokens lack spaces** — alignment helper concatenates them; verifier LLM tolerates it, but alignment view shows uglily. Future: prefer Qwen3 chunk-level boundaries for English.

---

## §11. Out of Scope

- **SenseVoice as third ASR engine** — research-evaluated (Cantonese CER 7.09%, better than Qwen3 alone), but adding a third ASR doesn't improve the architecture; user can swap secondary later via profile config. Defer to post-v5.
- **Stage history per-lang trace UI** — v4 A4 already has a stage-history sidebar. v5 needs per-lang dimension but UI design is deferred until v5-A3.
- **Re-segmentation algorithm** — long segments from verifier need sub-splitting for broadcast subtitle length compliance (≤28 char per line). Out of v5 core scope; addressed by a future "RenderSegmenter" stage.
- **Cross-lingual glossary CRUD UI** — backend schema (v3.15 multilingual) is ready; v5 extends to translator-injected glossary. Full editor UI deferred to v5-A3 polish.
- **Streaming ASR** — out of scope; v5 remains file-based.
- **Public internet exposure / SaaS** — out of scope (v4 R5 LAN-only posture continues).
- **Mobile responsive for new v5 pages** — v4 responsive baseline applies; new pages get desktop-first.

---

## §12. Acceptance Criteria

### Schema + backend
- [ ] v5 pipeline schema validator passes pytest matrix (valid + invalid cases ~25 tests)
- [ ] `promote_v4_to_v5` round-trips existing 8+ v4 pipeline JSONs without semantic change
- [ ] All 5 engine ABCs have concrete implementations + ≥10 unit tests each
- [ ] Pipeline runner DAG executor passes 1 ASR / 2 ASR / verifier-on / verifier-off matrix

### Quality (regression bar)
- [ ] HK Cantonese clip end-to-end produces ZH + EN SRT files with at least the prototype quality (count formulaic phrases, count correctly-identified names — automated diff against `out/v5_combined.json`)
- [ ] English Winning Factor clip ZH output contains zero v3.18 black-list formulaic phrases (`真正`, `儘管`, `就此而言`, `然而`, `事實上`, `值得一提的是`, `傷病纏身`)
- [ ] All existing v4 pipeline JSONs auto-promote and run end-to-end producing matching v4 output

### API + frontend
- [ ] All new endpoints documented in CLAUDE.md
- [ ] Legacy `/api/asr_profiles` + `/api/mt_profiles` aliases work, return correct data; deprecation header set
- [ ] Pipelines page editor saves valid v5 schema
- [ ] Proofread page override drawer accepts new field shape
- [ ] Render modal target-lang picker shows ≥1 lang option for every saved v5 pipeline

### Tests + CI
- [ ] Pytest: ≥80 new tests in v5-A1, ≥40 in v5-A2, ≥30 in v5-A3
- [ ] Vitest: ≥40 new unit tests in v5-A3
- [ ] Playwright: ≥5 new E2E in v5-A3 covering pipeline create / per-file override / multi-lang export
- [ ] Backward compat: all v4 tests still green

### Validation gates
- [ ] Empirical re-run of HK clip + Winning Factor clip post-impl produces outputs within ±10% of prototype quality metrics
- [ ] User sign-off on v5 sample SRT output before A3 merges to main

---

## §13. References

- [v4.0 design](2026-05-16-asr-mt-emergent-pipeline-design.md) — pipeline runner, stage executor base
- [v3.18 stage 2 prompt design](2026-05-15-stage2-prompt-override-design.md) — prompt overrides + formulaic phrase research
- [v3.15 multilingual glossary](2026-05-12-multilingual-glossary-design.md) — `source_lang` / `target_lang` schema reused
- [v3.8 OpenCC s2hk](../../../backend/asr/cn_convert.py) — same converter used in Qwen3-ASR output normalization
- Prototype outputs: [backend/scripts/v5_prototype/](../../../backend/scripts/v5_prototype/)
- Qwen3-ASR MLX port: https://github.com/moona3k/mlx-qwen3-asr
- mlx-whisper (existing): https://github.com/ml-explore/mlx-examples/tree/main/whisper
- RECOVER (LLM-as-judge ASR ensemble): arXiv 2603.16411
- N-best LLM rescoring: arXiv 2406.18972

---

**End of spec.**
