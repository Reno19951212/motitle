# 校對頁 AI 輔助修改（per-segment AI edit）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校對頁右側 detail panel 每個語言欄加「✦ AI」掣，popup 收用戶指令（自由輸入 + 4 個快速 chips），後端 LLM 出修改建議，預覽後經現有 PATCH 套用。

**Architecture:** 方案 A — suggest-only endpoint（`POST /api/files/<id>/ai-edit`，唔寫 registry）+ 前端經現有 `PATCH /translations/<idx>` 套用；順手修 PATCH 唔同步 `aligned_bilingual` 嘅現有 bug。Prompt 構建/解析隔離喺新 pure module `backend/ai_edit.py`。

**Tech Stack:** Flask + `_make_ollama_llm_call()`（Ollama qwen3.5:35b-a3b @0.3，Beta 模式自動行 OpenRouter）；vanilla JS（proofread.html）；pytest（mock LLM factory）；Playwright E2E。

**Spec:** `docs/superpowers/specs/2026-06-10-proofread-ai-edit-design.md`（已批准；UI mockup 已確認 — `.superpowers/brainstorm/89682-1781070476/content/ai-edit-preview.html` 係視覺基準）

**事實基準（讀 code 確認過，唔好估）：**
- LLM callable：`_make_ollama_llm_call()` 回 `(system, user) -> str`，temp 0.3 已綁死；HTTP 錯/超時 raise `ConnectionError`（app.py:362-377）
- output_lang `translations[pos]` 行：`{idx, start, end, status, by_lang: {lang: {text, status, flags}}, "<lang>_text": mirror, glossary_changes}`；`entry["output_languages"]` = `[first_lang, second_lang?]`；`entry["languages"]` = `[{role, label, lang}]`
- `aligned_bilingual[pos]` = `{start, end, by_lang: {lang: "純字串"}}`（值係字串唔係 dict！）
- PATCH 函數 `api_update_translation` 喺 app.py:3491-3596；output_lang branch 設定 `write_field`/`do_by_lang_write`/`by_lang_key`，寫 `updated` dict 後完全冇掂 `aligned_bilingual`
- 測試 pattern：`tests/test_segment_split_routes.py` — client fixture（R5_AUTH_BYPASS）+ `_seed_output_lang_file` 直插 `appmod._file_registry` + `monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: fake)` + `_save_registry` no-op。conftest autouse fixture 已自動 bypass auth+license
- 跑測試：`cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py -v`（全套有 order-dependent 污染 — **單獨跑呢個檔**）
- frontend `segs[cursorIdx]`：`.idx`（後端 translation idx）、`.en`（第一語言文字）、`.zh`（第二）、`._hasSecond`、`.cps`、`._cpsSecond`；`fileInfo.active_kind`、`_outputLangLabel(role)`（proofread.html:2429）；toast = `showToast(msg, kind)`；seg list 重繪 = `renderSegList()`（3116）+ `renderDetail()`（2436）

---

### Task 1: `backend/ai_edit.py` pure module（prompt 構建 + 回應解析）

**Files:**
- Create: `backend/ai_edit.py`
- Test: `backend/tests/test_ai_edit.py`

- [ ] **Step 1: 寫 failing unit tests**

`backend/tests/test_ai_edit.py`（新檔，先得 unit test 部分）:

```python
# backend/tests/test_ai_edit.py
import pytest

import ai_edit


# ---------- parse_response ----------

def test_parse_plain_json():
    assert ai_edit.parse_response('{"text": "無人比我更傷感。"}') == "無人比我更傷感。"

def test_parse_strips_think_tags_and_fences():
    raw = '<think>用戶想精簡</think>\n```json\n{"text": "無人比我更傷感。"}\n```'
    assert ai_edit.parse_response(raw) == "無人比我更傷感。"

def test_parse_accepts_bare_text():
    assert ai_edit.parse_response("無人比我更傷感。") == "無人比我更傷感。"

def test_parse_collapses_newlines():
    assert ai_edit.parse_response('{"text": "上半\n下半"}') == "上半 下半"

def test_parse_rejects_empty_and_garbage():
    assert ai_edit.parse_response("") is None
    assert ai_edit.parse_response(None) is None
    assert ai_edit.parse_response('{"text": ""}') is None
    assert ai_edit.parse_response('{"wrong_key": "x"}') is None

def test_parse_rejects_overlong():
    assert ai_edit.parse_response('{"text": "' + "字" * 201 + '"}') is None

def test_parse_json_rescue_from_trailing_prose():
    raw = '{"text": "好句子。"} 以上係修改後字幕'
    assert ai_edit.parse_response(raw) == "好句子。"


# ---------- prompts ----------

def test_system_prompt_contains_rules_and_label():
    sp = ai_edit.build_system_prompt("中文書面語")
    assert "中文書面語" in sp
    assert '{"text"' in sp           # 輸出格式
    assert "專有名詞" in sp           # byte-preserve 規則

def test_user_prompt_includes_other_lang_reference():
    up = ai_edit.build_user_prompt("中文書面語", "我想沒有人比我更傷感了。",
                                   "英文", "I don't think anyone...", "精簡呢句")
    assert "我想沒有人比我更傷感了。" in up
    assert "I don't think anyone..." in up
    assert "精簡呢句" in up

def test_user_prompt_omits_empty_other_lang():
    up = ai_edit.build_user_prompt("口語廣東話", "你好", "", "", "改更口語")
    assert "另一語言參考" not in up
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_edit'`

- [ ] **Step 3: 實現 `backend/ai_edit.py`**

