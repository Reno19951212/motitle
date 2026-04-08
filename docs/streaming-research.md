# 第三方 Whisper 串流方案研究報告

## 背景

現時 live 轉錄採用「每 3 秒切 chunk → 獨立轉錄」的模擬串流方式，延遲約 3-5 秒。本報告研究離線第三方串流方案，評估是否能改善延遲和體驗。

---

## 方案比較總覽

| 方案 | 串流延遲 | 繁中支援 | Flask 整合 | 離線 | 維護狀態 | 適合場景 |
|------|----------|----------|------------|------|----------|----------|
| **whisper_streaming (UFAL)** | ~3.3s | ✅ 好 | ✅ 優秀 | ✅ | ⚠️ 被 SimulStreaming 取代中 | Python 串流伺服器 |
| **SimulStreaming (UFAL)** | ~0.7s | ✅ 好 | ✅ 優秀 | ✅ | ✅ 活躍 | whisper_streaming 的繼任者 |
| **WhisperLive (Collabora)** | 低（未明確） | ✅ 好 | ⚠️ 需橋接 | ✅ | ✅ 活躍 | 多後端靈活部署 |
| **Speaches** | ~3.3s | ✅ 好 | ✅ OpenAI 兼容 API | ✅ | ✅ 活躍 | API 伺服器 |
| **whisper.cpp** | <500ms | ✅ 好 | ❌ C++ 需 wrapper | ✅ | ✅ 非常活躍 | 嵌入式/桌面端 |
| **Moonshine** | <100ms | ⚠️ 有限 | ✅ 好 | ✅ | ✅ 活躍 | 邊緣設備/超低延遲 |
| **現有方案（chunk-based）** | ~3-5s | ✅ 好 | ✅ 已整合 | ✅ | — | 當前架構 |

---

## 1. whisper_streaming (UFAL) — 最成熟的 Python 串流方案

**GitHub**: https://github.com/ufal/whisper_streaming

### 核心機制：LocalAgreement-2
- 維護一個 30 秒的滾動音訊 buffer
- 每次收到新音訊就重新轉錄整個 buffer
- **兩次連續轉錄結果一致的前綴才確認輸出**（LocalAgreement-2）
- 確認後在句子邊界截斷 buffer，繼續處理新音訊
- 自適應延遲：根據計算時間動態調整

### 後端支援
- **faster-whisper**（推薦）
- whisper-timestamped
- OpenAI API
- MLX-whisper（Apple Silicon）

### 延遲
- 平均 ~3.3 秒（英語）
- 延遲 ≈ 2 × MinChunkSize
- WER 比離線模式高 2-6%

### Flask 整合方式
```python
from whisper_online import OnlineASRProcessor, FasterWhisperASR

# 初始化（一次）
asr = FasterWhisperASR("zh", "small")
processor = OnlineASRProcessor(asr, buffer_trimming=("sentence", 15))

# 在 Flask-SocketIO handler 中：
@socketio.on('audio_chunk')
def handle_audio(data):
    audio_array = np.frombuffer(data, dtype=np.float32)  # 16kHz mono
    processor.insert_audio_chunk(audio_array)
    for begin, end, text in processor.process_iter():
        socketio.emit('live_subtitle', {'text': text, 'start': begin, 'end': end})
```

### 依賴
```
whisper-streaming
faster-whisper
librosa
soundfile
torch, torchaudio
```

### 優點
- 純 Python，易整合
- 句子邊界智能處理
- 內建 Silero VAD
- 多後端選擇

### 缺點
- **正被 SimulStreaming 取代**
- 每次要重新處理整個 buffer（計算量較大）
- 延遲仍在 3 秒級別

---

## 2. SimulStreaming (UFAL) — whisper_streaming 的繼任者

**GitHub**: https://github.com/ufal/SimulStreaming

### 核心改進
- 使用 **AlignAtt simultaneous policy**（比 LocalAgreement-2 更先進）
- **比 whisper_streaming 快 5 倍**
- 支援 Whisper large-v3、beam search、initial prompts
- MIT 授權

### 延遲
- 比 whisper_streaming 低很多（~0.7s 級別）
- 同樣的自適應機制

### 整合方式
- 與 whisper_streaming 相同的 module-based 整合模式
- 可直接替換

