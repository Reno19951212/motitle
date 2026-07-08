# 賽馬翻譯質量 P0 — racing.txt 術語/名/單位補強 Design

日期：2026-07-08
Worktree：`quality-standard`（based on dev @ 7bd9c91）
方向：Option A（忠實 1:1 + 學專業用詞語體，唔學壓縮改寫）
來源診斷：[diagnosis/improvement_backlog.md](2026-07-08-quality-standard-research/diagnosis/improvement_backlog.md)（PaddleOCR 提取 2 條馬會片專業字幕 → 對齊 MoTitle 輸出 → 逐 cue 診斷）

---

## 1. 問題

「參考老師」診斷（專業 HKJC 廣播字幕 vs MoTitle 賽馬 style 輸出，兩條馬會片）揭發**系統性、跨兩檔重複**嘅賽馬翻譯 gap。兩片都係 `source=en / output=[en,zh] / mt_style=racing / glossary=賽馬(1353條)` —— 即係現行 `racing.txt` 已生效，以下係 racing.txt + 詞彙表**真正遺漏**（唔係揀錯 style）：

| gap | MoTitle 錯 | 專業正解 | 跨檔 |
|---|---|---|---|
| track work / (his) work | 「該場地的表現」/「保留體力」 | **晨操** | ✅ 兩檔 |
| sprinter | 「轉彎好手」 | **短途賽駒** | 檔1 |
| back in the field / closers | 「在後方」 | **後上（賽駒）** | 檔1 |
| newcomer / first-timer | 「新來者」 | **初次上陣** | 檔2 |
| out of a … mare（母系血統，X=父系名） | 「未重置的母馬」（Reset→重置！） | **母系；Reset 當專名保留** | 檔1 |
| 距離單位 | 「二千公尺」（同檔內又有「1600 米」，不一致） | **一律「米」** | 檔1 |
| 騎師 Luke (Ferraris) | 「盧克」音譯 | **霍宏聲** | 檔1 |

診斷同時**驗證**咗：專業廣播字幕都用「」括馬名（「祝願」「球星」「星球勇士」）—— 同已 ship 嘅 name_brackets 一致。

## 2. 範圍

**IN（P0，全部落 `racing.txt`，賽馬 style 專屬，通用/體育新聞 style 不受影響）：**
1. D 段加 5 條賽馬術語（晨操 / 短途 / 後上 / 初次上陣 / 母系血統）
2. G 段騎師名單加 `Luke Ferraris → 霍宏聲`
3. J 段強化：距離單位一律「米」，禁「公尺」
4. D 段加一個示例示範 track work / 母系
5. 母系規則同時處理 Reset（「out of a X mare」→ X 是父系專名，不譯普通詞）—— **當作可獨立撤回嘅一項**

**OUT（記錄做 follow-up）：**
- ASR 聽壞（spinner/fine arty/Mayor's/reset mare 聽成 reset）→ 上游 ASR 層，另議。就算 prompt 寫 `sprinter→短途`，ASR 俾「spinner」都幫唔到。
- 英文用代詞時插入已知馬名（檔2「星球勇士」全用 he）→ cross-cue 實體追蹤，大功能，Defer。
- P2 名稱（寶馬香港打吡大賽全名等）。
- `sportsnews.txt` / `generic.txt` **完全唔郁**。

## 3. 設計

### 3.1 `racing.txt` 改動（純 config，無 code）

**D 段（賽馬語體）末尾追加術語**（跟現有 `trainer→練馬師（不可譯「教練」）` 格式）：
- `track work／(morning) work／gallops → 晨操（賽事語境的「work」指晨操，非「工作」「體力」）`
- `sprinter → 短途賽駒；sprint（距離）→ 短途`
- `closer／back in the field／off the pace／run on late → 後上（賽駒）`
- `newcomer／first-timer／debutant → 初次上陣（新馬）`
- `out of a … mare／broodmare sire → 母系血統；「out of a X mare」中的 X 是父系/外祖父名，屬專名須原樣保留，不可譯成普通詞（如 Reset 不可譯「重置」）`

**G 段（人名）名單追加**：`Luke Ferraris→霍宏聲`（插入現有 Vincent Ho→何澤堯… 名單）

