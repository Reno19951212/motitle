#!/usr/bin/env python3.11
"""qwen3-asr tuning runner — runs mlx_qwen3_asr.transcribe() with a named variant config.

Usage:
    venv_qwen/bin/python qwen3_tune_runner.py <variant_name> <audio_path> <output_json_path>

Variants:
    baseline    — current production: language=Cantonese, context=""
    A_context   — language=Cantonese, rich Cantonese horse-racing context (entity names)
    B_chinese   — language=Chinese (instead of Cantonese), same context as A
    C_maxtokens — language=Cantonese, same context as A, max_new_tokens=512

Audio: any format mlx_qwen3_asr accepts (mp4, wav, mp3, …)

Output JSON shape:
    {
      "variant": "...",
      "config": {...},
      "language": "...",
      "full_text": "...",
      "chunks": [{"start": float, "end": float, "text": str}, ...],
      "runtime_sec": float,
      "error": null | "..."
    }
"""
import json
import sys
import time


# 賽馬廣播 file 嘅實體名 + 廣東話/香港賽馬常用詞 — 用 space 分隔短詞 (per Qwen3-ASR docs)
RACING_CONTEXT_ENTITIES = (
    # 人名（騎師、馬主、教練）
    "袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 "
    # 馬名（呢條片提到）
    "美狼王 HIGHLAND BLINK 幸運風采 "
    # 場館 / 賽事
    "沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 "
    # 賽馬術語（廣播常用）
    "騎師 試騎 推騎 試閘 抽籤 排位 大熱門 頭馬 客艙 馬房 馬仔 香檳 打吡 "
    # 香港地理
    "香港 沙田 悉尼"
)


VARIANTS = {
    "baseline": {
        "language": "Cantonese",
        "context": "",
    },
    "A_context": {
        "language": "Cantonese",
        "context": RACING_CONTEXT_ENTITIES,
    },
    "B_chinese": {
        "language": "Chinese",
        "context": RACING_CONTEXT_ENTITIES,
    },
    "C_maxtokens": {
        "language": "Cantonese",
        "context": RACING_CONTEXT_ENTITIES,
        "max_new_tokens": 512,
    },
    "D_B_s2hk": {
        "language": "Chinese",
        "context": RACING_CONTEXT_ENTITIES,
        "_post_s2hk": True,
    },
}


def main():
    if len(sys.argv) != 4:
        sys.stderr.write(__doc__)
        sys.exit(2)

    variant_name, audio_path, output_path = sys.argv[1], sys.argv[2], sys.argv[3]

    if variant_name not in VARIANTS:
        sys.stderr.write(f"Unknown variant {variant_name!r}. Valid: {list(VARIANTS)}\n")
        sys.exit(2)

    cfg = dict(VARIANTS[variant_name])
    post_s2hk = cfg.pop("_post_s2hk", False)

    try:
        import mlx_qwen3_asr
    except ImportError:
        sys.stderr.write("mlx_qwen3_asr not available in this venv\n")
        sys.exit(2)

    t0 = time.time()
    err = None
    out = {
        "variant": variant_name,
        "config": cfg,
        "language": None,
        "full_text": "",
        "chunks": [],
        "runtime_sec": 0.0,
        "error": None,
    }

    try:
        result = mlx_qwen3_asr.transcribe(
            audio_path,
            model="Qwen/Qwen3-ASR-1.7B",
            return_timestamps=True,
            return_chunks=True,
            verbose=False,
            **cfg,
        )
        out["language"] = result.language
        out["full_text"] = result.text or ""
        if hasattr(result, "chunks") and result.chunks:
            for c in result.chunks:
                if isinstance(c, dict):
                    out["chunks"].append({
                        "start": c.get("start"),
                        "end": c.get("end"),
                        "text": c.get("text", ""),
                    })
                else:
                    out["chunks"].append({
                        "start": getattr(c, "start", None),
                        "end": getattr(c, "end", None),
                        "text": getattr(c, "text", ""),
                    })

        if post_s2hk and out["chunks"]:
            import opencc
            cc = opencc.OpenCC("s2hk")
            out["full_text"] = cc.convert(out["full_text"])
            out["chunks"] = [
                {**ch, "text": cc.convert(ch.get("text", ""))}
                for ch in out["chunks"]
            ]
            out["config"]["_post_s2hk"] = True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        out["error"] = err

    out["runtime_sec"] = round(time.time() - t0, 2)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    sys.stderr.write(f"variant={variant_name}  runtime={out['runtime_sec']}s  chunks={len(out['chunks'])}  error={err}\n")


if __name__ == "__main__":
    main()
