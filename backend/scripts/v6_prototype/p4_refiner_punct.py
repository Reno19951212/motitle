#!/usr/bin/env python3
"""V6 segmentation Validation Prototype 4 (2026-05-30).

Option 1: augment the refiner prompt so it INSERTS Chinese clause punctuation
into long run-on segments that have none, so the existing clause-split can then
break them. Validate that the augmented prompt:
  (a) adds punctuation at sensible breaks in long run-ons,
  (b) does NOT change any non-punctuation char (no meaning / name / number drift),
  (c) does NOT over-punctuate short / already-good segments.

Compares CURRENT vs AUGMENTED refiner prompt on the same inputs via the same
production model (qwen3.5:35b-a3b-mlx-bf16 @ Ollama). No pipeline mutation.

Run: python3 backend/scripts/v6_prototype/p4_refiner_punct.py
"""
import json
import os
import re
import urllib.request

TEMPLATE = "backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json"
MODEL = "qwen3.5:35b-a3b-mlx-bf16"
OLLAMA = "http://localhost:11434/api/chat"

# The new rule inserted before the 輸出 section. ONLY adds punctuation; forbids
# any character change or line break (refiner keeps first line only).
_PUNCT_RULE = (
    "3. 斷句輔助：若 target.text 超過約 24 字而中間完全冇標點符號，"
    "喺最自然嘅意群／子句邊界插入「，」或「、」，令字幕之後可以斷成可讀短句"
    "（每段大約 ≤24 字）。嚴格規則：只可以插入標點符號，"
    "絕對唔可以改動、增加或刪除任何文字（人名／地名／機構名／數字／粵語字全部原樣保留）；"
    "輸出仍然係單一 text 欄位，唔好換行。\n\n"
)

# Punctuation to strip for drift detection (Chinese + ASCII + spaces).
_STRIP = re.compile(r"[。！？，、；：,.!?;:\s]")

# Test set: 2 target run-ons (no internal punct) + 3 controls.
TESTS = [
    ("run-on 1 (no punct)", "呢度嘅每日平均都要處理超過八萬人次嘅跨境旅客同埋車輛"),
    ("run-on 2 (name+dates)", "當時嘅警務處處長麥景圖就喺一九四九年至一九五三年期間"),
    ("control short", "袁幸堯係今日最快時間"),
    ("control already-punct", "佢哋話今晚會落雨，大家記得帶遮"),
    ("control long+names", "今集嘅區區有警就請 Highland Sir 同我哋一齊深入了解打鼓嶺分區嘅警務工作"),
]


def load_prompt():
    sp = json.load(open(TEMPLATE))["system_prompt"]
    augmented = sp.replace("輸出：純 JSON object", _PUNCT_RULE + "輸出：純 JSON object")
    assert augmented != sp, "augmentation anchor not found"
    return sp, augmented


def call(system_prompt, target_text):
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(
                {"target": {"start": 0.0, "end": 5.0, "text": target_text}, "neighbors": []},
                ensure_ascii=False)},
        ],
        "stream": False,
        "think": False,  # match production OllamaLLM — qwen3.5 reasoning off
        "options": {"num_predict": 300, "temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.loads(r.read())
    content = (resp.get("message", {}).get("content") or "").strip()
    # parse {"action":"keep","text":"..."}
    try:
        if content.startswith("{"):
            return str(json.loads(content).get("text") or content).strip()
    except Exception:
        pass
    return content


def main():
    sp, aug = load_prompt()
    print("=" * 78)
    print("P4 — refiner punctuation-insertion validation (current vs augmented)")
    print("=" * 78)
    for label, text in TESTS:
        cur = call(sp, text)
        au = call(aug, text)
        in_stripped = _STRIP.sub("", text)
        au_stripped = _STRIP.sub("", au)
        drift = "NONE ✅" if au_stripped == in_stripped else "⚠️ CHARS CHANGED"
        added = au.count("，") + au.count("、") - (text.count("，") + text.count("、"))
        print(f"\n── {label} ({len(text)}字) ──")
        print(f"  in       : {text}")
        print(f"  current  : {cur}")
        print(f"  augmented: {au}")
        print(f"  added punct: {added} | non-punct drift vs input: {drift}")


if __name__ == "__main__":
    main()
