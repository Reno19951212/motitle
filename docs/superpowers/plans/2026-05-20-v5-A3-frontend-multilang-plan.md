# v5-A3 Frontend Multi-Lang UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the React frontend to consume the v5-A2 multi-lang backend — 5 new v5 profile CRUD pages, a per-target-lang Pipelines editor, a Proofread page that displays + edits multiple target-lang outputs, a Render modal that picks which lang to burn into video.

**Architecture:** Add 3 brand-new pages (LLMProfiles / TranslatorProfiles / VerifierProfiles) following the v4 Bold-shell pattern. Rename + extend 2 existing pages (AsrProfiles → TranscribeProfiles with `qwen3-asr` engine; MtProfiles → RefinerProfiles with narrowed same-lingual semantics). Rewrite Pipelines.tsx with a per-target-lang card layout replacing v4's flat stage list. Extend Proofread's `useFileData` hook to consume `?shape=v5` and extend the override drawer with per-lang refiner + per-pair translator textareas. Add target-lang picker to RenderModal. End A3 with a single commit that removes the legacy `/api/asr_profiles` + `/api/mt_profiles` route entries (replaced by v5 transcribe + refiner routes).

**Tech Stack:** Vite + React 18 + TypeScript strict (`noUncheckedIndexedAccess`); Zustand 5.0 + React Router 6.27; shadcn/ui (copy-in) + Tailwind 3.4; react-hook-form 7.53 + zod 3.23 (mirror backend validators); @dnd-kit 6.1 (drag-sort, kept from v4); react-dropzone 14.3 (kept); socket.io-client 4.8 (kept); Vitest 2.1 unit + Playwright 1.48 E2E.

**Parent spec:** `docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md` §8 (Frontend) + §9 (Migration phase split A3 scope)

**A1+A2 foundation (frozen — do NOT modify any backend):**
- 5 v5 REST blueprints (`/api/{llm,transcribe,translator,refiner,verifier}_profiles`) — all CRUD endpoints ready
- `POST /api/pipelines` accepts v5 schema (`{version: 5, asr_primary, asr_secondary?, asr_verifier?, target_languages, refinements, translators, glossary_stages, font_config}`)
- `POST /api/pipelines/<pid>/run` triggers v5 DAG executor (works end-to-end — verified live on HK clip)
- `GET /api/files/<id>/translations?shape=v5` returns `[{by_lang: {lang: {text, status, flags}}}]`
- Default `GET /api/files/<id>/translations` (no shape) returns v4 downgrade — frontend can switch over to `?shape=v5` at its own pace
- `/api/asr_profiles` + `/api/mt_profiles` legacy aliases continue to work with `Deprecation: true` header (removed in T10 of this plan)

**Branch:** continue on `feat/frontend-redesign` (A1+A2 already landed there — 44 commits).

---

## File Structure

### New files (created by this plan)

| Path | Responsibility |
|---|---|
| `frontend/src/lib/schemas/llm-profile.ts` | `LlmProfileSchema` + `LLM_BACKENDS` constant |
| `frontend/src/lib/schemas/transcribe-profile.ts` | `TranscribeProfileSchema` + `TRANSCRIBE_ENGINES` (incl. qwen3-asr) |
| `frontend/src/lib/schemas/translator-profile.ts` | `TranslatorProfileSchema` (source_lang != target_lang refine) |
| `frontend/src/lib/schemas/refiner-profile.ts` | `RefinerProfileSchema` |
| `frontend/src/lib/schemas/verifier-profile.ts` | `VerifierProfileSchema` |
| `frontend/src/lib/schemas/pipeline-v5.ts` | `PipelineV5Schema` (mirrors backend pipeline_schema_v5.py) |
| `frontend/src/lib/api/v5.ts` | Typed API helpers — `getLlmProfiles()`, `createLlmProfile()`, etc. (one per CRUD × 5 profile types + 1 v5 pipeline) |
| `frontend/src/pages/LLMProfiles.tsx` | LLM profile CRUD page (pattern setter — new entity) |
| `frontend/src/pages/TranslatorProfiles.tsx` | Translator profile CRUD (new) |
| `frontend/src/pages/VerifierProfiles.tsx` | Verifier profile CRUD (new) |
| `frontend/src/pages/TranscribeProfiles.tsx` | Replaces AsrProfiles.tsx (rename + add `qwen3-asr` engine) |
| `frontend/src/pages/RefinerProfiles.tsx` | Replaces MtProfiles.tsx (rename + narrow to same-lingual) |
| `frontend/src/pages/Proofread/TargetLangTabs.tsx` | Tab switcher between target langs in proofread page |
| `frontend/src/lib/schemas/llm-profile.test.ts` | Zod schema unit tests |
| `frontend/src/lib/schemas/transcribe-profile.test.ts` | Same shape |
| `frontend/src/lib/schemas/translator-profile.test.ts` | Same shape |
| `frontend/src/lib/schemas/refiner-profile.test.ts` | Same shape |
| `frontend/src/lib/schemas/verifier-profile.test.ts` | Same shape |
| `frontend/src/lib/schemas/pipeline-v5.test.ts` | v5 pipeline schema tests (mirror backend cross-field rules) |
| `frontend/src/lib/api/v5.test.ts` | API client mock tests |
| `frontend/tests-e2e/v5-profile-crud.spec.ts` | Playwright: create all 5 v5 profiles → assert visibility |
| `frontend/tests-e2e/v5-pipeline-builder.spec.ts` | Playwright: build v5 pipeline + multi-lang config |
| `frontend/tests-e2e/v5-proofread-multilang.spec.ts` | Playwright: load file with by_lang shape → switch target lang tabs |

### Modified files

| Path | Change |
|---|---|
| `frontend/src/pages/Pipelines.tsx` | Full rewrite — v4 flat stage list → v5 per-target-lang card layout |
| `frontend/src/pages/Proofread/index.tsx` | Add target-lang tab switcher; extended override drawer panels |
| `frontend/src/pages/Proofread/hooks/useFileData.ts` | Pass `?shape=v5` to translations fetch; type for v5 by_lang shape |
| `frontend/src/pages/Proofread/RenderModal.tsx` | Add target-lang picker (which lang to burn into output) |
| `frontend/src/router.tsx` | Add 3 new routes (`/llm_profiles`, `/translator_profiles`, `/verifier_profiles`); rename routes `/asr_profiles` → `/transcribe_profiles` + `/mt_profiles` → `/refiner_profiles` |
| `frontend/src/components/BoldRail.tsx` | Add 3 new rail entries (LLM/Translator/Verifier); rename ASR → Transcribe, MT → Refiner |
| `frontend/src/pages/Proofread/types.ts` | Add `V5Translation` interface alongside existing v4 `Translation` |
| `backend/routes/asr_profiles.py` | T10 only — remove file (legacy alias retired) |
| `backend/routes/mt_profiles.py` | T10 only — remove file (legacy alias retired) |
| `backend/bootstrap.py` | T10 only — drop the 2 legacy blueprint registrations |
| `CLAUDE.md` | T10 only — add v5-A3 progress entry above v5-A2 |

### Files NOT touched

- `backend/{llm,transcribe,translator,refiner,verifier}_profiles.py` — v5-A1 managers frozen
- `backend/routes/{llm,transcribe,translator,refiner,verifier}_profiles.py` — v5-A1 routes frozen
- `backend/pipeline_runner.py` — v5-A2 frozen
- `backend/stages/v5/*` — v5-A2 frozen
- `backend/pipeline_schema_v5.py` — v5-A1 frozen
- `backend/translations_normalize_v5.py` — v5-A2 frozen
- `backend/engines/*` — v5-A1 frozen
- Existing v4 frontend pages NOT touched in A3 except renamed (AsrProfiles → TranscribeProfiles, MtProfiles → RefinerProfiles)

---

## Task index

| # | Task | Phase |
|---|---|---|
| T1 | zod schemas — 5 v5 profile + v5 Pipeline | 1 — Schemas |
| T2 | API client v5 helpers (`lib/api/v5.ts`) | 1 — API |
| T3 | LLMProfiles page (pattern setter for 4 more) | 2 — Pages |
| T4 | TranscribeProfiles page (rename of AsrProfiles + qwen3-asr) | 2 — Pages |
| T5 | TranslatorProfiles page (NEW) | 2 — Pages |
| T6 | RefinerProfiles page (rename of MtProfiles + narrow) | 2 — Pages |
| T7 | VerifierProfiles page (NEW) | 2 — Pages |
| T8 | Pipelines page rewrite (per-target-lang card) | 3 — Pipelines |
| T9 | Proofread extensions (useFileData shape=v5 + target-lang tabs + override drawer) | 4 — Proofread |
| T10 | RenderModal target-lang picker + Router/BoldRail wiring + Playwright E2E + legacy alias retirement + CLAUDE.md | 5 — Wrap-up |

---

## Phase 1 — Schemas + API

### Task 1: zod schemas — 5 v5 profile + v5 Pipeline

**Files:**
- Create: `frontend/src/lib/schemas/llm-profile.ts` + `.test.ts`
- Create: `frontend/src/lib/schemas/transcribe-profile.ts` + `.test.ts`
- Create: `frontend/src/lib/schemas/translator-profile.ts` + `.test.ts`
- Create: `frontend/src/lib/schemas/refiner-profile.ts` + `.test.ts`
- Create: `frontend/src/lib/schemas/verifier-profile.ts` + `.test.ts`
- Create: `frontend/src/lib/schemas/pipeline-v5.ts` + `.test.ts`

Mirror the backend validators 1:1 so client-side validation catches errors before POST. The shapes match exactly what `validate_*_profile()` in `backend/*.py` checks.

- [ ] **Step 1: Write the 5 profile schema files**

Create `frontend/src/lib/schemas/llm-profile.ts`:
```typescript
import { z } from 'zod';

export const LLM_BACKENDS = ['ollama', 'openrouter', 'claude'] as const;

export const LlmProfileSchema = z.object({
  name: z.string().min(1).max(64),
  backend: z.enum(LLM_BACKENDS),
  model: z.string().min(1),
  base_url: z.string().url(),
  temperature: z.number().min(0).max(2).default(0.2),
  shared: z.boolean().default(false),
  api_key: z.string().optional(),
});

export type LlmProfile = z.infer<typeof LlmProfileSchema>;

export interface LlmProfileRow extends LlmProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
```

Create `frontend/src/lib/schemas/transcribe-profile.ts`:
```typescript
import { z } from 'zod';

export const TRANSCRIBE_ENGINES = ['whisper', 'mlx-whisper', 'qwen3-asr'] as const;
export const TRANSCRIBE_LANGUAGES = ['en', 'zh', 'ja', 'ko', 'yue', 'fr', 'de', 'es', 'th', 'auto'] as const;

export const TranscribeProfileSchema = z.object({
  name: z.string().min(1).max(64),
  engine: z.enum(TRANSCRIBE_ENGINES),
  language: z.enum(TRANSCRIBE_LANGUAGES).default('auto'),
  model_size: z.string().optional(),
  initial_prompt: z.string().max(512).optional(),
  shared: z.boolean().default(false),
});

export type TranscribeProfile = z.infer<typeof TranscribeProfileSchema>;

export interface TranscribeProfileRow extends TranscribeProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
```

