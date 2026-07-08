# 賽馬翻譯質量 P0 — racing.txt 補強 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用「參考老師」驗證閉環，empirically 確認 racing.txt 加賽馬術語/騎師/單位規則後有效且零 regression，然後先改真檔。

**Architecture:** 全部 dev-side 量度（唔掂 :5001 production）。一個候選 prompt 檔（`racing_candidate.txt`）+ 一個 pure-logic harness（term 命中偵測 / 時間軸對齊）+ MT runner（override `crosslang_mt._STYLE_CACHE["racing"]` 行真 translate 路徑，舊 vs 新 prompt）+ 4 個實驗（A 術語命中 / B regression / C Reset 獨立 / D 對參考重量度）。全部 gate 通過先將候選內容套落真 `racing.txt`。

**Tech Stack:** Python 3.9、本地 Ollama `qwen3.5:35b-a3b-mlx-bf16`（MT + judge）、`translation/crosslang_mt.py`、PaddleOCR 已提取嘅專業參考（`diagnosis/pro_*.json`）、pytest（純邏輯）。

## Global Constraints

- 工作目錄：`/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/.claude/worktrees/quality-standard`（下稱 `$WT`）。
- Production data READ-ONLY：`$MAIN/backend/data/registry.json`、`$MAIN/backend/config/glossaries/`、源片 —— 只讀。`$MAIN` = `/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai`。
- **唔准掂 :5001**；MT/judge 只經本地 Ollama `http://localhost:11434/api/chat`（POST `{model, stream:false, options:{temperature}, messages}`）。
- **唔准改真 `backend/config/mt_style_prompts/racing.txt` 直到 Task 8**（gate 通過先改）。
- Ollama 慢（~10-50s/call，79GB model cold reload 更慢）→ script timeout ≥420s/call；實驗用 background 跑。
- Python 3.9 typing（`List/Dict/Optional`）。Immutable：唔 mutate 入參。
- Harness + 實驗 script 全部入 `$WT/docs/superpowers/specs/2026-07-08-quality-standard-research/protos/racing_p0/`（下稱 `$P0`）。
- pytest 用 main repo venv：`source "$MAIN/backend/venv/bin/activate"`。
- 兩片 id：`f66d9705f78d`（Test Footage 1，29 cue）、`28deab03a71c`（Test Footage 2，21 cue）；專業參考：`$WT/docs/superpowers/specs/2026-07-08-quality-standard-research/diagnosis/pro_<fid>.json`（`[{start,end,text}]`）。
- Commit message `<type>: <desc>`，無 attribution footer。

---

### Task 1: 候選 prompt `racing_candidate.txt`

**Files:**
- Create: `$P0/racing_candidate.txt`（= 現行 racing.txt 內容 + 本 task 的插入）

**Interfaces:**
- Produces: `$P0/racing_candidate.txt`（完整 racing prompt，含 D 術語 5 條 + G Luke + J 單位 + 示例六）。母系/Reset 那一條術語有唯一標記字串 `【母系規則】` 做前綴，方便 Task 6 程式化剝走做 no-Reset variant。

- [ ] **Step 1: 複製現行 racing.txt**

```bash
mkdir -p "$P0"
cp "$MAIN/backend/config/mt_style_prompts/racing.txt" "$P0/racing_candidate.txt"
```

- [ ] **Step 2: D 段加 5 條術語** — 將 `racing_candidate.txt` 內 D 段結尾 `the map→跑法部署。` 換成（`Edit` old→new）：

old:
```
the map→跑法部署。
```
new（一行內，`、` 分隔；`【母系規則】` 標記只為程式定位，屬 prompt 可見文字）：
```
the map→跑法部署、track work／morning work／gallops→晨操（賽事語境的 work 指晨操，非「工作」或「體力」）、sprinter→短途賽駒（sprint 作距離時→短途）、closer／back in the field／off the pace／run on late→後上（賽駒）、newcomer／first-timer／debutant→初次上陣（新馬）、【母系規則】out of a … mare→母系血統；「out of a X mare」中的 X 是父系／外祖父名，屬專名須原樣保留，不可譯成普通詞（例：out of a Reset mare 的 Reset 不可譯「重置」）。
```

