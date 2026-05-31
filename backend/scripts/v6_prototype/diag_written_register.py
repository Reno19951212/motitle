"""Validation-First prototype — V6 Cantonese 口語 → FORMAL 書面語 register conversion.

Feeds REAL persisted colloquial-Cantonese refiner output (file de603727d3f8,
342 segs @ ~11.7 markers/100 chars) through TWO prompt variants on IDENTICAL
input, against the production Ollama model qwen3.5:35b-a3b-mlx-bf16:

  FOCUSED  = register-only rewrite  (== the recommended two-pass chain's 2nd refiner)
  COMBINED = cleanup + register     (== single-pass style, dual mandate)

Metrics (per CLAUDE.md Validation-First + the research workflow's P1-P5):
  - residual_colloquial_marker_rate per 100 chars  (baseline ~11.7; target <= 2.0)
  - name/number/ASCII byte-preservation rate        (target = 100%)
  - silent no-op rate (output == input)             (target < 15%)
  - length ratio out/in distribution                (median ~0.8-1.3x; flag >3.5x)
  - over-cap (>24 chars/line, the V6 clause_split cap)

NOT production code. Reads persisted data only — never mutates the live pipeline.
Run from backend/ with PYTHONPATH=. : python scripts/v6_prototype/diag_written_register.py [N]
"""
import json
import glob
import re
import sys
import urllib.request

FID = "de603727d3f8"
MODEL = "qwen3.5:35b-a3b-mlx-bf16"
OLLAMA = "http://localhost:11434/api/chat"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120

MARKERS = ["嘅", "喺", "唔", "係", "咗", "啦", "㗎", "嚟", "畀", "俾", "嘢",
           "佢", "哋", "而家", "點解", "乜", "嗰", "呢個", "冇", "睇", "咩", "囉", "喎"]
# Formal/bureaucratic over-formalization smell words (for P5 manual gate)
BUREAU = ["狀況", "事務", "予以", "進行了", "之相關", "茲", "上述", "該項", "之事宜"]

# Proper nouns from the Cantonese pipeline's qwen3_context — MUST survive byte-for-byte.
NAMES = ("袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 美狼王 "
         "幸運風采 沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 "
         "沙田 悉尼 香港 飛輪八 內欄").split()

FOCUSED_SYS = """你係專業繁體中文編輯。輸入係一句已經校對好嘅粵語廣播字幕（人名、地名、術語、數字都已正確）。
任務：淨係將呢句由【粵語口語 register】轉換成【正式繁體中文書面語 register】，貼近正規新聞/公文書面語，唔好保留口語感。

轉換規則：
- 粵語字→書面語：嘅→的、係→是、咗→了、喺→在、唔→不、冇→沒有、俾/畀→給或被(按語境)、嘢→東西/事物、佢→他/她/它、哋→們、而家→現在、點解→為何、睇→看、嗰→那、呢→這、乜/乜嘢→什麼、邊個→哪位/哪個、幾多→多少、咁→這樣/如此。
- 句末語氣助詞（啦/㗎/囉/喎/呀/咩/喇/嘅）一律刪除，必要時改為「了」「呢」等規範語氣。
- 用規範書面句式（如「表示」「指出」「進行」「準備就緒」），但唔可以變成累贅公文腔。

必須 byte-for-byte 保留唔變：人名、地名、賽馬術語、英文詞、數字、時間、賽事名。
長度 0.8–1.3× 原文。唔加任何外部資訊、唔加原文冇嘅連接詞。
保留生動四字詞/成語（如「傷病纏身」「大刀闊斧」），唔好拆成冗長學術詞。

只輸出轉換後嘅書面語文字一行，唔好加引號、JSON、標籤或任何解釋。"""

COMBINED_SYS = """你係專業繁體中文廣播字幕編輯。輸入係一句粵語廣播字幕。
任務（一次過做晒）：(1) 校對 ASR 錯漏、保人名地名術語正確；(2) 將句子由【粵語口語 register】轉換成【正式繁體中文書面語 register】，貼近正規新聞/公文書面語。

轉換規則：嘅→的、係→是、咗→了、喺→在、唔→不、冇→沒有、俾/畀→給或被、嘢→東西/事物、佢→他/她/它、哋→們、而家→現在、點解→為何、睇→看、嗰→那、呢→這、乜→什麼、咁→這樣；句末語氣助詞（啦/㗎/囉/喎/呀/咩/喇）刪除。用規範書面句式。
必須 byte-for-byte 保留：人名、地名、賽馬術語、英文詞、數字、時間、賽事名。長度 0.8–1.3×。唔加外部資訊。保留生動四字詞/成語。
只輸出轉換後嘅書面語文字一行，唔好加引號、JSON、標籤或解釋。"""


def _reg_file():
    rp = (glob.glob("data/**/registry.json", recursive=True) or ["data/registry.json"])[0]
    d = json.load(open(rp))
    files = d if isinstance(d, list) else d.get("files", d)
    if isinstance(files, dict):
        files = list(files.values())
    return [x for x in files if x.get("id") == FID][0]


def _protected_tokens(text):
    """Tokens that MUST survive byte-for-byte: digits, ASCII runs >=3 chars
    (race names/brands like 'HIGHLAND BLINK'; excludes casual 'OK'/'yeah' which
    SHOULD be formalized), and curated proper nouns present in the text."""
    toks = {t.strip() for t in re.findall(r"[A-Za-z][A-Za-z' ]*[A-Za-z]", text) if len(t.strip()) >= 3}
    toks |= set(re.findall(r"\d+(?:[:.]\d+)*", text))
    toks |= {nm for nm in NAMES if nm in text}
    return {t for t in toks if t}


