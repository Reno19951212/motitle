# Research — 詞彙表 Review v2 for output_lang（5-agent workflow + 真 Ollama probe）

> 2026-06-05。研究 workflow synthesizer 報告（含對真 code/data 嘅核實修正）。決策見 spec 2026-06-05-glossary-v2-design.md。

---

I now have complete, verified grounding. Critically, I found two facts that **contradict** parts of the research and must be flagged: (1) `target_aliases` is `None` for the racing entries — Option C's "deterministic alias-replace map" has almost nothing to build from; (2) this branch **already has `style` threading** (`style="racing"`) in `derive_aligned_output`, so the synthesizer must note glossary is orthogonal but the integration story differs from what the architecture agent assumed. I'm ready to synthesize.

---

# 詞彙表 Review 喺 output_lang Pipeline — 決策報告

> 四份研究已整合。我亦親自核對咗實際 code 同兩個真 glossary 嘅資料形態。**有兩個研究嘅假設同真實 code 唔一致，已喺下面用 ⚠️ 標出並修正。** 全程跟 CLAUDE.md 嘅 Validation-First mandate — 呢份係 decision-ready,但實際 prompt/MT 改動仍要先過 §4 嘅 stress test。

---

## 1. 推薦架構 — Separate post-derivation stage,target-side 為主,deterministic-first

### 揀邊個:三選一嘅裁決

| 方案 | 裁決 | 點解 |
|---|---|---|
| **A — inline 入 refiner**(register + glossary 一個 pass) | ❌ **否決做主方案** | Refiner 睇嘅係**中文**,glossary key 係**英文** → 結構上對唔到。而且 `formal_refine` 係 **per-segment**,naive 注入 1350 條 ≈ 16.5k token × 每段 → concern 1(refiner overload)直接坐實。 |
| **B — separate post-pass LLM**(workflow 之後另開一個 glossary-review 模型 pass) | ✅ **採納為 escalation 層** | 正正解決你嘅 concern 2(context loss):register 已轉好,glossary pass 睇住乾淨嘅最終中文,單一任務。但**淨靠 LLM 逐段逐 term 對 1350 條會爆炸** → 必須有 deterministic detector 喺前面。 |
| **C — deterministic target-side 字串正規化**(無 LLM) | ✅ **採納為預設 workhorse** | 馬名正規化本質係**字典 normalization**,唔係翻譯。Deterministic replace 對 1350 條係 microseconds、零 token、零 context。 |

### 最終推薦:**兩層 target-side post-derivation stage**

> **C(deterministic,預設)+ B(LLM,opt-in escalation,重用 `GLOSSARY_APPLY_SYSTEM_PROMPT`),擺喺整條 derive chain 之後,永遠 per-segment filtered。**

呢個直接答到你兩個 concern:
- **Concern 1(refiner overload)**:refiner 完全唔孭 glossary → 零負擔。Register conversion 同 glossary review 係兩個獨立 job、獨立 budget。
- **Concern 2(context loss)**:glossary stage 睇住已 refine + 已轉繁簡嘅最終中文,單一任務「呢句入面個名應該係 canonical 形式」,無上文損耗。

### ⚠️ 必須修正研究嘅關鍵假設(我核實過真 data)

**研究將 Option C 描述成「靠 `target_aliases` 砌 `{alias → target}` replace map」。但真實 racing glossary 嘅 `target_aliases` 全部係 `None`。** 1350 條全部冇 alias。所以:

- **純 C 嘅力量被高估咗。** 冇 alias,deterministic replace 只能做兩件事:(a) **剝走 `(H037)` suffix**(128/1350 條 target 有呢個 suffix → 呢個係真實、確定、零風險嘅 cleanup,係 C 嘅真正主力);(b) 將「target 完全一字不差出現」嘅情況確認/保留。**但 Whisper 嘅 mis-transcription(把「有財有勢」聽成「有財有事」)冇 alias map 就無從 deterministic 修正。**
- **後果:真正修 mis-transcribed 馬名,要靠 B(LLM escalation)做 fuzzy 對齊,唔係 C。** C 主力係 suffix-strip + 確認 verbatim;B 處理 near-miss。呢個重新分配咗工作量 — escalation 唔係「罕有 residual」,而係 mis-transcription 嘅主要修復途徑。
- **緩解 / 升級路徑**:長遠應該為高頻馬名 backfill `target_aliases`(常見錯法),令 C 接走更多 case。但 v1 唔可以假設 alias 存在。