- [ ] **Step 3: G 段騎師名單加 Luke** — 將 `David Hayes→希斯。` 換成 `David Hayes→希斯、Luke Ferraris→霍宏聲。`

- [ ] **Step 4: J 段強化單位** — 將 `數字、時間、距離保留阿拉伯數字（如「1600 米」「3 檔」）。` 換成 `數字、時間、距離保留阿拉伯數字（如「1600 米」「3 檔」）。距離單位一律用「米」，絕不可用「公尺」。`

- [ ] **Step 5: 加示例六**（喺示例五之後、`racing_candidate.txt` 檔末）：

```
示例六（賽馬 work＝晨操；母系血統，X 為父系名須保留）：
英文：His track work's been very good and he's out of a Reset mare.
中文：牠晨操表現理想，母系源自「Reset」。
```

- [ ] **Step 6: 核對 + Commit**

```bash
grep -c "晨操\|後上\|初次上陣\|霍宏聲\|公尺\|母系規則" "$P0/racing_candidate.txt"   # 期望 ≥6 命中行
git add "$P0/racing_candidate.txt"
git commit -m "test(racing-p0): 候選 racing.txt prompt（D 術語5條+G Luke+J 單位+示例六，母系規則標記）"
```

---

### Task 2: Harness 純邏輯 `refharness.py` + 單元測試

**Files:**
- Create: `$P0/refharness.py`
- Test: `$P0/test_refharness.py`

**Interfaces:**
- Produces:
  - `load_pair(fid) -> dict` → `{"mot": [{start,end,en,zh}], "pro": [{start,end,text}]}`（讀 registry + diagnosis/pro_<fid>.json）
  - `find_cue(mot, en_contains) -> Optional[dict]`（en 欄含子串，大小寫不敏感，返首個）
  - `term_accept(name, zh) -> bool`（term 命中判定）
  - `overlap_pro(pro, start, end) -> str`（時間軸重疊拼接專業文字）

- [ ] **Step 1: 寫 failing test**

```python
# $P0/test_refharness.py
import refharness as rh


def test_term_accept_track_work():
    assert rh.term_accept("track_work", "牠晨操表現理想")
    assert not rh.term_accept("track_work", "他在該場地的表現出色")


def test_term_accept_closer():
    assert rh.term_accept("closer", "後上賽駒佔優")
    assert not rh.term_accept("closer", "在後方的馬匹")


def test_term_accept_newcomer():
    assert rh.term_accept("newcomer", "對初次上陣的賽駒有利")
    assert rh.term_accept("newcomer", "新馬受惠")
    assert not rh.term_accept("newcomer", "對新來者有利")


def test_term_accept_unit_rejects_gongchi():
    assert rh.term_accept("unit", "今次扳上2000米")
    assert not rh.term_accept("unit", "二千公尺又是另一級距")


def test_term_accept_reset_protected():
    assert rh.term_accept("reset", "母系源自「Reset」")
    assert rh.term_accept("reset", "他的外祖父是Reset")
    assert not rh.term_accept("reset", "他是一匹未重置的母馬")


def test_find_cue_substring_ci():
    mot = [{"start": 0, "end": 1, "en": "His TRACK works very good", "zh": "x"}]
    assert rh.find_cue(mot, "track works")["en"].startswith("His")
    assert rh.find_cue(mot, "nonexistent") is None


def test_overlap_pro_joins_overlapping():
    pro = [{"start": 0, "end": 5, "text": "A"}, {"start": 5, "end": 10, "text": "B"},
           {"start": 10, "end": 12, "text": "C"}]
    assert rh.overlap_pro(pro, 4, 6) == "A B"
    assert rh.overlap_pro(pro, 20, 22) == ""
```

- [ ] **Step 2: 跑，睇 fail**

Run: `cd "$P0" && source "$MAIN/backend/venv/bin/activate" && pytest test_refharness.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'refharness'`

- [ ] **Step 3: 實作 `refharness.py`**

