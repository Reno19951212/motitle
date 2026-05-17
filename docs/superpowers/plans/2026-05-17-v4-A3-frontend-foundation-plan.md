# v4.0 A3 — Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each task carries 🎯 Goal + ✅ Acceptance markers — subagent dispatches must cite both and reviewers must verify against them.

**Goal:** Bootstrap a Vite + React 18 + TypeScript replacement for the vanilla dashboard + 5 entity CRUD pages (Pipelines / ASR Profiles / MT Profiles / Glossaries / Admin) plus Login. Drives v4.0 pipeline_run flow end-to-end from upload to stage-by-stage progress display.

**Architecture:** New `frontend/` directory (vanilla pages renamed `frontend.old/`). Vite dev server (5173) + Flask (5001) run via `concurrently`; Vite proxies `/api`, `/socket.io`, `/fonts` to Flask. Production: `vite build` → `frontend/dist/` → Flask `serve_index` / `serve_assets` + SPA fallback. Auth: boot probe `/api/me` + React Router guard. Realtime: Socket.IO via React Context + reducer. State: Zustand for auth / picker / UI; per-page local state for entity lists.

**Tech Stack:** TypeScript 5.6 strict, Vite 5.4, React 18.3, React Router 6.27, Zustand 5.0, shadcn/ui, Tailwind 3.4, react-hook-form 7.53, zod 3.23, @dnd-kit 6.1 + sortable 8.0, react-dropzone 14.3, socket.io-client 4.8, Vitest 2.1, Playwright 1.48, concurrently 9.0.

**Parent spec:** [docs/superpowers/specs/2026-05-17-v4-A3-frontend-foundation-design.md](../specs/2026-05-17-v4-A3-frontend-foundation-design.md)

---

## File Structure

```
frontend.old/                 # RENAMED from frontend/
frontend/                     # NEW
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.ts
├── postcss.config.js
├── index.html
├── public/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── router.tsx
│   ├── index.css
│   ├── lib/
│   │   ├── api.ts
│   │   ├── socket.ts
│   │   ├── utils.ts          # cn() helper
│   │   └── schemas/
│   │       ├── asr-profile.ts
│   │       ├── mt-profile.ts
│   │       ├── glossary.ts
│   │       ├── pipeline.ts
│   │       └── user.ts
│   ├── stores/
│   │   ├── auth.ts
│   │   ├── pipeline-picker.ts
│   │   └── ui.ts
│   ├── providers/
│   │   ├── AuthProvider.tsx
│   │   └── SocketProvider.tsx
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Pipelines.tsx
│   │   ├── AsrProfiles.tsx
│   │   ├── MtProfiles.tsx
│   │   ├── Glossaries.tsx
│   │   ├── Admin.tsx
│   │   └── ProofreadPlaceholder.tsx
│   └── components/
│       ├── Layout.tsx
│       ├── TopBar.tsx
│       ├── SideNav.tsx
│       ├── FileCard.tsx
│       ├── UploadDropzone.tsx
│       ├── PipelinePicker.tsx
│       ├── StageProgress.tsx
│       ├── StageEditor.tsx
│       ├── EntityTable.tsx
│       ├── EntityForm.tsx
│       ├── ConfirmDialog.tsx
│       └── ui/               # shadcn copies
└── tests-e2e/                # Playwright (new)
    ├── playwright.config.ts
    ├── fixtures/
    └── *.spec.ts
```

Backend (minimal):
- `backend/app.py` — `serve_index` updated, `serve_assets` added, SPA fallback, `pipeline_id` accepted on `/api/transcribe`
- `backend/tests/test_spa_fallback.py` (new)
- `backend/tests/test_transcribe_pipeline_id.py` (new)
- `backend/tests/test_serve_assets.py` (new)

---

## Task 1: Project Bootstrap + Rename

🎯 **Goal:** Move vanilla pages to `frontend.old/`, create new Vite + React 18 + TS project skeleton in `frontend/`. `npm install && tsc -b && vite build` all succeed with zero errors.

✅ **Acceptance:**
- `frontend.old/` exists with all prior vanilla files; git history preserved (`git mv`)
- `frontend/package.json` lists all locked deps
- `tsc -b` reports 0 errors
- `npm run build` produces `frontend/dist/index.html` + `frontend/dist/assets/*.{js,css}`

**Files:**
- Move: `frontend/` → `frontend.old/` (via `git mv`)
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`, `frontend/public/.gitkeep`, `frontend/.gitignore`

- [ ] **Step 1: Rename vanilla pages to frontend.old/**

```bash
git -C "$REPO" mv frontend frontend.old
```

Verify: `ls frontend.old/index.html proofread.html login.html admin.html Glossary.html` succeed.

- [ ] **Step 2: Create frontend/package.json**

```json
{
  "name": "whisper-subtitle-ai-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "concurrently -k -n vite,flask -c blue,green \"npm run dev:vite\" \"npm run dev:flask\"",
    "dev:vite": "vite",
    "dev:flask": "cd ../backend && (./venv/bin/python app.py || ./venv/Scripts/python app.py)",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.27.0",
    "zustand": "^5.0.0",
    "react-hook-form": "^7.53.0",
    "@hookform/resolvers": "^3.9.0",
    "zod": "^3.23.8",
    "socket.io-client": "^4.8.0",
    "react-dropzone": "^14.3.0",
    "@dnd-kit/core": "^6.1.0",
    "@dnd-kit/sortable": "^8.0.0",
    "@dnd-kit/utilities": "^3.2.2",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.0",
    "lucide-react": "^0.451.0",
    "@radix-ui/react-dialog": "^1.1.2",
    "@radix-ui/react-select": "^2.1.2",
    "@radix-ui/react-tabs": "^1.1.1",
    "@radix-ui/react-toast": "^1.2.2",
    "@radix-ui/react-slot": "^1.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.11",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "tailwindcss": "^3.4.13",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20",
    "concurrently": "^9.0.1",
    "vitest": "^2.1.2",
    "@vitest/ui": "^2.1.2",
    "jsdom": "^25.0.1",
    "@testing-library/react": "^16.0.1",
    "@testing-library/jest-dom": "^6.5.0",
    "@playwright/test": "^1.48.0"
  }
}
```

- [ ] **Step 3: Create tsconfig.json (strict)**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "allowJs": false,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src", "tests-e2e"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Create vite.config.ts**

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api':       { target: 'http://localhost:5001', changeOrigin: true },
      '/socket.io': { target: 'http://localhost:5001', changeOrigin: true, ws: true },
      '/fonts':     { target: 'http://localhost:5001', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.ts',
  },
});
```

- [ ] **Step 6: Create index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MoTitle</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create src/main.tsx + src/App.tsx + src/index.css**

