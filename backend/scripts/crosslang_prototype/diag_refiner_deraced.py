#!/usr/bin/env python3
"""Validation-First (2026-06-04) — 書面語 refiner: 賽馬版 vs 中性 de-raced 版.

The 粵→書面 path uses output_lang_postprocess.formal_refine, whose fixed prompt
(zh_written_register_v6.json) was built for the V6 賽馬 pipeline — racing preamble,
"賽馬術語" lock, and 3 racing examples — so NON-racing content (毛記) comes out
racing-flavoured. This compares, on the SAME real 毛記 yue base segments + the
production Ollama model, the current racing refiner (A) vs a neutral de-raced
refiner (B), to confirm B removes the racing bias without hurting register/meaning.

Metrics: racing-term injection count (terms in output NOT in the yue source),
口語 marker residue /100 chars, no-op rate, length-ratio, name/number preservation.
NOT production code; reads persisted yue output only. Run:
  cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/diag_refiner_deraced.py [N]
"""
import json, re, sys, time

YUE_JSON = "/tmp/tr_039d53ee8d1c.json"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 130

from translation.ollama_engine import OllamaTranslationEngine
_eng = OllamaTranslationEngine({"engine": "qwen3.5-35b-a3b"})
def llm(system, user):
    return _eng._call_ollama(system, user, 0.3)

# A = current production racing refiner
import output_lang_postprocess as olp
RACING_SYS = olp.REFINER_SYSTEM

# B = neutral de-raced refiner (drops racing preamble/lock/examples; adds explicit
#     "don't inject domain-specific terms" rule + neutral conversational examples).
NEUTRAL_SYS = (
    "你係專業繁體中文新聞編輯。輸入係一句粵語口語字幕（人名、地名、數字、時間軸都已正確）。\n"
    "任務：淨係將呢句由【粵語口語 register】轉換成【現代正式繁體中文書面語 register】，貼近規範新聞書面語。唔好保留口語感，亦唔好過度文言或公文化。\n\n"
    "轉換規則：\n"
    "1. 粵語特徵字 → 書面語：嘅→的、係→是、咗→了、喺→在、唔→不、冇→沒有、俾/畀→給或被(按語境)、嘢→東西/事物、佢→他/她/它、哋→們、而家→現在、點解→為何、睇→看、嗰→那、呢→這、乜/乜嘢→什麼、邊個→哪位/哪個、幾多→多少、咁→這樣/如此。\n"
    "2. 句末語氣助詞（啦/㗎/㗎啩/囉/喎/呀/咩/喇/嘅）一律刪除，必要時改為規範語氣（了/吧/呢）。\n"
    "3. 用規範現代書面句式（如「表示」「指出」「進行」），但嚴禁過度文言虛詞（惟/縱/乃）同累贅公文腔（茲/予以/上述/該項/之事宜）。\n"
    "4. 保留生動四字詞同成語，唔好拆成冗長學術詞。\n"
    "5. 數字、時間保留阿拉伯數字原狀。\n"
    "6. 必須 byte-for-byte 保留唔變：人名、地名、英文詞。\n"
    "7. 嚴禁將通用詞按主觀猜想改成原文冇嘅特定領域術語（例如賽馬／體育／財經術語）；忠實保留原文題材，唔好加戲。\n"
    "8. 長度 0.8–1.3× 原文字數。唔加外部資訊、唔加原文冇嘅句首連接詞。\n\n"
    '輸出：純 JSON object，無 markdown fence。只輸出：{"action": "keep", "text": "<書面語校對後文字>"}\n\n'
    '例子 1：輸入「佢琴日話想轉工，但係而家又話唔轉住。」→ 輸出 {"action": "keep", "text": "他昨日表示想轉工，但現在又說暫不轉換。"}\n'
    '例子 2：輸入「呢樣嘢好複雜，我哋要諗清楚先做。」→ 輸出 {"action": "keep", "text": "這件事相當複雜，我們要想清楚才做。"}\n'
    '例子 3：輸入「佢冇講原因，淨係話聽日返嚟。」→ 輸出 {"action": "keep", "text": "他沒有說明原因，只表示明日回來。"}'
)

