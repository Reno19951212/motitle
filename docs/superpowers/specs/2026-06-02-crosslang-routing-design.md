# Cross-language 輸出路由設計（Whisper 直出 + ASR+MT 混合）2026-06-02

**Goal**：output_lang pipeline 按「內容語言 vs 輸出語言」自動路由 —— 同方言用 Whisper 直出（最佳分句/質量），跨語言/跨方言用「內容 ASR + MT→輸出」，令任何輸出語言組合都有高質字幕。

**Branch**：`feat/output-language-pipeline`（worktree `worktree-fix-output-lang-single-display`）。

**Validation 證據**：[2026-06-02-crosslang-routing-validation-tracker.md](2026-06-02-crosslang-routing-validation-tracker.md)（全 matrix + 普通話 v2 再驗證，假設 ✅ VALIDATED）。

---

## 1. 背景 / 問題
現 output_lang 全部用 Whisper force-language 直出。實證：輸出語言 == 內容語言時優秀；不一致時崩壞 —— 死 loop（`police police police`/`舞舞舞`/`皮皮皮`）、幻覺、中日混合、誤譯（last-16→「16分」）、碎段爆炸（英→中 105 段）。跨語言 ASR+MT（即使 naive 1:1）一致勝出。普通話 v2 再揭示**粵↔普 cross-dialect 不對稱**：`普通話→口語廣東話` Whisper force-`yue` 唔會轉粵語（仍出普通話），必須 ASR+MT。

## 2. 語言模型
**來源語言**（`source_language`，權威，驅動 ASR + 路由）：`yue`(粵語) / `cmn`(普通話) / `en`(英文) / `ja`(日文)。
> 注：內部 source code 用 `cmn` 代表普通話以區別於輸出 `zh`；Whisper ASR：yue→`language=yue`、cmn→`language=zh`、en→`en`、ja→`ja`。

**輸出語言**（`output dropdown`）：`yue`(口語廣東話) / `zh`(中文書面語) / `cmn`(普通話) / `en`(英文) / `ja`(日文)。
> `zh` 同 `cmn` 同樣係 Mandarin-based 書面中文 base，分別在 register：`zh`(中文書面語) 加 V6 formal refiner；`cmn`(普通話) raw 唔加。

**字體**（`script`，只中文輸出 yue/zh/cmn 適用）：`trad`(繁體，OpenCC `s2hk`) / `simp`(簡體，OpenCC `t2s`)。永遠明確 OpenCC —— Whisper 'zh' native script 不穩定（v2 實證普通話片 native 出繁體），唔可靠。

## 3. 路由規則（實證敲定）
對**每個**輸出語言獨立判斷。`base 文本` 來源：

| 輸出 | Whisper 直出 條件（內容 audio）| 否則 |
|---|---|---|
| `yue` 口語廣東話 | 內容=`yue` | ASR(內容)+MT(→粵口語) |
| `zh` 中文書面語 | 內容∈{`yue`,`cmn`} | ASR(內容)+MT(→中文) |
| `cmn` 普通話 | 內容∈{`yue`,`cmn`} | ASR(內容)+MT(→中文) |
| `en` 英文 | 內容=`en` | ASR(內容)+MT(→英文) |
| `ja` 日文 | 內容=`ja` | ASR(內容)+MT(→日文) |

規則一句講：**Whisper 直出 iff「該輸出方言嘅 Whisper 轉錄喺該內容音上得到目標」** —— `yue` 限粵語內容；`zh`/`cmn` 收粵+普（Whisper 'zh' 食慣粵音→中文字幕，驗 5/4/5）；`en`/`ja` 限同語言內容。其餘（含粵↔普 cross-dialect、所有跨語言）→ ASR+MT。

純函數 `route_output(source_language, output_lang) -> "whisper" | "asr_mt"` 封裝此表（見 §6）。

