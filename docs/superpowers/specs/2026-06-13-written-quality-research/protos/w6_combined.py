"""W6 — best end-to-end combined refine pipeline (evidence-led, not stacked).

Recipe (each piece justified by W1-W5 empirical evidence):
  - BASE system prompt = W5 V2 (front-loaded iron rules: name-protect + 尾X pos gloss
    + anti-hallucination, BEFORE register-convert rules; + racing examples).  [W5: name +11pt, pos 0->100%, wrong halved]
  - + 埋邊=靠內欄 pos gloss appended (W2 missed it; W3 confirmed seg11/26/42 need it).
  - + garbled-cue guard line (W3: don't补 from context if the cue looks garbled — seg46 class).
  - + W4 P2 PER-CUE roster injection into SYSTEM (only glossary names that verbatim-hit
    THIS cue's base; auto-extracted via phonetic_correction.build_index). [W4: name->100%, mangled 5/5]
    MUST be SYSTEM not USER (W2: USER-turn roster -> 48/48 echo contract break).
  - + W3 ±2-cue context WINDOW in USER turn (semantic anchor for local meaning_error
    that prompt-alone can't fix: 米字/透出/拆名 — W5 residual seg3). [W3: name_mangled + local meaning fixed]
    NOT C2 whole-transcript (W3: register collapses 80%->54%, 8 lazy verbatim copies — dealbreaker).
  - + name-set diff BACKSTOP (deterministic flag of base-name dropped from refine).
    NOT phonetic post-check (W4: recall 0.40 on semantic mangle, useless + risk over-restore).

Stack (production-identical): Ollama qwen3.5:35b-a3b-mlx-bf16 @ temp0.3 think:false.
Input: corrected_spoken.json (48). Baseline: current_written.json. GT: W1-catalog.json.
"""
import json
import os
import re
import sys
import time
import urllib.request

BACKEND = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
sys.path.insert(0, BACKEND)
import phonetic_correction as pc  # noqa: E402

OLLAMA = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:35b-a3b-mlx-bf16"
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)

SPOKEN = json.load(open("/tmp/lq-written/corrected_spoken.json", encoding="utf-8"))
N = len(SPOKEN)
CTX = 2  # ±2 cue window (W3: N=2 narrow, register-safe; N=4 starts lazy-copying)

# ---- W5 V2 base prompt (the winning pure-prompt rewrite) ----
W5_V2 = open("/tmp/lq-written/results/W5-final-prompt.txt", encoding="utf-8").read().strip()

# ---- additional gloss/guard lines (evidence-led adds beyond W5) ----
EMBED_GLOSS = (
    "\n\n⚠️ 補充賽馬位置術語（同上同等重要，唔可以照字面理解）：\n"
    "- 「埋邊／埋便」＝靠近內欄（內側），**唔係**「附近」「靠邊」「在哪裡」。\n"
    "- 「放頭／放」＝領放（跑最前帶頭），**唔係**「出閘」。\n"
    "- 「透出」＝自馬群中突圍透出，**唔係**「透視」。\n"
    "- 「做P／做P繩」＝領放定速（pace），**唔係**「織繩」。")

GARBLED_GUARD = (
    "\n\n⚠️ 亂碼／殘缺句保護：如果本句似係 ASR 亂碼或語意殘缺（出現你無法理解嘅字組合），"
    "**只做最低限度 register 轉換、照字面保留**，**唔准**用上下文／賽事知識去補完、自創或推測一個完整意思。"
    "寧願保留殘句，都唔好幻覺。")

# ---- W3 ±2 window instruction (USER turn carries 前/本/後) ----
WIN_INSTR = (
    "\n\n你會收到【前文】【本句】【後文】三部分。前文同後文淨係畀你理解上下文意思"
    "（例如判斷某個詞係馬名、衫色花紋定係距離／位置），**唔好改寫亦唔好輸出佢哋**。"
    "只可以改寫【本句】，輸出只係【本句】嘅書面語 JSON {\"action\":\"keep\",\"text\":\"...\"}，唔好包含前後文。")

W6_BASE_SYSP = W5_V2 + EMBED_GLOSS + GARBLED_GUARD + WIN_INSTR

POS_TERMS = ["尾二", "尾三", "尾四"]