```python
"""AI 輔助修改（proofread per-segment AI edit）— pure prompt/parse logic.

No I/O, no Flask, no registry access — the route in app.py owns those.
Spec: docs/superpowers/specs/2026-06-10-proofread-ai-edit-design.md
"""
import json
import re
from typing import Optional

MAX_INSTRUCTION_CHARS = 500
MAX_OUTPUT_CHARS = 200

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TEXT_KEY_RE = re.compile(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"')


def build_system_prompt(target_label: str) -> str:
    return (
        "你係廣播字幕編輯助手。用戶會俾你一段字幕同一個修改指令，你按指令修改字幕。\n"
        "規則：\n"
        f"1. 只修改「{target_label}」欄嘅字幕；輸出必須維持同原字幕一致嘅語言同書寫系統（繁／簡），"
        "唔好轉做第二種語言（除非指令明確要求翻譯）。\n"
        "2. 保留專有名詞、人名、地名、數字、英文原樣，除非指令明確要求修改。\n"
        "3. 字幕要簡潔自然、適合廣播畫面閱讀；唔好加入原文冇嘅資訊。\n"
        '4. 只輸出 JSON，格式：{"text": "修改後字幕"}。唔好有 markdown、唔好有解釋、唔好有思考標籤。'
    )


def build_user_prompt(target_label: str, target_text: str,
                      other_label: str, other_text: str, instruction: str) -> str:
    payload = {
        "目標欄": target_label,
        "現有字幕": target_text,
        "用戶指令": instruction,
    }
    if (other_text or "").strip():
        payload["另一語言參考"] = {other_label or "另一語言": other_text}
    return json.dumps(payload, ensure_ascii=False)


def parse_response(raw) -> Optional[str]:
    """Lenient LLM-output parse → cleaned subtitle text, or None on any failure."""
    if not isinstance(raw, str):
        return None
    txt = _THINK_RE.sub("", raw).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```\s*$", "", txt).strip()
    if txt.startswith("{"):
        try:
            obj = json.loads(txt)
            txt = obj.get("text", "")
        except ValueError:
            m = _TEXT_KEY_RE.search(txt)
            if not m:
                return None
            try:
                txt = json.loads('"' + m.group(1) + '"')
            except ValueError:
                return None
    if not isinstance(txt, str):
        return None
    txt = " ".join(txt.split())  # collapse 換行/連續空白
    if not txt or len(txt) > MAX_OUTPUT_CHARS:
        return None
    return txt
```

注意 `test_parse_json_rescue_from_trailing_prose`：`{"text": "好句子。"} 以上係…` 唔係合法 JSON（trailing prose）→ `json.loads` 爆 `ValueError` → `_TEXT_KEY_RE` rescue 路徑。

- [ ] **Step 4: 跑測試確認 pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/ai_edit.py backend/tests/test_ai_edit.py
git commit -m "feat(ai-edit): pure prompt/parse module for proofread AI edit"
```

---

### Task 2: Route `POST /api/files/<file_id>/ai-edit`（suggest-only）

**Files:**
- Modify: `backend/app.py`（import 一行 + route 一個，放喺 `merge_next_segment` 之後 ~app.py:5494）
- Test: `backend/tests/test_ai_edit.py`（追加 route tests）

- [ ] **Step 1: 追加 failing route tests 落 `backend/tests/test_ai_edit.py`**

