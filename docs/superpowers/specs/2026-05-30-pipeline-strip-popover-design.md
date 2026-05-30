# 主介面 Pipeline Strip 顯示修復 — 精簡 + 步驟 popover

**日期**：2026-05-30
**Branch**：`fix/profile-and-v6`
**範圍**：`frontend/index.html`（CSS + `renderPipelineStrip` / `renderPipelineStripV6` + toggle JS）
**狀態**：Design — 待 user review

---

## 1. 問題（已實證）

主介面 topbar 嘅 pipeline strip（`#pipelineStrip`）喺 MacBook 14"（1512px）兩個 mode（Profile + V6）都顯示異常：steps（ASR/MT/輸出/術語表 或 VAD/Qwen3/輸出/Refiner）被壓到 ~25-60px、文字同箭咀**重疊成 unreadable garble**。

實測（Playwright 1512×900）：`.b-topbar` grid `auto minmax(0,1fr) auto auto` 分配後，search 234px + health-cluster **336-428px** + userChip 159px 食晒，`.pipeline-strip` 只剩 **399px(Profile)/491px(V6)**；preset dropdown 又食 **210-224px**；strip `overflowing:true`（scrollW > clientW）；steps flex-shrink 到 ~25px，`.step .v`（large-v3 / qwen3.5-35b-a3b / MP4）溢出重疊。現有 `@media (max-width:1100px)` compact 規則喺 1512 唔觸發。Mode-independent。截圖證據：`frontend/diag_topbar_profile.png` / `diag_topbar_v6.png`。

## 2. Root cause

橫向 strip 喺寬度受限嘅 topbar grid 入面，硬塞 preset + 4 steps + 箭咀，空間不足時 flex 壓縮 steps 至文字溢出重疊，且冇 graceful degradation。

## 3. 目標 / 決策（Option C：精簡 strip + 步驟 popover）

Topbar strip 永遠 compact（只 preset 選擇器 + 一粒「步驟」toggle），永遠 fit；完整 steps 搬入一個**寬度唔受 topbar grid 限制**嘅 popover，撳 toggle 彈出。steps 喺 popover 內有充足空間 → 永遠唔 garble；每個 step 嘅現有互動 100% 保留。

## 4. 設計

### 4.1 結構轉換（兩個 renderer 共通）

現有兩個 renderer 嘅 `el.innerHTML` 結構：
```
<div class="pipeline-preset-wrap"> …preset button + preset-menu… </div>
<span class="sep"></span>
…steps（.step + .arrow…，含各自 hover-menu / onclick）…
```
改為：
```
<div class="pipeline-preset-wrap"> …不變… </div>
<button class="pipeline-steps-toggle" onclick="togglePipelineSteps(this)">
  <span class="k">步驟</span><svg caret/>
</button>
<div class="pipeline-steps-popover">
  …steps（原封不動，連 hover-menu / onclick / arrows）…
</div>
```
**steps 內部 markup 完全唔變** —— 只係由 inline 搬入 `.pipeline-steps-popover` container，並喺前面加 toggle。preset-wrap 留 inline。

### 4.2 CSS

```css
/* strip 容器需要 relative 畀 popover 定位 */
.pipeline-strip { position: relative; }

/* preset 名 cap 闊度，唔再食 200px+ */
.pipeline-strip .pipeline-preset .pp-v {
  max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* compact toggle，樣式同 step 一致 */
.pipeline-steps-toggle {
  display: inline-flex; align-items: center; gap: 4px;
  background: none; border: 0; cursor: pointer;
  padding: 6px 10px; border-radius: 8px; color: var(--text-mid);
}
.pipeline-steps-toggle:hover { background: var(--surface-3); color: var(--text); }
.pipeline-steps-toggle .k { font-weight: 700; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }

/* 步驟 popover：闊度唔受 topbar 限制 → steps 有自然全寬，唔壓縮唔重疊 */
.pipeline-steps-popover {
  display: none;
  position: absolute; top: 100%; left: 0; margin-top: 6px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 16px 40px rgba(0,0,0,0.55);
  padding: 4px 6px; z-index: 90;
  align-items: center; gap: 2px;
  width: max-content; max-width: 90vw;
  /* overflow:visible 讓 step 嘅 hover-menu 向下逸出唔被剪 */
  overflow: visible;
}
.pipeline-steps-popover.open { display: flex; }
```