Create `frontend/src/lib/schemas/translator-profile.ts`:
```typescript
import { z } from 'zod';

export const TRANSLATOR_LANGS = ['en', 'zh', 'ja', 'ko', 'yue', 'fr', 'de', 'es', 'th'] as const;

export const TranslatorProfileSchema = z.object({
  name: z.string().min(1).max(64),
  source_lang: z.enum(TRANSLATOR_LANGS),
  target_lang: z.enum(TRANSLATOR_LANGS),
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
  shared: z.boolean().default(false),
}).refine(
  (data) => data.source_lang !== data.target_lang,
  { message: 'source_lang and target_lang must differ (use Refiner for same-lang polish)', path: ['target_lang'] },
);

export type TranslatorProfile = z.infer<typeof TranslatorProfileSchema>;

export interface TranslatorProfileRow extends TranslatorProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
```

Create `frontend/src/lib/schemas/refiner-profile.ts`:
```typescript
import { z } from 'zod';
import { TRANSLATOR_LANGS } from './translator-profile';

export const REFINER_LANGS = TRANSLATOR_LANGS;

export const RefinerProfileSchema = z.object({
  name: z.string().min(1).max(64),
  lang: z.enum(REFINER_LANGS),
  style: z.string().min(1),
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
  shared: z.boolean().default(false),
});

export type RefinerProfile = z.infer<typeof RefinerProfileSchema>;

export interface RefinerProfileRow extends RefinerProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
```

Create `frontend/src/lib/schemas/verifier-profile.ts`:
```typescript
import { z } from 'zod';
import { TRANSLATOR_LANGS } from './translator-profile';

export const VERIFIER_LANGS = TRANSLATOR_LANGS;

export const VerifierProfileSchema = z.object({
  name: z.string().min(1).max(64),
  lang: z.enum(VERIFIER_LANGS),
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
  shared: z.boolean().default(false),
});

export type VerifierProfile = z.infer<typeof VerifierProfileSchema>;

export interface VerifierProfileRow extends VerifierProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
```

- [ ] **Step 2: Write the v5 Pipeline schema file**

Create `frontend/src/lib/schemas/pipeline-v5.ts`:
```typescript
import { z } from 'zod';
import { TRANSLATOR_LANGS } from './translator-profile';

export const PIPELINE_V5_LANGS = TRANSLATOR_LANGS;

const FontConfigSchema = z.object({
  family: z.string().min(1),
  color: z.string().min(1),
  outline_color: z.string().min(1),
});

const AsrPrimarySchema = z.object({
  transcribe_profile_id: z.string().min(1),
  source_lang: z.enum(PIPELINE_V5_LANGS),
});

const AsrSecondarySchema = z.object({
  transcribe_profile_id: z.string().min(1),
  source_lang: z.enum(PIPELINE_V5_LANGS),
}).nullable();

const AsrVerifierSchema = z.object({
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
}).nullable();

const RefinementEntrySchema = z.object({
  refiner_profile_id: z.string().min(1),
});

const TranslatorEntrySchema = z.object({
  translator_profile_id: z.string().min(1),
});

export const PipelineV5Schema = z.object({
  name: z.string().min(1).max(64),
  version: z.literal(5),
  asr_primary: AsrPrimarySchema,
  asr_secondary: AsrSecondarySchema,
  asr_verifier: AsrVerifierSchema,
  target_languages: z.array(z.enum(PIPELINE_V5_LANGS)).min(1),
  refinements: z.record(z.string(), z.array(RefinementEntrySchema)),
  translators: z.record(z.string(), TranslatorEntrySchema),
  glossary_stages: z.record(z.string(), z.array(z.string())).optional().default({}),
  font_config: FontConfigSchema,
  shared: z.boolean().default(false),
}).refine(
  (data) => {
    // asr_secondary.source_lang must equal asr_primary.source_lang
    if (data.asr_secondary && data.asr_secondary.source_lang !== data.asr_primary.source_lang) {
      return false;
    }
    return true;
  },
  { message: 'asr_secondary.source_lang must equal asr_primary.source_lang', path: ['asr_secondary'] },
).refine(
  (data) => {
    // refinements keys must be subset of target_languages
    for (const lang of Object.keys(data.refinements)) {
      if (!data.target_languages.includes(lang as typeof data.target_languages[number])) {
        return false;
      }
    }
    return true;
  },
  { message: 'refinements keys must appear in target_languages', path: ['refinements'] },
).refine(
  (data) => {
    // translators[lang] required for every target_lang != source_lang
    const source = data.asr_primary.source_lang;
    for (const lang of data.target_languages) {
      if (lang !== source && !(lang in data.translators)) {
        return false;
      }
    }
    return true;
  },
  { message: 'translators required for every non-source target language', path: ['translators'] },
);

export type PipelineV5 = z.infer<typeof PipelineV5Schema>;

export interface PipelineV5Row extends PipelineV5 {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
```

- [ ] **Step 3: Write the 6 test files**

Create `frontend/src/lib/schemas/llm-profile.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { LlmProfileSchema } from './llm-profile';

describe('LlmProfileSchema', () => {
  it('accepts valid ollama profile', () => {
    const result = LlmProfileSchema.safeParse({
      name: 'Test',
      backend: 'ollama',
      model: 'qwen3.5:9b',
      base_url: 'http://localhost:11434',
      temperature: 0.2,
    });
    expect(result.success).toBe(true);
  });

  it('rejects unknown backend', () => {
    const result = LlmProfileSchema.safeParse({
      name: 'x',
      backend: 'bogus',
      model: 'm',
      base_url: 'http://x',
    });
    expect(result.success).toBe(false);
  });

  it('rejects bad base_url', () => {
    const result = LlmProfileSchema.safeParse({
      name: 'x',
      backend: 'ollama',
      model: 'm',
      base_url: 'not-a-url',
    });
    expect(result.success).toBe(false);
  });

  it('rejects temperature out of range', () => {
    const result = LlmProfileSchema.safeParse({
      name: 'x',
      backend: 'ollama',
      model: 'm',
      base_url: 'http://x',
      temperature: 5,
    });
    expect(result.success).toBe(false);
  });
});
```

Create `frontend/src/lib/schemas/transcribe-profile.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { TranscribeProfileSchema } from './transcribe-profile';

describe('TranscribeProfileSchema', () => {
  it('accepts qwen3-asr engine', () => {
    const result = TranscribeProfileSchema.safeParse({
      name: 'qwen3',
      engine: 'qwen3-asr',
      language: 'zh',
    });
    expect(result.success).toBe(true);
  });

  it('accepts whisper engine', () => {
    const result = TranscribeProfileSchema.safeParse({
      name: 'whisper',
      engine: 'whisper',
      language: 'en',
      model_size: 'large-v3',
    });
    expect(result.success).toBe(true);
  });

  it('rejects unknown engine', () => {
    const result = TranscribeProfileSchema.safeParse({
      name: 'x',
      engine: 'bogus',
      language: 'en',
    });
    expect(result.success).toBe(false);
  });

  it('rejects initial_prompt over 512 chars', () => {
    const result = TranscribeProfileSchema.safeParse({
      name: 'x',
      engine: 'whisper',
      language: 'en',
      initial_prompt: 'x'.repeat(513),
    });
    expect(result.success).toBe(false);
  });
});
```

Create `frontend/src/lib/schemas/translator-profile.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { TranslatorProfileSchema } from './translator-profile';

describe('TranslatorProfileSchema', () => {
  it('accepts zh→en', () => {
    const result = TranslatorProfileSchema.safeParse({
      name: 'zh-to-en',
      source_lang: 'zh',
      target_lang: 'en',
      llm_profile_id: 'llm-id',
      prompt_template_id: 'translator/zh_to_en_default',
    });
    expect(result.success).toBe(true);
  });

  it('rejects same source and target', () => {
    const result = TranslatorProfileSchema.safeParse({
      name: 'bad',
      source_lang: 'zh',
      target_lang: 'zh',
      llm_profile_id: 'x',
      prompt_template_id: 'y',
    });
    expect(result.success).toBe(false);
  });

  it('rejects missing llm_profile_id', () => {
    const result = TranslatorProfileSchema.safeParse({
      name: 'x',
      source_lang: 'zh',
      target_lang: 'en',
      llm_profile_id: '',
      prompt_template_id: 'y',
    });
    expect(result.success).toBe(false);
  });
});
```

Create `frontend/src/lib/schemas/refiner-profile.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { RefinerProfileSchema } from './refiner-profile';

describe('RefinerProfileSchema', () => {
  it('accepts zh broadcast-hk', () => {
    const result = RefinerProfileSchema.safeParse({
      name: 'zh-broadcast',
      lang: 'zh',
      style: 'broadcast-hk',
      llm_profile_id: 'llm-id',
      prompt_template_id: 'refiner/zh_broadcast_hk_default',
    });
    expect(result.success).toBe(true);
  });

  it('rejects missing style', () => {
    const result = RefinerProfileSchema.safeParse({
      name: 'x',
      lang: 'zh',
      style: '',
      llm_profile_id: 'x',
      prompt_template_id: 'y',
    });
    expect(result.success).toBe(false);
  });
});
```

Create `frontend/src/lib/schemas/verifier-profile.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { VerifierProfileSchema } from './verifier-profile';

describe('VerifierProfileSchema', () => {
  it('accepts zh verifier', () => {
    const result = VerifierProfileSchema.safeParse({
      name: 'zh-verifier',
      lang: 'zh',
      llm_profile_id: 'llm-id',
      prompt_template_id: 'verifier/zh_default',
    });
    expect(result.success).toBe(true);
  });

  it('rejects unknown lang', () => {
    const result = VerifierProfileSchema.safeParse({
      name: 'x',
      lang: 'klingon',
      llm_profile_id: 'x',
      prompt_template_id: 'y',
    });
    expect(result.success).toBe(false);
  });
});
```

