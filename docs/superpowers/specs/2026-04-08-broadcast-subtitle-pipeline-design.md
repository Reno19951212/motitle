# Broadcast Subtitle Pipeline — System Design

## Problem

A Hong Kong broadcast/TV station needs to convert English video content into Traditional Chinese (Cantonese) subtitles. The current project only supports same-language transcription (audio → same-language text). The station requires a professional pipeline: English ASR → Cantonese translation → proof-reading → burnt-in subtitle output, all running locally on open-source models at zero API cost.

## Target Users

Broadcast/TV station operators processing English news clips, programmes, and segments for Cantonese-speaking audiences.

## Environments

| Environment | Hardware | Purpose |
|---|---|---|
| Development | MacBook Pro M1 Pro, 16GB RAM | Testing with small models |
| Production | Dell Pro Max GB10, 128GB unified memory, NVIDIA Blackwell | Full pipeline with large models |

## Architecture Overview

The system is a **pipeline of 7 sub-systems**, each with a clear boundary and interface. Sub-systems communicate through well-defined data structures (see Data Flow section).

```
Input (MXF/MP4)
    │
    ▼
┌─────────────────────┐
│ 1. Profile Router   │  ← selects ASR + Translation model combo
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 2. ASR Pipeline     │  ← English speech → English transcript
│  (Whisper/Qwen3/FLG)│
└────────┬────────────┘
         │ English segments [{start, end, text}]
         ▼
┌─────────────────────┐
│ 3. Translation      │  ← English text → Cantonese text
│  (Qwen3-235B / 3B) │
│  + Glossary inject  │
└────────┬────────────┘
         │ Cantonese segments [{start, end, en_text, zh_text}]
         ▼
┌─────────────────────┐
│ 5. Proof-reading    │  ← Human review & edit
│    Editor UI        │
└────────┬────────────┘
         │ Approved segments
         ▼
┌─────────────────────┐
│ 6. Subtitle Render  │  ← Font config + FFmpeg burn-in
│  + 4. MXF I/O      │
└────────┬────────────┘
         │
         ▼
Output (MXF/MP4 with burnt-in subtitles)
```

## Sub-System Specifications

### Sub-System 1: Model Profile & Routing Engine

**Purpose:** Define reusable "profiles" — each profile specifies which ASR model and which translation model to use, along with their parameters. The system selects the active profile at runtime.

**Profile schema:**
```json
{
  "id": "broadcast-production",
  "name": "Broadcast Production",
  "description": "Full quality for broadcast output",
  "asr": {
    "engine": "qwen3-asr",
    "model_size": "large",
    "language": "en",
    "device": "cuda"
  },
  "translation": {
    "engine": "qwen3-235b",
    "quantization": null,
    "temperature": 0.1,
    "glossary_id": "broadcast-news"
  }
}
```

**Environment-aware defaults:**
- Dev profile: Whisper tiny/base + Qwen2.5-3B (Q4)
- Production profile: Qwen3-ASR large + Qwen3-235B-A22B

**Storage:** Profiles stored as JSON files in `config/profiles/`. One profile is marked as "active" in `config/settings.json`.

**Interface:**
- `get_active_profile() → Profile`
- `list_profiles() → Profile[]`
- `create_profile(data) → Profile`
- `update_profile(id, data) → Profile`
- `delete_profile(id) → void`
- `set_active_profile(id) → void`

**REST endpoints:**
- `GET /api/profiles` — list all
- `POST /api/profiles` — create
- `GET /api/profiles/:id` — get one
- `PATCH /api/profiles/:id` — update
- `DELETE /api/profiles/:id` — delete
- `POST /api/profiles/:id/activate` — set as active

---

### Sub-System 2: ASR Pipeline

**Purpose:** Convert English audio to English text segments with timestamps. Supports multiple ASR engines behind a unified interface.

**Supported engines:**
| Engine | Library | Dev (16GB) | Prod (128GB) |
|---|---|---|---|
| Whisper | faster-whisper / openai-whisper | tiny, base, small | all sizes |
| Qwen3-ASR | transformers / vllm | not feasible | large |
| FLG-ASR | TBD (needs research on integration) | not feasible | large |

**Unified interface:**
```python
class ASREngine(ABC):
    def transcribe(self, audio_path: str, language: str) -> list[Segment]:
        """Returns [{start: float, end: float, text: str}]"""
        pass

    def get_info(self) -> dict:
        """Returns engine name, model size, supported languages."""
        pass
```

Each engine is a concrete implementation. The profile router instantiates the correct engine based on the active profile.

**Audio extraction:** Same as current — FFmpeg extracts 16kHz mono WAV from video input. Supports MP4, MOV, AVI, MKV, WebM, MXF.

---

### Sub-System 3: Translation Pipeline

**Purpose:** Translate English transcript segments into Traditional Chinese (Cantonese).

**Engine:** Local LLM via Ollama or vLLM.
- Dev: Qwen2.5-3B or 7B (Q4 quantized, ~4-6GB RAM)
- Prod: Qwen3-235B-A22B (MoE, ~22B active params)

**Translation approach:**
1. Batch segments into groups (e.g., 10 segments per batch) for context coherence
2. Construct prompt with:
   - System instruction: "Translate English to Traditional Chinese Cantonese (港式粵語)"
   - Glossary terms as few-shot examples (from Sub-System 7)
   - The English segments to translate
3. Parse LLM response back into per-segment translations
4. Validate: each input segment must have exactly one output translation