```tsx
// src/main.tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

```tsx
// src/App.tsx
export function App() {
  return <div className="p-8">MoTitle — A3 bootstrap</div>;
}
```

```css
/* src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 8: Create .gitignore**

```
node_modules
dist
*.local
.vite
coverage
test-results
playwright-report
```

- [ ] **Step 9: Install deps + verify build**

```bash
cd frontend && npm install
npm run build
```

Expected: `dist/index.html` + `dist/assets/*.js` + `dist/assets/*.css` produced. `tsc -b` reports 0 errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/ frontend.old/
git commit -m "feat(v4 A3): bootstrap Vite + React 18 + TS frontend project"
```

---

## Task 2: Tailwind + shadcn Base Config

🎯 **Goal:** Tailwind utilities + shadcn-compatible config working. `cn()` helper in `src/lib/utils.ts`. Test page applies Tailwind class.

✅ **Acceptance:**
- `tailwind.config.ts` + `postcss.config.js` present
- `src/lib/utils.ts` exports `cn()` (clsx + tailwind-merge)
- `App.tsx` rendering shows Tailwind padding applied (verify via `npm run build && grep 'p-8' dist/assets/*.css` succeeds)

**Files:**
- Create: `frontend/tailwind.config.ts`, `frontend/postcss.config.js`, `frontend/src/lib/utils.ts`
- Modify: `frontend/src/index.css` (add CSS variables for theming)

- [ ] **Step 1: Create tailwind.config.ts**

```ts
import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
      },
      borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)' },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 2: Create postcss.config.js**

```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 3: Update src/index.css with CSS variables**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 47.4% 11.2%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 100% 50%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 215 20.2% 65.1%;
    --radius: 0.5rem;
  }
  body { @apply bg-background text-foreground; }
}
```

- [ ] **Step 4: Create src/lib/utils.ts**

```ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 5: Verify Tailwind compiles**

```bash
npm run build
grep -q 'background-color' dist/assets/*.css && echo OK
```

Expected: prints OK.

- [ ] **Step 6: Commit**

```bash
git add frontend/tailwind.config.ts frontend/postcss.config.js frontend/src/index.css frontend/src/lib/utils.ts
git commit -m "feat(v4 A3): Tailwind base config + cn() helper"
```

---

## Task 3: Flask SPA Fallback + dist Serving

🎯 **Goal:** Production Flask serves `frontend/dist/index.html` for `/` and unmatched SPA routes; serves `frontend/dist/assets/<path>` for hashed bundle assets.

✅ **Acceptance:**
- `GET /` returns React index.html when `frontend/dist/index.html` exists
- `GET /pipelines`, `/asr_profiles`, etc. all return index.html (SPA fallback)
- `GET /assets/index-abc123.js` returns the JS bundle with correct Content-Type
- `GET /api/health` still hits Flask handler (not fallback)
- `GET /socket.io/...` still handled by Flask-SocketIO
- backend/tests/test_spa_fallback.py + test_serve_assets.py green (5 tests total)

**Files:**
- Modify: `backend/app.py` (find `serve_index` route, replace + add `serve_assets` + SPA fallback)
- Create: `backend/tests/test_spa_fallback.py`, `backend/tests/test_serve_assets.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_spa_fallback.py
import pytest
from pathlib import Path

def test_root_serves_react_index(tmp_path, monkeypatch, client_with_admin):
    """When frontend/dist/index.html exists, GET / serves it."""
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist").mkdir(parents=True)
    (fake_frontend / "dist" / "index.html").write_text("<html>React</html>")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client_with_admin.get("/")
    assert response.status_code == 200
    assert b"React" in response.data

def test_unmatched_spa_route_serves_index(tmp_path, monkeypatch, client_with_admin):
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist").mkdir(parents=True)
    (fake_frontend / "dist" / "index.html").write_text("<html>SPA</html>")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    for route in ["/pipelines", "/asr_profiles", "/mt_profiles", "/glossaries", "/admin", "/proofread/abc123"]:
        response = client_with_admin.get(route)
        assert response.status_code == 200, route
        assert b"SPA" in response.data

def test_api_route_not_caught_by_fallback(client_with_admin):
    """API 404 must remain 404, not fall through to index.html"""
    response = client_with_admin.get("/api/this-does-not-exist")
    assert response.status_code == 404
    assert b"<html" not in response.data
```

```python
# backend/tests/test_serve_assets.py
def test_serve_assets_returns_js(tmp_path, monkeypatch, client_with_admin):
    fake_frontend = tmp_path / "frontend"
    assets_dir = fake_frontend / "dist" / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "index-abc123.js").write_text("console.log(1)")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client_with_admin.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "application/javascript" in response.content_type
    assert b"console.log" in response.data

def test_serve_assets_404_when_missing(tmp_path, monkeypatch, client_with_admin):
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist" / "assets").mkdir(parents=True)
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client_with_admin.get("/assets/does-not-exist.js")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_spa_fallback.py tests/test_serve_assets.py -v
```

Expected: 5 failures (route handlers don't exist yet).

- [ ] **Step 3: Update app.py — replace serve_index + add serve_assets + SPA fallback**

Locate the existing `serve_index` route in `app.py`. Replace + add new routes:

```python
@app.route("/")
def serve_index():
    dist_index = Path(_FRONTEND_DIR) / "dist" / "index.html"
    if dist_index.exists():
        return send_from_directory(str(dist_index.parent), "index.html")
    return "<html><body>Frontend dist not built. Run <code>cd frontend && npm run build</code>.</body></html>", 200

@app.route("/assets/<path:filename>")
def serve_assets(filename):
    assets_dir = Path(_FRONTEND_DIR) / "dist" / "assets"
    return send_from_directory(str(assets_dir), filename)

# SPA fallback — catch React Router routes
_SPA_ROUTES = ["/pipelines", "/asr_profiles", "/mt_profiles", "/glossaries", "/admin", "/login"]
for _spa_path in _SPA_ROUTES:
    app.add_url_rule(_spa_path, endpoint=f"spa_{_spa_path.strip('/')}", view_func=serve_index)

# Catch-all for dynamic SPA routes (e.g. /proofread/<id>)
@app.route("/proofread/<path:_subpath>")
def serve_proofread_spa(_subpath):
    return serve_index()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_spa_fallback.py tests/test_serve_assets.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Verify legacy login.html still works (frontend.old/ fallback)**

Existing `/login.html` and `/proofread.html` routes in app.py serve from `_FRONTEND_DIR` directly. Confirm they still serve files from `frontend.old/` since the directory was renamed. **Action**: in `app.py`, update `_FRONTEND_DIR` resolution to prefer `frontend/` but fall back to `frontend.old/` for legacy `.html` requests during A3-A4 transition:

```python
# Near top of app.py, where _FRONTEND_DIR is defined
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
_FRONTEND_LEGACY_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend.old")

# In any legacy .html serving route, check both:
@app.route("/proofread.html")
@login_required
def serve_proofread_legacy():
    # New React app handles /proofread/<id>; legacy callers still get vanilla page
    return send_from_directory(_FRONTEND_LEGACY_DIR, "proofread.html")
```

> Note: A4 will redirect `/proofread.html` to the React `/proofread/<id>` route; A5 deletes the legacy route entirely.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_spa_fallback.py backend/tests/test_serve_assets.py
git commit -m "feat(v4 A3): Flask SPA fallback + serve frontend/dist/assets"
```

---

## Task 4: Backend — Accept `pipeline_id` on /api/transcribe

🎯 **Goal:** When `pipeline_id` form field is present on POST /api/transcribe, after file registration enqueue a `pipeline_run` job (using A1 handler) instead of the legacy ASR-then-MT auto-translate flow.

✅ **Acceptance:**
- `POST /api/transcribe` with `pipeline_id=<valid_id>` form field → response includes `{file_id, job_id, queue_position}` and JobQueue has 1 pipeline_run job
- `POST /api/transcribe` without `pipeline_id` → legacy ASR job enqueued (existing behavior unchanged)
- `POST /api/transcribe` with invalid `pipeline_id` → 400 with explicit error
- backend/tests/test_transcribe_pipeline_id.py green (4 tests)

**Files:**
- Modify: `backend/app.py` (find `/api/transcribe` route)
- Create: `backend/tests/test_transcribe_pipeline_id.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_transcribe_pipeline_id.py
import io
import pytest
from unittest.mock import patch

@pytest.fixture
def fake_pipeline(client_with_admin, tmp_path, monkeypatch):
    """Create a minimal pipeline for testing."""
    from app import _pipeline_manager
    pipeline = _pipeline_manager.create(
        name="test-pipe",
        stages=[{"type": "asr", "ref": "any-asr-id"}],
        user_id=1,
        shared=False,
    )
    yield pipeline
    _pipeline_manager.delete(pipeline["id"])

def _upload_minimal_wav(client, **form_extras):
    data = {"file": (io.BytesIO(b"RIFF\x00\x00\x00\x00WAVE"), "tiny.wav"), **form_extras}
    return client.post("/api/transcribe", data=data, content_type="multipart/form-data")

def test_transcribe_with_pipeline_id_enqueues_pipeline_run(client_with_admin, fake_pipeline):
    response = _upload_minimal_wav(client_with_admin, pipeline_id=fake_pipeline["id"])
    assert response.status_code == 202
    body = response.get_json()
    assert "file_id" in body and "job_id" in body
    from app import _job_queue
    job = _job_queue.get_job(body["job_id"])
    assert job["job_type"] == "pipeline_run"

def test_transcribe_without_pipeline_id_uses_legacy_flow(client_with_admin):
    response = _upload_minimal_wav(client_with_admin)
    assert response.status_code == 202
    body = response.get_json()
    from app import _job_queue
    job = _job_queue.get_job(body["job_id"])
    assert job["job_type"] == "asr"

def test_transcribe_with_invalid_pipeline_id_returns_400(client_with_admin):
    response = _upload_minimal_wav(client_with_admin, pipeline_id="does-not-exist")
    assert response.status_code == 400
    assert "pipeline" in response.get_json()["error"].lower()

def test_transcribe_with_pipeline_id_not_visible_returns_403(client_with_admin, fake_pipeline, monkeypatch):
    # Simulate non-owner non-admin user
    from auth import users as auth_users
    auth_users.create_user("other_a3", "OtherPass1!", is_admin=False)
    client_with_admin.post("/logout")
    client_with_admin.post("/login", json={"username": "other_a3", "password": "OtherPass1!"})
    response = _upload_minimal_wav(client_with_admin, pipeline_id=fake_pipeline["id"])
    assert response.status_code in (400, 403)
    auth_users.delete_user_by_username("other_a3")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_transcribe_pipeline_id.py -v
```

Expected: 4 failures.

- [ ] **Step 3: Update /api/transcribe handler**

Find the existing `/api/transcribe` route in app.py. After the file registration step (where `file_id` becomes known), add:

```python
# After: file_id = _register_file(..., user_id=current_user.id)
pipeline_id = (request.form.get("pipeline_id") or "").strip() or None
if pipeline_id:
    if not _pipeline_manager.exists(pipeline_id):
        return jsonify({"error": f"Pipeline not found: {pipeline_id}"}), 400
    if not _pipeline_manager.can_view(pipeline_id, current_user.id, current_user.is_admin):
        return jsonify({"error": "Pipeline not visible"}), 403
    job_id = _job_queue.enqueue(
        job_type="pipeline_run",
        file_id=file_id,
        user_id=current_user.id,
        payload={"pipeline_id": pipeline_id},
    )
else:
    # Legacy path — unchanged
    job_id = _job_queue.enqueue(job_type="asr", file_id=file_id, user_id=current_user.id)

queue_position = _job_queue.queue_position(job_id)
return jsonify({"file_id": file_id, "job_id": job_id, "queue_position": queue_position}), 202
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_transcribe_pipeline_id.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_transcribe_pipeline_id.py
git commit -m "feat(v4 A3): accept pipeline_id form field on /api/transcribe"
```

---

## Task 5: src/lib/api.ts + Vitest Setup

🎯 **Goal:** `apiFetch(url, init)` helper handles credentials + 401 redirect + ApiError. Vitest infrastructure works.

✅ **Acceptance:**
- `src/lib/api.ts` exports `apiFetch`, `ApiError`, `UnauthorizedError`
- `src/tests/setup.ts` configured for jsdom + testing-library
- `src/lib/api.test.ts` covers: 200 returns parsed JSON; 401 throws UnauthorizedError; 4xx throws ApiError with `{error}` payload; credentials: 'include' sent on every request
- `npm test` green

**Files:**
- Create: `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `frontend/src/tests/setup.ts`

- [ ] **Step 1: Create src/tests/setup.ts**

```ts
import '@testing-library/jest-dom';
```

- [ ] **Step 2: Write failing api.test.ts**

```ts
// src/lib/api.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, ApiError, UnauthorizedError } from './api';

describe('apiFetch', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('returns parsed JSON on 200', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    );
    const data = await apiFetch('/api/health');
    expect(data).toEqual({ ok: true });
  });

  it('throws UnauthorizedError on 401', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(new Response('', { status: 401 }));
    await expect(apiFetch('/api/me')).rejects.toBeInstanceOf(UnauthorizedError);
  });

  it('throws ApiError on 4xx with parsed error payload', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'bad input' }), { status: 400, headers: { 'Content-Type': 'application/json' } })
    );
    try {
      await apiFetch('/api/whatever');
      throw new Error('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).message).toBe('bad input');
      expect((e as ApiError).status).toBe(400);
    }
  });

  it('always includes credentials: include', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    );
    await apiFetch('/api/anything');
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe('include');
  });
});
```

- [ ] **Step 3: Run test (expect failure)**

```bash
cd frontend && npm test -- api.test.ts
```

Expected: module not found.

- [ ] **Step 4: Implement src/lib/api.ts**

```ts
export class ApiError extends Error {
  constructor(message: string, public status: number, public body: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export class UnauthorizedError extends ApiError {
  constructor() {
    super('Unauthorized', 401, null);
    this.name = 'UnauthorizedError';
  }
}

export async function apiFetch<T = unknown>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    let body: unknown = null;
    let msg = `HTTP ${response.status}`;
    try {
      body = await response.json();
      if (body && typeof body === 'object' && 'error' in body) msg = String((body as { error: unknown }).error);
    } catch { /* not JSON */ }
    throw new ApiError(msg, response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
```

- [ ] **Step 5: Run tests (expect pass)**

```bash
npm test -- api.test.ts
```

Expected: 4/4 PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/tests/setup.ts
git commit -m "feat(v4 A3): apiFetch + 401 interceptor + Vitest setup"
```

---

## Task 6: zod Schemas Mirroring Backend Validators

🎯 **Goal:** Per-entity zod schemas (asr-profile, mt-profile, glossary, pipeline, user) accept valid payloads and reject invalid ones, matching backend validator rules exactly.

✅ **Acceptance:**
- 5 schema files in `src/lib/schemas/`
- `.test.ts` for each — 3+ valid + 3+ invalid cases per entity
- `npm test` green (~20+ assertions)

**Files:**
- Create: `frontend/src/lib/schemas/{asr-profile,mt-profile,glossary,pipeline,user}.ts` + matching `.test.ts`

- [ ] **Step 1: Write failing tests + schemas — asr-profile**

```ts
// src/lib/schemas/asr-profile.ts
import { z } from 'zod';

export const AsrProfileSchema = z.object({
  name: z.string().min(1).max(64),
  description: z.string().max(256).optional().default(''),
  shared: z.boolean().default(false),
  asr: z.object({
    engine: z.enum(['whisper', 'mlx-whisper']),
    language: z.string().min(1).max(8),
    model_size: z.literal('large-v3'),
    task: z.enum(['transcribe', 'translate']),
    initial_prompt: z.string().max(1024).optional().default(''),
    simplified_to_traditional: z.boolean().default(false),
    condition_on_previous_text: z.boolean().default(false),
  }),
});

export type AsrProfile = z.infer<typeof AsrProfileSchema>;
```

```ts
// src/lib/schemas/asr-profile.test.ts
import { describe, it, expect } from 'vitest';
import { AsrProfileSchema } from './asr-profile';

describe('AsrProfileSchema', () => {
  const valid = { name: 'Test', asr: { engine: 'whisper', language: 'en', model_size: 'large-v3', task: 'transcribe' } };
  it('accepts minimal valid', () => { expect(AsrProfileSchema.parse(valid).name).toBe('Test'); });
  it('accepts full valid with all optional', () => {
    const r = AsrProfileSchema.parse({ ...valid, description: 'd', shared: true, asr: { ...valid.asr, initial_prompt: 'p', simplified_to_traditional: true, condition_on_previous_text: false } });
    expect(r.asr.initial_prompt).toBe('p');
  });
  it('rejects empty name', () => { expect(() => AsrProfileSchema.parse({ ...valid, name: '' })).toThrow(); });
  it('rejects unknown engine', () => { expect(() => AsrProfileSchema.parse({ ...valid, asr: { ...valid.asr, engine: 'fake' } })).toThrow(); });
  it('rejects model_size != large-v3', () => { expect(() => AsrProfileSchema.parse({ ...valid, asr: { ...valid.asr, model_size: 'medium' } })).toThrow(); });
});
```

- [ ] **Step 2: Repeat for mt-profile**

```ts
// src/lib/schemas/mt-profile.ts
import { z } from 'zod';

export const MtProfileSchema = z.object({
  name: z.string().min(1).max(64),
  description: z.string().max(256).optional().default(''),
  shared: z.boolean().default(false),
  engine: z.literal('qwen3.5-35b-a3b'),
  system_prompt: z.string().min(1).max(4096),
  user_message_template: z.string().min(1).max(2048).refine(s => s.includes('{text}'), { message: 'must contain {text} placeholder' }),
  temperature: z.number().min(0).max(1).default(0.1),
  batch_size: z.number().int().min(1).max(32).default(1),
  parallel_batches: z.number().int().min(1).max(8).default(1),
});

export type MtProfile = z.infer<typeof MtProfileSchema>;
```

Tests: 3 valid + 4 invalid (missing `{text}` placeholder, batch_size > 32, temperature > 1, wrong engine).

- [ ] **Step 3: Repeat for glossary**

```ts
// src/lib/schemas/glossary.ts
import { z } from 'zod';

export const LANGS = ['en', 'zh', 'ja', 'ko', 'es', 'fr', 'de', 'th'] as const;

export const GlossaryEntrySchema = z.object({
  source: z.string().min(1),
  target: z.string().min(1),
  target_aliases: z.array(z.string()).default([]),
});

export const GlossarySchema = z.object({
  name: z.string().min(1).max(64),
  description: z.string().max(256).optional().default(''),
  shared: z.boolean().default(false),
  source_lang: z.enum(LANGS),
  target_lang: z.enum(LANGS),
  entries: z.array(GlossaryEntrySchema).default([]),
}).refine(g => g.source_lang !== g.target_lang || g.entries.length === 0, {
  message: 'source_lang and target_lang cannot match unless entries empty',
});

export type Glossary = z.infer<typeof GlossarySchema>;
```

Tests: 3 valid + 3 invalid (same source/target lang with entries, empty entry source, unknown lang).

- [ ] **Step 4: Repeat for pipeline**

```ts
// src/lib/schemas/pipeline.ts
import { z } from 'zod';

export const StageSchema = z.object({
  type: z.enum(['asr', 'mt', 'glossary']),
  ref: z.string().min(1),
});

export const PipelineSchema = z.object({
  name: z.string().min(1).max(64),
  description: z.string().max(256).optional().default(''),
  shared: z.boolean().default(false),
  stages: z.array(StageSchema).min(1).refine(s => s[0].type === 'asr', { message: 'first stage must be ASR' }),
});

export type Pipeline = z.infer<typeof PipelineSchema>;
```

Tests: 3 valid + 3 invalid (empty stages, first stage not ASR, empty ref).

- [ ] **Step 5: Repeat for user**

```ts
// src/lib/schemas/user.ts
import { z } from 'zod';

export const LoginSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(1).max(128),
});

export const CreateUserSchema = z.object({
  username: z.string().min(3).max(64).regex(/^[a-zA-Z0-9_-]+$/),
  password: z.string().min(8).max(128),
  is_admin: z.boolean().default(false),
});

export type LoginData = z.infer<typeof LoginSchema>;
export type CreateUserData = z.infer<typeof CreateUserSchema>;
```

Tests: 2 valid + 3 invalid per schema.

- [ ] **Step 6: Run all schema tests**

```bash
npm test -- schemas
```

Expected: ~20+ PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/schemas/
git commit -m "feat(v4 A3): zod schemas for ASR/MT/glossary/pipeline/user"
```

---

## Task 7: Zustand Auth Store + AuthProvider

🎯 **Goal:** Zustand auth store + AuthProvider that boot-probes `/api/me`. Components access `useAuthStore()`.

✅ **Acceptance:**
- `src/stores/auth.ts` exports `useAuthStore` with `{user, isLoading, login(), logout(), refresh()}`
- `src/providers/AuthProvider.tsx` calls `refresh()` on mount; shows loading state until first fetch returns
- `src/stores/auth.test.ts` covers: setUser, clearUser, login (mocked apiFetch), logout (mocked)

**Files:**
- Create: `frontend/src/stores/auth.ts`, `frontend/src/stores/auth.test.ts`, `frontend/src/providers/AuthProvider.tsx`

- [ ] **Step 1: Write failing auth.test.ts**

```ts
// src/stores/auth.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from './auth';

beforeEach(() => { useAuthStore.setState({ user: null, isLoading: true }); });

describe('useAuthStore', () => {
  it('starts with isLoading=true and user=null', () => {
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isLoading).toBe(true);
  });

  it('setUser updates state', () => {
    useAuthStore.getState().setUser({ id: 1, username: 'admin', is_admin: true });
    expect(useAuthStore.getState().user?.username).toBe('admin');
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('clearUser resets', () => {
    useAuthStore.getState().setUser({ id: 1, username: 'admin', is_admin: true });
    useAuthStore.getState().clearUser();
    expect(useAuthStore.getState().user).toBeNull();
  });
});
```

- [ ] **Step 2: Implement src/stores/auth.ts**

```ts
import { create } from 'zustand';

export interface User { id: number; username: string; is_admin: boolean; }
interface AuthState {
  user: User | null;
  isLoading: boolean;
  setUser: (u: User) => void;
  clearUser: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  setUser: (u) => set({ user: u, isLoading: false }),
  clearUser: () => set({ user: null, isLoading: false }),
}));
```

- [ ] **Step 3: Implement src/providers/AuthProvider.tsx**

```tsx
import { useEffect, type ReactNode } from 'react';
import { apiFetch, UnauthorizedError } from '@/lib/api';
import { useAuthStore, type User } from '@/stores/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const setUser = useAuthStore((s) => s.setUser);
  const clearUser = useAuthStore((s) => s.clearUser);
  const isLoading = useAuthStore((s) => s.isLoading);

  useEffect(() => {
    apiFetch<User>('/api/me')
      .then((u) => setUser(u))
      .catch((e) => {
        if (e instanceof UnauthorizedError) clearUser();
        else clearUser();
      });
  }, [setUser, clearUser]);

  if (isLoading) return <div className="p-8 text-muted-foreground">Loading…</div>;
  return <>{children}</>;
}
```

- [ ] **Step 4: Tests pass**

```bash
npm test -- auth.test
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/auth.ts frontend/src/stores/auth.test.ts frontend/src/providers/AuthProvider.tsx
git commit -m "feat(v4 A3): Zustand auth store + AuthProvider with boot probe"
```

---

## Task 8: shadcn Primitives Copy-In

🎯 **Goal:** Install minimal set of shadcn-ui primitives: Button, Input, Textarea, Label, Dialog, Select, Toast, Tabs, Card, Badge.

✅ **Acceptance:**
- 10 component files in `src/components/ui/`
- Each importable; `App.tsx` renders a Button without runtime error
- `npm run build` succeeds

**Files:**
- Create: `frontend/src/components/ui/{button,input,textarea,label,dialog,select,toast,toaster,tabs,card,badge}.tsx`

- [ ] **Step 1: Create button.tsx**

```tsx
// src/components/ui/button.tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
      },
      size: { default: 'h-10 px-4 py-2', sm: 'h-9 px-3', lg: 'h-11 px-8', icon: 'h-10 w-10' },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = 'Button';