```python
# ---------- route POST /api/files/<id>/ai-edit ----------
pytest.importorskip("flask")
import copy

import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True
    appmod.app.config["LOGIN_DISABLED"] = True
    with appmod.app.test_client() as c:
        yield c
    appmod.app.config.pop("R5_AUTH_BYPASS", None)
    appmod.app.config.pop("LOGIN_DISABLED", None)


def _seed_bilingual_file(fid="f-aiedit"):
    base = [
        {"start": 0.0, "end": 4.0, "text": "我想沒有人比我更傷感了。"},
        {"start": 4.0, "end": 7.0, "text": "多謝大家。"},
    ]
    trans = [
        {"idx": 0, "start": 0.0, "end": 4.0, "status": "pending",
         "by_lang": {"zh": {"text": "我想沒有人比我更傷感了。", "status": "pending", "flags": []},
                     "en": {"text": "I don't think anyone will hurt their feelings more than I do.",
                            "status": "pending", "flags": []}},
         "zh_text": "我想沒有人比我更傷感了。",
         "en_text": "I don't think anyone will hurt their feelings more than I do.",
         "glossary_changes": []},
        {"idx": 1, "start": 4.0, "end": 7.0, "status": "pending",
         "by_lang": {"zh": {"text": "多謝大家。", "status": "pending", "flags": []},
                     "en": {"text": "Thank you all.", "status": "pending", "flags": []}},
         "zh_text": "多謝大家。", "en_text": "Thank you all.",
         "glossary_changes": []},
    ]
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "status": "done", "active_kind": "output_lang", "source_language": "cmn",
            "output_languages": ["zh", "en"], "user_id": "u1",
            "languages": [{"role": "first", "label": "中文書面語", "lang": "zh"},
                          {"role": "second", "label": "英文", "lang": "en"}],
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": [copy.deepcopy(t) for t in trans],
            "aligned_bilingual": [
                {"start": 0.0, "end": 4.0,
                 "by_lang": {"zh": "我想沒有人比我更傷感了。",
                             "en": "I don't think anyone will hurt their feelings more than I do."}},
                {"start": 4.0, "end": 7.0,
                 "by_lang": {"zh": "多謝大家。", "en": "Thank you all."}},
            ],
        }
    return fid


def test_ai_edit_happy_path_does_not_mutate_registry(client, monkeypatch):
    fid = _seed_bilingual_file()
    captured = {}

    def fake_factory():
        def call(system, user):
            captured["system"] = system
            captured["user"] = user
            return '{"text": "無人比我更傷感。"}'
        return call

    monkeypatch.setattr(appmod, "_make_ollama_llm_call", fake_factory)
    with appmod._registry_lock:
        before = copy.deepcopy(appmod._file_registry[fid])

    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "精簡呢句"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["text"] == "無人比我更傷感。"
    assert data["source_text"] == "我想沒有人比我更傷感了。"
    assert data["role"] == "first" and data["pos"] == 0
    # 指令 + 兩個語言文字都入咗 prompt
    assert "精簡呢句" in captured["user"]
    assert "I don't think anyone" in captured["user"]      # 另一語言參考
    assert "中文書面語" in captured["system"]
    # suggest-only：registry 一定唔可以變
    with appmod._registry_lock:
        assert appmod._file_registry[fid] == before


def test_ai_edit_second_role_targets_en(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-2")
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "Thanks, everyone."}'))
    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 1, "role": "second", "instruction": "改更口語"})
    assert r.status_code == 200
    assert r.get_json()["source_text"] == "Thank you all."


def test_ai_edit_llm_connection_error_502(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-3")

    def boom_factory():
        def call(system, user):
            raise ConnectionError("ollama down")
        return call

    monkeypatch.setattr(appmod, "_make_ollama_llm_call", boom_factory)
    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "x"})
    assert r.status_code == 502
    assert "error" in r.get_json()


def test_ai_edit_garbage_output_422(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-4")
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: "<think>嗯</think>"))
    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "x"})
    assert r.status_code == 422


def test_ai_edit_validation_400s(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-5")
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "ok"}'))
    # 指令空
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 0, "role": "first", "instruction": "  "}).status_code == 400
    # 指令超長
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 0, "role": "first", "instruction": "字" * 501}).status_code == 400
    # 壞 role
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 0, "role": "third", "instruction": "x"}).status_code == 400
    # pos 越界
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 99, "role": "first", "instruction": "x"}).status_code == 404
    # pos 唔係 int
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": "0", "role": "first", "instruction": "x"}).status_code == 400


def test_ai_edit_rejects_non_output_lang(client, monkeypatch):
    with appmod._registry_lock:
        appmod._file_registry["f-profile"] = {
            "status": "done", "active_kind": "profile", "user_id": "u1",
            "translations": [{"idx": 0, "zh_text": "你好", "en_text": "hi", "status": "pending"}],
        }
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "ok"}'))
    r = client.post("/api/files/f-profile/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "x"})
    assert r.status_code == 400


def test_ai_edit_second_role_single_lang_400(client, monkeypatch):
    # 單語言 output_lang 檔 — role=second 應 400
    base = [{"start": 0.0, "end": 2.0, "text": "你好"}]
    with appmod._registry_lock:
        appmod._file_registry["f-single"] = {
            "status": "done", "active_kind": "output_lang", "user_id": "u1",
            "output_languages": ["yue"],
            "languages": [{"role": "first", "label": "口語廣東話", "lang": "yue"}],
            "segments": [dict(s) for s in base],
            "translations": [{"idx": 0, "start": 0.0, "end": 2.0, "status": "pending",
                              "by_lang": {"yue": {"text": "你好", "status": "pending", "flags": []}},
                              "yue_text": "你好", "glossary_changes": []}],
        }
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "ok"}'))
    r = client.post("/api/files/f-single/ai-edit",
                    json={"pos": 0, "role": "second", "instruction": "x"})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑測試確認新 tests fail（404 — route 未存在）**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py -v`
Expected: unit tests pass；route tests FAIL（`assert 404 == 200` 之類）

- [ ] **Step 3: 實現 route**

(a) `backend/app.py` import — 喺 `import segment_split as ss`（app.py:66）下面加：

```python
import ai_edit
```

(b) Route — 加喺 `merge_next_segment` 函數完咗之後（app.py ~5494，`@app.route('/api/files/<file_id>', methods=['PATCH'])` 之前）：

```python
@app.route('/api/files/<file_id>/ai-edit', methods=['POST'])
@require_file_owner
def ai_edit_segment(file_id):
    """AI 輔助修改（suggest-only）：LLM 按用戶指令重寫一段一個語言欄嘅字幕。

    唔寫 registry — 前端預覽後經 PATCH /translations/<idx> 套用。
    Spec: docs/superpowers/specs/2026-06-10-proofread-ai-edit-design.md
    """
    data = request.get_json(silent=True) or {}
    instruction = (data.get("instruction") or "").strip()
    role = data.get("role")
    pos = data.get("pos")
    if not instruction or len(instruction) > ai_edit.MAX_INSTRUCTION_CHARS:
        return jsonify({"error": "指令唔可以係空，亦唔可以超過 500 字"}), 400
    if role not in ("first", "second"):
        return jsonify({"error": "role 必須係 first 或 second"}), 400
    if not isinstance(pos, int) or isinstance(pos, bool):
        return jsonify({"error": "pos 必須係整數"}), 400

    # Phase 1 — snapshot under lock（LLM call 喺 lock 外做）
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "AI 輔助修改只支援輸出語言流程"}), 400
        translations = entry.get("translations") or []
        if not (0 <= pos < len(translations)):
            return jsonify({"error": "段落不存在"}), 404
        outs = entry.get("output_languages") or []
        if not outs:
            return jsonify({"error": "檔案冇輸出語言資料"}), 400
        if role == "second" and len(outs) < 2:
            return jsonify({"error": "呢個檔案冇第二語言"}), 400
        target_lang = outs[0] if role == "first" else outs[1]
        other_lang = (outs[1] if (role == "first" and len(outs) > 1)
                      else (outs[0] if role == "second" else None))
        row = translations[pos]

        def _text_of(lang):
            if not lang:
                return ""
            bl = (row.get("by_lang") or {}).get(lang) or {}
            return (bl.get("text") or row.get(f"{lang}_text") or "").strip()

        target_text = _text_of(target_lang)
        other_text = _text_of(other_lang)
        labels = {l.get("role"): (l.get("label") or l.get("lang") or "")
                  for l in (entry.get("languages") or [])}
        target_label = labels.get(role) or target_lang
        other_label = labels.get("first" if role == "second" else "second") or (other_lang or "")

    # Phase 2 — LLM call，lock 外（慢）；suggest-only 所以唔使 Phase-3 conflict check
    llm = _make_ollama_llm_call()
    try:
        raw = llm(
            ai_edit.build_system_prompt(target_label),
            ai_edit.build_user_prompt(target_label, target_text,
                                      other_label, other_text, instruction),
        )
    except (ConnectionError, RuntimeError) as e:
        app.logger.error("ai-edit LLM call failed file=%s pos=%s: %s", file_id, pos, e)
        return jsonify({"error": "AI 服務暫時冇回應，請再試"}), 502

    text = ai_edit.parse_response(raw)
    if text is None:
        return jsonify({"error": "AI 輸出無法解析，請再試或修改指令"}), 422
    return jsonify({"ok": True, "text": text, "source_text": target_text,
                    "pos": pos, "role": role}), 200
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py -v`
Expected: 全部 pass（10 unit + 7 route）

