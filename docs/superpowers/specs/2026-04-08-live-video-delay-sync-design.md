# Live Video Delay Sync Design

## Problem

In live transcription mode, subtitles arrive with a processing delay (3-5s for chunk mode, 1-2s for streaming mode). The current approach delays subtitle display via `setTimeout`, but this means subtitles appear detached from the corresponding video moment. Users see speech happen on screen, then the subtitle appears seconds later.

## Solution

Reverse the delay: buffer the live video preview by N seconds so it plays behind real-time, and display subtitles immediately when received. Since both the video and the transcription are delayed by roughly the same amount, they appear synchronised to the user.

## Scope

Frontend-only change (`frontend/index.html`). No backend changes required.

## Design

### 1. Video Stream Buffering

When live mode starts:

1. The existing `getUserMedia` / `getDisplayMedia` stream is captured via a `MediaRecorder` producing WebM segments (e.g. every 500ms).
2. A `MediaSource` with a `SourceBuffer` is created and assigned to the `<video>` element's `src` (replacing the direct stream assignment).
3. Each `MediaRecorder.ondataavailable` segment is appended to the `SourceBuffer`.
4. On each append, set `video.currentTime = max(0, video.buffered.end(0) - delay)` so playback trails real-time by the configured delay.

Fallback: if `MediaSource` is not supported (unlikely in modern browsers), fall back to the current direct-stream approach with subtitle-side `setTimeout` delay.

### 2. Slider Semantics Change

- Label changes from "字幕延遲" to "畫面延遲" when in live mode.
- Label reverts to "字幕延遲" when in file playback mode.
- Range: 0-5 seconds, step 0.1s (unchanged).
- Default value: 0.5s (unchanged).
- The `updateDelay()` function updates both `subtitleDelay` (used by file playback) and the video buffering offset (used by live mode).

### 3. Subtitle Display

- Remove the `setTimeout` wrapper in `addLiveSubtitle()`. Show subtitle text immediately upon receiving `live_subtitle` events.
- The `subtitleDuration` control continues to govern how long each subtitle stays visible.

### 4. File Playback Mode (No Change)

- File playback continues using the existing `timeupdate` listener with `subtitleDelay` offset.
- The slider label shows "字幕延遲" in this mode.

### 5. Cleanup

When live mode stops:

- Stop the `MediaRecorder`.
- Revoke the `MediaSource` object URL.
- Restore normal video source handling.

## Edge Cases

- **Delay = 0**: Video plays in real-time (same as current behaviour), subtitles still show immediately (may appear slightly after the speech, acceptable).
- **User changes delay mid-stream**: `video.currentTime` is adjusted on next buffer append cycle; transition is smooth, no seek artefact expected.
- **Browser without MediaSource**: Fall back to current `setTimeout` subtitle delay approach. Log a console warning.

## What Does NOT Change

- Backend transcription logic (chunk mode, streaming mode).
- WebSocket events and payloads.
- File upload / playback / export flows.
- VAD, dedup, or context carry-over logic.
- The slider range, step, or default value.