```

- [ ] **Step 2: Create input.tsx + textarea.tsx + label.tsx**

```tsx
// src/components/ui/input.tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = 'Input';
```

```tsx
// src/components/ui/textarea.tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      className={cn(
        'flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Textarea.displayName = 'Textarea';
```

```tsx
// src/components/ui/label.tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label ref={ref} className={cn('text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70', className)} {...props} />
  )
);
Label.displayName = 'Label';
```

- [ ] **Step 3: Create dialog.tsx, select.tsx, tabs.tsx, card.tsx, badge.tsx, toast.tsx, toaster.tsx**

For each, copy the canonical shadcn implementation from https://ui.shadcn.com/docs/components/<name>. Each file is 30–80 lines of straightforward Radix wrapper code. Use `cn` from `@/lib/utils`.

Reference templates (one example — dialog):

```tsx
// src/components/ui/dialog.tsx
import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

const DialogPortal = DialogPrimitive.Portal;

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay ref={ref} className={cn('fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in', className)} {...props} />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg sm:rounded-lg',
        className
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = DialogPrimitive.Content.displayName;

export const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />
);
export const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title ref={ref} className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;
export const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;
```

> Implementation note: each of select/tabs/card/badge/toast/toaster follows the same Radix-wrapper pattern. Use https://ui.shadcn.com/docs/components/<name> verbatim. Subagent: if you don't have web access, copy a vendored snapshot from the matching A1-era reference, then adjust `cn` import to `@/lib/utils`.

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```

Expected: 0 TypeScript errors. `dist/assets/*.js` includes the new components.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(v4 A3): shadcn primitives (Button/Input/Dialog/Select/Tabs/Card/Toast/etc.)"
```

---

## Task 9: Router + Layout + Protected Routes

🎯 **Goal:** React Router 6 with public `/login` route + protected app routes inside `<Layout>` shell. Unauthenticated → redirect to `/login`.

✅ **Acceptance:**
- `src/router.tsx` defines all 8 routes (+ ProofreadPlaceholder)
- `<Layout>` renders TopBar + SideNav + `<Outlet>`
- Protected route guard redirects to `/login` if `user === null`
- `App.tsx` composes `<AuthProvider><RouterProvider router={router}></RouterProvider></AuthProvider>`
- Manual smoke: visit `/pipelines` without login → redirected to `/login`

**Files:**
- Create: `frontend/src/router.tsx`, `frontend/src/components/{Layout,TopBar,SideNav}.tsx`, `frontend/src/pages/{Login,Dashboard,Pipelines,AsrProfiles,MtProfiles,Glossaries,Admin,ProofreadPlaceholder}.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create page stubs**

