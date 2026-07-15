# 術語表近音別名 — 閉環 UI + 行話表管理 Implementation Plan — Plan B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 令 Plan A 嘅確定性別名引擎真正「有人填得落」—— 術語表頁加近音別名 chip、校對頁掃描加「疑似聽錯」一鍵回饋、加系統行話表管理員編輯，令英文同粵語（連行話）嘅聽錯都可以一㩒變成永久別名。

**Architecture:** 三個來源嘅別名寫入路徑：glossary entry `source_variants`/`target_aliases`（經現有 `update_entry` append）、lexicon `variants`（新 `lexicon_manager.py` 原子寫）。校對頁 `glossary-preview` 擴充一個 `kind:'suspect'` 分節，用 Plan A 已有嘅 `en_correction.judge_candidates` / `phonetic_correction.match_segments` 生成疑似聽錯（零 LLM），逐項一鍵寫別名。全部 add-only、向後兼容。

**Tech Stack:** Python 3.9 + 純 stdlib、Flask、vanilla JS（無 build step）、pytest。

**Spec:** [docs/superpowers/specs/2026-07-14-glossary-fuzzy-alias-design.md](../specs/2026-07-14-glossary-fuzzy-alias-design.md) §5（閉環）+ §3.2（lexicon）
**依賴:** Plan A 已落地（`alias_rewrite.py`、`source_variants` 資料模型、`load_lexicon_variants`、`deterministic_apply` 修好）。branch `feat/glossary-fuzzy-match`。

**Scope note:** 本 plan = **核心閉環 + 行話表管理**。**自動學（AI 確認過嘅糾正寫入待確認別名列表）= Plan C**（後推：粵語 judge 改動冇 `entry_id`/`glossary_id` 有 attribution 不對稱，需獨立處理；用戶已同意唔即刻生效）。

## Global Constraints

- **Python 3.9**：`from typing import ...`，唔用 `list[]`。
- **Immutable**：原子寫（temp + `os.replace`），永不 in-place mutate 共享結構。
- **向後兼容 / add-only**：`glossary-preview` 只可以**加** field（`kind:'suspect'` items）；改名/刪 field 直接 break 前端。`racing_terms.json` dual-shape（bare string + `{term,variants}`）兩種必須並存。
- **Authz（沿用現有模型，唔改）**：glossary entry 寫入 = `_glossary_manager.can_edit(gid, uid, is_admin)`（shared 表 = admin only）；**lexicon 寫入 = `@admin_required`**（系統行話表全局共用）。403 要回清楚中文訊息，前端顯示。
- **零 LLM 喺掃描層**：疑似聽錯用確定性 candidate generator（`judge_candidates`/`match_segments`），**唔跑 judge**。人手一㩒 = 人做 judge。
- **粵語 attribution**：`phonetic_correction.match_segments` candidate **冇** `entry_id`/`glossary_id`（只有 canonical `glossary_name` + `source_index:'glossary'|'supplement'`）。`glossary` canonical → 靠 `strip_horse_id(target)` 反查 entry；`supplement` canonical → 行話 term（寫 lexicon）。
- **測試隔離**：單獨跑改到嘅 test file（memory `test-suite-isolation-baseline`）。`backend/venv/bin/python` 跑 pytest。
- **前端無 build step**：改 `.html`/`.js` 即時生效，hard refresh 就得；classic script 共享 page globals。

---

### Task 1: `lexicon_manager.py` — 系統行話表原子讀寫

**Files:**
- Create: `backend/lexicon_manager.py`
- Test: `backend/tests/test_lexicon_manager.py`

**Interfaces:**
- Consumes: `phonetic_correction.LEXICON_DIR`（`Path`，已存在）。
- Produces:
  - `get_lexicon(style: str) -> Optional[dict]` — 正規化 view `{"style": str, "terms": [{"term": str, "variants": List[str]}]}`；壞 style / 冇檔 → `None`。
  - `add_term_variant(style: str, term: str, variant: str) -> dict` — 為 `term` 追加一個 variant（dedupe），term 唔存在就新增一條 `{term, variants}`；bare-string 條目升級成 object；其餘條目原樣保留。回正規化 view。
  - `set_lexicon(style: str, terms: List[dict]) -> dict` — 管理員 bulk 覆寫（每條 `{term, variants}`；`variants` 空 → 寫返 bare string 保持精簡）。回正規化 view。
  - 原子寫（temp + `os.replace`）+ per-style lock（仿 `glossary.py` `_get_gm_lock`）。

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_lexicon_manager.py
import os, sys, json, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lexicon_manager as lm


