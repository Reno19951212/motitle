# 書面語 Refiner 質量提升（P0+P1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `formal_refine` 由逐段裸文字 → 鐵則 prompt + 逐句 glossary 正名注入（SYSTEM）+ ±2 上下文窗口（USER）+ name-diff flag，大幅提升書面語質量（位置術語 0→100%、馬名 87.5→100%）。

**Architecture:** 全部 byte-identical port 自驗證 proto `docs/superpowers/specs/2026-06-13-written-quality-research/protos/w6_combined.py`（W6 組合，實證 理想達成 68.8→91.7%）。改 `output_lang_postprocess.py` formal_refine + racing prompt JSON；thread glossaries 過 `derive_aligned_output` + `app.py` 兩個 call site。generic prompt 不變（只套域中性機制）。

**Tech Stack:** Flask、本地 Ollama qwen3.5:35b-a3b-mlx-bf16、pytest。

**Spec:** `docs/superpowers/specs/2026-06-13-written-refine-quality-design.md`（已批准）
**Proto（行為基準，唔准改演算法）:** `docs/superpowers/specs/2026-06-13-written-quality-research/protos/w6_combined.py` + `W5-final-prompt.txt`

**事實基準（已讀 code 確認）：**
- `output_lang_postprocess.py`：`_refiner_prompt(style)`（racing→`_REFINER_RACING`，else `_REFINER_GENERIC`，line 39-40）；`_THINK_RE`（line 43）；`formal_refine` 現簽名 `(segments, llm_call, style="generic", cancel_check=None)`（58-81）逐段 `llm_call(sysp, txt)`
- `derive_aligned_output`（output_lang_aligned.py:51）refine 分支：`out = olp.formal_refine(base, llm_call, style=style, cancel_check=cancel_check)` — 已有 `glossaries` 入參，只需傳落去
- `app.py:501` `_produce_output_lang` zh 分支：`base = olp.formal_refine(base, _make_ollama_llm_call(), cancel_check=_make_cancel_check(cancel_event))` — 冇傳 style/glossaries（scope 有 `mt_style`、`glossaries`）
- proto W6 常數：`CTX=2`、`POS_TERMS=["尾二","尾三","尾四"]`、`EMBED_GLOSS`/`GARBLED_GUARD`/`WIN_INSTR`/`per_cue_sysp`/`build_window_user`/`parse_keep` — 逐個 port
- glossary 正名集：`phonetic_correction.build_index([g],[])["meta"]` 嘅 keys（已 port 過，racing clip 10 個名）
- W5-final-prompt.txt = racing 新 base prompt（鐵則前置）；W6_BASE_SYSP = W5V2 + EMBED_GLOSS + GARBLED_GUARD + WIN_INSTR（順序要保住）
- 測試：`cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_written_refine.py -v`（單獨跑）

---

### Task 1: racing prompt 換成鐵則前置版

**Files:**
- Modify: `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`（`system_prompt` 欄）

- [ ] **Step 1:** 將 `system_prompt` 換成 `docs/superpowers/specs/2026-06-13-written-quality-research/protos/W5-final-prompt.txt` 全文 + 緊接 `EMBED_GLOSS`（埋邊/放頭/透出/做P 術語段，內容見 proto w6_combined.py `EMBED_GLOSS`）。**只改 `system_prompt`，其餘 key（id/name/version/lang/style）不變**。用 Python 寫（避免 JSON escape 手誤）：

```python
import json
P = 'backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json'
W5 = open('docs/superpowers/specs/2026-06-13-written-quality-research/protos/W5-final-prompt.txt', encoding='utf-8').read().strip()
EMBED_GLOSS = (
    "\n\n⚠️ 補充賽馬位置術語（同上同等重要，唔可以照字面理解）：\n"
    "- 「埋邊／埋便」＝靠近內欄（內側），**唔係**「附近」「靠邊」「在哪裡」。\n"
    "- 「放頭／放」＝領放（跑最前帶頭），**唔係**「出閘」。\n"
    "- 「透出」＝自馬群中突圍透出，**唔係**「透視」。\n"
    "- 「做P／做P繩」＝領放定速（pace），**唔係**「織繩」。")
d = json.load(open(P, encoding='utf-8'))
d['system_prompt'] = W5 + EMBED_GLOSS
json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('racing prompt updated; len =', len(d['system_prompt']))
```