```python
"""賽馬 P0 驗證 harness — 純邏輯（無 LLM、無 side effect）。"""
import json
import os
from typing import Dict, List, Optional

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
REG = MAIN + "/backend/data/registry.json"
DIAG = (MAIN + "/.claude/worktrees/quality-standard/docs/superpowers/specs"
        "/2026-07-08-quality-standard-research/diagnosis")

# term 名 → 判定函數。合格 = 期望術語出現 / 禁用詞不出現。
_NEWCOMER = ("初次上陣", "初出", "新馬")


def term_accept(name: str, zh: str) -> bool:
    z = zh or ""
    if name == "track_work":
        return "晨操" in z
    if name == "closer":
        return "後上" in z
    if name == "newcomer":
        return any(t in z for t in _NEWCOMER)
    if name == "unit":
        return "公尺" not in z
    if name == "reset":
        # 保護成功 = 冇譯「重置」，且保留 Reset 或譯母系血統
        return ("重置" not in z) and (("Reset" in z) or ("reset" not in z.lower()) or ("母系" in z))
    raise ValueError("unknown term " + name)


def find_cue(mot: List[dict], en_contains: str) -> Optional[dict]:
    key = (en_contains or "").lower()
    for c in mot:
        if key in (c.get("en") or "").lower():
            return c
    return None


def overlap_pro(pro: List[dict], start: float, end: float) -> str:
    parts = []
    for c in pro:
        if c.get("end", 0) > start and c.get("start", 0) < end:
            parts.append(c.get("text", ""))
    return " ".join(parts)


def load_pair(fid: str) -> Dict[str, list]:
    reg = json.load(open(REG))
    e = reg[fid]
    mot = []
    for r in e.get("translations", []):
        zh = ((r.get("by_lang") or {}).get("zh") or {}).get("text") or r.get("zh_text") or ""
        mot.append({"start": r.get("start"), "end": r.get("end"),
                    "en": r.get("en_text") or "", "zh": zh})
    pro_path = os.path.join(DIAG, f"pro_{fid}.json")
    pro_raw = json.load(open(pro_path))
    pro = pro_raw if isinstance(pro_raw, list) else pro_raw.get("cues", [])
    return {"mot": mot, "pro": pro}
```

- [ ] **Step 4: 跑，全 PASS**

Run: `pytest test_refharness.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add "$P0/refharness.py" "$P0/test_refharness.py"
git commit -m "test(racing-p0): refharness 純邏輯（term_accept/find_cue/overlap_pro/load_pair）+ 8 tests"
```

---

### Task 3: MT runner `mtrun.py`（prompt override + Ollama）

**Files:**
- Create: `$P0/mtrun.py`

**Interfaces:**
- Consumes: `translation.crosslang_mt`（override `_STYLE_CACHE["racing"]`）
- Produces:
  - `ollama(system, user, temperature=0.3, timeout=420) -> str`
  - `run_mt(cues, prompt_text, temperature=0.3) -> List[str]`（cues=`[{start,end,text}]`，返 zh 文字 list；行真 `crosslang_mt.translate_segments` 路徑，只 override prompt）
  - `read_prompt(path) -> str`、`BASELINE_PATH`（真 racing.txt）、`CANDIDATE_PATH`

- [ ] **Step 1: 實作**

```python
"""MT runner — 行真 crosslang_mt 路徑，只 override racing prompt（唔改真檔）。"""
import json
import sys
import urllib.request
from typing import List

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
sys.path.insert(0, MAIN + "/backend")
import translation.crosslang_mt as cmt  # noqa: E402

MODEL = "qwen3.5:35b-a3b-mlx-bf16"
BASELINE_PATH = MAIN + "/backend/config/mt_style_prompts/racing.txt"
CANDIDATE_PATH = (MAIN + "/.claude/worktrees/quality-standard/docs/superpowers/specs"
                  "/2026-07-08-quality-standard-research/protos/racing_p0/racing_candidate.txt")


def read_prompt(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def ollama(system: str, user: str, temperature: float = 0.3, timeout: int = 420) -> str:
    body = json.dumps({"model": MODEL, "stream": False,
                       "options": {"temperature": temperature},
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def run_mt(cues: List[dict], prompt_text: str, temperature: float = 0.3) -> List[str]:
    # override 真檔載入 — translate_segments 會用呢個 cached prompt
    cmt._STYLE_CACHE["racing"] = prompt_text
    llm = lambda s, u: ollama(s, u, temperature=temperature)
    out = cmt.translate_segments(cues, "en", "zh", llm, style="racing")
    return [o["text"] for o in out]
```

- [ ] **Step 2: Smoke 測（1 cue，真 Ollama）**

