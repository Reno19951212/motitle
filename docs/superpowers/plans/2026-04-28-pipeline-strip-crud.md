# Pipeline Strip CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the two stub buttons in the Pipeline preset menu (`💾 儲存當前設定` + `⚙ 管理預設`) and add a language-config CRUD subsection inside the ASR step dropdown, so users can manage Profile presets and language configs without leaving the top-bar workflow.

**Architecture:** Two coupled features in the same `frontend/index.html` Pipeline strip. Backend gains two new routes (`POST /api/languages` + `DELETE /api/languages/<id>`) and two new `LanguageConfigManager` methods (`create()` + `delete()`). Frontend gains four modals (Profile-save, Profile-manage, lang-config-create/edit, lang-config-manage) and a new `applyLanguageConfig()` step handler. Profile API is already complete — re-used as-is.

**Tech Stack:** Python 3.9+, Flask, pytest. Frontend: vanilla JS (no build), existing `.overlay` modal pattern, Playwright (Python async) for smoke.

---

## File Map

| File | Change |
|---|---|
| `backend/language_config.py` | Add `create(config)` + `delete(lang_id)` methods to `LanguageConfigManager` |
| `backend/app.py` | Add `POST /api/languages` + `DELETE /api/languages/<lang_id>` routes |
| `backend/tests/test_languages_crud.py` | New file — 8 pytest tests covering manager + routes |
| `frontend/index.html` | Add `availableLanguageConfigs` global + `fetchLanguageConfigs()` + `applyLanguageConfig()` + 4 modal markup blocks + 4 modal handler functions; modify `renderPipelineStrip()` ASR menu to insert lang-config sub-section; modify Profile preset menu to wire `💾` + `⚙` stub buttons |
| `/tmp/check_pipeline_crud.py` | New Playwright smoke covering 5 scenarios |