- popover `width: max-content` → steps 攞自然全寬（4 steps + 箭咀 ≈ 500-600px，遠低於 90vw=1360px @14"）→ 無壓縮無重疊。
- `overflow: visible` → 各 step 嘅 `.step-menu`（`position:absolute; top:100%`）正常向下展開唔被剪。
- popover z-index 90（高於 topbar content）；內部 `.step-menu` z-index 100（既有）→ stack 正常。

### 4.3 Toggle JS

新增 module-scope function：
```javascript
function togglePipelineSteps(btn) {
  const pop = btn.parentElement.querySelector('.pipeline-steps-popover');
  if (!pop) return;
  const willOpen = !pop.classList.contains('open');
  // 收埋其他開咗嘅（preset-menu 等）唔需要 — 只 toggle 自己
  pop.classList.toggle('open', willOpen);
}
// 撳出面收埋
document.addEventListener('click', (e) => {
  document.querySelectorAll('.pipeline-steps-popover.open').forEach(pop => {
    if (!pop.parentElement.contains(e.target)) pop.classList.remove('open');
  });
});
```
（outside-click handler 喺頁面 init 時 attach 一次；若已有類似 global handler 可併入。）

### 4.4 行為

- Compact strip：`[🔀 Pipeline · V6 / 賽馬廣播 ▾]  [步驟 ▾]` —— preset 選擇器（名 truncate）+ 步驟 toggle。永遠 fit topbar。
- 撳「步驟 ▾」→ popover 喺下方彈出，顯示完整 ASR→MT→輸出→術語（或 VAD→Qwen3→輸出→Refiner），值唔截斷、唔重疊。
- popover 內每個 step 互動不變：Profile ASR/MT hover-menu；V6 qwen3/refiner onclick `openPromptPanelInline`；VAD/輸出 read-only。
- 撳 toggle 再撳 / 撳出面 → 收埋。

## 5. 範圍外
- Backend 零改。
- preset-menu / step-menu / openPromptPanelInline 內部邏輯唔改（只係位置由 inline 變 popover 內）。
- health-cluster / search / userChip 唔改（root cause 由 popover 方案繞過，唔需要 reclaim 寬度）。
- 既有 `@media (max-width:1100/768)` 規則保留（mobile topbar-mid 仍 `display:none`，popover 一樣藏起）。

## 6. 風險
| 風險 | 緩解 |
|---|---|
| popover 內 hover-menu 被剪 | popover `overflow:visible` + z-index stack；Playwright 驗 hover-menu 可見 |
| nested hover 太 fiddly | 若實作發現 Profile ASR/MT hover-menu 喺 popover 內難用，將嗰兩個 step 由 hover 改 click（spec 容許此 fallback） |
| toggle 同 preset-menu 互相干擾 | 兩者獨立 container；outside-click 各自收埋 |
| 兩個 renderer 改唔一致 | 同一 transformation 套兩個；Playwright 兩個 mode 都測 |

## 7. 測試
**Playwright（`frontend/tests/test_pipeline_strip_popover.spec.js`）@ 1512×982，Profile + V6 兩個 mode：**
- strip 永遠唔 overflow：`.pipeline-strip` scrollWidth ≈ clientWidth（≤2px）。
- 預設 popover 隱藏（`.pipeline-steps-popover` 不可見）。
- 撳「步驟」toggle → popover 可見，內含 steps；steps 唔重疊（相鄰 step bounding box 唔重疊、每個 `.step .v` scrollWidth ≤ clientWidth+2）。
- 撳出面 → popover 收埋。
- 互動保留：V6 mode popover 內撳 Qwen3 Context step → `openPromptPanelInline` 觸發（panel 出現）；Profile mode preset 選擇器仍可開。

## 8. 驗收標準
1. 兩個 mode @1512：topbar strip 唔再 overflow、無 garble（preset + 步驟 toggle 永遠 fit）。
2. 步驟 popover 彈出後 steps 完整、值唔截斷唔重疊。
3. 所有現有互動保留（preset 切換、V6 qwen3/refiner inline panel、Profile ASR/MT 選擇）。
4. 撳出面收埋；mobile（≤768）行為不變。
5. Playwright 全綠。