### Exact integration points(file:function,全部已核實存在)

1. **新純模組 `backend/output_lang_glossary.py`**(跟 many-small-files rule):
   - `strip_horse_id_suffix(text) -> str` — 剝 `(H037)` 類 suffix(**確定永遠唔可以漏入字幕**)。
   - `build_target_index(glossary) -> dict` — 由 `entry["target"]`(剝 suffix 後)+ 任何 `target_aliases` 砌 target-side lookup。對 racing,alias 空 → 主要係 canonical target set。
   - `glossary_canonicalize(segments, target_index) -> List[dict]` — deterministic、immutable、CJK word-boundary-aware(重用 `app.py:_make_glossary_term_pattern` 嘅 `一-鿿㐀-䶿` boundary class,但 target-side)。**= C。**
   - `glossary_review_llm(segments, glossary, llm_call) -> List[dict]` — per-segment filtered;只有被 detector flag「含 near-miss 馬名」嘅 segment 先送 LLM,prompt 共用 `app.py:GLOSSARY_APPLY_SYSTEM_PROMPT`(已 battle-tested,有「verbatim-wins」規則)。**= B,opt-in。**

2. **`backend/output_lang_postprocess.py`** — 加 `glossary_stage(segments, glossary, llm_call, *, use_llm)` wrapper,call canonicalize → optional LLM,令兩個 driver 都 call 同一個 entry。

3. **`backend/app.py:_produce_output_lang`(~L354)** — 喺最後一步 `apply_script` **之後**插入:
   ```python
   base = olp.apply_script(base, script)
   if glossary:
       base = olp.glossary_stage(base, glossary, _make_ollama_llm_call(), use_llm=glossary_llm)
   ```

4. **`backend/output_lang_aligned.derive_aligned_output`(L30)** — 喺 `apply_script`(L46)**之後**同樣插入,令 paired bilingual export 一致 canonicalize。要將 `glossary` 加入 `derive_aligned_output` + `build_aligned_bilingual` 嘅 signature(thread through)。

5. **`_run_output_lang`(~L407)** — 喺 `_registry_lock` 入面同 `source_language`/`script` 一齊讀 `entry["glossary_id"]`,`_glossary_manager.get(gid)` load 一次,thread 入 `_produce_output_lang`。

### ⚠️ 注意:`mt_style` / `style` 已經喺呢個 branch 存在

研究(architecture agent)以為呢個 worktree 冇 `style` threading。**我核實過:`derive_aligned_output(..., style="generic")` 同 `crosslang_mt.translate_segments(..., style=style)` 已經喺度,而且 `derive_mode` 已經 dispatch `pass|mt|refine`。** 所以:

- Glossary stage **同 `style` 正交** — style 揀 refiner/MT prompt,glossary 喺輸出之後做 canonicalization,兩者唔衝突。
- 但 wiring 比研究描述簡單:你已經有 `style="racing"` threading 嘅先例可以照抄,加 `glossary_id` 行同一條路。**唔需要好似研究講嘅「等 newer branch」** — 呢個 branch 本身已經有 style infra 可以 mirror。

---

## 2. Matching + Filtering 策略(en→zh vs zh→zh 不對稱)

三份研究**一致同意**核心裁決(我亦核實正確):

| Derive mode(由 `derive_mode` 決定) | 例子 | Glossary 適用面 | 策略 |
|---|---|---|---|
| **`refine`**(同中文家族換語體) | 粵口語→書面語(賽馬主 use case) | ⚠️ **只能 target-side** | Refiner 睇中文。英文 key 對唔到。掃 segment 中文 text 對 `target`(+ 將來 aliases)。**= 推薦架構嘅主路。** |
| **`pass`**(passthrough,同語言) | yue→yue, en→en | target-side(同 refine) | 同上,canonicalize 已有中文。 |
| **`mt`**(跨家族) | en→zh, yue→en | source-side(只當 source 同 glossary source_lang 對得上) | en→zh:重用 `ollama_engine._filter_glossary_for_batch`(已 guard `en→zh`)。yue→en:glossary 係 en→zh,兩邊都對唔上 → **直接 skip**。 |

### Target-side filter(refine/pass 路,1350 條嘅關鍵)

CJK 無空格,**唔需要 word-boundary regex,純 `in` substring 已正確**:

