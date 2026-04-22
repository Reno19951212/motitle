# Proofread Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `proofread.html` so 段列表 occupies the full-height left column, Video and 修改字幕 sit side-by-side in the top-right area (equal width), and 時間軸 moves to the bottom of the right column.

**Architecture:** Method A — outer grid stays `340px | 1fr`; inside `.rv-b-right`, a new `.rv-b-top-row` grid wrapper holds Video (left) and Detail (right) at `1fr 1fr`; 時間軸 panel sits below as `flex-shrink:0`. Only HTML structure and two CSS rules change — no JS touched.

**Tech Stack:** Vanilla HTML/CSS, `frontend/proofread.html` only

---

### Task 1: Add `.rv-b-top-row` CSS rule

**Files:**
- Modify: `frontend/proofread.html` (CSS section, around line 301–303)

- [ ] **Step 1: Add the new CSS rule**

Find the block (around line 301):
```css
.rv-b-left { display: flex; flex-direction: column; gap: 12px; min-height: 0; min-width: 0; }
.rv-b-right { display: flex; flex-direction: column; gap: 12px; min-height: 0; min-width: 0; }
```

Replace with:
```css
.rv-b-left { display: flex; flex-direction: column; gap: 12px; min-height: 0; min-width: 0; }
.rv-b-right { display: flex; flex-direction: column; gap: 12px; min-height: 0; min-width: 0; }
.rv-b-top-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
```

- [ ] **Step 2: Update `.rv-b-video-wrap`**

Find (around line 304):
```css
.rv-b-video-wrap { flex-shrink: 0; }
```

Replace with:
```css
.rv-b-video-wrap { flex-shrink: 0; min-height: 0; }
```

- [ ] **Step 3: Verify CSS changes**

Read back lines 301–306 of `frontend/proofread.html` to confirm both rules are present and correct.

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): add rv-b-top-row CSS for layout redesign"
```

---

### Task 2: Restructure HTML — move video, add wrapper, reorder timeline

**Files:**
- Modify: `frontend/proofread.html` (HTML body, lines 526–594)

- [ ] **Step 1: Replace the entire `.rv-b` HTML block**

Find this block (lines 528–593):
```html
      <div class="rv-b">

        <!-- Left: video + segment rail -->
        <div class="rv-b-left">
          <div class="rv-b-video-wrap">
            <div class="rv-b-video">
              <div class="rv-b-video-placeholder" id="videoPlaceholder">選擇檔案以預覽視頻</div>
              <video id="videoPlayer" style="display:none;" controls></video>
              <div class="rv-b-video-sub" id="videoSub" style="display:none;"></div>
            </div>
          </div>

          <div class="rv-b-rail">
            <div class="rv-b-rail-head">
              段列表 · <span id="segCount">0</span> 段
            </div>
            <div class="rv-b-rail-list" id="segList">
              <div class="rv-b-rail-empty">載入中…</div>
            </div>
          </div>
        </div>

        <!-- Right: timeline + detail -->
        <div class="rv-b-right">
          <div class="rv-b-timeline-panel">
            <div class="rv-b-timeline-head">
              <div class="rv-b-tlh-l">
                <span class="k">時間軸</span>
                <span class="dot">·</span>
                <span>撳條波形跳至該位置</span>
              </div>
              <div class="rv-b-tlh-r">
              </div>
            </div>
            <div class="rv-wave" id="waveform" style="height:96px;">
              <div class="rv-wave-bars" id="waveformBars"></div>
              <div class="rv-wave-regions" id="waveformRegions"></div>
              <div class="rv-wave-playhead" id="waveformPlayhead" style="left:0%;display:none;">
                <div class="rv-wave-playhead-dot"></div>
              </div>
              <div class="rv-wave-ticks" id="waveformTicks"></div>
            </div>
            <div class="rv-b-wave-ctrl">
              <div class="rv-b-wave-ctrl-l">
                <span>當前：段 #<span id="curId">—</span></span>
                <span class="dot">·</span>
                <span class="mono">In <span id="curIn">—</span></span>
                <span class="dot">·</span>
                <span class="mono">Out <span id="curOut">—</span></span>
                <span class="dot">·</span>
                <span><span id="curDur">—</span>s</span>
              </div>
              <div class="rv-b-wave-ctrl-r">
                <button class="btn btn-ghost btn-sm" onclick="nav(-1)" title="上一段 (J)">◀</button>
                <button class="btn btn-ghost btn-sm" onclick="nav(1)" title="下一段 (K)">▶</button>
              </div>
            </div>
          </div>

          <div class="rv-b-detail" id="detailPanel">
            <div class="rv-b-empty" id="detailEmpty">選擇一段開始校對</div>
          </div>
        </div>

      </div>
