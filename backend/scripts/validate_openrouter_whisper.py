"""Validation-First Phase 0 — 實測 OpenRouter openai/whisper-large-v3 嘅 transcription
回應，確定有冇 segment / word timestamp，同記錄實際 JSON shape。

跑法（需要 key）：
    export OPENROUTER_API_KEY=sk-or-...
    python backend/scripts/validate_openrouter_whisper.py <audio_or_video>

結果人手抄入 docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md。

依賴 ffmpeg（提取/轉成 16k mono wav）— 與 production ASR 前處理對齊。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

MODEL = "openai/whisper-large-v3"
BASE = "https://openrouter.ai/api/v1"


def _to_wav(src: str) -> str:
    """Extract/convert to 16kHz mono wav via ffmpeg (matches production ASR input)."""
    out = tempfile.mktemp(suffix=".wav")
    cmd = ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", out]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def _post(payload: dict) -> dict:
    key = os.environ["OPENROUTER_API_KEY"]
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/audio/transcriptions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _probe(label: str, payload: dict) -> None:
    print(f"\n=== Probe {label} ===")
    t0 = time.time()
    try:
        out = _post(payload)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        print(f"  HTTPError {e.code}: {e.reason}\n  body: {detail[:600]}")
        return
    except (urllib.error.URLError, OSError) as e:
        print(f"  connection error: {e}")
        return
    dt = time.time() - t0

    keys = sorted(out.keys())
    has_segments = isinstance(out.get("segments"), list) and out["segments"]
    has_words = isinstance(out.get("words"), list) and out["words"]
    print(f"  latency_sec={dt:.1f}")
    print(f"  top_level_keys={keys}")
    print(f"  has_segment_timestamps={bool(has_segments)}")
    print(f"  has_word_timestamps={bool(has_words)}")
    if has_segments:
        print("  first_segment=", json.dumps(out["segments"][0], ensure_ascii=False))
    if has_words:
        print("  first_word=", json.dumps(out["words"][0], ensure_ascii=False))
    print("  text_preview=", (out.get("text") or "")[:200])


def main(src: str) -> None:
    if "OPENROUTER_API_KEY" not in os.environ:
        print("error: export OPENROUTER_API_KEY first")
        sys.exit(1)

    wav = _to_wav(src)
    try:
        b64 = base64.b64encode(open(wav, "rb").read()).decode("ascii")
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass

    base_payload = {
        "model": MODEL,
        "input_audio": {"data": b64, "format": "wav"},
        "language": "en",
    }

    # Probe A: ask for verbose_json + segment/word timestamp (OpenAI Whisper standard form)
    _probe("A (verbose_json + timestamp_granularities)", {
        **base_payload,
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment", "word"],
    })

    # Probe B: base payload only (fallback — see what default shape we get)
    _probe("B (base payload, no timestamp params)", base_payload)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python validate_openrouter_whisper.py <audio_or_video>")
        sys.exit(1)
    main(sys.argv[1])