- [ ] **Step 5: Smoke — import 唔爆**

Run: `cd backend && ./venv/bin/python -c "import app; print('import ok')"`
Expected: `import ok`

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_ai_edit.py
git commit -m "feat(ai-edit): POST /api/files/<id>/ai-edit suggest-only LLM endpoint"
```

---

### Task 3: PATCH `aligned_bilingual` 同步修正（現有 bug）

**Files:**
- Modify: `backend/app.py`（`api_update_translation` output_lang 寫入段，~app.py:3588-3595）
- Test: `backend/tests/test_ai_edit.py`（追加）

- [ ] **Step 1: 追加 failing tests**

```python
# ---------- PATCH /translations/<idx> aligned_bilingual sync（修現有 bug） ----------

def test_patch_translation_syncs_aligned_bilingual(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_bilingual_file("f-patch-sync")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "無人比我更傷感。", "role": "first"})
    assert r.status_code == 200
    with appmod._registry_lock:
        entry = appmod._file_registry[fid]
        # by_lang + mirror（原有行為）
        assert entry["translations"][0]["by_lang"]["zh"]["text"] == "無人比我更傷感。"
        assert entry["translations"][0]["zh_text"] == "無人比我更傷感。"
        # ★ 新行為：aligned grid 跟住改（雙語匯出/render 讀呢度）
        assert entry["aligned_bilingual"][0]["by_lang"]["zh"] == "無人比我更傷感。"
        # 另一語言唔受影響
        assert entry["aligned_bilingual"][0]["by_lang"]["en"].startswith("I don't think")


def test_patch_translation_without_aligned_grid_no_crash(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_bilingual_file("f-patch-noal")
    with appmod._registry_lock:
        appmod._file_registry[fid].pop("aligned_bilingual", None)
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "改咗", "role": "first"})
    assert r.status_code == 200
```

- [ ] **Step 2: 跑測試確認第一個 fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py -k aligned -v`
Expected: `test_patch_translation_syncs_aligned_bilingual` FAIL（aligned 仍係舊文字）；`no_crash` PASS

- [ ] **Step 3: 實現同步**

喺 `api_update_translation`，現有呢段（app.py:3588-3595）：

```python
        if do_by_lang_write:
            by_lang = dict(updated.get("by_lang") or {})
            if by_lang_key and by_lang_key in by_lang:
                by_lang[by_lang_key] = {**by_lang[by_lang_key], "text": new_text, "status": "approved"}
                updated["by_lang"] = by_lang
        new_translations[idx] = updated
        entry["translations"] = new_translations
        _save_registry()
```

改成（加 aligned 同步，仍喺同一個 `_registry_lock` 內）：

```python
        if do_by_lang_write:
            by_lang = dict(updated.get("by_lang") or {})
            if by_lang_key and by_lang_key in by_lang:
                by_lang[by_lang_key] = {**by_lang[by_lang_key], "text": new_text, "status": "approved"}
                updated["by_lang"] = by_lang
        new_translations[idx] = updated
        entry["translations"] = new_translations
        # Keep the paired bilingual grid in sync — bilingual export (subtitle.<fmt>)
        # and bilingual render read aligned_bilingual DIRECTLY, so a single-language
        # text edit must land there too (values are plain strings, not dicts).
        aligned = entry.get("aligned_bilingual")
        if by_lang_key and aligned and 0 <= idx < len(aligned):
            new_cue = dict(aligned[idx])
            new_cue["by_lang"] = {**(new_cue.get("by_lang") or {}), by_lang_key: new_text}
            entry["aligned_bilingual"] = aligned[:idx] + [new_cue] + aligned[idx + 1:]
        _save_registry()
```

- [ ] **Step 4: 跑測試確認 pass + 冇整爛舊行為**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py tests/test_segment_split_routes.py -v`
Expected: 全 pass（split suite 驗證冇 regression — 佢都用 PATCH 相鄰邏輯嘅 registry shape）

另跑現有 PATCH 相關 suite（單獨跑，避 full-suite 污染）：
Run: `cd backend && ./venv/bin/python -m pytest tests/test_api_translations.py -v 2>/dev/null || true`（如果檔案存在）

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_ai_edit.py
git commit -m "fix(translations): PATCH single-language edit now syncs aligned_bilingual (bilingual export/render read it directly)"
```