Run:
```bash
cd "$P0" && python3 -c "
import mtrun
zh = mtrun.run_mt([{'start':0,'end':1,'text':'His track works very good.'}], mtrun.read_prompt(mtrun.CANDIDATE_PATH))
print(repr(zh[0]))
"
```
Expected：印出一句繁體中文（理想含「晨操」；呢步只證 runner 通，未係正式量度）。

- [ ] **Step 3: Commit**

```bash
git add "$P0/mtrun.py"
git commit -m "test(racing-p0): mtrun — prompt-override MT runner + Ollama（行真 crosslang_mt 路徑）"
```

---

### Task 4: 實驗 A — 目標術語命中（舊 vs 新，各 3 次）

**Files:**
- Create: `$P0/exp_a.py`
- Modify: `$WT/docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md`（新建/追加）

**Interfaces:**
- Consumes: `refharness`（find_cue/term_accept/load_pair）、`mtrun`（run_mt/read_prompt/paths）

- [ ] **Step 1: 實作 exp_a.py**

```python
"""實驗 A：目標術語命中率（舊 racing.txt vs 候選，各 cue 重跑 3 次）。"""
import json
import refharness as rh
import mtrun

RUNS = 3
# (fid, en 子串定位 cue, term 名)
TARGETS = [
    ("f66d9705f78d", "in his work", "track_work"),
    ("28deab03a71c", "track works", "track_work"),
    ("f66d9705f78d", "back in the field", "closer"),
    ("28deab03a71c", "newcomers", "newcomer"),
    ("f66d9705f78d", "another step", "unit"),
    ("f66d9705f78d", "reset mare", "reset"),
]


def main():
    old = mtrun.read_prompt(mtrun.BASELINE_PATH)
    new = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    pairs = {fid: rh.load_pair(fid) for fid in {t[0] for t in TARGETS}}
    rows = []
    for fid, sub, term in TARGETS:
        cue = rh.find_cue(pairs[fid]["mot"], sub)
        assert cue, f"cue not found: {fid} / {sub}"
        seg = [{"start": cue["start"], "end": cue["end"], "text": cue["en"]}]
        rec = {"fid": fid, "term": term, "en": cue["en"], "old": [], "new": []}
        for _ in range(RUNS):
            rec["old"].append(mtrun.run_mt(seg, old)[0])
            rec["new"].append(mtrun.run_mt(seg, new)[0])
        rec["old_hit"] = sum(rh.term_accept(term, z) for z in rec["old"])
        rec["new_hit"] = sum(rh.term_accept(term, z) for z in rec["new"])
        rows.append(rec)
        print(f"[{term}] {fid} old {rec['old_hit']}/{RUNS} → new {rec['new_hit']}/{RUNS}")
        for z in rec["new"]:
            print("    new:", z[:60])
    json.dump(rows, open("exp_a_results.json", "w"), ensure_ascii=False, indent=1)
    passed = all(r["new_hit"] >= 2 for r in rows)
    print("\nGATE A:", "PASS" if passed else "FAIL",
          "(每 term new_hit ≥ 2/3)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑（background，真 LLM，36 次 MT call）**

Run: `cd "$P0" && python3 exp_a.py`（若逾時，改 background；每 call ~10-50s，總約 10-30 分鐘）
Expected：每 term `new_hit ≥ 2/3`，`GATE A: PASS`。若某 term FAIL → 記錄，於 Task 8 決策（可能要調 prompt 措辭再重跑本 task）。

- [ ] **Step 3: 記錄入 tracker**

新建 `$WT/docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md`，寫 `## 實驗 A — 術語命中` section：逐 term 列 `old_hit/3 → new_hit/3` + 2-3 個 new 輸出樣本 + GATE A PASS/FAIL。

- [ ] **Step 4: Commit**

```bash
git add "$P0/exp_a.py" "$P0/exp_a_results.json" "$WT/docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md"
git commit -m "test(racing-p0): 實驗A 術語命中 — <PASS/FAIL 摘要>"
```

---

### Task 5: 實驗 B — Regression（全 50 cue，新 vs 舊 judge）

**Files:**
- Create: `$P0/exp_b.py`
- Modify: validation tracker（追加 `## 實驗 B`）

**Interfaces:**
- Consumes: `refharness.load_pair`、`mtrun`（run_mt/ollama/paths）

