# V6 粵語書面語 Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent, separately-selectable V6 Cantonese pipeline「[v6] 賽馬廣播 (書面語)」that outputs modern formal written Chinese (現代正式書面語) via a two-pass chained refiner, without touching the existing colloquial pipeline.

**Architecture:** Config-only. The existing `pipeline_runner.py::_run_v6` refiner loop (`refinements[target_lang]`, ~L588-646) already runs an ordered list of `RefinerStage`s, mutating `lang_segments` between passes. We add a NEW pipeline JSON whose `refinements.zh` is a 2-element chain: pass 1 = the existing 口語 refiner `f7f72bd9` (unchanged), pass 2 = a new 書面語 register refiner `9dbe1aa3` that flips register on the already-cleaned Cantonese. Three new config files + one test. Zero Python changes.

**Tech Stack:** Python 3.9, pytest, Flask (V6 pipeline runner), Ollama `qwen3.5:35b-a3b-mlx-bf16` (reused via existing LLM profile `9402593c`). Config JSON loaded by `PipelineManager` / `RefinerProfileManager` / prompt-template loader (`engines/factory.py::load_prompt_template`).

---

## Background the engineer needs

- **Prior art** lives on branch `feat/phase-1-frontend-design` (commits `ac96d75` prompt template / `43d614d` refiner profile / `42bc3d1` pipeline). The files are ABSENT on the current branch `fix/profile-and-v6` — clean slate, no collision. Read a prior-art file without checking out:
  `git show feat/phase-1-frontend-design:backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json`
- **Two must-fixes vs prior art:** (1) prior-art `user_id` is `627` → set to `null` (matches the existing 口語 pipeline `4696bbaa` + refiner `f7f72bd9`, both `user_id:null, shared:false`, so the new pipeline is visible to every user in the picker); (2) the prior-art prompt described a dead `{target, neighbors}` JSON input envelope — production `LLMRefiner.refine()` passes **bare segment text**, so our prompt takes a bare sentence and outputs `{"action":"keep","text":...}`.
- **Validated** already (prototype on 120 real persisted 口語 segments): residual markers 16.63→0.13/100 chars, names 100%, no-op 0.8%, length median 1.0×. See `docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md`.
- **Prompt-template loader:** `from engines.factory import load_prompt_template` → `load_prompt_template("refiner/zh_written_register_v6")` returns the `system_prompt` string. Template JSON `id` field = `"refiner/zh_written_register_v6"` and the file lives at `config/prompt_templates_v5/refiner/zh_written_register_v6.json`.
- **Test fixture pattern** (from `tests/test_v6_child_manager_subdir.py`): an `admin_app` fixture that `monkeypatch.setenv("R5_AUTH_BYPASS","1")` then `importlib.reload(app)`, exposing `_pipeline_manager`, `_refiner_profile_manager`. Managers expose `.get(id)`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json` (NEW) | The 書面語 register-conversion system prompt (modern formal, Arabic numerals, byte-preserve names, keep idioms). |
| `backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json` (NEW) | Refiner profile binding the template to LLM profile `9402593c`; `user_id:null`. |
| `backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json` (NEW) | Pipeline「[v6] 賽馬廣播 (書面語)」, clone of `4696bbaa` with `refinements.zh=[f7f72bd9, 9dbe1aa3]`; `user_id:null`. |
| `backend/tests/test_v6_written_register.py` (NEW) | Config-load assertions + 口語-pipeline regression guard. |
| `docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md` (MODIFY) | Append integration-re-run results. |
| `CLAUDE.md` (MODIFY) | Completed-feature entry. |

---

### Task 1: Failing config-load test

**Files:**
- Create: `backend/tests/test_v6_written_register.py`

- [ ] **Step 1: Write the failing test**

```python
"""V6 粵語書面語 pipeline — config-load + 口語-pipeline regression guard (2026-05-31)."""
import importlib
import pytest