Create `frontend/src/lib/schemas/pipeline-v5.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { PipelineV5Schema } from './pipeline-v5';

const VALID_MINIMAL = {
  name: 'test',
  version: 5 as const,
  asr_primary: { transcribe_profile_id: 'tp1', source_lang: 'zh' as const },
  asr_secondary: null,
  asr_verifier: null,
  target_languages: ['zh' as const],
  refinements: { zh: [] },
  translators: {},
  glossary_stages: {},
  font_config: { family: 'Noto Sans TC', color: 'white', outline_color: 'black' },
};

describe('PipelineV5Schema', () => {
  it('accepts minimal valid v5 pipeline (source-lang only target)', () => {
    const result = PipelineV5Schema.safeParse(VALID_MINIMAL);
    expect(result.success).toBe(true);
  });

  it('rejects refinements key not in target_languages', () => {
    const result = PipelineV5Schema.safeParse({
      ...VALID_MINIMAL,
      refinements: { zh: [], ja: [] },
    });
    expect(result.success).toBe(false);
  });

  it('rejects asr_secondary lang mismatch', () => {
    const result = PipelineV5Schema.safeParse({
      ...VALID_MINIMAL,
      asr_secondary: { transcribe_profile_id: 'tp2', source_lang: 'en' as const },
    });
    expect(result.success).toBe(false);
  });

  it('rejects missing translator for non-source target', () => {
    const result = PipelineV5Schema.safeParse({
      ...VALID_MINIMAL,
      target_languages: ['zh' as const, 'en' as const],
      refinements: { zh: [], en: [] },
      translators: {},  // missing 'en' entry
    });
    expect(result.success).toBe(false);
  });

  it('accepts ZH + EN with translator', () => {
    const result = PipelineV5Schema.safeParse({
      ...VALID_MINIMAL,
      target_languages: ['zh' as const, 'en' as const],
      refinements: { zh: [], en: [] },
      translators: { en: { translator_profile_id: 'tr1' } },
    });
    expect(result.success).toBe(true);
  });
});
```

- [ ] **Step 4: Run all schema tests**

```bash
cd frontend && npm run test -- src/lib/schemas/ 2>&1 | tail -20
```
Expected: All schema test files pass (5 profile × ~3-4 tests + 5 pipeline tests = ~20 tests).

- [ ] **Step 5: Commit T1**

```bash
git add frontend/src/lib/schemas/
git commit -m "feat(v5-a3): zod schemas for 5 v5 profile types + v5 Pipeline

Mirror backend validators in pipeline_schema_v5.py + 5 *_profiles.py:
- LlmProfileSchema (ollama/openrouter/claude backends)
- TranscribeProfileSchema (whisper/mlx-whisper/qwen3-asr engines)
- TranslatorProfileSchema (source_lang != target_lang refine)
- RefinerProfileSchema (same-lingual polish)
- VerifierProfileSchema (LLM-as-judge)
- PipelineV5Schema (3 cross-field rules: target_languages includes
  refinements keys; asr_secondary lang matches primary; translators
  required for non-source targets)

~20 new vitest cases."
```

---

### Task 2: API client v5 helpers

**Files:**
- Create: `frontend/src/lib/api/v5.ts`
- Create: `frontend/src/lib/api/v5.test.ts`

Centralize the 30 v5 REST calls (5 entity types × 5 endpoints + 1 pipeline create + 1 pipeline run + 1 translations fetch) into a typed wrapper. Pages don't need to know the URL paths or query param conventions.

- [ ] **Step 1: Inspect existing `lib/api.ts`** for the established pattern

```bash
cat frontend/src/lib/api.ts | head -40
```

The existing `apiFetch(path, init)` wrapper handles cookies + JSON parsing. v5 helpers build on top of it.

- [ ] **Step 2: Write failing test**

Create `frontend/src/lib/api/v5.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as v5 from './v5';

describe('v5 API client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getLlmProfiles fetches /api/llm_profiles', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ profiles: [] }),
    });
    const profiles = await v5.getLlmProfiles();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/llm_profiles',
      expect.objectContaining({ credentials: 'include' }),
    );
    expect(profiles).toEqual([]);
  });

  it('createTranscribeProfile POSTs to /api/transcribe_profiles', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'tp1', name: 'test' }),
    });
    const profile = await v5.createTranscribeProfile({
      name: 'test',
      engine: 'whisper',
      language: 'en',
      shared: false,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcribe_profiles',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
    expect(profile.id).toBe('tp1');
  });

  it('getTranslations passes ?shape=v5 query', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ translations: [] }),
    });
    await v5.getTranslations('file-id');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/files/file-id/translations?shape=v5',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('runPipeline POSTs to /api/pipelines/<id>/run with file_id body', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ job_id: 'abc' }),
    });
    const out = await v5.runPipeline('pipe-id', 'file-id');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/pipelines/pipe-id/run',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ file_id: 'file-id' }),
      }),
    );
    expect(out.job_id).toBe('abc');
  });

  it('throws on non-ok HTTP', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ error: 'validation failed' }),
    });
    await expect(v5.getLlmProfiles()).rejects.toThrow(/validation failed/);
  });
});
```

- [ ] **Step 3: Run test fail**

```bash
cd frontend && npm run test -- src/lib/api/v5.test.ts 2>&1 | tail -5
```
Expected: FAIL — `Cannot find module './v5'`.

- [ ] **Step 4: Create `frontend/src/lib/api/v5.ts`**

```typescript
/**
 * v5 API client — typed wrappers around the 5 v5 REST resources + v5 pipeline.
 *
 * All calls go through fetch() with credentials:'include' so the session cookie
 * is sent. Non-ok responses raise an Error with the server-provided message.
 */
import type {
  LlmProfile, LlmProfileRow,
} from '@/lib/schemas/llm-profile';
import type {
  TranscribeProfile, TranscribeProfileRow,
} from '@/lib/schemas/transcribe-profile';
import type {
  TranslatorProfile, TranslatorProfileRow,
} from '@/lib/schemas/translator-profile';
import type {
  RefinerProfile, RefinerProfileRow,
} from '@/lib/schemas/refiner-profile';
import type {
  VerifierProfile, VerifierProfileRow,
} from '@/lib/schemas/verifier-profile';
import type {
  PipelineV5, PipelineV5Row,
} from '@/lib/schemas/pipeline-v5';

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'include', ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

async function jsonPost<T>(path: string, body: unknown): Promise<T> {
  return fetchJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function jsonPatch<T>(path: string, body: unknown): Promise<T> {
  return fetchJson<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function httpDelete<T>(path: string): Promise<T> {
  return fetchJson<T>(path, { method: 'DELETE' });
}

// ============================================================
// LLM Profile CRUD
// ============================================================

export async function getLlmProfiles(): Promise<LlmProfileRow[]> {
  const r = await fetchJson<{ profiles: LlmProfileRow[] }>('/api/llm_profiles');
  return r.profiles;
}

export async function createLlmProfile(p: LlmProfile): Promise<LlmProfileRow> {
  return jsonPost('/api/llm_profiles', p);
}

export async function updateLlmProfile(id: string, patch: Partial<LlmProfile>): Promise<LlmProfileRow> {
  return jsonPatch(`/api/llm_profiles/${id}`, patch);
}

export async function deleteLlmProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete(`/api/llm_profiles/${id}`);
}

// ============================================================
// Transcribe Profile CRUD
// ============================================================

export async function getTranscribeProfiles(): Promise<TranscribeProfileRow[]> {
  const r = await fetchJson<{ profiles: TranscribeProfileRow[] }>('/api/transcribe_profiles');
  return r.profiles;
}

export async function createTranscribeProfile(p: TranscribeProfile): Promise<TranscribeProfileRow> {
  return jsonPost('/api/transcribe_profiles', p);
}

export async function updateTranscribeProfile(id: string, patch: Partial<TranscribeProfile>): Promise<TranscribeProfileRow> {
  return jsonPatch(`/api/transcribe_profiles/${id}`, patch);
}

export async function deleteTranscribeProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete(`/api/transcribe_profiles/${id}`);
}

// ============================================================
// Translator Profile CRUD
// ============================================================

export async function getTranslatorProfiles(): Promise<TranslatorProfileRow[]> {
  const r = await fetchJson<{ profiles: TranslatorProfileRow[] }>('/api/translator_profiles');
  return r.profiles;
}

export async function createTranslatorProfile(p: TranslatorProfile): Promise<TranslatorProfileRow> {
  return jsonPost('/api/translator_profiles', p);
}

export async function updateTranslatorProfile(id: string, patch: Partial<TranslatorProfile>): Promise<TranslatorProfileRow> {
  return jsonPatch(`/api/translator_profiles/${id}`, patch);
}

export async function deleteTranslatorProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete(`/api/translator_profiles/${id}`);
}

// ============================================================
// Refiner Profile CRUD
// ============================================================

export async function getRefinerProfiles(): Promise<RefinerProfileRow[]> {
  const r = await fetchJson<{ profiles: RefinerProfileRow[] }>('/api/refiner_profiles');
  return r.profiles;
}

export async function createRefinerProfile(p: RefinerProfile): Promise<RefinerProfileRow> {
  return jsonPost('/api/refiner_profiles', p);
}

export async function updateRefinerProfile(id: string, patch: Partial<RefinerProfile>): Promise<RefinerProfileRow> {
  return jsonPatch(`/api/refiner_profiles/${id}`, patch);
}

export async function deleteRefinerProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete(`/api/refiner_profiles/${id}`);
}

// ============================================================
// Verifier Profile CRUD
// ============================================================

export async function getVerifierProfiles(): Promise<VerifierProfileRow[]> {
  const r = await fetchJson<{ profiles: VerifierProfileRow[] }>('/api/verifier_profiles');
  return r.profiles;
}

export async function createVerifierProfile(p: VerifierProfile): Promise<VerifierProfileRow> {
  return jsonPost('/api/verifier_profiles', p);
}

export async function updateVerifierProfile(id: string, patch: Partial<VerifierProfile>): Promise<VerifierProfileRow> {
  return jsonPatch(`/api/verifier_profiles/${id}`, patch);
}

export async function deleteVerifierProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete(`/api/verifier_profiles/${id}`);
}

// ============================================================
// v5 Pipeline + runs
// ============================================================

export async function createPipelineV5(p: PipelineV5): Promise<PipelineV5Row> {
  return jsonPost('/api/pipelines', p);
}

export async function runPipeline(pipelineId: string, fileId: string): Promise<{ job_id: string }> {
  return jsonPost(`/api/pipelines/${pipelineId}/run`, { file_id: fileId });
}

// ============================================================
// File translations (multi-lang by_lang shape)
// ============================================================

export interface V5Translation {
  idx: number;
  start: number;
  end: number;
  source_lang: string;
  source_text: string;
  by_lang: Record<string, { text: string; status: string; flags: string[] }>;
}

export async function getTranslations(fileId: string): Promise<V5Translation[]> {
  const r = await fetchJson<{ translations: V5Translation[] }>(
    `/api/files/${fileId}/translations?shape=v5`,
  );
  return r.translations;
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm run test -- src/lib/api/v5.test.ts 2>&1 | tail -10
```
Expected: 5 PASS.

- [ ] **Step 6: Commit T2**

```bash
git add frontend/src/lib/api/v5.ts frontend/src/lib/api/v5.test.ts
git commit -m "feat(v5-a3): v5 API client — 5 profile CRUD + pipeline + translations

Typed wrappers around the 30 v5 REST calls. getTranslations() passes
?shape=v5 so client always sees by_lang shape regardless of backend default.

5 vitest cases verify URL paths, payload shape, credentials cookie."
```

