"""Validation-First — FULL-clip cleaned Whisper Large v3 quality per output language (2026-06-01).

Runs the 3 user clips IN FULL through mlx-whisper large-v3 with the production
anti-hallucination setting (condition_on_previous_text=False), applies s2hk to zh
output, and quantifies quality per target so the user can judge before deciding
engine-routing vs pure-Whisper.

Outputs full text to /tmp/wfull_<name>_<task>.txt + a metrics summary.
Run: cd backend && PYTHONPATH=. python scripts/diag_whisper_full_quality.py
"""
import json
import re
import subprocess
import time

import mlx_whisper
from asr.cn_convert import _get_converter

REPO = "mlx-community/whisper-large-v3-mlx"
DL = "/Users/renocheung/Downloads"
VIDS = [
    ("gamehub_粵", f"{DL}/gamehub-（中文語音）.mp4", "zh", True),     # +ja probe
    ("警察_粵", f"{DL}/香港警察結業會操（中文語音）.mp4", "zh", False),
    ("HarryKane_英", f"{DL}/Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4", "en", False),
]
CANTO_MARKERS = list("嘅喺咗係唔佢啦㗎喎嚟畀") + ["哋", "嘢", "冇", "睇"]


def _wav(src, out):
    subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", out], capture_output=True)


def _run(wav, language, task):
    t0 = time.time()
    kw = {"path_or_hf_repo": REPO, "task": task, "condition_on_previous_text": False}
    if language is not None:
        kw["language"] = language
    r = mlx_whisper.transcribe(wav, **kw)
    return (r.get("text", "") or "").strip(), round(time.time() - t0, 1)


def _hallucination_loop(text):
    # crude: does any 10-char window repeat >=5 times total?
    worst = 0
    for i in range(0, max(0, len(text) - 10), 7):
        w = text[i:i + 10]
        if w.strip():
            worst = max(worst, text.count(w))
    return worst


def _canto_rate(text):
    if not text:
        return 0.0
    return round(sum(text.count(m) for m in CANTO_MARKERS) / len(text) * 100, 2)


def main():
    conv = _get_converter("s2hk")
    summary = {}
    for name, src, native, ja_probe in VIDS:
        wav = f"/tmp/wfull_{name}.wav"
        _wav(src, wav)
        print(f"\n{'='*72}\n## {name} (native={native})\n{'='*72}", flush=True)

        tr, t1 = _run(wav, native, "transcribe")
        if native == "zh":
            tr = conv.convert(tr)  # s2hk
        loop_tr = _hallucination_loop(tr)
        open(f"/tmp/wfull_{name}_transcribe.txt", "w").write(tr)
        print(f"[transcribe {native}+s2hk] {t1}s, {len(tr)}字, 口語marker/100={_canto_rate(tr)}, loop={loop_tr}")
        print(f"  頭: {tr[:200]}\n  尾: {tr[-160:]}", flush=True)

        en, t2 = _run(wav, native, "translate")
        loop_en = _hallucination_loop(en)
        open(f"/tmp/wfull_{name}_translate_en.txt", "w").write(en)
        print(f"[translate→en] {t2}s, {len(en)}字, loop={loop_en}")
        print(f"  頭: {en[:200]}\n  尾: {en[-160:]}", flush=True)

        rec = {"transcribe_chars": len(tr), "transcribe_canto_rate": _canto_rate(tr),
               "transcribe_loop": loop_tr, "translate_chars": len(en), "translate_loop": loop_en}

        if ja_probe:
            ja, t3 = _run(wav, "ja", "transcribe")
            loop_ja = _hallucination_loop(ja)
            open(f"/tmp/wfull_{name}_ja.txt", "w").write(ja)
            print(f"[force-ja] {t3}s, {len(ja)}字, loop={loop_ja}")
            print(f"  頭: {ja[:200]}\n  尾: {ja[-160:]}", flush=True)
            rec["ja_chars"] = len(ja); rec["ja_loop"] = loop_ja
        summary[name] = rec

    json.dump(summary, open("/tmp/wfull_summary.json", "w"), ensure_ascii=False, indent=2)
    print(f"\n# metrics: /tmp/wfull_summary.json | full texts: /tmp/wfull_*.txt")


if __name__ == "__main__":
    main()