def _seed(tmp_path, monkeypatch, terms):
    d = tmp_path / "lex"
    d.mkdir()
    (d / "racing_terms.json").write_text(
        json.dumps({"style": "racing", "comment": "x", "terms": terms}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(lm, "LEXICON_DIR", pathlib.Path(d))


def test_get_lexicon_normalizes_both_shapes(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["內欄位置", {"term": "殿後", "variants": ["電流位"]}])
    view = lm.get_lexicon("racing")
    terms = {t["term"]: t["variants"] for t in view["terms"]}
    assert terms["內欄位置"] == []           # bare string → variants []
    assert terms["殿後"] == ["電流位"]


def test_add_term_variant_dedupes_and_upgrades_shape(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["殿後"])   # bare string
    lm.add_term_variant("racing", "殿後", "電流位")
    lm.add_term_variant("racing", "殿後", "電流位")  # dup → no-op
    view = lm.get_lexicon("racing")
    dh = [t for t in view["terms"] if t["term"] == "殿後"][0]
    assert dh["variants"] == ["電流位"]
    # 原始檔真係變咗 object shape，load_lexicon 仍抽到 term
    import phonetic_correction as pc
    monkeypatch.setattr(pc, "LEXICON_DIR", lm.LEXICON_DIR)
    assert "殿後" in pc.load_lexicon("racing")
    assert lm.get_lexicon("racing")  # 檔案合法


def test_add_term_variant_creates_missing_term(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["內欄位置"])
    lm.add_term_variant("racing", "後上", "後尚")
    view = lm.get_lexicon("racing")
    assert any(t["term"] == "後上" and t["variants"] == ["後尚"] for t in view["terms"])


def test_set_lexicon_empty_variants_writes_bare_string(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [{"term": "殿後", "variants": ["x"]}])
    lm.set_lexicon("racing", [{"term": "殿後", "variants": []},
                              {"term": "尾二", "variants": ["尾指位置"]}])
    raw = json.loads((lm.LEXICON_DIR / "racing_terms.json").read_text(encoding="utf-8"))
    assert "殿後" in raw["terms"]                       # bare string（空 variants）
    assert {"term": "尾二", "variants": ["尾指位置"]} in raw["terms"]


def test_bad_style_returns_none(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["x"])
    assert lm.get_lexicon("../etc") is None
    assert lm.get_lexicon("nonexistent") is None
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_lexicon_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lexicon_manager'`

- [ ] **Step 3: 實現**

```python
# backend/lexicon_manager.py
"""系統行話表（phonetic lexicon）原子讀寫 — pure-ish manager。

config/phonetic_lexicons/<style>_terms.json 嘅 CRUD。dual-shape 保留：
term 可以係 bare string 或 {"term","variants"} object。variants 非空 → object；
空 → bare string（精簡）。原子寫 + per-style lock。管理員專屬（route 層 gate）。
Python 3.9 / immutable。
"""
import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from phonetic_correction import LEXICON_DIR  # 同一個 config 目錄

_STYLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LOCKS: Dict[str, threading.Lock] = {}
_MASTER = threading.Lock()


def _lock(style: str) -> threading.Lock:
    with _MASTER:
        if style not in _LOCKS:
            _LOCKS[style] = threading.Lock()
        return _LOCKS[style]


def _path(style: str) -> Optional[Path]:
    if not style or not _STYLE_RE.match(style):
        return None
    return LEXICON_DIR / "{}_terms.json".format(style)


def _read_raw(style: str) -> Optional[dict]:
    p = _path(style)
    if p is None or not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_terms(raw_terms) -> List[dict]:
    out: List[dict] = []
    for item in raw_terms or []:
        if isinstance(item, str) and item.strip():
            out.append({"term": item.strip(), "variants": []})
        elif isinstance(item, dict):
            term = (item.get("term") or "").strip()
            if not term:
                continue
            variants = [str(v).strip() for v in (item.get("variants") or [])
                        if v and str(v).strip()]
            out.append({"term": term, "variants": variants})
    return out


def get_lexicon(style: str) -> Optional[dict]:
    """正規化 view {"style", "terms":[{"term","variants"}]}；壞 style/冇檔 → None。"""
    data = _read_raw(style)
    if data is None:
        return None
    return {"style": style, "terms": _normalize_terms(data.get("terms"))}


def _write(style: str, data: dict) -> None:
    p = _path(style)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _to_raw_terms(terms: List[dict]) -> List:
    """正規化 terms → 磁碟 shape：variants 非空 → object，空 → bare string。"""
    raw: List = []
    for t in terms:
        term = (t.get("term") or "").strip()
        if not term:
            continue
        variants = [str(v).strip() for v in (t.get("variants") or []) if v and str(v).strip()]
        raw.append({"term": term, "variants": variants} if variants else term)
    return raw


def set_lexicon(style: str, terms: List[dict]) -> Optional[dict]:
    """管理員 bulk 覆寫 terms。回正規化 view；壞 style/冇檔 → None。"""
    with _lock(style):
        data = _read_raw(style)
        if data is None:
            return None
        data = dict(data)
        data["terms"] = _to_raw_terms(_normalize_terms(terms))
        _write(style, data)
        return {"style": style, "terms": _normalize_terms(data["terms"])}


def add_term_variant(style: str, term: str, variant: str) -> Optional[dict]:
    """為 term 追加一個 variant（dedupe）；term 唔存在就新增。回正規化 view。"""
    term = (term or "").strip()
    variant = (variant or "").strip()
    if not term or not variant:
        return get_lexicon(style)
    with _lock(style):
        data = _read_raw(style)
        if data is None:
            return None
        terms = _normalize_terms(data.get("terms"))
        found = next((t for t in terms if t["term"] == term), None)
        if found is None:
            terms.append({"term": term, "variants": [variant]})
        elif variant not in found["variants"]:
            found["variants"].append(variant)
        data = dict(data)
        data["terms"] = _to_raw_terms(terms)
        _write(style, data)
        return {"style": style, "terms": _normalize_terms(data["terms"])}
```

- [ ] **Step 4: 跑 test 確認 pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_lexicon_manager.py -v`
Expected: PASS（5 個）

- [ ] **Step 5: Commit**

```bash
git add backend/lexicon_manager.py backend/tests/test_lexicon_manager.py
git commit -m "feat(lexicon): lexicon_manager 原子讀寫（dual-shape 保留、per-style lock、term/variant CRUD）"
```

---

### Task 2: 行話表 REST（GET view / PUT admin bulk）

**Files:**
- Modify: `backend/app.py`（加兩條 route，放喺 glossary routes 附近，約 :3130）
- Test: `backend/tests/test_lexicon_routes.py`

**Interfaces:**
- Consumes: `lexicon_manager.get_lexicon` / `set_lexicon`；`auth/decorators.admin_required`（:67）。
- Produces:
  - `GET /api/lexicons/<style>` `@login_required` → `{style, terms:[{term,variants}]}`；未知 → 404。
  - `PUT /api/lexicons/<style>` `@admin_required` body `{terms:[{term,variants}]}` → 更新後 view；未知 → 404，壞 body → 400。

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_lexicon_routes.py — 依現有 route test 的 client fixture idiom
import os, sys, json, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_get_lexicon(client):
    r = client.get("/api/lexicons/racing")
    assert r.status_code == 200
    body = r.get_json()
    assert body["style"] == "racing"
    assert isinstance(body["terms"], list)
    assert all("term" in t and "variants" in t for t in body["terms"])


def test_get_unknown_lexicon_404(client):
    assert client.get("/api/lexicons/nope").status_code == 404


def test_put_lexicon_admin_bulk(client):
    # R5_AUTH_BYPASS in conftest → treated as admin
    cur = client.get("/api/lexicons/racing").get_json()["terms"]
    payload = {"terms": cur + [{"term": "後上測試", "variants": ["後尚測試"]}]}
    r = client.put("/api/lexicons/racing", json=payload)
    assert r.status_code == 200
    terms = {t["term"]: t["variants"] for t in r.get_json()["terms"]}
    assert terms.get("後上測試") == ["後尚測試"]
    # 還原（唔污染真檔）
    client.put("/api/lexicons/racing", json={"terms": cur})


def test_put_bad_body_400(client):
    assert client.put("/api/lexicons/racing", json={"terms": "oops"}).status_code == 400
```

> **注意**：conftest 應該有 autouse `R5_AUTH_BYPASS`（同現有 API 測試一致），`admin_required` 會 short-circuit 當 admin。若無 `client` fixture，跟 `test_glossary_api` 或 `test_glossary_review_routes` 嘅 client 建法對齊（record 喺 deviations）。**PUT 測試改真檔要還原**（用 setup/teardown 或測試尾還原，如上）。

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_lexicon_routes.py -v`
Expected: FAIL — 404（route 未存在）

- [ ] **Step 3: 實現（app.py 加 route）**

```python
@app.route('/api/lexicons/<style>', methods=['GET'])
@login_required
def api_get_lexicon(style):
    """系統行話表（phonetic lexicon）view — 登入即可讀。"""
    import lexicon_manager
    view = lexicon_manager.get_lexicon(style)
    if view is None:
        return jsonify({"error": "未知行話表"}), 404
    return jsonify(view)


@app.route('/api/lexicons/<style>', methods=['PUT'])
@admin_required
def api_put_lexicon(style):
    """系統行話表 bulk 覆寫 — 管理員專屬（全局共用資源）。"""
    import lexicon_manager
    data = request.get_json(silent=True) or {}
    terms = data.get("terms")
    if not isinstance(terms, list):
        return jsonify({"error": "terms 必須係 list"}), 400
    for t in terms:
        if not isinstance(t, dict) or not (t.get("term") or "").strip():
            return jsonify({"error": "每個 term 必須有非空 term 字串"}), 400
    view = lexicon_manager.set_lexicon(style, terms)
    if view is None:
        return jsonify({"error": "未知行話表"}), 404
    return jsonify(view)
```

> `admin_required` 由 `from auth.decorators import admin_required`（app.py 頂部應該已 import；若無，加）。確認 import 存在：`grep -n "admin_required" app.py | head -1`。

- [ ] **Step 4: 跑 test + import app smoke**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_lexicon_routes.py -v && ./venv/bin/python -c "import sys; sys.path.insert(0,'.'); import app; print('import app OK')"`
Expected: PASS（4 個）+ `import app OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_lexicon_routes.py
git commit -m "feat(lexicon): GET /api/lexicons/<style>（登入）+ PUT（管理員 bulk）REST"
```

---

### Task 3: 一鍵加別名 endpoint

**Files:**
- Modify: `backend/app.py`（加 route，放喺 `glossary-apply-item` 附近，約 :5440）
- Test: `backend/tests/test_glossary_add_alias.py`

**Interfaces:**
- Consumes: `_glossary_manager`（`get` / `can_edit` / `update_entry`）；`lexicon_manager.add_term_variant`；`output_lang_glossary.strip_horse_id`；`auth.decorators.require_file_owner`。
- Produces: `POST /api/files/<file_id>/glossary-add-alias`
  - body `{kind: 'source'|'target'|'lexicon', variant: str, canonical: str, glossary_id?: str, entry_id?: str, style?: str}`
  - `source` → append `variant` 落 entry `source_variants`；`target` → append 落 `target_aliases`（entry_id 無就靠 canonical 反查）；`lexicon` → `add_term_variant(style, canonical, variant)`（admin）。
  - 回 `{ok: true, kind, field?, count?}`；auth 失敗 403 中文訊息；壞 body 400；entry/glossary 唔存在 404。

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_glossary_add_alias.py — client fixture idiom 同 test_glossary_review_routes
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _mk_glossary(client):
    r = client.post("/api/glossaries", json={"name": "aliastest",
                    "source_lang": "en", "target_lang": "zh"})
    gid = r.get_json()["id"]
    g = client.post(f"/api/glossaries/{gid}/entries",
                    json={"source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)"}).get_json()
    eid = g["entries"][-1]["id"]
    return gid, eid


def _mk_file(client):
    # reuse whatever helper the review-route tests use to seed an output_lang file;
    # here we only need a file_id the caller owns. Align to the existing fixture.
    from conftest_helpers import seed_output_lang_file  # if present; else inline-seed
    return seed_output_lang_file(client)


def test_add_source_variant(client):
    gid, eid = _mk_glossary(client)
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "source", "variant": "Speedy Smarty", "canonical": "SPEEDY SMARTIE",
        "glossary_id": gid, "entry_id": eid})
    assert r.status_code == 200
    assert r.get_json()["field"] == "source_variants"
    g = client.get(f"/api/glossaries/{gid}").get_json()
    e = [x for x in g["entries"] if x["id"] == eid][0]
    assert "Speedy Smarty" in e["source_variants"]


