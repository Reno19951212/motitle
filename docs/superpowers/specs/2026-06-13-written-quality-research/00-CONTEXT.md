# lq-written 共用 context（所有 agent 必讀）

## 任務
大幅提升**中文書面語**（yue 源 → zh refine 軌）輸出質量。口語廣東話軌已經靠語音糾錯（已 ship 落 dev）做到高質，但書面語 refiner 仍然有兩類問題：
1. **字唔準 / 名詞被破壞**：馬名術語被當普通詞改走 — 好友心得→獲好評、幸運有您→「幸運，有您支持」、錶之星河→「米字」星河、尾三→第三匹、尾二→最後兩匹/最後一件
2. **意思解錯 / 幻覺**：逐段獨立改、短句冇上下文 → 亂解＋無中生有（精算暴雪→「表現穩健」）

用戶核心要求：**令 refiner 參考返成個 transcript / 上下文嘅意思嚟做**（而家係逐段孤立）。

## 現狀機制（root cause）
- `backend/output_lang_postprocess.py` `formal_refine(segments, llm_call, style)`：**逐段獨立** `llm_call(sysp, one_segment_text)` — 零上下文。
- racing prompt：`backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`（system_prompt 已有 rule 6「byte-for-byte 保留人名/地名/賽馬術語」+ rule 5 數字保留，但實測照樣破壞名詞 + 誤解位置術語「尾二/尾三/尾四」）。
- 書面語係 yue→zh 嘅 derive mode='refine'；輸入 base 係語音糾錯後嘅口語文字。

## 資源
- `/tmp/lq-written/corrected_spoken.json` — 語音糾錯後嘅高質口語 base（48 段，refine 嘅 INPUT）[{start,end,text}]
- `/tmp/lq-written/current_written.json` — 現狀書面語輸出（問題所在）[{idx,spoken,written}]
- `/tmp/lq-research/glossary.json` — 賽馬詞彙表（1352 條，target「名 (編號)」）
- `/tmp/lq-research/results/A1-catalog.json` — 口語 error catalog（每段 corrected_text，可借嚟做書面語 ground-truth 嘅起點）
- `/tmp/lq-research/audio.wav` — 原音訊（108.6s，需要核對原意時用）
- racing refiner prompt：上述 json
- `backend/phonetic_correction.py` — **B1 粵拼 matcher 可重用**做「書面語後處理名詞校驗」（build_index/match_segments — 將 refine 後文字再對詞彙表/術語表，捉走被改壞嘅名）

## Stack（Validation-First 強制 — 用 production 同款）
- LLM：**本地 Ollama `qwen3.5:35b-a3b-mlx-bf16`** @ temp 0.3（正常模式，Beta 已關）。POST http://localhost:11434/api/chat {model, messages, stream:false, think:false, options:{temperature:0.3}}。**一定要 `think:false`**（唔係會 90s+/call）。
- Python：`"/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python"`（sys.path 加 backend 可 import phonetic_correction / output_lang_postprocess）。
- 載真 prompt：`json.load(.../refiner/zh_written_register_v6.json)['system_prompt']`。

## 規則
- 結果寫 `/tmp/lq-written/results/<代號>.json`（量化）+ 同名 .md（人讀）；proto 留 `/tmp/lq-written/protos/`。
- 量度對住 W1 嘅書面語 error catalog（`/tmp/lq-written/results/W1-catalog.json`）。指標：名詞保留率、位置術語正確率（尾二/尾三 等）、意思忠實度（無幻覺/無漏意）、register 正確（真係書面語唔係口語）、格式穩定（48 進 48 出）。
- 唔准掂 backend/data、registry、:5001、worktree 源碼（純研究）。
- 誠實：改善唔到就講改善唔到，數字唔好靠估。對比一定要同 current_written.json baseline 計。
