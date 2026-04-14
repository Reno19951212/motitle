# Ollama Cloud Models Support — Design Spec

**Date:** 2026-04-14
**Status:** Approved (brainstorming phase complete)
**Scope:** Add three Ollama Cloud models as selectable options in 翻譯設定 ▶ 引擎

---

## 1. Goal

Enable users to select high-capacity Ollama Cloud models for subtitle translation without modifying the existing local Ollama workflow. The three target models are:

| Friendly key | Ollama tag | Context | Notes |
|---|---|---|---|
| `glm-4.6-cloud` | `glm-4.6:cloud` | 198K | Non-thinking, fast response |
| `qwen3.5-397b-cloud` | `qwen3.5:397b-cloud` | 256K | MoE; triggers `_is_thinking_model()` — runs with `think=false` by default |
| `gpt-oss-120b-cloud` | `gpt-oss:120b-cloud` | 128K | OpenAI MoE, non-thinking |

All three are accessed via the existing `http://localhost:11434/api/chat` endpoint after the user runs `ollama signin` once — the Ollama CLI transparently proxies cloud model requests.

## 2. Non-Goals

- No new standalone `ollama_cloud` engine class (rejected in favor of minimal diff)
- No API-key management UI (Ollama CLI handles auth via `ollama signin`)
- No changes to `profiles.py` schema (existing structure accommodates new engine keys)
- No dynamic timeout adjustment for cloud models (keep 120s hard-coded)
- No `<option disabled>` or hard blocking — visual hints only

## 3. Architecture

### 3.1 Backend — `backend/translation/ollama_engine.py`

**`ENGINE_TO_MODEL` gains three entries:**

```python
ENGINE_TO_MODEL = {
    "qwen2.5-3b": "qwen2.5:3b",
    "qwen2.5-7b": "qwen2.5:7b",
    "qwen2.5-72b": "qwen2.5:72b",
    "qwen3-235b": "qwen3:235b",
    "qwen3.5-9b": "qwen3.5:9b",
    "glm-4.6-cloud": "glm-4.6:cloud",
    "qwen3.5-397b-cloud": "qwen3.5:397b-cloud",
    "gpt-oss-120b-cloud": "gpt-oss:120b-cloud",
}

CLOUD_ENGINES = frozenset({
    "glm-4.6-cloud",
    "qwen3.5-397b-cloud",
    "gpt-oss-120b-cloud",
})
```

**`get_models()` returns `is_cloud` flag:**

```python
def get_models(self) -> list:
    return [
        {
            "engine": engine_key,
            "model": model_tag,
            "available": self._check_model_available(model_tag),
            "is_cloud": engine_key in CLOUD_ENGINES,
        }
        for engine_key, model_tag in ENGINE_TO_MODEL.items()
    ]
```

**Thinking mode — `_is_thinking_model()` unchanged:**

The existing `startswith("qwen3")` check already covers `qwen3.5:397b-cloud`. Default `think=False` (via `self._config.get("think", False)`) keeps response time practical.

- `qwen3.5:397b-cloud` → matches → `think=False` inserted ✓
- `gpt-oss:120b-cloud` → does not match → no `think` key ✓
- `glm-4.6:cloud` → does not match → no `think` key ✓

**Timeout — unchanged:**

`urllib.request.urlopen(req, timeout=120)` remains hard-coded at 120s. Cloud models are hosted on data-center GPUs and typically respond faster than large local MoE models. If cloud latency issues arise in production, revisit.

**Availability check — unchanged (with verification step at implementation time):**

`_check_model_available()` queries `http://localhost:11434/api/tags`. Ollama documentation states that cloud models "behave like regular models" and appear in `ollama ls` after `ollama signin`. Since `ollama ls` and the `/api/tags` HTTP endpoint both query the same local daemon, cloud models should surface via `/api/tags` without code changes.

**Verification step (must run during implementation):**
1. Before writing the feature, run `curl -s http://localhost:11434/api/tags` without signin — confirm no cloud tags.
2. Run `ollama signin` and then `curl -s http://localhost:11434/api/tags` — confirm cloud model tags (e.g. `glm-4.6:cloud`, `gpt-oss:120b-cloud`) appear in the `models[].name` list.
3. If step 2 does NOT show cloud tags, the spec is wrong on this point and availability detection needs a fallback (e.g. probing `ollama ps` / `ollama list` via subprocess, or hard-coding `available: true` for cloud engines when `ollama whoami` reports signed-in state). Flag to user and revise spec before continuing.

Unsigned users will see `available: false` for cloud entries regardless, which is the correct UI behavior.

### 3.2 Frontend — `frontend/index.html`

The engine-model dropdown currently renders as a flat `<select>`. Change the render path to group options by `is_cloud`:

```js
function renderTranslationModels(models) {
  const select = document.getElementById('translationModel');
  select.innerHTML = '';

  const local = models.filter(m => !m.is_cloud);
  const cloud = models.filter(m => m.is_cloud);

  if (local.length) {
    const group = document.createElement('optgroup');
    group.label = '本地模型';
    local.forEach(m => group.appendChild(buildOption(m)));
    select.appendChild(group);
  }

  if (cloud.length) {
    const group = document.createElement('optgroup');
    group.label = '雲端模型（需要 ollama signin）';
    cloud.forEach(m => group.appendChild(buildOption(m)));
    select.appendChild(group);
  }
}

function buildOption(m) {
  const opt = document.createElement('option');
  opt.value = m.engine;
  const status = m.available ? '✓' : '⚠';
  opt.textContent = `${status} ${m.engine}`;
  if (!m.available) {
    opt.title = m.is_cloud
      ? '需要先執行 `ollama signin` 登入 Ollama Cloud'
      : `需要先執行 \`ollama pull ${m.model}\``;
  }
  return opt;
}
```

**UX matrix:**

| State | Display | Tooltip |
|---|---|---|
| Local pulled | `✓ qwen3.5-9b` | — |
| Local not pulled | `⚠ qwen2.5-72b` | `需要先執行 ollama pull qwen2.5:72b` |
| Cloud signed-in | `✓ gpt-oss-120b-cloud` | — |
| Cloud not signed-in | `⚠ gpt-oss-120b-cloud` | `需要先執行 ollama signin 登入 Ollama Cloud` |

Unavailable options remain selectable — attempting translation raises `ConnectionError` with a clear message from existing error handling.

**Implementation note:** The exact location of the current dropdown render function in `frontend/index.html` is to be located via Grep during implementation (`translationModel` / `translation_engine` / relevant render function). The spec reflects the intended pattern, not exact line numbers.

## 4. Testing

All test changes live in `backend/tests/test_translation.py`.

### 4.1 Update existing test

**`test_ollama_engine_get_models_mocked`** — expand expected model count and assert `is_cloud` field:
- Change expected `len(models) == 5` → `8`
- Assert `is_cloud == True` for the three cloud keys
- Assert `is_cloud == False` for all existing local keys

### 4.2 New tests

**`test_ollama_cloud_qwen_model_is_thinking_detected`**
- Construct engine with `config={"engine": "qwen3.5-397b-cloud"}`
- Assert `engine._is_thinking_model() == True`

**`test_ollama_cloud_qwen_request_body_has_think_false`**
- Mock `urllib.request.urlopen` to capture request body
- Construct engine with `qwen3.5-397b-cloud`
- Call `translate()` on a single segment
- Parse captured payload JSON
- Assert `body["think"] == False`

**`test_ollama_gpt_oss_cloud_not_thinking_model`**
- Construct engine with `gpt-oss-120b-cloud`
- Assert `engine._is_thinking_model() == False`
- Assert captured request body has no `think` key

**`test_ollama_glm_cloud_not_thinking_model`**
- Same pattern as above but for `glm-4.6-cloud`

**`test_ollama_cloud_models_marked_is_cloud`** (dedicated flag test)
- Mock `_check_model_available` to return `True` for all
- Assert that exactly `{glm-4.6-cloud, qwen3.5-397b-cloud, gpt-oss-120b-cloud}` have `is_cloud == True`
- Assert all other entries have `is_cloud == False`

## 5. Documentation Updates

### 5.1 `CLAUDE.md`

Add to v3.0 feature history:
> - **Ollama Cloud 模型支援**：新增 3 個 cloud engine（`glm-4.6-cloud`、`qwen3.5-397b-cloud`、`gpt-oss-120b-cloud`），透過現有 Ollama CLI `signin` 機制存取；前端 dropdown 分「本地模型」同「雲端模型（需要 ollama signin）」兩組，未可用嘅選項顯示 `⚠` + tooltip 提示。

### 5.2 `README.md`（繁體中文）

翻譯引擎章節新增一段：
> ### Ollama Cloud 模型（選用）
> 系統支援三個 Ollama Cloud 模型，可提供更高質素嘅翻譯結果：
> - **glm-4.6-cloud** — 通用中英翻譯
> - **qwen3.5-397b-cloud** — Qwen 系列最大 MoE，粵語翻譯質素最高
> - **gpt-oss-120b-cloud** — OpenAI 開源 MoE
>
> 使用前需要登入 Ollama Cloud（付費服務）：
> ```bash
> ollama signin
> ```
> 登入後雲端模型會自動出現喺翻譯引擎選單，唔需要 `ollama pull`。

## 6. Out of Scope / Deferred

- **API-key based direct cloud access** — current design依賴 `ollama signin`（localhost proxy path）。如果將來要支援 headless server 直接 call `https://ollama.com/api/chat` + Bearer token，需要獨立 `ollama_cloud` engine class。
- **Cloud-specific timeouts or retry policies** — defer until real-world usage shows problems.
- **Profile migration** — 現有用戶 profile 保持可用，唔需要 schema change。

## 7. Acceptance Criteria

- [ ] `ENGINE_TO_MODEL` 有 8 entries（5 local + 3 cloud）
- [ ] `get_models()` 每個 entry 返回 `is_cloud` boolean
- [ ] `qwen3.5:397b-cloud` 觸發 `_is_thinking_model() == True` 且 request body 包含 `think: false`
- [ ] `glm-4.6:cloud` 同 `gpt-oss:120b-cloud` 嘅 request body 冇 `think` key
- [ ] 前端 dropdown 分兩組顯示（本地 / 雲端）
- [ ] 未 signin / 未 pull 嘅 entry 顯示 `⚠` 同正確 tooltip
- [ ] `backend/tests/test_translation.py` 全部 PASS（含更新同新 test）
- [ ] `CLAUDE.md` 同 `README.md` 已更新
