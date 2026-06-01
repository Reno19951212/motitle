# Validation-First Tracker — Whisper Large v3 輸出語言能力（2026-06-01）

**狀態**：✅ 實測完成 — 待 user review 後繼續設計 ｜ **Branch**：`feat/output-language-pipeline`
**Prototype**：`backend/scripts/diag_whisper_output_langs.py`（mlx-whisper large-v3，production model）
**測試片**：user 提供 3 條真實廣播片頭 90s —— `gamehub-（中文語音）`(粵)、`香港警察結業會操（中文語音）`(粵)、`Harry-Kane-Post-Match-Interview-Bayern（英文語音）`(英)。

## 假設
純 Whisper Large v3（transcribe + translate + force language）可以輸出用戶想要嘅 4 種目標語言（粵口語 / 粵書面 / 英 / 日），撇除 MT。

## 結果（量化 + 質性）

| 測試 | 輸出（節錄）| 判定 |
|---|---|---|
| gamehub transcribe `zh` | 「又返到每個禮拜你**最期待的**Gamehub…評價兩極你會**怎樣**處理」（13s, 1528 字）| ⚠️ **書面/普通話化中文，非口語粵語**（無 嘅/喺/咗；用「的/怎樣/我很高興」）|
| gamehub translate `→en` | 「Back to the Gamehub you are most looking forward to every week…」（3.7s）| ✅ 順、可用 |
| gamehub force `ja` transcribe | 「毎週最期待の**ゲームハブ大作推出評価**2劇どういう扱いをするか…」（25.6s）| ⚠️ **中日混合**（日文文法 + 中文詞彙），非乾淨日譯 |
| 警察 transcribe `zh` | 「今晚我**很高興**和**很榮幸**以檢閱官的身份…」（14.7s, 276 字）| ⚠️ 同上：書面/普通話化 |
| 警察 translate `→en` | 「**wrong The police are the police. The police are the police…**Today I am very happy…」（14s）| ⚠️ 開頭 **hallucination loop**，後恢復 |
| HarryKane transcribe `en` | 「Congratulations, job done, through to the last 16…」（4.6s, 1893 字）| ✅ 完美 |
| HarryKane translate `→en` | 同 transcribe（英→英）| ✅ |

## 結論（推翻部分原假設）
1. **`language=zh` ≠ 口語廣東話** —— Whisper large-v3 嘅中文 corpus 偏普通話，吐出書面/普通話化中文。所以：
   - 「**中文廣東話書面語**」目標 ≈ Whisper-zh 直接做到 ✅
   - 「**中文廣東話口語**」目標 ✗ Whisper-zh 做唔到（口語粵語要 Qwen3-ASR / V6 content track）
2. **Cross-language 確實有輸出**（force language）—— 但 `→日文` 係中日混合 hybrid，質量 marginal；`→英文` 用 translate task 可用但 hallucination-prone。
3. **Hallucination**（zh 尾巴「wrong…」、英 translate 開頭 loop）—— raw prototype 未經 v3.8 cascade-dedup / VAD；production ASR pipeline 有 guard 可清，但需確認套用後乾淨度。

## 對設計嘅影響（待 user 決定）
- 4-選項 matrix 對 Whisper 嘅真實 mapping：書面語 ✅、英文 ✅(+guard)、日文 ⚠️(hybrid)、**口語 ✗**(Whisper 出書面)。
- 要決定：(a) 口語 target 點算（接受 Whisper 書面輸出？定保留 Qwen3 做口語？）；(b) 日文 hybrid 收唔收貨（要睇全片質量）；(c) hallucination guard 套用後再驗。

## 下一步
User review 本實證 → 敲定可行 matrix + 口語/日文 處理 → 繼續 brainstorm 設計 → spec → plan。

## 全片 cleaned 驗證（condition_on_previous_text=False + s2hk，2026-06-01）
Prototype `backend/scripts/diag_whisper_full_quality.py`；全文存 `/tmp/wfull_*.txt`。

| 片 | transcribe zh+s2hk | translate→en | force-ja |
|---|---|---|---|
| gamehub(10min) | 3171字 **口語marker=0.0** loop=6 全片乾淨 | 10713字 連貫可用 | 3391字 中日混合(尾段自然) |
| 警察(2.4min) | 397字 口語marker=0.25 **無 hallucination 尾巴** | 1485字 **loop 已消失**(開頭小 artifact「A!」) | — |
| HarryKane(1.7min) | 2084字 完美英文 | 2093字 完美(=transcribe) | — |