**J 段（格式與長度）強化單位**：現有「數字、時間、距離保留阿拉伯數字（如「1600 米」「3 檔」）」後補一句：**「距離單位一律用『米』，絕不可用『公尺』。」**

**D 段新增示例**（示範術語，馬名純示範）：
```
示例六（賽馬 work＝晨操，母系血統）：
英文：His track work's been very good and he's out of a Reset mare.
中文：牠晨操表現理想，母系源自「Reset」。
```

**唔郁**：A/B/C（反幻覺/不增減/不完整片段）、E/F（專名一致/馬名保護）、H/I/K、輸出格式 —— 全部已驗證核心，淨加唔改。

### 3.2 為何唔用詞彙表落賽馬術語

- 詞彙表 + `_filter_source_side` + `llm_review` 係為**具名實體（馬/騎師）**設計，`llm_review` 系統 prompt 講明「將中文字幕入面對應嗰隻馬嘅名改成規範中文名」—— 塞普通術語（track work→晨操）唔係佢職責，且單字術語（sprinter）易撞 `is_name_candidate` 邊界。
- `racing.txt` D 段本身就係術語表，係術語嘅天然歸宿，且賽馬 style-gated（同賽馬專屬原則一致）。
- 騎師名擺 racing.txt G 段：G 段已係策展騎師名單，一致。（馬名續留詞彙表，現行運作良好。）

## 4. Validation-First（強制，改 MT prompt）

全部 **dev-side 量度**（scratch script + 本地 Ollama qwen3.5:35b-a3b-mlx-bf16 @0.3，讀 registry，**唔掂 :5001 production**），OCR 專業參考做 ground truth。

**A. 目標術語命中** — 對每條有已知目標術語嘅 cue，用**舊 vs 新** racing.txt 各重跑 `crosslang_mt.translate_segments` **3 次**（MT 溫度隨機，單次無效），數正解術語命中率。預期：舊低 → 新高。
**B. Regression** — 新 prompt 重跑兩片全 50 cue，LLM judge 逐 cue「新 vs 舊」比對：新版有冇引入舊版冇嘅意思錯/語體漂移/幻覺。淨 regression 目標 = 0。
**C. Reset 規則獨立開關** — 有效且零 regression 先保留，否則單獨撤呢一條。
**D. 對參考重量度** — 全部改完，同一 harness 重新對齊專業參考，睇晨操/短途/後上/初次上陣/單位 由 ❌→✓、整體無新錯。

Harness scripts 入 `docs/superpowers/specs/2026-07-08-quality-standard-research/protos/`，結果入 `2026-07-08-racing-quality-p0-validation-tracker.md`。

## 5. 成功標準

| 項目 | 門檻 |
|---|---|
| 術語命中（A） | 6 條術語各自 cue 新 prompt ≥2/3 次命中（舊 baseline 對比記錄） |
| Regression（B） | 兩片 50 cue **淨 regression = 0** |
| Reset（C） | 獨立驗：有效且零 regression 先保留 |
| 對參考（D） | 目標術語 ❌→✓，整體無新錯 |

## 6. 落地（驗證通過後）

1. 改 `backend/config/mt_style_prompts/racing.txt`（純 config）
2. 補 `2026-07-08-racing-quality-p0-validation-tracker.md` 實證
3. 文檔：CLAUDE.md（MT prompt / style 段落）+ README（賽馬質量段落）
4. 用戶自行揀啱 timing 重新處理真檔驗收

## 7. 錯誤處理 / 風險

- racing.txt 係已驗證 tuned prompt → 淨加唔改核心、每項可獨立撤；Regression gate（B/C）係安全網。
- 術語過度套用風險（例：非賽馬語境嘅「work」被硬譯晨操）→ 術語加註條件（「賽事語境的 work」），並靠 B 檢查。
- MT 非確定性 → A/B 用多次重跑，唔靠單次。
- ASR-garble 類明確 out of scope，唔會因加 prompt 規則而假裝修好（誠實記錄）。

## 8. 文檔更新（完成時）

CLAUDE.md · README.md · validation tracker · 本 design（+ 對應 plan）。
