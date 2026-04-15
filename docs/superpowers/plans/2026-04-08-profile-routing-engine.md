# Model Profile & Routing Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a profile system that lets users define and switch between ASR + translation model combinations, with environment-aware defaults (dev vs production).

**Architecture:** Profiles are stored as JSON files in `config/profiles/`, with an active profile pointer in `config/settings.json`. A Python module (`backend/profiles.py`) provides the CRUD interface. Flask routes expose REST endpoints. The frontend adds a profile selector dropdown that replaces the current model selector when in "broadcast pipeline" mode.

**Tech Stack:** Python 3.8+, Flask, JSON file storage, vanilla JS frontend.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/profiles.py` | Profile CRUD logic, validation, active profile management |
| Create | `backend/config/settings.json` | Global settings including active profile ID |
| Create | `backend/config/profiles/dev-default.json` | Default dev profile (Whisper tiny + Qwen2.5-3B) |
| Create | `backend/config/profiles/prod-default.json` | Default production profile (Qwen3-ASR + Qwen3-235B) |
| Create | `backend/tests/test_profiles.py` | Unit tests for profile CRUD |
| Modify | `backend/app.py` | Register profile REST endpoints |
| Modify | `frontend/index.html` | Profile selector UI |

---

### Task 1: Create profile data module with schema validation

**Files:**
- Create: `backend/profiles.py`
- Create: `backend/config/settings.json`
- Create: `backend/config/profiles/` (directory)
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_profiles.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/config/profiles
mkdir -p backend/tests
touch backend/tests/__init__.py
```

- [ ] **Step 2: Write failing test for profile validation**

Create `backend/tests/test_profiles.py`:

```python
import pytest
import json
import shutil
from pathlib import Path

# Use a temp config dir for each test
@pytest.fixture
def config_dir(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"active_profile": None}))
    return tmp_path


def test_validate_profile_valid(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Test Profile",
        "description": "For testing",
        "asr": {
            "engine": "whisper",
            "model_size": "tiny",
            "language": "en",
            "device": "cpu"
        },
        "translation": {
            "engine": "qwen2.5-3b",
            "quantization": "q4",
            "temperature": 0.1,
            "glossary_id": None
        }
    }
    errors = mgr.validate(profile_data)
    assert errors == []


def test_validate_profile_missing_name(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    profile_data = {
        "description": "No name",
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert "name is required" in errors


def test_validate_profile_invalid_asr_engine(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Bad Engine",
        "description": "",
        "asr": {"engine": "nonexistent", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert any("asr.engine" in e for e in errors)


def test_validate_profile_missing_asr(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "No ASR",
        "description": "",
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert "asr is required" in errors
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles'`

- [ ] **Step 4: Implement ProfileManager with validation**

Create `backend/profiles.py`:

