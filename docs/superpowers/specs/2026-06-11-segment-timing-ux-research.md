# 校對頁段落時間調整 UX — 研究報告

日期：2026-06-11 ｜ 狀態：研究完成 + 用戶反饋已納入（v2 設計，未實施）｜ 方法：Workflow（3 並行研究員：現有 UI 結構／後端數據模型／業界 UX 慣例 + 1 評審綜合）

## 結論：「Boundary Trim Bar」— 升級現有時間軸底部嘅「當前段」行

三種互動「動詞」寫入同一個後端 timing 操作，全部住喺現有 `.rv-b-wave-ctrl` 行（時間軸 panel 底部，本身已經顯示 `當前：段 #N · In · Out · 時長` — proofread.html:1066-1080），**零新增垂直空間，編輯界面 = 顯示界面**：

1. **微調 Nudge（主力）**：In/Out 各有 `◀ ▶` 細掣（±0.1s）+ 鍵盤 `[`/`]`（In）、`Shift+[`/`]`（Out）、`Alt`＝0.01s 細步 — Subtitle Edit 嘅 ±100ms 業界慣例。完全唔受時間軸像素密度影響（呢頁時間軸係全片比例、無 zoom — 30 分鐘片一段 cue 得 2-6px 闊，drag 根本捉唔到）
2. **設為播放頭（次力）**：`⤓播放頭` 掣 + `I`/`O` 鍵 — 啱 1-3 秒大偏移；用戶睇片定格之後一下捕捉判斷；`,`/`.` 微移播放頭。2026-06-10 修好嘅「暫停 seek 唔扯 cursor」guard 啱啱解決埋呢個 pattern 嘅經典 failure mode
3. **數字時間輸入（精確後備）**：現有 `#curIn`/`#curOut` 顯示 span 變成可編輯 mono input（Enter/blur commit）— 滿足「導演話呢句要喺 00:01:23.10 開始」

### 核心設計決策：Roll-on-contact（相連邊界一齊郁）

呢個 app 嘅 cue grid 係**連續、無重疊**（split/merge 維持呢個 invariant），而下游**完全冇防禦**重疊（SRT 照 list 順序出、libass 疊 Dialogue、renderer 對 start>=end 嘅 cue 直接靜默丟棄 renderer.py:173-175）。所以邊界調整必須 model 做「**共享邊界移動**」：段 N 嘅 In 同段 N-1 嘅 Out 相連時，一齊 roll — 每個操作**結構上不可能**產生非法狀態，唔使彈 error dialog。最少時長 clamp 0.4s（同 split floor 一致）。有 gap 時自由移動、撞到鄰段就 clamp。

### 其餘行為

- **即時預覽**：本地即改 segs[] → 現有 `setCursor(i,false)` 鏈自動重繪 ctrl row／detail／rail／waveform regions；字幕 overlay 下一個 timeupdate 自動跟新時間
- **自動回播**：改完由 In−0.7s 播到邊界+0.5s，免手聽結果（可關）
- **儲存**：optimistic + 400ms debounce 合併連按做一個 PATCH（絕對時間，唔係 delta — 冪等）；server clamp 後回傳實際值 reconcile；409/400 回滾 + toast
- **批核狀態保留**：timing-only 編輯**唔 reset approval**（split/merge/rerun reset 係因為文字變咗；呢度文字冇變，雙語 render 又要求全批核 — reset 會逼人白做重審）
- 順手修返：rail 行嘅 In/Out 堆疊 timecode display（CSS `.rv-b-rail-ts` 633-635 仲喺度但 markup 冇 emit — CLAUDE.md 講嘅 display 其實已甩咗）

### 後端需求（新 endpoint）

`PATCH /api/files/<id>/segments/<pos>/timing`，body `{in_ms?, out_ms?}`（絕對 ms）→ `{rows:[{idx,start,end},…], clamped}`（roll 時連鄰段一齊回傳）。
- 驗證：start<end、時長 ≥0.4s、clamp 鄰界（gap 可以、重疊永不）；相連邊界 atomic roll 兩行
- **四庫同步**（`_registry_lock` 內，照 split cascade）：`translations[pos]` + `segments[pos]` + **`content_asr_segments[pos]`**（唔同步嘅話下次 glossary-reapply 會用舊 timing 重建成個 grid 靜默還原你嘅修改！）+ `aligned_bilingual[pos]`
- 409：render／AI Rerun 進行中（同 split/merge 一致）；只限 output_lang
- AI Rerun 已有 timing-drift conflict check（5647-5649）— 反方向 fail-safe 已存在

