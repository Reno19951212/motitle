"""Validation-First — what can Whisper Large v3 actually output per source→target? (2026-06-01)

Tests the 3 user-supplied real broadcast clips (first ~90s each) through the
PRODUCTION model mlx-whisper large-v3:
  - transcribe in the native language (source-language transcript)
  - translate task (Whisper translate → English only)
  - one cross-language probe: Cantonese audio forced language='ja' (does Whisper
    produce Japanese, or garbage? — tests the user's "Whisper does cross-language" belief)

Prints outputs + char counts; saves /tmp/diag_whisper_output_langs.json.
Run: cd backend && PYTHONPATH=. python scripts/diag_whisper_output_langs.py
"""
import json
import subprocess
import time

import mlx_whisper

REPO = "mlx-community/whisper-large-v3-mlx"
DL = "/Users/renocheung/Downloads"
VIDS = [
    ("gamehub_粵語", f"{DL}/gamehub-（中文語音）.mp4", "zh"),
    ("警察會操_粵語", f"{DL}/香港警察結業會操（中文語音）.mp4", "zh"),
    ("HarryKane_英語", f"{DL}/Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4", "en"),
]
CLIP_SEC = 90


def _clip(src, out):
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-t", str(CLIP_SEC), "-ar", "16000", "-ac", "1", out],
        capture_output=True,
    )


def _run(wav, language, task):
    t0 = time.time()
    kwargs = {"path_or_hf_repo": REPO, "task": task}
    if language is not None:
        kwargs["language"] = language
    r = mlx_whisper.transcribe(wav, **kwargs)
    return (r.get("text", "") or "").strip(), round(time.time() - t0, 1)


def main():
    out = {}
    for name, src, native in VIDS:
        wav = f"/tmp/wclip_{name}.wav"
        _clip(src, wav)
        print(f"\n{'='*70}\n## {name}  (native={native})\n{'='*70}", flush=True)

        tr, t1 = _run(wav, native, "transcribe")
        print(f"[transcribe {native}]  ({t1}s, {len(tr)} chars)\n  {tr[:360]}", flush=True)

        en, t2 = _run(wav, native, "translate")
        print(f"[translate →en]  ({t2}s, {len(en)} chars)\n  {en[:360]}", flush=True)

        rec = {"native": native, "transcribe": tr, "translate_en": en, "secs": [t1, t2]}

        # cross-language probe only on a Cantonese clip
        if native == "zh" and name.startswith("gamehub"):
            ja, t3 = _run(wav, "ja", "transcribe")
            print(f"[transcribe ja on 粵語 audio — cross-lang probe]  ({t3}s, {len(ja)} chars)\n  {ja[:360]}", flush=True)
            rec["forced_ja_transcribe"] = ja
        out[name] = rec

    json.dump(out, open("/tmp/diag_whisper_output_langs.json", "w"), ensure_ascii=False, indent=2)
    print("\n# wrote /tmp/diag_whisper_output_langs.json")


if __name__ == "__main__":
    main()
