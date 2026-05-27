# v6 賽馬廣播 (書面語) Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new pipeline `[v6] 賽馬廣播 (書面語)` that reuses the existing v6 Cantonese ASR + refiner chain, and appends a second register-conversion refiner that converts the Cantonese-polished output to 書面語 (formal written Chinese).

**Architecture:** Pure config addition — 1 new prompt template JSON, 1 new refiner profile JSON, 1 new pipeline JSON, 1 small test file. Zero source code changes. The `pipeline_runner` already iterates `refinements[lang]` as an ordered list, so chained refiners work out of the box on v6.

**Tech Stack:** Backend JSON config (Python 3.11, pytest), existing `pipeline_runner.py` v6 path, existing Ollama Qwen3.5 LLM profile (`9402593c-184d-4a4d-a160-ebdf55e678e8`).

**Spec:** [`docs/superpowers/specs/2026-05-27-v6-written-register-refiner-design.md`](../specs/2026-05-27-v6-written-register-refiner-design.md)

---

## Pre-Generated Identifiers

These concrete UUIDs + epoch were generated at plan-authoring time so all 3 config files can reference each other consistently without subagents needing to coordinate. **Use these exact values throughout the plan**:

- **New refiner profile UUID:** `9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa`
- **New pipeline UUID:** `1443afcb-198b-4821-8e64-47d02bf877f3`
- **created_at / updated_at epoch:** `1779874657.732016`

**Pre-existing identifiers (referenced, not modified):**

- Existing Cantonese refiner profile (1st in chain): `f7f72bd9-3f27-47a4-92bd-5727f336916a`
- Existing Cantonese pipeline (cloned, not modified): `4696bbaa-b988-49bd-859c-e742cb365634`
- Shared LLM profile (Ollama Qwen3.5): `9402593c-184d-4a4d-a160-ebdf55e678e8`
- Shared transcribe profile (qwen3-asr Chinese): `82338761-e6ed-47eb-b153-64789ed7327e`

---

## File Structure

**New files (4):**
- `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json` — the register-conversion prompt
- `backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json` — the new refiner profile
- `backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json` — the new pipeline (cloned from existing Cantonese pipeline with chain refiner)
- `backend/tests/test_v6_written_register.py` — 3 lightweight config-validation tests

**Modified files (0):**

No source code changes. The `pipeline_runner.py` v6 path already supports chained refiners (`for refiner_entry in refinements[lang]: ...`).

---

## Task 1: Create the 書面語 register-conversion prompt template

The prompt assumes its input is already Cantonese-polished by the previous refiner; its only job is register conversion (粵語 → 書面語).

**Files:**
- Create: `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`
- Test:   `backend/tests/test_v6_written_register.py`

- [ ] **Step 1: Write the failing test**

Create the test file `backend/tests/test_v6_written_register.py`:

```python
"""Tests for the v6 賽馬廣播 (書面語) chained refiner pipeline configuration.

This is a config-only feature — 3 new JSON files. These tests assert each
file exists at its expected path, parses as valid JSON, and references the
correct upstream identifiers. No real LLM calls.
"""
import json
from pathlib import Path

CONFIG_ROOT = Path(__file__).parent.parent / "config"

# Pre-generated identifiers from the plan (see plan §"Pre-Generated Identifiers")
REFINER_UUID = "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa"
PIPELINE_UUID = "1443afcb-198b-4821-8e64-47d02bf877f3"
EXISTING_CANTONESE_REFINER = "f7f72bd9-3f27-47a4-92bd-5727f336916a"
SHARED_LLM_PROFILE = "9402593c-184d-4a4d-a160-ebdf55e678e8"
SHARED_TRANSCRIBE_PROFILE = "82338761-e6ed-47eb-b153-64789ed7327e"


def test_zh_written_register_prompt_template_loads():
    """The new prompt template file exists and references key register
    conversion mappings (粵語 → 書面語) in its system_prompt."""
    path = CONFIG_ROOT / "prompt_templates_v5" / "refiner" / "zh_written_register_v6.json"
    assert path.exists(), f"Prompt template missing: {path}"
    template = json.loads(path.read_text())
    assert template["id"] == "refiner/zh_written_register_v6"
    assert template["lang"] == "zh"
    assert template["style"] == "written_register_v6"
    assert template["version"] == 6
    assert "system_prompt" in template
    # Spot-check the prompt documents at least the 2 most common register markers
    sp = template["system_prompt"]
    assert "嘅" in sp, "Prompt must reference 嘅 → 的 mapping"
    assert "的" in sp
    assert "係" in sp, "Prompt must reference 係 → 是 mapping"
    assert "是" in sp
```