---

## Phase 2 — Profile Pages

### Task 3: LLMProfiles page (pattern setter)

**Files:**
- Create: `frontend/src/pages/LLMProfiles.tsx`

This page sets the v5 profile CRUD pattern. T4-T7 replicate it with field substitutions.

UX shape (mirror existing AsrProfiles.tsx Bold-shell layout):
- Left column: BoldRail (active='llm')
- Top: BoldTopbar (page title + health pills)
- Body: 2-col grid (left=profile list, right=editor form)
- List rows: name + delete chip
- Form: react-hook-form + zodResolver, "Save" + "Cancel" buttons
- "New" button creates a fresh profile in form state
- Save: POST or PATCH depending on form state

- [ ] **Step 1: Read existing AsrProfiles.tsx for the template**

```bash
cat frontend/src/pages/AsrProfiles.tsx | head -120
```

Note the file structure: imports, defaults, interfaces, component body, list+form panes.

- [ ] **Step 2: Create `frontend/src/pages/LLMProfiles.tsx`**

```typescript
// src/pages/LLMProfiles.tsx
// v5-A3 — LLM Profile CRUD page following the Bold-shell pattern. NEW v5 entity
// for backend LLM config (Ollama / OpenRouter / Claude) referenced by translator
// / refiner / verifier engines.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  LlmProfileSchema, LLM_BACKENDS,
  type LlmProfile, type LlmProfileRow,
} from '@/lib/schemas/llm-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: LlmProfile = {
  name: '',
  backend: 'ollama',
  model: '',
  base_url: 'http://localhost:11434',
  temperature: 0.2,
  shared: false,
};

export default function LLMProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<LlmProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<LlmProfile>({
    resolver: zodResolver(LlmProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const profiles = await v5.getLlmProfiles();
      setRows(profiles);
    } catch (e) {
      console.error('Failed to load LLM profiles', e);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset({
      name: row.name,
      backend: row.backend,
      model: row.model,
      base_url: row.base_url,
      temperature: row.temperature,
      shared: row.shared,
      api_key: row.api_key,
    });
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: LlmProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateLlmProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createLlmProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Save failed';
      alert(msg);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteLlmProfile(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
      if (selectedId === id) {
        newProfile();
      }
    } catch (e) {
      alert((e as Error).message);
    }
    setConfirmDelete(null);
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    clearUser();
    navigate('/login');
  }

  return (
    <div className="b-page">
      <BoldRail activeId="llm" />
      <main className="b-main">
        <header className="b-topbar">
          <div className="brand">
            <span className="brand-mark">M</span>
            <span className="brand-title">LLM Profiles</span>
          </div>
          <div className="health-cluster">
            <span className={`health-pill ${socketState === 'connected' ? 'ok' : 'warn'}`}>
              {socketState === 'connected' ? 'WS' : '——'}
            </span>
            <span className="health-pill">{user.username}</span>
            <button className="action-chip" onClick={logout}>Logout</button>
          </div>
        </header>

        <div className="b-body" style={{ gridTemplateColumns: '320px 1fr' }}>
          <aside className="b-col">
            <div className="panel">
              <div className="panel-head">
                <h2>Profiles</h2>
                <button className="action-chip" onClick={newProfile}>
                  <Icon name="plus" size={12} /> New
                </button>
              </div>
              <ul className="entry-list">
                {rows.map((r) => (
                  <li
                    key={r.id}
                    className={`entry-row ${selectedId === r.id ? 'on' : ''}`}
                    onClick={() => selectRow(r.id)}
                  >
                    <span className="entry-name">{r.name}</span>
                    <span className="entry-meta">{r.backend}</span>
                    <button
                      className="entry-del"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(r.id);
                      }}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <section className="b-col">
            <form className="panel" onSubmit={form.handleSubmit(onSubmit)}>
              <div className="panel-head">
                <h2>{selectedId ? 'Edit Profile' : 'New Profile'}</h2>
                <button type="submit" className="action-chip primary">Save</button>
              </div>

              <label className="field">
                Name
                <input type="text" {...form.register('name')} />
                {form.formState.errors.name && (
                  <span className="error">{form.formState.errors.name.message}</span>
                )}
              </label>

              <label className="field">
                Backend
                <select {...form.register('backend')}>
                  {LLM_BACKENDS.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </label>

              <label className="field">
                Model
                <input type="text" {...form.register('model')} placeholder="qwen3.5:9b" />
              </label>

              <label className="field">
                Base URL
                <input type="text" {...form.register('base_url')} />
              </label>

              <label className="field">
                Temperature
                <input
                  type="number"
                  step={0.1}
                  min={0}
                  max={2}
                  {...form.register('temperature', { valueAsNumber: true })}
                />
              </label>

              <label className="field">
                API Key (OpenRouter only)
                <input type="password" {...form.register('api_key')} />
              </label>

              <label className="field-row">
                <input type="checkbox" {...form.register('shared')} />
                Shared (visible to other users)
              </label>
            </form>
          </section>
        </div>
      </main>

      {confirmDelete && (
        <ConfirmDialog
          title="Delete LLM Profile?"
          message="This cannot be undone. References in pipelines will become broken."
          onConfirm={() => onDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Smoke build to catch typos**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "src/pages/LLMProfiles" | head -5
```
Expected: no errors mentioning LLMProfiles.tsx.

- [ ] **Step 4: Commit T3**

```bash
git add frontend/src/pages/LLMProfiles.tsx
git commit -m "feat(v5-a3): LLMProfiles page (pattern setter)

Bold-shell CRUD layout following the AsrProfiles.tsx template. NEW v5
entity for Ollama / OpenRouter / Claude backend configs that translator,
refiner, and verifier engines reference via llm_profile_id."
```

---

### Task 4: TranscribeProfiles page (rename of AsrProfiles + qwen3-asr engine)

**Files:**
- Create: `frontend/src/pages/TranscribeProfiles.tsx`
- (Keep AsrProfiles.tsx for backward compat during transition — removed in T10)

T4 creates a new page (does NOT delete AsrProfiles.tsx yet). Engine dropdown adds `qwen3-asr`. Language dropdown adds `yue` + `th`.

- [ ] **Step 1: Create `frontend/src/pages/TranscribeProfiles.tsx`**

```typescript
// src/pages/TranscribeProfiles.tsx
// v5-A3 — Transcribe Profile CRUD page (replaces AsrProfiles.tsx). Adds
// `qwen3-asr` engine + `yue` / `th` language options.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  TranscribeProfileSchema, TRANSCRIBE_ENGINES, TRANSCRIBE_LANGUAGES,
  type TranscribeProfile, type TranscribeProfileRow,
} from '@/lib/schemas/transcribe-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: TranscribeProfile = {
  name: '',
  engine: 'mlx-whisper',
  language: 'en',
  model_size: 'large-v3',
  initial_prompt: '',
  shared: false,
};

export default function TranscribeProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<TranscribeProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<TranscribeProfile>({
    resolver: zodResolver(TranscribeProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const profiles = await v5.getTranscribeProfiles();
      setRows(profiles);
    } catch (e) {
      console.error('Failed to load transcribe profiles', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset(row);
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: TranscribeProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateTranscribeProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createTranscribeProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteTranscribeProfile(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
      if (selectedId === id) newProfile();
    } catch (e) {
      alert((e as Error).message);
    }
    setConfirmDelete(null);
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    clearUser();
    navigate('/login');
  }

  return (
    <div className="b-page">
      <BoldRail activeId="transcribe" />
      <main className="b-main">
        <header className="b-topbar">
          <div className="brand">
            <span className="brand-mark">M</span>
            <span className="brand-title">Transcribe Profiles</span>
          </div>
          <div className="health-cluster">
            <span className={`health-pill ${socketState === 'connected' ? 'ok' : 'warn'}`}>
              {socketState === 'connected' ? 'WS' : '——'}
            </span>
            <span className="health-pill">{user.username}</span>
            <button className="action-chip" onClick={logout}>Logout</button>
          </div>
        </header>

        <div className="b-body" style={{ gridTemplateColumns: '320px 1fr' }}>
          <aside className="b-col">
            <div className="panel">
              <div className="panel-head">
                <h2>Profiles</h2>
                <button className="action-chip" onClick={newProfile}>
                  <Icon name="plus" size={12} /> New
                </button>
              </div>
              <ul className="entry-list">
                {rows.map((r) => (
                  <li
                    key={r.id}
                    className={`entry-row ${selectedId === r.id ? 'on' : ''}`}
                    onClick={() => selectRow(r.id)}
                  >
                    <span className="entry-name">{r.name}</span>
                    <span className="entry-meta">{r.engine} / {r.language}</span>
                    <button
                      className="entry-del"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(r.id); }}
                    >×</button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <section className="b-col">
            <form className="panel" onSubmit={form.handleSubmit(onSubmit)}>
              <div className="panel-head">
                <h2>{selectedId ? 'Edit' : 'New'}</h2>
                <button type="submit" className="action-chip primary">Save</button>
              </div>
              <label className="field">
                Name<input type="text" {...form.register('name')} />
              </label>
              <label className="field">
                Engine
                <select {...form.register('engine')}>
                  {TRANSCRIBE_ENGINES.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </label>
              <label className="field">
                Language
                <select {...form.register('language')}>
                  {TRANSCRIBE_LANGUAGES.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label className="field">
                Model Size
                <input type="text" {...form.register('model_size')} placeholder="large-v3 / 1.7B" />
              </label>
              <label className="field">
                Initial Prompt (max 512 chars)
                <textarea {...form.register('initial_prompt')} rows={4} />
              </label>
              <label className="field-row">
                <input type="checkbox" {...form.register('shared')} />
                Shared
              </label>
            </form>
          </section>
        </div>
      </main>

      {confirmDelete && (
        <ConfirmDialog
          title="Delete Transcribe Profile?"
          message="Pipelines referencing this profile will break."
          onConfirm={() => onDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "TranscribeProfiles" | head -3
```
Expected: clean (or pre-existing unrelated errors).

- [ ] **Step 3: Commit T4**

```bash
git add frontend/src/pages/TranscribeProfiles.tsx
git commit -m "feat(v5-a3): TranscribeProfiles page (qwen3-asr engine + yue/th langs)

Replaces AsrProfiles.tsx for v5 transcribe workflow. AsrProfiles.tsx
retained for backward compat through A3; legacy alias removed in T10."
```

---

### Task 5: TranslatorProfiles page (NEW)

**Files:**
- Create: `frontend/src/pages/TranslatorProfiles.tsx`

Source/target lang dropdowns are siblings — UI must guide user away from same-lang (zod schema enforces it but UI should pre-empt).

- [ ] **Step 1: Create `frontend/src/pages/TranslatorProfiles.tsx`**