PIPELINE_ID = "1443afcb-198b-4821-8e64-47d02bf877f3"
REFINER_ID = "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa"
CANTO_PIPELINE_ID = "4696bbaa-b988-49bd-859c-e742cb365634"
COLLOQUIAL_REFINER_ID = "f7f72bd9-3f27-47a4-92bd-5727f336916a"
TEMPLATE_ID = "refiner/zh_written_register_v6"


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_written_prompt_template_loads_with_register_rules():
    from engines.factory import load_prompt_template
    sp = load_prompt_template(TEMPLATE_ID)
    assert sp and isinstance(sp, str)
    # modern-formal register rules present
    for cue in ["嘅→的", "係→是", "咗→了", "書面語"]:
        assert cue in sp, f"missing register cue: {cue}"
    # locked dials: Arabic numerals kept, over-literary forbidden
    assert "阿拉伯數字" in sp
    assert "1650" in sp  # the kept-Arabic example
    assert "惟" in sp and "禁" in sp  # explicit ban on over-literary 文言虛詞


def test_written_refiner_profile_loads_user_id_null(admin_app):
    prof = admin_app._refiner_profile_manager.get(REFINER_ID)
    assert prof is not None, f"refiner profile {REFINER_ID} not found"
    assert prof["lang"] == "zh"
    assert prof["prompt_template_id"] == TEMPLATE_ID
    assert prof["llm_profile_id"] == "9402593c-184d-4a4d-a160-ebdf55e678e8"
    assert prof.get("user_id") is None  # must be null, NOT 627


def test_written_pipeline_chains_two_refiners(admin_app):
    p = admin_app._pipeline_manager.get(PIPELINE_ID)
    assert p is not None, f"pipeline {PIPELINE_ID} not found"
    assert p.get("user_id") is None
    assert "書面語" in p["name"]
    chain = p["refinements"]["zh"]
    assert len(chain) == 2, f"expected 2-refiner chain, got {len(chain)}"
    assert chain[0]["refiner_profile_id"] == COLLOQUIAL_REFINER_ID
    assert chain[1]["refiner_profile_id"] == REFINER_ID


