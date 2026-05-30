# Subsystem B — per-video 雙語(第一/第二語言)統一模型

**日期**：2026-05-30 ｜ **Branch**：`fix/profile-and-v6` ｜ **狀態**：Design — 待 user review
**研究**：[2026-05-30-unified-progress-and-bilingual-research.md](../research/2026-05-30-unified-progress-and-bilingual-research.md)
**註**：Subsystem A（進度 step-diagram）另 spec，先做。B 分 **B1（核心，此 spec）** + **B2（可選，deferred）**。

---

## 1. 問題（研究實證 + user 澄清）

字幕語言選擇喺兩個 kind 唔統一、`subtitle_source` 硬編碼 EN/ZH 而非 language-code-aware：
- **Profile**：一個 run 自動出兩個語言 —— `segments.text` = **ASR 原文(第一)**、`translations.zh_text` = **MT 譯文(第二)**。但 row 冇 `source_lang`,語言對隱式硬編碼 EN→ZH。
- **V6**：一個 run = **一個語言**(refiner = source-lang 結果);第二語言**可選、唔強制**。`by_lang` dict 可多 key 但今日得 1。
- `subtitle_text.resolve_segment_text` 硬讀 `text`/`en_text`(EN 側)+ `zh_text`(ZH 側);`subtitle_source` ∈ {auto,en,zh,bilingual} 硬編碼 'en'/'zh' 做欄名。跨 kind 語義混亂(Profile `zh`=第二/譯文;V6 `zh`=第一/refiner)。

**User 模型**:每條 video 有「第一語言 + 可選第二語言」。Profile:第一=ASR原文、第二=MT譯文(已有)。V6:第一=refiner;第二可選。

## 2. 目標 / 決策（B1）

引入 **role-based(第一/第二)語言抽象**:統一選擇器同 resolver 用「第一/第二語言」概念(language-code-aware),按 kind map 去現有 storage field。**唔大改 storage、唔強制 migration**。Profile 現有 ASR/MT 直接 map;V6 顯示一個語言(第二 track 結構預留)。零新 MT(B2 先做產生)。

## 3. 模型

### 3.1 per-file 語言 descriptor（新，derived，expose 喺 /api/files + /api/files/<id>/languages）
```
languages: [
  {role: "first",  lang: "<code>", label: "<原文/語言名>"},
  {role: "second", lang: "<code>", label: "<譯文/語言名>"}   # 可缺(V6 無第二時)
]
```
- **Profile**:`[{role:first, lang: profile.asr.language(e.g."en"), label:"原文"}, {role:second, lang:"zh", label:"譯文"}]`（Profile 今日恆 EN→ZH;lang code 由 profile.asr.language + 固定 target zh）。
- **V6**：`[{role:first, lang: source_lang(e.g."zh"), label:"原文"}]`；若 `by_lang` 有第二 key → 加 `{role:second, lang:<2nd>, label:"譯文"}`（B2 先會 populate）。

### 3.2 role → storage field 對映（resolver 內部，per kind）
| role | Profile | V6 |
|---|---|---|
| first | `seg.text` / `en_text`(ASR 原文) | `by_lang[source_lang].text` / `zh_text` mirror(refiner) |
| second | `zh_text`(MT 譯文) | `by_lang[<2nd>].text`（B2，今日無）|

### 3.3 統一選擇器
`subtitle_source` 由 {auto,en,zh,bilingual} 擴為 **{auto, first, second, bilingual}**（canonical role-based）。**Backward-compat**：保留 `en`/`zh` 做 alias —— resolver 內部把 legacy `en`→`first`、`zh`→`second`（Profile 一致;V6 `zh` 因為 refiner=first 會 map 去 first，由 descriptor 解決）。新 UI 用 first/second + 顯示實際語言名(由 descriptor)。

## 4. 設計（B1）

- **`backend/subtitle_text.py`**：
  - `VALID_SUBTITLE_SOURCES` 加 `first`/`second`(保留 en/zh/auto/bilingual)。
  - `resolve_segment_text(seg, mode, order, line_break, *, first_field=None, second_field=None)` —— mode 'first'/'second'/'bilingual' 用傳入嘅 first/second 取值 helper(取代硬讀 en_text/zh_text)。legacy 'en'/'zh'/'auto' 行為保留(map en→first/zh→second)。
  - 新 helper `resolve_language_descriptor(file_entry, profile_or_pipeline)` → 上面 3.1 嘅 list。
- **`backend/app.py`**：
  - `/api/files` 每 file 加 `languages`(by descriptor)。新 `GET /api/files/<id>/languages`。
  - `POST /api/render` + `GET /api/files/<id>/subtitle.<fmt>` + `PATCH /api/files/<id>` 嘅 subtitle_source 接受 first/second/bilingual(+ legacy en/zh)。render/export 用 descriptor 解析 role → 取對應 track text(取代現有硬 zh_text 讀法 + V6 zh-source en 拒絕 guard 改用 descriptor)。
  - `PATCH /api/files/<id>/translations/<idx>` 接 optional `role`(預設 'second' for Profile 向後兼容 = zh_text;'first' for V6 = refiner)—— 寫去對應 field（+ V6 dual-write by_lang）。
- **`frontend`**（index.html file-card dropdown + proofread `#proofreadSourceMode`）：選項由硬「原文 EN / 譯文 ZH / 雙語」改為由 `file.languages` descriptor 動態顯示「第一語言:<名> / 第二語言:<名> / 雙語 / 跟 Profile」;V6 無第二語言時隱藏第二選項。`pickSubtitleText` JS resolver mirror backend role-based。

## 5. B2（deferred，可選 — 唔喺此 plan）
V6 真正**產生**第二語言:V6 pipeline 加 translator stage（用 pipeline JSON 現有空 `translators` + `target_languages`），refiner 結果再翻譯到 target lang，寫入 `by_lang[<2nd>]` + mirror。Additive。等 user 要先做。

## 6. 範圍外
- 同 Subsystem A（進度）唔重疊（A 改 progress contract;B 改 language model）。共用 active_kind 抽象。
- 唔強制 storage migration（role→field 對映喺 resolver,舊資料照讀）。
- glossary 第二語言對(B2 相關)。

## 7. 風險
| 風險 | 緩解 |
|---|---|
| resolver generalize 撞既有 en/zh 行為 | 保留 en/zh alias + 完整既有 test 不變;新增 first/second test |
| 跨 kind role 對映錯(Profile zh=second vs V6 zh=first) | descriptor 由 kind derive role;unit test 兩 kind 各驗 |
| render/export 改動破壞現有 zh 輸出 | descriptor 對 Profile 解析 second=zh_text(= 現行為);regression test |
| V6 無第二語言時 UI 出空第二選項 | descriptor 缺 second → UI 隱藏;test |

## 8. 驗收標準（B1）
1. `/api/files` 每 file 有 `languages` descriptor;Profile=[first:原文, second:譯文]、V6=[first:原文]。
2. 統一選擇器顯示實際語言名;V6 無第二語言時唔出第二選項。
3. `resolve_segment_text` role-based(first/second/bilingual)正確,legacy en/zh 行為不變。
4. render/export/PATCH 接 first/second;Profile 現有 zh 輸出不變(second=zh_text)。
5. 兩 kind regression 綠;新 first/second test 綠。
6. B2(V6 產生第二語言)deferred,結構預留(by_lang multi-key + translators key)。