```python
def filter_glossary_target_side(target_index, segment_zh):
    # target_index: {canonical_target(剝 suffix) : entry}
    return [e for tgt, e in target_index.items() if tgt and tgt in segment_zh]
```

**Filter 後預期每段命中數**:廣播評述一句通常 mention 0–3 個馬名 → **每段 0–3 條**,極少更多。注入 block 因此係 0–3 條,prompt 完全安全。Broadcast(19 條)source-side 通常 0–2 條。

### ⚠️ 主導風險係 FALSE-INJECTION,唔係 follow-rate(stress-test agent 嘅最強發現)

- Broadcast glossary 有垃圾 entry:`And→和`、`box→禁區`、`subtitle→字幕`、`Club→球會`。`和`/`球會` 係常用字,target-side substring match 會喺**完全冇講呢個 term 嘅乾淨句**誤中。
- Racing:**10 條 target 剝 suffix 後 ≤2 字** → 同樣係 substring 撞中地雷(研究 probe 實測到 `球星`、`字幕`、`火悟空`、`新力` 嘅 coincidental 命中)。
- **緩解**:(a) deterministic replace 對 ≤2 字 target 要極保守(可選擇對 ≤2 字 target **唔做** target-side match,或要求更長 context);(b)凡有疑問升 B,靠 `GLOSSARY_APPLY_SYSTEM_PROMPT` 嘅「same entity 先改」規則擋住;(c) suffix-strip 永遠安全,無 false-injection 風險。

---

## 3. Scale 裁決(empirical probe 實測)

probe agent 跑咗真 model(`qwen3.5:35b-a3b-mlx-bf16 @0.3`)4 段 × 3 條件:

| 條件 | System prompt | Warm steady-state | 一次性 KV prefill | Valid JSON | Leakage |
|---|---|---|---|---|---|
| 無 glossary | ~695 tok | 0.63s/call | — | 4/4 | 0/4 |
| 19 條 full | ~872 tok | 0.65s/call | 可忽略 | 4/4 | 0/4 |
| **1350 條 full**(~17.5k tok) | ~17,529 tok | **0.60s/call** | **~8–10s 一次** | 4/4 | **0/4** |

**裁決**:
- **Full-inject 1350 條,純 latency 唔係 blocker。** KV cache warm 之後每 call ~0s overhead;job 開頭一次性 prefill ~8s。100 段 job ≈ 67s(vs 無 glossary 60s,**+7% amortized**)。Context 用 6.4%,無 exhaustion。
- **但對 refine 路,full-inject 係 no-op**(英文 key 對唔到中文輸入)。所以 full-inject 嘅「可行」結論**只對 mt 路有意義**。
- **Filtered**(每段 ~5–15 條,~67–189 tok)無論如何都係正路:既然 refine 要 target-side、mt 要 source-side,filter 係正確機制而唔止係 perf 優化。

**Scale 結論:deterministic C 對 1350 條係字面零成本(microseconds)。LLM B 嘅成本 = 被 flag 嘅 segment 數 × 0.6s,同 glossary 大細無關 → 1350 vs 19 喺 B 路徑成本幾乎一樣。** 真正成本動因係「幾多段含 candidate」,唔係 glossary 有幾大。

---

## 4. Stress-Test Plan(build 之前必須跑,Validation-First gate)

### Metrics(per-cell,逐段 aggregate)

| Metric | 定義 | 量度法 |
|---|---|---|
| **FOLLOW-RATE** | gold-applicable term 中正確 canonicalize 嘅 %(target present、`(H###)` 已剝) | 對 gold-applicability set 計 `correct/applicable`。**≥85% 先 ship-eligible。** |
| **FALSE-INJECTION**(kill-switch) | segment 冇 mention 但被誤注入/替換嘅 % | baseline vs glossary diff,新出現且無 gold 理據 = false。**≤1.0% 硬上限,>2% auto-reject。** |
| **SUFFIX-LEAK** | `(H###)` 漏入字幕嘅 % | **必須 = 0%。** |
| **QUALITY REGRESSION** | vs baseline:over-cap(>28字)、empty、register-marker drift、meaning-drift | 重用既有 v6 marker heuristic + char-cap counter;meaning-drift 靠 30-seg 人手 audit。over-cap ≤+1.0pp、empty ≤+0.5pp、0 新 meaning-drift。 |
| **LATENCY p50/p90/max/段** | glossary-enabled call wall-clock | `perf_counter`;**p90 ≤ 2× no-glossary baseline p90**(inline 路);post-pass 只計被 flag 段。 |