def test_add_target_alias_by_canonical_lookup(client):
    gid, eid = _mk_glossary(client)
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "target", "variant": "伶俐飄駒", "canonical": "伶俐驫駒",
        "glossary_id": gid})   # 無 entry_id → 靠 canonical 反查
    assert r.status_code == 200
    g = client.get(f"/api/glossaries/{gid}").get_json()
    e = [x for x in g["entries"] if x["id"] == eid][0]
    assert "伶俐飄駒" in e["target_aliases"]


def test_add_lexicon_variant(client):
    fid = _mk_file(client)
    cur = client.get("/api/lexicons/racing").get_json()["terms"]
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "lexicon", "variant": "電流位測試", "canonical": "殿後", "style": "racing"})
    assert r.status_code == 200
    terms = {t["term"]: t["variants"] for t in client.get("/api/lexicons/racing").get_json()["terms"]}
    assert "電流位測試" in terms.get("殿後", [])
    client.put("/api/lexicons/racing", json={"terms": cur})   # 還原


def test_bad_kind_400(client):
    fid = _mk_file(client)
    assert client.post(f"/api/files/{fid}/glossary-add-alias",
                       json={"kind": "bogus", "variant": "x", "canonical": "y"}).status_code == 400
```

> **注意**：`_mk_file` 用現有測試 seed output_lang 檔嘅方法對齊（`test_glossary_review_routes.py` 應該有）。若冇現成 helper，inline seed 一個最小 output_lang registry entry（`active_kind='output_lang'`）。record 喺 deviations。

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_glossary_add_alias.py -v`
Expected: FAIL — 404（route 未存在）