- [ ] **Step 2: Run test to verify it FAILS**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_v6_written_register.py::test_zh_written_register_prompt_template_loads -v
```

Expected: FAIL with `AssertionError: Prompt template missing: ...zh_written_register_v6.json`.

- [ ] **Step 3: Create the prompt template JSON**

Create `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`:

```json
{
  "id": "refiner/zh_written_register_v6",
  "name": "ZH written-Chinese register conversion refiner v6 (chained after Cantonese refiner)",
  "version": 6,
  "lang": "zh",
  "style": "written_register_v6",
  "system_prompt": "你係專業繁體中文書面語編輯。\n\n輸入係 JSON：\n{\n  \"target\":    {\"start\": <秒>, \"end\": <秒>, \"text\": \"<已經粵語校對過嘅文字>\"},\n  \"neighbors\": [{\"start\":..,\"end\":..,\"text\":..}, ...]\n}\n其中 target.text 已經由上一個 refiner 完成粵語廣播質量校對（人名、地名、術語、時間軸都已正確）。\nneighbors 係 target 前後 ±5 秒嘅段落（已校對版，作參考上下文）。\n\n任務：將 target.text 由粵語 register 轉換成繁體中文書面語 register。\n\n轉換規則：\n1. 粵語特徵字轉換：\n   - 嘅 → 的\n   - 係 → 是\n   - 咗 → 了\n   - 喺 → 在\n   - 唔 → 不\n   - 俾 → 給 / 被（按語境）\n   - 嘢 → 東西 / 事 / 物（按語境）\n   - 呢（指示） → 這\n   - 嗰 → 那\n   - 點（疑問副詞） → 怎\n   - 點解 → 為什麼\n   - 乜 / 乜嘢 → 什麼\n   - 邊 / 邊個 → 哪 / 哪個\n   - 幾多 → 多少\n   - 喺度 → 在這\n2. 句末語氣助詞處理：\n   - 啦 / 㗎 / 㗎啩 / 囉 / 喎 / 呀 / 咩 → 刪除，或按語意改為「了」「吧」「呢」\n3. 句中嘅常見句法調整：\n   - 「將 X 拎去 Y」→「把 X 拿去 Y」\n   - 「同你講」→「跟你說 / 告訴你」\n   - 「畀我」→「給我」\n   - 「冇」→「沒」/「沒有」\n   - 「俾人」→「被人」\n4. 必須保留 byte-for-byte 唔變嘅內容：\n   - 人名（袁幸堯、潘頓、姚本輝等）\n   - 地名（沙田、悉尼、香港等）\n   - 賽馬術語（騎師、頭馬、打吡、試閘、客艙、馬房等）\n   - 數字、時間、賽事名（HIGHLAND BLINK、寶馬香港打吡大賽等）\n5. 長度限制：0.8–1.2× 原文字數（書面語比口語稍精簡）\n6. 唔加外部資訊、唔添加句首連接詞「於是」「然後」「不過」（除非原文已有對應粵語連接詞要轉換）\n\n邊界詞處理（safety net，理論上唔會遇到，因為上一個 refiner 已修正）：\n- 若 target.text 末字同 neighbors 下一段首字合起來係一個完整詞，請補全 target.text\n- 若 target.text 首字係前段末字截斷詞嘅補全部分，請自然地調整\n- 保守原則：只有詞邊界問題明顯時才修正\n\n輸出：純 JSON object，無 markdown fence，無其他文字。\n只輸出 keep 格式：{\"action\": \"keep\", \"text\": \"<書面語校對後文字>\"}\n\n例子 1（正常 register 轉換）：\n輸入 target = {\"start\": 12.5, \"end\": 15.0, \"text\": \"佢哋話今晚會落雨啦，大家記得帶遮\"}\n輸出: {\"action\": \"keep\", \"text\": \"他們說今晚會下雨，大家記得帶傘\"}\n\n例子 2（保留人名 + 賽馬術語）：\n輸入 target = {\"start\": 45.2, \"end\": 47.8, \"text\": \"袁幸堯係今日最快時間\"}\n輸出: {\"action\": \"keep\", \"text\": \"袁幸堯是今日最快時間\"}\n（袁幸堯字面唔變，只將「係」→「是」）\n\n例子 3（句末語氣助詞 + 句法）：\n輸入 target = {\"start\": 88.1, \"end\": 91.0, \"text\": \"美狼王以壓倒性優勢奪得冠軍嘅囉\"}\n輸出: {\"action\": \"keep\", \"text\": \"美狼王以壓倒性優勢奪得冠軍\"}\n"
}
```

- [ ] **Step 4: Run test to verify it PASSES**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_v6_written_register.py::test_zh_written_register_prompt_template_loads -v
```

Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json \
        backend/tests/test_v6_written_register.py