```typescript
// src/pages/TranslatorProfiles.tsx
// v5-A3 — NEW Translator Profile CRUD. Cross-lingual entity referenced by
// pipeline.translators[lang]. source_lang MUST differ from target_lang.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  TranslatorProfileSchema, TRANSLATOR_LANGS,
  type TranslatorProfile, type TranslatorProfileRow,
} from '@/lib/schemas/translator-profile';
import type { LlmProfileRow } from '@/lib/schemas/llm-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: TranslatorProfile = {
  name: '',
  source_lang: 'zh',
  target_lang: 'en',
  llm_profile_id: '',
  prompt_template_id: 'translator/zh_to_en_default',
  shared: false,
};

export default function TranslatorProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<TranslatorProfileRow[]>([]);
  const [llms, setLlms] = useState<LlmProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<TranslatorProfile>({
    resolver: zodResolver(TranslatorProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const [profiles, llmRows] = await Promise.all([
        v5.getTranslatorProfiles(),
        v5.getLlmProfiles(),
      ]);
      setRows(profiles);
      setLlms(llmRows);
    } catch (e) {
      console.error('Failed to load', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset(row);
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: TranslatorProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateTranslatorProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createTranslatorProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteTranslatorProfile(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
      if (selectedId === id) newProfile();
    } catch (e) {
      alert((e as Error).message);
    }
    setConfirmDelete(null);
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    clearUser();
    navigate('/login');
  }

  return (
    <div className="b-page">
      <BoldRail activeId="translator" />
      <main className="b-main">
        <header className="b-topbar">
          <div className="brand">
            <span className="brand-mark">M</span>
            <span className="brand-title">Translator Profiles</span>
          </div>
          <div className="health-cluster">
            <span className={`health-pill ${socketState === 'connected' ? 'ok' : 'warn'}`}>
              {socketState === 'connected' ? 'WS' : '——'}
            </span>
            <span className="health-pill">{user.username}</span>
            <button className="action-chip" onClick={logout}>Logout</button>
          </div>
        </header>

        <div className="b-body" style={{ gridTemplateColumns: '320px 1fr' }}>
          <aside className="b-col">
            <div className="panel">
              <div className="panel-head">
                <h2>Profiles</h2>
                <button className="action-chip" onClick={newProfile}>
                  <Icon name="plus" size={12} /> New
                </button>
              </div>
              <ul className="entry-list">
                {rows.map((r) => (
                  <li
                    key={r.id}
                    className={`entry-row ${selectedId === r.id ? 'on' : ''}`}
                    onClick={() => selectRow(r.id)}
                  >
                    <span className="entry-name">{r.name}</span>
                    <span className="entry-meta">{r.source_lang} → {r.target_lang}</span>
                    <button
                      className="entry-del"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(r.id); }}
                    >×</button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <section className="b-col">
            <form className="panel" onSubmit={form.handleSubmit(onSubmit)}>
              <div className="panel-head">
                <h2>{selectedId ? 'Edit' : 'New'}</h2>
                <button type="submit" className="action-chip primary">Save</button>
              </div>
              <label className="field">
                Name<input type="text" {...form.register('name')} />
              </label>
              <label className="field">
                Source Language
                <select {...form.register('source_lang')}>
                  {TRANSLATOR_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label className="field">
                Target Language
                <select {...form.register('target_lang')}>
                  {TRANSLATOR_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
                {form.formState.errors.target_lang && (
                  <span className="error">{form.formState.errors.target_lang.message}</span>
                )}
              </label>
              <label className="field">
                LLM Profile
                <select {...form.register('llm_profile_id')}>
                  <option value="">— select —</option>
                  {llms.map((l) => (
                    <option key={l.id} value={l.id}>{l.name} ({l.backend})</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Prompt Template ID
                <input type="text" {...form.register('prompt_template_id')} placeholder="translator/zh_to_en_default" />
              </label>
              <label className="field-row">
                <input type="checkbox" {...form.register('shared')} />
                Shared
              </label>
            </form>
          </section>
        </div>
      </main>

      {confirmDelete && (
        <ConfirmDialog
          title="Delete Translator Profile?"
          message="Pipelines referencing this profile will break."
          onConfirm={() => onDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "TranslatorProfiles" | head -3
```
Expected: clean.

- [ ] **Step 3: Commit T5**

```bash
git add frontend/src/pages/TranslatorProfiles.tsx
git commit -m "feat(v5-a3): TranslatorProfiles page (NEW cross-lingual entity)

CRUD for translator profiles. LLM profile dropdown populated from
/api/llm_profiles (must create LLM profile first to reference it here)."
```

---

### Task 6: RefinerProfiles page (rename of MtProfiles + narrow semantics)

**Files:**
- Create: `frontend/src/pages/RefinerProfiles.tsx`

Same shape as TranslatorProfiles but `lang` + `style` instead of `source_lang` + `target_lang`. No cross-field rule.

- [ ] **Step 1: Create `frontend/src/pages/RefinerProfiles.tsx`**

```typescript
// src/pages/RefinerProfiles.tsx
// v5-A3 — Refiner Profile CRUD (replaces MtProfiles.tsx). Same-lingual polish:
// no source/target distinction, just `lang` + `style` (e.g. zh + broadcast-hk).
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  RefinerProfileSchema, REFINER_LANGS,
  type RefinerProfile, type RefinerProfileRow,
} from '@/lib/schemas/refiner-profile';
import type { LlmProfileRow } from '@/lib/schemas/llm-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: RefinerProfile = {
  name: '',
  lang: 'zh',
  style: 'broadcast-hk',
  llm_profile_id: '',
  prompt_template_id: 'refiner/zh_broadcast_hk_default',
  shared: false,
};

export default function RefinerProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<RefinerProfileRow[]>([]);
  const [llms, setLlms] = useState<LlmProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<RefinerProfile>({
    resolver: zodResolver(RefinerProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const [profiles, llmRows] = await Promise.all([
        v5.getRefinerProfiles(),
        v5.getLlmProfiles(),
      ]);
      setRows(profiles);
      setLlms(llmRows);
    } catch (e) {
      console.error('Failed to load', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset(row);
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: RefinerProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateRefinerProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createRefinerProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteRefinerProfile(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
      if (selectedId === id) newProfile();
    } catch (e) {
      alert((e as Error).message);
    }
    setConfirmDelete(null);
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    clearUser();
    navigate('/login');
  }

  return (
    <div className="b-page">
      <BoldRail activeId="refiner" />
      <main className="b-main">
        <header className="b-topbar">
          <div className="brand">
            <span className="brand-mark">M</span>
            <span className="brand-title">Refiner Profiles</span>
          </div>
          <div className="health-cluster">
            <span className={`health-pill ${socketState === 'connected' ? 'ok' : 'warn'}`}>
              {socketState === 'connected' ? 'WS' : '——'}
            </span>
            <span className="health-pill">{user.username}</span>
            <button className="action-chip" onClick={logout}>Logout</button>
          </div>
        </header>

        <div className="b-body" style={{ gridTemplateColumns: '320px 1fr' }}>
          <aside className="b-col">
            <div className="panel">
              <div className="panel-head">
                <h2>Profiles</h2>
                <button className="action-chip" onClick={newProfile}>
                  <Icon name="plus" size={12} /> New
                </button>
              </div>
              <ul className="entry-list">
                {rows.map((r) => (
                  <li
                    key={r.id}
                    className={`entry-row ${selectedId === r.id ? 'on' : ''}`}
                    onClick={() => selectRow(r.id)}
                  >
                    <span className="entry-name">{r.name}</span>
                    <span className="entry-meta">{r.lang} / {r.style}</span>
                    <button
                      className="entry-del"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(r.id); }}
                    >×</button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <section className="b-col">
            <form className="panel" onSubmit={form.handleSubmit(onSubmit)}>
              <div className="panel-head">
                <h2>{selectedId ? 'Edit' : 'New'}</h2>
                <button type="submit" className="action-chip primary">Save</button>
              </div>
              <label className="field">
                Name<input type="text" {...form.register('name')} />
              </label>
              <label className="field">
                Language
                <select {...form.register('lang')}>
                  {REFINER_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label className="field">
                Style<input type="text" {...form.register('style')} placeholder="broadcast-hk / newscast" />
              </label>
              <label className="field">
                LLM Profile
                <select {...form.register('llm_profile_id')}>
                  <option value="">— select —</option>
                  {llms.map((l) => (
                    <option key={l.id} value={l.id}>{l.name} ({l.backend})</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Prompt Template ID
                <input type="text" {...form.register('prompt_template_id')} />
              </label>
              <label className="field-row">
                <input type="checkbox" {...form.register('shared')} />
                Shared
              </label>
            </form>
          </section>
        </div>
      </main>

      {confirmDelete && (
        <ConfirmDialog
          title="Delete Refiner Profile?"
          message="Pipelines referencing this profile will break."
          onConfirm={() => onDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "RefinerProfiles" | head -3
```

- [ ] **Step 3: Commit T6**

```bash
git add frontend/src/pages/RefinerProfiles.tsx
git commit -m "feat(v5-a3): RefinerProfiles page (rename of MtProfiles, same-lingual narrow)

Replaces MtProfiles.tsx for v5 refiner workflow. Style field free-form
(broadcast-hk / newscast / etc.). LLM profile dropdown populated from
/api/llm_profiles."
```

---

### Task 7: VerifierProfiles page (NEW)

**Files:**
- Create: `frontend/src/pages/VerifierProfiles.tsx`

Smallest of the 5 — only 4 fields (name, lang, llm_profile_id, prompt_template_id).

- [ ] **Step 1: Create `frontend/src/pages/VerifierProfiles.tsx`**