def call(sysp, user):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": sysp},
                     {"role": "user", "content": user}],
        "stream": False, "think": False, "options": {"temperature": 0.3},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["message"]["content"]


def parse_keep(raw):
    raw = _THINK_RE.sub("", raw or "").strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw).get("text", raw)
        except Exception:
            return raw
    return raw


# ---- W4 P2 per-cue roster injection (SYSTEM append) ----
def per_cue_sysp(base_names, pos_terms_present):
    if not base_names and not pos_terms_present:
        return W6_BASE_SYSP
    extra = "\n\n【本句保護詞（轉換時必須逐字原樣保留，唔准當普通詞拆開、改寫或合併）】\n"
    if base_names:
        extra += "馬名／賽事名：" + "、".join(base_names) + "。\n"
    if pos_terms_present:
        extra += ("賽馬名次術語（名次標籤，原樣保留，唔好改成「第X匹」「最後X匹」）："
                  + "、".join(pos_terms_present)
                  + "（尾二=倒數第二、尾三=倒數第三、尾四=倒數第四）。\n")
    extra += "唔好輸出呢段提示，唔好將呢啲詞加入冇提及佢哋嘅句子。"
    return W6_BASE_SYSP + extra


def build_window_user(i, txt):
    before = [SPOKEN[k]["text"] for k in range(max(0, i - CTX), i)]
    after = [SPOKEN[k]["text"] for k in range(i + 1, min(N, i + CTX + 1))]
    parts = []
    if before:
        parts.append("【前文】\n" + "\n".join(before))
    parts.append("【本句】\n" + txt)
    if after:
        parts.append("【後文】\n" + "\n".join(after))
    return "\n\n".join(parts)


def pos_in(t):
    return [x for x in POS_TERMS if x in t]


def main():
    g = json.load(open("/tmp/lq-research/glossary.json", encoding="utf-8"))
    idx = pc.build_index([g], [])
    glossary_names = sorted(set(idx["meta"]))
    per_base_names = []
    for s in SPOKEN:
        t = s.get("text") or ""
        per_base_names.append([n for n in glossary_names if n in t])

    out = []
    times = []
    backstop_flags = []  # name-set diff: base had name, refine dropped it
    for i, s in enumerate(SPOKEN):
        txt = (s.get("text") or "").strip()
        if not txt:
            out.append({"idx": i, "written": txt, "sec": 0.0})
            continue
        bn = per_base_names[i]
        pt = pos_in(txt)
        sysp = per_cue_sysp(bn, pt)
        user = build_window_user(i, txt)
        t0 = time.time()
        w = parse_keep(call(sysp, user))
        dt = time.time() - t0
        times.append(dt)
        # name-set diff backstop (deterministic FLAG only; NOT phonetic restore)
        dropped = [nm for nm in bn if nm not in w]
        if dropped:
            backstop_flags.append({"idx": i, "dropped": dropped, "written": w})
        out.append({"idx": i, "written": w, "sec": round(dt, 2),
                    "injected_names": bn, "injected_pos": pt})
        print("[w6 {:2d}] {:.1f}s {} -> {}".format(i, dt, txt[:14], w[:30]),
              file=sys.stderr)

    meta = {
        "model": MODEL, "temp": 0.3, "think": False,
        "calls": len(times), "total_sec": round(sum(times), 1),
        "avg_sec": round(sum(times) / len(times), 2),
        "max_sec": round(max(times), 2),
        "ctx_window": CTX,
        "summary_call": False,
        "n_out": len(out),
        "backstop_flags": backstop_flags,
        "recipe": ("W5V2 prompt + 埋邊/放頭/透出/做P gloss + garbled guard + "
                   "W4 per-cue roster inj (SYSTEM) + W3 ±2 window (USER) + "
                   "name-set diff backstop (flag-only)"),
    }
    res = {"variant": "W6", "meta": meta, "segments": out}
    path = "/tmp/lq-written/protos/w6_combined_out.json"
    json.dump(res, open(path, "w"), ensure_ascii=False, indent=1)
    print("WROTE " + path, file=sys.stderr)
    print("calls={} total={:.1f}s avg={:.2f}s max={:.2f}s backstop_flags={}".format(
        meta["calls"], meta["total_sec"], meta["avg_sec"], meta["max_sec"],
        len(backstop_flags)), file=sys.stderr)


if __name__ == "__main__":
    main()
