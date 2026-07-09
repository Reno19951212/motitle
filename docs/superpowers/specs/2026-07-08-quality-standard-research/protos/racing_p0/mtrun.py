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


def ollama(system: str, user: str, temperature: float = 0.3, timeout: int = 420) -> str:
    body = json.dumps({"model": MODEL, "stream": False,
                       "options": {"temperature": temperature},
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def run_mt(cues: List[dict], prompt_text: str, temperature: float = 0.3) -> List[str]:
    # override 真檔載入 — translate_segments 會用呢個 cached prompt
    cmt._STYLE_CACHE["racing"] = prompt_text
    llm = lambda s, u: ollama(s, u, temperature=temperature)
    out = cmt.translate_segments(cues, "en", "zh", llm, style="racing")
    return [o["text"] for o in out]