```typescript
// src/pages/VerifierProfiles.tsx
// v5-A3 — NEW Verifier Profile CRUD. LLM-as-judge config used by
// pipeline.asr_verifier to reconcile primary + secondary ASR outputs.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  VerifierProfileSchema, VERIFIER_LANGS,
  type VerifierProfile, type VerifierProfileRow,
} from '@/lib/schemas/verifier-profile';
import type { LlmProfileRow } from '@/lib/schemas/llm-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: VerifierProfile = {
  name: '',
  lang: 'zh',
  llm_profile_id: '',
  prompt_template_id: 'verifier/zh_default',
  shared: false,
};

export default function VerifierProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<VerifierProfileRow[]>([]);
  const [llms, setLlms] = useState<LlmProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<VerifierProfile>({
    resolver: zodResolver(VerifierProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const [profiles, llmRows] = await Promise.all([
        v5.getVerifierProfiles(),
        v5.getLlmProfiles(),
      ]);
      setRows(profiles);
      setLlms(llmRows);
    } catch (e) {
      console.error('Failed to load', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset(row);
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: VerifierProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateVerifierProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createVerifierProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteVerifierProfile(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
      if (selectedId === id) newProfile();
    } catch (e) {
      alert((e as Error).message);
    }
    setConfirmDelete(null);
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    clearUser();
    navigate('/login');
  }

  return (
    <div className="b-page">
      <BoldRail activeId="verifier" />
      <main className="b-main">
        <header className="b-topbar">
          <div className="brand">
            <span className="brand-mark">M</span>
            <span className="brand-title">Verifier Profiles</span>
          </div>
          <div className="health-cluster">
            <span className={`health-pill ${socketState === 'connected' ? 'ok' : 'warn'}`}>
              {socketState === 'connected' ? 'WS' : '——'}
            </span>
            <span className="health-pill">{user.username}</span>
            <button className="action-chip" onClick={logout}>Logout</button>
          </div>
        </header>

        <div className="b-body" style={{ gridTemplateColumns: '320px 1fr' }}>
          <aside className="b-col">
            <div className="panel">
              <div className="panel-head">
                <h2>Profiles</h2>
                <button className="action-chip" onClick={newProfile}>
                  <Icon name="plus" size={12} /> New
                </button>
              </div>
              <ul className="entry-list">
                {rows.map((r) => (
                  <li
                    key={r.id}
                    className={`entry-row ${selectedId === r.id ? 'on' : ''}`}
                    onClick={() => selectRow(r.id)}
                  >
                    <span className="entry-name">{r.name}</span>
                    <span className="entry-meta">{r.lang}</span>
                    <button
                      className="entry-del"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(r.id); }}
                    >×</button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <section className="b-col">
            <form className="panel" onSubmit={form.handleSubmit(onSubmit)}>
              <div className="panel-head">
                <h2>{selectedId ? 'Edit' : 'New'}</h2>
                <button type="submit" className="action-chip primary">Save</button>
              </div>
              <label className="field">
                Name<input type="text" {...form.register('name')} />
              </label>
              <label className="field">
                Language (source audio)
                <select {...form.register('lang')}>
                  {VERIFIER_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label className="field">
                LLM Profile
                <select {...form.register('llm_profile_id')}>
                  <option value="">— select —</option>
                  {llms.map((l) => (
                    <option key={l.id} value={l.id}>{l.name} ({l.backend})</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Prompt Template ID
                <input type="text" {...form.register('prompt_template_id')} />
              </label>
              <label className="field-row">
                <input type="checkbox" {...form.register('shared')} />
                Shared
              </label>
            </form>
          </section>
        </div>
      </main>

      {confirmDelete && (
        <ConfirmDialog
          title="Delete Verifier Profile?"
          message="Pipelines referencing this profile will break."
          onConfirm={() => onDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit T7**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "VerifierProfiles" | head -3
git add frontend/src/pages/VerifierProfiles.tsx
git commit -m "feat(v5-a3): VerifierProfiles page (NEW LLM-as-judge entity)

Smallest of the 5 v5 profile pages: name, lang (source audio language),
llm_profile_id, prompt_template_id."
```

---

## Phase 3 — Pipelines Page Rewrite

### Task 8: Pipelines page rewrite (per-target-lang card)

**Files:**
- Modify: `frontend/src/pages/Pipelines.tsx` (rewrite)

The v4 page renders a flat draggable stage list. v5 needs a per-target-lang card layout. ASR section is global to the pipeline; per-target-lang cards each contain refiner chain + (if non-source) translator picker.

Layout sketch:
```
[ Pipeline Header — name + Save ]
[ ASR section — Primary dropdown + Secondary toggle + Verifier toggle ]
[ Source language: zh ]
[ Target Languages: [+ Add] ]
[ Card: ZH 輸出 (source-lang, no translator)
   - Refiner: [profile dropdown ▼] [Edit prompt]
]
[ Card: EN 輸出
   - Translator: [profile dropdown ▼] [Edit prompt]
   - Refiner: [profile dropdown ▼] [Edit prompt]
]
[ Font Config — unchanged from v4 ]
```

- [ ] **Step 1: Read existing Pipelines.tsx for the v4 baseline**

```bash
cat frontend/src/pages/Pipelines.tsx | head -50
```

The v4 file is 385 lines. We're going to fully replace it.

- [ ] **Step 2: Rewrite `frontend/src/pages/Pipelines.tsx`**

```typescript
// src/pages/Pipelines.tsx
// v5-A3 — Full rewrite for per-target-lang card layout. Replaces the v4 flat
// draggable stage list with a structured editor: ASR section (Primary + optional
// Secondary + optional Verifier), then one card per target language (each card
// has optional translator + refiner chain).
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  PipelineV5Schema, PIPELINE_V5_LANGS,
  type PipelineV5, type PipelineV5Row,
} from '@/lib/schemas/pipeline-v5';
import type { TranscribeProfileRow } from '@/lib/schemas/transcribe-profile';
import type { LlmProfileRow } from '@/lib/schemas/llm-profile';
import type { TranslatorProfileRow } from '@/lib/schemas/translator-profile';
import type { RefinerProfileRow } from '@/lib/schemas/refiner-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaultPipeline: PipelineV5 = {
  name: '',
  version: 5,
  asr_primary: { transcribe_profile_id: '', source_lang: 'zh' },
  asr_secondary: null,
  asr_verifier: null,
  target_languages: ['zh'],
  refinements: { zh: [] },
  translators: {},
  glossary_stages: {},
  font_config: { family: 'Noto Sans TC', color: 'white', outline_color: 'black' },
  shared: false,
};

export default function Pipelines() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();

  const [transcribes, setTranscribes] = useState<TranscribeProfileRow[]>([]);
  const [llms, setLlms] = useState<LlmProfileRow[]>([]);
  const [translators, setTranslators] = useState<TranslatorProfileRow[]>([]);
  const [refiners, setRefiners] = useState<RefinerProfileRow[]>([]);

  const form = useForm<PipelineV5>({
    resolver: zodResolver(PipelineV5Schema),
    defaultValues: defaultPipeline,
  });

  const targetLanguages = form.watch('target_languages');
  const sourceLang = form.watch('asr_primary.source_lang');
  const secondaryEnabled = form.watch('asr_secondary') !== null;
  const verifierEnabled = form.watch('asr_verifier') !== null;

  useEffect(() => {
    Promise.all([
      v5.getTranscribeProfiles(),
      v5.getLlmProfiles(),
      v5.getTranslatorProfiles(),
      v5.getRefinerProfiles(),
    ]).then(([tr, llm, xl, rf]) => {
      setTranscribes(tr);
      setLlms(llm);
      setTranslators(xl);
      setRefiners(rf);
    });
  }, []);

  function toggleSecondary() {
    if (secondaryEnabled) {
      form.setValue('asr_secondary', null);
      form.setValue('asr_verifier', null);  // verifier requires secondary
    } else {
      form.setValue('asr_secondary', { transcribe_profile_id: '', source_lang: sourceLang });
    }
  }

  function toggleVerifier() {
    if (verifierEnabled) {
      form.setValue('asr_verifier', null);
    } else {
      form.setValue('asr_verifier', { llm_profile_id: '', prompt_template_id: `verifier/${sourceLang}_default` });
    }
  }

  function addTargetLang(lang: PipelineV5['target_languages'][number]) {
    const current = form.getValues('target_languages');
    if (current.includes(lang)) return;
    form.setValue('target_languages', [...current, lang]);
    // Ensure refinements[lang] = [] exists
    const refinements = form.getValues('refinements');
    form.setValue('refinements', { ...refinements, [lang]: [] });
  }

  function removeTargetLang(lang: string) {
    const current = form.getValues('target_languages');
    const filtered = current.filter((l) => l !== lang);
    form.setValue('target_languages', filtered);
    const refinements = { ...form.getValues('refinements') };
    delete refinements[lang];
    form.setValue('refinements', refinements);
    const translatorsMap = { ...form.getValues('translators') };
    delete translatorsMap[lang];
    form.setValue('translators', translatorsMap);
  }

  function setTranslatorForLang(lang: string, profileId: string) {
    const translatorsMap = { ...form.getValues('translators') };
    translatorsMap[lang] = { translator_profile_id: profileId };
    form.setValue('translators', translatorsMap);
  }

  function setRefinerForLang(lang: string, profileId: string) {
    const refinements = { ...form.getValues('refinements') };
    refinements[lang] = profileId ? [{ refiner_profile_id: profileId }] : [];
    form.setValue('refinements', refinements);
  }

  async function onSubmit(data: PipelineV5) {
    try {
      const created = await v5.createPipelineV5(data);
      alert(`Pipeline created: ${created.id}`);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    clearUser();
    navigate('/login');
  }

  return (
    <div className="b-page">
      <BoldRail activeId="pipeline" />
      <main className="b-main">
        <header className="b-topbar">
          <div className="brand">
            <span className="brand-mark">M</span>
            <span className="brand-title">Pipelines (v5)</span>
          </div>
          <div className="health-cluster">
            <span className={`health-pill ${socketState === 'connected' ? 'ok' : 'warn'}`}>
              {socketState === 'connected' ? 'WS' : '——'}
            </span>
            <span className="health-pill">{user.username}</span>
            <button className="action-chip" onClick={logout}>Logout</button>
          </div>
        </header>

        <div className="b-body" style={{ gridTemplateColumns: '1fr' }}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <section className="panel">
              <div className="panel-head">
                <h2>Pipeline Name</h2>
                <button type="submit" className="action-chip primary">Save Pipeline</button>
              </div>
              <input type="text" {...form.register('name')} placeholder="HK broadcast (ZH + EN)" />
            </section>

            <section className="panel">
              <div className="panel-head"><h2>ASR</h2></div>
              <label className="field">
                Primary Transcribe Profile
                <select {...form.register('asr_primary.transcribe_profile_id')}>
                  <option value="">— select —</option>
                  {transcribes.map((t) => (
                    <option key={t.id} value={t.id}>{t.name} ({t.engine}/{t.language})</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Source Language
                <select {...form.register('asr_primary.source_lang')}>
                  {PIPELINE_V5_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>

              <label className="field-row">
                <input type="checkbox" checked={secondaryEnabled} onChange={toggleSecondary} />
                Enable Secondary ASR (dual-ASR cross-validation)
              </label>

              {secondaryEnabled && (
                <label className="field">
                  Secondary Transcribe Profile
                  <Controller
                    control={form.control}
                    name="asr_secondary.transcribe_profile_id"
                    render={({ field }) => (
                      <select {...field} value={field.value || ''}>
                        <option value="">— select —</option>
                        {transcribes.map((t) => (
                          <option key={t.id} value={t.id}>{t.name} ({t.engine})</option>
                        ))}
                      </select>
                    )}
                  />
                </label>
              )}

              {secondaryEnabled && (
                <label className="field-row">
                  <input type="checkbox" checked={verifierEnabled} onChange={toggleVerifier} />
                  Enable Verifier (LLM-as-judge between primary + secondary)
                </label>
              )}

              {verifierEnabled && (
                <>
                  <label className="field">
                    Verifier LLM Profile
                    <Controller
                      control={form.control}
                      name="asr_verifier.llm_profile_id"
                      render={({ field }) => (
                        <select {...field} value={field.value || ''}>
                          <option value="">— select —</option>
                          {llms.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                        </select>
                      )}
                    />
                  </label>
                  <label className="field">
                    Verifier Prompt Template
                    <Controller
                      control={form.control}
                      name="asr_verifier.prompt_template_id"
                      render={({ field }) => (
                        <input type="text" {...field} value={field.value || ''} />
                      )}
                    />
                  </label>
                </>
              )}
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Target Languages</h2>
              </div>
              <div className="lang-chip-row">
                {PIPELINE_V5_LANGS.map((l) => (
                  <button
                    key={l}
                    type="button"
                    className={`action-chip ${targetLanguages.includes(l) ? 'primary' : ''}`}
                    onClick={() => targetLanguages.includes(l) ? removeTargetLang(l) : addTargetLang(l)}
                  >
                    {l}
                  </button>
                ))}
              </div>

              <div className="lang-cards" style={{ marginTop: 16 }}>
                {targetLanguages.map((lang) => (
                  <div key={lang} className="panel" style={{ marginBottom: 8 }}>
                    <div className="panel-head">
                      <h3>{lang} 輸出{lang === sourceLang ? ' (source-lang)' : ''}</h3>
                    </div>

                    {lang !== sourceLang && (
                      <label className="field">
                        Translator ({sourceLang} → {lang})
                        <select
                          value={form.watch(`translators.${lang}.translator_profile_id`) || ''}
                          onChange={(e) => setTranslatorForLang(lang, e.target.value)}
                        >
                          <option value="">— select —</option>
                          {translators
                            .filter((t) => t.source_lang === sourceLang && t.target_lang === lang)
                            .map((t) => (
                              <option key={t.id} value={t.id}>{t.name}</option>
                            ))}
                        </select>
                      </label>
                    )}

                    <label className="field">
                      Refiner ({lang} polish — optional)
                      <select
                        value={form.watch(`refinements.${lang}`)?.[0]?.refiner_profile_id || ''}
                        onChange={(e) => setRefinerForLang(lang, e.target.value)}
                      >
                        <option value="">— none —</option>
                        {refiners
                          .filter((r) => r.lang === lang)
                          .map((r) => (
                            <option key={r.id} value={r.id}>{r.name} ({r.style})</option>
                          ))}
                      </select>
                    </label>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panel-head"><h2>Font Config</h2></div>
              <label className="field">
                Family<input type="text" {...form.register('font_config.family')} />
              </label>
              <label className="field">
                Color<input type="text" {...form.register('font_config.color')} />
              </label>
              <label className="field">
                Outline Color<input type="text" {...form.register('font_config.outline_color')} />
              </label>
            </section>
          </form>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Pipelines" | head -5
```
Expected: clean (or pre-existing).