def test_colloquial_pipeline_unchanged_single_refiner(admin_app):
    """Regression: the existing 口語 pipeline must keep its single-refiner chain."""
    p = admin_app._pipeline_manager.get(CANTO_PIPELINE_ID)
    assert p is not None
    chain = p["refinements"]["zh"]
    assert len(chain) == 1, "口語 pipeline must NOT gain a second refiner"
    assert chain[0]["refiner_profile_id"] == COLLOQUIAL_REFINER_ID
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_written_register.py -q`
Expected: FAIL — `load_prompt_template` raises / returns nothing for the missing template, and `_refiner_profile_manager.get(REFINER_ID)` / `_pipeline_manager.get(PIPELINE_ID)` return `None` (configs don't exist yet). The regression test (`test_colloquial_pipeline_unchanged_single_refiner`) should PASS already.

- [ ] **Step 3: Commit the RED test**

```bash
git add backend/tests/test_v6_written_register.py
git commit -m "test(v6): RED — 書面語 pipeline config-load + 口語 regression guard"
```

---

### Task 2: Add the 書面語 refiner prompt template

**Files:**
- Create: `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`

- [ ] **Step 1: Create the template file** (exact content)

```json
{
  "id": "refiner/zh_written_register_v6",
  "name": "ZH 書面語 register conversion v6 (modern formal)",
  "version": 6,
  "lang": "zh",
  "style": "written_register_v6",
  "system_prompt": "你係專業繁體中文新聞編輯。輸入係一句已經粵語校對好嘅廣播字幕（人名、地名、賽馬術語、數字、時間軸都已正確）。\n任務：淨係將呢句由【粵語口語 register】轉換成【現代正式繁體中文書面語 register】，貼近規範新聞書面語。唔好保留口語感，亦唔好過度文言或公文化。\n\n轉換規則：\n1. 粵語特徵字 → 書面語：嘅→的、係→是、咗→了、喺→在、唔→不、冇→沒有、俾/畀→給或被(按語境)、嘢→東西/事物(按語境)、佢→他/她/它、哋→們、而家→現在、點解→為何、睇→看、嗰→那、呢→這、乜/乜嘢→什麼、邊個→哪位/哪個、幾多→多少、咁→這樣/如此、喺度→在此。\n2. 句末語氣助詞（啦/㗎/㗎啩/囉/喎/呀/咩/喇/嘅）一律刪除，必要時改為規範語氣（了/吧/呢）。\n3. 用規範現代書面句式（如「表示」「指出」「進行」「準備就緒」），但嚴禁過度文言虛詞（惟/縱/乃/之乎者也）同累贅公文腔（茲/予以/上述/該項/之事宜）。\n4. 保留生動四字詞同成語（如「傷病纏身」「大刀闊斧」「旗開得勝」），唔好拆成冗長學術詞。\n5. 數字、時間保留阿拉伯數字原狀（如「1650 米」唔好寫成「一千六百五十米」）。\n6. 必須 byte-for-byte 保留唔變：人名、地名、賽馬術語、英文詞、賽事名（袁幸堯、潘頓、沙田、HIGHLAND BLINK、寶馬香港打吡大賽 等）。\n7. 長度 0.8–1.3× 原文字數。唔加外部資訊、唔加原文冇嘅句首連接詞。\n\n輸出：純 JSON object，無 markdown fence，無其他文字。只輸出 keep 格式：{\"action\": \"keep\", \"text\": \"<書面語校對後文字>\"}\n\n例子 1：輸入「準備起步啦。咁出閘嘅時候，都望住喺內欄啊。」→ 輸出 {\"action\": \"keep\", \"text\": \"準備起步。出閘時均望向內欄。\"}\n例子 2：輸入「飛輪八夠唔夠快？佢反應都 OK 㗎。」→ 輸出 {\"action\": \"keep\", \"text\": \"飛輪八速度是否足夠？其反應亦屬良好。\"}\n例子 3：輸入「第六場係四班 1650 米嚟㗎」→ 輸出 {\"action\": \"keep\", \"text\": \"第六場為四班 1650 米賽事。\"}"
}
```

- [ ] **Step 2: Run the template test**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_written_register.py::test_written_prompt_template_loads_with_register_rules -q`
Expected: PASS (template loads; all cues `嘅→的`/`係→是`/`咗→了`/`書面語`/`阿拉伯數字`/`1650`/`惟`+`禁` present).

- [ ] **Step 3: Commit**

```bash
git add backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json
git commit -m "feat(v6): 書面語 register refiner prompt template (modern formal, Arabic numerals)"
```

---

### Task 3: Add the 書面語 refiner profile (user_id:null)

**Files:**
- Create: `backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json`

- [ ] **Step 1: Create the refiner profile** (exact content — note `user_id: null`)

```json
{
  "id": "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa",
  "name": "Refiner ZH 書面語 register conversion v6",
  "lang": "zh",
  "style": "written_register_v6",
  "llm_profile_id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
  "prompt_template_id": "refiner/zh_written_register_v6",
  "shared": false,
  "user_id": null,
  "created_at": 1779874657.732016,
  "updated_at": 1779874657.732016
}
```