- [ ] **Step 3: 實現（app.py 加 route）**

```python
@app.route('/api/files/<file_id>/glossary-add-alias', methods=['POST'])
@require_file_owner
def api_glossary_add_alias(file_id):
    """一鍵把一個「疑似聽錯」寫成永久別名（宣告層）。

    kind='source' → entry.source_variants；'target' → entry.target_aliases
    （entry_id 無就靠 canonical 反查 target）；'lexicon' → 系統行話表（管理員）。
    """
    import lexicon_manager
    from output_lang_glossary import strip_horse_id

    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    variant = (data.get("variant") or "").strip()
    canonical = (data.get("canonical") or "").strip()
    if kind not in ("source", "target", "lexicon") or not variant:
        return jsonify({"error": "壞參數：kind / variant"}), 400

    if kind == "lexicon":
        if not app.config.get("R5_AUTH_BYPASS") and not getattr(current_user, "is_admin", False):
            return jsonify({"error": "系統行話表只有管理員可以修改"}), 403
        if not canonical:
            return jsonify({"error": "lexicon 需要 canonical（行話正名）"}), 400
        style = (data.get("style") or "racing").strip()
        view = lexicon_manager.add_term_variant(style, canonical, variant)
        if view is None:
            return jsonify({"error": "未知行話表"}), 404
        return jsonify({"ok": True, "kind": "lexicon"})

    # kind in (source, target) — glossary entry 寫入
    gid = data.get("glossary_id")
    if not gid or _glossary_manager.get(gid) is None:
        return jsonify({"error": "未知詞彙表"}), 404
    if not app.config.get("R5_AUTH_BYPASS") and not _glossary_manager.can_edit(
            gid, current_user.id, current_user.is_admin):
        return jsonify({"error": "你冇權修改呢個詞彙表（共享表只有管理員可改）"}), 403

    glossary = _glossary_manager.get(gid)
    eid = data.get("entry_id")
    entry = None
    if eid:
        entry = next((e for e in glossary["entries"] if e.get("id") == eid), None)
    if entry is None and canonical:
        # 靠 canonical 反查（粵語 candidate 冇 entry_id）
        entry = next((e for e in glossary["entries"]
                      if strip_horse_id(e.get("target") or "") == canonical), None)
    if entry is None:
        return jsonify({"error": "搵唔到對應詞條"}), 404

    field = "source_variants" if kind == "source" else "target_aliases"
    existing = entry.get(field) or []
    if not isinstance(existing, list):
        existing = [existing]
    if variant in existing:
        return jsonify({"ok": True, "kind": kind, "field": field,
                        "count": len(existing)})   # 已存在 → idempotent
    new_list = list(existing) + [variant]
    try:
        _glossary_manager.update_entry(gid, entry["id"], {field: new_list})
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"ok": True, "kind": kind, "field": field, "count": len(new_list)})
```

- [ ] **Step 4: 跑 test + smoke**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_glossary_add_alias.py -v && ./venv/bin/python -c "import sys; sys.path.insert(0,'.'); import app; print('OK')"`
Expected: PASS（5 個）+ `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_add_alias.py
git commit -m "feat(alias): 一鍵加別名 endpoint（source_variants/target_aliases/lexicon，authz per kind）"
```

---

### Task 4: `glossary-preview` 加「疑似聽錯」suspects

**Files:**
- Modify: `backend/app.py`（`api_glossary_preview` :5212-5285）
- Test: `backend/tests/test_glossary_preview_suspects.py`

**Interfaces:**
- Consumes: `en_correction.build_index` + `judge_candidates`；`phonetic_correction.build_index` + `match_segments` + `load_lexicon`；`strip_horse_id`。
- Produces: 每個 track 嘅 `items` 加 `kind:'suspect'` 項：`{idx, start, kind:'suspect', span, canonical, glossary, glossary_id, entry_id, side, source_index, style}`。`totals` 加 `suspect`。

> **語言 gate（同 Plan A 一致）**：`content_lang=='en'` 先跑 en judge（en track）；`content_lang=='yue'` 先跑 phonetic match（yue/zh/cmn track）。cmn/ja 內容 → 零 suspects。**Cap 每軌 40 項**（超出 print + 截斷），dedupe by `(idx, span, canonical)`，並排除已係 `fix`/`ok` 嘅 `(idx, span)`。

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_glossary_preview_suspects.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# 用一個 helper：直接測 suspect 生成純函數，避免 seed 成個 registry。


def test_en_suspect_generation():
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "MALPENSA", "target": "賢知友您"}],
    }]
    texts = ["It's Malpenza with a wide draw"]
    starts = [1.0]
    sus = app._suspects_for_track("en", texts, starts, glossaries, "en", "racing")
    assert any(s["canonical"] == "MALPENSA" and s["span"].lower().startswith("malpen")
               and s["side"] == "source" and s["entry_id"] == "e1" for s in sus)


def test_zh_suspect_lexicon_side():
    import app
    # 殿後 係 lexicon supplement term；聽錯 "電流位置" 應成 suspect side=lexicon
    texts = ["佢一直電流位置"]
    starts = [1.0]
    sus = app._suspects_for_track("yue", texts, starts, [], "yue", "racing")
    # 只驗 helper 唔炒 + 若有命中 side/source_index 正確
    for s in sus:
        assert s["side"] in ("target", "lexicon")
        if s["source_index"] == "supplement":
            assert s["side"] == "lexicon"


def test_non_yue_non_en_content_no_suspects():
    import app
    assert app._suspects_for_track("ja", ["x"], [1.0], [], "ja", "generic") == []
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_glossary_preview_suspects.py -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_suspects_for_track'`

