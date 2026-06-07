# Admin Beta 測試模式（OpenRouter 雲端模型）Implementation Plan

> **Status (2026-06-07):** Tasks 1–5 + close-out done. Beta shipped as **LLM-only** (翻譯 / 書面語 refiner → OpenRouter `qwen/qwen3.5-35b-a3b`; ASR stays local). ASR-on-OpenRouter Tasks 6/7 **CANCELLED** by Phase 0 gate — OpenRouter's `/api/v1/audio/transcriptions` returns no segment/word timestamps; see [docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md](../specs/2026-06-07-beta-openrouter-validation-tracker.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 喺 Admin User 區加一個全局 Beta 測試模式開關，開啟後將 output_lang pipeline 嘅 ASR（Whisper）+ LLM（Qwen3.5-A3B）由本地切換去 OpenRouter 雲端。

**Architecture:** Flag-gated 注入 —— 一個 `settings.json` 全局 flag，喺現有兩個 override 接縫（`_make_ollama_llm_call` / `_output_lang_asr_override`）檢查。LLM 半邊複用現成 `OpenRouterTranslationEngine`；ASR 半邊新起一個 `OpenRouterWhisperEngine(ASREngine)`。`crosslang_mt` / `formal_refine` / dispatch 零改動。

**Tech Stack:** Python 3.8+ (Flask, urllib), Vanilla JS frontend, OpenRouter `/api/v1/audio/transcriptions` + `/chat/completions`, pytest.

**Design spec:** [docs/superpowers/specs/2026-06-07-beta-openrouter-mode-design.md](../specs/2026-06-07-beta-openrouter-mode-design.md)

**Reference (read before starting):**
- Settings I/O: `backend/profiles.py:405-435`（`_read_settings`/`_write_settings`/`set_global_font` pattern）
- ASR ABC + factory: `backend/asr/__init__.py`（`ASREngine` / `Word` / `create_asr_engine`）
- LLM/ASR 注入點: `backend/app.py:302-331`（`_output_lang_asr_override` / `_make_ollama_llm_call`）
- ASR engine 選擇: `backend/app.py:1517-1614`（override → `use_profile_engine` → `create_asr_engine` → `engine.transcribe`）
- OpenRouter engine: `backend/translation/openrouter_engine.py:91-195`（constructor + `_call_ollama`）
- Admin route pattern: `backend/auth/admin.py:102-131`（`@admin_required` + `log_audit`）
- Profile manager on app config: `backend/app.py:1105`（`app.config["PROFILE_MANAGER"]`）
- Frontend nav/pane: `frontend/user.html:251-322` + `frontend/js/user.js:44-92`

> **Test isolation note**：呢個 repo full-suite 有已知 order-dependent 失敗。驗 regression 只**單獨跑你改到嘅 test file**，唔好信 full-suite 紅字。

---

## Task 1: Validation-First Phase 0 — OpenRouter Whisper timestamp 實測（ASR 硬 gate）

> CLAUDE.md 強制：落任何 ASR engine 代碼之前，必須先 empirical 驗證並記錄。呢個 task 係 **Task 6/7 嘅硬 gate**。LLM 半邊（Task 2-5）唔受此 gate 阻擋。

**Files:**
- Create: `backend/scripts/validate_openrouter_whisper.py`
- Create: `docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md`

- [ ] **Step 1: 寫驗證 script**

```python
# backend/scripts/validate_openrouter_whisper.py
"""Validation-First Phase 0 — 實測 OpenRouter openai/whisper-large-v3 嘅 transcription
回應，確定有冇 segment / word timestamp，同記錄實際 JSON shape。

跑法（需要 key）：
    export OPENROUTER_API_KEY=sk-or-...
    python backend/scripts/validate_openrouter_whisper.py <audio.wav>

結果人手抄入 docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md。
"""
import base64
import json
import os
import sys
import time
import urllib.request

MODEL = "openai/whisper-large-v3"
BASE = "https://openrouter.ai/api/v1"


def _post(payload: dict) -> dict:
    key = os.environ["OPENROUTER_API_KEY"]
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/audio/transcriptions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(audio_path: str) -> None:
    with open(audio_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    fmt = audio_path.rsplit(".", 1)[-1].lower()

    # Probe A: 要求 verbose_json + segment/word timestamp（OpenAI Whisper 標準形）
    payload = {
        "model": MODEL,
        "input_audio": {"data": b64, "format": fmt},
        "language": "en",
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment", "word"],
    }
    t0 = time.time()
    try:
        out = _post(payload)
    except urllib.error.HTTPError as e:
        print("HTTPError", e.code, e.read().decode("utf-8", "replace"))
        return
    dt = time.time() - t0

    keys = sorted(out.keys())
    has_segments = isinstance(out.get("segments"), list) and out["segments"]
    has_words = isinstance(out.get("words"), list) and out["words"]
    print(f"latency_sec={dt:.1f}")
    print(f"top_level_keys={keys}")
    print(f"has_segment_timestamps={bool(has_segments)}")
    print(f"has_word_timestamps={bool(has_words)}")
    if has_segments:
        print("first_segment=", json.dumps(out["segments"][0], ensure_ascii=False))
    if has_words:
        print("first_word=", json.dumps(out["words"][0], ensure_ascii=False))
    print("text_preview=", (out.get("text") or "")[:160])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python validate_openrouter_whisper.py <audio.wav>")
        sys.exit(1)
    main(sys.argv[1])
```

