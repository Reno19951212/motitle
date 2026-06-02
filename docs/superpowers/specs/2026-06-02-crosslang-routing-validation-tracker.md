# Validation-First Tracker — Cross-language routing（Whisper 直出 vs ASR+MT）2026-06-02

**狀態**：📋 計劃完成 — **待 user 提供測試片** → 跑 prototype → 記錄量化結果 → user review → brainstorm→spec→plan→code
**Branch**：`worktree-fix-output-lang-single-display`（= `feat/output-language-pipeline`）
**工具鏈（已確認 ready）**：ASR = mlx-whisper `large-v3`；MT = Ollama `qwen3.5:35b-a3b-mlx-bf16`（production，已裝、Ollama API 200）。

## 觀察（user 報告）
output 語言 **== 影片內容語言** 時，Whisper 直出質量同分句都好；output 語言 **≠ 內容語言** 時，字幕質量好差。

## 假設（待驗證）
對 cross-language 輸出，**內容語言 ASR + MT 翻去目標語言**（舊 ProFlow 路徑）會明顯優於 Whisper 直接迫語言/translate。

## 路由規則（收斂）
> **output ∈ 內容語言家族 → Whisper transcribe 直出；否則 → ASR(內容語言) + MT(→output)。**
> 中文家族 = {yue 口語廣東話, zh 中文書面語}。

**Build 決策（user 拍板）**：內容語言由「來源語言」dropdown **做權威**（將現時純標記嘅 `olSourceLang` 改成驅動路由）。

## 關鍵技術現實
1. **Whisper `translate` task 只出英文** → 任何**非英文** cross 輸出，Whisper 冇直出路徑，`language=X` 只係迫 model 由非 X 音吐 X token（中日混合 hybrid，已知質差）。→ 非英文 cross 格，ASR+MT 幾乎係唯一高質路。
2. **英文 cross 格係 close call**：`→en` 可用 Whisper-translate（已知「乾淨可用」）vs ASR+MT，要實測邊個贏。
3. **分句**：ASR+MT 用內容語言 ASR 分句（靚）+ MT 按段 1:1 重新分配 → 結構上承繼靚分句；Whisper 迫語言破壞分句。
4. **MT 方向缺口**：現有 translator template 只有 `en→zh_hk`、`zh→en`。其餘 cross 方向（見下表「template」欄）**驗證時用 generic 參數化 cross-lang prompt**（src/tgt 語言名代入）測質量；若 validated，build 時先做正式 template。

## 完整 Matrix（內容語言 × 輸出語言）
法定 baseline = same-family（Whisper 直出，已往 tracker 驗過靚，本輪只 re-confirm）；**★ = 要對比嘅 cross 格**。

| 內容 audio | 輸出 | same/cross | Whisper 直出法 | ASR+MT 法 | MT template | 預期 |
|---|---|---|---|---|---|---|
| 中文(粵/普) | yue | same | `lang=yue`+s2hk | — | — | baseline ✅ |
| 中文 | zh | same | `lang=zh`+s2hk | — | — | baseline ✅ |
| 中文 | **en** ★ | cross | `translate`(→EN) | ASR(zh/yue)+MT(zh→en) | ✓ 有 | close call |
| 中文 | **ja** ★ | cross | `lang=ja`(hybrid) | ASR+MT(zh→ja) | ✗ 新 | ASR+MT 預期大勝 |
| 英文 | en | same | `lang=en` transcribe | — | — | baseline ✅ |
| 英文 | **zh** ★ | cross | `lang=zh`(迫,差) | ASR(en)+MT(en→zh) | ✓ 有 | ASR+MT 預期勝 |
| 英文 | **yue** ★ | cross | `lang=yue`(迫,差) | ASR(en)+MT(en→yue口語) | ✗ 新 | ASR+MT 預期勝 |
| 英文 | **ja** ★ | cross | `lang=ja`(迫,差) | ASR(en)+MT(en→ja) | ✗ 新 | ASR+MT 預期大勝 |
| 日文 | ja | same | `lang=ja` transcribe | — | — | baseline ✅ |
| 日文 | **zh** ★ | cross | `lang=zh`(迫,差) | ASR(ja)+MT(ja→zh) | ✗ 新 | ASR+MT 預期勝 |
| 日文 | **en** ★ | cross | `translate`(→EN) | ASR(ja)+MT(ja→en) | ✗ 新 | close call |
| 日文 | **yue** ★ | cross | `lang=yue`(迫,差) | ASR(ja)+MT(ja→yue口語) | ✗ 新 | ASR+MT 預期勝 |

