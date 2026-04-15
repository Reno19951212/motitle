# Live Video Delay Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Buffer the live video preview by a user-configurable delay so that the delayed video and immediately-displayed subtitles appear synchronised.

**Architecture:** Replace the direct `srcObject` stream assignment with a `MediaSource` + `SourceBuffer` pipeline. A `MediaRecorder` feeds WebM segments into the buffer; playback position is held N seconds behind the buffer head. Subtitle display removes its `setTimeout` wrapper. The existing delay slider controls the video buffer offset in live mode, and retains its subtitle-delay semantics in file playback mode.

**Tech Stack:** Vanilla JS (MediaSource API, MediaRecorder API), HTML5 `<video>`, no new dependencies.

---

## File Map

- **Modify:** `frontend/index.html`
  - State variables (~line 838): add video-delay buffer state
  - HTML (~line 756): add `id` to delay label for dynamic text
  - `startLive()` (~line 1318): set up MediaSource pipeline
  - `stopLive()` (~line 1508): tear down MediaSource pipeline
  - `addLiveSubtitle()` (~line 1543): remove `setTimeout` wrapper
  - `updateDelay()` (~line 1816): update label text based on mode

No new files. No backend changes.

---

### Task 1: Add delay label id and video-delay state variables

**Files:**
- Modify: `frontend/index.html:756` (HTML label)
- Modify: `frontend/index.html:838-846` (JS state variables)

- [ ] **Step 1: Add `id` to the delay label so it can be updated dynamically**

Change line 756 from:
```html
<label>字幕延遲 <span class="delay-badge">同步補償</span></label>
```
to:
```html
<label id="delayLabel">字幕延遲 <span class="delay-badge">同步補償</span></label>
```

- [ ] **Step 2: Add video-delay state variables after the existing state block (~line 846)**

After `let subtitleDuration = 4.0;` add:
```javascript
// Video delay buffering state (live mode)
let isLiveMode = false;
let delayMediaSource = null;
let delaySourceBuffer = null;
let delayRecorder = null;
let delayObjectURL = null;
let delayBufferQueue = [];  // segments waiting while SourceBuffer is updating
```

- [ ] **Step 3: Verify no syntax errors by opening the page in a browser**

Open `frontend/index.html` in a browser, check the JS console for errors. Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add delay label id and video-delay buffer state variables"
```

---

### Task 2: Implement MediaSource video buffering setup in `startLive()`

**Files:**
- Modify: `frontend/index.html:1318-1351` (`startLive()` function)

- [ ] **Step 1: Add the `setupVideoDelayBuffer(stream, video)` function**

Add this function before `startLive()` (around line 1316):

```javascript
function setupVideoDelayBuffer(stream, videoEl) {
  if (typeof MediaSource === 'undefined' || subtitleDelay === 0) {
    // Fallback: direct stream, no buffering
    videoEl.srcObject = stream;
    console.warn('MediaSource not available or delay=0, using direct stream');
    return false;
  }

  delayMediaSource = new MediaSource();
  delayObjectURL = URL.createObjectURL(delayMediaSource);
  videoEl.src = delayObjectURL;

  delayMediaSource.addEventListener('sourceopen', () => {
    // Use VP8+Opus WebM — widely supported
    const mimeType = 'video/webm; codecs="vp8, opus"';
    if (!MediaSource.isTypeSupported(mimeType)) {
      console.warn('MediaSource mime not supported, falling back to direct stream');
      teardownVideoDelayBuffer(videoEl, stream);
      videoEl.srcObject = stream;
      return;
    }

    delaySourceBuffer = delayMediaSource.addSourceBuffer(mimeType);
    delaySourceBuffer.mode = 'segments';

    delaySourceBuffer.addEventListener('updateend', () => {
      // Append queued segments
      if (delayBufferQueue.length > 0 && !delaySourceBuffer.updating) {
        delaySourceBuffer.appendBuffer(delayBufferQueue.shift());
      }
      // Keep playback trailing by the configured delay
      applyVideoDelay(videoEl);
    });

    // Start recording the stream into MediaSource
    delayRecorder = new MediaRecorder(stream, {
      mimeType: 'video/webm; codecs=vp8,opus',
      videoBitsPerSecond: 1500000,
    });

    delayRecorder.ondataavailable = async (e) => {
      if (e.data.size > 0 && delaySourceBuffer) {
        const buffer = await e.data.arrayBuffer();
        if (delaySourceBuffer.updating || delayBufferQueue.length > 0) {
          delayBufferQueue.push(buffer);
        } else {
          delaySourceBuffer.appendBuffer(buffer);
        }
      }
    };

    delayRecorder.start(500);  // produce a segment every 500ms
    videoEl.play().catch(() => {});
  });

  return true;
}

function applyVideoDelay(videoEl) {
  if (!videoEl || !videoEl.buffered || videoEl.buffered.length === 0) return;
  const bufferedEnd = videoEl.buffered.end(videoEl.buffered.length - 1);
  const target = Math.max(0, bufferedEnd - subtitleDelay);
  // Only seek if we've drifted more than 0.3s from the target
  if (Math.abs(videoEl.currentTime - target) > 0.3) {
    videoEl.currentTime = target;
  }
}
```

- [ ] **Step 2: Modify `startLive()` to use the buffer setup**

Replace lines 1334-1337 (the `// Show live video` block):
```javascript
  // Show live video
  const liveVideo = document.getElementById('liveVideo');
  liveVideo.srcObject = mediaStream;
  liveVideo.style.display = 'block';
```