**核心結論（全片實證）**：
1. `condition_on_previous_text=False` **修好 hallucination loop**（警察 90s 嘅「wrong/police loop」全消）→ 輸出可用。
2. **Whisper-zh = 書面化中文（口語marker≈0）**，非口語粵語 → 「書面語」target ✅、「口語」target ✗。
3. **translate→英文** 全片乾淨可用（粵→英、英→英）。
4. **force-ja** 中日混合、質量參差（片尾自然、片頭中文詞污染）→ marginal，當草稿用。

**Validated mapping**：書面中文 ✅Whisper-zh ｜ 英文 ✅Whisper-translate ｜ 日文 ⚠️Whisper-force-ja(marginal) ｜ 口語粵語 ✗Whisper(需Qwen3/V6)。

## ★ 補驗證：Whisper language=yue（廣東話）→ 口語粵語（2026-06-01）
頭先只測 `zh`(普通話→書面)，漏咗 `yue`(廣東話)。補測 90s clip + s2hk：

| 片 | language=**yue** 口語marker/100 | language=zh | 節錄(yue) |
|---|---|---|---|
| gamehub | **4.44** | 0.0 | 「又返到每個禮拜你最期待**嘅**…你會**點**處理?…同你**睇睇**」 |
| 警察 | **11.48** | 0.38 | 「今晚我**好高興同埋好榮幸**…你**哋嘅**工作**唔單止係**…」 |

**結論（推翻「Whisper 做唔到口語」）**：Whisper Large v3 `language=yue` 真正輸出口語廣東話（嘅/係/點/睇/哋/唔/好）。
**最終 mapping（全部純 Whisper，零 MT/Qwen3）**：口語=`yue`+s2hk ✅｜書面=`zh`+s2hk ✅｜英文=`translate` ✅｜日文=`ja` ⚠️marginal。
（注意：yue 仍偶有短重複，靠 segment_utils dedup 清。）

## ★★ T11 整合驗證 — real dual-Whisper-pass 全鏈路（2026-06-01）✅ PASS
Harness `backend/scripts/integ_output_lang.py`（live HTTP API，clean-restart backend :5001）。真檔 `香港警察結業會操（中文語音）.mp4`（2.4min 粵語），`POST /api/transcribe` + `output_languages=["yue","en"]` → 等兩個 Whisper pass。

| 驗證項 | 結果 |
|---|---|
| 第一 pass（yue + s2hk）| 46 段，`by_lang.yue.text`=「今晚我**好**高興**同埋好**榮幸」— 真口語粵語 marker + 繁體 HK（榮幸）✅ |
| 第二 pass（en, `task=translate` via `asr_output` job）| `by_lang.en.text`=「The Los Angeles Police…」乾淨英文 ✅（內容有 Whisper translate 小幻覺但語言正確）|
| 持久化 | `by_lang.{yue,en}` + authoritative `yue_text`/`en_text` mirror 一致 ✅ |
| descriptor `/languages` | `[{first,yue,口語廣東話},{second,en,英文}]` ✅ |
| status | `done`（first pass 後 status=done + 自動 enqueue 第二 pass asr_output）✅ |
| export | `source=first`→粵語 SRT、`source=second`→英文 SRT ✅ |

**結論**：整條 dual-Whisper-pass output_lang pipeline（T1-T7 backend）端到端實證通過 —— `transcribe_with_segments` lang/task/s2hk override 真正抵達 mlx engine、`asr_profile_override` 強制 mlx large-v3、s2hk 轉繁、`build_output_translations` by_lang + mirror、`_run_output_lang` + `_run_output_lang_second`（asr_output 第二 pass）、descriptor、role-fields、export 全部正確。

**Backend regression（pytest）**：output_lang + shared-code 子系統（output_lang/transcribe_override/persist/subtitle_text/bilingual_api/asr_output/progress_adapter/register_file）**135 passed / 0 failed**。render/v6/queue/proofreading 子系統全部在 isolation 下綠（queue_retry 5、v6 58、render 104/1）；唯一 fail = v3.3 已知 `test_ass_filter_escapes_colon_in_path`（macOS tmpdir colon-escape baseline）。零新增 regression。

**已知 minor（非 blocker）**：(1) 轉錄期間 progress shim 仍報 `profile` kind（`report_from_subtitle_segment` hardcode）→ queue bar 顯示「轉錄中」可用但 step-diagram 暫顯 profile 3-step（_reset 已 seed output_lang）；(2) `/api/files` row 未 echo raw `output_languages` 欄（descriptor `languages` 已有，frontend 用 descriptor → 無影響）；(3) V6 pipeline-strip spec 4 fail 係 v3.20 popover redesign 既有 stale（早於本 branch baseline，非本次 regression）。