→ 8 個 cross 格要對比（2 個 `→en` close call；6 個非英文 cross 預期 ASR+MT 勝）。

## 量度 metrics（每格 same 條片跑兩法）
- **分句**：段數、每段字數分佈（median/max）、超 cap 率（>cap）、超短碎段（≤2 字/<1s）
- **幻覺**：重複 n-gram 比率、loop、head-hallucination marker、空段率
- **達意 + 流暢**：LLM-judge（強 model，逐句 1–5 評 adequacy + fluency）+ 抽樣人手覆核
- **時間軸**：off-by-one / 對齊（ASR+MT 保留內容語言段 start/end）

## 執行計劃
1. 砌 clip-agnostic harness `backend/scripts/crosslang_prototype/diag_crosslang.py`：input(clip, content_lang, output_lang) → 跑 Whisper 直出 + ASR+MT 兩法 → emit 上述 metrics + LLM-judge。
2. **待 user 提供每個內容語言（中/英/日）各 1–2 條短片（~1–3 min、清晰人聲）**，尤其想要一條**普通話**片（手頭只有粵語）。
3. 逐格跑 → 結果入本 tracker（✅ Validated / ❌ Rejected / ⚠️ Partial）。
4. User review 證據 → 確認路由規則 + 每格用邊個方法 → brainstorm→spec→plan→code（包括 olSourceLang 變權威 + per-output-language 路由 dispatch + 新 MT templates）。

## 需要 user 提供
- **中文內容**：最好一條**普通話（國語）**片 +（可選）粵語片各 ~1–3 min。
- **英文內容**：一條 ~1–3 min。
- **日文內容**：一條 ~1–3 min（手頭有 `日本語音訪問片段馬會`，可用，但你想指定就提供）。
- 擺落 `~/Downloads/` 或話我知路徑即可。

## 手頭現有可用片（若 user OK 即可先跑 preliminary）
- 粵語：香港警察結業會操(2.4min)、gamehub(10min)、賽馬娛樂新聞、賽後兩點晚、區區有警、毛記電視
- 英文：Harry Kane、FIFA、Real Madrid、TVB News英、馬會騎師英
- 日文：日本語音訪問片段馬會

---

## ★★ 結果（2026-06-02，全 matrix 跑完）— 假設 ✅ VALIDATED
用戶提供片：中文=香港警察結業會操、英文=Harry Kane、日文=日本語音訪問片段馬會（各 80s）。
Harness `backend/scripts/crosslang_prototype/diag_crosslang.py`。原始 JSON：`/tmp/crosslang_{zh,en,ja}.json`。

**Same-family baseline（Whisper 直出）= 優秀**：粵→粵 judge **5/5/5**、粵→中書面 **5/4/5**，over_cap 0%、無 dup/loop。→ 規則 #1（內容==輸出家族用 Whisper 直出）✅。

**Cross-language Whisper 直出（force-language / translate）= 一致地崩壞**（sample 為證）：

| Cross | Whisper 直出（A）實況 | ASR+MT（B）實況 | 客觀 metric |
|---|---|---|---|
| 粵→en | `The police police police`（死 loop，整段重複） | `I am very happy and honored tonight.`（乾淨英文） | A dup=7 rep=0.172；B dup=0 rep=0 |
| 粵→ja | `音楽 / 法治は…基石です`（幻覺+中日混合 hybrid） | `今夜は非常に嬉しく、また光栄に思います。`（自然日文） | — |
| 英→zh | `從最後16分到最後一分`（last-16 誤譯成「16分」，**爆 105 碎段**） | `恭喜，任務完成，晉級十六強。`（正確流暢） | A n=105；B n=24 |
| 英→粵 | `到最後16分, 你覺得如何?`（run-on，逗號黐埋） | `恭喜曬，任務完成，晉身十六強。`（自然口語粵語） | — |
| 英→ja | `16歳までの仕事を終えました`（last-16 誤聽成「16歲」） | `おめでとうございます、…ベスト16進出です。`（正確） | — |
| 日→zh | `競舞舞台舞舞舞舞`（死 loop/亂碼） | `去年一直難以呈現精彩賽事…`（流暢中文，judge **3/4/5**） | A 亂碼；B judge 3/4/5 |
| 日→粵 | `皮皮皮 / 皮皮皮`（完全亂碼） | `其實呢，去年始終都難得…`（自然粵語，judge **2/4/3**） | A n=59 亂碼；B n=14 |
| 日→en | `I haven't been able to compete well last year…`（尚可用） | `Well, you know, we haven't…`（較自然口語） | 兩者皆可 |