```python
"""Profile management for ASR + Translation model routing."""

import json
import uuid
import time
from pathlib import Path

VALID_ASR_ENGINES = {"whisper", "qwen3-asr", "flg-asr"}
VALID_TRANSLATION_ENGINES = {"qwen3-235b", "qwen2.5-72b", "qwen2.5-7b", "qwen2.5-3b"}
VALID_DEVICES = {"cpu", "cuda", "mps", "auto"}


class ProfileManager:
    def __init__(self, config_dir: Path):
        self._config_dir = Path(config_dir)
        self._profiles_dir = self._config_dir / "profiles"
        self._settings_file = self._config_dir / "settings.json"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        if not self._settings_file.exists():
            self._write_settings({"active_profile": None})

    def _read_settings(self) -> dict:
        return json.loads(self._settings_file.read_text(encoding="utf-8"))

    def _write_settings(self, settings: dict) -> None:
        self._settings_file.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _profile_path(self, profile_id: str) -> Path:
        return self._profiles_dir / f"{profile_id}.json"

    def validate(self, data: dict) -> list[str]:
        """Validate profile data. Returns list of error strings (empty = valid)."""
        errors = []

        if not data.get("name"):
            errors.append("name is required")

        asr = data.get("asr")
        if not asr:
            errors.append("asr is required")
        else:
            if asr.get("engine") not in VALID_ASR_ENGINES:
                errors.append(f"asr.engine must be one of {sorted(VALID_ASR_ENGINES)}")
            if not asr.get("language"):
                errors.append("asr.language is required")
            if asr.get("device") and asr["device"] not in VALID_DEVICES:
                errors.append(f"asr.device must be one of {sorted(VALID_DEVICES)}")

        translation = data.get("translation")
        if not translation:
            errors.append("translation is required")
        else:
            if translation.get("engine") not in VALID_TRANSLATION_ENGINES:
                errors.append(f"translation.engine must be one of {sorted(VALID_TRANSLATION_ENGINES)}")

        return errors

    def create(self, data: dict) -> dict:
        """Create a new profile. Returns the created profile with id."""
        errors = self.validate(data)
        if errors:
            raise ValueError(errors)

        profile_id = uuid.uuid4().hex[:12]
        profile = {
            "id": profile_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "asr": data["asr"],
            "translation": data["translation"],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._profile_path(profile_id).write_text(
            json.dumps(profile, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return profile

    def get(self, profile_id: str) -> dict | None:
        """Get a profile by ID. Returns None if not found."""
        path = self._profile_path(profile_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[dict]:
        """List all profiles, sorted by name."""
        profiles = []
        for path in self._profiles_dir.glob("*.json"):
            profiles.append(json.loads(path.read_text(encoding="utf-8")))
        return sorted(profiles, key=lambda p: p.get("name", ""))

    def update(self, profile_id: str, data: dict) -> dict | None:
        """Update a profile. Returns updated profile or None if not found."""
        existing = self.get(profile_id)
        if not existing:
            return None

        merged = {**existing, **data, "id": profile_id, "updated_at": time.time()}
        # Re-validate the merged result
        errors = self.validate(merged)
        if errors:
            raise ValueError(errors)

        self._profile_path(profile_id).write_text(
            json.dumps(merged, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return merged

    def delete(self, profile_id: str) -> bool:
        """Delete a profile. Returns True if deleted, False if not found."""
        path = self._profile_path(profile_id)
        if not path.exists():
            return False
        path.unlink()
        # If this was the active profile, clear active
        settings = self._read_settings()
        if settings.get("active_profile") == profile_id:
            settings["active_profile"] = None
            self._write_settings(settings)
        return True

    def get_active(self) -> dict | None:
        """Get the active profile. Returns None if no active profile set."""
        settings = self._read_settings()
        active_id = settings.get("active_profile")
        if not active_id:
            return None
        return self.get(active_id)

    def set_active(self, profile_id: str) -> dict | None:
        """Set a profile as active. Returns the profile or None if not found."""
        profile = self.get(profile_id)
        if not profile:
            return None
        settings = self._read_settings()
        settings["active_profile"] = profile_id
        self._write_settings(settings)
        return profile
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_profiles.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/profiles.py backend/tests/
git commit -m "feat: add ProfileManager with validation and schema"
```

---

### Task 2: Add CRUD and active profile tests

**Files:**
- Modify: `backend/tests/test_profiles.py`

- [ ] **Step 1: Add CRUD tests**

Append to `backend/tests/test_profiles.py`:

```python
VALID_PROFILE = {
    "name": "Dev Default",
    "description": "Development testing profile",
    "asr": {
        "engine": "whisper",
        "model_size": "tiny",
        "language": "en",
        "device": "cpu"
    },
    "translation": {
        "engine": "qwen2.5-3b",
        "quantization": "q4",
        "temperature": 0.1,
        "glossary_id": None
    }
}


def test_create_profile(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    profile = mgr.create(VALID_PROFILE)
    assert profile["id"]
    assert profile["name"] == "Dev Default"
    assert profile["asr"]["engine"] == "whisper"
    assert profile["created_at"] > 0


def test_create_profile_invalid_raises(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    with pytest.raises(ValueError):
        mgr.create({"name": ""})


def test_get_profile(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    fetched = mgr.get(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Dev Default"


def test_get_nonexistent_returns_none(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    assert mgr.get("nonexistent") is None


def test_list_profiles(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    mgr.create({**VALID_PROFILE, "name": "Bravo"})
    mgr.create({**VALID_PROFILE, "name": "Alpha"})
    profiles = mgr.list_all()
    assert len(profiles) == 2
    assert profiles[0]["name"] == "Alpha"  # sorted by name
    assert profiles[1]["name"] == "Bravo"


def test_update_profile(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    updated = mgr.update(created["id"], {
        "name": "Updated Name",
        "asr": {**VALID_PROFILE["asr"], "model_size": "base"},
        "translation": VALID_PROFILE["translation"],
    })
    assert updated["name"] == "Updated Name"
    assert updated["asr"]["model_size"] == "base"
    assert updated["id"] == created["id"]


def test_update_nonexistent_returns_none(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    assert mgr.update("nonexistent", VALID_PROFILE) is None


def test_delete_profile(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    assert mgr.delete(created["id"]) is True
    assert mgr.get(created["id"]) is None


def test_delete_nonexistent_returns_false(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    assert mgr.delete("nonexistent") is False


def test_set_and_get_active_profile(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    p1 = mgr.create({**VALID_PROFILE, "name": "Profile 1"})
    p2 = mgr.create({**VALID_PROFILE, "name": "Profile 2"})

    mgr.set_active(p1["id"])
    assert mgr.get_active()["id"] == p1["id"]

    mgr.set_active(p2["id"])
    assert mgr.get_active()["id"] == p2["id"]


def test_get_active_when_none_set(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    assert mgr.get_active() is None


def test_delete_active_profile_clears_active(config_dir):
    from profiles import ProfileManager

    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    mgr.set_active(created["id"])
    mgr.delete(created["id"])
    assert mgr.get_active() is None
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/test_profiles.py -v`
Expected: All 15 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_profiles.py
git commit -m "test: add comprehensive CRUD and active profile tests"
```

---

### Task 3: Create default profile files

**Files:**
- Create: `backend/config/settings.json`
- Create: `backend/config/profiles/dev-default.json`
- Create: `backend/config/profiles/prod-default.json`

- [ ] **Step 1: Create settings.json**

Create `backend/config/settings.json`:

```json
{
  "active_profile": "dev-default"
}
```

- [ ] **Step 2: Create dev-default profile**

Create `backend/config/profiles/dev-default.json`:

```json
{
  "id": "dev-default",
  "name": "Development",
  "description": "Lightweight models for development and testing on MacBook (16GB RAM)",
  "asr": {
    "engine": "whisper",
    "model_size": "tiny",
    "language": "en",
    "device": "auto"
  },
  "translation": {
    "engine": "qwen2.5-3b",
    "quantization": "q4",
    "temperature": 0.1,
    "glossary_id": null
  },
  "created_at": 1712534400,
  "updated_at": 1712534400
}
```

- [ ] **Step 3: Create prod-default profile**

Create `backend/config/profiles/prod-default.json`:

```json
{
  "id": "prod-default",
  "name": "Broadcast Production",
  "description": "Full quality models for Dell Pro Max GB10 (128GB RAM)",
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
    "glossary_id": null
  },
  "created_at": 1712534400,
  "updated_at": 1712534400
}
```

- [ ] **Step 4: Verify ProfileManager loads default profiles**

Run:
```bash
cd backend && python -c "
from profiles import ProfileManager
from pathlib import Path
mgr = ProfileManager(Path('config'))
profiles = mgr.list_all()
print(f'Profiles: {len(profiles)}')
for p in profiles:
    print(f'  {p[\"id\"]}: {p[\"name\"]}')
active = mgr.get_active()
print(f'Active: {active[\"name\"] if active else None}')
"
```

Expected output:
```
Profiles: 2
  dev-default: Development
  prod-default: Broadcast Production
Active: Development
```

- [ ] **Step 5: Commit**

```bash
git add backend/config/
git commit -m "feat: add default dev and production profile configs"
```

---

### Task 4: Add REST API endpoints to app.py

**Files:**
- Modify: `backend/app.py` (add routes, import ProfileManager)

- [ ] **Step 1: Write API integration test**

Append to `backend/tests/test_profiles.py`:

```python
import sys
from pathlib import Path

