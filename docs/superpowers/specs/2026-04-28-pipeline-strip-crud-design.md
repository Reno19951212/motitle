# Pipeline Strip CRUD — 預設 + 語言配置嘅前端 CRUD

**Date:** 2026-04-28
**Status:** Approved

---

## Problem

頂部 Pipeline strip 而家係讀-only 加 PATCH active Profile：用戶可以喺 dropdown 揀 ASR model / MT engine / Glossary，但唔可以：

1. **儲存當前 Pipeline 組合做新 Profile 預設** — 兩個 stub button (`💾 儲存當前設定`、`⚙ 管理預設`) 喺 [frontend/index.html:1975-1976](frontend/index.html#L1975) 已經有 markup 但冇 onclick，撳唔到嘢
2. **揀同管理 ASR 嘅語言配置** — Profile JSON 入面 `asr.language_config_id` 控制 segmentation 同 batch params，但 frontend 完全冇 UI 暴露呢個欄位。要改要直接 edit JSON file，亦冇路徑由 frontend 新增 / 編輯 / 刪除 language config

兩個 gap 共同特性：**Pipeline strip 係日常工作流嘅核心，但 CRUD 操作完全冇 surface**。用戶要做組合管理、要 cycle 唔同 segmentation profile，都要走 sidebar Profile editor 或者 raw JSON editing — 反工作流。

---

## Goal

兩個 frontend CRUD 入口都駁通：

- **Pipeline 預設 CRUD** — `💾 儲存當前設定為新預設` + `⚙ 管理預設` 兩個 modal 工作
- **語言配置 CRUD** — ASR step menu 入面加 sub-section 列出可選嘅 language config + `➕ 新增` + `⚙ 管理` modal

兩個都跟 Pipeline strip 嘅樂高哲學：選項即 list、操作即 dropdown、CRUD 即 modal。

---

## Non-Goals

- 唔做 Profile 內部欄位（ASR model_size / MT engine / font ...）嘅深層編輯 UI — sidebar Profile editor 已經有完整 schema-driven form
- 唔做 language config 嘅 cascade delete（被 Profile 使用嘅 config 唔俾刪，要 user 先改 Profile）
- 唔做 language → language_config_id 嘅 mapping / filter — dropdown 直接列全部，揀錯影響有限（language_config 只控 segment 同 batch params，唔影響 ASR `language` 識別）
- 唔做 import / export language config（CSV-style bulk）— 用戶日常 workflow 唔頻繁建變體
- 唔改 backend Profile API（已齊全）— 只加 `POST` + `DELETE /api/languages`

---

## Design

### 整體架構

```
Pipeline Strip (top bar)
├── [Pipeline 預設 ▾]
│   dropdown:
│     • Broadcast Production (當前)
│     • dev-default
│     ──────────────────
│     💾 將當前設定儲存為新預設…   ← 新 modal: Profile 儲存
│     ⚙ 管理預設…                    ← 新 modal: Profile 管理
│
├── [ASR ▾]
│   dropdown:
│     — ASR 模型 —
│     • tiny / small / medium / large-v3 (現有)
│     ──────────────────
│     — 語言配置 —                    ← 新 sub-section
│     • en — English
│     • zh — Chinese
│     • zh-news — 中文 · 新聞 (用戶建)
│     ──────────────────
│     ➕ 新增語言配置…                 ← 新 modal: LangConfig 建立
│     ⚙ 管理語言配置…                 ← 新 modal: LangConfig 管理
│
├── [MT ▾]   (不變)
├── [輸出 ▾] (不變)
└── [術語表 ▾] (不變)
```

---

### Feature 1 — Pipeline 預設 CRUD

#### A. 「💾 儲存當前設定為新預設」 modal

```
┌─ 儲存為新 Pipeline 預設 ─────────────────────┐
│ 預設名稱*       [ Broadcast 4K Master      ]│
│ 描述（可選）    [ ProRes HQ + Claude Opus  ]│
│                                              │
│ 將會包含當前設定：                           │
│   ASR        large-v3 (mlx-whisper)         │
│   MT         openrouter / claude-opus-4.5   │
│   術語表     broadcast-news (17 條)         │
│   字型       Noto Sans TC, 35pt             │
│                                              │
│           [取消]    [儲存並啟用]             │
└──────────────────────────────────────────────┘
```

行為：
- Form 預填當前 `activeProfile.name + " (副本)"` + 空 description
- `[儲存並啟用]` → POST `/api/profiles` body 用 `activeProfile` deep-clone + 改 `name` / `description` + 移除 `id` / `created_at` / `updated_at`（後端會分配新 uuid）
- POST 200 之後即刻 POST `/api/profiles/<new_id>/activate`，即時 `renderPipelineStrip()`，toast `已儲存並啟用：${name}`
- POST 失敗 → toast `儲存失敗: ${error}`，modal 保持打開等用戶 retry / 取消
- Active Profile 為 None（極罕見）→ `💾` button disable 加 tooltip `請先啟用一個 Profile`

#### B. 「⚙ 管理預設」 modal

```
┌─ Pipeline 預設管理 ───────────────────────────┐
│ + 新增預設                                    │
│                                               │
│ ✓ Broadcast Production           (當前)       │
│   Full quality models                  [✎][🗑]│
│   ASR large-v3 · MT openrouter                │
│ ──────────────────────────────────────────── │
│   dev-default                                 │
│   Lightweight dev preset                [✎][🗑]│
│   ASR small · MT mock                         │
│                                               │
│                            [關閉]             │
└───────────────────────────────────────────────┘
```

行為：
- List view 由 `GET /api/profiles` 拎，per-row buttons：
  - **✎ 編輯** → 開「編輯預設」modal（同儲存 form 一樣，但 prefill），save 用 `PATCH /api/profiles/<id>` 只 patch `name` + `description`（深層欄位仲係用 sidebar editor）
  - **🗑 刪除** → confirm dialog → `DELETE /api/profiles/<id>`；當前 active profile 嘅 🗑 button disabled 加 tooltip `當前 Profile 唔可以刪除，請先切換到另一個`
- Click row body → `POST /api/profiles/<id>/activate`，badge 即時更新

#### C. Click outside / Esc 關 modal

兩個 modal 都用現有 `.overlay` pattern（同 glossary apply / render modal 一致）。

---

### Feature 2 — 語言配置 CRUD（ASR step menu sub-section）

#### A. ASR step menu 加語言配置 sub-section

```
[ASR · large-v3 ▾]
┌─────────────────────────────────────┐
│ ASR · 模型                          │
│   ⦿ large-v3                        │
│   ○ medium / small / tiny           │
│ ─────────────────────────────────── │
│ 語言配置                            │
│   ⦿ en — English                    │
│   ○ zh — Chinese                    │
│   ○ zh-news — 中文 · 新聞           │
│ ─────────────────────────────────── │
│   ➕ 新增語言配置…                  │
│   ⚙ 管理語言配置…                   │
└─────────────────────────────────────┘
```

實作：
- Page load 時 `fetchLanguageConfigs()` (`GET /api/languages`) cache 落 `availableLanguageConfigs` global，同 `glossaries` 嘅 pattern 一致
- `renderPipelineStrip()` 內部 ASR menu 由 [frontend/index.html:1979](frontend/index.html#L1979) 改寫為包含兩個 section（model + lang config），透過 `<div class="split-divider"></div>` 分隔，視覺對齊 Pipeline preset menu 嘅 `[+ 新增 / ⚙ 管理]` pattern
- Click language config row → `applyLanguageConfig(lcId)`：
  ```js
  async function applyLanguageConfig(lcId) {
    if (!activeProfile) return;
    const newAsr = {...activeProfile.asr, language_config_id: lcId};
    const r = await fetch(`${API_BASE}/api/profiles/${activeProfile.id}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({asr: newAsr}),
    });
    if (!r.ok) { showToast('切換語言配置失敗', 'error'); return; }
    activeProfile = (await r.json()).profile;
    renderPipelineStrip();
    showToast(`已切換語言配置：${lcId}`, 'success');
  }
  ```

#### B. 「➕ 新增 / 編輯」 modal

共用同一份 form，由 `mode = 'create' | 'edit'` 切換 POST vs PATCH。

```
┌─ 新增語言配置 ──────────────────────────────────┐
│ ID *               [zh-news              ]      │
│   ↳ 唯一識別碼，只可英數字 + 連字號             │
│                                                 │
│ 顯示名稱 *         [中文 · 新聞              ]  │
│   ↳ Dropdown 入面顯示嘅 label                  │
│                                                 │
│ ─── ASR 分段參數 ───                            │
│ 每段最多字數       [───●─────]  25  (5–60)     │
│   ↳ Whisper 出嚟超過呢個字數會喺句號處再切      │
│                                                 │
│ 每段最長秒數       [────●────]  8s  (2–60)     │
│   ↳ 一段字幕最長停留多耐                        │
│                                                 │
│ ─── 翻譯參數 ───                                │
│ 每批 batch 大小    [──●──────]  8   (1–20)     │
│   ↳ 一次過餵 LLM 幾多句翻譯                     │
│                                                 │
│ Temperature        [─●───────]  0.1 (0–1)      │
│   ↳ 0 = 穩定；1 = 多樣化但唔穩定                │
│                                                 │
│            [取消]      [儲存]                   │
└─────────────────────────────────────────────────┘
```

Form fields → JSON shape（對應現有 `backend/config/languages/{en,zh}.json` schema）：

```json
{
  "id": "zh-news",
  "name": "中文 · 新聞",
  "asr": {
    "max_words_per_segment": 20,
    "max_segment_duration": 5
  },
  "translation": {
    "batch_size": 8,
    "temperature": 0.1
  }
}
```

驗證（前端 + 後端 mirror）：
- `id` 必填、`/^[a-z0-9-]+$/`、長度 1–32
- `name` 必填、長度 1–50
- `max_words_per_segment` int 5–60
- `max_segment_duration` int 2–60
- `batch_size` int 1–20
- `temperature` float 0–1（step 0.05）

POST 200 後刷新 `availableLanguageConfigs` cache，重 render Pipeline strip，toast `已建立語言配置：${id}`。

POST 409（id 撞名）→ inline error 喺 ID 欄位下面顯示 `呢個 ID 已存在`，唔關 modal。

#### C. 「⚙ 管理語言配置」 modal

```
┌─ 語言配置管理 ──────────────────────────────┐
│ + 新增配置                                   │
│                                              │
│ • en — English                  (內置) [✎]   │
│   25 字 / 40s · batch 8 · temp 0.1          │
│ • zh — Chinese                  (內置) [✎]   │
│   30 字 / 8s · batch 8 · temp 0.1           │
│ • zh-news — 中文 · 新聞              [✎][🗑]│
│   20 字 / 5s · batch 8 · temp 0.1           │
│                                              │
│                            [關閉]            │
└──────────────────────────────────────────────┘
```

行為：
- `en` / `zh` 內置 config 嘅 🗑 button absent，✎ 仍然可以（PATCH name / params）— 但 ID 唔可以改（disable input）
- 其他 config：✎ + 🗑 都可以；🗑 撳前 confirm dialog
- 刪除返 400 帶 affected profile names → toast `'${id}' 仲被使用：${profile_names.join(', ')}`，modal 保持打開

#### D. Pipeline strip ASR step 顯示語言配置 (optional UX)

Pipeline strip 嘅 ASR step 而家只顯示 `model_size`（[frontend/index.html:2017](frontend/index.html#L2017)）。為咗用戶見到當前選緊邊個 language config，display 改為：`large-v3 · zh-news`（model_size + 短橫線 + lc_id）。Hover tooltip 完整名 `Whisper large-v3 · 中文 · 新聞`。

---

### Backend changes

#### A. 加 `POST /api/languages`

```python
@app.route('/api/languages', methods=['POST'])
def api_create_language_config():
    data = request.get_json() or {}
    lc_id = data.get('id', '').strip()

    if not lc_id or not re.match(r'^[a-z0-9-]{1,32}$', lc_id):
        return jsonify({'error': 'Invalid id (must match [a-z0-9-]{1,32})'}), 400
    if _language_config_manager.get(lc_id) is not None:
        return jsonify({'error': f'Language config "{lc_id}" already exists'}), 409

    name = (data.get('name') or '').strip()
    if not name or len(name) > 50:
        return jsonify({'error': 'Invalid name (1–50 chars required)'}), 400

    asr = data.get('asr', {})
    tr  = data.get('translation', {})
    try:
        config = {
            'id': lc_id,
            'name': name,
            'asr': {
                'max_words_per_segment': _validate_int(asr.get('max_words_per_segment'), 5, 60),
                'max_segment_duration':  _validate_int(asr.get('max_segment_duration'), 2, 60),
            },
            'translation': {
                'batch_size':  _validate_int(tr.get('batch_size'), 1, 20),
                'temperature': _validate_float(tr.get('temperature'), 0, 1),
            },
        }
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    _language_config_manager.create(config)
    return jsonify({'config': config}), 200