- [ ] **Step 2: Run the refiner-profile test**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_written_register.py::test_written_refiner_profile_loads_user_id_null -q`
Expected: PASS (`_refiner_profile_manager.get("9dbe1aa3-...")` returns the profile, `lang=="zh"`, `prompt_template_id=="refiner/zh_written_register_v6"`, `user_id is None`).

- [ ] **Step 3: Commit**

```bash
git add backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json
git commit -m "feat(v6): 書面語 register refiner profile (user_id null, reuse llm 9402593c)"
```

---

### Task 4: Add the 書面語 pipeline (chained refiner, user_id:null)

**Files:**
- Create: `backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json`

- [ ] **Step 1: Create the pipeline file** (exact content — clone of 4696bbaa with 2-refiner chain + `user_id:null`)

```json
{
  "name": "[v6] 賽馬廣播 (書面語)",
  "pipeline_type": "v6_vad_dual_asr",
  "version": 6,
  "source_lang": "zh",
  "target_languages": ["zh"],
  "vad": {"threshold": 0.5, "min_speech_duration_ms": 250, "max_speech_duration_s": 15, "min_silence_duration_ms": 500, "speech_pad_ms": 200},
  "asr_primary": {"transcribe_profile_id": "82338761-e6ed-47eb-b153-64789ed7327e", "source_lang": "zh"},
  "qwen3_asr": {"language": "Chinese", "context": "袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 美狼王 HIGHLAND BLINK 幸運風采 沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 騎師 試騎 推騎 試閘 抽籤 排位 大熱門 頭馬 客艙 馬房 馬仔 香檳 打吡 香港 沙田 悉尼", "post_s2hk": true},
  "refinements": {"zh": [{"refiner_profile_id": "f7f72bd9-3f27-47a4-92bd-5727f336916a"}, {"refiner_profile_id": "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa"}]},
  "translators": {},
  "glossary_stages": [],
  "font_config": {"family": "Noto Sans TC", "color": "white", "outline_color": "black"},
  "shared": false,
  "id": "1443afcb-198b-4821-8e64-47d02bf877f3",
  "user_id": null,
  "created_at": 1779874657.732016,
  "updated_at": 1779874657.732016
}
```

- [ ] **Step 2: Run the full test file**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_written_register.py -q`
Expected: 4 PASS (template + refiner + 2-refiner chain + 口語-pipeline-unchanged regression guard).

- [ ] **Step 3: Commit**

```bash
git add backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json
git commit -m "feat(v6): [v6] 賽馬廣播 (書面語) pipeline — chained 口語→書面語 refiner (user_id null)"
```

---

### Task 5: Regression suite + boot/picker check

**Files:** none (verification only)

- [ ] **Step 1: Run V6 / pipeline / refiner regression**

Run: `cd backend && source venv/bin/activate && pytest tests/ -k "v6 or pipeline or refiner" -q`
Expected: no NEW failures vs baseline. Known pre-existing isolation failures are acceptable IF they fail identically without this change (e.g. `test_v6_second_language` full-suite isolation). If any NEW failure appears, STOP and investigate.

- [ ] **Step 2: Boot backend + confirm the pipeline is selectable, 口語 unchanged**

```bash
cd backend && source venv/bin/activate
python3 -c "from auth import users; users.update_password('data/app.db','admin_p3','TestPass1!')"
pkill -if "app.py"; sleep 2
set -a && source .env && set +a && nohup python app.py > /tmp/wr_backend.log 2>&1 &
sleep 8
# login + list pipelines
J=/tmp/wr_cookies.txt
curl -s -c $J -X POST http://localhost:5001/login -H 'Content-Type: application/json' -d '{"username":"admin_p3","password":"TestPass1!"}' -o /dev/null -w "login %{http_code}\n"
curl -s -b $J http://localhost:5001/api/pipelines | python3 -c "import sys,json; ps=json.load(sys.stdin); ps=ps if isinstance(ps,list) else ps.get('pipelines',ps); names={p['name']:len(p.get('refinements',{}).get('zh',[])) for p in ps if 'name' in p}; print(names)"
```
Expected output includes BOTH `'[v6] 賽馬廣播 (書面語)': 2` AND `'[v6] 賽馬廣播 (Cantonese)': 1`.

---

### Task 6: Validation-First integration re-run (real clip end-to-end)

**Files:**
- Modify: `docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md` (append「整合驗證」section)

**Context:** The register-conversion quality is already prototype-validated on persisted data. This task confirms the new pipeline is wired and runs end-to-end (both refiners execute), measures residual-marker rate on the LIVE persisted `by_lang.zh`, checks latency stays in `R5_QWEN3_TIMEOUT_SEC` budget, and confirms the 口語 pipeline output is byte-identical (zero regression).

- [ ] **Step 1: Snapshot the 口語 pipeline baseline output for `de603727d3f8`**

```bash
cd backend && source venv/bin/activate && PYTHONPATH=. python3 - <<'PY'
import json, glob
rp=(glob.glob("data/**/registry.json",recursive=True) or ["data/registry.json"])[0]
d=json.load(open(rp)); files=d if isinstance(d,list) else d.get("files",d)
if isinstance(files,dict): files=list(files.values())
f=[x for x in files if x.get("id")=="de603727d3f8"][0]
zh=[(r.get("zh_text") or "").strip() for r in (f.get("translations") or [])]
json.dump(zh, open("/tmp/wr_baseline_colloquial.json","w"), ensure_ascii=False)
print("baseline 口語 segs:", len(zh))
PY
```

