"""MT runner — 行真 crosslang_mt 路徑，只 override racing prompt（唔改真檔）。"""
import json
import sys
import urllib.request
from typing import List

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
sys.path.insert(0, MAIN + "/backend")
import translation.crosslang_mt as cmt  # noqa: E402

MODEL = "qwen3.5:35b-a3b-mlx-bf16"
BASELINE_PATH = MAIN + "/backend/config/mt_style_prompts/racing.txt"
CANDIDATE_PATH = (MAIN + "/.claude/worktrees/quality-standard/docs/superpowers/specs"
                  "/2026-07-08-quality-standard-research/protos/racing_p0/racing_candidate.txt")


def read_prompt(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def ollama(system: str, user: str, temperature: float = 0.3, timeout: int = 600,
           attempts: int = 3) -> str:
    # keep_alive 令 79GB model 全程駐留，避免 call 之間被 evict 要 cold-reload
    #（cold-reload 曾超 420s 令 exp_a 逾時炒檔）。timeout 逾時 = 短暫 reload → retry。
    body = json.dumps({"model": MODEL, "stream": False, "keep_alive": "30m",
                       "options": {"temperature": temperature},
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:  # noqa: BLE001 — timeout / transient reload → retry
            last = e
            print(f"    [ollama retry {i + 1}/{attempts}]: {e}", flush=True)
    raise last


# 退化守衛：qwen3.5 駐留重負下會吐 prompt 示例輸出當譯文（實測「在中段稍微」=示例二、
# 「母系源自「Reset」」=示例六）。真 input 幾乎唔可能剛好等於某示例輸出 → 當退化 echo，retry。
_EXAMPLE_OUTPUTS = frozenset({
    "他們會早段搶攻，不惜一切手段競逐。",
    "在中段稍微",
    "他抽得三檔有利檔位，今早狀態出眾。",
    "「Family Jewel」與「Amazing Partners」均順利出閘。",
    "「Amazing Partners」是其致勝因素，跑法部署所在。",
    "牠晨操表現理想，母系源自「Reset」。",
})


import difflib  # noqa: E402

# chat-mode 退化：model 當 system prompt 係指令去回應而唔譯（實測「明白，請輸入…」）
_CHAT_MARK = ("明白", "請輸入", "請提供", "我明白", "作為", "我是一", "抱歉", "understood",
              "please provide", "as an ai", "i am")


def _is_degenerate(text: str, en: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t in _EXAMPLE_OUTPUTS:
        return True
    # 近似 echo：撞正某示例輸出 ≥0.85（避開輕微變體如「他抽得 3 檔有利，今早狀態出眾」）
    for ex in _EXAMPLE_OUTPUTS:
        if difflib.SequenceMatcher(None, t, ex).ratio() >= 0.85:
            return True
    # chat-mode 拒譯
    low = t.lower()
    if any(m in t or m in low for m in _CHAT_MARK):
        return True
    return False


def run_mt(cues: List[dict], prompt_text: str, temperature: float = 0.3,
           echo_retries: int = 3) -> List[str]:
    # override 真檔載入 — translate_segments 會用呢個 cached prompt
    cmt._STYLE_CACHE["racing"] = prompt_text
    out: List[str] = []
    for cue in cues:
        en = cue.get("text") or ""
        zh = ""
        for _ in range(max(1, echo_retries)):
            zh = cmt.translate_segments([cue], "en", "zh",
                                        lambda s, u: ollama(s, u, temperature=temperature),
                                        style="racing")[0]["text"]
            if not _is_degenerate(zh, en):
                break
            print(f"    [degen-guard retry] '{en[:30]}' → 退化輸出 '{zh[:22]}'", flush=True)
        out.append(zh)
    return out