---

### Task 4: Frontend — ✦ AI 掣 + ae-* popup（proofread.html）

**Files:**
- Modify: `frontend/proofread.html`（4 處：CSS、renderDetail template、modal markup、JS）

視覺基準 = mockup `.superpowers/brainstorm/89682-1781070476/content/ai-edit-preview.html`。

- [ ] **Step 1: 加 CSS** — 喺 `/* Toast */` comment（~line 738）之前插入：

```css
    /* AI 輔助修改（ae-*）— spec 2026-06-10-proofread-ai-edit-design.md */
    .ae-btn {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 2px 9px; border-radius: 6px;
      font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em;
      color: var(--accent-2); background: var(--accent-soft);
      border: 1px solid var(--accent-ring); cursor: pointer;
      text-transform: none; font-family: inherit;
      transition: background .12s;
    }
    .ae-btn:hover { background: rgba(108,99,255,0.22); }
    .ae-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.6);
      display: flex; align-items: center; justify-content: center;
      z-index: 3000; opacity: 0; pointer-events: none; transition: opacity 0.2s;
    }
    .ae-overlay.open { opacity: 1; pointer-events: auto; }
    .ae-modal {
      background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
      width: 520px; max-width: calc(100vw - 40px); max-height: 80vh;
      display: flex; flex-direction: column; box-shadow: var(--shadow);
    }
    .ae-header {
      padding: 14px 18px; border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px; font-weight: 700;
    }
    .ae-header .ae-sub { color: var(--text-dim); font-weight: 500; margin-left: 6px; }
    .ae-close { background: none; border: none; color: var(--text-dim); font-size: 18px; cursor: pointer; padding: 0 4px; line-height: 1; }
    .ae-close:hover { color: var(--text); }
    .ae-body { flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 12px; }
    .ae-sec { font-size: 10.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); }
    .ae-before { padding: 10px 12px; background: var(--surface-2); border-left: 2px solid var(--border-strong); border-radius: 0 6px 6px 0; font-size: 14px; line-height: 1.6; color: var(--text-mid); }
    .ae-chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .ae-chip { padding: 5px 11px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface-2); font-size: 12px; font-weight: 600; color: var(--text-mid); cursor: pointer; font-family: inherit; }
    .ae-chip:hover { border-color: var(--accent-ring); color: var(--accent-2); }
    .ae-chip.on { background: var(--accent-soft); border-color: var(--accent-ring); color: var(--accent-2); }
    .ae-inst { background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 7px; padding: 10px 12px; font-family: inherit; font-size: 13.5px; line-height: 1.5; min-height: 54px; resize: vertical; width: 100%; }
    .ae-inst:focus { outline: 2px solid var(--accent-ring); border-color: var(--accent); }
    .ae-result { padding: 10px 12px; background: rgba(34,197,94,0.07); border-left: 2px solid var(--success); border-radius: 0 6px 6px 0; font-size: 15px; line-height: 1.6; display: none; }
    .ae-result.show { display: block; }
    .ae-loading { display: none; align-items: center; gap: 9px; font-size: 12.5px; color: var(--text-mid); padding: 4px 2px; }
    .ae-loading.show { display: flex; }
    .ae-spin { width: 14px; height: 14px; border: 2px solid var(--border-strong); border-top-color: var(--accent-2); border-radius: 50%; animation: aespin .7s linear infinite; }
    @keyframes aespin { to { transform: rotate(360deg); } }
    .ae-footer { display: flex; align-items: center; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border); }
```

- [ ] **Step 2: renderDetail template 加掣** — 兩處（proofread.html renderDetail，~2493-2519）：

第一語言 label 行（現有）：
```javascript
          <div class="rv-b-detail-label">
            <span>${escapeHtml(enLabel)}</span>
            ${confStub}
            ${cpsFirstHtml}
          </div>
```
改成：
```javascript
          <div class="rv-b-detail-label">
            <span>${escapeHtml(enLabel)}</span>
            ${confStub}
            ${cpsFirstHtml}
            ${isOutputLang ? `<button class="ae-btn" onclick="openAiEditModal('first')" title="AI 輔助修改第一語言">✦ AI</button>` : ''}
          </div>
```

第二語言 label 行（現有，喺 `${showZhField ?` block 內）：
```javascript
          <div class="rv-b-detail-label">
            <span>${escapeHtml(zhLabel)}</span>
            ${confStub}
            ${cpsSecondHtml}
          </div>
```
改成：
```javascript
          <div class="rv-b-detail-label">
            <span>${escapeHtml(zhLabel)}</span>
            ${confStub}
            ${cpsSecondHtml}
            ${isOutputLang ? `<button class="ae-btn" onclick="openAiEditModal('second')" title="AI 輔助修改第二語言">✦ AI</button>` : ''}
          </div>
```
（`isOutputLang` gate ⇒ Profile/V6 檔唔出掣；second 掣只喺 `showZhField` block 內 ⇒ 單語言檔自動冇。）

- [ ] **Step 3: Modal markup** — 喺 `<!-- Glossary Apply Modal -->` 嘅 `</div>`（gaOverlay 閂咗之後，`<!-- Licence grace` 之前）加：