## 4. 中文輸出可組合 pipeline
任何中文輸出（yue/zh/cmn）：
```
base 文本（Whisper 直出 或 ASR+MT）
  → [若 output==zh：V6 formal-register refiner]   # 重用 zh_written_register_v6 + refiner profile 9dbe1aa3
  → [clause_split（若 base 來自 ASR+MT，控 over_cap）]
  → OpenCC（script==trad → s2hk；script==simp → t2s）
```
英文/日文輸出：base（Whisper 或 ASR+MT）→ [clause_split 若 ASR+MT 且 CJK 否則略]。無 OpenCC、無 refiner。

## 5. 架構（選項 A：在現有 output_lang handler 內路由）
保持 `_run_output_lang`（第一輸出語言）/ `_run_output_lang_second`（asr_output job，第二輸出語言）做單一入口。新增 per-output 路由 + 共享內容 ASR。**不**動 Profile / V6 dispatch。

**內容 ASR 共享**：跨語言輸出需要「內容語言 ASR」做 MT source。整條片**只跑一次** Whisper transcribe（`language=source_language` 對應碼），存落 file entry `content_asr_segments`（list）供第一 + 第二輸出語言重用，慳第二次 Whisper。

## 6. 元件 / 資料流

### 6.1 新檔 `backend/output_lang_router.py`（純函數）
```python
from typing import Dict, List, Optional

# 輸出方言 → Whisper 直出可接受嘅內容語言集合
_DIRECT_OK: Dict[str, frozenset] = {
    "yue": frozenset({"yue"}),
    "zh":  frozenset({"yue", "cmn"}),
    "cmn": frozenset({"yue", "cmn"}),
    "en":  frozenset({"en"}),
    "ja":  frozenset({"ja"}),
}

def route_output(source_language: str, output_lang: str) -> str:
    """Return 'whisper' (direct) or 'asr_mt' for one output language."""
    return "whisper" if source_language in _DIRECT_OK.get(output_lang, frozenset()) else "asr_mt"

# 輸出方言 → Whisper transcribe 參數（直出路徑）
_WHISPER_LANG: Dict[str, str] = {"yue": "yue", "zh": "zh", "cmn": "zh", "en": "en", "ja": "ja"}

def whisper_direct_params(output_lang: str) -> dict:
    """language=/task= for direct Whisper of this output dialect (no script — OpenCC handled later)."""
    if output_lang in ("yue", "zh", "cmn"):
        return {"lang_override": _WHISPER_LANG[output_lang], "task_override": "transcribe"}
    if output_lang == "ja":
        return {"lang_override": "ja", "task_override": "transcribe"}
    return {"lang_override": "en", "task_override": "transcribe"}  # en content→en

def content_asr_lang(source_language: str) -> str:
    """Whisper language for transcribing the CONTENT (the MT source)."""
    return {"yue": "yue", "cmn": "zh", "en": "en", "ja": "ja"}[source_language]
```

### 6.2 新檔 `backend/translation/crosslang_mt.py`（generic 參數化 cross-lang MT）
```python
from typing import List, Optional

# 輸出方言 → MT 目標語言描述（代入 prompt）
_MT_TARGET_NAME = {
    "yue": "香港口語廣東話（用口語字眼如 嘅/係/喺/咗/唔/睇，繁體字）",
    "zh":  "現代正式繁體中文書面語",
    "cmn": "標準普通話書面中文",
    "en":  "English",
    "ja":  "自然書面日本語",
}
_SRC_NAME = {"yue": "粵語/中文", "cmn": "普通話/中文", "en": "English", "ja": "Japanese"}

_MT_SYS = ("你係專業廣播字幕翻譯員。將用戶提供嘅單句{src}字幕，翻譯成{tgt}。"
           "規則：貼近廣播口播、自然流暢；唔好加原文冇嘅資訊；保留專有名詞；"
           "輸出一行、只輸出譯文本身，唔好任何解釋或標籤。")

def translate_segments(content_segments: List[dict], source_language: str,
                       output_lang: str, llm_call) -> List[dict]:
    """Per-segment 1:1 MT preserving start/end. llm_call(system, user)->str injected
    (production: OllamaTranslationEngine bound to qwen3.5:35b)."""
    sysp = _MT_SYS.format(src=_SRC_NAME[source_language], tgt=_MT_TARGET_NAME[output_lang])
    out = []
    for s in content_segments:
        txt = (s.get("text") or "").strip()
        tr = llm_call(sysp, txt) if txt else ""
        out.append({"start": s["start"], "end": s["end"], "text": tr})
    return out
```
> MT 引擎 = Ollama `qwen3.5:35b-a3b-mlx-bf16`（現有 `OllamaTranslationEngine` 單段路徑；`llm_call` = engine 的 `_call_ollama` 包裝，think=False、temp 0.3）。