## 用戶反饋修訂（2026-06-11，v2 設計 — 最終方向）

用戶睇完 v1 mockup 後三點修訂，**v2 成為實施基準**：

1. **快捷鍵淨返 `I`/`O`**（設 In/Out 為播放頭）— 其餘鍵盤快捷鍵（`[`/`]` nudge、`Alt` 細步、`,`/`.`）全部唔要，太多餘
2. **微調改用拖拉**：±0.1s nudge 掣互動太迂迴 — 改為當前段 region 左右**拖拉把手**（揸住直接拖個頭/個尾）。即係將原 rank 4 嘅 edge-drag 升做主力（用戶明確要求）
3. **時間軸要有縮放**：全片 view 長片段段勁細 — 加 zoom 控制（⊡全片 / − / ＋ / **⌖對焦本段**），放大後橫向捲動；「對焦本段」一掣 zoom 到當前段佔視窗 ~25%

保留：In/Out 數字輸入（精確 fallback）、⤓播放頭掣、roll-on-contact 語義、0.4s clamp、批核狀態保留、後端 timing endpoint 設計全部不變。

**v2 實施要點**（建基於研究發現嘅基建需求）：
- 時間軸改成 viewport（overflow-x）+ inner（width = zoom×100%）結構；regions 絕對定位喺 inner 內，pan 用原生捲動
- 拖拉把手只喺 `.cur` region 顯示（避免細 region 誤捉），mousedown 喺把手、mousemove/mouseup 喺 document；拖緊顯示浮動 timecode；**拖拉期間要 suppress regions 嘅 innerHTML 重建**（現有 9 個 call site 會殺 drag state — 拖完先重建）
- 拖拉同 click-to-seek 共存：click handler 跳過 `.grip` 目標
- zoom 後 `renderWaveformBars` 要按 zoom 重新取樣（`/api/files/<id>/waveform?bins=N` 已支援 bins 參數）
- v2 mockup：`/tmp/timing-preview/index.html`（port 8777），互動已 Playwright 驗證（拖拉+roll、I/O、zoom cycle、0.4s clamp）

## 被拒／延後方案排名

| 排名 | 方案 | 判決 |
|---|---|---|
| 4 | 波形 region 邊緣拖拉（Aegisub/NLE 式） | **延後** — 最直覺但呢條 strip 全片比例無 zoom，cue 得幾 px 闊；要先起 zoom-to-cue 視窗 + 全套 drag 基建（page 而家零 pointer/drag handler，regions 每次 re-render 會殺 drag state）。effort 最大。如果操作員之後有需求，`.rv-b-tlh-r` 空 toolbar 位留咗俾 zoom toggle |
| 5 | ASR 詞邊界 snap（Descript 式，Tab 跳到下一個字邊） | **延後 enhancement** — pipeline 已有 word_timestamps，但未送到校對頁；翻譯軌同 content 詞唔係 1:1；DTW 喺音樂/重疊位會 drift。v1 之後先考慮 |
| ✗ | Tap-sync 邊播邊敲（Amara 式） | **直接拒絕** — 係由零 timing 成條片嘅工具；ASR 已經對咗 95%+，呢頁係逐點修正 |

## 互動 mockup

`.superpowers/brainstorm/81827-1781108138/content/timing-trim-bar.html`（preview server port 52555）— 互動驗證咗：nudge、roll（黃色閃示相連邊郁咗）、0.4s clamp、數字輸入 commit、播放頭定點、鍵盤全套。

## 評審判詞（節錄）

> 呢頁嘅任務 profile 係「快速覆核幾百段大致正確嘅 ASR cue，偶然修一個邊界」— 唔係 NLE。最優先要做到「2 秒內修好一個邊界，唔離開鍵盤 flow」。Nudge 完全 decouple 咗調整同時間軸像素密度，係呢頁最難約束（全片比例無 zoom）嘅唯一解。Roll-on-contact 令每個操作 by construction 合法 — 呢個比任何 validation dialog 都好。