### Matrix(8 LLM cells + 2 baseline,cheap→expensive fail-fast)

| # | Glossary | Arch | Inject | Clip(registry file_id) | 用途 |
|---|---|---|---|---|---|
| B1 | 無 | baseline | — | Real Madrid `0858fc835535`(en→zh mt) | mt floor |
| B2 | 無 | baseline | — | 賽馬娛樂新聞 `7e66599d5085`(yue→zh refine) | refine floor |
| 1 | 19 | inline | full | Real Madrid | 小 glossary inline |
| 2 | 19 | post-pass | full | Real Madrid + 賽馬娛樂新聞 | 小 glossary post-pass + target-side |
| 3 | 1350 | inline | full | Winning Factor `39fea6251836` | **Concern-1 worst case** |
| 4 | 1350 | inline | filtered | Winning Factor | filter 救唔救到 inline |
| 5 | 1350 | post-pass | full | Winning Factor + 賽馬娛樂新聞 | **Concern-2 候選**,full |
| 6 | 1350 | post-pass | filtered | Winning Factor + 賽馬娛樂新聞 | **預測贏家**,filtered |

> ⚠️ **我加一個必跑 cell:純 deterministic(C,無 LLM)對 1350 條**。研究 matrix 全部係 LLM cell,但推薦架構嘅 workhorse 係 deterministic。必須實測:(a) suffix-strip recall(128 條有 suffix 嘅,deterministic 剝走幾多 %);(b) ≤2 字 target 嘅 false-injection rate;(c) latency(預期 ~0)。呢個 cell 決定 C 孭幾多、B 補幾多。

### Acceptance(全部要 hold 先 ship-eligible)

1. FOLLOW-RATE ≥ 85%
2. FALSE-INJECTION ≤ 1.0%(>2% auto-reject)
3. SUFFIX-LEAK = 0%
4. over-cap ≤+1.0pp、empty ≤+0.5pp、0 新 meaning-drift
5. LATENCY p90 ≤ 2× baseline(inline);post-pass 放寬到只計 flag 段
6. **Scale robustness**:19→1350 follow-rate 跌 ≤5pp 且 false-injection 唔過 §criteria-2 上限

**架構決策規則**:`inline-full-1350` 過晒 → ship inline(最簡)。若 inline 只敗喺 latency/prompt-size 但 `post-pass-filtered-1350` 過 → **ship separate post-pass + filter**(印證你 Concern-2 直覺)。若連 post-pass-full 都敗 false-injection 但 post-pass-**filtered** 過 → filtering 強制必須。若**無一個 1350 cell** 過 false-injection ≤2% → racing-scale 暫**不可 ship**,改 candidate-gating(只對 pre-filter flag 過嘅段做 review)再驗。

### Prototype spec(implement-ready)

- **檔案**:`backend/scripts/crosslang_prototype/diag_glossary_v2.py`
- **LLM**:`OllamaTranslationEngine({"engine":"qwen3.5-35b-a3b"})._call_ollama(sys,user,0.3)` — production binding,**唔可以換細 model**。
- **ASR**:**唔重跑**,直接由 `backend/data/registry.json` 食已轉錄 segments(mlx-whisper large-v3 輸出)。
- **Prompt**:baseline 重用 `output_lang_postprocess.formal_refine`(template `zh_written_register_generic.json`/`_v6.json`)同 `crosslang_mt.translate_segments`(`_MT_SYS`)原封不動;glossary cell append/wrap。
- **必備人手 artifact**:`gold_applicability.json` — 逐 clip 標 `{seg_index: [applicable_term_ids]}`。**冇呢個,follow-rate 同 false-injection 分母無法計。** racingnews 故意標 ~0 個馬名(佢講騎師 布浩穎/袁幸堯,唔喺馬名 glossary)→ 正好測 false-injection floor。
- **CLI**:`--clip --glossary --arch{inline|postpass} --inject{full|filtered} --side{source|target|auto} --cell --limit --out`
- **輸出**:逐 cell JSON + aggregate markdown 表(follow% / false-inj% / suffix-leak% / over-cap Δ / empty Δ / lat p50·p90·max / prompt tok / no-op%)+ **19-vs-1350 delta block** + 30-seg 人手 audit dump。
- **Tracker**:`docs/superpowers/specs/2026-06-05-glossary-v2-validation-tracker.md`,證據放 `docs/superpowers/validation/glossary-v2/`。