```

#### B. 加 `DELETE /api/languages/<id>`

```python
@app.route('/api/languages/<lc_id>', methods=['DELETE'])
def api_delete_language_config(lc_id):
    if lc_id in ('en', 'zh'):
        return jsonify({'error': 'Cannot delete built-in language config'}), 400

    if _language_config_manager.get(lc_id) is None:
        return jsonify({'error': 'Not found'}), 404

    used_by = [
        p['name'] for p in _profile_manager.list_all()
        if p.get('asr', {}).get('language_config_id') == lc_id
    ]
    if used_by:
        return jsonify({
            'error': f'Language config "{lc_id}" used by {len(used_by)} profile(s): {", ".join(used_by)}'
        }), 400

    _language_config_manager.delete(lc_id)
    return jsonify({'ok': True}), 200
```

#### C. `LanguageConfigManager` 加 `create()` / `delete()` method

`backend/language_config.py` 已經有 `get()` / `update()` / `list_all()`。要加：

```python
def create(self, config: dict) -> dict:
    path = self._dir / f"{config['id']}.json"
    if path.exists():
        raise ValueError(f"Language config {config['id']} already exists")
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2))
    return config

def delete(self, lc_id: str) -> None:
    path = self._dir / f"{lc_id}.json"
    if path.exists():
        path.unlink()