- [ ] **Step 2: 驗證載入**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -c "import json; s=json.load(open('config/prompt_templates_v5/refiner/zh_written_register_v6.json'))['system_prompt']; assert '三條鐵則' in s and '倒數第' in s and '埋邊' in s; print('ok', len(s))"`
Expected: `ok <len>`

- [ ] **Step 3: Commit**

```bash
git add backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json
git commit -m "feat(refine): racing 書面語 prompt 換鐵則前置版（名詞保護+位置術語+反幻覺，W5 V2 驗證）"
```

---

### Task 2: `formal_refine` 加 roster 注入 + 窗口 + name-diff（TDD）

**Files:**
- Modify: `backend/output_lang_postprocess.py`
- Test: `backend/tests/test_written_refine.py`（新）

- [ ] **Step 1: 寫 failing tests**

```python
# backend/tests/test_written_refine.py
"""書面語 refiner W6 機制 — port 自 2026-06-13 written-quality 研究 W6 proto。"""
import output_lang_postprocess as olp


GLOSS = [{"name": "賽馬", "entries": [
    {"source": "BEST PAL", "target": "好友心得 (D456)"},
    {"source": "LUCKY", "target": "幸運有您 (E356)"},
]}]


def _segs(*texts):
    return [{"start": float(i), "end": float(i + 1), "text": t} for i, t in enumerate(texts)]


def _capture_llm():
    """回 (llm, calls) — calls 記錄每次 (system, user)。LLM 回 keep JSON 照抄 user 本句。"""
    calls = []

    def llm(system, user):
        calls.append((system, user))
        # 抽【本句】（或者成個 user）做輸出，模擬「乖乖只改本句」
        body = user.split("【本句】")[-1].split("【後文】")[0].strip() if "【本句】" in user else user
        import json as _j
        return _j.dumps({"action": "keep", "text": body})
    return llm, calls


def test_window_user_format():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("第一句", "第二句", "第三句", "第四句", "第五句"),
                      llm, style="racing", glossaries=GLOSS, context_window=2)
    # 中間段（idx 2）user 要有前文（第一/第二）+ 本句（第三）+ 後文（第四/第五）
    sys2, user2 = calls[2]
    assert "【前文】" in user2 and "【本句】" in user2 and "【後文】" in user2
    assert "第三句" in user2 and "第一句" in user2 and "第五句" in user2


def test_window_boundaries():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("頭", "二", "尾"), llm, style="racing",
                      glossaries=GLOSS, context_window=2)
    assert "【前文】" not in calls[0][1]          # 第一段冇前文
    assert "【後文】" not in calls[-1][1]         # 最後段冇後文


def test_roster_injected_in_system_not_user():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("第六位外面位置好友心得"), llm, style="racing",
                      glossaries=GLOSS, context_window=0)
    sysp, user = calls[0]
    assert "好友心得" in sysp and "本句保護詞" in sysp     # 注入喺 SYSTEM
    # 本句命中嘅名先注入；冇出現嘅名唔注入
    assert "幸運有您" not in sysp


def test_pos_terms_racing_only():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("尾三紅衫"), llm, style="racing", glossaries=None, context_window=0)
    assert "尾三" in calls[0][0] and "倒數第三" in calls[0][0]
    llm2, calls2 = _capture_llm()
    olp.formal_refine(_segs("尾三紅衫"), llm2, style="generic", glossaries=None, context_window=0)
    assert "本句保護詞" not in calls2[0][0]               # generic 無位置術語注入


def test_name_diff_flag_recorded():
    # LLM 將馬名改走 → name_dropped flag
    def drop_llm(system, user):
        import json as _j
        return _j.dumps({"action": "keep", "text": "第六位外檔位置獲好評"})  # 好友心得 冇咗
    out = olp.formal_refine(_segs("第六位外面位置好友心得"), drop_llm, style="racing",
                            glossaries=GLOSS, context_window=0)
    assert out[0].get("refine_name_dropped") == ["好友心得"]