- [ ] **Step 3: 實現（app.py 加 helper + 掛入 preview loop）**

喺 `api_glossary_preview` 上面加 module-level helper：

```python
_SUSPECT_CAP = 40   # 每軌上限（超出 print + 截斷，唔靜默）


def _suspects_for_track(lang, texts, starts, glossaries, content_lang, mt_style):
    """確定性疑似聽錯 candidate（零 LLM）。en track（content en）用 judge_candidates，
    yue/zh/cmn track（content yue）用 phonetic match_segments。回 suspect item list。"""
    from output_lang_glossary import strip_horse_id
    out = []
    segs = [{"start": 0, "end": 1, "text": t or ""} for t in texts]

    if lang == "en" and content_lang == "en":
        from en_correction import build_index as _en_build, judge_candidates
        cands = judge_candidates(segs, _en_build(glossaries))
        for c in cands:
            i = c["idx"]
            out.append({"idx": i, "start": starts[i] if i < len(starts) else None,
                        "kind": "suspect", "span": c["span"], "canonical": c["source"],
                        "glossary": c.get("glossary", ""), "glossary_id": c.get("glossary_id"),
                        "entry_id": c.get("entry_id"), "side": "source",
                        "source_index": "glossary", "style": mt_style})
    elif lang in ("yue", "zh", "cmn") and content_lang == "yue":
        from phonetic_correction import (build_index as _pc_build, match_segments,
                                         load_lexicon)
        index = _pc_build(glossaries, load_lexicon(mt_style))
        cands, _ = match_segments(segs, index)
        # canonical → (entry_id, glossary_id, glossary_name) 反查（glossary source_index）
        by_target = {}
        for g in glossaries:
            for e in g.get("entries", []):
                key = strip_horse_id(e.get("target") or "")
                if key and key not in by_target:
                    by_target[key] = (e.get("id"), g.get("id"), g.get("name", ""))
        for c in cands:
            i = c["seg_idx"]
            canonical = c["glossary_name"]
            si = c.get("source_index", "glossary")
            if si == "supplement":
                side, eid, gid, gname = "lexicon", None, None, ""
            else:
                eid, gid, gname = by_target.get(canonical, (None, None, ""))
                side = "target"
            out.append({"idx": i, "start": starts[i] if i < len(starts) else None,
                        "kind": "suspect", "span": c["span"], "canonical": canonical,
                        "glossary": gname, "glossary_id": gid, "entry_id": eid,
                        "side": side, "source_index": si, "style": mt_style})

    # dedupe by (idx, span, canonical) + cap
    seen, deduped = set(), []
    for s in out:
        k = (s["idx"], s["span"], s["canonical"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(s)
    if len(deduped) > _SUSPECT_CAP:
        print(f"[glossary-preview] {lang} suspects {len(deduped)} 超上限 {_SUSPECT_CAP}，截斷",
              flush=True)
        deduped = deduped[:_SUSPECT_CAP]
    return deduped
```

改 `api_glossary_preview` snapshot（:5243 附近）加 `mt_style`：

```python
        source_language = entry.get("source_language") or "yue"
        mt_style = entry.get("mt_style") or "generic"
```

改 per-track loop（:5273-5278），喺 `tracks.append(trk)` 之前加：

```python
        # 疑似聽錯（確定性，零 LLM）— add-only kind:'suspect'。
        existing = {(it["idx"], it.get("alias") or it.get("canonical"))
                    for it in trk["items"]}
        for s in _suspects_for_track(lang, texts, [r.get("start") for r in rows],
                                     glossaries, content_lang, mt_style):
            if (s["idx"], s["span"]) in existing:
                continue
            trk["items"].append(s)
```

改 `totals`（:5280-5284）加 suspect：

```python
    totals = {
        "fix": sum(1 for t in tracks for i in t["items"] if i["kind"] == "fix"),
        "ok": sum(1 for t in tracks for i in t["items"] if i["kind"] == "ok"),
        "suspect": sum(1 for t in tracks for i in t["items"] if i["kind"] == "suspect"),
        "rows": len(rows),
    }
```

- [ ] **Step 4: 跑 test + smoke**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_glossary_preview_suspects.py -v && ./venv/bin/python -c "import sys; sys.path.insert(0,'.'); import app; print('OK')"`
Expected: PASS（3 個）+ `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_preview_suspects.py
git commit -m "feat(preview): glossary-preview 加疑似聽錯 suspects（en judge / yue phonetic，零 LLM，add-only）"
```

---

### Task 5: Glossary.html — 近音寫法（source_variants）chip 列

**Files:**
- Modify: `frontend/Glossary.html`（`renderDetail` :959-1006、`saveEntryField` :1025-1026、`filteredEntries` :898-912、`renderTable` :928-935）

- [ ] **Step 1: renderDetail 加 source_variants 欄（原文之下）**

`:958` 之後加 variants read：

```javascript
    const aliases = Array.isArray(entry.target_aliases) ? entry.target_aliases : [];
    const variants = Array.isArray(entry.source_variants) ? entry.source_variants : [];