- [ ] **Step 1: 實作 exp_b.py**

```python
"""實驗 B：regression — 兩片全 cue 用新 prompt，逐 cue judge「新 vs 舊」有冇引入新錯。"""
import json
import re
import refharness as rh
import mtrun

FIDS = ["f66d9705f78d", "28deab03a71c"]
JUDGE_SYS = (
    "你係英譯中字幕質量審核員。俾你一句英文原文、譯法A、譯法B。"
    "判斷 B 相對 A 有冇引入「A 冇而 B 有」的意思錯誤／漏譯／幻覺／語體漂移（粵語口語或公文腔）。"
    "淨係睇 B 有冇變差，唔使理風格長短差異。只回 JSON：{\"regression\": true/false, \"why\": \"…\"}")
_J = re.compile(r'"regression"\s*:\s*(true|false)')


def judge(en, a, b):
    u = f"英文：{en}\n譯法A（舊）：{a}\n譯法B（新）：{b}\nB 相對 A 有冇引入新錯誤？"
    raw = mtrun.ollama(JUDGE_SYS, u, temperature=0.2)
    m = _J.search(raw or "")
    return (m and m.group(1) == "true"), raw


def main():
    old_p = mtrun.read_prompt(mtrun.BASELINE_PATH)
    new_p = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    regressions = []
    total = 0
    for fid in FIDS:
        mot = rh.load_pair(fid)["mot"]
        cues = [{"start": c["start"], "end": c["end"], "text": c["en"]} for c in mot if c["en"].strip()]
        old_zh = mtrun.run_mt(cues, old_p)
        new_zh = mtrun.run_mt(cues, new_p)
        for i, c in enumerate(cues):
            total += 1
            reg, raw = judge(c["text"], old_zh[i], new_zh[i])
            if reg:
                regressions.append({"fid": fid, "en": c["text"],
                                    "old": old_zh[i], "new": new_zh[i], "why": raw[:200]})
    json.dump(regressions, open("exp_b_results.json", "w"), ensure_ascii=False, indent=1)
    print(f"GATE B: {'PASS' if not regressions else 'FAIL'} — {len(regressions)}/{total} regressions")
    for r in regressions:
        print(f"  {r['fid']}: {r['en'][:40]}\n    舊:{r['old'][:40]}\n    新:{r['new'][:40]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑（background，~150 MT + 50 judge call，較長）**

Run: `cd "$P0" && python3 exp_b.py`（建議 background）
Expected：`GATE B: PASS`（0 regression）。若有 regression → 逐個人手覆核（judge 可能誤報）；真 regression 要調 prompt 或撤對應術語再重跑。

- [ ] **Step 3: 記 tracker `## 實驗 B` + Commit**

```bash
git add "$P0/exp_b.py" "$P0/exp_b_results.json" "$WT/docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md"
git commit -m "test(racing-p0): 實驗B regression — <N regressions, PASS/FAIL>"
```

---

### Task 6: 實驗 C — Reset/母系規則獨立驗

**Files:**
- Create: `$P0/exp_c.py`
- Modify: validation tracker（追加 `## 實驗 C`）

**Interfaces:**
- Consumes: `refharness`、`mtrun`。no-Reset variant = 候選 prompt 移除 `【母系規則】…。` 嗰句（用標記定位）。

- [ ] **Step 1: 實作 exp_c.py**

```python
"""實驗 C：母系/Reset 規則獨立 — 有 vs 冇該規則，量 reset cue 命中 + 抽查唔 regress。"""
import json
import re
import refharness as rh
import mtrun

RUNS = 3


def strip_mare_rule(prompt: str) -> str:
    # 移除【母系規則】起，到該句句號止（含）。
    return re.sub(r"【母系規則】[^。]*。", "", prompt)


def main():
    full = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    noreset = strip_mare_rule(full)
    assert "母系規則" not in noreset and "母系規則" in full
    cue = rh.find_cue(rh.load_pair("f66d9705f78d")["mot"], "reset mare")
    seg = [{"start": cue["start"], "end": cue["end"], "text": cue["en"]}]
    with_hit = sum(rh.term_accept("reset", mtrun.run_mt(seg, full)[0]) for _ in range(RUNS))
    without_hit = sum(rh.term_accept("reset", mtrun.run_mt(seg, noreset)[0]) for _ in range(RUNS))
    print(f"reset cue: with-rule {with_hit}/{RUNS}  vs  without-rule {without_hit}/{RUNS}")
    json.dump({"with": with_hit, "without": without_hit}, open("exp_c_results.json", "w"))
    keep = with_hit >= 2 and with_hit > without_hit
    print("GATE C:", "KEEP 母系規則" if keep else "DROP 母系規則（無明顯增益）")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑**

Run: `cd "$P0" && python3 exp_c.py`
Expected：`with_hit ≥ 2` 且 `> without_hit` → KEEP；否則 DROP（Task 8 剝走該規則）。搭配 Task 5 的 B 結果（B 已檢查母系規則有無 regress 其他 cue）綜合判斷。

- [ ] **Step 3: 記 tracker `## 實驗 C` + Commit**