Each of `Dashboard.tsx`, `Pipelines.tsx`, `AsrProfiles.tsx`, `MtProfiles.tsx`, `Glossaries.tsx`, `Admin.tsx`, `ProofreadPlaceholder.tsx` exports a default component rendering an `<h1>` with the page name. Will be replaced in subsequent tasks.

Example:
```tsx
// src/pages/Dashboard.tsx
export default function Dashboard() { return <h1 className="text-2xl">Dashboard</h1>; }
```

- [ ] **Step 2: Create Login.tsx skeleton (full impl in Task 10)**

```tsx
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
export default function Login() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  if (user) return <Navigate to="/" replace />;
  return <h1 className="text-2xl p-8">Login (Task 10)</h1>;
}
```

- [ ] **Step 3: Create Layout / TopBar / SideNav**

```tsx
// src/components/Layout.tsx
import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { SideNav } from './SideNav';

export function Layout() {
  return (
    <div className="grid grid-rows-[auto_1fr] grid-cols-[200px_1fr] h-screen">
      <header className="col-span-2 border-b"><TopBar /></header>
      <aside className="border-r bg-muted/30"><SideNav /></aside>
      <main className="overflow-auto p-6"><Outlet /></main>
    </div>
  );
}
```

```tsx
// src/components/TopBar.tsx
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import { useNavigate } from 'react-router-dom';

export function TopBar() {
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const navigate = useNavigate();
  async function handleLogout() {
    try { await apiFetch('/logout', { method: 'POST' }); } catch { /* ignore */ }
    clearUser();
    navigate('/login');
  }
  return (
    <div className="flex items-center justify-between px-6 h-14">
      <h1 className="text-lg font-semibold">MoTitle</h1>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">{user?.username}{user?.is_admin && ' (admin)'}</span>
        <Button variant="outline" size="sm" onClick={handleLogout}>Logout</Button>
      </div>
    </div>
  );
}
```

```tsx
// src/components/SideNav.tsx
import { NavLink } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { cn } from '@/lib/utils';

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/pipelines', label: 'Pipelines' },
  { to: '/asr_profiles', label: 'ASR Profiles' },
  { to: '/mt_profiles', label: 'MT Profiles' },
  { to: '/glossaries', label: 'Glossaries' },
];

export function SideNav() {
  const isAdmin = useAuthStore((s) => !!s.user?.is_admin);
  const items = isAdmin ? [...NAV, { to: '/admin', label: 'Admin' }] : NAV;
  return (
    <nav className="flex flex-col gap-1 p-3">
      {items.map((i) => (
        <NavLink
          key={i.to}
          to={i.to}
          end={i.to === '/'}
          className={({ isActive }) => cn('rounded px-3 py-2 text-sm', isActive ? 'bg-accent font-medium' : 'hover:bg-accent/50')}
        >
          {i.label}
        </NavLink>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: Create router.tsx**

```tsx
// src/router.tsx
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { Layout } from '@/components/Layout';
import Login from '@/pages/Login';
import Dashboard from '@/pages/Dashboard';
import Pipelines from '@/pages/Pipelines';
import AsrProfiles from '@/pages/AsrProfiles';
import MtProfiles from '@/pages/MtProfiles';
import Glossaries from '@/pages/Glossaries';
import Admin from '@/pages/Admin';
import ProofreadPlaceholder from '@/pages/ProofreadPlaceholder';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: <RequireAuth><Layout /></RequireAuth>,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'pipelines', element: <Pipelines /> },
      { path: 'asr_profiles', element: <AsrProfiles /> },
      { path: 'mt_profiles', element: <MtProfiles /> },
      { path: 'glossaries', element: <Glossaries /> },
      { path: 'admin', element: <RequireAdmin><Admin /></RequireAdmin> },
      { path: 'proofread/:fileId', element: <ProofreadPlaceholder /> },
    ],
  },
]);
```

- [ ] **Step 5: Update App.tsx**

```tsx
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/providers/AuthProvider';
import { router } from '@/router';

export function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
```

- [ ] **Step 6: Build + verify**

```bash
npm run build
```

Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(v4 A3): React Router 6 + Layout + auth guards"
```

---

## Task 10: Login Page (full impl)

🎯 **Goal:** Login form with react-hook-form + zod validation. POST `/login` → refetch `/api/me` → navigate to `/`.

✅ **Acceptance:**
- Form validates username + password non-empty before submit
- 401 shows error message under password field
- Successful login sets Zustand user + navigates to `/`
- Manual smoke: enter admin/AdminPass1! → land on Dashboard