```

Replace with:
```html
      <div class="rv-b">

        <!-- Left: segment rail only (full height) -->
        <div class="rv-b-left">
          <div class="rv-b-rail">
            <div class="rv-b-rail-head">
              段列表 · <span id="segCount">0</span> 段
            </div>
            <div class="rv-b-rail-list" id="segList">
              <div class="rv-b-rail-empty">載入中…</div>
            </div>
          </div>
        </div>

        <!-- Right: top row (video + detail) + timeline at bottom -->
        <div class="rv-b-right">
          <div class="rv-b-top-row">
            <div class="rv-b-video-wrap">
              <div class="rv-b-video">
                <div class="rv-b-video-placeholder" id="videoPlaceholder">選擇檔案以預覽視頻</div>
                <video id="videoPlayer" style="display:none;" controls></video>
                <div class="rv-b-video-sub" id="videoSub" style="display:none;"></div>
              </div>
            </div>

            <div class="rv-b-detail" id="detailPanel">
              <div class="rv-b-empty" id="detailEmpty">選擇一段開始校對</div>
            </div>
          </div>

          <div class="rv-b-timeline-panel">
            <div class="rv-b-timeline-head">
              <div class="rv-b-tlh-l">
                <span class="k">時間軸</span>
                <span class="dot">·</span>
                <span>撳條波形跳至該位置</span>
              </div>
              <div class="rv-b-tlh-r">
              </div>
            </div>
            <div class="rv-wave" id="waveform" style="height:96px;">
              <div class="rv-wave-bars" id="waveformBars"></div>
              <div class="rv-wave-regions" id="waveformRegions"></div>
              <div class="rv-wave-playhead" id="waveformPlayhead" style="left:0%;display:none;">
                <div class="rv-wave-playhead-dot"></div>
              </div>
              <div class="rv-wave-ticks" id="waveformTicks"></div>
            </div>
            <div class="rv-b-wave-ctrl">
              <div class="rv-b-wave-ctrl-l">
                <span>當前：段 #<span id="curId">—</span></span>
                <span class="dot">·</span>
                <span class="mono">In <span id="curIn">—</span></span>
                <span class="dot">·</span>
                <span class="mono">Out <span id="curOut">—</span></span>
                <span class="dot">·</span>
                <span><span id="curDur">—</span>s</span>
              </div>
              <div class="rv-b-wave-ctrl-r">
                <button class="btn btn-ghost btn-sm" onclick="nav(-1)" title="上一段 (J)">◀</button>
                <button class="btn btn-ghost btn-sm" onclick="nav(1)" title="下一段 (K)">▶</button>
              </div>
            </div>
          </div>
        </div>

      </div>
```

- [ ] **Step 2: Verify HTML structure**

Grep to confirm:
```bash
grep -n "rv-b-top-row\|rv-b-left\|rv-b-right\|rv-b-video-wrap\|rv-b-detail\|rv-b-timeline-panel\|rv-b-rail" frontend/proofread.html
```

Expected output (approximate line numbers):
```
301: .rv-b-left { ... }
302: .rv-b-right { ... }
303: .rv-b-top-row { ... }
529: <div class="rv-b-left">
531:   <div class="rv-b-rail">
539: <div class="rv-b-right">
540:   <div class="rv-b-top-row">
541:     <div class="rv-b-video-wrap">
548:     <div class="rv-b-detail" id="detailPanel">
552:   <div class="rv-b-timeline-panel">
```

Confirm:
- `rv-b-video-wrap` appears inside `rv-b-top-row` (NOT inside `rv-b-left`)
- `rv-b-detail` appears inside `rv-b-top-row` (NOT after `rv-b-timeline-panel`)
- `rv-b-timeline-panel` appears after `rv-b-top-row`, as the last child of `rv-b-right`
- `rv-b-left` contains only `rv-b-rail`

- [ ] **Step 3: Open in browser and verify visually**

Open `frontend/proofread.html?file_id=<any-id>` in the browser. Confirm:
- Left column: 段列表 only, full height
- Top-right: Video (left half) + 修改字幕 detail panel (right half), side by side
- Bottom-right: 時間軸 waveform spanning the full right column width
- No layout breakage, no missing elements

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): restructure layout — 段列表 full-height left, video+detail top-right, timeline bottom"
```