```bash
git add "$P0/exp_c.py" "$P0/exp_c_results.json" "$WT/docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md"
git commit -m "test(racing-p0): 實驗C 母系/Reset 規則 — <KEEP/DROP>"
```

---

### Task 7: 實驗 D — 對專業參考重量度

**Files:**
- Create: `$P0/exp_d.py`
- Modify: validation tracker（追加 `## 實驗 D`）

**Interfaces:**
- Consumes: `refharness`（load_pair/overlap_pro/term_accept）、`mtrun`。用最終選定 prompt（視 Task 6 KEEP/DROP，讀 CANDIDATE_PATH 或其 strip 版）。

- [ ] **Step 1: 實作 exp_d.py**

```python
"""實驗 D：最終 prompt 全片重跑，對齊專業參考，睇目標術語 ❌→✓ + 打印對照。"""
import json
import sys
import re
import refharness as rh
import mtrun
from exp_c import strip_mare_rule

TARGETS = [
    ("f66d9705f78d", "in his work", "track_work"),
    ("28deab03a71c", "track works", "track_work"),
    ("f66d9705f78d", "back in the field", "closer"),
    ("28deab03a71c", "newcomers", "newcomer"),
    ("f66d9705f78d", "another step", "unit"),
    ("f66d9705f78d", "reset mare", "reset"),
]


def main():
    keep_mare = "--drop-mare" not in sys.argv
    prompt = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    if not keep_mare:
        prompt = strip_mare_rule(prompt)
    out = {}
    for fid in ["f66d9705f78d", "28deab03a71c"]:
        pair = rh.load_pair(fid)
        cues = [{"start": c["start"], "end": c["end"], "text": c["en"]} for c in pair["mot"]]
        zh = mtrun.run_mt(cues, prompt)
        out[fid] = [{"start": cues[i]["start"], "en": cues[i]["text"], "new_zh": zh[i],
                     "pro": rh.overlap_pro(pair["pro"], cues[i]["start"], cues[i]["end"])}
                    for i in range(len(cues))]
    json.dump(out, open("exp_d_results.json", "w"), ensure_ascii=False, indent=1)
    # 目標術語 ❌→✓
    for fid, sub, term in TARGETS:
        row = next((r for r in out[fid] if sub.lower() in r["en"].lower()), None)
        ok = row and rh.term_accept(term, row["new_zh"])
        print(f"[{term}] {fid}: {'✓' if ok else '❌'}  {row['new_zh'][:50] if row else '—'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑（用 Task 6 決定嘅 `--drop-mare` 或唔加）**

Run: `cd "$P0" && python3 exp_d.py` （若 Task 6 DROP → `python3 exp_d.py --drop-mare`）
Expected：6 個目標 term 全 ✓（reset 視 Task 6）。

- [ ] **Step 3: 記 tracker `## 實驗 D`（含最終逐 cue 對照摘要）+ Commit**

```bash
git add "$P0/exp_d.py" "$P0/exp_d_results.json" "$WT/docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md"
git commit -m "test(racing-p0): 實驗D 對參考重量度 — 目標術語 ❌→✓"
```

---

### Task 8: 決策 gate → 套落真 racing.txt + 文檔

**Files:**
- Modify: `$MAIN/backend/config/mt_style_prompts/racing.txt`（← 候選內容，視 Task 6 決定含/剝母系規則；**去除 `【母系規則】` 標記字**）
- Modify: `$WT/CLAUDE.md`（MT prompt / style 段落）
- Modify: `$WT/README.md`（賽馬質量段落）
- Modify: validation tracker（`## 決策` 總結）