- [ ] **Step 2: 跑驗證（需要真 key + 一段測試 clip）**

Run:
```bash
cd backend
export OPENROUTER_API_KEY=sk-or-...        # 由操作者提供
python scripts/validate_openrouter_whisper.py <已知測試.wav>
```
Expected: 印出 `has_segment_timestamps=True/False`、`first_segment=...`、latency。若 Probe A 嘅 `response_format`/`timestamp_granularities` 被 reject（HTTPError 400），記低錯誤訊息，再試淨係 base payload（去走嗰兩個 param）睇返咩 shape。

- [ ] **Step 3: 記錄結果入 tracker**

寫入 `docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md`，內容包括：
- 用咩 request param 攞到 timestamp（確認 Task 6 engine 要用嘅 request body 形狀）
- 實際回應 JSON shape（segment 物件嘅 field 名：`start`/`end`/`text`？）
- ✅ Validated / ❌ Rejected / ⚠️ Partial 標記，每項一行
- 轉錄質素 + latency vs 本地 mlx-whisper large-v3 嘅 directional 觀察

Tracker 起始內容：
```markdown
# Beta OpenRouter Validation Tracker — 2026-06-07

Production stack 對齊：ASR = OpenRouter `openai/whisper-large-v3` vs 本地 mlx-whisper large-v3。

## V1 — OpenRouter whisper 回應有冇 segment timestamp（ASR 硬 gate）
- 狀態：⬜ 待跑
- Request param：（填 Probe A 定 base payload 成功）
- 回應 shape：（填 top_level_keys + first_segment）
- 結論：✅/❌/⚠️

## V2 — word-level timestamp
- 狀態：⬜ 待跑
- 結論：✅/❌/⚠️

## V3 — 轉錄質素 + latency vs 本地 large-v3
- 狀態：⬜ 待跑
- 觀察：
```

- [ ] **Step 4: GATE 判定**

- **若 V1 = ✅（有 segment `{start,end}`）** → Task 6/7 可進行；將確認嘅 request param 形狀同 segment field 名帶入 Task 6。
- **若 V1 = ❌（淨係 flat text，無 segment timestamp）** → **停 Task 6/7**。回報用戶，按 design §7 fallback：Beta 只切 LLM（Task 2-5 已足夠交付），ASR 留本地。喺 tracker 寫明 gate 否決理由。

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/validate_openrouter_whisper.py docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md
git commit -m "test: Validation-First Phase 0 — OpenRouter whisper timestamp probe + tracker"
```

---

## Task 2: `beta_mode` module + ProfileManager flag

**Files:**
- Create: `backend/beta_mode.py`
- Modify: `backend/profiles.py`（喺 `set_global_font` 之後，line 435 附近加兩個 method）
- Test: `backend/tests/test_beta_mode.py`

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_beta_mode.py
import os
import json
from pathlib import Path

import beta_mode
from profiles import ProfileManager


def test_beta_model_constants_are_parity():
    assert beta_mode.BETA_ASR_MODEL == "openai/whisper-large-v3"
    assert beta_mode.BETA_LLM_MODEL == "qwen/qwen3.5-35b-a3b"


def test_profile_manager_beta_flag_roundtrip(tmp_path):
    pm = ProfileManager(tmp_path)
    assert pm.get_beta_mode() is False           # default off
    assert pm.set_beta_mode(True) is True
    assert pm.get_beta_mode() is True
    # persisted to settings.json, other keys preserved
    pm.set_beta_mode(False)
    assert pm.get_beta_mode() is False


def test_set_key_writes_env_and_environ(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("FLASK_SECRET_KEY=abc\n", encoding="utf-8")
    monkeypatch.setattr(beta_mode, "_ENV_PATH", env_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert beta_mode.key_status() is False
    beta_mode.set_key("sk-or-test")
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-test"
    assert beta_mode.key_status() is True
    content = env_path.read_text(encoding="utf-8")
    assert "FLASK_SECRET_KEY=abc" in content          # other line preserved
    assert "OPENROUTER_API_KEY=sk-or-test" in content


def test_set_key_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(beta_mode, "_ENV_PATH", tmp_path / ".env")
    import pytest
    with pytest.raises(ValueError):
        beta_mode.set_key("   ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_beta_mode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beta_mode'` / `AttributeError: get_beta_mode`.