**Validation ranges** — I will use the existing constants in [backend/language_config.py:11-18](backend/language_config.py#L11-L18) (`MIN/MAX_MAX_WORDS = 5–200`, `MIN/MAX_MAX_DURATION = 1.0–60.0`, `MIN/MAX_BATCH_SIZE = 1–50`, `MIN/MAX_TEMPERATURE = 0.0–2.0`) — these are slightly wider than the spec's slider ranges. The spec's narrower ranges were illustrative; production validation must use the existing constants so PATCH and POST behave identically. Frontend slider `min`/`max` will mirror these existing constants.

---

### Task 1: Backend pytest — RED phase (8 failing tests)

Write all backend tests before any implementation. They will fail because `create()` / `delete()` and the two routes don't exist yet.

**Files:**
- Create: `backend/tests/test_languages_crud.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for language config CRUD: LanguageConfigManager.create()/delete() + POST/DELETE routes."""
import json
import pytest
from pathlib import Path

from app import app, _language_config_manager, _profile_manager


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client with isolated language_config + profile dirs."""
    # Re-point both managers to a temp dir so we don't touch real config
    from language_config import LanguageConfigManager
    from profiles import ProfileManager

    # Seed built-ins so delete-builtin tests have real targets
    lang_dir = tmp_path / "languages"
    lang_dir.mkdir()
    (lang_dir / "en.json").write_text(json.dumps({
        "id": "en", "name": "English",
        "asr": {"max_words_per_segment": 25, "max_segment_duration": 40},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }))
    (lang_dir / "zh.json").write_text(json.dumps({
        "id": "zh", "name": "Chinese",
        "asr": {"max_words_per_segment": 30, "max_segment_duration": 8},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }))

    new_lc_mgr = LanguageConfigManager(tmp_path)
    new_prof_mgr = ProfileManager(tmp_path)

    monkeypatch.setattr("app._language_config_manager", new_lc_mgr)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _valid_body(lc_id="zh-news", name="中文 · 新聞"):
    return {
        "id": lc_id,
        "name": name,
        "asr": {"max_words_per_segment": 20, "max_segment_duration": 5},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }


def test_create_language_config_success(client):
    """POST with valid body returns 200 and creates the file."""
    resp = client.post("/api/languages", json=_valid_body())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["config"]["id"] == "zh-news"
    assert data["config"]["name"] == "中文 · 新聞"
    assert data["config"]["asr"]["max_words_per_segment"] == 20


def test_create_id_collision(client):
    """POST with id that already exists returns 409."""
    client.post("/api/languages", json=_valid_body("zh-news"))
    resp = client.post("/api/languages", json=_valid_body("zh-news", "Different name"))
    assert resp.status_code == 409
    assert "already exists" in resp.get_json()["error"].lower()


def test_create_invalid_id_format(client):
    """POST with id containing illegal chars (slash, space, uppercase) returns 400."""
    for bad_id in ["my/lang", "zh news", "ZH-NEWS", "中文", ""]:
        resp = client.post("/api/languages", json=_valid_body(bad_id))
        assert resp.status_code == 400, f"id={bad_id!r} should be rejected, got {resp.status_code}"


def test_create_out_of_range_value(client):
    """POST with numeric values outside the validation ranges returns 400."""
    body = _valid_body()
    body["asr"]["max_words_per_segment"] = 500  # over 200 max
    resp = client.post("/api/languages", json=body)
    assert resp.status_code == 400


def test_delete_built_in_blocked(client):
    """DELETE /api/languages/en (built-in) returns 400."""
    resp = client.delete("/api/languages/en")
    assert resp.status_code == 400
    assert "built-in" in resp.get_json()["error"].lower()


def test_delete_in_use_blocked(client):
    """DELETE config used by a profile returns 400 with profile names."""
    # Create a custom config
    client.post("/api/languages", json=_valid_body("zh-news"))
    # Create a profile that uses it
    profile = _profile_manager.create({
        "id": "test-profile",
        "name": "Test Profile",
        "asr": {"engine": "mlx-whisper", "language_config_id": "zh-news"},
        "translation": {"engine": "mock"},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#fff",
                 "outline_color": "#000", "outline_width": 2, "margin_bottom": 40},
    })
    resp = client.delete("/api/languages/zh-news")
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "Test Profile" in error or "test-profile" in error


def test_delete_unused_succeeds(client, tmp_path):
    """DELETE custom config with no referencing profile returns 200 + file gone."""
    client.post("/api/languages", json=_valid_body("zh-news"))
    resp = client.delete("/api/languages/zh-news")
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True
    # Verify GET returns 404 now
    get_resp = client.get("/api/languages/zh-news")
    assert get_resp.status_code == 404


def test_delete_nonexistent(client):
    """DELETE id that never existed returns 404."""
    resp = client.delete("/api/languages/never-existed")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — confirm all 8 FAIL**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_languages_crud.py -v
```

Expected: 8 tests FAIL — most with `404 Not Found` (route doesn't exist) or `405 Method Not Allowed`. Exit code 1.

- [ ] **Step 3: Commit the RED tests**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_languages_crud.py
git commit -m "test(languages): add RED tests for create/delete CRUD"
```

---

### Task 2: `LanguageConfigManager.create()` + `delete()`

Add the two methods to the existing manager. After this task the manager-level tests still fail at the route layer, but `create()` / `delete()` themselves work.

**Files:**
- Modify: `backend/language_config.py` — append two methods to the class (after existing `update()` at line 49–77)

- [ ] **Step 1: Insert `create()` and `delete()` after `update()`**

Find the existing `update()` method ending around line 77 (`return updated`). Add immediately after it (before `def _validate(self, data: dict)` on line 79):

```python
    def create(self, data: dict) -> dict:
        """Create a new language config. Raises ValueError on validation error.

        Required keys: id, name, asr.max_words_per_segment, asr.max_segment_duration,
        translation.batch_size, translation.temperature.
        """
        import re
        lang_id = (data.get("id") or "").strip()
        if not re.match(r"^[a-z0-9-]{1,32}$", lang_id):
            raise ValueError("id must match [a-z0-9-]{1,32}")

        if self.get(lang_id) is not None:
            raise ValueError(f"Language config '{lang_id}' already exists")

        name = (data.get("name") or "").strip()
        if not name or len(name) > 50:
            raise ValueError("name is required and must be 1–50 chars")

        errors = self._validate(data)
        if errors:
            raise ValueError("; ".join(errors))

        config = {
            "id": lang_id,
            "name": name,
            "asr": data.get("asr", DEFAULT_ASR_CONFIG),
            "translation": data.get("translation", DEFAULT_TRANSLATION_CONFIG),
        }

        path = self._lang_path(lang_id)
        path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return config

    def delete(self, lang_id: str) -> bool:
        """Delete a language config file. Returns True if deleted, False if not found."""
        path = self._lang_path(lang_id)
        if not path.exists():
            return False
        path.unlink()
        return True
```

- [ ] **Step 2: Verify the edit**

```bash
grep -n "def create\|def delete" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/language_config.py"
```

Expected output:
```
79:    def create(self, data: dict) -> dict:
112:    def delete(self, lang_id: str) -> bool:
```

(Line numbers approximate; the point is two new methods exist.)

- [ ] **Step 3: Run a focused unit test against the manager directly**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python3 -c "
from pathlib import Path
import tempfile
from language_config import LanguageConfigManager

with tempfile.TemporaryDirectory() as td:
    mgr = LanguageConfigManager(Path(td))
    cfg = mgr.create({
        'id': 'zh-news', 'name': '中文新聞',
        'asr': {'max_words_per_segment': 20, 'max_segment_duration': 5},
        'translation': {'batch_size': 8, 'temperature': 0.1},
    })
    assert cfg['id'] == 'zh-news', cfg
    assert mgr.get('zh-news') is not None
    try:
        mgr.create({'id': 'zh-news', 'name': 'dup',
                    'asr': {'max_words_per_segment': 20, 'max_segment_duration': 5},
                    'translation': {'batch_size': 8, 'temperature': 0.1}})
        raise AssertionError('expected ValueError on duplicate')
    except ValueError as e:
        assert 'already exists' in str(e)
    assert mgr.delete('zh-news') is True
    assert mgr.get('zh-news') is None
    assert mgr.delete('zh-news') is False
print('OK')
"
```

Expected output: `OK`. Exit code 0.

---

### Task 3: `POST` + `DELETE` routes in `app.py`

Wire the manager methods into Flask routes. After this all 8 backend tests should pass.

**Files:**
- Modify: `backend/app.py` — add two routes after the existing `PATCH /api/languages/<lang_id>` (around [app.py:1610](backend/app.py#L1610))

- [ ] **Step 1: Find the PATCH route end and insert two new routes after it**

Find the `api_update_language` function. After its closing `}` / `return jsonify(...)`, insert:

```python
@app.route('/api/languages', methods=['POST'])
def api_create_language():
    """Create a new language config."""
    data = request.get_json(silent=True) or {}
    try:
        config = _language_config_manager.create(data)
    except ValueError as e:
        msg = str(e)
        # Distinguish "already exists" (409) from validation errors (400)
        if 'already exists' in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 400
    return jsonify({'config': config}), 200


@app.route('/api/languages/<lang_id>', methods=['DELETE'])
def api_delete_language(lang_id):
    """Delete a language config. Built-ins (en/zh) and in-use configs are blocked."""
    if lang_id in ('en', 'zh'):
        return jsonify({'error': 'Cannot delete built-in language config'}), 400

    if _language_config_manager.get(lang_id) is None:
        return jsonify({'error': 'Not found'}), 404

    used_by = []
    for p in _profile_manager.list_all():
        if p.get('asr', {}).get('language_config_id') == lang_id:
            used_by.append(p.get('name') or p.get('id') or '<unnamed>')

    if used_by:
        return jsonify({
            'error': f'Language config "{lang_id}" used by {len(used_by)} profile(s): {", ".join(used_by)}'
        }), 400

    _language_config_manager.delete(lang_id)
    return jsonify({'ok': True}), 200
```

- [ ] **Step 2: Run all backend tests — expect 8/8 PASS**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_languages_crud.py -v
```

Expected output: `8 passed`. Exit code 0.

- [ ] **Step 3: Run the full backend test suite to confirm no regressions**

```bash
pytest tests/ -q
```

Expected output: all tests pass (or only the pre-existing macOS tmpdir colon-escape test fails, which is documented as known in CLAUDE.md v3.3).

- [ ] **Step 4: Commit backend implementation**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/language_config.py backend/app.py
git commit -m "feat(languages): POST/DELETE /api/languages + manager create/delete"
```

---

### Task 4: Playwright RED smoke (5 frontend scenarios)

Write the frontend smoke before any UI changes. They will fail because the new modals + menu sub-section don't exist yet.

**Files:**
- Create: `/tmp/check_pipeline_crud.py`

- [ ] **Step 1: Write the smoke**

```python
"""
Smoke: pipeline strip CRUD (Profile preset save/manage + language config CRUD).
Run: python3 /tmp/check_pipeline_crud.py
Requires: playwright installed.
Backend mocked via page.route — no live backend needed.
"""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
DASHBOARD = (REPO / "frontend/index.html").resolve().as_uri()

PROFILE = {
    "profile": {
        "id": "test-profile", "name": "Test Profile",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3",
                "language": "en", "language_config_id": "en"},
        "translation": {"engine": "mock", "glossary_id": None},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#fff",
                 "outline_color": "#000", "outline_width": 2, "margin_bottom": 40},
    }
}
PROFILES_LIST = {"profiles": [PROFILE["profile"]]}

LANG_CONFIGS = {"languages": [
    {"id": "en", "name": "English",
     "asr": {"max_words_per_segment": 25, "max_segment_duration": 40},
     "translation": {"batch_size": 8, "temperature": 0.1}},
    {"id": "zh", "name": "Chinese",
     "asr": {"max_words_per_segment": 30, "max_segment_duration": 8},
     "translation": {"batch_size": 8, "temperature": 0.1}},
    {"id": "zh-news", "name": "中文 · 新聞",
     "asr": {"max_words_per_segment": 20, "max_segment_duration": 5},
     "translation": {"batch_size": 8, "temperature": 0.1}},
]}


async def setup_routes(page, *, post_lang_status=200, delete_lang_status=200,
                       delete_lang_body=None, profile_post_resp=None):
    """Mock all backend endpoints used by Pipeline strip CRUD."""
    captured = {"profile_patches": [], "lang_posts": [], "lang_deletes": []}

    async def handle(route):
        url = route.request.url
        method = route.request.method

        if "/api/profiles/active" in url and method == "GET":
            await route.fulfill(status=200, body=json.dumps(PROFILE),
                                content_type="application/json")
        elif url.endswith("/api/profiles") and method == "GET":
            await route.fulfill(status=200, body=json.dumps(PROFILES_LIST),
                                content_type="application/json")
        elif url.endswith("/api/profiles") and method == "POST":
            body = json.loads(route.request.post_data or "{}")
            captured["profile_patches"].append(("POST", body))
            new_profile = {**body, "id": "new-prof-1"}
            await route.fulfill(status=200,
                                body=json.dumps({"profile": new_profile}),
                                content_type="application/json")
        elif "/api/profiles/" in url and "/activate" in url and method == "POST":
            await route.fulfill(status=200,
                                body=json.dumps({"profile": PROFILE["profile"]}),
                                content_type="application/json")
        elif "/api/profiles/" in url and method == "PATCH":
            body = json.loads(route.request.post_data or "{}")
            captured["profile_patches"].append(("PATCH", body))
            patched = {**PROFILE["profile"], **body}
            if "asr" in body:
                patched["asr"] = {**PROFILE["profile"]["asr"], **body["asr"]}
            await route.fulfill(status=200,
                                body=json.dumps({"profile": patched}),
                                content_type="application/json")
        elif url.endswith("/api/languages") and method == "GET":
            await route.fulfill(status=200, body=json.dumps(LANG_CONFIGS),
                                content_type="application/json")
        elif url.endswith("/api/languages") and method == "POST":
            body = json.loads(route.request.post_data or "{}")
            captured["lang_posts"].append(body)
            await route.fulfill(status=post_lang_status,
                                body=json.dumps({"config": body}
                                                if post_lang_status == 200
                                                else {"error": "ID exists"}),
                                content_type="application/json")
        elif "/api/languages/" in url and method == "DELETE":
            lc_id = url.rsplit("/", 1)[-1]
            captured["lang_deletes"].append(lc_id)
            await route.fulfill(status=delete_lang_status,
                                body=json.dumps(delete_lang_body or {"ok": True}),
                                content_type="application/json")
        elif "/api/glossaries" in url and method == "GET":
            await route.fulfill(status=200,
                                body=json.dumps({"glossaries": []}),
                                content_type="application/json")
        elif "/api/files" in url and method == "GET":
            await route.fulfill(status=200, body=json.dumps({"files": []}),
                                content_type="application/json")
        else:
            await route.continue_()

    await page.route("**/*", handle)
    return captured


async def scenario_a_save_profile_preset(browser):
    """Open Pipeline preset menu → 💾 → modal → fill name → save → POST /api/profiles."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    captured = await setup_routes(page)
    await page.goto(DASHBOARD)
    await page.wait_for_timeout(1000)

    # Open save-preset modal
    await page.evaluate("openProfileSaveModal()")
    await page.wait_for_selector("#ppsOverlay.open", timeout=3000)
    await page.fill("#ppsName", "Broadcast 4K Master")
    await page.fill("#ppsDesc", "ProRes HQ + Claude Opus")
    await page.click("#ppsSaveBtn")
    await page.wait_for_timeout(500)

    posts = [p for p in captured["profile_patches"] if p[0] == "POST"]
    if len(posts) != 1:
        await ctx.close()
        return False, f"expected 1 POST /api/profiles, got {len(posts)}"
    body = posts[0][1]
    if body.get("name") != "Broadcast 4K Master":
        await ctx.close()
        return False, f"name not in POST body: {body}"
    if body.get("description") != "ProRes HQ + Claude Opus":
        await ctx.close()
        return False, f"description not in POST body: {body}"
    await ctx.close()
    return True, ""


async def scenario_b_create_language_config(browser):
    """Open ASR menu → ➕ 新增語言配置 → fill form → save → POST /api/languages."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    captured = await setup_routes(page)
    await page.goto(DASHBOARD)
    await page.wait_for_timeout(1000)

    await page.evaluate("openLangConfigCreateModal()")
    await page.wait_for_selector("#lcOverlay.open", timeout=3000)
    await page.fill("#lcId", "zh-drama")
    await page.fill("#lcName", "中文 · 戲劇")
    await page.click("#lcSaveBtn")
    await page.wait_for_timeout(500)

    if not captured["lang_posts"]:
        await ctx.close()
        return False, "no POST /api/languages captured"
    body = captured["lang_posts"][0]
    if body.get("id") != "zh-drama":
        await ctx.close()
        return False, f"id wrong in body: {body}"
    if "asr" not in body or "translation" not in body:
        await ctx.close()
        return False, f"asr/translation missing: {body}"
    await ctx.close()
    return True, ""


async def scenario_c_apply_language_config(browser):
    """Click a language config in ASR menu → PATCH active profile asr.language_config_id."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    captured = await setup_routes(page)
    await page.goto(DASHBOARD)
    await page.wait_for_timeout(1000)

    await page.evaluate("applyLanguageConfig('zh-news')")
    await page.wait_for_timeout(500)

    patches = [p for p in captured["profile_patches"] if p[0] == "PATCH"]
    if not patches:
        await ctx.close()
        return False, "no PATCH captured"
    body = patches[0][1]
    if body.get("asr", {}).get("language_config_id") != "zh-news":
        await ctx.close()
        return False, f"language_config_id not in PATCH body: {body}"
    await ctx.close()
    return True, ""


async def scenario_d_builtin_protected(browser):
    """Open lang-config manage modal → 'en' row should not have a delete button."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await setup_routes(page)
    await page.goto(DASHBOARD)
    await page.wait_for_timeout(1000)

    await page.evaluate("openLangConfigManageModal()")
    await page.wait_for_selector("#lcmOverlay.open", timeout=3000)
    await page.wait_for_timeout(300)

    # Row for 'en' should exist but have no delete button
    en_row = page.locator("[data-lc-id='en']")
    if await en_row.count() == 0:
        await ctx.close()
        return False, "no row found for built-in 'en'"
    en_delete = en_row.locator("button[data-action='delete']")
    if await en_delete.count() != 0:
        await ctx.close()
        return False, "built-in 'en' has a delete button (should be absent)"
    # Sanity: zh-news should HAVE a delete button
    custom_delete = page.locator("[data-lc-id='zh-news'] button[data-action='delete']")
    if await custom_delete.count() == 0:
        await ctx.close()
        return False, "custom 'zh-news' missing delete button"
    await ctx.close()
    return True, ""


async def scenario_e_in_use_delete_blocked(browser):
    """Delete an in-use config → 400 with profile names → toast appears, modal stays open."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await setup_routes(page,
                       delete_lang_status=400,
                       delete_lang_body={"error": 'Language config "zh-news" used by 1 profile(s): Test Profile'})
    await page.goto(DASHBOARD)
    await page.wait_for_timeout(1000)

    await page.evaluate("openLangConfigManageModal()")
    await page.wait_for_selector("#lcmOverlay.open", timeout=3000)
    await page.wait_for_timeout(300)

    # Auto-confirm window.confirm so the delete proceeds
    await page.evaluate("window.confirm = () => true")
    await page.click("[data-lc-id='zh-news'] button[data-action='delete']")
    await page.wait_for_timeout(500)

    # Modal should still be open
    overlay_open = await page.locator("#lcmOverlay.open").count()
    if overlay_open == 0:
        await ctx.close()
        return False, "manage modal closed unexpectedly after blocked delete"
    # Toast should show with profile name
    toasts = page.locator(".toast")
    toast_count = await toasts.count()
    if toast_count == 0:
        await ctx.close()
        return False, "no toast appeared"
    found_profile_name = False
    for i in range(toast_count):
        txt = await toasts.nth(i).inner_text()
        if "Test Profile" in txt:
            found_profile_name = True
            break
    if not found_profile_name:
        await ctx.close()
        return False, f"profile name 'Test Profile' missing from toast(s)"
    await ctx.close()
    return True, ""


async def run():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        for label, fn in [
            ("A — save Profile preset", scenario_a_save_profile_preset),
            ("B — create language config", scenario_b_create_language_config),
            ("C — apply language config (PATCH)", scenario_c_apply_language_config),
            ("D — built-in delete absent", scenario_d_builtin_protected),
            ("E — in-use delete blocked + toast", scenario_e_in_use_delete_blocked),
        ]:
            ok, err = await fn(browser)
            if ok:
                print(f"PASS {label}")
            else:
                errors.append(f"FAIL {label}: {err}")

        await browser.close()

    if errors:
        print("\n--- FAILURES ---")
        for e in errors:
            print(e)
        sys.exit(1)
    print("\nAll scenarios PASSED")


asyncio.run(run())
```

- [ ] **Step 2: Run smoke — confirm all 5 scenarios FAIL**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python3 /tmp/check_pipeline_crud.py
```

Expected: ≥ 4 scenarios FAIL with messages like `openProfileSaveModal is not defined`, `#lcOverlay not found`, `applyLanguageConfig is not defined`. Exit code 1.

(Smoke is in `/tmp/`, never committed.)

---

### Task 5: Frontend — language config dropdown sub-section + `applyLanguageConfig()`

Wire scenario C. Add the language-config global cache, the fetch helper, the apply handler, and the ASR menu sub-section render.

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add `availableLanguageConfigs` global + `fetchLanguageConfigs()`**

Find the existing `let availableProfiles = [];` ([frontend/index.html:1565](frontend/index.html#L1565)). Add immediately after:

```js
    let availableLanguageConfigs = [];
```

Find `async function fetchProfiles()` ([frontend/index.html:3449](frontend/index.html#L3449)) — `async function fetchGlossaries()` follows it around line 3458. Add a new function between them:

```js
    async function fetchLanguageConfigs() {
      try {
        const r = await fetch(`${API_BASE}/api/languages`);
        if (!r.ok) return;
        const d = await r.json();
        availableLanguageConfigs = d.languages || [];
      } catch (e) { /* keep cache empty on error */ }
    }
```

Find the bootstrap chain (around [frontend/index.html:3524](frontend/index.html#L3524)):
```js
fetchActiveProfile().then(fetchProfiles).then(fetchGlossaries).then(fetchFileList);
```
Replace with:
```js
fetchActiveProfile().then(fetchProfiles).then(fetchLanguageConfigs).then(fetchGlossaries).then(fetchFileList);
```

- [ ] **Step 2: Add `applyLanguageConfig()` handler**

Find `async function applyGlossary(glossId)` ([frontend/index.html:2056](frontend/index.html#L2056)). Add immediately before it:

```js
    async function applyLanguageConfig(lcId) {
      if (!activeProfile) {
        showToast('請先啟用一個 Profile', 'error');
        return;
      }
      const newAsr = { ...activeProfile.asr, language_config_id: lcId };
      try {
        const r = await fetch(`${API_BASE}/api/profiles/${activeProfile.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ asr: newAsr }),
        });
        if (!r.ok) throw new Error((await r.json()).error || '切換失敗');
        const d = await r.json();
        activeProfile = d.profile;
        renderPipelineStrip();
        showToast(`已切換語言配置：${lcId}`, 'success');
      } catch (e) {
        showToast(`切換語言配置失敗: ${e.message}`, 'error');
      }
    }
```

- [ ] **Step 3: Modify `renderPipelineStrip()` ASR menu to add language-config sub-section**

Find the line that builds the ASR menu HTML ([frontend/index.html:1979](frontend/index.html#L1979)):

```js
      const asrMenuHtml = renderStepMenu('ASR · 選擇', ASR_OPTIONS, asrModel, 'applyAsrModel').replace('<div class="step-menu">', '<div class="step-menu" data-kind="asr">');
```

Replace with:

```js
      const currentLcId = p.asr?.language_config_id || p.asr?.language || 'en';
      const lcDropdownHtml = (availableLanguageConfigs.length === 0
        ? '<div style="padding:8px 12px; color:var(--text-dim); font-size:11px;">（無語言配置）</div>'
        : availableLanguageConfigs.map(lc => `
          <button ${lc.id === currentLcId ? 'class="on"' : ''} onclick="applyLanguageConfig('${lc.id}')">
            <div class="smn-main">
              <span class="smn-name">${escapeHtml(lc.id)} — ${escapeHtml(lc.name)}</span>
              ${lc.id === currentLcId ? '<span class="smn-badge">當前</span>' : ''}
            </div>
          </button>`).join(''));

      const asrMenuHtml = renderStepMenu('ASR · 選擇', ASR_OPTIONS, asrModel, 'applyAsrModel')
        .replace('<div class="step-menu">', '<div class="step-menu" data-kind="asr">')
        .replace('</div>', `
          <div class="split-divider"></div>
          <div class="step-menu-head">語言配置</div>
          ${lcDropdownHtml}
          <div class="split-divider"></div>
          <button class="smn-manage" onclick="openLangConfigCreateModal()">
            <span class="fmt-badge outline">➕</span><span class="fmt-desc">新增語言配置…</span>
          </button>
          <button class="smn-manage" onclick="openLangConfigManageModal()">
            <span class="fmt-badge outline">⚙</span><span class="fmt-desc">管理語言配置…</span>
          </button>
        </div>`);
```

(The `.replace('</div>', ...)` only replaces the FIRST `</div>` it finds, which is the closing of the `.step-menu` div — that is the correct insertion point.)

- [ ] **Step 4: Add stub modal-open functions so scenario C can run before Tasks 6 + 7**

`applyLanguageConfig()` is called in scenario C before any modal is opened, so scenario C should pass after this task. But scenarios B / D / E need the modal-open functions to at least be defined or scenario A needs `openProfileSaveModal` defined — Task 4's `page.evaluate` will throw `ReferenceError` if the function name is missing.

Add four no-op stubs (will be replaced in Tasks 6 + 7) immediately before `applyLanguageConfig`:

```js
    function openProfileSaveModal()    { console.warn('openProfileSaveModal not yet implemented'); }
    function openProfileManageModal()  { console.warn('openProfileManageModal not yet implemented'); }
    function openLangConfigCreateModal() { console.warn('openLangConfigCreateModal not yet implemented'); }
    function openLangConfigManageModal() { console.warn('openLangConfigManageModal not yet implemented'); }
```

These get **replaced** (not augmented) in Tasks 6 + 7 — same name, fully implemented body.

- [ ] **Step 5: Run smoke — only scenario C should pass; A/B/D/E still fail**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python3 /tmp/check_pipeline_crud.py
```

Expected:
```
PASS C — apply language config (PATCH)
FAIL A — save Profile preset: ...
FAIL B — create language config: ...
FAIL D — built-in delete absent: ...
FAIL E — in-use delete blocked + toast: ...
```

---

### Task 6: Frontend — language config create + manage modals

Wire scenarios B, D, E. Add modal markup + `openLangConfigCreateModal()` + `openLangConfigManageModal()` + `saveLanguageConfig()` + `deleteLanguageConfig()`.

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add modal markup near other overlays**

Find the closing tag of an existing `.overlay` block. (Search for `id="orOverlay"` — the OpenRouter modal — and look for its sibling overlays.) Add after the last existing overlay, before the closing `</body>`:

```html
<!-- Language Config Create / Edit Modal -->
<div class="overlay" id="lcOverlay">
  <div class="overlay-box" style="width: 540px;">
    <div class="overlay-head">
      <span id="lcTitle">新增語言配置</span>
      <button class="or-close" onclick="closeLangConfigModal()" aria-label="關閉">&times;</button>
    </div>
    <div class="overlay-body" style="padding: 16px 20px;">
      <div style="display:grid;gap:14px;">
        <label style="display:flex;flex-direction:column;gap:4px;">
          <span style="font-size:12px;font-weight:600;">ID *</span>
          <input id="lcId" pattern="[a-z0-9-]+" maxlength="32" placeholder="zh-news"
                 style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--surface-2);color:var(--text);">
          <span style="font-size:11px;color:var(--text-dim);">唯一識別碼，只可英數字 + 連字號</span>
          <span id="lcIdError" style="font-size:11px;color:var(--danger,#ef4444);display:none;"></span>
        </label>
        <label style="display:flex;flex-direction:column;gap:4px;">
          <span style="font-size:12px;font-weight:600;">顯示名稱 *</span>
          <input id="lcName" maxlength="50" placeholder="中文 · 新聞"
                 style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--surface-2);color:var(--text);">
        </label>
        <fieldset style="border:1px solid var(--border);border-radius:6px;padding:10px 14px;">
          <legend style="font-size:11px;color:var(--text-dim);padding:0 6px;">ASR 分段參數</legend>
          <label style="display:flex;align-items:center;gap:10px;margin:6px 0;font-size:12px;">
            每段最多字數
            <input id="lcMaxWords" type="range" min="5" max="200" value="25" style="flex:1;">
            <span id="lcMaxWordsVal" style="min-width:30px;text-align:right;font-family:var(--font-mono);">25</span>
          </label>
          <label style="display:flex;align-items:center;gap:10px;margin:6px 0;font-size:12px;">
            每段最長秒數
            <input id="lcMaxDur" type="range" min="1" max="60" value="8" style="flex:1;">
            <span id="lcMaxDurVal" style="min-width:30px;text-align:right;font-family:var(--font-mono);">8</span>
          </label>
        </fieldset>
        <fieldset style="border:1px solid var(--border);border-radius:6px;padding:10px 14px;">
          <legend style="font-size:11px;color:var(--text-dim);padding:0 6px;">翻譯參數</legend>
          <label style="display:flex;align-items:center;gap:10px;margin:6px 0;font-size:12px;">
            每批 batch 大小
            <input id="lcBatch" type="range" min="1" max="50" value="8" style="flex:1;">
            <span id="lcBatchVal" style="min-width:30px;text-align:right;font-family:var(--font-mono);">8</span>
          </label>
          <label style="display:flex;align-items:center;gap:10px;margin:6px 0;font-size:12px;">
            Temperature
            <input id="lcTemp" type="range" min="0" max="2" step="0.05" value="0.1" style="flex:1;">
            <span id="lcTempVal" style="min-width:36px;text-align:right;font-family:var(--font-mono);">0.10</span>
          </label>
        </fieldset>
      </div>
    </div>
    <div class="overlay-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 20px;">
      <button class="or-btn" onclick="closeLangConfigModal()">取消</button>
      <button class="or-btn primary" id="lcSaveBtn" onclick="saveLanguageConfig()">儲存</button>
    </div>
  </div>
</div>

<!-- Language Config Manage Modal -->
<div class="overlay" id="lcmOverlay">
  <div class="overlay-box" style="width: 600px;">
    <div class="overlay-head">
      <span>語言配置管理</span>
      <button class="or-close" onclick="closeLangConfigManageModal()" aria-label="關閉">&times;</button>
    </div>
    <div class="overlay-body" id="lcmBody" style="padding: 12px 20px;"></div>
    <div class="overlay-footer" style="display:flex;justify-content:space-between;gap:8px;padding:12px 20px;">
      <button class="or-btn" onclick="openLangConfigCreateModal()">+ 新增配置</button>
      <button class="or-btn" onclick="closeLangConfigManageModal()">關閉</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Replace the `openLangConfigCreateModal` / `openLangConfigManageModal` stubs with real implementations**

Find the four stubs added in Task 5 Step 4 and replace **all four** with:

```js
    let _lcEditingId = null;  // null = create mode; id string = edit mode

    function openLangConfigCreateModal(prefillId = null) {
      _lcEditingId = prefillId;
      const isEdit = prefillId !== null;
      const existing = isEdit ? availableLanguageConfigs.find(lc => lc.id === prefillId) : null;
      document.getElementById('lcTitle').textContent = isEdit ? '編輯語言配置' : '新增語言配置';
      document.getElementById('lcId').value = existing?.id || '';
      document.getElementById('lcId').disabled = isEdit;  // ID immutable on edit
      document.getElementById('lcName').value = existing?.name || '';
      document.getElementById('lcMaxWords').value = existing?.asr?.max_words_per_segment ?? 25;
      document.getElementById('lcMaxDur').value = existing?.asr?.max_segment_duration ?? 8;
      document.getElementById('lcBatch').value = existing?.translation?.batch_size ?? 8;
      document.getElementById('lcTemp').value = existing?.translation?.temperature ?? 0.1;
      _lcSyncSliderLabels();
      document.getElementById('lcIdError').style.display = 'none';
      document.getElementById('lcOverlay').classList.add('open');
      // Wire slider labels
      ['lcMaxWords','lcMaxDur','lcBatch','lcTemp'].forEach(id => {
        document.getElementById(id).oninput = _lcSyncSliderLabels;
      });
      setTimeout(() => document.getElementById(isEdit ? 'lcName' : 'lcId').focus(), 50);
    }

    function _lcSyncSliderLabels() {
      document.getElementById('lcMaxWordsVal').textContent = document.getElementById('lcMaxWords').value;
      document.getElementById('lcMaxDurVal').textContent = document.getElementById('lcMaxDur').value;
      document.getElementById('lcBatchVal').textContent = document.getElementById('lcBatch').value;
      document.getElementById('lcTempVal').textContent = parseFloat(document.getElementById('lcTemp').value).toFixed(2);
    }

    function closeLangConfigModal() {
      document.getElementById('lcOverlay').classList.remove('open');
      _lcEditingId = null;
    }

    async function saveLanguageConfig() {
      const id = document.getElementById('lcId').value.trim();
      const name = document.getElementById('lcName').value.trim();
      if (!name) { showToast('顯示名稱必填', 'error'); return; }
      if (!_lcEditingId && !/^[a-z0-9-]{1,32}$/.test(id)) {
        document.getElementById('lcIdError').textContent = 'ID 必須係 1–32 個英數字 / 連字號';
        document.getElementById('lcIdError').style.display = 'block';
        return;
      }
      const body = {
        id: _lcEditingId || id,
        name,
        asr: {
          max_words_per_segment: parseInt(document.getElementById('lcMaxWords').value, 10),
          max_segment_duration: parseFloat(document.getElementById('lcMaxDur').value),
        },
        translation: {
          batch_size: parseInt(document.getElementById('lcBatch').value, 10),
          temperature: parseFloat(document.getElementById('lcTemp').value),
        },
      };
      const isEdit = _lcEditingId !== null;
      const url = isEdit
        ? `${API_BASE}/api/languages/${encodeURIComponent(_lcEditingId)}`
        : `${API_BASE}/api/languages`;
      const method = isEdit ? 'PATCH' : 'POST';
      try {
        const r = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (r.status === 409) {
          document.getElementById('lcIdError').textContent = '呢個 ID 已存在';
          document.getElementById('lcIdError').style.display = 'block';
          return;
        }
        if (!r.ok) throw new Error((await r.json()).error || '儲存失敗');
        await fetchLanguageConfigs();
        renderPipelineStrip();
        closeLangConfigModal();
        showToast(isEdit ? `已更新語言配置：${body.id}` : `已建立語言配置：${body.id}`, 'success');
        // If manage modal is open, refresh its list
        if (document.getElementById('lcmOverlay').classList.contains('open')) {
          _renderLangConfigManageList();
        }
      } catch (e) {
        showToast(`儲存失敗: ${e.message}`, 'error');
      }
    }

    function openLangConfigManageModal() {
      _renderLangConfigManageList();
      document.getElementById('lcmOverlay').classList.add('open');
    }

    function closeLangConfigManageModal() {
      document.getElementById('lcmOverlay').classList.remove('open');
    }

    function _renderLangConfigManageList() {
      const body = document.getElementById('lcmBody');
      const builtIn = new Set(['en', 'zh']);
      body.innerHTML = availableLanguageConfigs.map(lc => {
        const isBuiltIn = builtIn.has(lc.id);
        const params = `${lc.asr?.max_words_per_segment || '?'} 字 / ${lc.asr?.max_segment_duration || '?'}s · batch ${lc.translation?.batch_size || '?'} · temp ${(lc.translation?.temperature ?? 0).toFixed(2)}`;
        return `
          <div data-lc-id="${escapeHtml(lc.id)}" style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);">
            <div style="flex:1;min-width:0;">
              <div style="font-weight:600;font-size:13px;">
                ${escapeHtml(lc.id)} — ${escapeHtml(lc.name)}
                ${isBuiltIn ? '<span class="smn-badge" style="margin-left:6px;">內置</span>' : ''}
              </div>
              <div style="font-size:11px;color:var(--text-dim);">${escapeHtml(params)}</div>
            </div>
            <button class="btn btn-ghost btn-sm" data-action="edit" onclick="openLangConfigCreateModal('${lc.id}')">✎</button>
            ${isBuiltIn ? '' : `<button class="btn btn-ghost btn-sm" data-action="delete" onclick="deleteLanguageConfig('${lc.id}')">🗑</button>`}
          </div>`;
      }).join('') || '<div style="color:var(--text-dim);padding:12px 0;">暫無語言配置</div>';
    }

    async function deleteLanguageConfig(lcId) {
      if (!confirm(`確定刪除語言配置「${lcId}」？`)) return;
      try {
        const r = await fetch(`${API_BASE}/api/languages/${encodeURIComponent(lcId)}`, { method: 'DELETE' });
        if (!r.ok) {
          const err = (await r.json()).error || '刪除失敗';
          showToast(err, 'error');
          return;
        }
        await fetchLanguageConfigs();
        renderPipelineStrip();
        _renderLangConfigManageList();
        showToast(`已刪除語言配置：${lcId}`, 'success');
      } catch (e) {
        showToast(`刪除失敗: ${e.message}`, 'error');
      }
    }
```

- [ ] **Step 3: Run smoke — scenarios B, C, D, E should pass; only A still fails**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python3 /tmp/check_pipeline_crud.py
```

Expected:
```
FAIL A — save Profile preset: ...
PASS B — create language config
PASS C — apply language config (PATCH)
PASS D — built-in delete absent
PASS E — in-use delete blocked + toast
```

---

### Task 7: Frontend — Profile preset save + manage modals

Wire scenario A. Add modal markup + replace `openProfileSaveModal` / `openProfileManageModal` stubs with real implementations.

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add modal markup**

Add after the Language Config modals from Task 6:

```html
<!-- Profile Preset Save Modal -->
<div class="overlay" id="ppsOverlay">
  <div class="overlay-box" style="width: 540px;">
    <div class="overlay-head">
      <span>儲存為新 Pipeline 預設</span>
      <button class="or-close" onclick="closeProfileSaveModal()" aria-label="關閉">&times;</button>
    </div>
    <div class="overlay-body" style="padding: 16px 20px;">
      <div style="display:grid;gap:14px;">
        <label style="display:flex;flex-direction:column;gap:4px;">
          <span style="font-size:12px;font-weight:600;">預設名稱 *</span>
          <input id="ppsName" maxlength="80"
                 style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--surface-2);color:var(--text);">
        </label>
        <label style="display:flex;flex-direction:column;gap:4px;">
          <span style="font-size:12px;font-weight:600;">描述（可選）</span>
          <input id="ppsDesc" maxlength="160"
                 style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--surface-2);color:var(--text);">
        </label>
        <div id="ppsSummary" style="font-size:11px;color:var(--text-dim);background:var(--surface-2);padding:10px 12px;border-radius:4px;line-height:1.6;font-family:var(--font-mono);"></div>
      </div>
    </div>
    <div class="overlay-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 20px;">
      <button class="or-btn" onclick="closeProfileSaveModal()">取消</button>
      <button class="or-btn primary" id="ppsSaveBtn" onclick="saveProfileAsPreset()">儲存並啟用</button>
    </div>
  </div>
</div>

<!-- Profile Preset Manage Modal -->
<div class="overlay" id="ppmOverlay">
  <div class="overlay-box" style="width: 600px;">
    <div class="overlay-head">
      <span>Pipeline 預設管理</span>
      <button class="or-close" onclick="closeProfileManageModal()" aria-label="關閉">&times;</button>
    </div>
    <div class="overlay-body" id="ppmBody" style="padding: 12px 20px;"></div>
    <div class="overlay-footer" style="display:flex;justify-content:space-between;gap:8px;padding:12px 20px;">
      <button class="or-btn" onclick="openProfileSaveModal()">+ 新增預設</button>
      <button class="or-btn" onclick="closeProfileManageModal()">關閉</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Replace `openProfileSaveModal` / `openProfileManageModal` stubs with real implementations**

Find the two stubs added in Task 5 Step 4 (now still defined alongside the lang-config stubs that were already replaced in Task 6). Replace these two specifically:

```js
    let _ppsEditingId = null;

    function openProfileSaveModal(editingId = null) {
      _ppsEditingId = editingId;
      const editing = editingId ? availableProfiles.find(p => p.id === editingId) : null;
      const src = editing || activeProfile;
      if (!src) {
        showToast('請先啟用一個 Profile', 'error');
        return;
      }
      document.querySelector('#ppsOverlay .overlay-head span').textContent =
        editing ? '編輯 Pipeline 預設' : '儲存為新 Pipeline 預設';
      document.getElementById('ppsName').value = editing
        ? src.name
        : (src.name || '') + ' (副本)';
      document.getElementById('ppsDesc').value = src.description || '';
      const asr = src.asr || {};
      const tr = src.translation || {};
      const gloss = glossaries.find(g => g.id === tr.glossary_id);
      const font = src.font || {};
      document.getElementById('ppsSummary').innerHTML = `
        ASR        ${escapeHtml(asr.model_size || '—')} (${escapeHtml(asr.engine || '—')})<br>
        MT         ${escapeHtml(tr.engine || '—')}${tr.openrouter_model ? ' / ' + escapeHtml(tr.openrouter_model) : ''}<br>
        術語表     ${escapeHtml(gloss?.name || '無')}${gloss ? ' (' + (gloss.entry_count || gloss.entries?.length || 0) + ' 條)' : ''}<br>
        字型       ${escapeHtml(font.family || '—')}, ${font.size || '—'}pt`;
      document.getElementById('ppsSaveBtn').textContent = editing ? '儲存' : '儲存並啟用';
      document.getElementById('ppsOverlay').classList.add('open');
      setTimeout(() => document.getElementById('ppsName').focus(), 50);
    }

    function closeProfileSaveModal() {
      document.getElementById('ppsOverlay').classList.remove('open');
      _ppsEditingId = null;
    }

    async function saveProfileAsPreset() {
      const name = document.getElementById('ppsName').value.trim();
      const description = document.getElementById('ppsDesc').value.trim();
      if (!name) { showToast('預設名稱必填', 'error'); return; }
      try {
        if (_ppsEditingId) {
          // Edit mode: PATCH only name + description
          const r = await fetch(`${API_BASE}/api/profiles/${_ppsEditingId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description }),
          });
          if (!r.ok) throw new Error((await r.json()).error || '儲存失敗');
          await fetchProfiles();
          await fetchActiveProfile();
          renderPipelineStrip();
          closeProfileSaveModal();
          showToast(`已更新預設：${name}`, 'success');
          if (document.getElementById('ppmOverlay').classList.contains('open')) {
            _renderProfileManageList();
          }
        } else {
          // Create mode: POST cloned activeProfile, then activate
          if (!activeProfile) { showToast('請先啟用一個 Profile', 'error'); return; }
          const { id: _id, created_at: _ca, updated_at: _ua, ...rest } = activeProfile;
          const body = { ...rest, name, description };
          const r = await fetch(`${API_BASE}/api/profiles`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
          if (!r.ok) throw new Error((await r.json()).error || '建立失敗');
          const created = (await r.json()).profile;
          await fetch(`${API_BASE}/api/profiles/${created.id}/activate`, { method: 'POST' });
          await fetchProfiles();
          await fetchActiveProfile();
          renderPipelineStrip();
          closeProfileSaveModal();
          showToast(`已儲存並啟用：${name}`, 'success');
        }
      } catch (e) {
        showToast(`儲存失敗: ${e.message}`, 'error');
      }
    }

    function openProfileManageModal() {
      _renderProfileManageList();
      document.getElementById('ppmOverlay').classList.add('open');
    }

    function closeProfileManageModal() {
      document.getElementById('ppmOverlay').classList.remove('open');
    }

    function _renderProfileManageList() {
      const body = document.getElementById('ppmBody');
      const activeId = activeProfile?.id;
      body.innerHTML = availableProfiles.map(p => {
        const isActive = p.id === activeId;
        const summary = `ASR ${p.asr?.model_size || '—'} · MT ${(p.translation?.engine || '—').replace(/-cloud$/,'')}`;
        return `
          <div data-prof-id="${escapeHtml(p.id)}" style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);">
            <div style="flex:1;min-width:0;cursor:pointer;" onclick="activateProfile('${p.id}'); _renderProfileManageList();">
              <div style="font-weight:600;font-size:13px;">
                ${isActive ? '<span style="color:var(--accent-2);">✓ </span>' : ''}${escapeHtml(p.name || p.id)}
                ${isActive ? '<span class="smn-badge" style="margin-left:6px;">當前</span>' : ''}
              </div>
              ${p.description ? `<div style="font-size:11px;color:var(--text-dim);margin-top:2px;">${escapeHtml(p.description)}</div>` : ''}
              <div style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono);">${escapeHtml(summary)}</div>
            </div>
            <button class="btn btn-ghost btn-sm" data-action="edit" onclick="openProfileSaveModal('${p.id}')" title="編輯">✎</button>
            ${isActive ? '' : `<button class="btn btn-ghost btn-sm" data-action="delete" onclick="deleteProfilePreset('${p.id}')" title="刪除">🗑</button>`}
          </div>`;
      }).join('') || '<div style="color:var(--text-dim);padding:12px 0;">暫無預設</div>';
    }

    async function deleteProfilePreset(profId) {
      const prof = availableProfiles.find(p => p.id === profId);
      if (!prof) return;
      if (!confirm(`確定刪除預設「${prof.name || profId}」？`)) return;
      try {
        const r = await fetch(`${API_BASE}/api/profiles/${encodeURIComponent(profId)}`, { method: 'DELETE' });
        if (!r.ok) throw new Error((await r.json()).error || '刪除失敗');
        await fetchProfiles();
        renderPipelineStrip();
        _renderProfileManageList();
        showToast(`已刪除預設：${prof.name || profId}`, 'success');
      } catch (e) {
        showToast(`刪除失敗: ${e.message}`, 'error');
      }
    }
```

- [ ] **Step 3: Wire the existing two stub buttons in Pipeline preset menu**

Find lines 1975–1976 in `renderPipelineStrip()`:

```js
          <button class="smn-manage"><span class="fmt-badge outline">💾</span><span class="fmt-desc">將當前設定儲存為新預設…</span></button>
          <button class="smn-manage"><span class="fmt-badge outline">⚙</span><span class="fmt-desc">管理預設…</span></button>
```

Replace with:

```js
          <button class="smn-manage" onclick="openProfileSaveModal()"><span class="fmt-badge outline">💾</span><span class="fmt-desc">將當前設定儲存為新預設…</span></button>
          <button class="smn-manage" onclick="openProfileManageModal()"><span class="fmt-badge outline">⚙</span><span class="fmt-desc">管理預設…</span></button>
```

---

### Task 8: GREEN run + commit

- [ ] **Step 1: Run all 5 Playwright scenarios — expect all PASS**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python3 /tmp/check_pipeline_crud.py
```

Expected:
```
PASS A — save Profile preset
PASS B — create language config
PASS C — apply language config (PATCH)
PASS D — built-in delete absent
PASS E — in-use delete blocked + toast

All scenarios PASSED
```

Exit code 0.

- [ ] **Step 2: Re-run backend tests one more time to confirm no regression**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_languages_crud.py -v
pytest tests/ -q
```

Expected: 8/8 in `test_languages_crud.py`; full suite passes (or only the documented v3.3 macOS tmpdir test fails).

- [ ] **Step 3: Commit frontend implementation**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/index.html
git commit -m "feat(pipeline): wire preset CRUD + add language config CRUD in ASR menu

- Profile preset menu's 💾 / ⚙ buttons now open save/manage modals
- ASR step menu adds language config sub-section + ➕ create + ⚙ manage
- New modals: language config create/edit, language config manage,
  Profile preset save, Profile preset manage
- New handlers: applyLanguageConfig, saveLanguageConfig,
  deleteLanguageConfig, saveProfileAsPreset, deleteProfilePreset
- New global cache: availableLanguageConfigs (fetched at boot)"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Profile preset 「💾 儲存當前設定」 modal — Task 7 Step 1 markup + Step 2 `openProfileSaveModal`/`saveProfileAsPreset`
- ✅ Profile preset 「⚙ 管理預設」 modal — Task 7 Step 1 markup + Step 2 `openProfileManageModal`/`_renderProfileManageList`/`deleteProfilePreset`
- ✅ ASR step menu language config sub-section — Task 5 Step 3
- ✅ `applyLanguageConfig()` handler — Task 5 Step 2
- ✅ ➕ 新增 modal — Task 6 Step 1 markup + Step 2 `openLangConfigCreateModal`/`saveLanguageConfig`
- ✅ ⚙ 管理 modal — Task 6 Step 1 markup + Step 2 `openLangConfigManageModal`/`_renderLangConfigManageList`/`deleteLanguageConfig`
- ✅ Backend POST `/api/languages` — Task 3 Step 1
- ✅ Backend DELETE `/api/languages/<id>` with built-in + in-use protection — Task 3 Step 1
- ✅ Manager `create()` / `delete()` — Task 2 Step 1
- ✅ Built-in (`en`/`zh`) protection — Task 6 Step 2 `_renderLangConfigManageList` skips delete button; Task 3 Step 1 returns 400
- ✅ In-use delete blocked + toast — Task 3 Step 1 returns 400 with profile names; Task 6 Step 2 `deleteLanguageConfig` shows toast and keeps modal open
- ✅ Pipeline strip ASR step display optionally shows lc_id — left out (spec marked it optional). If needed, can be added by changing Task 5's `renderPipelineStrip` line that builds the `[ASR]` step display label.
- ✅ 8 backend pytest tests — Task 1
- ✅ 5 Playwright scenarios — Task 4

**Placeholder scan:** Every step has actual code or exact commands. No TBDs, no "implement later". ✅

**Type consistency:**
- `openLangConfigCreateModal(prefillId)` defined Task 6 Step 2; called from Task 6 Step 2 `_renderLangConfigManageList` row's `onclick="openLangConfigCreateModal('${lc.id}')"` — matches signature ✅
- `openProfileSaveModal(editingId)` defined Task 7 Step 2; called from Task 7 Step 2 `_renderProfileManageList` row's `onclick="openProfileSaveModal('${p.id}')"` — matches signature ✅
- `availableLanguageConfigs` declared Task 5 Step 1 as global; referenced in Task 5 Step 3 (`renderPipelineStrip`) and Task 6 Step 2 (`_renderLangConfigManageList`) ✅
- `_lcEditingId`/`_ppsEditingId` private state; clear lifecycle via close handlers ✅
- POST body shape from Task 6 Step 2 (`{id, name, asr:{max_words_per_segment, max_segment_duration}, translation:{batch_size, temperature}}`) matches backend `LanguageConfigManager.create()` keys (Task 2 Step 1) and pytest body fixture (Task 1 Step 1) ✅
- DELETE response shape `{ok: true}` (Task 3 Step 1) matches Task 1 assertion `resp.get_json().get("ok") is True` ✅
- DELETE error response `{error: "..."}` (Task 3 Step 1) consumed by Task 6 Step 2 `deleteLanguageConfig` `(await r.json()).error` and Task 1 `resp.get_json()["error"]` ✅
- Validation ranges: Task 2 uses existing constants from `language_config.py` (5–200, 1.0–60.0, 1–50, 0.0–2.0); Task 6 sliders mirror those ranges ✅