With:
```javascript
  // Show live video (with delay buffer if supported)
  const liveVideo = document.getElementById('liveVideo');
  isLiveMode = true;
  const useBuffer = setupVideoDelayBuffer(mediaStream, liveVideo);
  if (!useBuffer) {
    liveVideo.srcObject = mediaStream;
  }
  liveVideo.style.display = 'block';
```

- [ ] **Step 3: Update the delay label to "畫面延遲" at the end of `startLive()`**

Add before the closing `}` of `startLive()`:
```javascript
  // Update delay label for live mode
  document.getElementById('delayLabel').innerHTML = '畫面延遲 <span class="delay-badge">同步補償</span>';
```

- [ ] **Step 4: Test in browser**

1. Open the page, start live mode (camera).
2. Verify the video appears with a slight delay.
3. Check console for errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat: implement MediaSource video delay buffer in startLive()"
```

---

### Task 3: Implement teardown in `stopLive()` and cleanup

**Files:**
- Modify: `frontend/index.html:1508-1541` (`stopLive()` function)

- [ ] **Step 1: Add the `teardownVideoDelayBuffer()` function**

Add this function right after `applyVideoDelay()`:

```javascript
function teardownVideoDelayBuffer(videoEl, fallbackStream) {
  if (delayRecorder && delayRecorder.state !== 'inactive') {
    delayRecorder.stop();
  }
  delayRecorder = null;

  if (delaySourceBuffer) {
    try {
      if (delayMediaSource && delayMediaSource.readyState === 'open') {
        delayMediaSource.removeSourceBuffer(delaySourceBuffer);
      }
    } catch (e) { /* ignore */ }
  }
  delaySourceBuffer = null;
  delayBufferQueue = [];

  if (delayMediaSource && delayMediaSource.readyState === 'open') {
    try { delayMediaSource.endOfStream(); } catch (e) { /* ignore */ }
  }
  delayMediaSource = null;

  if (delayObjectURL) {
    URL.revokeObjectURL(delayObjectURL);
    delayObjectURL = null;
  }

  if (videoEl) {
    videoEl.removeAttribute('src');
    videoEl.srcObject = fallbackStream || null;
  }
}
```

- [ ] **Step 2: Call teardown in `stopLive()`**

In `stopLive()`, add this block right before `document.getElementById('liveVideo').srcObject = null;` (line 1532):

```javascript
  // Teardown video delay buffer
  teardownVideoDelayBuffer(document.getElementById('liveVideo'), null);
  isLiveMode = false;
```

And change the existing line 1532 from:
```javascript
  document.getElementById('liveVideo').srcObject = null;
```
to (remove it — `teardownVideoDelayBuffer` already clears it):
```javascript
  // srcObject cleared by teardownVideoDelayBuffer above
```

- [ ] **Step 3: Restore delay label in `stopLive()`**

Add after `isLiveMode = false;`:
```javascript
  document.getElementById('delayLabel').innerHTML = '字幕延遲 <span class="delay-badge">同步補償</span>';
```

- [ ] **Step 4: Test in browser**

1. Start live mode, verify video delay works.
2. Stop live mode.
3. Verify no console errors, no lingering object URLs.
4. Start live mode again — should work cleanly.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat: implement video delay buffer teardown in stopLive()"
```

---

### Task 4: Remove `setTimeout` from `addLiveSubtitle()` and update `updateDelay()`

**Files:**
- Modify: `frontend/index.html:1543-1566` (`addLiveSubtitle()`)
- Modify: `frontend/index.html:1816-1819` (`updateDelay()`)

- [ ] **Step 1: Remove `setTimeout` wrapper from `addLiveSubtitle()`**

Replace lines 1554-1557:
```javascript
  const delay = subtitleDelay * 1000;
  setTimeout(() => {
    showSubtitleText(text);
  }, delay);
```

With:
```javascript
  showSubtitleText(text);
```

- [ ] **Step 2: Update `updateDelay()` to change label based on mode**

Replace the `updateDelay` function:
```javascript
function updateDelay(val) {
  subtitleDelay = parseFloat(val);
  document.getElementById('delayValue').textContent = `${val}s`;
  // In live mode, apply the new delay to the video buffer immediately
  if (isLiveMode) {
    const liveVideo = document.getElementById('liveVideo');
    applyVideoDelay(liveVideo);
  }
}
```

- [ ] **Step 3: Test in browser**

1. Start live mode with delay set to 2s.
2. Speak — subtitle should appear immediately.
3. Video should trail real-time by ~2s.
4. Adjust slider mid-stream — video offset should change smoothly.
5. Switch to file playback mode — subtitles should sync via `timeupdate` as before.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat: show live subtitles immediately, apply delay to video buffer"
```

---

### Task 5: Handle edge cases and fallback

**Files:**
- Modify: `frontend/index.html` (minor additions)

- [ ] **Step 1: Handle delay=0 in live mode**

In `setupVideoDelayBuffer()`, the check `subtitleDelay === 0` already falls back to direct stream. Verify this works:

1. Set slider to 0.
2. Start live mode.
3. Video should play in real-time (direct stream), subtitles show immediately.

- [ ] **Step 2: Handle browser without MediaSource**

The `typeof MediaSource === 'undefined'` check in `setupVideoDelayBuffer()` handles this. To test, temporarily add `window.MediaSource = undefined` before `startLive()` and verify fallback works (direct stream + immediate subtitle display).

- [ ] **Step 3: Verify file playback mode is unaffected**

1. Upload a file and transcribe.
2. Play the video.
3. Adjust delay slider.
4. Verify subtitles sync via `timeupdate` offset as before.
5. Verify label shows "字幕延遲".

- [ ] **Step 4: Final commit**

```bash
git add frontend/index.html
git commit -m "feat: complete live video delay sync with fallback handling"
```