```

`body.innerHTML` template：喺 原文 `.gl-field`（:960-963 收 `</div>` 於 963）同 譯文 `.gl-field`（:964 開）之間，插入：

```html
      <div class="gl-field">
        <label>近音寫法 (原文別名)</label>
        <div class="gl-chips" id="dVariants">
          ${variants.map((v, i) => `<span class="gl-chip">${escapeHtml(v)}<button data-idx="${i}" title="移除">×</button></span>`).join('')}
          <button class="gl-chip-add" id="dVariantAdd">+ 加入</button>
        </div>
      </div>
```

- [ ] **Step 2: renderDetail 加 variant chip handlers**（仿 alias handlers :987-1006，用同一個 `_aliasSaveBusy` flag 串行化）

喺 alias add handler（:1006 收）之後加：

```javascript
    document.querySelectorAll('#dVariants .gl-chip button').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (_aliasSaveBusy) return;
        _aliasSaveBusy = true;
        try {
          const idx = parseInt(btn.dataset.idx, 10);
          const next = variants.slice(); next.splice(idx, 1);
          await saveEntryField('source_variants', next);
        } finally { _aliasSaveBusy = false; }
      });
    });
    document.getElementById('dVariantAdd').addEventListener('click', async () => {
      if (_aliasSaveBusy) return;
      const v = prompt('加入近音寫法（原文聽錯/拼錯形式）：');
      if (!v || !v.trim()) return;
      _aliasSaveBusy = true;
      try {
        await saveEntryField('source_variants', [...variants, v.trim()]);
      } finally { _aliasSaveBusy = false; }
    });
```

- [ ] **Step 3: saveEntryField re-render 分支加 source_variants**

`:1025` `if (field === 'target_aliases')` 改成：

```javascript
        if (field === 'target_aliases' || field === 'source_variants') {
          renderDetail();
```

- [ ] **Step 4: filteredEntries 搜尋 + renderTable badge**

`filteredEntries`（:902-906）搜尋 predicate 加 `source_variants`：

```javascript
      || (Array.isArray(e.source_variants) && e.source_variants.some(v => (v || '').toLowerCase().includes(q)))
```

`renderTable` 行 template（:930-932 `.gl-td-source`）喺 source span 之下加別名 badge（用死 CSS `.gl-alt`）：

```javascript
        `<div class="gl-td-source"><span>${escapeHtml(e.source)}</span>${
          (Array.isArray(e.source_variants) && e.source_variants.length)
            ? `<span class="gl-alt">近音 ${e.source_variants.length}</span>` : ''
        }</div>`
```

- [ ] **Step 5: 手動驗證（前端無 test；hard-refresh 校對 chip 行為）**

啟動/沿用 :5001，開 `/Glossary.html`，揀一條 en→zh 詞條 → 見到「近音寫法」chip 列喺原文下 → +加入「Speedy Smarty」→ toast「已儲存」→ 重新載入仍在 → 表格該行顯示「近音 1」badge。GET 該 glossary 確認 `source_variants` 已存。

- [ ] **Step 6: Commit**

```bash
git add frontend/Glossary.html
git commit -m "feat(glossary-ui): 詞條詳情加近音寫法 (source_variants) chip 列 + 表格別名 badge + 搜尋"
```

---

### Task 6: Glossary.html — 系統行話表 admin UI

**Files:**
- Modify: `frontend/Glossary.html`（`/api/me` boot :700-709 存 isAdmin；加一個 admin-only「系統行話表」入口 + modal + JS）

- [ ] **Step 1: 存 isAdmin 落 state**

`/api/me` boot（:700-709），喺 `u.is_admin` 分支加 `state.isAdmin = !!u.is_admin;`（`state` 物件 :732-740 加 `isAdmin: false` 預設）。

- [ ] **Step 2: 加 admin-only 入口掣**（table-head toolbar，仿 `#glBracketsWrap` :632-639 pattern，`display:none` 預設）

喺 toolbar 加 `<button id="lexAdminBtn" style="display:none;">系統行話表</button>`；boot 完 `if (state.isAdmin) lexAdminBtn.style.display='';`。

- [ ] **Step 3: 加 modal + JS**（GET `/api/lexicons/racing` render 一個 term/variants 編輯清單；PUT 儲存；仿 saveEntryField 的 apiJson + toast + 403 alert）

```javascript
async function openLexAdmin() {
  const style = 'racing';
  let view;
  try { view = await apiJson('GET', `/api/lexicons/${style}`); }
  catch (e) { toast(`載入失敗: ${e.message}`, 'error'); return; }
  // render view.terms 做可編輯清單（每 term 一行 + variants chip；空 variants 都顯示）
  // 「儲存」→ PUT /api/lexicons/<style> {terms}；403 → alert「需要管理員」
  _renderLexModal(style, view.terms);
  document.getElementById('lexOverlay').classList.add('open');
}
async function saveLex(style, terms) {
  try {
    await apiJson('PUT', `/api/lexicons/${style}`, { terms });
    toast('行話表已儲存', 'success');
  } catch (e) {
    if (/HTTP 403/.test(e.message)) alert('你唔係管理員，無權修改系統行話表');
    else toast(`儲存失敗: ${e.message}`, 'error');
  }
}
```

> modal DOM（`#lexOverlay` / `#lexBody` / 儲存掣 / 關閉）仿現有 modal markup（e.g. glossary review modal 或 name_brackets）。每 term 一行：term 名（唯讀或可改）+ variants chip（+加入/×移除，收集成 `{term, variants}` array）。「儲存」收集全部 terms → `saveLex`。

- [ ] **Step 4: 手動驗證**

admin 帳戶開 `/Glossary.html` → 見「系統行話表」掣（非 admin 見唔到）→ 開 modal → 為「殿後」加 variant「電流位置」→ 儲存 toast → 重開仍在 → `GET /api/lexicons/racing` 確認。非 admin PUT → 403 → alert。

- [ ] **Step 5: Commit**

```bash
git add frontend/Glossary.html
git commit -m "feat(glossary-ui): 系統行話表 admin 編輯 modal（GET/PUT lexicons，isAdmin gate）"
```

---

### Task 7: 校對頁掃描 modal — 「疑似聽錯」分節 + 一鍵加別名

**Files:**
- Modify: `frontend/js/glossary-review.js`（`_renderModal` :106-141 加第三節；加 suspect row + 一鍵 handler）
- Modify: `frontend/proofread.html`（`.ga-*` CSS 補 suspect 樣式，若需要）

**Interfaces:**
- Consumes: `POST /api/files/<id>/glossary-add-alias`（Task 3）。preview `items` 已含 `kind:'suspect'`（Task 4）。

- [ ] **Step 1: `_renderModal` 加 suspect section**

`:111-112` fixes/oks 之後加：

```javascript
      const suspects = t.items ? t.items.filter(it => it.kind === 'suspect') : [];
```

`:117-128` fixRows/okRows 之後加 suspectRows：

```javascript
      const suspectRows = suspects.length
        ? `<div class="ga-section-head ga-section-head-suspect">疑似聽錯 (${suspects.length}) — 一鍵加為近音別名</div>`
          + suspects.map((it, si) => _suspectRowHtml(t, ti, si, it)).join('')
        : '';
```

`:139` track template 由 `${inapp}${emptyMsg}${fixRows}${okRows}` 改成 `...${fixRows}${okRows}${suspectRows}`。`emptyMsg` 條件（:130）加 `&& !suspects.length`。header count（:137）加 `· ${suspects.length} 疑似`。

- [ ] **Step 2: 加 `_suspectRowHtml` + 一鍵 handler**

```javascript
  function _suspectRowHtml(t, ti, si, it) {
    const rowText = _rowTextFor(t.lang, it.idx);
    const where = it.side === 'lexicon' ? '系統行話表'
                : it.side === 'source' ? '原文近音' : '譯文別名';
    return `<div class="ga-row suspect" data-ti="${ti}" data-si="${si}">
      <div class="ga-row-body">
        <div class="ga-row-term">
          <span class="susp-span">${escapeHtml(it.span)}</span> ≈ ${escapeHtml(it.canonical)}
          <span class="gl-src-tag">${escapeHtml(it.glossary || where)}</span>
          <span class="seg-link" onclick="_grJumpSeg(${it.idx})">#${it.idx + 1} ${_fmtTc(it.start)}</span>
          <button class="susp-add" data-ti="${ti}" data-si="${si}">＋ 加為近音別名</button>
          <span class="gr-state"></span>
        </div>
        <div class="ga-row-line">字幕：${_hl(rowText, it.span)}</div>
        <div class="ga-row-line ga-hint">確定性掃描 · 加咗別名之後「全部重新生成」即生效（${escapeHtml(where)}）</div>
      </div>
    </div>`;
  }
```

wire（`_wireFooter` 或 `_renderModal` 尾）— event delegation 喺 `#grBody`：

```javascript
  function _wireSuspectAdds() {
    document.querySelectorAll('#grBody .susp-add').forEach(btn => {
      if (btn._wired) return; btn._wired = true;
      btn.addEventListener('click', async () => {
        const ti = parseInt(btn.dataset.ti, 10), si = parseInt(btn.dataset.si, 10);
        const t = scanData.tracks[ti];
        const it = (t.items || []).filter(x => x.kind === 'suspect')[si];
        if (!it) return;
        const st = btn.parentElement.querySelector('.gr-state');
        btn.disabled = true; if (st) st.textContent = '…';
        try {
          const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-add-alias`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              kind: it.side === 'source' ? 'source' : (it.side === 'lexicon' ? 'lexicon' : 'target'),
              variant: it.span, canonical: it.canonical,
              glossary_id: it.glossary_id || null, entry_id: it.entry_id || null,
              style: it.style || 'racing',
            }),
          });
          const body = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
          if (st) { st.textContent = '✓ 已加'; st.className = 'gr-state ok'; }
          btn.textContent = '已加入';
        } catch (e) {
          btn.disabled = false;
          if (st) { st.textContent = `✗ ${e.message}`; st.className = 'gr-state err'; }
        }
      });
    });
  }