- [ ] **Step 2: Re-process `de603727d3f8` with the new 書面語 pipeline (set active + re-transcribe), poll to done**

```bash
cd backend && source venv/bin/activate
J=/tmp/wr_cookies.txt
# set the 書面語 pipeline active for this file's re-run
curl -s -b $J -X POST http://localhost:5001/api/active -H 'Content-Type: application/json' \
  -d '{"kind":"pipeline_v6","id":"1443afcb-198b-4821-8e64-47d02bf877f3"}' -w "\nactive %{http_code}\n"
curl -s -b $J -X POST http://localhost:5001/api/files/de603727d3f8/transcribe -H 'Content-Type: application/json' -d '{}' -w "\nenqueue %{http_code}\n"
```
Then poll `/api/files` until `status=='done'` (V6 broadcast budget ~4–6 min; cap `R5_QWEN3_TIMEOUT_SEC=900`). Record wall-clock.

- [ ] **Step 3: Measure register conversion on the LIVE persisted output**

```bash
cd backend && source venv/bin/activate && PYTHONPATH=. python3 - <<'PY'
import json, glob, re
MARK=list("嘅喺唔係咗啦㗎嚟畀")+["俾","嘢","佢","哋","而家","點解"]
NAMES="袁幸堯 姚本輝 潘頓 沙田 悉尼 香港 HIGHLAND BLINK 飛輪八".split()
rp=(glob.glob("data/**/registry.json",recursive=True) or ["data/registry.json"])[0]
d=json.load(open(rp)); files=d if isinstance(d,list) else d.get("files",d)
if isinstance(files,dict): files=list(files.values())
f=[x for x in files if x.get("id")=="de603727d3f8"][0]
zh=[((r.get("by_lang",{}).get("zh",{}) or {}).get("text") or r.get("zh_text") or "").strip() for r in (f.get("translations") or [])]
txt="".join(zh); mk=sum(txt.count(m) for m in MARK)
overcap=sum(1 for s in zh for ln in re.split(r"\\N|\n",s) if len(ln.strip())>24)
print(f"LIVE 書面語: segs={len(zh)} chars={len(txt)} | residual_markers/100={mk/max(1,len(txt))*100:.2f} (target<=2.0) | over-cap>24={overcap}")
print("sample:", " | ".join(zh[:5]))
PY
```
Expected: residual_markers/100 ≤ 2.0 (prototype hit 0.13); names visibly preserved in sample; over-cap a few segments (clause_split handles).

- [ ] **Step 4: Confirm 口語 pipeline byte-identical (zero regression)**

```bash
cd backend && source venv/bin/activate
# re-activate the 口語 pipeline and re-run, then diff against the Step-1 baseline
J=/tmp/wr_cookies.txt
curl -s -b $J -X POST http://localhost:5001/api/active -H 'Content-Type: application/json' \
  -d '{"kind":"pipeline_v6","id":"4696bbaa-b988-49bd-859c-e742cb365634"}' -w "\nactive %{http_code}\n"
curl -s -b $J -X POST http://localhost:5001/api/files/de603727d3f8/transcribe -H 'Content-Type: application/json' -d '{}' -w "\nenqueue %{http_code}\n"
# (poll to done, then) compare:
PYTHONPATH=. python3 - <<'PY'
import json, glob
base=json.load(open("/tmp/wr_baseline_colloquial.json"))
rp=(glob.glob("data/**/registry.json",recursive=True) or ["data/registry.json"])[0]
d=json.load(open(rp)); files=d if isinstance(d,list) else d.get("files",d)
if isinstance(files,dict): files=list(files.values())
f=[x for x in files if x.get("id")=="de603727d3f8"][0]
now=[(r.get("zh_text") or "").strip() for r in (f.get("translations") or [])]
print("口語 re-run identical to baseline:", now==base, f"({len(base)} vs {len(now)} segs)")
PY
```
Note: LLM output has mild non-determinism even at temp 0.1, so "byte-identical" may be ~near-identical; the real regression gate is that the 口語 pipeline's `refinements.zh` is unchanged (Task 1 test) and it still produces colloquial output. Record the segment-count match + a spot diff in the tracker. (Restore the 書面語 or original active pipeline as desired afterward.)