### 6.3 dispatch（`backend/app.py`，per output language）
`_run_output_lang(file_id, job, audio_path, cancel_event)` 改寫成：
1. 讀 `source_language` + `output_languages` + `script` 自 file entry。
2. 第一輸出語言 `first = outs[0]`：呼叫新 helper `_produce_output_lang(audio_path, source_language, first, script, cancel_event)` → segments。寫 `by_lang[first]` + `{first}_text` mirror（同現狀 shape）。計 `asr_seconds`。
3. 若 `len(outs)>1`：enqueue `asr_output`（同現狀）。
4. `content_asr_segments` 第一次計到就存落 file entry 供第二 pass 重用。

`_produce_output_lang(...)` 新 helper（路由核心）：
```
method = route_output(source_language, output_lang)
if method == "whisper":
    base = transcribe_with_segments(audio, **whisper_direct_params(output_lang), asr_profile_override=mlx_large_v3, progress...)
else:  # asr_mt
    content_segs = <file entry cache> or transcribe_with_segments(audio, lang_override=content_asr_lang(source_language), ...)  # 共享
    base = crosslang_mt.translate_segments(content_segs, source_language, output_lang, llm_call)
# 中文後處理
if output_lang in ("yue","zh","cmn"):
    if method == "asr_mt": base = clause_split(base, char_cap=18)   # 控 over_cap
    if output_lang == "zh": base = v6_formal_refine(base)           # register
    base = opencc(base, "s2hk" if script=="trad" else "t2s")
elif output_lang == "ja" and method == "asr_mt":
    base = clause_split(base, char_cap=18)
return base
```
`_run_output_lang_second` 同樣經 `_produce_output_lang`（第二輸出語言），重用 `content_asr_segments` cache（cross 時唔再 Whisper 一次）。

`_asr_handler` / `_whisper_params_for_lang`（舊）：保留向後兼容；新路徑優先。舊 `_whisper_params_for_lang` 對「same-dialect 直出」格仍適用，由 `whisper_direct_params` 取代/包裝。

## 7. clause-split（cross 輸出控段長）
重用 V6 `backend/stages/v6/clause_split.py::split_v6_aligned` 同款邏輯（中文標點切句 + greedy 填行 + min-dur guard），抽成可獨立呼叫嘅 `clause_split(segments, char_cap=18, min_dur=1.0)`。只施於 ASR+MT 中文/日文輸出（base 承繼內容 ASR 段，over_cap 偏高）。Whisper 直出格唔郁（分句已佳）。

## 8. 資料模型
file entry 新增：`source_language`(str ∈ {yue,cmn,en,ja})、`script`(str ∈ {trad,simp}，default trad)、`content_asr_segments`(list，cross 共享 cache，可選)。
`by_lang[<output>].{text,status,flags}` + `{output}_text` mirror **完全不變** → descriptor / 資訊 tab / proofread / export / render / overlay **零改 shape**。`resolve_language_descriptor` output_lang 分支沿用（label 已涵蓋 yue/zh/en/ja；新增 `cmn` label「普通話」）。