```html
<!-- AI 輔助修改 Modal -->
<div class="ae-overlay" id="aeOverlay">
  <div class="ae-modal">
    <div class="ae-header">
      <span>✦ AI 輔助修改<span class="ae-sub" id="aeTitleSub"></span></span>
      <button class="ae-close" onclick="closeAiEditModal()" aria-label="關閉 AI 輔助修改">&times;</button>
    </div>
    <div class="ae-body">
      <div class="ae-sec">修改前</div>
      <div class="ae-before" id="aeBefore"></div>
      <div class="ae-sec">快速選項（撳完可再修改指令）</div>
      <div class="ae-chips" id="aeChips">
        <button class="ae-chip" data-k="translate" onclick="aePickChip(this)">⇄ 對照翻譯</button>
        <button class="ae-chip" data-k="written" onclick="aePickChip(this)">改更書面</button>
        <button class="ae-chip" data-k="spoken" onclick="aePickChip(this)">改更口語</button>
        <button class="ae-chip" data-k="concise" onclick="aePickChip(this)">精簡句子</button>
      </div>
      <div class="ae-sec">指令</div>
      <textarea class="ae-inst" id="aeInst" placeholder="輸入你想 AI 點樣修改呢段字幕，例如：將「傷感」改做「難過」"></textarea>
      <div class="ae-loading" id="aeLoading"><span class="ae-spin"></span>AI 生成中…</div>
      <div class="ae-sec" id="aeAfterHead" style="display:none">修改後（預覽）</div>
      <div class="ae-result" id="aeResult"></div>
    </div>
    <div class="ae-footer">
      <button class="btn btn-ghost" onclick="closeAiEditModal()">取消</button>
      <div class="spacer"></div>
      <button class="btn btn-ghost" id="aeRetry" onclick="aeGenerate()" style="display:none">↻ 再生成</button>
      <button class="btn btn-primary" id="aeGen" onclick="aeGenerate()">生成</button>
      <button class="btn btn-primary" id="aeApply" onclick="aeApply()" style="display:none">✓ 套用</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: JS** — 喺 `saveEnIfDirty()` 函數完咗之後（~app proofread.html:2822，`approveAndAdvance` 之前）加：

```javascript
  // ============================================================
  // AI 輔助修改（ae-*）— spec 2026-06-10-proofread-ai-edit-design.md
  // suggest: POST /api/files/<id>/ai-edit；套用: 現有 PATCH /translations/<idx>
  // ============================================================
  let _aeState = null;   // { idx, role, beforeText, resultText, busy }

  function openAiEditModal(role) {
    const s = segs[cursorIdx];
    if (!s) return;
    const beforeText = role === 'first' ? (s.en || '') : (s.zh || '');
    _aeState = { idx: s.idx, role, beforeText, resultText: null, busy: false };
    document.getElementById('aeTitleSub').textContent =
      ' · ' + (role === 'first' ? (_outputLangLabel('first') || '第一語言') : (_outputLangLabel('second') || '第二語言'));
    document.getElementById('aeBefore').textContent = beforeText || '（空白）';
    document.getElementById('aeInst').value = '';
    document.querySelectorAll('#aeChips .ae-chip').forEach(c => c.classList.remove('on'));
    // 對照翻譯 chip 要有另一語言先有意義
    const hasOther = role === 'first' ? !!s._hasSecond : true;
    document.querySelector('#aeChips [data-k="translate"]').style.display = hasOther ? '' : 'none';
    _aeResetResult();
    document.getElementById('aeOverlay').classList.add('open');
  }

  function closeAiEditModal() {
    document.getElementById('aeOverlay').classList.remove('open');
    _aeState = null;
  }

  function aePickChip(el) {
    document.querySelectorAll('#aeChips .ae-chip').forEach(c => c.classList.toggle('on', c === el));
    const role = _aeState ? _aeState.role : 'first';
    const otherLabel = role === 'first'
      ? (_outputLangLabel('second') || '第二語言')
      : (_outputLangLabel('first') || '第一語言');
    const texts = {
      translate: `根據${otherLabel}嘅意思，重新翻譯呢段字幕`,
      written: '將語氣改得更書面正式',
      spoken: '將語氣改得更口語自然',
      concise: '喺唔改變意思嘅前提下精簡呢句字幕',
    };
    document.getElementById('aeInst').value = texts[el.dataset.k] || '';
    _aeResetResult();
  }

  function _aeResetResult() {
    document.getElementById('aeResult').classList.remove('show');
    document.getElementById('aeAfterHead').style.display = 'none';
    document.getElementById('aeApply').style.display = 'none';
    document.getElementById('aeRetry').style.display = 'none';
    document.getElementById('aeGen').style.display = '';
    document.getElementById('aeLoading').classList.remove('show');
  }

  async function aeGenerate() {
    if (!_aeState || _aeState.busy) return;
    const inst = document.getElementById('aeInst').value.trim();
    if (!inst) { showToast('請輸入指令或撳快速選項', 'warning'); return; }
    if (inst.length > 500) { showToast('指令唔可以超過 500 字', 'warning'); return; }
    _aeState.busy = true;
    const genBtn = document.getElementById('aeGen');
    const retryBtn = document.getElementById('aeRetry');
    genBtn.disabled = true; retryBtn.disabled = true;
    document.getElementById('aeLoading').classList.add('show');
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/ai-edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pos: _aeState.idx, role: _aeState.role, instruction: inst }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
      if (!_aeState) return;            // 生成期間用戶閂咗 modal — 棄置結果
      _aeState.resultText = data.text;
      document.getElementById('aeResult').textContent = data.text;
      document.getElementById('aeResult').classList.add('show');
      document.getElementById('aeAfterHead').style.display = '';
      genBtn.style.display = 'none';
      retryBtn.style.display = '';
      document.getElementById('aeApply').style.display = '';
    } catch (e) {
      showToast(`AI 生成失敗：${e.message}`, 'error');
    } finally {
      if (_aeState) _aeState.busy = false;
      genBtn.disabled = false; retryBtn.disabled = false;
      document.getElementById('aeLoading').classList.remove('show');
    }
  }

  async function aeApply() {
    if (!_aeState || !_aeState.resultText) return;
    const { idx, role, resultText } = _aeState;
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/translations/${idx}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: resultText, role }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.error || `HTTP ${r.status}`);
      }
      // 用 idx 搵返段（唔靠 cursorIdx — 防 modal 開住時 cursor 變）
      const s = segs.find(x => x.idx === idx);
      if (s) {
        const dur = (s.out - s.in) / 1000;
        if (role === 'first') {
          s.en = resultText;
          s.cps = dur > 0 ? Math.round((resultText.length / dur) * 10) / 10 : 0;
        } else {
          s.zh = resultText;
          s._cpsSecond = dur > 0 ? Math.round((resultText.length / dur) * 10) / 10 : 0;
        }
        s.edited = true;
        s.approved = true;   // PATCH 後端 auto-approve，前端鏡返
      }
      closeAiEditModal();
      renderDetail();
      renderSegList();
      showToast('已套用 AI 修改 ✓', 'success');
    } catch (e) {
      showToast(`套用失敗：${e.message}`, 'error');
    }
  }