- [ ] **Step 5: Append results to the tracker + commit**

Append a「## 整合驗證（live end-to-end）」section to `docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md` with: residual_markers/100, over-cap, latency, names-preserved spot-check, 口語-pipeline regression result, and a ✅/⚠️ verdict.

```bash
git add docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md
git commit -m "validation(v6): 書面語 pipeline integration re-run results (de603727d3f8 end-to-end)"
```

---

### Task 7: Documentation (CLAUDE.md)

**Files:**
- Modify: `CLAUDE.md` (add a Completed-Feature entry at the top of「## Completed Features」)

- [ ] **Step 1: Add the entry** (insert directly under the `## Completed Features` line)

```markdown
### V6 粵語書面語 pipeline — two-pass chained refiner（2026-05-31）
- **目標**：新增獨立可揀 V6 pipeline「[v6] 賽馬廣播 (書面語)」輸出現代正式繁體書面語，唔影響現有口語 pipeline。
- **架構（config-only）**：`pipeline_runner._run_v6` 嘅 `refinements[zh]` loop 已支援鏈式 → 新 pipeline `refinements.zh = [口語 refiner f7f72bd9, 書面語 register refiner 9dbe1aa3]`。Pass 2 收 pass 1 已清理嘅粵語，淨係 flip register。零 Python 改動。
- **新檔**：prompt template `config/prompt_templates_v5/refiner/zh_written_register_v6.json`（現代正式書面語、阿拉伯數字、禁過度文言、保成語、byte 保專名）+ refiner profile `9dbe1aa3`（`user_id:null`，reuse LLM `9402593c`）+ pipeline `1443afcb`（`user_id:null`）。移植自 feat branch `ac96d75`/`43d614d`/`42bc3d1`。
- **Validation-First**：prototype（120 真實口語段，真 Ollama qwen3.5-35b）殘餘 marker 16.63→0.13/100、專名 100%、no-op 0.8%；整合 re-run `de603727d3f8` 端到端確認。Tracker：[docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md](docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md)。Spec/Plan：[spec](docs/superpowers/specs/2026-05-31-v6-written-register-design.md) / [plan](docs/superpowers/plans/2026-05-31-v6-written-register-plan.md)。
- **範圍外**：單-pass、EN pipeline、>2 refiner、register flag、per-file toggle。
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(v6): CLAUDE.md entry — 粵語書面語 chained-refiner pipeline"
```

---

## Self-Review

**Spec coverage:** ① approach (two-pass chain) → Tasks 2-4. ② 3 config files → Tasks 2,3,4; test → Task 1. ③ prompt with all locked dials → Task 2 (full content). ④ data flow / chain → Task 4 pipeline JSON. ⑤ error handling / 口語 untouched → Task 1 regression test + Task 6 Step 4. ⑥ testing + integration validation → Tasks 5,6. CLAUDE.md → Task 7. All spec sections covered.

**Placeholder scan:** No TBD/TODO. Every config file has full literal content; the test has full code; commands are concrete. The only judgement step is Task 6 Step 5 (writing tracker prose from measured numbers) — that is inherent to a validation write-up, not a placeholder.

**Type/ID consistency:** IDs consistent across tasks — pipeline `1443afcb-198b-4821-8e64-47d02bf877f3`, refiner `9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa`, template id `refiner/zh_written_register_v6`, 口語 refiner `f7f72bd9-3f27-47a4-92bd-5727f336916a`, LLM `9402593c-184d-4a4d-a160-ebdf55e678e8`, transcribe `82338761-e6ed-47eb-b153-64789ed7327e`, file `de603727d3f8`. `user_id:null` in both new configs. The test references match the file contents byte-for-byte.