- [ ] **Step 4: Commit T8**

```bash
git add frontend/src/pages/Pipelines.tsx
git commit -m "feat(v5-a3): Pipelines page rewrite — per-target-lang card layout

Replaces v4 flat draggable stage list with:
- Pipeline name + Save
- ASR section: Primary + optional Secondary + optional Verifier toggles
- Target Languages chip row + per-lang cards (each: optional translator
  for non-source lang, optional refiner with profile dropdown)
- Font config unchanged

Saves to POST /api/pipelines with version: 5. Client-side validation via
PipelineV5Schema enforces 3 cross-field rules before submit."
```

---

## Phase 4 — Proofread Extensions

### Task 9: Proofread page extensions

**Files:**
- Modify: `frontend/src/pages/Proofread/index.tsx` (add target-lang tabs)
- Modify: `frontend/src/pages/Proofread/hooks/useFileData.ts` (consume ?shape=v5)
- Modify: `frontend/src/pages/Proofread/types.ts` (add V5Translation interface)
- Create: `frontend/src/pages/Proofread/TargetLangTabs.tsx`

The Proofread page currently shows one ZH column + one EN column. v5 needs N columns (one per by_lang key). Simplest UX: tab switcher between langs at the top, current segment table shows the selected lang.

- [ ] **Step 1: Update types**

Open `frontend/src/pages/Proofread/types.ts`. Add at end:
```typescript
// v5-A3 — multi-lang shape from GET /api/files/<id>/translations?shape=v5
export interface V5Translation {
  idx: number;
  start: number;
  end: number;
  source_lang: string;
  source_text: string;
  by_lang: Record<string, { text: string; status: string; flags: string[] }>;
}
```

- [ ] **Step 2: Update useFileData hook**

Open `frontend/src/pages/Proofread/hooks/useFileData.ts`. Find the translations fetch (look for `/translations` URL). Replace its fetch call with the v5 helper. Add `import * as v5 from '@/lib/api/v5'` near the top. The fetch should become:

```typescript
// Fetch translations in v5 by_lang shape
const v5Translations = await v5.getTranslations(fileId);
```

Then convert v5 → v4 shape for backward-compat with existing Proofread UI **OR** keep v5 shape and migrate UI in step 3. Decision: **keep v5 shape** since we're about to add target-lang tabs that need it.

Replace the file's `Translation[]` type imports with the new `V5Translation` interface where it represents fetched data. Existing UI that depends on `t.zh_text` will be migrated to `t.by_lang[activeLang].text` in step 3.

- [ ] **Step 3: Create the tab switcher**

Create `frontend/src/pages/Proofread/TargetLangTabs.tsx`:
```typescript
// Proofread target-lang tabs — switch which lang the segment table shows.
import type { V5Translation } from './types';

interface Props {
  translations: V5Translation[];
  activeLang: string;
  onSelect: (lang: string) => void;
}

export function TargetLangTabs({ translations, activeLang, onSelect }: Props) {
  // Compute unique target langs from by_lang keys across all rows
  const langs = new Set<string>();
  for (const t of translations) {
    for (const k of Object.keys(t.by_lang)) {
      langs.add(k);
    }
  }
  const sorted = Array.from(langs).sort();

  return (
    <div className="lang-tabs">
      {sorted.map((l) => (
        <button
          key={l}
          className={`lang-tab ${l === activeLang ? 'on' : ''}`}
          onClick={() => onSelect(l)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Wire into Proofread/index.tsx**

In `frontend/src/pages/Proofread/index.tsx`:
1. Add `useState<string>('zh')` for `activeLang` (default to first available, ideally source_lang).
2. Add `<TargetLangTabs translations={v5Translations} activeLang={activeLang} onSelect={setActiveLang} />` near top of segment area.
3. In SegmentRow / DetailEditor, replace `t.zh_text` with `t.by_lang[activeLang]?.text || ''`.
4. Default `activeLang` initialization:
   ```typescript
   useEffect(() => {
     if (translations.length > 0) {
       const sourceLang = translations[0].source_lang;
       setActiveLang(sourceLang);
     }
   }, [translations]);
   ```

Read the existing Proofread/index.tsx to find the right insertion points. Don't make assumptions about which segment renderer accesses `zh_text` — search and replace pattern.

- [ ] **Step 5: Smoke build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```
Expected: build succeeds (or pre-existing v4 warnings).

- [ ] **Step 6: Commit T9**

```bash
git add frontend/src/pages/Proofread/
git commit -m "feat(v5-a3): Proofread multi-lang tabs + v5 by_lang consumption

- useFileData hook fetches with ?shape=v5
- New TargetLangTabs component switches between by_lang keys
- SegmentRow / DetailEditor read t.by_lang[activeLang].text instead of
  hardcoded zh_text
- Default active lang = source_lang (so source-lang output shown first)

types.V5Translation interface added alongside existing v4 Translation."
```

---

## Phase 5 — Wrap-up

### Task 10: RenderModal target-lang picker + Router/BoldRail wiring + Playwright + legacy alias retirement + CLAUDE.md

This task wires everything together and retires legacy v4 routes. Multiple commits.

**Files:**
- Modify: `frontend/src/pages/Proofread/RenderModal.tsx` (add target-lang picker)
- Modify: `frontend/src/router.tsx` (add 3 new routes, rename 2)
- Modify: `frontend/src/components/BoldRail.tsx` (add 3 entries, rename 2)
- Create: 3 Playwright spec files under `frontend/tests-e2e/`
- Modify: `backend/bootstrap.py` (drop 2 legacy blueprint registrations)
- Delete: `backend/routes/asr_profiles.py`, `backend/routes/mt_profiles.py`
- Modify: `CLAUDE.md`

#### Step 1: Add target-lang picker to RenderModal

Open `frontend/src/pages/Proofread/RenderModal.tsx`. Find the render options form. Add a target-lang dropdown near the top:

```typescript
// At top of form, before format tabs:
<label className="field">
  Target Language (which lang to burn into subtitles)
  <select value={targetLang} onChange={(e) => setTargetLang(e.target.value)}>
    {availableLangs.map((l) => <option key={l} value={l}>{l}</option>)}
  </select>
</label>
```

Pass `availableLangs` from parent (derive from `translations[0].by_lang` keys). Wire `targetLang` into the POST `/api/render` body — backend already supports `lang` param.

#### Step 2: Update router

Open `frontend/src/router.tsx`. Add lazy imports + routes:
```typescript
const LLMProfiles = lazy(() => import('@/pages/LLMProfiles'));
const TranscribeProfiles = lazy(() => import('@/pages/TranscribeProfiles'));
const TranslatorProfiles = lazy(() => import('@/pages/TranslatorProfiles'));
const RefinerProfiles = lazy(() => import('@/pages/RefinerProfiles'));
const VerifierProfiles = lazy(() => import('@/pages/VerifierProfiles'));

// In the route children list (alongside other Bold pages):
{ path: 'llm_profiles', element: <LLMProfiles /> },
{ path: 'transcribe_profiles', element: <TranscribeProfiles /> },
{ path: 'translator_profiles', element: <TranslatorProfiles /> },
{ path: 'refiner_profiles', element: <RefinerProfiles /> },
{ path: 'verifier_profiles', element: <VerifierProfiles /> },
// Keep legacy routes redirecting:
{ path: 'asr_profiles', element: <Navigate to="/transcribe_profiles" replace /> },
{ path: 'mt_profiles', element: <Navigate to="/refiner_profiles" replace /> },
```

Drop the `AsrProfiles` + `MtProfiles` direct route entries (replaced by Navigate redirects).

#### Step 3: Update BoldRail

Open `frontend/src/components/BoldRail.tsx`. Update `RAIL_ITEMS` to add LLM/Translator/Verifier entries; rename ASR → Transcribe, MT → Refiner:

```typescript
export const RAIL_ITEMS: Array<{
  id: string;
  icon: IconName;
  label: string;
  href: string;
}> = [
  { id: 'home',       icon: 'home',     label: '主頁',     href: '/' },
  { id: 'files',      icon: 'film',     label: '檔案',     href: '/' },
  { id: 'proof',      icon: 'edit',     label: '校對',     href: '/' },
  { id: 'pipeline',   icon: 'flow',     label: 'Pipeline', href: '/pipelines' },
  { id: 'llm',        icon: 'cog',      label: 'LLM',      href: '/llm_profiles' },
  { id: 'transcribe', icon: 'waveform', label: 'Transcribe', href: '/transcribe_profiles' },
  { id: 'translator', icon: 'layers',   label: 'Translator', href: '/translator_profiles' },
  { id: 'refiner',    icon: 'edit',     label: 'Refiner',  href: '/refiner_profiles' },
  { id: 'verifier',   icon: 'check',    label: 'Verifier', href: '/verifier_profiles' },
  { id: 'gloss',      icon: 'book',     label: '術語表',   href: '/glossaries' },
  { id: 'admin',      icon: 'user',     label: '管理員',   href: '/admin' },
];
```

#### Step 4: Add Playwright specs

Create `frontend/tests-e2e/v5-profile-crud.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

test.describe('v5 profile CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="username"]', process.env.E2E_USER || 'admin');
    await page.fill('input[name="password"]', process.env.E2E_PASSWORD || 'AdminPass1!');
    await page.click('button[type="submit"]');
    await page.waitForURL('/');
  });

  test('create LLM profile', async ({ page }) => {
    await page.goto('/llm_profiles');
    await page.click('text=New');
    await page.fill('input[name="name"]', 'E2E LLM');
    await page.fill('input[name="model"]', 'qwen3.5:9b');
    await page.fill('input[name="base_url"]', 'http://localhost:11434');
    await page.click('button:has-text("Save")');
    await expect(page.locator('text=E2E LLM')).toBeVisible();
  });

  test('create Transcribe profile with qwen3-asr', async ({ page }) => {
    await page.goto('/transcribe_profiles');
    await page.click('text=New');
    await page.fill('input[name="name"]', 'E2E Qwen3');
    await page.selectOption('select[name="engine"]', 'qwen3-asr');
    await page.selectOption('select[name="language"]', 'zh');
    await page.click('button:has-text("Save")');
    await expect(page.locator('text=E2E Qwen3')).toBeVisible();
  });
});
```

Create `frontend/tests-e2e/v5-pipeline-builder.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

test('v5 pipeline builder lets user pick target languages', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="username"]', process.env.E2E_USER || 'admin');
  await page.fill('input[name="password"]', process.env.E2E_PASSWORD || 'AdminPass1!');
  await page.click('button[type="submit"]');
  await page.waitForURL('/');
  await page.goto('/pipelines');

  // ASR section visible
  await expect(page.locator('h2:has-text("ASR")')).toBeVisible();

  // Target language chips clickable
  await expect(page.locator('button.action-chip:has-text("zh")')).toBeVisible();
  await page.click('button.action-chip:has-text("en")');

  // EN card appears
  await expect(page.locator('h3:has-text("en 輸出")')).toBeVisible();
});
```

Create `frontend/tests-e2e/v5-proofread-multilang.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

test('proofread page shows target-lang tabs when file has by_lang data', async ({ page }) => {
  // This test assumes a pre-populated file with v5 by_lang translations exists.
  // Skips gracefully if not available.
  await page.goto('/login');
  await page.fill('input[name="username"]', process.env.E2E_USER || 'admin');
  await page.fill('input[name="password"]', process.env.E2E_PASSWORD || 'AdminPass1!');
  await page.click('button[type="submit"]');
  await page.waitForURL('/');

  // Try a known file id — skip if 404
  const FID = process.env.E2E_V5_FILE_ID || 'b9b9e4fad18c';
  await page.goto(`/proofread/${FID}`);

  const tabs = page.locator('.lang-tabs button');
  const count = await tabs.count();
  if (count < 2) {
    test.skip(true, `File ${FID} doesn't have multi-lang v5 data`);
  }

  // Click EN tab if present
  const enTab = page.locator('.lang-tabs button:has-text("en")');
  if (await enTab.count() > 0) {
    await enTab.click();
    // Segment table should re-render
    await page.waitForTimeout(300);
  }
});
```

#### Step 5: Delete legacy backend routes

```bash
git rm backend/routes/asr_profiles.py backend/routes/mt_profiles.py
```

#### Step 6: Update bootstrap.py

Open `backend/bootstrap.py`. Remove the 2 import lines + 2 `register_blueprint` calls for `asr_profiles_bp` and `mt_profiles_bp`. Search for those exact names and remove their lines.

#### Step 7: Update CLAUDE.md

Append v5-A3 entry above v5-A2 entry in "Completed Features":

```markdown
### v5-A3 — Frontend Multi-Lang UI (in progress on `feat/frontend-redesign`)
- Builds the React frontend to consume v5-A2's multi-lang backend. 5 v5 profile CRUD pages, per-target-lang Pipelines editor, multi-lang Proofread with target-lang tab switcher, RenderModal target-lang picker. Spec: [docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md](docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md) §8. Plan: [docs/superpowers/plans/2026-05-20-v5-A3-frontend-multilang-plan.md](docs/superpowers/plans/2026-05-20-v5-A3-frontend-multilang-plan.md).
- **Schemas (T1)**: 5 v5 profile zod schemas + v5 Pipeline schema with 3 cross-field rules mirroring backend `pipeline_schema_v5.py`. ~20 vitest cases.
- **API client (T2)** ([frontend/src/lib/api/v5.ts](frontend/src/lib/api/v5.ts)) — typed wrappers around 30 v5 REST calls; `getTranslations(fileId)` automatically passes `?shape=v5`.
- **5 v5 profile pages (T3-T7)** — Bold-shell CRUD pattern from v4 AsrProfiles.tsx:
  - LLMProfiles.tsx (NEW pattern setter)
  - TranscribeProfiles.tsx (replaces AsrProfiles, adds qwen3-asr engine + yue/th)
  - TranslatorProfiles.tsx (NEW cross-lingual, refines source_lang != target_lang)
  - RefinerProfiles.tsx (replaces MtProfiles, narrowed same-lingual)
  - VerifierProfiles.tsx (NEW LLM-as-judge)
- **Pipelines page rewrite (T8)** — flat v4 stage list → per-target-lang card layout. ASR section (Primary + optional Secondary + optional Verifier toggles); Target Languages chip row; per-lang cards each with optional translator (non-source) + optional refiner. Client-side validation via PipelineV5Schema before submit.
- **Proofread multi-lang (T9)** — TargetLangTabs component switches between by_lang keys; SegmentRow / DetailEditor read `t.by_lang[activeLang].text` instead of hardcoded `zh_text`. useFileData hook fetches `?shape=v5`.
- **RenderModal target-lang picker (T10)** — dropdown selects which lang to burn into subtitles; falls back to source_lang by default.
- **Legacy alias retirement (T10)** — `/api/asr_profiles` + `/api/mt_profiles` v4 routes deleted from backend (removed Deprecation headers, removed bootstrap.py registrations, removed route module files). Frontend routes `/asr_profiles` + `/mt_profiles` now redirect to v5 equivalents via React Router Navigate.
- **Tests**: ~50 new vitest + 3 new Playwright E2E specs covering profile CRUD, pipeline builder, multi-lang proofread.
- **Out of A3 scope**: Glossary cross-lingual schema migration (v3.15 multilingual already supports it but v5 Pipelines page doesn't render the multi-glossary picker yet — keeps to single glossary per stage); pipeline cancel mid-stage cleanup; per-stage rerun on v5; rename frontend test helpers.
- **V5 complete**: A1 (32 commits) + A2 (10 commits + 2 fix) + A3 (~16 commits) ≈ 60 commits land the full v5 dual-ASR + Refiner-Translator separation feature on `feat/frontend-redesign`.
```

#### Step 8: Run all tests + commit

```bash
cd frontend && npm run test 2>&1 | tail -5
cd .. && cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -5
```

Backend pytest expects 956 - removed tests (test_asr_profiles + test_mt_profiles routes if they tested aliases) = check it shipps roughly the same. Adjust legacy route tests by either removing if they test the deleted alias headers or updating to point at the new v5 path.

```bash
# 4 commits separately for trace clarity
git add frontend/src/pages/Proofread/RenderModal.tsx
git commit -m "feat(v5-a3): RenderModal target-lang picker"

git add frontend/src/router.tsx frontend/src/components/BoldRail.tsx
git commit -m "feat(v5-a3): wire 3 new pages + rename 2; legacy routes redirect"

git add frontend/tests-e2e/v5-*.spec.ts
git commit -m "test(v5-a3): Playwright E2E for v5 profile CRUD + pipeline builder + multilang proofread"

git rm backend/routes/asr_profiles.py backend/routes/mt_profiles.py
# Edit bootstrap.py to drop the 2 registrations + commit
git add backend/bootstrap.py
git commit -m "chore(v5-a3): retire legacy /api/asr_profiles + /api/mt_profiles route modules

Frontend has migrated to /api/transcribe_profiles + /api/refiner_profiles.
Deprecation headers + Sunset metadata from v5-A1 served their purpose;
removing the routes simplifies the surface area before merging v5 to main."

git add CLAUDE.md
git commit -m "docs(v5-a3): CLAUDE.md progress entry for frontend multilang phase"
```

## Final verification

After all 10 tasks complete:

```bash
cd frontend && npm run build 2>&1 | tail -5    # Vite build succeeds
cd frontend && npm run test 2>&1 | tail -5     # All vitest pass
cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -5  # ~950 pass (slight drop from legacy route removal)
```

Live smoke (manual, optional):
```bash
# Start backend on :5001 + frontend on :5173
# Login → /llm_profiles → create LLM profile
# → /transcribe_profiles → create with qwen3-asr
# → /pipelines → build v5 pipeline with ZH + EN targets
# → Trigger pipeline run on HK clip
# → /proofread/<fid> → switch between ZH / EN tabs
```

---

## Self-review notes

1. **Spec coverage**: §8 frontend mockups (per-target-lang card on Pipelines + override drawer extension on Proofread + Render lang picker) all have tasks (T8, T9, T10). §9 phase split A3 scope (5 profile pages + Pipelines + Proofread + Render + legacy retirement) all have tasks. ✓

2. **Placeholder scan**: No "TBD" / "TODO" / "fill in" in plan body. ✓

3. **Type consistency**:
   - `LlmProfile` / `LlmProfileRow` etc. — consistent across schema files + API client + pages
   - `PipelineV5` / `PipelineV5Row` — consistent
   - `V5Translation` interface used both in `lib/api/v5.ts` and `Proofread/types.ts`
   - `availableLangs` / `activeLang` / `targetLang` — consistent across Proofread components

4. **Glossary cross-lingual UI deferred** to post-A3 — backend v3.15 multilingual schema is ready but Pipelines page doesn't render the multi-glossary picker. Documented in A3 out-of-scope.

5. **AsrProfiles.tsx / MtProfiles.tsx** are renamed via NEW files (TranscribeProfiles + RefinerProfiles); the legacy files are NOT deleted in T4/T6 — only the backend route modules are deleted in T10. Frontend keeps both old file names so during A3 development the frontend continues to work, then T10's router redirect closes the loop.

---

**End of v5-A3 plan.**