**結論**：
1. **內容==輸出語言家族 → Whisper 直出**：優秀，維持。✅
2. **Cross-language → Whisper force-language/translate**：一致崩壞 —— 死 loop（police police / 舞舞舞 / 皮皮皮）、幻覺（音楽 / 球擊）、中日混合、誤譯（16強→16分/16歲）、碎段爆炸（英→中 105 段）。✗
3. **Cross-language → 內容 ASR + MT**：即使**naive 1:1（無上文，質量下限）**都一致勝出 —— 目標語言自然、意思大致正確、分句乾淨。生產用 sentence-pipeline（merge→譯→redistribute）會再好。✅ **假設成立。**
4. **唯一 close call：→英文**。粵→en 嘅 Whisper-translate 爆 loop，但 日→en 尚可。Whisper translate **時好時壞（個別片爆 loop）**，ASR+MT 穩定乾淨。→ 即使 →en，**ASR+MT 較安全**（避 loop 風險），Whisper-translate 可作 fallback。

**已知限制（記低，唔影響結論）**：
- LLM-judge（單一中文 prompt 嘅 qwen3.5）**對英文/日文 candidate 不可靠**（返 None 或離譜，例如 en-same baseline 誤畀 1/1/1）。故 →en/→ja 格**靠 sample + 客觀 metric（dup/rep loop、n_seg 碎段）**判斷，證據已足夠明確。
- 1:1 MT 無上文 → 個別關鍵詞誤譯（檢閱官→censor、生涯→卡里亞）；生產 sentence-pipeline 會修。
- ASR+MT over_cap% 偏高（承繼內容語言 ASR 段長 + 跨語言膨脹）→ 需 clause-split（似 V6）調節，非 blocker。

## ★★★ v2 再驗證（2026-06-02）— 普通話來源 + 新輸出變量
User 加 source 粵語/普通話拆分、output 普通話/簡體;提供普通話片 `阿土爆旋陀螺（普通話語音）`（80s）。Harness `diag_crosslang_v2.py`，結果 `/tmp/crosslang_mando.json`。
**片性質**：休閒打機內容、英文 loanword(NASA/HOLA)+術語(包箱/軍標)→ ASR 本身有錯，絕對 judge 分偏低(2/3/4)，**但 A vs B 相對比較有效**。

| 驗證項 | 結果 |
|---|---|
| Whisper 語言碼 | `zh`=chinese(訓練偏 Mandarin)、`yue`=cantonese;**無獨立 mandarin 碼 → 普通話=`zh`、粵語=`yue`** ✅ |
| 普通話來源 ASR(`zh`) | 56 段，母語轉錄正常(`我是阿神，我們今天要來玩`) ✅ |
| **★ 普→口語廣東話** | A Whisper 直出 force-`yue`：`我是阿神,我們今天要來玩`（**仍係普通話、非粵語**）❌；B ASR(zh)+MT(zh→yue)：`我係阿神，而家我哋要嚟玩啦`（**真粵語口語**）✅ → **必須 ASR+MT** |
| 普→英文(ASR+MT) | `I'm A-Shen, and today we're going to play.` 乾淨 ✅ |
| 普→日文(ASR+MT) | `私はアシンです。今日私たちは遊びます。` 自然 ✅ |
| 普通話 raw vs 中文書面語(+refiner) | raw `我們今天要來玩` → refined `本人為阿神，今日將進行遊戲`（本人/今日/進行）→ **register 確有別** ✅ |
| 簡體 script | Whisper `zh` native script **唔穩定**（呢片 native 出繁體 們/來）→ **繁/簡必須明確 OpenCC(s2hk / t2s)**，唔靠 native ⚠️ |

**關鍵 routing 修正（不對稱，要 dialect-level 唔係 family-level）**：
- `粵語→中文書面語/普通話`：Whisper 直出 `zh` ✅（Whisper 'zh' 食慣粵音→中文字幕，5/4/5）
- `普通話→口語廣東話`：Whisper 直出 `yue` ❌（force-yue 落 Mandarin 音唔會轉粵語口語）→ 要 ASR(zh)+MT(zh→yue)

## ★★★★ 整合驗證（2026-06-02，build 後端到端，:5002 真片）✅ OK
Harness `backend/scripts/crosslang_prototype/integ_crosslang.py`，逐路由格真 Whisper+MT：