def test_name_diff_no_flag_when_kept():
    def keep_llm(system, user):
        import json as _j
        return _j.dumps({"action": "keep", "text": "第六位、外檔位置的是好友心得。"})
    out = olp.formal_refine(_segs("第六位外面位置好友心得"), keep_llm, style="racing",
                            glossaries=GLOSS, context_window=0)
    assert "refine_name_dropped" not in out[0]


def test_context_window_zero_no_window():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("甲", "乙"), llm, style="racing", glossaries=None, context_window=0)
    assert "【前文】" not in calls[0][1] and "【本句】" not in calls[0][1]   # 純本句


def test_empty_segment_passthrough():
    llm, calls = _capture_llm()
    out = olp.formal_refine(_segs("有字", ""), llm, style="racing", glossaries=None)
    assert out[1]["text"] == ""
    assert len(calls) == 1                              # 空段唔 call LLM


def test_cancel_check_raises():
    class _C(Exception):
        pass

    def boom():
        raise _C()
    import pytest
    with pytest.raises(_C):
        olp.formal_refine(_segs("一句"), lambda s, u: "x", style="racing", cancel_check=boom)


def test_glossary_import_failopen(monkeypatch):
    # phonetic_correction 攞唔到 → 空 name set，唔 crash（仍正常 refine）
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "phonetic_correction":
            raise ImportError("simulated")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    llm, calls = _capture_llm()
    out = olp.formal_refine(_segs("好友心得"), llm, style="racing", glossaries=GLOSS, context_window=0)
    assert len(out) == 1                                # 唔 crash
    assert "本句保護詞" not in calls[0][0]               # 冇 name set → 冇注入
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `cd backend && "…venv…/python" -m pytest tests/test_written_refine.py -v`
Expected: 多個 FAIL（formal_refine 未收 glossaries/context_window，冇注入/窗口/flag）

- [ ] **Step 3: 實現** — `output_lang_postprocess.py`：

(a) `_THINK_RE` 之後加 W6 常數 + helper（port 自 proto）：

```python
# ── 書面語 refiner W6 機制（port 自 2026-06-13 written-quality 研究）──────────
_POS_TERMS = ["尾二", "尾三", "尾四"]

_GARBLED_GUARD = (
    "\n\n⚠️ 亂碼／殘缺句保護：如果本句似係 ASR 亂碼或語意殘缺（出現你無法理解嘅字組合），"
    "**只做最低限度 register 轉換、照字面保留**，**唔准**用上下文／賽事知識去補完、自創或推測一個完整意思。"
    "寧願保留殘句，都唔好幻覺。")

_WIN_INSTR = (
    "\n\n你會收到【前文】【本句】【後文】三部分。前文同後文淨係畀你理解上下文意思"
    "（例如判斷某個詞係馬名、衫色花紋定係距離／位置），**唔好改寫亦唔好輸出佢哋**。"
    "只可以改寫【本句】，輸出只係【本句】嘅書面語 JSON {\"action\":\"keep\",\"text\":\"...\"}，唔好包含前後文。")


def _glossary_name_set(glossaries) -> set:
    """Glossary target 正名集（strip 編號）— roster 注入用。
    phonetic_correction 攞唔到（ImportError）→ 空 set（fail-open，唔阻 refine）。"""
    if not glossaries:
        return set()
    try:
        import phonetic_correction as _pc
        idx = _pc.build_index(list(glossaries), [])
        return set(idx.get("meta") or {})
    except Exception:
        return set()


def _inject_roster(base_sysp: str, names: List[str], pos_terms: List[str]) -> str:
    """本句命中嘅 glossary 名 + 位置術語逐字注入 SYSTEM（W4 P2，必須 SYSTEM）。"""
    if not names and not pos_terms:
        return base_sysp
    extra = "\n\n【本句保護詞（轉換時必須逐字原樣保留，唔准當普通詞拆開、改寫或合併）】\n"
    if names:
        extra += "馬名／賽事名：" + "、".join(names) + "。\n"
    if pos_terms:
        extra += ("賽馬名次術語（名次標籤，原樣保留，唔好改成「第X匹」「最後X匹」）："
                  + "、".join(pos_terms)
                  + "（尾二=倒數第二、尾三=倒數第三、尾四=倒數第四）。\n")
    extra += "唔好輸出呢段提示，唔好將呢啲詞加入冇提及佢哋嘅句子。"
    return base_sysp + extra


def _refine_window_user(texts: List[str], i: int, ctx: int) -> str:
    """【前文 ±ctx】【本句】【後文 ±ctx】（前後文只讀）。ctx<=0 → 純本句。"""
    if ctx <= 0:
        return texts[i]
    before = [t for t in texts[max(0, i - ctx):i] if t]
    after = [t for t in texts[i + 1:i + 1 + ctx] if t]
    parts = []
    if before:
        parts.append("【前文】\n" + "\n".join(before))
    parts.append("【本句】\n" + texts[i])
    if after:
        parts.append("【後文】\n" + "\n".join(after))
    return "\n\n".join(parts)
```

