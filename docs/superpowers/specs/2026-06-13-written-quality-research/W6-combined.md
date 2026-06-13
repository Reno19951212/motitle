# W6 — 最佳組合 end-to-end（書面語 refiner）

**任務**：按 W1–W5 數據砌最佳 refine pipeline（跟證據揀，唔全部疊）→ 48 段完整跑 → 端到端計分（current → improved → ideal）→ 評 production 可行性。

**Stack（production 同款）**：本地 Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3、`think:false`。輸入 `corrected_spoken.json`（48 段語音糾錯後高質口語 base）。Baseline = `current_written.json`。Ground-truth = `W1-catalog.json`。

---

## 1. 贏家組合（證據導向，唔係全部疊）

| 件 | 出處 | 點解採用（empirical） |
|---|---|---|
| **BASE prompt = W5 V2** | W5 | 純 prompt 重寫，**鐵則前置**（名詞保護→尾X gloss→反幻覺，放 register-convert 規則之前）+ 賽馬例子。W5 證 name +11pt / pos 0→100% / wrong 減半。 |
| **+ 埋邊/放頭/透出/做P gloss** | W2 漏、W3 證 | W2 只 gloss 尾X；W3 證 seg11/26/42（埋邊）一直錯要補。順手補 seg10（放頭）/ seg30（透出）/ seg46（做P）同類 lexical 術語。 |
| **+ garbled-cue guard** | W3 | W3 發現全局摘要令 garbled cue over-confident 幻覺。明示「似亂碼就照字面、唔好用上下文補完」。 |
| **+ W4 P2 per-cue roster injection（SYSTEM）** | W4 | 只注入**本句** base verbatim 命中嘅 glossary 名。W4 證 name→100% / mangled 5/5。**必須 SYSTEM**（W2：放 USER turn → 48/48 echo 污染）。 |
| **+ W3 ±2 cue context window（USER）** | W3 | 語義錨點，救 prompt-alone 救唔到嘅 local meaning（米字/透出/拆名）。N=2（register-safe；N=4 開始照抄）。 |
| **+ name-set diff backstop（flag-only）** | W4 | deterministic flag「base 有名→refine 丟失」。**唔 auto-restore**（W4 證 phonetic recall 0.40 無用 + auto-restore 吞句誤傷）→ 只 flag 交畀 proofread。 |

**明確 REJECT（有證據）**：
- **C2 全文一次過**（W3）：register 崩 80→54%、8 段 lazy 照抄。dealbreaker。
- **phonetic post-check restore**（W4）：name_mangled 係語義改寫非同音錯字，recall 0.40；放寬則吞句。
- **C3 two-stage summary**（W3 + 本次）：summary call +8s、且令 garbled cue 幻覺更差。±2 window 已得 local-context 好處而**無此風險，慳一個 call**。

---

## 2. 端到端計分（baseline → W6，對 W1 ideal）

| 指標 | baseline（current_written） | **W6** | 備註 |
|---|---|---|---|
| 格式 48 進 48 出 | ✓ | ✓ | run1 + run2 都穩 |
| **名詞保留率** | 35/40 (87.5%) | **40/40 (100%)** / run2 39/40 | run2 唯一 drop = seg3，backstop flag 捉到 |
| **位置術語（尾二/三/四）** | 0/5 (0%) | **5/5 (100%)** | 兩次穩定 |
| **name_mangled 修復** | 0/5 | **5/5** / run2 4/5 | seg 3,11,15,33,44 |
| **意思忠實（class2 judge）** | 0/9 | **6/9** | 兩次同數，最佳於所有 worker |
| **register marker 洩漏** | 0 | **0** | 48 段零口語殘留 |
| lazy 照抄段 | 0 | 1（seg28 源本身已書面，非偷懶；C2 有 8） | |
| **理想達成率** | **33/48 (68.8%)** | **44–45/48 (91.7–93.8%)** | seg10 機械低估，真實 45/48 |

**逐 tag before → after（W1 17 個有錯段）**：

| Error tag | W1 段數 | W6 修復 | 仍未修 |
|---|---|---|---|
| `name_mangled` | 5 | **5/5** | — |
| `term_misread`（尾X） | 5 | **5/5** | — |
| `meaning_error` | 10 | 6 | seg 3, 10*, 11, 46 |
| `hallucination` | 5 | 3 | seg 11, 46 |
| `register_bad` | 1 | 1 | — |
| `dropped` | 1 | 1 | — |

\* seg10 機械標未修但實際已修（放頭=領放=ideal 意思），judge 未覆蓋該段。

---

## 3. 代表性對照表（current → improved → ideal）