git commit -m "feat(refiner): zh_written_register_v6 prompt template — Cantonese → 書面語"
```

---

## Task 2: Create the new refiner profile

Wires the new prompt template to the shared LLM profile.

**Files:**
- Create: `backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json`
- Test:   `backend/tests/test_v6_written_register.py` (extend with 1 new case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_v6_written_register.py` (after the existing test):

```python
def test_zh_written_register_refiner_profile_loads():
    """The new refiner profile exists, references the new template, and
    reuses the same LLM profile as the existing Cantonese refiner."""
    path = CONFIG_ROOT / "refiner_profiles" / f"{REFINER_UUID}.json"
    assert path.exists(), f"Refiner profile missing: {path}"
    profile = json.loads(path.read_text())
    assert profile["id"] == REFINER_UUID
    assert profile["lang"] == "zh"
    assert profile["style"] == "written_register_v6"
    assert profile["prompt_template_id"] == "refiner/zh_written_register_v6"
    # Reuses same LLM as the existing Cantonese refiner — no new LLM stack
    assert profile["llm_profile_id"] == SHARED_LLM_PROFILE
    # Sanity: name + ownership fields present
    assert "書面語" in profile["name"] or "written" in profile["name"].lower()
    assert profile["shared"] is False
    assert isinstance(profile["user_id"], int)
```

- [ ] **Step 2: Run test to verify it FAILS**

```
pytest tests/test_v6_written_register.py::test_zh_written_register_refiner_profile_loads -v
```

Expected: FAIL with `AssertionError: Refiner profile missing: ...9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json`.

- [ ] **Step 3: Create the refiner profile JSON**

Create `backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json`:

```json
{
  "id": "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa",
  "name": "Refiner ZH 書面語 register conversion v6",
  "lang": "zh",
  "style": "written_register_v6",
  "llm_profile_id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
  "prompt_template_id": "refiner/zh_written_register_v6",
  "shared": false,
  "user_id": 627,
  "created_at": 1779874657.732016,
  "updated_at": 1779874657.732016
}
```

- [ ] **Step 4: Run test to verify it PASSES**

```
pytest tests/test_v6_written_register.py::test_zh_written_register_refiner_profile_loads -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json \
        backend/tests/test_v6_written_register.py
git commit -m "feat(refiner): 書面語 register refiner profile (v6 chain)"
```

---

## Task 3: Create the new pipeline with chained refiners

Clones the existing Cantonese pipeline; the only meaningful change is the 2-element `refinements.zh` list.