(b) `formal_refine` 全 function 換成：

```python
def formal_refine(segments: List[dict], llm_call: Callable[[str, str], str],
                  style: str = "generic", glossaries: Optional[List[dict]] = None,
                  context_window: int = 2,
                  cancel_check: Optional[Callable[[], None]] = None) -> List[dict]:
    """中文書面語 register refiner（W6：鐵則 prompt + 逐句正名注入 + ±N 上下文窗口
    + name-diff flag）。`style='racing'` → racing prompt + 位置術語注入；其他 → neutral。
    `glossaries` 供逐句馬名注入（無 → 唔注入）；`context_window` 前後文句數（0 → 逐段無窗口）。
    cancel_check 每段前 call。研究：docs/superpowers/specs/2026-06-13-written-quality-research/。"""
    base_sysp = _refiner_prompt(style) + _GARBLED_GUARD
    if context_window > 0:
        base_sysp += _WIN_INSTR
    name_set = _glossary_name_set(glossaries)
    pos_enabled = (style == "racing")
    texts = [(s.get("text") or "").strip() for s in segments]
    out: List[dict] = []
    for i, s in enumerate(segments):
        if cancel_check is not None:
            cancel_check()
        txt = texts[i]
        if not txt:
            out.append({**s})
            continue
        names_here = [n for n in name_set if n in txt]
        pos_here = [p for p in _POS_TERMS if p in txt] if pos_enabled else []
        sysp = _inject_roster(base_sysp, names_here, pos_here)
        user = _refine_window_user(texts, i, context_window)
        raw = _THINK_RE.sub("", llm_call(sysp, user) or "").strip()
        refined = raw
        if raw.startswith("{"):
            try:
                refined = json.loads(raw).get("text", raw)
            except Exception:
                refined = raw
        new_seg = {**s, "text": refined}
        dropped = [n for n in names_here if n not in refined]
        if dropped:
            new_seg["refine_name_dropped"] = dropped     # flag-only backstop（唔自動還原）
        out.append(new_seg)
    return out
```

- [ ] **Step 4: 跑測試全 pass + regression**

Run: `cd backend && "…venv…/python" -m pytest tests/test_written_refine.py tests/test_output_lang_postprocess.py -v` → 全 PASS（如有舊 formal_refine 測試，行為對非賽馬/無 glossary 應仍合理 — 若舊測試 assert 舊 prompt 文字，更新做新行為並記錄）

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_postprocess.py backend/tests/test_written_refine.py
git commit -m "feat(refine): formal_refine 加逐句正名注入(SYSTEM)+±2窗口+name-diff flag（W6 port）"
```

---

### Task 3: thread glossaries 過 call sites

**Files:**
- Modify: `backend/output_lang_aligned.py:51`、`backend/app.py:501`
- Test: `backend/tests/test_written_refine.py`（追加整合測試）

- [ ] **Step 1: failing 整合測試**（追加落 test_written_refine.py）：

```python
def test_derive_threads_glossaries_into_refine(monkeypatch):
    import output_lang_aligned as ola
    seen = {}

    def fake_refine(segments, llm_call, style="generic", glossaries=None,
                    context_window=2, cancel_check=None):
        seen["glossaries"] = glossaries
        seen["style"] = style
        return [{**s} for s in segments]
    monkeypatch.setattr(ola.olp, "formal_refine", fake_refine)
    base = [{"start": 0.0, "end": 1.0, "text": "尾三紅衫好友心得"}]
    # yue→zh = refine mode
    ola.derive_aligned_output(base, "yue", "zh", "trad", lambda s, u: "x",
                              style="racing", glossaries=GLOSS)
    assert seen["glossaries"] == GLOSS and seen["style"] == "racing"