### 結論
- **如果要從頭整合串流方案，應該選 SimulStreaming 而非 whisper_streaming**

---

## 3. WhisperLive (Collabora) — 多後端靈活方案

**GitHub**: https://github.com/collabora/WhisperLive

### 架構
- 獨立的 client-server 架構
- 雙向 WebSocket 通訊
- Silero VAD 觸發音訊傳輸
- 部分轉錄（unconfirmed）+ 最終確認（confirmed）雙層結果

### 後端
- faster-whisper（主要）
- TensorRT（NVIDIA GPU 加速）
- OpenVINO（Intel 加速）

### Flask 整合
- **需要作為獨立服務運行**（預設 port 9090）
- 然後建立 Flask → WhisperLive 的橋接
- 或抽取其轉錄邏輯（需大量重構）

### 限制
- 最多 4 個併發連接（預設）
- 會話限時 600 秒（預設）
- 不能直接嵌入 Flask

### 繁中支援
- Whisper 只有 `zh` 語言碼，不區分繁簡
- 需用 `initial_prompt` 引導或後處理轉換

---

## 4. Speaches — OpenAI 兼容 API 伺服器

**GitHub**: https://github.com/speaches-ai/speaches

### 架構
- OpenAI API 兼容的 STT/TTS 伺服器
- Server-Sent Events (SSE) 串流
- Docker 部署
- faster-whisper 後端

### 整合
- 因為兼容 OpenAI API，用 `openai` Python SDK 即可串接
- 非常容易整合到任何 Python 應用

### 適合場景
- 需要 OpenAI API 兼容介面
- Docker 環境部署

---

## 5. whisper.cpp — 最低延遲的離線方案

**GitHub**: https://github.com/ggml-org/whisper.cpp

### 特點
- C/C++ 實作，GGML 框架
- 每 500ms 採樣一次的串流模式
- 支援 Vulkan GPU 加速
- 可在 Raspberry Pi 運行

### 整合難度
- **高**：C++ 需要 wrapper（ctypes / 子進程通訊）
- 不適合直接嵌入 Python/Flask

---

## 6. Moonshine — 超低延遲邊緣方案

**GitHub**: https://github.com/moonshine-ai/moonshine

### 特點
- 專為邊緣設備設計的輕量 ASR 模型
- 比 Whisper Tiny 減少 5 倍計算量，相同準確度
- <100ms 延遲
- ~27M 參數

### 繁中支援
- **有限**：主要針對英語和主要亞洲語言
- 無明確繁體中文模型

---

## 推薦方案

### 首選：SimulStreaming (UFAL)

**原因：**
1. 純 Python，與現有 Flask-SocketIO 架構最容易整合
2. 比 whisper_streaming 快 5 倍（~0.7s 延遲 vs 現有的 3-5s）
3. 使用相同的 faster-whisper 後端（已在項目中使用）
4. 支援 `initial_prompt`（可引導繁體中文輸出）
5. MIT 授權，活躍維護
6. 與現有的 chunk-based 方案可共存（漸進式遷移）

### 整合策略

```
Phase 1: 在現有架構旁邊加入 SimulStreaming 作為可選串流模式
Phase 2: 前端加入模式切換（chunk-based vs streaming）
Phase 3: 測試後決定是否完全遷移
```

### 次選：WhisperLive (Collabora)

如果需要 TensorRT/OpenVINO 加速支援，WhisperLive 提供更多後端選擇，但整合難度較高。

---

## 與現有方案的對比

| 指標 | 現有 chunk-based | SimulStreaming |
|------|-----------------|---------------|
| 延遲 | 3-5 秒 | ~0.7 秒 |
| 句子截斷 | 靠 overlap 緩解 | 智能句子邊界 |
| 上下文連貫 | initial_prompt carry-over | 內建 buffer 連貫 |
| VAD | 前端能量偵測 + vad_filter | 內建 Silero VAD |
| 去重 | 手動去重邏輯 | LocalAgreement 自動處理 |
| 計算量 | 每 chunk 獨立轉錄 | 重複處理 buffer（較高） |
| 部分結果 | 無（等 chunk 完成） | 有（unconfirmed + confirmed） |
| 整合難度 | 已完成 | 中等 |
