# lq-research 共用 context（所有 agent 必讀）

## 任務
用戶要求大幅提升 yue 源賽馬影片嘅中文輸出質量。目標檔：09e0e3679f35（YTDown_YouTube_Media_9p0b_SlvsT4，108.6 秒賽事評述，48 段字幕）。核心問題：Whisper ASR 出**同音字錯誤**（馬名/賽馬術語），現有 glossary stage 只做字面 string match → 完全救唔到譯音錯字。

## 已證實 facts
- 「星際快車」vs ASR 輸出「升制快車」粵拼完全相同：`sing1 zai3 faai3 ce1`（ToJyutping 驗證）
- 用戶舉例：「內藍米字標誌星河」實為「內欄位置標之星河」；「幸運有利快」應為「幸運有你」
- 賽馬 glossary 1352 條 en→zh，target 格式「中文名 (編號)」如「有財有勢 (H037)」— 匹配時要 strip「 (XXX)」
- Glossary 覆蓋唔齊：星際快車/笑傲江湖/翠紅 FOUND；幸運有你/標之星河/美麗傳承 MISSING
- 現有 pipeline：mlx-whisper large-v3（lang=yue，initial_prompt 支援但 output_lang 路徑未用）→ passthrough（yue 口語）/formal_refine（書面語）→ OpenCC → glossary_stage（字面 match + LLM review）

## 資源
- `/tmp/lq-research/segments.json` — 48 段現有 ASR 輸出 [{idx,start,end,text,glossary_changes}]
- `/tmp/lq-research/glossary.json` — 賽馬詞彙表全文
- `/tmp/lq-research/audio.wav` — 16kHz mono 音訊（108.6s）
- `/tmp/lq-research/pylib` — `sys.path.insert(0,'/tmp/lq-research/pylib')` 後可 `import ToJyutping, pypinyin`
- mlx-whisper：用 `"/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python"`（有 mlx_whisper；model repo 用 `mlx-community/whisper-large-v3-mlx`，本地 cache 有，傳 local path 可用 huggingface_hub.snapshot_download(repo, local_files_only=True)）
- LLM：本地 Ollama `http://localhost:11434`，model **`qwen3.5:35b-a3b-mlx-bf16`**（production 同款；Validation-First 規定用 production stack）。POST /api/chat {model, messages, stream:false, options:{temperature:0.3}}
- Pipeline 源碼（read-only 參考）：`/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/.claude/worktrees/lang-quality/backend/`（output_lang_glossary.py / output_lang_postprocess.py / output_lang_aligned.py / asr/mlx_whisper_engine.py / translation/crosslang_mt.py）

## 規則
- 所有實驗結果寫落 `/tmp/lq-research/results/<你嘅代號>.json`（量化數據）+ 同名 .md（人讀摘要）。
- prototype script 留底喺 `/tmp/lq-research/protos/`。
- 量度一律對住 A1 嘅 error catalog（`/tmp/lq-research/results/A1-catalog.json`）計 recovered / missed / false_positive。
- 唔准掂 backend/data、registry、:5001 server、worktree 源碼（唔好改 — 呢輪純研究）。
- 結論要誠實：救唔到就話救唔到，數字唔好靠估。