def _marker_count(text):
    return sum(text.count(m) for m in MARKERS)


def ollama(system, user):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_predict": 400},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    txt = (out.get("message", {}) or {}).get("content", "") or ""
    # strip any stray fences/labels
    txt = re.sub(r"^```.*?\n|```$", "", txt.strip())
    txt = re.sub(r'^\s*(?:譯文|書面語|輸出|Output)\s*[:：]\s*', "", txt.strip())
    return txt.strip().splitlines()[0].strip() if txt.strip() else ""


def overcap(texts, cap=24):
    n = 0
    for s in texts:
        for line in re.split(r"\\N|\n", s):
            if len(line.strip()) > cap:
                n += 1
                break
    return n


def run_arm(name, system, segs):
    outs, noop, name_fail = [], 0, 0
    for i, s in enumerate(segs):
        src = s["text"]
        try:
            out = ollama(system, src)
        except Exception as e:
            out = src
            print(f"  !! seg {i} err {e}", flush=True)
        if not out:
            out = src
        outs.append(out)
        if out == src and _marker_count(src) > 0:
            noop += 1
        prot = _protected_tokens(src)
        missing = [t for t in prot if t not in out]
        if missing:
            name_fail += 1
        if (i + 1) % 25 == 0:
            print(f"  [{name}] {i+1}/{len(segs)}", flush=True)
    in_txt = "".join(s["text"] for s in segs)
    out_txt = "".join(outs)
    in_chars = len(in_txt)
    out_chars = len(out_txt)
    ratios = [len(o) / max(1, len(s["text"])) for o, s in zip(outs, segs)]
    res = {
        "arm": name,
        "segs": len(segs),
        "residual_markers_per_100": round(_marker_count(out_txt) / max(1, out_chars) * 100, 2),
        "name_preservation_rate": round((len(segs) - name_fail) / max(1, len(segs)) * 100, 1),
        "silent_noop_rate": round(noop / max(1, len(segs)) * 100, 1),
        "len_ratio_median": round(sorted(ratios)[len(ratios) // 2], 2),
        "len_ratio_max": round(max(ratios), 2),
        "len_blowups_gt_3_5x": sum(1 for r in ratios if r > 3.5),
        "overcap_gt24": overcap(outs),
        "outs": outs,
    }
    return res


def main():
    f = _reg_file()
    tr = f.get("translations") or []
    segs = []
    for r in tr:
        t = (r.get("zh_text") or (r.get("by_lang", {}).get("zh", {}) or {}).get("text") or "").strip()
        if t:
            segs.append({"text": t, "start": r.get("start"), "end": r.get("end")})
    segs = segs[:N]
    in_txt = "".join(s["text"] for s in segs)
    base_markers = round(_marker_count(in_txt) / max(1, len(in_txt)) * 100, 2)
    base_overcap = overcap([s["text"] for s in segs])
    print(f"# file {FID}: {len(segs)} segs, {len(in_txt)} chars")
    print(f"# BASELINE 口語: residual_markers/100 = {base_markers} | over-cap>24 = {base_overcap}/{len(segs)}\n")

    focused = run_arm("FOCUSED(2-pass register-only)", FOCUSED_SYS, segs)
    combined = run_arm("COMBINED(1-pass dual-mandate)", COMBINED_SYS, segs)

    print("\n=== METRICS (baseline → arms) ===")
    print(f"{'metric':32} {'BASELINE':>10} {'FOCUSED':>10} {'COMBINED':>10}")
    rows = [
        ("residual_markers_per_100", base_markers, focused["residual_markers_per_100"], combined["residual_markers_per_100"]),
        ("name_preservation_rate%", 100.0, focused["name_preservation_rate"], combined["name_preservation_rate"]),
        ("silent_noop_rate%", "-", focused["silent_noop_rate"], combined["silent_noop_rate"]),
        ("len_ratio_median", 1.0, focused["len_ratio_median"], combined["len_ratio_median"]),
        ("len_blowups_>3.5x", 0, focused["len_blowups_gt_3_5x"], combined["len_blowups_gt_3_5x"]),
        (f"over-cap>24 (/{len(segs)})", base_overcap, focused["overcap_gt24"], combined["overcap_gt24"]),
    ]
    for r in rows:
        print(f"{r[0]:32} {str(r[1]):>10} {str(r[2]):>10} {str(r[3]):>10}")

    print("\n=== 15 SAMPLE conversions (口語 → FOCUSED → COMBINED) — manual register/formality check ===")
    for i in range(min(15, len(segs))):
        print(f"#{i} 口語: {segs[i]['text']}")
        print(f"   書(F): {focused['outs'][i]}")
        print(f"   書(C): {combined['outs'][i]}")

    json.dump({"baseline_markers": base_markers, "focused": {k: v for k, v in focused.items() if k != 'outs'},
               "combined": {k: v for k, v in combined.items() if k != 'outs'},
               "samples": [{"src": segs[i]["text"], "focused": focused["outs"][i], "combined": combined["outs"][i]}
                           for i in range(len(segs))]},
              open("/tmp/diag_written_register.json", "w"), ensure_ascii=False, indent=2)
    print("\n# wrote /tmp/diag_written_register.json")


if __name__ == "__main__":
    main()