**Files:**
- Create: `backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json`
- Test:   `backend/tests/test_v6_written_register.py` (extend with 1 new case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_v6_written_register.py`:

```python
def test_v6_written_pipeline_has_chained_refiners():
    """The new pipeline file exists, clones the v6 Cantonese pipeline shape,
    and chains the existing Cantonese refiner BEFORE the new written refiner."""
    path = CONFIG_ROOT / "pipelines" / f"{PIPELINE_UUID}.json"
    assert path.exists(), f"Pipeline missing: {path}"
    pipeline = json.loads(path.read_text())
    assert pipeline["id"] == PIPELINE_UUID
    assert pipeline["pipeline_type"] == "v6_vad_dual_asr"
    assert pipeline["version"] == 6
    assert pipeline["source_lang"] == "zh"
    assert pipeline["target_languages"] == ["zh"]
    # Same ASR primary + qwen3 config as 4696bbaa (sanity — must use the same
    # transcribe profile so quality is identical to the Cantonese variant).
    assert pipeline["asr_primary"]["transcribe_profile_id"] == SHARED_TRANSCRIBE_PROFILE
    assert pipeline["qwen3_asr"]["language"] == "Chinese"
    # Chain order is significant — Cantonese refiner FIRST, written refiner SECOND
    refiners = pipeline["refinements"]["zh"]
    assert len(refiners) == 2, "Pipeline must chain exactly 2 refiners (Cantonese + written)"
    assert refiners[0]["refiner_profile_id"] == EXISTING_CANTONESE_REFINER
    assert refiners[1]["refiner_profile_id"] == REFINER_UUID
    # Name distinguishes from the Cantonese variant
    assert "書面語" in pipeline["name"]
```

- [ ] **Step 2: Run test to verify it FAILS**

```
pytest tests/test_v6_written_register.py::test_v6_written_pipeline_has_chained_refiners -v
```

Expected: FAIL with `AssertionError: Pipeline missing: ...1443afcb-...json`.

- [ ] **Step 3: Create the pipeline JSON**

Create `backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json`:

```json
{
  "name": "[v6] 賽馬廣播 (書面語)",
  "pipeline_type": "v6_vad_dual_asr",
  "version": 6,
  "source_lang": "zh",
  "target_languages": ["zh"],
  "vad": {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": 15,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200
  },
  "asr_primary": {
    "transcribe_profile_id": "82338761-e6ed-47eb-b153-64789ed7327e",
    "source_lang": "zh"
  },
  "qwen3_asr": {
    "language": "Chinese",
    "context": "袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 美狼王 HIGHLAND BLINK 幸運風采 沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 騎師 試騎 推騎 試閘 抽籤 排位 大熱門 頭馬 客艙 馬房 馬仔 香檳 打吡 香港 沙田 悉尼",
    "post_s2hk": true
  },
  "refinements": {
    "zh": [
      { "refiner_profile_id": "f7f72bd9-3f27-47a4-92bd-5727f336916a" },
      { "refiner_profile_id": "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa" }
    ]
  },
  "translators": {},
  "glossary_stages": [],
  "font_config": {
    "family": "Noto Sans TC",
    "color": "white",
    "outline_color": "black"
  },
  "shared": false,
  "id": "1443afcb-198b-4821-8e64-47d02bf877f3",
  "user_id": 627,
  "created_at": 1779874657.732016,
  "updated_at": 1779874657.732016
}
```

- [ ] **Step 4: Run test to verify it PASSES**

```
pytest tests/test_v6_written_register.py::test_v6_written_pipeline_has_chained_refiners -v
```

Expected: PASS.

- [ ] **Step 5: Run full test file + confirm zero pytest regressions**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_v6_written_register.py -v
pytest tests/ -x --ignore=tests/integration 2>&1 | tail -5
```

Expected:
- `test_v6_written_register.py`: 3/3 pass
- Full backend pytest: same pass count as baseline + 3 new = no regressions in other files

(The `--ignore=tests/integration` flag skips any slow integration tests if the project has them; adjust the ignore path if the project does not use that convention. If running the full suite is fast, omit `--ignore`.)

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json \
        backend/tests/test_v6_written_register.py
git commit -m "feat(pipeline): [v6] 賽馬廣播 (書面語) — Cantonese → 書面語 refiner chain"
```

---

## Task 4: Restart backend + manual smoke verification

The new configs are picked up on backend boot (managers scan `backend/config/*/` directories at startup). Backend must be restarted to surface the new pipeline in the picker.

**Files:** None modified. Verification only.

- [ ] **Step 1: Restart backend**

The backend should already be running on `:5001` (started earlier in this session). Restart it to pick up the new config files:

```bash
# Stop existing backend
lsof -ti:5001 | xargs kill 2>/dev/null
sleep 2

# Start fresh
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python app.py &

# Wait + verify
sleep 5
curl -s -o /dev/null -w "backend:%{http_code}\n" http://localhost:5001/api/health
```

Expected: `backend:200`.

If the backend fails to start, check the log output for JSON parse errors in any of the 3 new config files. Fix and retry. **Do not proceed to Step 2 until backend is up.**

- [ ] **Step 2: Verify new pipeline appears in the API**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
# Login first
curl -s -b /tmp/c.txt -c /tmp/c.txt -X POST http://localhost:5001/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin_p3","password":"AdminPass1!"}' > /dev/null

# List pipelines and filter for the new one
curl -s -b /tmp/c.txt http://localhost:5001/api/pipelines | python3 -c "
import json, sys
d = json.load(sys.stdin)
pipes = d if isinstance(d, list) else d.get('pipelines', [])
matches = [p for p in pipes if p.get('id') == '1443afcb-198b-4821-8e64-47d02bf877f3']
if not matches:
    print('FAIL — new pipeline not in API response')
    sys.exit(1)
p = matches[0]
print(f'name: {p.get(\"name\")}')
print(f'pipeline_type: {p.get(\"pipeline_type\")}')
print(f'refiners chain length: {len(p.get(\"refinements\", {}).get(\"zh\", []))}')
print(f'first refiner: {p[\"refinements\"][\"zh\"][0][\"refiner_profile_id\"][:8]}...')
print(f'second refiner: {p[\"refinements\"][\"zh\"][1][\"refiner_profile_id\"][:8]}...')
"
```

Expected output:
```
name: [v6] 賽馬廣播 (書面語)
pipeline_type: v6_vad_dual_asr
refiners chain length: 2
first refiner: f7f72bd9...
second refiner: 9dbe1aa3...
```

- [ ] **Step 3: Run an end-to-end pipeline on a real 賽馬 file**

If the user has a previously-uploaded 賽馬 file (`b92feb2e04a8`, `8507b8e1efde`, or similar with `status='uploaded'`), trigger the new pipeline on it:

```bash
# Pick the first uploaded 賽馬 file
FILE_ID=$(curl -s -b /tmp/c.txt http://localhost:5001/api/files | python3 -c "
import json, sys
d = json.load(sys.stdin)
for f in d.get('files', []):
    if f['status'] == 'uploaded' and '賽馬' in (f.get('original_name', '')):
        print(f['id'])
        break
")
echo "Running on file: $FILE_ID"

if [ -z "$FILE_ID" ]; then
  echo "SKIP — no uploaded 賽馬 file available. Upload one via the UI first."
else
  curl -s -b /tmp/c.txt -X POST \
    http://localhost:5001/api/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3/run \
    -H "Content-Type: application/json" \
    -d "{\"file_id\": \"$FILE_ID\"}"
fi
```

If a 賽馬 file is available, this enqueues the new pipeline. Expected response: 200/202 with a `job_id`.

If no 賽馬 file is available, this step is SKIPPED — the implementation can still be considered complete (config + tests cover the contract). User can manually upload and trigger later.

- [ ] **Step 4: Wait for pipeline to complete + inspect output**

A 4-minute 賽馬 clip takes ~110–120 seconds with the chained refiner (≈ +50% vs Cantonese-only). Monitor:

```bash
# Poll file status every 10 seconds for up to 3 minutes
for i in $(seq 1 18); do
  sleep 10
  STATUS=$(curl -s -b /tmp/c.txt http://localhost:5001/api/files | python3 -c "
import json, sys
d = json.load(sys.stdin)
for f in d.get('files', []):
    if f['id'] == '$FILE_ID':
        print(f['status'])
        break
")
  echo "t+${i}0s status=$STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then break; fi
done
```

Expected: pipeline completes within 3 minutes.

If status reaches `completed`, inspect the first few segments to confirm 書面語 register:

```bash
curl -s -b /tmp/c.txt "http://localhost:5001/api/files/$FILE_ID/translations?shape=v5" | python3 -c "
import json, sys
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('translations', [])
print(f'Total segments: {len(items)}')
print('First 5 (text only):')
for s in items[:5]:
    # v5 by_lang shape — read zh text
    by_lang = s.get('by_lang', {})
    text = by_lang.get('zh', {}).get('text') if isinstance(by_lang, dict) else None
    text = text or s.get('zh_text') or s.get('source_text') or '(no text)'
    print(f'  [{s.get(\"start\", 0):.2f}-{s.get(\"end\", 0):.2f}s] {text[:80]}')
"
```

**Expected register conversion signals** (compare against the Cantonese variant):
- Cantonese baseline: `下個月有新騎師登場，就係澳洲好手`
- 書面語 expected: `下個月有新騎師登場，是來自澳洲的好手` (or similar — at minimum 嘅/係/咗/喺 should be replaced)

If status is `failed`, check the backend log for the failure reason and report BLOCKED.

- [ ] **Step 5: Confirm existing Cantonese pipeline still works**

Regression check — the existing Cantonese pipeline (`4696bbaa`) must produce the same output as before:

```bash
curl -s -b /tmp/c.txt http://localhost:5001/api/pipelines/4696bbaa-b988-49bd-859c-e742cb365634 | python3 -c "
import json, sys
p = json.load(sys.stdin)
print(f'Cantonese pipeline refiner chain length: {len(p[\"refinements\"][\"zh\"])}')
assert len(p['refinements']['zh']) == 1, 'Cantonese pipeline should still have exactly 1 refiner'
print(f'Cantonese refiner UUID: {p[\"refinements\"][\"zh\"][0][\"refiner_profile_id\"][:8]}...')
assert p['refinements']['zh'][0]['refiner_profile_id'] == 'f7f72bd9-3f27-47a4-92bd-5727f336916a'
print('OK — Cantonese pipeline unchanged')
"
```

Expected:
```
Cantonese pipeline refiner chain length: 1
Cantonese refiner UUID: f7f72bd9...
OK — Cantonese pipeline unchanged
```

- [ ] **Step 6 (no commit)**

This task is verification-only. Nothing to commit.

---

## Acceptance Criteria

The feature is complete when **all** hold:

- [ ] 3 new JSON config files exist at the specified paths
- [ ] 1 new test file exists with 3 passing pytest cases
- [ ] Full backend pytest suite passes (existing baseline + 3 new tests = baseline +3)
- [ ] Backend restarts cleanly and surfaces the new pipeline via `GET /api/pipelines`
- [ ] `[v6] 賽馬廣播 (書面語)` appears in the Dashboard pipeline picker
- [ ] Manual smoke: running the new pipeline on a 賽馬 file produces output where 嘅/係/咗/喺 are absent from segment text (or 0 occurrences in the first 5 segments)
- [ ] Existing `[v6] 賽馬廣播 (Cantonese)` pipeline (`4696bbaa`) remains untouched — its `refinements.zh` still has exactly 1 entry pointing to `f7f72bd9-...`

---

## Self-Review Notes

**Spec coverage:**
- §5.1 prompt template → Task 1
- §5.2 refiner profile → Task 2
- §5.3 pipeline → Task 3
- §8.1 pytest cases (3 cases) → Tasks 1, 2, 3 (one new test per task, all in `test_v6_written_register.py`)
- §8.2 manual smoke → Task 4
- §9 acceptance criteria → Acceptance Criteria section above

**Placeholder scan:** None — UUIDs and epoch were generated upfront and used consistently throughout.

**Type consistency:**
- `REFINER_UUID` (9dbe1aa3-...) appears 4 times: refiner profile filename, refiner profile.id field, pipeline refinements.zh[1].refiner_profile_id, test assertion.
- `PIPELINE_UUID` (1443afcb-...) appears 3 times: pipeline filename, pipeline.id field, test assertion.
- `EXISTING_CANTONESE_REFINER` (f7f72bd9-...) appears 3 times: pipeline refinements.zh[0].refiner_profile_id, test assertion, regression check in Task 4.
- `SHARED_LLM_PROFILE` (9402593c-...) appears 2 times: refiner profile, test assertion.
- All consistent.