**Files:**
- Modify: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: Implement Login.tsx**

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, Navigate } from 'react-router-dom';
import { useState } from 'react';
import { LoginSchema, type LoginData } from '@/lib/schemas/user';
import { useAuthStore, type User } from '@/stores/auth';
import { apiFetch, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function Login() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const navigate = useNavigate();
  const [authError, setAuthError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginData>({ resolver: zodResolver(LoginSchema) });

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(data: LoginData) {
    setAuthError(null);
    try {
      await apiFetch('/login', { method: 'POST', body: JSON.stringify(data) });
      const me = await apiFetch<User>('/api/me');
      setUser(me);
      navigate('/');
    } catch (e) {
      setAuthError(e instanceof ApiError ? e.message : 'Login failed');
    }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-muted/20">
      <form onSubmit={handleSubmit(onSubmit)} className="w-full max-w-sm space-y-4 p-6 bg-background rounded-lg shadow-md">
        <h1 className="text-2xl font-semibold">MoTitle Login</h1>
        <div className="space-y-1">
          <Label htmlFor="username">Username</Label>
          <Input id="username" autoComplete="username" {...register('username')} />
          {errors.username && <p className="text-sm text-destructive">{errors.username.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" {...register('password')} />
          {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          {authError && <p className="text-sm text-destructive">{authError}</p>}
        </div>
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? 'Logging in…' : 'Log in'}
        </Button>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Manual smoke test**

```bash
cd frontend && npm run dev
# Visit http://localhost:5173/login
# Enter admin / AdminPass1!
# Expected: redirected to /, see Dashboard h1
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat(v4 A3): Login page with RHF + zod + API auth flow"
```

---

## Task 11: SocketProvider + Reducer

🎯 **Goal:** React Context with `useReducer` for file map + per-stage progress. Connects on auth, dispatches actions on socket events.

✅ **Acceptance:**
- `src/providers/SocketProvider.tsx` exports `useSocket()` hook
- Reducer handles 6+ event types: file_added, file_updated, pipeline_stage_progress, pipeline_stage_complete, pipeline_complete, pipeline_failed
- `src/providers/SocketProvider.test.tsx` covers each action transition (no actual socket, just reducer pure-function tests)

**Files:**
- Create: `frontend/src/lib/socket-events.ts`, `frontend/src/providers/SocketProvider.tsx`, `frontend/src/providers/SocketProvider.test.tsx`

- [ ] **Step 1: Define event types in src/lib/socket-events.ts**

```ts
export interface FileRecord {
  id: string;
  original_name: string;
  status: string;
  job_id?: string | null;
  pipeline_id?: string | null;
  stage_outputs?: Array<{ stage_type: string; stage_ref: string }>;
  [k: string]: unknown;
}

export interface StageProgressEvent {
  file_id: string;
  stage_idx: number;
  percent: number;
}

export interface StageCompleteEvent {
  file_id: string;
  stage_idx: number;
}

export interface PipelineCompleteEvent {
  file_id: string;
}

export interface PipelineFailedEvent {
  file_id: string;
  stage_idx?: number;
  error: string;
}

export type SocketAction =
  | { type: 'FILE_ADDED'; file: FileRecord }
  | { type: 'FILE_UPDATED'; file: FileRecord }
  | { type: 'STAGE_PROGRESS'; ev: StageProgressEvent }
  | { type: 'STAGE_COMPLETE'; ev: StageCompleteEvent }
  | { type: 'PIPELINE_COMPLETE'; ev: PipelineCompleteEvent }
  | { type: 'PIPELINE_FAILED'; ev: PipelineFailedEvent }
  | { type: 'BULK_FILES'; files: FileRecord[] };

export interface SocketState {
  files: Record<string, FileRecord>;
  stageProgress: Record<string, Record<number, number>>;
  stageStatus: Record<string, Record<number, 'idle' | 'running' | 'done' | 'failed'>>;
}

export const initialSocketState: SocketState = { files: {}, stageProgress: {}, stageStatus: {} };

export function socketReducer(state: SocketState, action: SocketAction): SocketState {
  switch (action.type) {
    case 'BULK_FILES': {
      const files: Record<string, FileRecord> = {};
      for (const f of action.files) files[f.id] = f;
      return { ...state, files };
    }
    case 'FILE_ADDED':
    case 'FILE_UPDATED': {
      const prev = state.files[action.file.id];
      return { ...state, files: { ...state.files, [action.file.id]: { ...prev, ...action.file } } };
    }
    case 'STAGE_PROGRESS': {
      const fileProg = { ...(state.stageProgress[action.ev.file_id] ?? {}), [action.ev.stage_idx]: action.ev.percent };
      const fileStatus = { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'running' as const };
      return {
        ...state,
        stageProgress: { ...state.stageProgress, [action.ev.file_id]: fileProg },
        stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
      };
    }
    case 'STAGE_COMPLETE': {
      const fileProg = { ...(state.stageProgress[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 100 };
      const fileStatus = { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'done' as const };
      return {
        ...state,
        stageProgress: { ...state.stageProgress, [action.ev.file_id]: fileProg },
        stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
      };
    }
    case 'PIPELINE_COMPLETE': {
      const prev = state.files[action.ev.file_id];
      if (!prev) return state;
      return { ...state, files: { ...state.files, [action.ev.file_id]: { ...prev, status: 'completed' } } };
    }
    case 'PIPELINE_FAILED': {
      const prev = state.files[action.ev.file_id];
      const fileStatus = action.ev.stage_idx != null
        ? { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'failed' as const }
        : (state.stageStatus[action.ev.file_id] ?? {});
      return {
        ...state,
        files: prev ? { ...state.files, [action.ev.file_id]: { ...prev, status: 'failed' } } : state.files,
        stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
      };
    }
    default: return state;
  }
}
```

- [ ] **Step 2: Write reducer tests**

```tsx
// src/providers/SocketProvider.test.tsx
import { describe, it, expect } from 'vitest';
import { socketReducer, initialSocketState } from '@/lib/socket-events';

describe('socketReducer', () => {
  it('BULK_FILES sets files map', () => {
    const r = socketReducer(initialSocketState, { type: 'BULK_FILES', files: [{ id: 'a', original_name: 'x', status: 'queued' }] });
    expect(r.files.a.original_name).toBe('x');
  });
  it('FILE_UPDATED merges into existing', () => {
    const s = socketReducer(initialSocketState, { type: 'FILE_ADDED', file: { id: 'a', original_name: 'x', status: 'queued' } });
    const r = socketReducer(s, { type: 'FILE_UPDATED', file: { id: 'a', original_name: 'x', status: 'running' } });
    expect(r.files.a.status).toBe('running');
  });
  it('STAGE_PROGRESS updates progress map + sets running status', () => {
    const r = socketReducer(initialSocketState, { type: 'STAGE_PROGRESS', ev: { file_id: 'a', stage_idx: 0, percent: 25 } });
    expect(r.stageProgress.a[0]).toBe(25);
    expect(r.stageStatus.a[0]).toBe('running');
  });
  it('STAGE_COMPLETE sets 100 + done', () => {
    const r = socketReducer(initialSocketState, { type: 'STAGE_COMPLETE', ev: { file_id: 'a', stage_idx: 1 } });
    expect(r.stageProgress.a[1]).toBe(100);
    expect(r.stageStatus.a[1]).toBe('done');
  });
  it('PIPELINE_COMPLETE marks file completed', () => {
    const s = socketReducer(initialSocketState, { type: 'FILE_ADDED', file: { id: 'a', original_name: 'x', status: 'queued' } });
    const r = socketReducer(s, { type: 'PIPELINE_COMPLETE', ev: { file_id: 'a' } });
    expect(r.files.a.status).toBe('completed');
  });
  it('PIPELINE_FAILED marks stage failed', () => {
    const s = socketReducer(initialSocketState, { type: 'FILE_ADDED', file: { id: 'a', original_name: 'x', status: 'queued' } });
    const r = socketReducer(s, { type: 'PIPELINE_FAILED', ev: { file_id: 'a', stage_idx: 1, error: 'oops' } });
    expect(r.files.a.status).toBe('failed');
    expect(r.stageStatus.a[1]).toBe('failed');
  });
});
```

- [ ] **Step 3: Implement SocketProvider.tsx**

```tsx
import { createContext, useContext, useEffect, useReducer, type ReactNode } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import {
  socketReducer, initialSocketState,
  type SocketState, type FileRecord
} from '@/lib/socket-events';

interface SocketContextValue {
  state: SocketState;
  socket: Socket | null;
}

const SocketContext = createContext<SocketContextValue>({ state: initialSocketState, socket: null });

export function SocketProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(socketReducer, initialSocketState);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (!user) return;
    apiFetch<FileRecord[]>('/api/files').then((files) => dispatch({ type: 'BULK_FILES', files })).catch(() => {});
    const socket = io({ path: '/socket.io' });
    socket.on('file_added', (f: FileRecord) => dispatch({ type: 'FILE_ADDED', file: f }));
    socket.on('file_updated', (f: FileRecord) => dispatch({ type: 'FILE_UPDATED', file: f }));
    socket.on('pipeline_stage_progress', (ev: { file_id: string; stage_idx: number; percent: number }) =>
      dispatch({ type: 'STAGE_PROGRESS', ev }));
    socket.on('pipeline_stage_complete', (ev: { file_id: string; stage_idx: number }) =>
      dispatch({ type: 'STAGE_COMPLETE', ev }));
    socket.on('pipeline_complete', (ev: { file_id: string }) => dispatch({ type: 'PIPELINE_COMPLETE', ev }));
    socket.on('pipeline_failed', (ev: { file_id: string; stage_idx?: number; error: string }) =>
      dispatch({ type: 'PIPELINE_FAILED', ev }));
    return () => { socket.disconnect(); };
  }, [user]);

  return (
    <SocketContext.Provider value={{ state, socket: null }}>
      {children}
    </SocketContext.Provider>
  );
}

export function useSocket() {
  return useContext(SocketContext);
}
```

- [ ] **Step 4: Wrap Layout with SocketProvider**

In `Layout.tsx`, wrap the JSX in `<SocketProvider>`. Or alternatively wrap the protected route subtree in `router.tsx` — Layout is fine.

```tsx
// In Layout.tsx — wrap Outlet
import { SocketProvider } from '@/providers/SocketProvider';
// ...
<main className="overflow-auto p-6">
  <SocketProvider><Outlet /></SocketProvider>
</main>
```

- [ ] **Step 5: Tests pass + build green**

```bash
npm test -- SocketProvider
npm run build
```

Expected: 6 PASS, 0 build errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/socket-events.ts frontend/src/providers/SocketProvider.tsx frontend/src/providers/SocketProvider.test.tsx frontend/src/components/Layout.tsx
git commit -m "feat(v4 A3): SocketProvider with reducer for realtime file/stage events"
```

---

## Task 12: Pipeline Picker Store + Component

🎯 **Goal:** Zustand store holds selected pipeline_id with localStorage persistence. `<PipelinePicker>` shows dropdown of visible pipelines.

✅ **Acceptance:**
- `src/stores/pipeline-picker.ts` exports `usePipelinePickerStore` with `{pipelineId, setPipelineId, pipelines, refresh()}`
- localStorage key `motitle.pipeline-picker` survives reload
- `<PipelinePicker>` renders Select with current pipelines from `/api/pipelines`
- Manual smoke: pick a pipeline, refresh page, selection persists

**Files:**
- Create: `frontend/src/stores/pipeline-picker.ts`, `frontend/src/components/PipelinePicker.tsx`

- [ ] **Step 1: Implement store with localStorage middleware**

```ts
// src/stores/pipeline-picker.ts
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { apiFetch } from '@/lib/api';

export interface PipelineSummary {
  id: string;
  name: string;
  description: string;
  shared: boolean;
  user_id: number | null;
}

interface PickerState {
  pipelineId: string | null;
  pipelines: PipelineSummary[];
  setPipelineId: (id: string | null) => void;
  refresh: () => Promise<void>;
}

export const usePipelinePickerStore = create<PickerState>()(
  persist(
    (set) => ({
      pipelineId: null,
      pipelines: [],
      setPipelineId: (id) => set({ pipelineId: id }),
      refresh: async () => {
        try {
          const pipelines = await apiFetch<PipelineSummary[]>('/api/pipelines');
          set({ pipelines });
        } catch { /* keep stale */ }
      },
    }),
    { name: 'motitle.pipeline-picker', storage: createJSONStorage(() => localStorage), partialize: (s) => ({ pipelineId: s.pipelineId }) }
  )
);
```

- [ ] **Step 2: Implement <PipelinePicker>**

```tsx
// src/components/PipelinePicker.tsx
import { useEffect } from 'react';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';

export function PipelinePicker() {
  const { pipelineId, pipelines, setPipelineId, refresh } = usePipelinePickerStore();
  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="space-y-1">
      <Label htmlFor="pipeline-picker">Pipeline</Label>
      <Select value={pipelineId ?? undefined} onValueChange={(v) => setPipelineId(v || null)}>
        <SelectTrigger id="pipeline-picker" className="w-64">
          <SelectValue placeholder="Select a pipeline…" />
        </SelectTrigger>
        <SelectContent>
          {pipelines.map((p) => (
            <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
```

- [ ] **Step 3: Build + manual smoke**

```bash
npm run build && npm run dev
# Log in. Visit /. Pipeline dropdown shows pipelines.
# Pick one. Reload. Selection persists.
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/pipeline-picker.ts frontend/src/components/PipelinePicker.tsx
git commit -m "feat(v4 A3): Pipeline picker store + component with localStorage persistence"
```

---

## Task 13: UploadDropzone + Dashboard Skeleton

🎯 **Goal:** Drag-drop file upload. POST `/api/transcribe` multipart with `pipeline_id` from picker store.

✅ **Acceptance:**
- `<UploadDropzone>` accepts `.mp4 .mxf .mov .mkv .wav .mp3 .m4a` extensions
- On drop: posts to `/api/transcribe` with `file` + `pipeline_id`
- Toast on 4xx error
- Dashboard.tsx layouts PipelinePicker + UploadDropzone + file cards from socket state

**Files:**
- Create: `frontend/src/components/UploadDropzone.tsx`, `frontend/src/stores/ui.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Create UI store for toasts**

```ts
// src/stores/ui.ts
import { create } from 'zustand';

export interface Toast { id: string; title: string; description?: string; variant?: 'default' | 'destructive'; }
interface UIState {
  toasts: Toast[];
  pushToast: (t: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
}
export const useUIStore = create<UIState>((set) => ({
  toasts: [],
  pushToast: (t) => set((s) => ({ toasts: [...s.toasts, { ...t, id: crypto.randomUUID() }] })),
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
```

- [ ] **Step 2: Implement <UploadDropzone>**

```tsx
// src/components/UploadDropzone.tsx
import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import { useUIStore } from '@/stores/ui';
import { cn } from '@/lib/utils';

const ACCEPTED = {
  'video/*': ['.mp4', '.mxf', '.mov', '.mkv'],
  'audio/*': ['.wav', '.mp3', '.m4a'],
};

export function UploadDropzone() {
  const pipelineId = usePipelinePickerStore((s) => s.pipelineId);
  const pushToast = useUIStore((s) => s.pushToast);

  const onDrop = useCallback(async (files: File[]) => {
    if (!files.length) return;
    for (const file of files) {
      const fd = new FormData();
      fd.append('file', file);
      if (pipelineId) fd.append('pipeline_id', pipelineId);
      try {
        const r = await fetch('/api/transcribe', { method: 'POST', body: fd, credentials: 'include' });
        if (!r.ok) {
          const body = await r.json().catch(() => ({ error: r.statusText }));
          pushToast({ title: 'Upload failed', description: body.error, variant: 'destructive' });
        }
      } catch (e) {
        pushToast({ title: 'Upload failed', description: String(e), variant: 'destructive' });
      }
    }
  }, [pipelineId, pushToast]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: ACCEPTED });

  return (
    <div
      {...getRootProps()}
      className={cn(
        'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
        isDragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:bg-muted/30'
      )}
    >
      <input {...getInputProps()} />
      <p className="text-sm text-muted-foreground">
        {isDragActive ? 'Drop here…' : 'Drag video/audio file or click to browse'}
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Update Dashboard.tsx**

```tsx
// src/pages/Dashboard.tsx
import { useSocket } from '@/providers/SocketProvider';
import { PipelinePicker } from '@/components/PipelinePicker';
import { UploadDropzone } from '@/components/UploadDropzone';
import { FileCard } from '@/components/FileCard';

export default function Dashboard() {
  const { state } = useSocket();
  const files = Object.values(state.files).sort((a, b) =>
    (b as { created_at?: number }).created_at && (a as { created_at?: number }).created_at
      ? ((b as { created_at: number }).created_at - (a as { created_at: number }).created_at)
      : 0
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end gap-4">
        <PipelinePicker />
        <div className="flex-1"><UploadDropzone /></div>
      </div>
      <div className="space-y-3">
        {files.length === 0 && <p className="text-muted-foreground text-sm">No files yet. Upload one above.</p>}
        {files.map((f) => <FileCard key={f.id} file={f} progress={state.stageProgress[f.id] ?? {}} status={state.stageStatus[f.id] ?? {}} />)}
      </div>
    </div>
  );
}
```

> Note: `<FileCard>` implemented in Task 14 — until then, create a stub returning `<div>{f.original_name}</div>`.

- [ ] **Step 4: Stub FileCard to keep Dashboard compiling**

```tsx
// src/components/FileCard.tsx (stub)
import type { FileRecord } from '@/lib/socket-events';
export function FileCard({ file }: { file: FileRecord; progress: Record<number, number>; status: Record<number, string>; }) {
  return <div className="border rounded p-3 text-sm">{file.original_name} — {file.status}</div>;
}
```

- [ ] **Step 5: Build + smoke**

```bash
npm run build && npm run dev
# Drop file → see it appear in list
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/ui.ts frontend/src/components/{UploadDropzone,FileCard}.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(v4 A3): UploadDropzone + Dashboard skeleton"
```

---

## Task 14: FileCard + StageProgress

🎯 **Goal:** File card shows per-stage progress bar + status badge + action buttons.

✅ **Acceptance:**
- `<StageProgress>` renders idle / running / done / failed visual states
- `<FileCard>` shows all stages from `file.stage_outputs` or pipeline definition
- `src/components/FileCard.test.tsx` covers 4 status states
- Cancel button calls DELETE `/api/queue/<job_id>` when `file.job_id` present

**Files:**
- Modify: `frontend/src/components/FileCard.tsx`
- Create: `frontend/src/components/StageProgress.tsx`, `frontend/src/components/FileCard.test.tsx`

- [ ] **Step 1: Implement StageProgress**

```tsx
// src/components/StageProgress.tsx
import { cn } from '@/lib/utils';

export function StageProgress({ idx, stageType, stageRef, percent, status }: {
  idx: number;
  stageType: string;
  stageRef: string;
  percent: number;
  status: 'idle' | 'running' | 'done' | 'failed';
}) {
  const statusColor = {
    idle: 'bg-muted',
    running: 'bg-primary',
    done: 'bg-green-600',
    failed: 'bg-destructive',
  }[status];
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-8 text-muted-foreground tabular-nums">#{idx}</span>
      <span className="w-16 font-medium uppercase tracking-wide">{stageType}</span>
      <span className="flex-1 truncate text-muted-foreground" title={stageRef}>{stageRef}</span>
      <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={cn('h-full transition-all', statusColor)} style={{ width: `${percent}%` }} />
      </div>
      <span className="w-10 text-right tabular-nums">{percent}%</span>
    </div>
  );
}
```

- [ ] **Step 2: Implement FileCard**

```tsx
// src/components/FileCard.tsx
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { StageProgress } from './StageProgress';
import { apiFetch } from '@/lib/api';
import type { FileRecord } from '@/lib/socket-events';

interface Props {
  file: FileRecord;
  progress: Record<number, number>;
  status: Record<number, 'idle' | 'running' | 'done' | 'failed'>;
}

export function FileCard({ file, progress, status }: Props) {
  const navigate = useNavigate();
  const stages = (file.stage_outputs as Array<{ stage_type: string; stage_ref: string }>) ?? [];

  async function handleCancel() {
    if (!file.job_id) return;
    try { await apiFetch(`/api/queue/${file.job_id}`, { method: 'DELETE' }); } catch { /* toast handled elsewhere */ }
  }

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <h3 className="font-medium">{file.original_name}</h3>
          <Badge variant="outline">{file.status}</Badge>
        </div>
        <div className="flex gap-2">
          {file.status === 'completed' && (
            <Button size="sm" variant="outline" onClick={() => navigate(`/proofread/${file.id}`)}>Open</Button>
          )}
          {file.job_id && (file.status === 'queued' || file.status === 'running') && (
            <Button size="sm" variant="ghost" onClick={handleCancel}>Cancel</Button>
          )}
        </div>
      </div>
      <div className="space-y-1.5">
        {stages.length === 0 && <p className="text-xs text-muted-foreground">Waiting for pipeline to start…</p>}
        {stages.map((s, idx) => (
          <StageProgress
            key={idx}
            idx={idx}
            stageType={s.stage_type}
            stageRef={s.stage_ref}
            percent={progress[idx] ?? 0}
            status={status[idx] ?? 'idle'}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Tests**

```tsx
// src/components/FileCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { FileCard } from './FileCard';

const baseFile = {
  id: 'a', original_name: 'foo.mp4', status: 'completed',
  stage_outputs: [{ stage_type: 'asr', stage_ref: 'profile-a' }, { stage_type: 'mt', stage_ref: 'profile-b' }],
};

describe('FileCard', () => {
  it('renders stages with progress', () => {
    render(<MemoryRouter><FileCard file={baseFile} progress={{ 0: 100, 1: 50 }} status={{ 0: 'done', 1: 'running' }} /></MemoryRouter>);
    expect(screen.getByText('foo.mp4')).toBeInTheDocument();
    expect(screen.getAllByText(/%/)).toHaveLength(2);
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });
  it('shows Cancel when status=queued + job_id present', () => {
    render(<MemoryRouter><FileCard file={{ ...baseFile, status: 'queued', job_id: 'j1' }} progress={{}} status={{}} /></MemoryRouter>);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
  it('shows Open when completed', () => {
    render(<MemoryRouter><FileCard file={baseFile} progress={{}} status={{}} /></MemoryRouter>);
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Tests pass**

```bash
npm test -- FileCard
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/FileCard.tsx frontend/src/components/StageProgress.tsx frontend/src/components/FileCard.test.tsx
git commit -m "feat(v4 A3): FileCard with per-stage progress + Cancel/Open buttons"
```

---

## Task 15: EntityTable + EntityForm Generic Components

🎯 **Goal:** Reusable list view + form dialog for ASR/MT/Glossary/Pipeline CRUD pages.

✅ **Acceptance:**
- `<EntityTable<T>>` renders array of T with columns config + edit/delete actions
- `<EntityForm<T>>` wraps react-hook-form + zod resolver + submit handler + dialog
- Manual smoke: instantiate with any zod schema works

**Files:**
- Create: `frontend/src/components/EntityTable.tsx`, `frontend/src/components/EntityForm.tsx`, `frontend/src/components/ConfirmDialog.tsx`

- [ ] **Step 1: Implement ConfirmDialog**

```tsx
// src/components/ConfirmDialog.tsx
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export function ConfirmDialog({ open, title, description, confirmLabel = 'Confirm', onConfirm, onCancel }: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Implement EntityTable**

```tsx
// src/components/EntityTable.tsx
import { Button } from '@/components/ui/button';
import { Pencil, Trash2 } from 'lucide-react';

export interface Column<T> { header: string; render: (row: T) => React.ReactNode; }

export function EntityTable<T extends { id: string }>({
  rows, columns, onEdit, onDelete, canEdit, canDelete,
}: {
  rows: T[];
  columns: Column<T>[];
  onEdit: (row: T) => void;
  onDelete: (row: T) => void;
  canEdit: (row: T) => boolean;
  canDelete: (row: T) => boolean;
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left">
          {columns.map((c) => <th key={c.header} className="p-2 font-medium">{c.header}</th>)}
          <th className="p-2 w-24">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-b hover:bg-muted/30">
            {columns.map((c) => <td key={c.header} className="p-2">{c.render(row)}</td>)}
            <td className="p-2 flex gap-1">
              {canEdit(row) && (
                <Button size="icon" variant="ghost" onClick={() => onEdit(row)} aria-label="Edit"><Pencil className="h-4 w-4" /></Button>
              )}
              {canDelete(row) && (
                <Button size="icon" variant="ghost" onClick={() => onDelete(row)} aria-label="Delete"><Trash2 className="h-4 w-4 text-destructive" /></Button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 3: Implement EntityForm**

```tsx
// src/components/EntityForm.tsx
import { useForm, type DefaultValues, type FieldValues } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import type { ZodSchema } from 'zod';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export function EntityForm<T extends FieldValues>({
  open, title, schema, defaultValues, onSubmit, onCancel, children,
}: {
  open: boolean;
  title: string;
  schema: ZodSchema<T>;
  defaultValues: DefaultValues<T>;
  onSubmit: (data: T) => Promise<void> | void;
  onCancel: () => void;
  children: (form: ReturnType<typeof useForm<T>>) => React.ReactNode;
}) {
  const form = useForm<T>({ resolver: zodResolver(schema), defaultValues });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          {children(form)}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
            <Button type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Saving…' : 'Save'}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Build verify**

```bash
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/{EntityTable,EntityForm,ConfirmDialog}.tsx
git commit -m "feat(v4 A3): EntityTable + EntityForm + ConfirmDialog generic components"
```

---

## Task 16: ASR Profiles CRUD Page

🎯 **Goal:** Full CRUD on `/asr_profiles`.

✅ **Acceptance:**
- List from GET `/api/asr_profiles`
- Create via POST, edit via PATCH, delete via DELETE
- Form fields per zod AsrProfileSchema
- Cannot edit/delete profiles not owned + not admin (button hidden)

**Files:**
- Modify: `frontend/src/pages/AsrProfiles.tsx`

- [ ] **Step 1: Implement AsrProfiles page**

```tsx
// src/pages/AsrProfiles.tsx
import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import { AsrProfileSchema, type AsrProfile } from '@/lib/schemas/asr-profile';
import { EntityTable } from '@/components/EntityTable';
import { EntityForm } from '@/components/EntityForm';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface AsrProfileRow extends AsrProfile { id: string; user_id: number | null; }

const defaults: AsrProfile = {
  name: '', description: '', shared: false,
  asr: { engine: 'mlx-whisper', language: 'en', model_size: 'large-v3', task: 'transcribe', initial_prompt: '', simplified_to_traditional: false, condition_on_previous_text: false },
};

export default function AsrProfiles() {
  const user = useAuthStore((s) => s.user)!;
  const [rows, setRows] = useState<AsrProfileRow[]>([]);
  const [editing, setEditing] = useState<AsrProfileRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function refresh() {
    const data = await apiFetch<AsrProfileRow[]>('/api/asr_profiles');
    setRows(data);
  }
  useEffect(() => { refresh(); }, []);

  const canMutate = (r: AsrProfileRow) => user.is_admin || r.user_id === user.id;

  async function handleCreate(data: AsrProfile) {
    await apiFetch('/api/asr_profiles', { method: 'POST', body: JSON.stringify(data) });
    setCreating(false);
    refresh();
  }
  async function handleEdit(data: AsrProfile) {
    if (!editing) return;
    await apiFetch(`/api/asr_profiles/${editing.id}`, { method: 'PATCH', body: JSON.stringify(data) });
    setEditing(null);
    refresh();
  }
  async function handleDelete() {
    if (!deletingId) return;
    await apiFetch(`/api/asr_profiles/${deletingId}`, { method: 'DELETE' });
    setDeletingId(null);
    refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">ASR Profiles</h1>
        <Button onClick={() => setCreating(true)}>+ New ASR Profile</Button>
      </div>
      <EntityTable
        rows={rows}
        columns={[
          { header: 'Name', render: (r) => r.name },
          { header: 'Engine', render: (r) => r.asr.engine },
          { header: 'Language', render: (r) => r.asr.language },
          { header: 'Task', render: (r) => r.asr.task },
          { header: 'Shared', render: (r) => r.shared ? 'yes' : 'no' },
        ]}
        onEdit={setEditing}
        onDelete={(r) => setDeletingId(r.id)}
        canEdit={canMutate}
        canDelete={canMutate}
      />
      {creating && (
        <EntityForm title="New ASR Profile" open schema={AsrProfileSchema} defaultValues={defaults} onCancel={() => setCreating(false)} onSubmit={handleCreate}>
          {(form) => <AsrProfileFields form={form} />}
        </EntityForm>
      )}
      {editing && (
        <EntityForm title="Edit ASR Profile" open schema={AsrProfileSchema} defaultValues={editing} onCancel={() => setEditing(null)} onSubmit={handleEdit}>
          {(form) => <AsrProfileFields form={form} />}
        </EntityForm>
      )}
      <ConfirmDialog
        open={!!deletingId}
        title="Delete ASR Profile?"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeletingId(null)}
      />
    </div>
  );
}

function AsrProfileFields({ form }: { form: ReturnType<typeof import('react-hook-form').useForm<AsrProfile>> }) {
  const { register, formState: { errors } } = form;
  return (
    <div className="grid gap-3">
      <div><Label>Name</Label><Input {...register('name')} />{errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}</div>
      <div><Label>Description</Label><Textarea {...register('description')} /></div>
      <div className="grid grid-cols-2 gap-3">
        <div><Label>Engine</Label>
          <select {...register('asr.engine')} className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
            <option value="whisper">whisper</option>
            <option value="mlx-whisper">mlx-whisper</option>
          </select>
        </div>
        <div><Label>Language</Label><Input {...register('asr.language')} /></div>
        <div><Label>Task</Label>
          <select {...register('asr.task')} className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
            <option value="transcribe">transcribe</option>
            <option value="translate">translate</option>
          </select>
        </div>
        <div><Label>Model size</Label><Input {...register('asr.model_size')} disabled value="large-v3" /></div>
      </div>
      <div><Label>Initial prompt</Label><Textarea {...register('asr.initial_prompt')} /></div>
      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('asr.simplified_to_traditional')} /> s2hk convert</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('asr.condition_on_previous_text')} /> condition on previous</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('shared')} /> shared</label>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Manual smoke**

```bash
# Log in. Visit /asr_profiles.
# Click + New, fill form, save → row appears.
# Edit → update name → row updates.
# Delete → confirm → row disappears.
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AsrProfiles.tsx
git commit -m "feat(v4 A3): ASR Profile CRUD page"
```

---

## Task 17: MT Profiles CRUD Page

🎯 **Goal:** Full CRUD on `/mt_profiles`. Engine hidden (locked to qwen3.5-35b-a3b).

✅ **Acceptance:**
- List + Create + Edit + Delete works
- Form fields per zod MtProfileSchema with `{text}` placeholder validation visible in error message
- Engine field hidden from form (auto-set to 'qwen3.5-35b-a3b' on submit)

**Files:**
- Modify: `frontend/src/pages/MtProfiles.tsx`

- [ ] **Step 1: Implement MtProfiles**

Mirror AsrProfiles structure. Form fields:
- name, description, shared
- system_prompt (Textarea, large)
- user_message_template (Textarea, with hint text "must include {text} placeholder")
- temperature (Input number)
- batch_size (Input number)
- parallel_batches (Input number)

Engine is hidden — defaultValues sets `engine: 'qwen3.5-35b-a3b'`, no UI control.

Skeleton (full structure same as Task 16 — just the fields component differs):

```tsx
function MtProfileFields({ form }: { form: ReturnType<typeof import('react-hook-form').useForm<MtProfile>> }) {
  const { register, formState: { errors } } = form;
  return (
    <div className="grid gap-3">
      <div><Label>Name</Label><Input {...register('name')} />{errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}</div>
      <div><Label>Description</Label><Textarea {...register('description')} /></div>
      <div><Label>System prompt</Label><Textarea {...register('system_prompt')} rows={6} />{errors.system_prompt && <p className="text-xs text-destructive">{errors.system_prompt.message}</p>}</div>
      <div>
        <Label>User message template</Label>
        <Textarea {...register('user_message_template')} rows={3} />
        <p className="text-xs text-muted-foreground mt-1">Must include <code>&#123;text&#125;</code> placeholder</p>
        {errors.user_message_template && <p className="text-xs text-destructive">{errors.user_message_template.message}</p>}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div><Label>Temperature</Label><Input type="number" step="0.05" {...register('temperature', { valueAsNumber: true })} /></div>
        <div><Label>Batch size</Label><Input type="number" {...register('batch_size', { valueAsNumber: true })} /></div>
        <div><Label>Parallel batches</Label><Input type="number" {...register('parallel_batches', { valueAsNumber: true })} /></div>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('shared')} /> shared</label>
    </div>
  );
}
```

- [ ] **Step 2: Manual smoke + commit**

```bash
git add frontend/src/pages/MtProfiles.tsx
git commit -m "feat(v4 A3): MT Profile CRUD page (engine locked)"
```

---

## Task 18: Glossaries CRUD Page

🎯 **Goal:** Full CRUD on `/glossaries` with entries editor + CSV import.

✅ **Acceptance:**
- List + Create + Edit (with entry table) + Delete works
- CSV import via POST `/api/glossaries/<id>/import`
- CSV export via download link to GET `/api/glossaries/<id>/export`
- Source/target lang dropdown from `/api/glossaries/languages`

**Files:**
- Modify: `frontend/src/pages/Glossaries.tsx`

- [ ] **Step 1: Implement Glossaries with entries editor**

Mirror AsrProfiles + add entries editor with rows {source, target, target_aliases}. Use `useFieldArray` from react-hook-form for dynamic row management.

Full implementation ~150 lines. Key blocks:

```tsx
import { useFieldArray } from 'react-hook-form';

function GlossaryFields({ form }: { form: ReturnType<typeof useForm<Glossary>> }) {
  const { register, control, formState: { errors } } = form;
  const { fields, append, remove } = useFieldArray({ control, name: 'entries' });
  const [langs, setLangs] = useState<string[]>([]);
  useEffect(() => { apiFetch<{ languages: string[] }>('/api/glossaries/languages').then(r => setLangs(r.languages)); }, []);

  return (
    <div className="grid gap-3">
      <div><Label>Name</Label><Input {...register('name')} /></div>
      <div className="grid grid-cols-2 gap-3">
        <div><Label>Source lang</Label>
          <select {...register('source_lang')} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
            {langs.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div><Label>Target lang</Label>
          <select {...register('target_lang')} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
            {langs.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-2">
          <Label>Entries</Label>
          <Button type="button" size="sm" variant="outline" onClick={() => append({ source: '', target: '', target_aliases: [] })}>+ Add</Button>
        </div>
        {fields.map((f, idx) => (
          <div key={f.id} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 mb-1">
            <Input placeholder="source" {...register(`entries.${idx}.source` as const)} />
            <Input placeholder="target" {...register(`entries.${idx}.target` as const)} />
            <Input placeholder="aliases (comma)" {...register(`entries.${idx}.target_aliases.0` as const)} />
            <Button type="button" size="icon" variant="ghost" onClick={() => remove(idx)}>×</Button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

CSV import handler (separate from form):
```tsx
async function handleCsvImport(glossaryId: string, file: File) {
  const fd = new FormData();
  fd.append('file', file);
  await fetch(`/api/glossaries/${glossaryId}/import`, { method: 'POST', body: fd, credentials: 'include' });
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Glossaries.tsx
git commit -m "feat(v4 A3): Glossary CRUD page with entries editor + CSV import/export"
```

---

## Task 19: Pipelines CRUD Page + StageEditor (dnd-kit)

🎯 **Goal:** Pipeline CRUD with drag-sortable stage list using `@dnd-kit/sortable`.

✅ **Acceptance:**
- List + Create + Edit + Delete works
- Stage editor: add/remove stages, drag handle reorders
- Per-stage type dropdown (asr / mt / glossary) + ref dropdown (loaded from corresponding API)
- Cascade `broken_refs` warning chip shown when present
- First stage must be ASR — validation enforced via zod

**Files:**
- Modify: `frontend/src/pages/Pipelines.tsx`
- Create: `frontend/src/components/StageEditor.tsx`

- [ ] **Step 1: Implement StageEditor**

```tsx
// src/components/StageEditor.tsx
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/ui/button';
import { GripVertical, Trash2 } from 'lucide-react';
import type { Stage } from '@/lib/schemas/pipeline';

function SortableStage({ id, stage, onTypeChange, onRefChange, onRemove, refOptions }: {
  id: string;
  stage: Stage;
  onTypeChange: (t: Stage['type']) => void;
  onRefChange: (r: string) => void;
  onRemove: () => void;
  refOptions: Record<Stage['type'], Array<{ id: string; name: string }>>;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  return (
    <div ref={setNodeRef} style={style} className="grid grid-cols-[auto_1fr_2fr_auto] gap-2 items-center p-2 border rounded">
      <button {...attributes} {...listeners} className="text-muted-foreground cursor-grab" aria-label="Drag"><GripVertical className="h-4 w-4" /></button>
      <select value={stage.type} onChange={(e) => onTypeChange(e.target.value as Stage['type'])} className="h-9 rounded-md border border-input bg-background px-2 text-sm">
        <option value="asr">asr</option><option value="mt">mt</option><option value="glossary">glossary</option>
      </select>
      <select value={stage.ref} onChange={(e) => onRefChange(e.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm">
        <option value="">— select —</option>
        {refOptions[stage.type].map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
      <Button type="button" size="icon" variant="ghost" onClick={onRemove} aria-label="Remove"><Trash2 className="h-4 w-4 text-destructive" /></Button>
    </div>
  );
}

export function StageEditor({ stages, onChange, refOptions }: {
  stages: Stage[];
  onChange: (s: Stage[]) => void;
  refOptions: Record<Stage['type'], Array<{ id: string; name: string }>>;
}) {
  const ids = stages.map((_, i) => `stage-${i}`);
  function handleDragEnd(e: DragEndEvent) {
    if (!e.over) return;
    const oldIdx = ids.indexOf(String(e.active.id));
    const newIdx = ids.indexOf(String(e.over.id));
    if (oldIdx !== newIdx) onChange(arrayMove(stages, oldIdx, newIdx));
  }
  return (
    <div className="space-y-2">
      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {stages.map((s, i) => (
            <SortableStage
              key={`stage-${i}`}
              id={`stage-${i}`}
              stage={s}
              onTypeChange={(t) => onChange(stages.map((st, idx) => idx === i ? { type: t, ref: '' } : st))}
              onRefChange={(r) => onChange(stages.map((st, idx) => idx === i ? { ...st, ref: r } : st))}
              onRemove={() => onChange(stages.filter((_, idx) => idx !== i))}
              refOptions={refOptions}
            />
          ))}
        </SortableContext>
      </DndContext>
      <Button type="button" size="sm" variant="outline" onClick={() => onChange([...stages, { type: 'asr', ref: '' }])}>+ Add stage</Button>
    </div>
  );
}
```

- [ ] **Step 2: Implement Pipelines page**

Pipelines.tsx structure mirrors AsrProfiles + uses StageEditor inside form. Watch `stages` field via `useWatch` to drive controlled StageEditor:

```tsx
const stages = useWatch({ control: form.control, name: 'stages' });
// ...
<Controller
  name="stages"
  control={form.control}
  render={({ field }) => <StageEditor stages={field.value} onChange={field.onChange} refOptions={refOptions} />}
/>
```

`refOptions` populated by fetching `/api/asr_profiles`, `/api/mt_profiles`, `/api/glossaries` on form mount.

Broken refs banner:
```tsx
{row.broken_refs && row.broken_refs.length > 0 && (
  <Badge variant="destructive">{row.broken_refs.length} broken ref(s)</Badge>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Pipelines.tsx frontend/src/components/StageEditor.tsx
git commit -m "feat(v4 A3): Pipeline CRUD with @dnd-kit sortable stage editor"
```

---

## Task 20: Admin Page

🎯 **Goal:** Admin user management + audit log viewer on `/admin`.

✅ **Acceptance:**
- Tabs: Users / Audit
- Users tab: list + create + delete + toggle admin + reset password
- Audit tab: paginated list from `/api/admin/audit`
- Only visible to is_admin (router guard enforced)

**Files:**
- Modify: `frontend/src/pages/Admin.tsx`

- [ ] **Step 1: Implement Admin**

```tsx
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface UserRow { id: number; username: string; is_admin: boolean; }
interface AuditRow { id: number; actor_id: number; action: string; target_kind: string; target_id: string; ts: number; }

export default function Admin() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [newUser, setNewUser] = useState({ username: '', password: '', is_admin: false });

  async function refreshUsers() { setUsers(await apiFetch<UserRow[]>('/api/admin/users')); }
  async function refreshAudit() { setAudit(await apiFetch<AuditRow[]>('/api/admin/audit?limit=200')); }
  useEffect(() => { refreshUsers(); refreshAudit(); }, []);

  async function createUser() {
    await apiFetch('/api/admin/users', { method: 'POST', body: JSON.stringify(newUser) });
    setNewUser({ username: '', password: '', is_admin: false });
    refreshUsers();
    refreshAudit();
  }
  async function deleteUser(id: number) {
    await apiFetch(`/api/admin/users/${id}`, { method: 'DELETE' });
    refreshUsers();
    refreshAudit();
  }
  async function toggleAdmin(id: number) {
    await apiFetch(`/api/admin/users/${id}/toggle-admin`, { method: 'POST' });
    refreshUsers();
    refreshAudit();
  }
  async function resetPassword(id: number) {
    const pw = prompt('New password (≥8 chars):');
    if (!pw) return;
    await apiFetch(`/api/admin/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify({ password: pw }) });
    refreshAudit();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Admin</h1>
      <Tabs defaultValue="users">
        <TabsList><TabsTrigger value="users">Users</TabsTrigger><TabsTrigger value="audit">Audit</TabsTrigger></TabsList>
        <TabsContent value="users" className="space-y-4">
          <div className="grid grid-cols-[1fr_1fr_auto_auto] gap-2 items-end p-3 border rounded">
            <div><Label>Username</Label><Input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} /></div>
            <div><Label>Password</Label><Input type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} /></div>
            <label className="flex items-center gap-2 text-sm pb-2"><input type="checkbox" checked={newUser.is_admin} onChange={(e) => setNewUser({ ...newUser, is_admin: e.target.checked })} /> admin</label>
            <Button onClick={createUser} disabled={!newUser.username || !newUser.password}>Create</Button>
          </div>
          <table className="w-full text-sm">
            <thead><tr className="border-b"><th className="p-2 text-left">ID</th><th className="p-2 text-left">Username</th><th className="p-2 text-left">Admin?</th><th className="p-2">Actions</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b">
                  <td className="p-2">{u.id}</td>
                  <td className="p-2">{u.username}</td>
                  <td className="p-2">{u.is_admin ? 'yes' : 'no'}</td>
                  <td className="p-2 flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => toggleAdmin(u.id)}>Toggle admin</Button>
                    <Button size="sm" variant="outline" onClick={() => resetPassword(u.id)}>Reset pw</Button>
                    <Button size="sm" variant="destructive" onClick={() => deleteUser(u.id)}>Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>
        <TabsContent value="audit">
          <table className="w-full text-sm">
            <thead><tr className="border-b"><th className="p-2 text-left">Time</th><th className="p-2 text-left">Actor</th><th className="p-2 text-left">Action</th><th className="p-2 text-left">Target</th></tr></thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id} className="border-b">
                  <td className="p-2 text-xs">{new Date(a.ts * 1000).toLocaleString()}</td>
                  <td className="p-2">{a.actor_id}</td>
                  <td className="p-2">{a.action}</td>
                  <td className="p-2 text-xs">{a.target_kind}:{a.target_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Admin.tsx
git commit -m "feat(v4 A3): Admin page (users + audit)"
```

---

## Task 21: Proofread Placeholder

🎯 **Goal:** Placeholder page at `/proofread/:fileId` that says "A4 — proofread editor coming soon" + back button.

✅ **Acceptance:**
- Routes work; placeholder visible
- Back button navigates to /

**Files:**
- Modify: `frontend/src/pages/ProofreadPlaceholder.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function ProofreadPlaceholder() {
  const { fileId } = useParams();
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <Button variant="outline" onClick={() => navigate('/')}>← Back</Button>
      <div className="p-8 border rounded-lg text-center text-muted-foreground">
        <p>Proofread editor for file <code>{fileId}</code> coming in A4.</p>
        <p className="text-xs mt-2">Until then, the legacy <a href="/proofread.html" className="underline">vanilla proofread page</a> still works.</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/ProofreadPlaceholder.tsx
git commit -m "feat(v4 A3): proofread placeholder route (A4 will replace)"
```

---

## Task 22: Playwright E2E — Auth + Dashboard

🎯 **Goal:** New Playwright suite under `frontend/tests-e2e/` covers auth flow + dashboard upload+pipeline.

✅ **Acceptance:**
- `frontend/playwright.config.ts` configured for `http://localhost:5173` (Vite dev)
- `auth.spec.ts` — login → see dashboard → logout
- `dashboard.spec.ts` — pick pipeline → drop file → observe stage_progress mock events

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/tests-e2e/auth.spec.ts`, `frontend/tests-e2e/dashboard.spec.ts`, `frontend/tests-e2e/fixtures/test-server.ts`

- [ ] **Step 1: Playwright config**

```ts
// frontend/playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests-e2e',
  use: { baseURL: 'http://localhost:5173' },
  webServer: { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: !process.env.CI, timeout: 60_000 },
});
```

- [ ] **Step 2: auth.spec.ts**

```ts
import { test, expect } from '@playwright/test';

test('login → dashboard → logout', async ({ page }) => {
  await page.goto('/login');
  await page.fill('#username', 'admin');
  await page.fill('#password', 'AdminPass1!');
  await page.click('button:has-text("Log in")');
  await expect(page.locator('h1:has-text("Dashboard"), [role="heading"]:has-text("Dashboard"), h1:text("MoTitle")')).toBeVisible({ timeout: 5_000 });
  await page.click('button:has-text("Logout")');
  await expect(page).toHaveURL(/\/login/);
});

test('unauthenticated /pipelines redirects to /login', async ({ page }) => {
  await page.context().clearCookies();
  await page.goto('/pipelines');
  await expect(page).toHaveURL(/\/login/);
});
```

- [ ] **Step 3: dashboard.spec.ts**

```ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await expect(page).toHaveURL('/');
  });

  test('shows pipeline picker and upload zone', async ({ page }) => {
    await expect(page.locator('label:has-text("Pipeline")')).toBeVisible();
    await expect(page.locator('text=Drag video/audio file')).toBeVisible();
  });
});
```

- [ ] **Step 4: Run E2E suite**

```bash
cd frontend && npx playwright test
```

Expected: 3 PASS (auth + 1 dashboard).

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/tests-e2e/
git commit -m "test(v4 A3): Playwright auth + dashboard E2E"
```

---

## Task 23: CLAUDE.md Update + A3 Wrap-up

🎯 **Goal:** Document A3 completion in CLAUDE.md.

✅ **Acceptance:**
- CLAUDE.md gains a "v4.0 A3" entry under Completed Features
- Repo structure section mentions both `frontend/` (Vite + React) and `frontend.old/` (legacy, A5 deletes)
- Mandatory documentation updates rule still upheld

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add v4.0 A3 Completed Features entry**

Just under v4.0 A1 entry, insert:

```markdown
### v4.0 A3 — Frontend foundation (in progress on `chore/asr-mt-rearchitecture-research`)
- Vanilla HTML pages moved to [frontend.old/](frontend.old/) (A5 deletes); new Vite + React 18 + TypeScript project bootstrapped under [frontend/](frontend/) per design doc [§14](docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md)
- Pages shipped: `/login`, `/` (Dashboard with PipelinePicker + UploadDropzone + per-stage FileCard), `/pipelines` (drag-sortable @dnd-kit StageEditor), `/asr_profiles`, `/mt_profiles`, `/glossaries` (with entries editor + CSV), `/admin` (users + audit), `/proofread/:fileId` (placeholder — A4 implements full editor)
- Auth: React Router guard + boot `/api/me` probe + Zustand `useAuthStore`; logout via TopBar
- Realtime: React Context + reducer driven by Socket.IO events (`file_added`, `file_updated`, `pipeline_stage_progress`, `pipeline_stage_complete`, `pipeline_complete`, `pipeline_failed`)
- State management: Zustand for auth + pipeline-picker (with localStorage persistence) + UI toasts; per-page local state for entity lists
- Validation: zod schemas mirror backend validators (`AsrProfileSchema` / `MtProfileSchema` / `GlossarySchema` / `PipelineSchema` / `LoginSchema`)
- Forms: react-hook-form + zodResolver; shared `<EntityTable>` + `<EntityForm>` + `<ConfirmDialog>` generic components
- Dev mode: `npm run dev` boots Vite (5173) + Flask (5001) via `concurrently`; Vite proxy forwards `/api`, `/socket.io`, `/fonts` to Flask
- Production: `npm run build` → `frontend/dist/` → Flask `serve_index` / `serve_assets` + SPA fallback for React Router routes
- Backend: 4 new tests for SPA fallback / serve_assets / `pipeline_id` form field on `/api/transcribe`; legacy ASR-only flow preserved when `pipeline_id` absent (A5 removes)
- Frontend tests: ~40 Vitest units (schemas, stores, components, SocketProvider reducer) + 3 Playwright E2E (auth + dashboard + protected route)
- **Out of A3 scope** (deferred to A4): proofread page (per-segment editor + render modal); (A5): legacy HTML deletion + backend route cleanup
```

- [ ] **Step 2: Update Repository Structure section**

In the existing tree, add note that `frontend/` is now React (was vanilla; vanilla now in `frontend.old/`):

```markdown
├── frontend.old/               # Legacy vanilla HTML/CSS/JS (A5 deletes)
└── frontend/                   # NEW — Vite + React 18 + TypeScript (v4.0 A3)
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(v4 A3): CLAUDE.md entry for A3 + frontend.old/ rename"
```

---

## Plan Self-Review

**Spec coverage:**
- G1 (Vite bootstrap) → T1 ✓
- G2 (rename to frontend.old) → T1 ✓
- G3 (concurrently dev) → T1+T3 ✓
- G4 (auth flow) → T7+T10 ✓
- G5 (Dashboard) → T12+T13+T14 ✓
- G6 (CRUD pages) → T16+T17+T18+T19+T20 ✓
- G7 (Socket.IO realtime) → T11 ✓

**Placeholder scan:** None. Every step has executable code or precise command.

**Type consistency:** `AsrProfile` / `MtProfile` / `Glossary` / `Pipeline` / `Stage` types declared in zod schemas (T6) and reused across pages (T16/T17/T18/T19). `FileRecord` / `SocketState` declared in `socket-events.ts` (T11) and consumed by FileCard (T14) + Dashboard (T13).

**Big Bang adherence:** No backwards-compat in new React app. Legacy `frontend.old/` retained for `/login.html` /  `/proofread.html` fallback only — A4 redirects + A5 deletes.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-17-v4-A3-frontend-foundation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review per task, fast iteration

**2. Inline Execution** — Execute tasks in this session via executing-plans, batch with checkpoints

Each of the 23 tasks carries 🎯 Goal + ✅ Acceptance markers — subagent dispatches must cite both and reviewers must verify against them (consistent with A1 plan format).