# Ensure backend is on sys.path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def client(tmp_path):
    """Create a Flask test client with a temp config dir."""
    from app import app, _init_profile_manager
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_list_profiles_empty(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profiles"] == []


def test_api_create_profile(client):
    resp = client.post("/api/profiles", json=VALID_PROFILE)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["profile"]["name"] == "Dev Default"
    assert data["profile"]["id"]


def test_api_create_invalid_returns_400(client):
    resp = client.post("/api/profiles", json={"name": ""})
    assert resp.status_code == 400
    assert "errors" in resp.get_json()


def test_api_get_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.get(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    assert resp.get_json()["profile"]["id"] == pid


def test_api_get_nonexistent_returns_404(client):
    resp = client.get("/api/profiles/nonexistent")
    assert resp.status_code == 404


def test_api_update_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.patch(f"/api/profiles/{pid}", json={
        "name": "Updated",
        "asr": VALID_PROFILE["asr"],
        "translation": VALID_PROFILE["translation"],
    })
    assert resp.status_code == 200
    assert resp.get_json()["profile"]["name"] == "Updated"


def test_api_delete_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.delete(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    resp2 = client.get(f"/api/profiles/{pid}")
    assert resp2.status_code == 404


def test_api_activate_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.post(f"/api/profiles/{pid}/activate")
    assert resp.status_code == 200
    # Verify active
    resp2 = client.get("/api/profiles/active")
    assert resp2.status_code == 200
    assert resp2.get_json()["profile"]["id"] == pid


def test_api_get_active_when_none(client):
    resp = client.get("/api/profiles/active")
    assert resp.status_code == 200
    assert resp.get_json()["profile"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_profiles.py::test_api_list_profiles_empty -v`
Expected: FAIL — `ImportError: cannot import name '_init_profile_manager'`

- [ ] **Step 3: Add profile routes to app.py**

Add these lines near the top of `backend/app.py`, after the existing imports and app setup (after line ~47):

```python
from profiles import ProfileManager

# Profile management
CONFIG_DIR = Path(__file__).parent / "config"
_profile_manager = ProfileManager(CONFIG_DIR)


def _init_profile_manager(config_dir: Path):
    """Re-initialize profile manager (used by tests)."""
    global _profile_manager
    _profile_manager = ProfileManager(config_dir)
```

Add these routes after the existing `/api/models` route (after line ~545):

```python
# ============================================================
# Profile Management API
# ============================================================

@app.route('/api/profiles', methods=['GET'])
def api_list_profiles():
    """List all profiles."""
    return jsonify({"profiles": _profile_manager.list_all()})


@app.route('/api/profiles', methods=['POST'])
def api_create_profile():
    """Create a new profile."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        profile = _profile_manager.create(data)
        return jsonify({"profile": profile}), 201
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/profiles/active', methods=['GET'])
def api_get_active_profile():
    """Get the active profile."""
    profile = _profile_manager.get_active()
    return jsonify({"profile": profile})


@app.route('/api/profiles/<profile_id>', methods=['GET'])
def api_get_profile(profile_id):
    """Get a profile by ID."""
    profile = _profile_manager.get(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"profile": profile})


@app.route('/api/profiles/<profile_id>', methods=['PATCH'])
def api_update_profile(profile_id):
    """Update a profile."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        profile = _profile_manager.update(profile_id, data)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify({"profile": profile})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/profiles/<profile_id>', methods=['DELETE'])
def api_delete_profile(profile_id):
    """Delete a profile."""
    if _profile_manager.delete(profile_id):
        return jsonify({"message": "Profile deleted"})
    return jsonify({"error": "Profile not found"}), 404


@app.route('/api/profiles/<profile_id>/activate', methods=['POST'])
def api_activate_profile(profile_id):
    """Set a profile as active."""
    profile = _profile_manager.set_active(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"profile": profile})
```

**Important:** The `/api/profiles/active` route MUST be registered BEFORE the `/api/profiles/<profile_id>` route, otherwise Flask will treat "active" as a profile_id.

- [ ] **Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/test_profiles.py -v`
Expected: All 24 tests PASS (15 unit + 9 API)

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_profiles.py
git commit -m "feat: add profile REST API endpoints"
```

---

### Task 5: Add profile selector to frontend

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add profile selector dropdown in the controls panel**

Find the model selector HTML (around line 737):

```html
<select id="modelSelect">
```

Add a profile selector section BEFORE the model selector `control-group`:

```html
        <div class="control-group">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <label>Pipeline Profile</label>
            <span class="range-value" id="activeProfileName" style="font-size:12px;">—</span>
          </div>
          <select id="profileSelect" onchange="activateProfile(this.value)">
            <option value="">Select profile...</option>
          </select>
          <div id="profileInfo" style="font-size:11px;margin-top:4px;color:var(--text-dim);"></div>
        </div>
```

- [ ] **Step 2: Add profile JS functions**

Add these functions in the `// Settings` section of the `<script>` block (around line 1930):

```javascript
// ============================================================
// Profile Management
// ============================================================
let profilesData = [];

async function loadProfiles() {
  try {
    const resp = await fetch(`${API_BASE}/api/profiles`);
    const data = await resp.json();
    profilesData = data.profiles || [];
    renderProfileSelect();
    await loadActiveProfile();
  } catch (e) {
    console.warn('Failed to load profiles:', e);
  }
}

function renderProfileSelect() {
  const select = document.getElementById('profileSelect');
  const currentValue = select.value;
  select.innerHTML = '<option value="">Select profile...</option>';
  for (const p of profilesData) {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    select.appendChild(opt);
  }
  if (currentValue) select.value = currentValue;
}

async function loadActiveProfile() {
  try {
    const resp = await fetch(`${API_BASE}/api/profiles/active`);
    const data = await resp.json();
    const profile = data.profile;
    const nameEl = document.getElementById('activeProfileName');
    const infoEl = document.getElementById('profileInfo');
    const select = document.getElementById('profileSelect');

    if (profile) {
      nameEl.textContent = profile.name;
      select.value = profile.id;
      infoEl.textContent = `ASR: ${profile.asr.engine} (${profile.asr.model_size}) | Translation: ${profile.translation.engine}`;
    } else {
      nameEl.textContent = '—';
      select.value = '';
      infoEl.textContent = '';
    }
  } catch (e) {
    console.warn('Failed to load active profile:', e);
  }
}

async function activateProfile(profileId) {
  if (!profileId) return;
  try {
    const resp = await fetch(`${API_BASE}/api/profiles/${profileId}/activate`, { method: 'POST' });
    if (resp.ok) {
      await loadActiveProfile();
      showToast('Profile activated', 'success');
    }
  } catch (e) {
    showToast('Failed to activate profile', 'error');
  }
}
```

- [ ] **Step 3: Call loadProfiles() on page load**

Find the existing `DOMContentLoaded` or initialization block. Add `loadProfiles()` to the init sequence. Look for where `fetchModelStatus()` is called (around line 1870) and add after it:

```javascript
loadProfiles();
```

- [ ] **Step 4: Test in browser**

1. Open the page.
2. Verify the "Pipeline Profile" dropdown appears above the model selector.
3. Verify "Development" and "Broadcast Production" appear in the dropdown.
4. Select "Development" — verify info text shows "ASR: whisper (tiny) | Translation: qwen2.5-3b".
5. Refresh page — verify the active profile persists.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add profile selector UI to frontend"
```

---

### Task 6: Manual integration test

**Files:** None (verification only)

- [ ] **Step 1: Start the backend**

```bash
cd backend && source venv/bin/activate && python app.py
```

- [ ] **Step 2: Test API with curl**

```bash
# List profiles
curl -s http://localhost:5001/api/profiles | python3 -m json.tool

# Get active profile
curl -s http://localhost:5001/api/profiles/active | python3 -m json.tool

# Create a custom profile
curl -s -X POST http://localhost:5001/api/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "News Fast",
    "description": "Fast turnaround for news clips",
    "asr": {"engine": "whisper", "model_size": "base", "language": "en", "device": "auto"},
    "translation": {"engine": "qwen2.5-7b", "quantization": "q4", "temperature": 0.1, "glossary_id": null}
  }' | python3 -m json.tool

# Activate it
curl -s -X POST http://localhost:5001/api/profiles/<id_from_above>/activate | python3 -m json.tool

# Delete it
curl -s -X DELETE http://localhost:5001/api/profiles/<id_from_above> | python3 -m json.tool
```

Expected: All return valid JSON, correct status codes.

- [ ] **Step 3: Test frontend**

1. Open `frontend/index.html` in browser.
2. Profile dropdown loads with profiles.
3. Switch profiles — info text updates.
4. Refresh — active profile persists.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 1 — Model Profile & Routing Engine"
```