**Interfaces:**
- Consumes: 實驗 A/B/C/D 全部結果。

- [ ] **Step 1: 決策 gate 檢查**

確認 tracker：GATE A PASS（各 term new_hit ≥2/3）、GATE B PASS（淨 regression 0）、GATE C（KEEP/DROP 已定）、GATE D 目標術語 ✓。**任何硬 gate FAIL → 唔准入 Task 8 落真檔**，返對應實驗 task 調 prompt 重跑。

- [ ] **Step 2: 套候選落真 racing.txt**

由 `$P0/racing_candidate.txt` 取內容套落 `$MAIN/backend/config/mt_style_prompts/racing.txt`：
- 若 Task 6 = KEEP：套全部，但**刪走 `【母系規則】` 呢 4 個標記字**（保留其後規則文字）。
- 若 Task 6 = DROP：套全部 + 用 `exp_c.strip_mare_rule` 邏輯剝走整句母系規則。

核對：`diff` 真檔 vs 候選只差預期行；`grep -c "晨操\|後上\|初次上陣\|霍宏聲\|公尺" racing.txt` ≥5；`grep -c "母系規則" racing.txt` == 0（標記已清）。

- [ ] **Step 3: import 冒煙 + 一句真跑**

```bash
cd "$MAIN/backend" && source venv/bin/activate && python3 -c "
import translation.crosslang_mt as c
p = c.build_mt_system_prompt('en','zh','racing')
assert '晨操' in p and '公尺' in p and '母系規則' not in p
print('racing.txt loaded OK, len', len(p))
"
```
Expected：印 `racing.txt loaded OK`（`公尺` 出現係因規則文字「不可用公尺」，正常）。

- [ ] **Step 4: 文檔**

- CLAUDE.md「MT prompt / style + ops fixes」段落補一句：racing.txt 加賽馬術語（晨操/短途/後上/初次上陣/母系）+ 騎師 Luke→霍宏聲 + 單位米，參考老師診斷驅動 + Validation-First（實驗 A/B/C/D，tracker 2026-07-08-racing-quality-p0）。
- README.md 賽馬質量段落補：英文賽馬片用「賽馬」風格時，晨操/短途/後上/初次上陣等行話同單位（米）會譯得更貼專業廣播；騎師 Luke Ferraris → 霍宏聲。
- tracker 加 `## 決策` 總結（A/B/C/D 結果 + KEEP/DROP + 落地）。

- [ ] **Step 5: Commit**

```bash
cd "$WT"
git add backend/config/mt_style_prompts/racing.txt CLAUDE.md README.md docs/superpowers/specs/2026-07-08-racing-quality-p0-validation-tracker.md
git commit -m "feat(racing-mt): racing.txt 加術語(晨操/短途/後上/初次上陣/母系)+騎師Luke+單位米（參考老師診斷+A/B/C/D 驗證）"
```

- [ ] **Step 6: E2E（用戶自行）** — 提示用戶：揀啱 timing 用「賽馬」風格重新處理一條真賽馬片，校對頁應見晨操/短途/後上/米。（本步唔喺自動化範圍，交用戶驗收。）

---

## Self-Review 記錄

- **Spec coverage**：§3.1 racing.txt 改動→T1+T8；§3.2 唔用詞彙表→設計理由，無 code；§4 A/B/C/D→T4/T5/T6/T7；§5 成功門檻→各實驗 gate + T8 決策；§6 落地→T8；§7 風險（獨立撤/regression gate/過度套用註條件/ASR out-of-scope）→T5/T6 + T1 D 段條件註。無 gap。
- **Type consistency**：`run_mt(cues, prompt_text, temperature)`、`read_prompt`、`BASELINE_PATH`/`CANDIDATE_PATH`（T3 定義）喺 T4-T7 一致使用；`term_accept(name, zh)`/`find_cue`/`overlap_pro`/`load_pair`（T2）喺 T4-T7 一致；`strip_mare_rule`（T6）喺 T7 import 使用。
- **Placeholder scan**：無 TBD；實驗結果摘要用 `<…>` 只喺 commit message（實際數字實跑填入），非 code placeholder。