**Unified interface:**
```python
class TranslationEngine(ABC):
    def translate(self, segments: list[Segment], glossary: list[GlossaryEntry]) -> list[TranslatedSegment]:
        """Returns [{start, end, en_text, zh_text}]"""
        pass
```

**Quality target:** >=97% accuracy. Achieved through:
- Glossary injection (consistent terminology)
- Batch translation (contextual coherence)
- Human proof-reading (Sub-System 5)

---

### Sub-System 4: MXF I/O

**Purpose:** Handle MXF format input and output.

**Input:** FFmpeg already supports MXF decoding. Audio extraction reuses the existing FFmpeg pipeline — no new code needed for input.

**Output:** FFmpeg can mux burnt-in subtitle video back into MXF container. The subtitle renderer (Sub-System 6) produces the video stream; this sub-system wraps it in the correct container format.

**Output formats:**
- MP4 (H.264 + AAC) — web/general use
- MXF (XDCAM HD422 or DNxHD) — broadcast delivery

---

### Sub-System 5: Proof-reading Editor

**Purpose:** UI for human operators to review and correct translated subtitles before rendering.

**Features:**
- Side-by-side view: English original + Cantonese translation
- Video player synced to the current segment (click segment → seek video)
- Inline editing of Cantonese text
- Status per segment: pending / approved / rejected
- Bulk approve (for segments that need no changes)
- "Approve All & Render" button — only enabled when all segments are approved
- Keyboard shortcuts for efficient review (Tab to next, Enter to approve, etc.)

**Builds on existing:** The current frontend already has inline segment editing (v1.5). This sub-system extends it with the dual-language view and approval workflow.

---

### Sub-System 6: Font & Subtitle Renderer

**Purpose:** Burn approved subtitles into the video with configurable font settings.

**Font configuration:**
```json
{
  "font_family": "Noto Sans TC",
  "font_size": 48,
  "font_color": "#FFFFFF",
  "outline_color": "#000000",
  "outline_width": 2,
  "position": "bottom",
  "margin_bottom": 40
}
```

**Rendering:** FFmpeg `drawtext` or `ass` filter. Generate an ASS/SRT file from approved segments, then burn in:
```
ffmpeg -i input.mp4 -vf "subtitles=subs.ass:force_style='FontName=...'" output.mp4
```

**Stored in:** Font settings saved per profile or as global defaults in `config/font.json`.

---

### Sub-System 7: Glossary Manager

**Purpose:** Maintain terminology glossaries that are injected into the translation prompt.

**Glossary entry schema:**
```json
{
  "en": "Legislative Council",
  "zh": "立法會",
  "context": "Hong Kong government institution"
}
```

**Features:**
- CRUD for glossary entries
- Multiple glossaries (e.g., "broadcast-news", "sports", "finance")
- Import/export CSV
- Profile links to a glossary by ID

**REST endpoints:**
- `GET /api/glossaries` — list all
- `POST /api/glossaries` — create
- `GET /api/glossaries/:id` — get with entries
- `POST /api/glossaries/:id/entries` — add entry
- `PATCH /api/glossaries/:id/entries/:eid` — update entry
- `DELETE /api/glossaries/:id/entries/:eid` — delete entry
- `POST /api/glossaries/:id/import` — CSV import
- `GET /api/glossaries/:id/export` — CSV export

---

## Data Flow

```
VideoFile (MXF/MP4)
    │
    │  extract_audio(video) → audio.wav
    ▼
ASREngine.transcribe(audio.wav, "en")
    │
    │  → Segment[] = [{start: 0.0, end: 3.5, text: "Good evening..."}, ...]
    ▼
TranslationEngine.translate(segments, glossary)
    │
    │  → TranslatedSegment[] = [{start: 0.0, end: 3.5, en_text: "Good evening...", zh_text: "各位觀眾晚上好..."}, ...]
    ▼
ProofreadingEditor (human review)
    │
    │  → ApprovedSegment[] (same structure, all status=approved)
    ▼
SubtitleRenderer.render(video, approved_segments, font_config)
    │
    │  → output.mp4 / output.mxf (with burnt-in subtitles)
    ▼
Done
```

## Implementation Order

| Phase | Sub-System | Why First |
|---|---|---|
| Phase 1 | 1. Profile Router | Foundation — everything depends on knowing which model to use |
| Phase 2 | 2. ASR Pipeline | Core input — need English transcript before anything else |
| Phase 3 | 3. Translation Pipeline | Core transform — the main value-add |
| Phase 4 | 7. Glossary Manager | Improves translation quality, needed before proof-reading |
| Phase 5 | 5. Proof-reading Editor | Human QA layer |
| Phase 6 | 6. Subtitle Renderer + 4. MXF I/O | Final output |

Each phase gets its own spec → plan → implementation cycle.

## What Does NOT Change (Yet)

- The existing file upload, live transcription, and streaming features remain functional
- The current frontend structure (single HTML file) — will be evaluated for splitting when proof-reading editor is designed in detail
- Backend framework (Flask + SocketIs

## Open Questions (To Resolve in Phase Specs)

- FLG-ASR integration details — library, API, model format (needs research)
- Exact MXF codec requirements for broadcast delivery (XDCAM HD422? DNxHD?)
- Whether to use Ollama or vLLM for local LLM serving (depends on GB10 compatibility)
- Frontend: keep single-file or split into components when adding proof-reading editor