```

#### D. `_validate_int` / `_validate_float` helpers

如果 `app.py` 已經有就重用；冇就加：

```python
def _validate_int(value, lo, hi):
    if value is None: raise ValueError(f'Required field missing')
    try: v = int(value)
    except (TypeError, ValueError): raise ValueError(f'Must be integer, got {value!r}')
    if not (lo <= v <= hi): raise ValueError(f'Must be in {lo}–{hi}, got {v}')
    return v

def _validate_float(value, lo, hi):
    if value is None: raise ValueError(f'Required field missing')
    try: v = float(value)
    except (TypeError, ValueError): raise ValueError(f'Must be number, got {value!r}')
    if not (lo <= v <= hi): raise ValueError(f'Must be in {lo}–{hi}, got {v}')
    return v
```

---

## Edge Cases

| 場景 | 行為 |
|---|---|
| Active Profile `language_config_id` 指住已刪除 config | Backend `transcribe_with_segments()` 已存在 fallback 去 `DEFAULT_ASR_CONFIG` ([app.py:458](backend/app.py#L458))。Frontend dropdown 顯示 `<unknown> — (config 已刪除)`，紅色 hint 鼓勵用戶揀返一個 |
| 建立新 Profile 預設冇填 description | Description 係 optional |
| ID 撞名（zh-news 已存在）| POST 409；前端 inline error，唔關 modal |
| ID 含非法字元（中文、空格、`/`）| 前端 `pattern="[a-z0-9-]+"` block，後端再 regex validate（path-injection 防護）|
| 刪除 `en` / `zh` 內置 config | 400；前端 🗑 button absent for built-ins |
| 刪除被 Profile 使用嘅 config | 400 列出 profile names；前端 toast 顯示，modal 保持打開 |
| 建立 Profile 預設時 active Profile 係 None | `💾` button disable + tooltip |
| Profile name 撞名 | 後端唔阻止（id uuid 先係 unique key）；前端友善加 ` (副本)` 後綴 |
| 編輯內置 config 把 ID 改咗 | ID input disabled — 內置 config 嘅 ID 係 hardcoded fallback target |
| 同時開多個 manage modal（兩 tab）| Socket.IO `profile_updated` 事件已存在會 propagate；language config 暫無 socket event，PATCH/DELETE 後其他 tab 要手動刷新 — 標記為 known limitation，後續可以加 `language_config_updated` event |

---

## Testing

### Backend (pytest, `backend/tests/test_languages_crud.py`)

- `test_create_language_config_success` — POST 合法 body → 200 + JSON includes new config，文件 exist
- `test_create_id_collision` — POST id 已存在 → 409
- `test_create_invalid_id_format` — POST id `"my/lang"` → 400
- `test_create_out_of_range_value` — POST `max_words_per_segment: 100` → 400
- `test_delete_built_in_blocked` — DELETE `/api/languages/en` → 400
- `test_delete_in_use_blocked` — DELETE config 被 profile 使用 → 400 含 profile names
- `test_delete_unused_succeeds` — DELETE 未使用 config → 200，文件唔再存在
- `test_delete_nonexistent` — DELETE 唔存在嘅 id → 404

### Frontend (Playwright smoke `/tmp/check_pipeline_crud.py`)

- **Scenario A (Profile 儲存)**：open Pipeline preset menu → 撳 `💾` → modal 出現 → 填名 → POST mock → toast 出 → dropdown reopen 見到新 entry
- **Scenario B (Language config 新增)**：open ASR step menu → 撳 `➕` → form 出 → 填 + 儲存 → POST mock → ASR menu reopen 見到新 config
- **Scenario C (PATCH active profile)**：點擊 dropdown 入面新建 config → PATCH mock 攔截 body 包含 `asr.language_config_id: <new_id>` → toast 出
- **Scenario D (built-in 保護)**：open 管理 modal → `en` row 嘅 🗑 button absent
- **Scenario E (in-use delete blocked)**：嘗試刪除 in-use config → mock backend 返 400 → toast 出 + modal 保持打開

---

## Out of Scope

- 深層 Profile 欄位編輯（ASR / MT / font / render）— 用 sidebar editor
- Cascade delete（刪 language config 同時刪 / 改 affected profile）
- Bulk import / export language config
- Language config socket event broadcast 跨 tab 同步 — 已知 limitation
- Default value 推薦（譬如針對 zh-news 自動填短句參數）— 用戶手動填