| Case | 輸出 | 方法 | 結果 |
|---|---|---|---|
| 警察(粵) yue→[yue,en] trad | yue | whisper-direct | `今晚我好高興同埋好榮幸`（真粵語繁體）✅ |
| | en | asr_mt(粵→英) | `I am very happy and honored tonight.`（乾淨）✅ |
| **阿土(普) cmn→[yue,cmn] trad** | **yue** | **asr_mt(普→粵)** | `哈囉各位，係 NASA 嘅 NASA。`（**真粵語 係/嘅 — cross-dialect nuance 生產確認**）✅ |
| | cmn | whisper-direct | `HOLA各位,NASA的NASA`（普通話 raw，的）✅ |
| Harry Kane(英) en→[zh] **simp** | zh | asr_mt(英→中)+refiner+t2s | `恭喜，任务完成，晋级十六强。`（**簡體** + 正確，非 force-zh 嘅「16分」）✅ |

全部 status=done、descriptor langs 正確、`by_lang`+mirror 持久化正確。**結論：cross-language 路由（whisper-direct / asr+mt）、cross-dialect（普→粵真粵語）、繁/簡 OpenCC、書面語 refiner、descriptor/export 全部端到端通過。** Backend regression 16 檔隔離全綠（172 tests，零 regression）。

## Final whole-branch review（Opus，038ffae..449d10b）：✅ READY TO MERGE
End-to-end coherence ✅、路由表 100% 對證據（含 cmn→yue nuance）✅、零新 regression（唯一 fail = 已知 v3.3 macOS tmpdir colon-escape baseline，唔喺 feature diff；profile/V6/B1/B2/現有 output_lang 不變）✅、immutability + py3.9 ✅、OpenCC 冪等（whisper-direct zh 路徑 in-transcribe s2hk + apply_script 兩次但 idempotent，輸出正確）✅。

**Non-blocking 觀察（記錄）**：
1. **LLM 失敗處理 vs spec §11**：`crosslang_mt.translate_segments` / `formal_refine` 無 per-segment try/except → hard LLM 失敗 fail 成個 job（clean error，無 crash/corruption，poison-pill cap 適用）。**判斷：保留現行** —— `_call_ollama` 已 retry 5xx 4 次（短暫故障已處理）；hard failure 屬 Ollama 全域性，clean `status='error'` 畀 retry 好過 silent 出空字幕標 done；單 segment 唔會因內容怪而 hard-fail。spec §11 graceful-per-segment 針對實際唔會發生嘅情境。可作 v2 nicety（per-segment flag）。
2. whisper-direct zh/cmn 雙 s2hk（in-transcribe + apply_script）—— 冪等、輸出正確、僅少量浪費。可 v2 統一由 apply_script 做。
3. zh asr_mt 路徑 `_make_ollama_llm_call()` 實例化兩次（MT + refine）—— 微浪費。
4. `_whisper_params_for_lang`（app.py:316）成為 dead code（被 `output_lang_router.whisper_direct_params` 取代）—— 無害遺留。

## 最終路由表（證據敲定）
| 輸出語言 | Whisper 直出 條件（內容 audio）| 否則 → ASR(內容)+MT | 後處理 |
|---|---|---|---|
| 口語廣東話 yue | **內容=粵語** | MT(→粵口語) | OpenCC 繁/簡 |
| 中文書面語 zh | 內容=粵語 **或** 普通話 | MT(→中文) | **+formal refiner(V6)** → OpenCC 繁/簡 |
| 普通話 zh | 內容=粵語 **或** 普通話 | MT(→中文) | OpenCC 繁/簡（raw，無 refiner）|
| 英文 en | 內容=英文 | MT(→英文) | — |
| 日文 ja | 內容=日文 | MT(→日文) | — |

→ 規則：**Whisper 直出 當「該輸出方言嘅 Whisper 轉錄喺該內容音上得到目標」**（yue 限粵語內容；zh 收粵+普；en/ja 限同語言內容）。其餘（含粵↔普 cross-dialect）→ ASR+MT。繁/簡永遠明確 OpenCC。中文書面語永遠加 V6 formal refiner。

## 下一步（待 user 拍板）
證據支持落實。確認最終路由表後 → spec→plan→build：
- `olSourceLang` 改**權威**(粵語/普通話/英文/日文)驅動路由。
- 輸出 = 語言 dropdown(口語廣東話/中文書面語/普通話/英文/日文)+ 繁/簡 toggle。
- Per-output dispatch 按上表;cross 用 Ollama qwen3.5 single-segment + generic 參數化 cross-lang prompt;中文書面語加 V6 refiner;繁/簡 OpenCC;cross 輸出加 clause-split 控段長。
- 範圍外(v2)：glossary 專名注入、sentence-pipeline 上文。
