# ZH ASR Cascade — Simplified Chinese Drift Investigation

**Date:** 2026-05-08
**Branch:** Debug
**Driver:** /ralph-loop（5 iterations max）
**File under investigation:** `9f97af067e21` (賽馬娛樂新聞 25:26 #26 袁幸堯)
**Bug summary:** ASR 輸出由 ~171.48s（2:51）開始斷崖式由繁體中文崩潰成簡體中文。手動 verify：seg[170.00s]=「原來是這堆草」（繁），seg[171.48s]=「大家都非常担心马仔跌了一份午餐会饿」（簡）。

---

## ⭐ Final Verdict

**Single root cause confirmed: H1（`simplified_to_traditional` flag 喺 zh.json 完全缺席）**

| # | Hypothesis | Verdict |
|---|---|---|
| H1 | `simplified_to_traditional` 喺當前 zh.json 係咪 true？ | ✅ **Root cause** — flag absent |
| H2 | ZH profile 嘅 `language_config_id` 係咪指住 zh？ | ✅ Correct wiring |
| H3 | transcribe_with_segments() 入面 OpenCC conditional check 點寫？ | ✅ Conditional 寫法正確 |
| H4 | cn_convert.py 真係 import 到？opencc package 喺 venv？ | ✅ Stack 100% healthy |
| H5 | 抽 segment[171.48s] 嘅 raw text 對比 OpenCC 手動轉換結果 | ✅ OpenCC 真係冇跑（不是漏轉） |
| H6 | merge_short_segments() / split_segments() 喺 OpenCC 之後跑會 reset text？ | ✅ Pipeline order 安全 |

**因果鏈：**
```
zh.json 冇 simplified_to_traditional key
 → asr_params.get('simplified_to_traditional') → None (falsy)
 → app.py:483 conditional 永遠唔 enter
 → convert_segments_s2t() 永遠唔 call
 → mlx-whisper raw 輸出（中文 corpus 偏 Mandarin/簡體）
 → 頭段受 initial_prompt bias 偶然出繁體
 → 後段 prompt bias 失效後跌返訓練 distribution → 崩成簡體
```

**為何 v3.8 ship 個陣冇即時暴露呢個 bug？**
- v3.8 嘅 commit `6bb7d61` 加咗 schema validation + pipeline integration code，但**冇順手將 zh.json default 改 `simplified_to_traditional: true`**。
- 預期係用戶自己 opt-in（feature 設計上）。
- 但 ZH profile 內裡有 `initial_prompt: "繁體中文"`，頭幾分鐘嘅 raw output 偶然會係繁體，掩蓋咗 flag 缺席嘅事實。長片（>2:30）一旦 prompt bias 失效就立即崩。

**Suggested fix:**

```diff
  // backend/config/languages/zh.json
  {
    "id": "zh",
    "name": "Chinese",
    "asr": {
      "max_words_per_segment": 16,
-     "max_segment_duration": 15
+     "max_segment_duration": 15,
+     "simplified_to_traditional": true
    },
    ...
  }
```

加咗 flag 之後：
1. **新 ASR run** 會自動經 OpenCC s2hk → 全片繁體
2. **既有 file `9f97af067e21`** 嘅 stored segments **唔會自動回填** — 要 re-transcribe，或者寫 one-off migration script 對 registry 入面跑 `convert_segments_s2t(..., mode="s2hk")` 補做後處理（Iteration 1 suggested fix 段）

**架構 follow-up 考慮（不在 root cause 範圍）：**

- 而家嘅 design 係「opt-in flag」，但對 `language=zh` 嘅 ZH profile 嚟講，幾乎一定係要繁體輸出。可以諗：
  - **A方案**：將 `simplified_to_traditional: true` 寫入 zh.json default（呢個 PR 嘅修法）
  - **B方案**：將 conditional 加多個 fallback — 當 `language=zh` 但 flag 缺席，預設行 OpenCC（safer default）
  - **C方案**：Front-end Profile 表單 surface 呢個 flag，視覺提示 user opt-in

決策由 user 揀。Bug 修復不須等呢個決策。

---

## Hypothesis Backlog & Verdicts

### H1. `simplified_to_traditional` 喺當前 zh.json 係咪 true？

**Verdict:** ✅ **Confirmed root cause** — flag 完全缺席。

**Evidence:**
- 讀 [backend/config/languages/zh.json](../../../backend/config/languages/zh.json:1-12)（12 行 file 全文）：`asr` block 只有 `max_words_per_segment` + `max_segment_duration`，**完全冇 `simplified_to_traditional` key**。
- `git log -- backend/config/languages/zh.json` 顯示最近一個 touch 嘅 commit 係 v3.8 s2hk feature commit `6bb7d61`：
  ```
  6bb7d61 feat(v3.8): Chinese ASR quality — initial_prompt + s2hk + cascade fix
  ```
- `git show 6bb7d61:backend/config/languages/zh.json` 嘅內容**同 HEAD 完全一樣** — 即 v3.8 嘅 commit **冇 set `simplified_to_traditional: true` 做 default**，只係加咗 schema validation（[backend/language_config.py](../../../backend/language_config.py)）同 pipeline 嘅 conditional integration（[backend/app.py](../../../backend/app.py) 入面 `if asr_params.get("simplified_to_traditional"):`）。
- `git diff 6bb7d61 HEAD -- backend/config/languages/zh.json` 返回**空** — 即 v3.8 ship 之後，呢個 file 一直冇變過。

**因果鏈：**
```
zh.json 冇 simplified_to_traditional key
 → asr_params.get('simplified_to_traditional') 返回 None
 → app.py 入面 conditional `if asr_params.get(...)` 永遠 false
 → convert_segments_s2t() 永遠唔 call
 → mlx-whisper 原樣輸出（簡體佔多數，因 Whisper 中文 corpus 偏 Mandarin）
 → 用戶見到斷崖式簡體
```

**為何斷崖喺 ~2:51 而非由頭簡體？**
ASR 頭幾個 30s window 受 `initial_prompt: "以下係香港賽馬新聞，繁體中文。"` 影響 → decoder bias 偏繁體 token。第 5 個 30s window（~2:30 之後）prompt 影響式微，decoder 跌返 training distribution（簡體佔多）。所以實際呢條片係 **OpenCC 從來冇跑** + **`initial_prompt` 嘅繁體 bias 喺後段失效** 嘅疊加效果。OpenCC 修咗就會將簡體輸出（無論喺第幾個 window）轉返繁體；`initial_prompt` 已係 mitigation 但唔夠長保。

---

### H2. ZH profile 嘅 `language_config_id` 係咪指住 zh？

**Verdict:** ✅ **Confirmed correct wiring** — profile 完全正確接駁去 zh language config。

**Evidence（[backend/config/profiles/b877d8b5-5c44-46d9-af74-bf6367eb51c0.json](../../../backend/config/profiles/b877d8b5-5c44-46d9-af74-bf6367eb51c0.json)）：**

```json
"asr": {
  "engine": "mlx-whisper",
  "language_config_id": "zh",        ← 正確指 zh.json
  "language": "zh",                  ← 正確
  "condition_on_previous_text": false, ← v3.8 cascade fix 已 set
  "model_size": "large-v3",
  "initial_prompt": "以下係香港賽馬新聞，繁體中文。"  ← 已 set 但只 cover 頭幾個 30s window
}
```

**重要 architectural 確認：** flag 一定要喺 `zh.json` 入面，**唔係喺 profile 入面**。因為 [backend/app.py:467](../../../backend/app.py#L467) 嘅 `asr_params = lang_config["asr"]` — 即 conditional 只 read language config，唔 read profile asr block。即使將來有人試圖將 `simplified_to_traditional: true` 寫入 profile asr 都會被忽略；正確修法只有改 zh.json。

---

### H3. transcribe_with_segments() 入面 OpenCC conditional check 點寫？

**Verdict:** ✅ **Confirmed correct** — conditional 寫法正確，唔係 wiring bug。

**Evidence:**
- [backend/app.py:465-467](../../../backend/app.py#L465-L467) — `asr_params` 嘅嚟源：
  ```python
  lang_config_id = profile["asr"].get("language_config_id", language)
  lang_config = _language_config_manager.get(lang_config_id)
  asr_params = lang_config["asr"] if lang_config else DEFAULT_ASR_CONFIG
  ```
  正確 read profile.asr.language_config_id（fallback 到 `language`），再經 `_language_config_manager.get()` 拎 zh.json 嘅 `asr` block。零 typo、零繞路。
- [backend/app.py:483-485](../../../backend/app.py#L483-L485) — conditional：
  ```python
  if asr_params.get("simplified_to_traditional"):
      from asr.cn_convert import convert_segments_s2t
      raw_segments = convert_segments_s2t(raw_segments, mode="s2hk")
  ```
  `.get()` 對 missing key 返回 `None`（falsy）→ block 永遠唔執行，但**唔係 bug**，係正確嘅「opt-in」設計。問題單純喺 H1（flag 缺席）。
- 即使將來改 zh.json 加 `simplified_to_traditional: true`，呢個 conditional **零改動**就會自動接駁 OpenCC pipeline。

---

### H4. cn_convert.py 真係 import 到？opencc package 喺 venv 入面咪 installed？

**Verdict:** ✅ **Confirmed healthy** — OpenCC stack 100% 完好，無 ImportError、無 silent failure。

**Evidence（4 個 sub-test 全 pass）：**

| Test | Command | Result |
|---|---|---|
| H4a | `import opencc` | ✅ 成功 import（package: `opencc-python-reimplemented`） |
| H4b | `OpenCC('s2hk').convert('担心')` | ✅ 返 `'擔心'` |
| H4c | `from asr.cn_convert import convert_segments_s2t` | ✅ 成功，docstring 完整 |
| H4d | `convert_segments_s2t([{'text': '大家都非常担心马仔跌了一份午餐会饿'}])` | ✅ 返 `'大家都非常擔心馬仔跌了一份午餐會餓'` — 對 production 出問題嗰段 perfect 轉換 |

H4d 個 input 係 `9f97af067e21` 喺 `[171.48s]` 嗰段（即 user 觀察到斷崖嗰一段）。OpenCC 跑得通、而且**完美轉換**到應有嘅繁體輸出。意思即係：呢個 production 個案嘅修復路徑非常直接 — 加返個 flag、re-transcribe 或補做後處理即可。

---

### H5. 抽 segment[171.48s] 嘅 raw text 對比 OpenCC 手動轉換結果

**Verdict:** ✅ **Confirmed: OpenCC 真係冇跑**（不是「跑咗但唔識轉某啲字」）。

**Evidence（H4d 同步收）：**

```
input (production registry)  : 大家都非常担心马仔跌了一份午餐会饿
expected (OpenCC s2hk output): 大家都非常擔心馬仔跌了一份午餐會餓
actual (registry stored text): 大家都非常担心马仔跌了一份午餐会饿  ← 同 input 一樣（即 OpenCC 從未介入）
match flag                   : True (output == expected)
```

如果 OpenCC 跑過但有 character 漏轉，stored text 應該係 mixed（部分繁、部分簡）；但實際 stored text 100% 對應未轉嘅 input，無一字轉繁。再加埋頭段（≤170s）嘅 stored text 又**確實係繁體**（例如 seg[170.00s]=「原來是這堆草」，「來」「這」係繁體），表明繁體唔係 OpenCC 提供，而係 mlx-whisper 自己受 `initial_prompt` 影響輸出嘅。

兩段對照（一段繁、一段簡）證實：**頭段繁體 = `initial_prompt` 嘅 bias 偶然 work 出嚟嘅 raw output；尾段簡體 = `initial_prompt` bias 失效後 raw output**。OpenCC **從一而終冇參與過**。

---

### H6. merge_short_segments() / split_segments() 喺 OpenCC 之後跑會唔會 reset text？

**Verdict:** ✅ **Confirmed safe** — pipeline order 正確，OpenCC 喺最後 mutation step。

**Evidence（同 H3 同一段 code 讀出）:**

[backend/app.py:461-485](../../../backend/app.py#L461-L485) 嘅 step 順序：
```
Step 1 — engine.transcribe()             (line 461)
Step 2 — split_segments()                 (line 468-472)
Step 3 — merge_short_segments()           (line 475-480)
Step 4 — convert_segments_s2t() OpenCC   (line 483-485)  ← 最後 mutation
Step 5 — emit segments to client          (line 487-498)  ← 唔再 mutate text
```

`raw_segments` 喺 step 4 之後唔再被任何 post-processor 改寫 — 即將來 zh.json 修咗 flag、OpenCC 跑咗，**結果唔會被 split/merge 覆蓋**。

---

## Suggested Fix（**唔好實作**）

**改 [backend/config/languages/zh.json](../../../backend/config/languages/zh.json:5)：**

From:
```json
{
  "id": "zh",
  "name": "Chinese",
  "asr": {
    "max_words_per_segment": 16,
    "max_segment_duration": 15
  },
  ...
}
```

To:
```json
{
  "id": "zh",
  "name": "Chinese",
  "asr": {
    "max_words_per_segment": 16,
    "max_segment_duration": 15,
    "simplified_to_traditional": true
  },
  ...
}
```

**修咗之後仍要做嘅事：**

1. 對呢條 file（`9f97af067e21`）re-transcribe（因為 segment 已存咗喺 registry，唔會自動重新轉換）
2. 或者寫一個 one-off migration script 對 registry 入面 stored segment 跑 `convert_segments_s2t(..., mode="s2hk")` 補做後處理
3. 對其他 ZH file（如有）同樣處理

---

## Next Iteration Plan

- Iteration 2: 驗證 H3（confirm conditional 真係 read 個 flag、唔係其他 path 漏咗）
- Iteration 3: 驗證 H4（OpenCC import 健康度，避免修咗 zh.json 後又遇 silent ImportError）
- Iteration 4: 抽 H5 sample 做 visual confirmation
- Iteration 5: 收 H6（pipeline order 確認 OpenCC 唔被後續 step 覆蓋）

如果 H3 / H4 揭示**第二個** bug（例如 conditional 寫錯、import 失敗），就降級 H1 為 **共因之一**而非單一 root cause。