```

喺 `_renderModal` 尾（`_wireFooter(); _updateCount();` 之後）call `_wireSuspectAdds();`。

- [ ] **Step 3: CSS**（proofread.html `.ga-*` 區加）

```css
.ga-section-head-suspect { color: var(--warning, #f9e2af); }
.ga-row.suspect .susp-span { text-decoration: underline dotted; }
.susp-add { margin-left: 8px; font-size: 11px; cursor: pointer; }
```

- [ ] **Step 4: 手動驗證（真檔 E2E）**

開一個 en 源或 yue 源 output_lang 檔嘅校對頁 → 「🔍 掃描詞彙表」→ 見到「疑似聽錯」分節列出 fuzzy 命中（例 en 檔 `Malpenza ≈ MALPENSA`）→ 㩒「＋ 加為近音別名」→ ✓ 已加 → `GET` 該 glossary 確認 `source_variants` 有「Malpenza」→「全部重新生成」後該 cue 變正名。

- [ ] **Step 5: Commit**

```bash
git add frontend/js/glossary-review.js frontend/proofread.html
git commit -m "feat(proofread): 掃描 modal 疑似聽錯分節 + 一鍵加為近音別名（source/target/lexicon）"
```

---

### Task 8: 整合驗證（真檔 E2E gate）

**Files:**
- Create: `backend/scripts/aliasui_verify.py`（read/write endpoint round-trip，跑真 registry 檔）
- Modify: `docs/superpowers/specs/2026-07-14-glossary-alias-validation-tracker.md`（append Plan B 驗證節）

> 目標：證明閉環真係 round-trip（preview 見到疑似聽錯 → add-alias 寫入 → 別名確實落 glossary/lexicon）。零 LLM（掃描層本身零 LLM；「全部重新生成」生效已由 Plan A Task 8 覆蓋，此處只驗寫入鏈）。

- [ ] **Step 1: 寫 verify script（用 Flask test client，唔掂 live server）**

```python
# backend/scripts/aliasui_verify.py
"""Plan B 閉環 round-trip 驗證 — Flask test client，零 LLM。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("R5_AUTH_BYPASS", "1")
os.environ.setdefault("R5_LICENSE_BYPASS", "1")
import app as appmod

app = appmod.app
c = app.test_client()

# 1) suspect 生成（helper 直測，真 glossary db323f9d 上一個已知聽錯）
glossaries = [__import__("json").load(open(os.path.join(
    os.path.dirname(__file__), "..", "config", "glossaries",
    "db323f9d-8f1e-44da-a20f-64d1ace09b89.json"), encoding="utf-8"))]
sus = appmod._suspects_for_track("en", ["It's Malpenza with a wide draw"], [1.0],
                                 glossaries, "en", "racing")
print("GATE1 en suspect 生成:", any(s["canonical"] == "MALPENSA" for s in sus))

# 2) lexicon add round-trip
before = c.get("/api/lexicons/racing").get_json()["terms"]
# 直接 add_term_variant（route 需要 file — 用 manager 直測寫入鏈）
import lexicon_manager
lexicon_manager.add_term_variant("racing", "殿後", "電流位驗證")
after = {t["term"]: t["variants"] for t in c.get("/api/lexicons/racing").get_json()["terms"]}
print("GATE2 lexicon 寫入 round-trip:", "電流位驗證" in after.get("殿後", []))
lexicon_manager.set_lexicon("racing", [{"term": t["term"],
    "variants": [v for v in t["variants"] if v != "電流位驗證"]} for t in
    [{"term": k, "variants": v} for k, v in after.items()]])  # 還原

print("\nALL PASS:", any(s["canonical"] == "MALPENSA" for s in sus) and "電流位驗證" in after.get("殿後", []))
```

- [ ] **Step 2: 跑 verify**

Run: `cd backend && ./venv/bin/python scripts/aliasui_verify.py`
Expected: `GATE1 en suspect 生成: True` / `GATE2 lexicon 寫入 round-trip: True` / `ALL PASS: True`

- [ ] **Step 3: 跑晒新增/改到嘅 test file（隔離）**

Run: `cd backend && for f in test_lexicon_manager test_lexicon_routes test_glossary_add_alias test_glossary_preview_suspects; do ./venv/bin/python -m pytest tests/$f.py -q; done`
Expected: 全 PASS

- [ ] **Step 4: 記錄落 tracker + commit**

tracker 加「## Plan B 閉環驗證（2026-07-15）」記 GATE1/GATE2 + verify script 路徑。

```bash
git add backend/scripts/aliasui_verify.py docs/superpowers/specs/2026-07-14-glossary-alias-validation-tracker.md
git commit -m "test(alias-ui): Plan B 閉環 round-trip 驗證（suspect 生成 + lexicon 寫入）"
```

---

### Task 9: 文檔更新

**Files:**
- Modify: `CLAUDE.md`（REST 表加 4 條 endpoint + Current State 補閉環）、`README.md`（繁中操作）、`docs/PRD.md`

- [ ] **Step 1: CLAUDE.md REST 表加**

```markdown
| GET | `/api/lexicons/<style>` | 系統行話表 view（登入即可讀）|
| PUT | `/api/lexicons/<style>` | 系統行話表 bulk 覆寫（管理員專屬）|
| POST | `/api/files/<id>/glossary-add-alias` | 一鍵把疑似聽錯寫成永久別名（source_variants/target_aliases/lexicon variants；authz per kind）|
```

`glossary-preview` 行補：`items` 加 `kind:'suspect'`（疑似聽錯，確定性零 LLM）；`totals` 加 `suspect`。Current State「術語表宣告別名」節補一句閉環已通（Glossary.html 近音 chip + 系統行話表 admin + 校對頁一鍵回饋）。**Plan C（自動學）仍待做。**

- [ ] **Step 2: README.md 繁中操作段** — 點喺術語表填近音別名、校對頁一鍵回饋、系統行話表（管理員）、加咗之後要「全部重新生成」先對舊檔生效。

- [ ] **Step 3: PRD.md 標記閉環完成。**

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/PRD.md
git commit -m "docs(alias): 近音別名閉環 + 系統行話表（CLAUDE.md REST + README + PRD）"
```

---

## Self-Review

**Spec coverage（design §5 + §3.2）：**
- §5.1 術語表頁近音 chip + 表格 badge → Task 5 ✅
- §5.2 校對頁一鍵回饋（疑似聽錯分節 + 一鍵）→ Task 4（backend suspects）+ Task 7（frontend）✅
- §5.3 自動學 → **Plan C**（scope note 已標）
- §3.2 行話表 variants + 管理員可改 → Task 1（manager）+ Task 2（REST）+ Task 6（UI）✅
- 一鍵寫入三路（source/target/lexicon）→ Task 3 ✅
- 粵語 attribution（canonical 反查 / lexicon 路由）→ Task 3 + Task 4 ✅

**Placeholder scan：** 無 TBD。Frontend task（5-7）用「exact 行號 anchor + 完整 markup/handler code」，modal DOM 講明「仿現有 pattern」係對齊指示（現有 modal 結構已由 research map 確認存在），非 placeholder。Task 3/8 的 `_mk_file`/seed 對齊現有 fixture — 已標明 record 落 deviations。

**Type consistency：** suspect item shape `{idx,start,kind:'suspect',span,canonical,glossary,glossary_id,entry_id,side,source_index,style}` — Task 4 產生、Task 7 消費、Task 3 一鍵消費（kind ← side 映射：source→source / lexicon→lexicon / else→target），三處一致。`add-alias` body `{kind,variant,canonical,glossary_id,entry_id,style}` — Task 3 定義、Task 7 送、Task 8 驗，一致。`get_lexicon` view `{style,terms:[{term,variants}]}` — Task 1 產、Task 2/6 消費，一致。

---

## Execution Handoff

Plan B 完成後：Task 1-7 全 test/手動驗證 PASS + Task 8 gate GATE1/GATE2 PASS + Task 9 docs。之後可選 Plan C（自動學）。