_MARKERS = set("嘅係咗喺唔冇嗰呢㗎喎囉啦咩喇佢哋嘢乜嚟畀俾睇咁啲")
# racing-specific vocabulary that should NEVER appear for non-racing content
_RACING = ["騎師", "練馬師", "馬匹", "馬房", "馬會", "出閘", "內欄", "讓磅", "策騎", "賽駒",
           "頭馬", "沙田", "跑馬地", "打吡", "讓賽", "賽道", "跑道", "閘", "賽事", "場次",
           "落飛", "馬經", "馬主", "騎手", "賽駒"]
def mrate(t): return round(sum(1 for c in (t or "") if c in _MARKERS) / max(1, len(t)) * 100, 2)
def racing_hits(out, src):
    # count racing terms present in OUTPUT but absent from the yue SOURCE (= injected)
    return sum(out.count(w) for w in _RACING if w not in src and w in out)

def parse(raw):
    raw = (raw or "").strip()
    raw = re.sub(r"^```[a-z]*\n?|```$", "", raw).strip()
    if raw.startswith("{"):
        try: return json.loads(raw).get("text", raw)
        except Exception: pass
    return raw.splitlines()[0] if raw else ""

yue = [(s.get("yue_text") or "").strip() for s in json.load(open(YUE_JSON))["translations"][:N]]
yue = [t for t in yue if t]
print(f"[load] {len(yue)} yue segs", flush=True)

def run(name, sysp):
    outs, noop = [], 0
    for i, src in enumerate(yue):
        o = parse(llm(sysp, src)) or src
        outs.append(o)
        if o == src and mrate(src) > 0: noop += 1
        if (i + 1) % 25 == 0: print(f"  [{name}] {i+1}/{len(yue)}", flush=True)
    inj = sum(racing_hits(o, s) for o, s in zip(outs, yue))
    inj_segs = sum(1 for o, s in zip(outs, yue) if racing_hits(o, s) > 0)
    full = "".join(outs)
    ratios = sorted(len(o) / max(1, len(s)) for o, s in zip(outs, yue))
    return {"name": name, "outs": outs, "racing_injected_terms": inj, "racing_injected_segs": inj_segs,
            "marker_per_100": mrate(full), "noop_pct": round(noop / max(1, len(yue)) * 100, 1),
            "len_ratio_median": round(ratios[len(ratios)//2], 2)}

t0 = time.time()
A = run("A_racing", RACING_SYS)
B = run("B_neutral", NEUTRAL_SYS)
print(f"\n[done {time.time()-t0:.0f}s]")

print("\n" + "=" * 70)
print("REFINER 賽馬版(A) vs 中性 de-raced(B) — 毛記 (non-racing) 內容")
print("=" * 70)
for r in (A, B):
    print(f"\n{r['name']}: racing-terms injected = {r['racing_injected_terms']} "
          f"(in {r['racing_injected_segs']} segs) | 口語marker/100 = {r['marker_per_100']} "
          f"| noop {r['noop_pct']}% | len-median {r['len_ratio_median']}x")
print(f"\n► racing 味去走？  A 注入 {A['racing_injected_segs']} 段 → B 注入 {B['racing_injected_segs']} 段")
print("\n── 樣本（yue → A賽馬版 → B中性版），列出 A 注入馬經詞嘅段 ──")
shown = 0
for i, s in enumerate(yue):
    if racing_hits(A["outs"][i], s) > 0 and shown < 12:
        print(f"  口語: {s}")
        print(f"   A : {A['outs'][i]}")
        print(f"   B : {B['outs'][i]}")
        shown += 1
if shown == 0:
    for i in range(min(8, len(yue))):
        print(f"  口語: {yue[i]}")
        print(f"   A : {A['outs'][i]}")
        print(f"   B : {B['outs'][i]}")

json.dump({"A": A, "B": B, "yue": yue}, open("/tmp/diag_refiner_deraced.json", "w"), ensure_ascii=False, indent=2)
print("\nfull JSON → /tmp/diag_refiner_deraced.json")