```

- [ ] **Step 5: Esc handler** — 現有 listener（~proofread.html:3211）：

```javascript
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (e.target && e.target.tagName === 'TEXTAREA') return;
    const ga = document.getElementById('gaOverlay');
    if (ga?.classList.contains('open')) {
      ga.classList.remove('open');
      e.preventDefault();
    }
  });
```
改成（ae 行先，因為佢通常開喺 ga 之上；textarea-skip 對 #aeInst 同樣適用 — 用戶喺指令框撳 Esc 唔會誤閂）：

```javascript
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (e.target && e.target.tagName === 'TEXTAREA') return;
    const ae = document.getElementById('aeOverlay');
    if (ae?.classList.contains('open')) {
      closeAiEditModal();
      e.preventDefault();
      return;
    }
    const ga = document.getElementById('gaOverlay');
    if (ga?.classList.contains('open')) {
      ga.classList.remove('open');
      e.preventDefault();
    }
  });
```

- [ ] **Step 6: Smoke — 頁面載入無 JS error**（要 :5001 行緊 dev code；frontend 係 static per-request 讀 disk，唔使重啟 backend，但要主 repo dev 包含本 commit — 執行時如果 :5001 行緊主 repo，先 ff dev 或者直接喺 worktree 開多個 server）

最簡：用 Playwright 開 `http://localhost:5001/proofread.html?file_id=97ce36e85e97`（login `admin_p3`/`TestPass1!`，POST `/login`），assert 冇 pageerror、`.ae-btn` 出現兩粒、撳開 modal、Esc 閂。

- [ ] **Step 7: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): ✦ AI 輔助修改 — per-language AI edit popup (chips + preview + apply)"
```

---

### Task 5: E2E（真 Chrome + 真後端 + 真 LLM）

**Files:**
- Create: `/tmp/ai_edit_e2e.py`（測試 artifact，唔 commit）

- [ ] **Step 1: 寫 E2E script**

```python
"""E2E: proofread AI 輔助修改 — 真 Chrome + :5001 + 真 Ollama LLM。"""
import asyncio
from playwright.async_api import async_playwright

BASE = 'http://localhost:5001'
FILE_ID = '97ce36e85e97'   # 馬會騎師訪問 en+zh 雙語檔

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', headless=True)
        page = await (await b.new_context(viewport={'width': 1600, 'height': 1000})).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        await page.goto(BASE + '/login.html')
        await page.evaluate("""async () => { await fetch('/login', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({username:'admin_p3', password:'TestPass1!'})}); }""")
        await page.goto(BASE + f'/proofread.html?file_id={FILE_ID}')
        await page.wait_for_selector('.rv-b-detail-input', timeout=20000)
        # 兩粒 AI 掣
        assert await page.locator('.ae-btn').count() == 2, 'expected 2 ✦ AI buttons'
        before = await page.input_value('#zhInput')
        # 開第二語言 popup → 精簡 chip → 生成（真 LLM，等耐啲）
        await page.click('.ae-btn >> nth=1')
        assert await page.is_visible('.ae-overlay.open')
        await page.click('#aeChips [data-k="concise"]')
        inst = await page.input_value('#aeInst')
        assert inst, 'chip did not prefill instruction'
        await page.click('#aeGen')
        await page.wait_for_selector('.ae-result.show', timeout=120000)
        result = (await page.text_content('#aeResult')).strip()
        print('LLM result:', result)
        assert result and result != before
        await page.screenshot(path='/tmp/ai-edit-e2e-preview.png')
        # 套用 → textarea 更新
        await page.click('#aeApply')
        await page.wait_for_timeout(800)
        assert not await page.is_visible('.ae-overlay.open')
        after = await page.input_value('#zhInput')
        print('before:', before)
        print('after :', after)
        assert after == result
        print('JS errors:', errs if errs else 'none')
        assert not errs
        await b.close()
        print('E2E PASS')

asyncio.run(main())
```

- [ ] **Step 2: 跑**

Run: `"/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" /tmp/ai_edit_e2e.py`
Expected: `E2E PASS`（LLM 一般 2–10 秒；前提 :5001 行緊包含本 feature 嘅 code + Ollama 起咗）

前提檢查：`curl -s http://localhost:11434/api/tags | head -c 200`（Ollama alive）；`curl -s http://localhost:5001/api/ready`。