| # | 錯類 | current（現狀，有問題） | **W6（改進後）** | ideal（理想） |
|---|---|---|---|---|
| 3 | name+meaning | 內欄馬匹「米字」星河 | 內欄藍色賽衣的是**米字錶之星河**。 ⚠️名保住但米字 mis-attach | 內欄位置的錶之星河。 |
| 7 | 尾三 | **第三匹**穿紅色賽衣的馬是翠紅。（意思相反！） | **倒數第三**、穿紅色賽衣的是翠紅。 ✅達 ideal | 倒數第三、穿紅色賽衣的是翠紅。 |
| 8 | 尾二+殿後+幻覺 | 最後兩匹馬中，橙衫笑傲江湖暫居末位，**精算暴雪則表現穩健**。 | **倒數第二**、穿橙色賽衣的是笑傲江湖，目前**落後**的是精算暴雪。 ✅幻覺除、位置對、殿後歸屬對 | 倒數第二、橙衫的笑傲江湖，暫時殿後的是精算暴雪。 |
| 11 | name+garbled | 第二位馬匹**稍顯幸運，有您支持**。（拆散馬名） | 倒數第二、靠近內欄的是**幸運有您**。 ⚠️名修返但「第二位」over-apply 尾X | 第二位的是幸運有您。 |
| 15 | name_mangled | 第六位外檔位置**獲好評**（馬名消失） | 第六位、外檔位置的是**好友心得**。 ✅達 ideal | 第六位、外檔位置的是好友心得。 |
| 16 | 尾四+黑帽 | **最後四匹負黑頭馬**的友愛心得 | **倒數第四**、戴黑色頭盔的是友愛心得。 ✅位置+黑帽全修 | 倒數第四、戴黑帽的友愛心得。 |
| 19 | 尾二 | **最後一件**橙色賽服馬匹笑傲江湖（量詞錯落馬） | **倒數第二**、穿橙色賽衣的是笑傲江湖。 ✅達 ideal | 倒數第二、橙衫的就是笑傲江湖。 |
| 26 | 馬名當成語 | **在哪裡都能笑傲江湖**（成語典故化） | **靠近內欄的就是笑傲江湖** ✅達 ideal | 靠近內欄的就是笑傲江湖。 |
| 30 | 透出≠透視 | **透視**是錶之星河 | **自馬群中突圍**的是錶之星河 ✅達 ideal | 透出的是錶之星河。 |
| 33 | 一名拆兩匹+疑問句 | **「錶之星」與「星河」誰佔先機？** | **錶之星河仍佔領先**。 ✅合返一匹+陳述句 | 錶之星河還是佔先。 |
| 44 | 長句·精算暴風 | …**精算暴風**山來遲跑過第二… | …**精算暴雪**山來遲，跑過第二… ✅名修返（雪≠風） | …精算暴雪姍姍來遲跑了第二… |
| 46 | 真 garbled | 財寒遭遇暴雪，**負責編織 P 繩**的是星際快車 | 財寒都落敗，精算暴雪亦已跑完。**領放定速**的是星際快車在此。 ⚠️做P修返但財寒/暴雪仍 over-interpret | （財寒）放頭的力竭了，做領放 P 的是星際快車在此。 |

---

## 4. 耗時 + 可行性

- **Call 數**：48（1 call/段，**無 summary call**——比 C3G 省一個）。
- **耗時**：warm run **18.7s / 48 段 = avg 0.39s/段**（max 1.26s）。run1 total 41.9s 因含 18.1s 模型冷啟（seg0）。
- **vs budget**：48 段 < 20s（warm），遠低於 `R5_QWEN3_TIMEOUT_SEC=900s`。
- **結構改動**：roster 注入係 SYSTEM-prompt append（零 schema 改動）、±2 window 係 USER turn 輕量。
- **裁決**：**production 可行**。broadcast budget 完全接受。

---

## 5. 誠實 caveats

- **temp 0.3 stochastic**：跑 2 次。name 39–40/40、mangled 4–5/5、class2 **6/9 兩次同數**、pos **5/5 兩次穩**。個別 cue（seg3）run-to-run 搖擺，aggregate 穩定。
- **class2 judge 係同隻 model 自判**（self-judge bias）；但對 current_written 校準 0/9（同 W1 人手 catalog 一致）。建議人手覆核 showcase。
- **理想達成率係機械近似**（clean 段保持 + flagged 段 tag resolved），非逐字對 ideal。seg10 顯示機械會低估 → 真實 **45/48** 而非 44/48。
- **3 個結構性殘留**：
  - **seg3**（name-span 邊界歧義）：「內藍+米字+名」無分隔，model 米字 mis-attach；name 本身保住。
  - **seg11**（源頭歧義）：「埋邊有啲」W1 已標難；「第二位」被 over-apply 尾X 邏輯。
  - **seg46**（真 garbled，W1=uncertain）：garbled-guard 已除「織繩」幻覺、修好「做P→領放」，但「財寒/暴雪咗」仍 over-interpret。**refiner 階段結構性無解，要上游 ASR**（W2/W3/W5 一致結論）。
- 單一 108.6s racing clip、單一賽馬領域。體育新聞/通用領域未測。

---

**檔案**：proto `/tmp/lq-written/protos/w6_combined.py`（主）+ `w6_score.py`（計分）。輸出 `w6_combined_out_run1.json` / `_run2.json` / `w6_judge.json` / `w6_judge_run2.json` / `w6_score_out.json`。最終 prompt 組裝喺 `w6_combined.py`（W5 V2 + gloss/guard/window 串接）。