- [ ] **Step 3: 寫 `backend/beta_mode.py`**

```python
# backend/beta_mode.py
"""Central state + constants for the Admin Beta test mode (OpenRouter cloud models).

Beta mode is a single global flag (settings.json 'beta_openrouter'). When ON, the
output_lang pipeline's ASR + LLM route to OpenRouter instead of local mlx-whisper /
Ollama. Model ids are hardcoded parity with the local production stack.
"""
import os
from pathlib import Path

# Hardcoded parity with the local production stack (not user-editable).
BETA_ASR_MODEL = "openai/whisper-large-v3"
BETA_LLM_MODEL = "qwen/qwen3.5-35b-a3b"

_ENV_PATH = Path(__file__).parent / ".env"   # backend/.env (gitignored)
_KEY_NAME = "OPENROUTER_API_KEY"


def key_status() -> bool:
    """True when an OpenRouter API key is present in the environment."""
    return bool(os.environ.get(_KEY_NAME))


def set_key(key: str) -> None:
    """Persist OPENROUTER_API_KEY to backend/.env (preserving other lines) and set
    it in os.environ so the running process picks it up immediately."""
    key = (key or "").strip()
    if not key:
        raise ValueError("OpenRouter API key cannot be empty")
    _write_env_var(_ENV_PATH, _KEY_NAME, key)
    os.environ[_KEY_NAME] = key


def _write_env_var(path: Path, name: str, value: str) -> None:
    """Set name=value in a .env file, preserving every other line. Creates the file
    if missing. Builds a NEW content string (no in-place mutation)."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = name + "="
    new_line = f"{name}={value}"
    out, replaced = [], False
    for ln in lines:
        if ln.startswith(prefix):
            out.append(new_line)
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(new_line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
```

- [ ] **Step 4: 加 ProfileManager flag methods（`backend/profiles.py`，緊接 `set_global_font` 之後）**

```python
    def get_beta_mode(self) -> bool:
        """Global Beta test mode flag (settings.json 'beta_openrouter'). Default False."""
        return bool(self._read_settings().get("beta_openrouter", False))

    def set_beta_mode(self, enabled: bool) -> bool:
        """Persist the Beta mode flag (immutable update — other keys preserved).
        Returns the new boolean value."""
        settings = self._read_settings()
        self._write_settings({**settings, "beta_openrouter": bool(enabled)})
        return bool(enabled)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_beta_mode.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/beta_mode.py backend/profiles.py backend/tests/test_beta_mode.py
git commit -m "feat(beta): beta_mode module + ProfileManager global flag"
```

---

## Task 3: Admin API endpoints（GET/PUT `/api/admin/beta-mode`）