## 9. API
`POST /api/transcribe`（現有 output_lang）新增 form field：
- `source_language`：str ∈ {yue,cmn,en,ja}（必，output_lang mode）。
- `script`：str ∈ {trad,simp}（可選，default trad）。
- `output_languages`：JSON array（現有；值擴至含 `cmn`）。
驗證失敗 → 400 `{error}`。`/api/files/<id>/translate-second {lang}`：`lang` 可為 cmn；route_output 決定 whisper/asr_mt。

## 10. 前端（`index.html` 上傳 popup `#olOverlay`）
- **來源語言** dropdown：`粵語 / 普通話 / 英文 / 日文`（取代 `中文/英文/日文/其他`），變**權威**送 `source_language`。
- **輸出第一/第二語言** dropdown：`口語廣東話 / 中文書面語 / 普通話 / 英文 / 日文`（第二可「無」）。
- **繁/簡 toggle**：一個 radio/segmented（繁體 / 簡體），送 `script`；只中文輸出有意義（純英/日輸出時可隱藏或忽略）。
- `confirmOutputLangModal` 砌 `source_language` + `output_languages` + `script` 落 FormData。
- 資訊 tab（已加）可額外顯示每個輸出語言用咗 Whisper-direct 定 ASR+MT（method）—— 可選，non-blocking。

## 11. 錯誤處理
- 路由純函數 total（unknown lang → 安全 default asr_mt）。
- MT/refiner LLM 失敗：per-segment try/except，失敗段留空 text + flag，唔中斷成個 job（現有 output_lang 模式一致）。
- content ASR 空 → status='error'（現有）。
- 路由唔影響 cancel_event / poison-pill retry（沿用）。

## 12. 測試
- `test_output_lang_router.py`：`route_output` 全 matrix（粵→yue=whisper、普→yue=asr_mt、英→中=asr_mt、普→中=whisper…）+ `whisper_direct_params` / `content_asr_lang`。
- `test_crosslang_mt.py`：`translate_segments` 用 stub llm_call（1:1、空段、prompt 代入 src/tgt）。
- `test_produce_output_lang.py`：dispatch 路由（stub transcribe + stub MT）→ whisper vs asr_mt 分流 + 中文後處理鏈（refiner only for zh、OpenCC trad/simp、clause_split only asr_mt）。
- 整合 re-run（真片每路由格）：粵→yue(whisper)、普→yue(asr_mt)、英→中(asr_mt)、普→中(whisper)、各 +繁/簡。
- Regression：same-dialect 直出 + Profile/V6 byte-identical；現有 output_lang single/dual 顯示 fix + 資訊 tab 不破。
- Playwright：popup 來源 dropdown(粵/普) + 繁簡 toggle 送正確 form。

## 13. File structure
- 新：`backend/output_lang_router.py`、`backend/translation/crosslang_mt.py`、`backend/output_lang_clause_split.py`（或重用 v6 clause_split 抽 helper）、上述 test 檔。
- 改：`backend/app.py`（`_run_output_lang`/`_run_output_lang_second`/`_produce_output_lang`/`/api/transcribe` 收新 field）、`backend/subtitle_text.py`（`cmn` label + descriptor）、`frontend/index.html`（popup 來源 dropdown + 繁簡 toggle + confirm）、`backend/asr/__init__` 無需改。
- 重用：`config/prompt_templates_v5/refiner/zh_written_register_v6.json` + refiner profile `9dbe1aa3`（V6 formal refiner）、OpenCC（`asr/cn_convert.py` 或直接 opencc）、`OllamaTranslationEngine`。

## 14. 範圍外（v2）
- Glossary 專名注入入 cross-lang MT（驗證見 檢閱官→censor / 卡里亞 等專名誤譯，廣播片需要，但 v1 先用 generic prompt）。
- MT sentence-pipeline 上文（v1 single-segment 1:1 已勝 Whisper-direct；上文可再提質）。
- 中文書面語經 ASR(yue)+refiner vs Whisper-zh+refiner 的細微 fidelity 取捨（v1 用路由表現選）。
- 來源語言 Whisper 自動偵測（v1 靠 dropdown 權威）。