- [ ] **Step 3: 用 Read tool 開 `/tmp/ai-edit-e2e-preview.png` 肉眼驗 popup 樣 == mockup**

注意：E2E 會真係改咗段 0 嘅第二語言文字（PATCH 落 registry）。測完如要還原：再開 popup 手動改返，或接受改動（係合理嘅精簡結果）。

---

### Task 6: Validation-First live 驗證 + tracker

**Files:**
- Create: `/tmp/ai_edit_validate.py`（artifact）
- Create: `docs/superpowers/specs/2026-06-10-proofread-ai-edit-validation-tracker.md`

- [ ] **Step 1: 寫 validation script** — 經 API 對真實檔案（`97ce36e85e97`）頭 3 段 × 4 種指令（對照翻譯/更書面/更口語/精簡）各跑一次（12 個 call，production model qwen3.5:35b-a3b）：

```python
"""Validation-First: ai-edit 4 種指令 × 3 段真字幕 × production model."""
import json
import urllib.request

BASE = 'http://localhost:5001'
FID = '97ce36e85e97'

def post(path, body, cookie):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Cookie': cookie},
                                 method='POST')
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def login():
    req = urllib.request.Request(BASE + '/login',
                                 data=json.dumps({'username': 'admin_p3', 'password': 'TestPass1!'}).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as r:
        return r.headers.get('Set-Cookie', '').split(';')[0]

INSTRUCTIONS = {
    '對照翻譯': '根據英文嘅意思，重新翻譯呢段字幕',
    '更書面': '將語氣改得更書面正式',
    '更口語': '將語氣改得更口語自然',
    '精簡': '喺唔改變意思嘅前提下精簡呢句字幕',
}

cookie = login()
for pos in range(3):
    for name, inst in INSTRUCTIONS.items():
        try:
            d = post(f'/api/files/{FID}/ai-edit',
                     {'pos': pos, 'role': 'first', 'instruction': inst}, cookie)
            print(f'pos={pos} [{name}] {d["source_text"]!r} -> {d["text"]!r}')
        except Exception as e:
            print(f'pos={pos} [{name}] FAILED: {e}')
```

- [ ] **Step 2: 跑 + 人手評每個輸出**（✅ 符合指令 / ⚠️ 部分 / ❌ 失敗：轉咗語言、加料、超長、丟專名）

- [ ] **Step 3: 寫 tracker** `docs/superpowers/specs/2026-06-10-proofread-ai-edit-validation-tracker.md`，格式跟現有 tracker（逐項 ✅/⚠️/❌ + 原始輸出樣本 + 結論）。如有 ❌ 多過 2/12 → 調整 system prompt 規則並重跑（記兩輪結果）。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-10-proofread-ai-edit-validation-tracker.md
git commit -m "docs(validation): ai-edit live validation tracker (4 instructions x 3 segs, qwen3.5:35b-a3b)"
```

---

### Task 7: 文檔（CLAUDE.md + README）

**Files:**
- Modify: `CLAUDE.md`（REST endpoints table + Current State 一段）
- Modify: `README.md`（繁體中文用戶說明）

- [ ] **Step 1: CLAUDE.md** — REST table 加一行（放喺 `/api/files/<id>/segments/<pos>/merge-next` 行之後）：

```markdown
| POST | `/api/files/<id>/ai-edit` | output_lang only — AI 輔助修改（suggest-only）：body `{pos, role: first\|second, instruction ≤500字}`；LLM 按指令重寫該段該語言字幕，回 `{text, source_text}`；**唔寫 registry**（前端經 PATCH /translations/<idx> 套用）；400 非 output_lang/壞參數、404 段落唔存在、422 LLM 輸出無法解析、502 LLM 冇回應 |
```

Current State 加一段（喺「Proofread segment split / merge」段之後）：

```markdown
### Proofread AI 輔助修改（output_lang，NEW 2026-06-10）

- Detail panel 每個語言欄 label 行有「✦ AI」掣（output_lang 檔先出現）→ ae-* popup：修改前 → 快速 chips（對照翻譯/改更書面/改更口語/精簡句子，填入指令框可再修改）→ 生成（`POST /api/files/<id>/ai-edit`，suggest-only）→ 修改後預覽 → 套用（現有 `PATCH /translations/<idx>` + `{text, role}`）。
- LLM 同 output_lang pipeline 共用 `_make_ollama_llm_call()`（Beta 模式自動行 OpenRouter）。Prompt/解析喺 `backend/ai_edit.py`（pure，`tests/test_ai_edit.py`）。
- **PATCH 同步修正**：`PATCH /translations/<idx>` 而家會同步 `aligned_bilingual[idx].by_lang[lang]`（之前單欄編輯唔會反映落雙語匯出/render — 已修）。
```

- [ ] **Step 2: README.md** — 「校對」章節加用戶說明（繁體中文，幾句 + 快速選項列表即可，跟 README 現有風格）。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: AI 輔助修改 feature (CLAUDE.md REST + Current State, README 用戶說明)"
```

---

## 驗收清單（全 plan 完成後）

- [ ] `cd backend && ./venv/bin/python -m pytest tests/test_ai_edit.py tests/test_segment_split_routes.py -v` 全 PASS（單獨跑，避 full-suite 污染）
- [ ] `./venv/bin/python -c "import app"` 唔爆
- [ ] E2E PASS + screenshot 同 mockup 視覺一致
- [ ] Validation tracker ❌ ≤ 2/12（否則已調 prompt 重跑）
- [ ] CLAUDE.md + README 已更新
- [ ] V6/Profile 檔開 proofread — 冇 ✦ AI 掣（regression 肉眼驗）