**Files:**
- Modify: `backend/auth/admin.py`（top import + 喺檔案末尾加兩個 route）
- Test: `backend/tests/test_admin_beta_mode.py`

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_admin_beta_mode.py
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test")   # app.py requires it at import time
import json
import pytest

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    flask_app = app_module.app
    flask_app.config["R5_AUTH_BYPASS"] = True            # skip @admin_required
    flask_app.config["TESTING"] = True
    # isolate settings + env from the real machine
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    flask_app.config["PROFILE_MANAGER"] = pm
    monkeypatch.setattr(app_module, "_profile_manager", pm, raising=False)
    import beta_mode
    monkeypatch.setattr(beta_mode, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return flask_app.test_client()


def test_get_beta_mode_default(client):
    r = client.get("/api/admin/beta-mode")
    assert r.status_code == 200
    data = r.get_json()
    assert data["enabled"] is False
    assert data["key_configured"] is False
    assert data["asr_model"] == "openai/whisper-large-v3"
    assert data["llm_model"] == "qwen/qwen3.5-35b-a3b"


def test_enable_without_key_is_400(client):
    r = client.put("/api/admin/beta-mode", json={"enabled": True})
    assert r.status_code == 400


def test_set_key_then_enable(client):
    r1 = client.put("/api/admin/beta-mode", json={"api_key": "sk-or-x", "enabled": True})
    assert r1.status_code == 200
    body = r1.get_json()
    assert body["enabled"] is True
    assert body["key_configured"] is True
    # GET reflects the persisted flag
    assert client.get("/api/admin/beta-mode").get_json()["enabled"] is True


def test_empty_key_is_400(client):
    r = client.put("/api/admin/beta-mode", json={"api_key": "   "})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_admin_beta_mode.py -v`
Expected: FAIL — 404 on the new routes (not yet defined).

- [ ] **Step 3: 加 import + routes（`backend/auth/admin.py`）**

喺檔案 top（line 12 `from auth.audit import log_audit` 之後）加：
```python
import beta_mode
```

喺檔案末尾加：
```python
@bp.get("/api/admin/beta-mode")
@admin_required
def get_beta_mode_route():
    pm = current_app.config["PROFILE_MANAGER"]
    return jsonify({
        "enabled": pm.get_beta_mode(),
        "key_configured": beta_mode.key_status(),
        "asr_model": beta_mode.BETA_ASR_MODEL,
        "llm_model": beta_mode.BETA_LLM_MODEL,
    }), 200


@bp.put("/api/admin/beta-mode")
@admin_required
def update_beta_mode_route():
    pm = current_app.config["PROFILE_MANAGER"]
    data = request.get_json(silent=True) or {}

    if "api_key" in data:
        try:
            beta_mode.set_key(data.get("api_key") or "")
        except ValueError:
            return jsonify({"error": "OpenRouter API key 不能為空"}), 400

    enabled = bool(data.get("enabled", pm.get_beta_mode()))
    if enabled and not beta_mode.key_status():
        return jsonify({"error": "請先設定 OpenRouter API key 先可以開啟 Beta 模式"}), 400

    pm.set_beta_mode(enabled)
    log_audit(current_app.config["AUTH_DB_PATH"], actor_id=current_user.id,
              action="beta.toggle", target_kind="settings", target_id="beta_openrouter",
              details={"enabled": enabled})
    return jsonify({
        "enabled": enabled,
        "key_configured": beta_mode.key_status(),
        "asr_model": beta_mode.BETA_ASR_MODEL,
        "llm_model": beta_mode.BETA_LLM_MODEL,
    }), 200
```

> 註：`log_audit` 喺 R5_AUTH_BYPASS 測試下 `current_user` 係 AnonymousUser（無 `.id`）。test 用 bypass，`current_user.id` 會 AttributeError。**所以 test fixture 唔好觸發 audit 失敗** —— 改用：log_audit 包一個 try/except 防護，或測試只斷言 status_code。為求穩陣，將 `log_audit(...)` 行包：
```python
    try:
        log_audit(current_app.config["AUTH_DB_PATH"], actor_id=getattr(current_user, "id", None),
                  action="beta.toggle", target_kind="settings", target_id="beta_openrouter",
                  details={"enabled": enabled})
    except Exception:
        pass
```
用呢個防護版本取代上面 plain `log_audit` 呼叫。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_admin_beta_mode.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/auth/admin.py backend/tests/test_admin_beta_mode.py
git commit -m "feat(beta): admin GET/PUT /api/admin/beta-mode endpoints"
```

---

## Task 4: Frontend Beta pane（`user.html` + `user.js`）

**Files:**
- Modify: `frontend/user.html`（nav item + pane）
- Modify: `frontend/js/user.js`（reveal + load/save）

> 此 repo 前端無 build step、無前端 unit test framework。驗證靠 curl（Task 8 smoke）+ 人手。本 task 無自動 test step。

- [ ] **Step 1: 加 nav item（`frontend/user.html`，line 256 `navAudit` 之後）**

```html
            <div class="u-nav-item" id="navBeta" data-pane="beta" hidden><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.5l1.8 3.8 4.2.5-3 2.9.7 4.1L8 11.4 4.3 12.8l.7-4.1-3-2.9 4.2-.5z"/></svg>Beta 測試模式</div>
```

- [ ] **Step 2: 加 pane（`frontend/user.html`，line 322 `pane-audit` 收尾 `</div>` 之後、`</div>` (u-content) 之前）**

```html
            <!-- PANE: beta -->
            <div class="u-pane" id="pane-beta">
              <div class="pane-head"><div class="h-title">Beta 測試模式</div><div class="h-sub">將後台 ASR + LLM 切換去 OpenRouter 雲端 · Cloud model test mode</div></div>
              <section class="ucard" id="betaSection">
                <div class="ucard-head"><span class="lead"></span>OpenRouter 雲端模型</div>
                <div class="pw-hint" style="margin-bottom:14px;"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><path d="M8 5.5v3M8 11h0"/></svg>開啟後，語音轉文字（Whisper）同翻譯/書面語（Qwen3.5）會改用 OpenRouter 雲端，按用量計費。失敗唔會自動退回本地。</div>
                <div class="field" style="margin-bottom:12px;">
                  <label style="display:flex;align-items:center;gap:10px;cursor:pointer;">
                    <input type="checkbox" id="betaEnabled"> <b>啟用 Beta 測試模式</b>
                  </label>
                </div>
                <div class="field" style="margin-bottom:12px;">
                  <label>OpenRouter API Key</label>
                  <input type="password" id="betaApiKey" placeholder="sk-or-…（留空 = 不變更）" autocomplete="off">
                  <div class="pw-hint" id="betaKeyStatus" style="margin-top:6px;"></div>
                </div>
                <div class="field" style="margin-bottom:12px;font-size:12.5px;color:var(--text-dim);">
                  <div>ASR 模型：<span id="betaAsrModel" style="font-family:var(--font-mono);">—</span></div>
                  <div>LLM 模型：<span id="betaLlmModel" style="font-family:var(--font-mono);">—</span></div>
                </div>
                <button type="button" class="btn-primary" id="betaSaveBtn" style="align-self:flex-start;">儲存</button>
                <span id="betaMsg" class="pw-msg"></span>
              </section>
            </div>
```

- [ ] **Step 3: 加 reveal + load/save JS（`frontend/js/user.js`）**

喺 `loadMe()` 嘅 admin block（line 85-91）內，`loadAudit();` 之後加：
```javascript
    document.getElementById('navBeta').hidden = false;
    loadBetaMode();
```

喺檔案末尾加：
```javascript
// ---- beta test mode (admin) ----
async function loadBetaMode() {
  const r = await fetch('/api/admin/beta-mode', { credentials: 'same-origin' });
  if (!r.ok) return;
  const d = await r.json();
  document.getElementById('betaEnabled').checked = !!d.enabled;
  document.getElementById('betaAsrModel').textContent = d.asr_model || '—';
  document.getElementById('betaLlmModel').textContent = d.llm_model || '—';
  document.getElementById('betaKeyStatus').textContent =
    d.key_configured ? '✓ API key 已設定' : '✕ 未設定 API key';
}

document.getElementById('betaSaveBtn').addEventListener('click', async () => {
  const msg = document.getElementById('betaMsg');
  msg.textContent = ''; msg.className = 'pw-msg';
  const body = { enabled: document.getElementById('betaEnabled').checked };
  const key = document.getElementById('betaApiKey').value.trim();
  if (key) body.api_key = key;
  const r = await fetch('/api/admin/beta-mode', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin', body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (r.ok) {
    msg.textContent = '✓ 已儲存'; msg.className = 'pw-msg ok';
    document.getElementById('betaApiKey').value = '';
    showToast('Beta 設定已儲存', 'success');
    loadBetaMode();
  } else {
    msg.textContent = '✕ ' + (d.error || `HTTP ${r.status}`); msg.className = 'pw-msg err';
  }
});
```

- [ ] **Step 4: 人手驗證**

啟動 backend，admin 登入 `/user.html`，確認左側出現「Beta 測試模式」分頁、可開關、輸入 key 儲存後狀態變「✓ API key 已設定」、開 toggle 無 key 時顯示 400 錯誤。

- [ ] **Step 5: Commit**

```bash
git add frontend/user.html frontend/js/user.js
git commit -m "feat(beta): admin Beta test mode pane (toggle + API key + status)"
```

---

## Task 5: LLM 注入（flag 開 → OpenRouter Qwen3.5）— 不受 ASR gate 阻擋

**Files:**
- Modify: `backend/app.py:328-331`（`_make_ollama_llm_call`）
- Test: `backend/tests/test_beta_llm_injection.py`

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_beta_llm_injection.py
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test")   # app.py requires it at import time
import pytest
import app as app_module
from profiles import ProfileManager


@pytest.fixture
def pm(tmp_path, monkeypatch):
    m = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", m, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    return m


def test_llm_call_uses_openrouter_when_beta_on(pm, monkeypatch):
    pm.set_beta_mode(True)
    captured = {}

    class FakeEng:
        def __init__(self, cfg): captured["cfg"] = cfg
        def _call_ollama(self, system, user, temp):
            captured["temp"] = temp
            return "OR-RESULT"

    import translation.openrouter_engine as ore
    monkeypatch.setattr(ore, "OpenRouterTranslationEngine", FakeEng)

    call = app_module._make_ollama_llm_call()
    assert call("sys", "usr") == "OR-RESULT"
    assert captured["cfg"]["openrouter_model"] == "qwen/qwen3.5-35b-a3b"
    assert captured["temp"] == 0.3


def test_llm_call_uses_ollama_when_beta_off(pm, monkeypatch):
    pm.set_beta_mode(False)
    sentinel = object()
    monkeypatch.setattr(app_module, "_make_ollama_llm_call_engine",
                        lambda: type("E", (), {"_call_ollama": lambda self, s, u, t: "LOCAL"})())
    call = app_module._make_ollama_llm_call()
    assert call("sys", "usr") == "LOCAL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_beta_llm_injection.py -v`
Expected: FAIL — `test_llm_call_uses_openrouter_when_beta_on` returns local Ollama result, not "OR-RESULT".

- [ ] **Step 3: 改 `_make_ollama_llm_call`（`backend/app.py:328-331`）**

```python
def _make_ollama_llm_call():
    """(system, user) -> str LLM client for cross-lang MT + the 書面語 refiner.

    Beta test mode ON → route to OpenRouter (qwen/qwen3.5-35b-a3b); same temp 0.3
    for parity. OFF → local Ollama (unchanged).
    """
    if _profile_manager.get_beta_mode():
        import beta_mode
        from translation.openrouter_engine import OpenRouterTranslationEngine
        eng = OpenRouterTranslationEngine({
            "openrouter_model": beta_mode.BETA_LLM_MODEL,
            "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        })
        return lambda system, user: eng._call_ollama(system, user, 0.3)
    eng = _make_ollama_llm_call_engine()
    return lambda system, user: eng._call_ollama(system, user, 0.3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_beta_llm_injection.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_beta_llm_injection.py
git commit -m "feat(beta): route output_lang LLM to OpenRouter when beta mode on"
```

---

## Task 6: `OpenRouterWhisperEngine` + factory（⚠️ 需 Task 1 V1 = ✅）— ❌ CANCELLED (Phase 0 gate)

> **GATE**：只有 Task 1 tracker V1 標 ✅（OpenRouter whisper 返到 segment timestamp）先做呢個 task。下面 `_map_response` 用 OpenAI verbose_json 標準形（`segments:[{start,end,text}]`）—— **以 Task 1 tracker 記錄嘅實際 field 名為準**，若不同就同步改 Step 1 test + Step 3 code。

**Files:**
- Create: `backend/asr/openrouter_whisper_engine.py`
- Modify: `backend/asr/__init__.py:43-56`（factory mapping）
- Test: `backend/tests/test_openrouter_whisper_engine.py`

- [ ] **Step 1: 寫 failing test（mock HTTP，唔打真網絡）**

```python
# backend/tests/test_openrouter_whisper_engine.py
import json
import pytest


def _fake_response(payload):
    """Build a urlopen context-manager stub returning JSON bytes."""
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(payload).encode("utf-8")
    return _Ctx()


def test_maps_verbose_json_to_segments(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    from asr.openrouter_whisper_engine import OpenRouterWhisperEngine
    eng = OpenRouterWhisperEngine({"engine": "openrouter-whisper",
                                   "model": "openai/whisper-large-v3"})

    payload = {"text": "hello world",
               "segments": [{"start": 0.0, "end": 1.2, "text": "hello"},
                            {"start": 1.2, "end": 2.4, "text": "world"}],
               "words": [{"word": "hello", "start": 0.0, "end": 0.6},
                         {"word": "world", "start": 1.2, "end": 1.8}]}
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _fake_response(payload))

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFxxxx")
    segs = eng.transcribe(str(audio), language="en")
    assert len(segs) == 2
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 1.2 and segs[0]["text"] == "hello"
    assert segs[0]["words"][0]["word"] == "hello"


def test_missing_segments_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    from asr.openrouter_whisper_engine import OpenRouterWhisperEngine
    eng = OpenRouterWhisperEngine({"engine": "openrouter-whisper", "model": "openai/whisper-large-v3"})
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=0: _fake_response({"text": "flat only"}))
    audio = tmp_path / "a.wav"; audio.write_bytes(b"RIFFxxxx")
    with pytest.raises(RuntimeError):
        eng.transcribe(str(audio), language="en")


def test_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from asr.openrouter_whisper_engine import OpenRouterWhisperEngine
    with pytest.raises(RuntimeError):
        OpenRouterWhisperEngine({"engine": "openrouter-whisper", "model": "openai/whisper-large-v3"})


def test_factory_creates_engine(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    from asr import create_asr_engine
    from asr.openrouter_whisper_engine import OpenRouterWhisperEngine
    eng = create_asr_engine({"engine": "openrouter-whisper", "model": "openai/whisper-large-v3"})
    assert isinstance(eng, OpenRouterWhisperEngine)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_openrouter_whisper_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: asr.openrouter_whisper_engine`.

- [ ] **Step 3: 寫 `backend/asr/openrouter_whisper_engine.py`**

```python
# backend/asr/openrouter_whisper_engine.py
"""OpenRouter Whisper ASR engine — Beta test mode cloud transcription.

POSTs base64 audio to OpenRouter's /api/v1/audio/transcriptions and maps the
OpenAI verbose_json response to the [{start,end,text,words}] segment shape the
rest of the pipeline consumes. Hard-fails (RuntimeError) on any error — Beta mode
never silently falls back to local.

NOTE: request params + response field names are confirmed by Validation-First
Phase 0 (docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md).
"""
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

from . import ASREngine, Segment

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterWhisperEngine(ASREngine):
    def __init__(self, config: dict):
        self._model = config.get("model", "openai/whisper-large-v3")
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "OpenRouter API key 未設定（OPENROUTER_API_KEY）— 無法以 Beta 模式轉錄"
            )

    def transcribe(self, audio_path: str, language: str = "en") -> List[Segment]:
        b64 = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
        fmt = Path(audio_path).suffix.lstrip(".").lower() or "wav"
        payload = {
            "model": self._model,
            "input_audio": {"data": b64, "format": fmt},
            "language": language,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment", "word"],
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{_BASE_URL}/audio/transcriptions",
            data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            raise RuntimeError(f"OpenRouter 轉錄失敗 HTTP {e.code}：{e.reason} {detail}")
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"OpenRouter 轉錄連線失敗：{e}")
        return self._map_response(raw)

    @staticmethod
    def _map_response(raw: dict) -> List[Segment]:
        segments = raw.get("segments")
        if not isinstance(segments, list) or not segments:
            raise RuntimeError(
                "OpenRouter whisper 回應無 segment timestamp — Beta ASR 不可行（見 Phase 0 gate）"
            )
        words_all = raw.get("words") if isinstance(raw.get("words"), list) else []
        out: List[Segment] = []
        for s in segments:
            start = float(s.get("start", 0.0))
            end = float(s.get("end", start))
            text = (s.get("text") or "").strip()
            seg = {"start": start, "end": end, "text": text}
            seg_words = [
                {"word": w.get("word", ""), "start": float(w.get("start", 0.0)),
                 "end": float(w.get("end", 0.0)), "probability": 1.0}
                for w in words_all
                if start <= float(w.get("start", -1.0)) < end
            ]
            if seg_words:
                seg["words"] = seg_words
            out.append(seg)
        return out

    def get_info(self) -> dict:
        return {"engine": "openrouter-whisper", "model_size": self._model,
                "languages": ["en", "zh", "yue", "ja", "multi"],
                "available": bool(self._api_key)}

    def get_params_schema(self) -> dict:
        return {"model": {"type": "string", "default": "openai/whisper-large-v3"}}
```

- [ ] **Step 4: 加 factory mapping（`backend/asr/__init__.py`，line 51 `whispercpp` 分支之前）**

```python
    elif engine_name == "openrouter-whisper":
        from .openrouter_whisper_engine import OpenRouterWhisperEngine
        return OpenRouterWhisperEngine(asr_config)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_openrouter_whisper_engine.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/asr/openrouter_whisper_engine.py backend/asr/__init__.py backend/tests/test_openrouter_whisper_engine.py
git commit -m "feat(beta): OpenRouter Whisper ASR engine + factory mapping"
```

---

## Task 7: ASR override 注入（flag 開 → openrouter-whisper）（⚠️ 需 Task 6）— ❌ CANCELLED (Phase 0 gate)

**Files:**
- Modify: `backend/app.py:302-309`（`_output_lang_asr_override`）
- Test: `backend/tests/test_beta_asr_override.py`

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_beta_asr_override.py
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test")   # app.py requires it at import time
import pytest
import app as app_module
from profiles import ProfileManager


@pytest.fixture
def pm(tmp_path, monkeypatch):
    m = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", m, raising=False)
    return m


def test_override_is_openrouter_when_beta_on(pm):
    pm.set_beta_mode(True)
    ov = app_module._output_lang_asr_override()
    assert ov["asr"]["engine"] == "openrouter-whisper"
    assert ov["asr"]["model"] == "openai/whisper-large-v3"
    assert ov["asr"]["condition_on_previous_text"] is False


def test_override_is_platform_when_beta_off(pm):
    pm.set_beta_mode(False)
    ov = app_module._output_lang_asr_override()
    # platform default never routes to openrouter
    assert ov["asr"]["engine"] != "openrouter-whisper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_beta_asr_override.py -v`
Expected: FAIL — `test_override_is_openrouter_when_beta_on` gets the platform mlx-whisper override.

- [ ] **Step 3: 改 `_output_lang_asr_override`（`backend/app.py:302-309`）**

```python
def _output_lang_asr_override():
    """Return a FRESH override dict for the output-language ASR pass.

    Beta test mode ON → OpenRouter whisper-large-v3. OFF → platform_backend default
    (macOS/auto == the validated mlx large-v3 cond=False dict, unchanged).
    """
    if _profile_manager.get_beta_mode():
        import beta_mode
        return {"asr": {"engine": "openrouter-whisper",
                        "model": beta_mode.BETA_ASR_MODEL,
                        "condition_on_previous_text": False}}
    import platform_backend as _pb
    return _pb.resolve_asr_override(os.environ, _pb.detect_platform())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_beta_asr_override.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: 回歸驗證（單獨跑改到嘅 test files）**

Run:
```bash
cd backend && python -m pytest tests/test_beta_mode.py tests/test_admin_beta_mode.py \
  tests/test_beta_llm_injection.py tests/test_openrouter_whisper_engine.py \
  tests/test_beta_asr_override.py -v
```
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_beta_asr_override.py
git commit -m "feat(beta): route output_lang ASR to OpenRouter whisper when beta mode on"
```

---

## Task 8: settings.json 預設 + 文檔

**Files:**
- Modify: `backend/config/settings.json`（加 `"beta_openrouter": false`）
- Modify: `CLAUDE.md`、`README.md`、`docs/PRD.md`

- [ ] **Step 1: settings.json 加預設 key**

喺 `backend/config/settings.json` root 加 `"beta_openrouter": false`（與 `active_profile` / `font` 同層）。

- [ ] **Step 2: curl smoke（backend 行緊 + admin session cookie）**

```bash
curl -s http://localhost:5001/api/admin/beta-mode -b cookies.txt   # 需 admin 登入 cookie
```
Expected: `{"enabled":false,"key_configured":...,"asr_model":"openai/whisper-large-v3","llm_model":"qwen/qwen3.5-35b-a3b"}`。

- [ ] **Step 3: 更新 CLAUDE.md**

- REST endpoints 表加 `GET/PUT /api/admin/beta-mode`（admin-only，全局 Beta 開關 + OpenRouter key 設定）。
- 「Current State」加一段「Admin Beta 測試模式」：全局 flag `settings.json:beta_openrouter`；開啟後 output_lang 嘅 ASR→`openrouter-whisper`（`openai/whisper-large-v3`）、LLM→OpenRouter `qwen/qwen3.5-35b-a3b`；硬編碼 parity；硬失敗無 fallback；key 存 `backend/.env`。
- Repository Structure 加 `backend/beta_mode.py`、`backend/asr/openrouter_whisper_engine.py`。
- Validation-First 記錄連結到 tracker。

- [ ] **Step 4: 更新 README.md（繁體中文，user-facing）**

加「Beta 測試模式」一節：點樣喺「我的帳戶 → Beta 測試模式」開啟、輸入 OpenRouter API key、兩個雲端模型、計費提示、失敗會顯示錯誤（唔自動退本地）。

- [ ] **Step 5: 更新 docs/PRD.md**

相關功能 status marker 由 📋 → ✅（如無對應條目，喺適當章節加一行 Beta 測試模式）。

- [ ] **Step 6: Commit**

```bash
git add backend/config/settings.json CLAUDE.md README.md docs/PRD.md
git commit -m "docs(beta): settings default + CLAUDE.md/README/PRD for Beta OpenRouter mode"
```

---

## 完成定義（Verification Gates）

1. **代碼質素** — Task 2/3/5/6/7 嘅 test file 單獨跑全 PASS；無 hardcode（model id 集中 `beta_mode.py`）。
2. **功能正確性** — curl `/api/admin/beta-mode` GET/PUT 格式一致；開 toggle 無 key → 400；前端分頁可開關 + 存 key。
3. **整合驗證** — flag 開：`_make_ollama_llm_call` 行 OpenRouter、`_output_lang_asr_override` 出 openrouter-whisper；flag 關：兩者退回本地（regression test 綠）。**真實 e2e（一條真片走 output_lang）需 Task 1 ✅ + 真 key，由操作者跑。**
4. **文檔完整性** — CLAUDE.md + README.md + PRD.md + 兩份 spec/tracker 已更新。

## Gate 摘要

- **Task 1（Phase 0）** 係 **Task 6 + Task 7 嘅硬 gate**。V1 = ❌（無 segment timestamp）→ 停 ASR 半邊，只交付 LLM 半邊（Task 2-5 + Task 8 去走 ASR 描述），ASR 留本地。
- Task 2/3/4/5 **不受** gate 阻擋，任何時候可做。