```

- [ ] **Step 2: fail 確認** → **Step 3: 改 call sites**

`output_lang_aligned.py:51`：
```python
        out = olp.formal_refine(base, llm_call, style=style, cancel_check=cancel_check)
```
→
```python
        out = olp.formal_refine(base, llm_call, style=style, glossaries=glossaries,
                                cancel_check=cancel_check)
```

`app.py:501`：
```python
        if output_lang == "zh":
            base = olp.formal_refine(base, _make_ollama_llm_call(),
                                     cancel_check=_make_cancel_check(cancel_event))
```
→
```python
        if output_lang == "zh":
            base = olp.formal_refine(base, _make_ollama_llm_call(), style=mt_style,
                                     glossaries=glossaries,
                                     cancel_check=_make_cancel_check(cancel_event))
```

- [ ] **Step 4: 跑測試 + import check**

Run: `cd backend && "…venv…/python" -m pytest tests/test_written_refine.py tests/test_output_lang_aligned.py -q` → PASS
Run: `cd backend && FLASK_SECRET_KEY=test "…venv…/python" -c "import app; print('ok')"` → ok

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_aligned.py backend/app.py backend/tests/test_written_refine.py
git commit -m "feat(refine): thread glossaries 過 derive_aligned_output + _produce zh refine call"
```

---

### Task 4: P1.5 多 clip gating（GATING — orchestrator 親自做）

- [ ] 寫 `/tmp/wr_validate.py`：對 ≥3 條 yue clip（racing 回歸 48c1657e7ec1 / racing #2 de5bd2b803bf / generic 570fde92b502 或 798853512b6d）：攞 `content_asr_segments` → 先過語音糾錯（口語 base）→ `formal_refine` baseline（舊 prompt，無 glossaries/window）vs 新（style+glossaries+window=2）→ 真 local Ollama think:false
- [ ] racing clip 對 W1 catalog 量：位置術語、名詞保留、意思忠實（人手/LLM judge 覆核 showcase）— **唔可以低過研究數字（位置 5/5、名詞 40/40、理想 ~44/48）**
- [ ] generic clip 量：名詞保留升或平、register 無崩（無口語殘留）、48 進 48 出 — **有 regression → generic 收窄（context_window=0 或唔注入）再驗**
- [ ] 寫 `docs/superpowers/specs/2026-06-13-written-refine-validation-tracker.md`（✅/⚠️/❌ + 數字）

### Task 5: E2E + 文檔

- [ ] dev ff + 重啟 :5001 → 處理一條 yue 賽馬檔（output_languages 含 `zh`，揀賽馬詞彙表+賽馬風格）→ 完成後 API 攞 zh 軌核對：位置術語（尾二→倒數第二）、馬名保留（好友心得/幸運有您）。注意現有測試檔多數 output_languages=['yue']，需要新上載一條含 zh 嘅，或用 `/api/files/<id>/translate-second {lang:'zh'}` 加第二語言
- [ ] CLAUDE.md：Current State 加「書面語 refiner 質量 (P0+P1, 2026-06-13)」段；README：輸出語言章節補書面語質量說明（繁中）
- [ ] Commit `docs: 書面語 refiner 質量提升`

---

## 驗收清單

- [ ] test_written_refine.py 全 PASS（單獨跑）；regression（test_output_lang_aligned/test_output_lang_postprocess）PASS；import app OK
- [ ] P1.5：racing 唔低過研究數字 + generic 無 regression；tracker 寫好
- [ ] E2E：賽馬檔 zh 軌位置術語 + 馬名修正可見
- [ ] CLAUDE.md + README 更新