### 跑序:B1,B2 → cell 1,2 → **deterministic-C cell**(我新增) → cell 4 然後 3 → cell 5,6。

---

## 5. Upload-popup「Glossary Review」selector wiring

> 此 branch 用 `olOverlay` + `olSourceLang`/`olFirstLang`/`olSecondLang`/`olScript`(無 style selector)。研究引用嘅 `confirmOutputLangModal`/`startTranscription` 行號對應 newer branch;以下 anchor 用此 branch 嘅真實 element。

1. **`frontend/index.html` `olOverlay`** — 喺 `olScript` 後加:
   ```html
   <select id="olGlossary"><option value="">無(唔做詞彙表 review)</option></select>
   ```
   由 `GET /api/glossaries` populate(`{id, name, source_lang→target_lang}`)。可加一個 checkbox `olGlossaryLlm`「啟用 LLM 精修(慢、修正錯轉)」對應 §1 嘅 `use_llm` escalation toggle。

2. **confirm handler**(此 branch 嘅 output_lang confirm):
   ```js
   pendingGlossaryId = document.getElementById('olGlossary').value || '';
   pendingGlossaryLlm = document.getElementById('olGlossaryLlm')?.checked || false;
   ```

3. **`startTranscription()` 嘅 `output_languages` block**:
   ```js
   if (pendingGlossaryId) formData.append('glossary_id', pendingGlossaryId);
   if (pendingGlossaryLlm) formData.append('glossary_llm', '1');
   ```

4. **`backend/app.py` transcribe handler**(讀 `source_language`/`script` 嗰度,~L4154)— 加:
   ```python
   glossary_id = request.form.get('glossary_id') or None
   if glossary_id and not _glossary_manager.get(glossary_id):
       return jsonify({"error": "未知詞彙表"}), 400
   ```
   存落 file entry(同 `source_language`/`script` 一齊,~L1189):`entry["glossary_id"] = glossary_id`、`entry["glossary_llm"] = ...`。

5. **`_run_output_lang`** 喺 lock 內讀 `entry["glossary_id"]` → `_glossary_manager.get(gid)` → thread 入 `_produce_output_lang` 同(經 `_run_output_lang_second` 的 best-effort build)入 `build_aligned_bilingual`/`derive_aligned_output`。

---

## 研究分歧(必須喺 build 前畀 user 知)

1. **⚠️ `target_aliases` = `None`(我核實,推翻 architecture agent)**:Option C 被描述成「靠 alias 砌 replace map」,但 1350 條全部冇 alias。**C 嘅真正主力係 suffix-strip + verbatim 確認,唔係 fuzzy 修正。** 修 mis-transcribed 馬名要靠 B(LLM)。呢個重排咗 C/B 工作量 — B 唔係「罕有 residual」。**建議**:v1 接受 B 做主修;v2 backfill 高頻馬名 aliases 令 C 接走更多。

2. **⚠️ `style`/`mt_style` 已喺呢個 branch(我核實,推翻 architecture agent 「等 newer branch」嘅講法)**:`derive_aligned_output(..., style=)` 同 `derive_mode` dispatch 已存在。Wiring 比研究預期簡單,照抄 `style="racing"` 嘅 threading 先例即可。

3. **probe agent 對 refine 路嘅「glossary 完全 no-op」結論偏絕對**:佢啱「**source-side 注入** 對 refine 係 no-op」,但**target-side canonicalization**(本報告主路)對 refine **有用** — 正規化 refiner 已輸出嘅中文馬名 + 剝 suffix。probe 自己無測 target-side。reuse agent 同 stress-test agent 都正確指出 target-side 係 refine 路嘅正解。**採用 target-side 結論,probe 嘅 no-op 只限於 source-side。**

4. **三個 agent 一致**:(a) inline-A 對 1350 條否決;(b) post-derivation separate stage 係正確 placement(印證 Concern 2);(c) false-injection(尤其 ≤2 字 target + broadcast 垃圾 entry)係主導 ship/no-ship 風險,唔係 follow-rate。呢三點無分歧,信心高。

**淨係 §4 stress test(含我新增嘅 deterministic-C cell)綠燈晒,先入 spec→plan→code。** 最 gating 嘅單一數字 = **1350-term false-injection ≤1%**;預測贏家 = **Cell 6(post-pass + filtered)** + 一個前置 deterministic suffix-strip 層。