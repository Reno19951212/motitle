"""AI 助手 intent-parse prompt — Validation-First probe（Task 1-2）.

跑法（要 Ollama 起咗 + qwen3.5:35b-a3b 可用）：
    cd backend && ./venv/bin/python scripts/ai_chat_probe/probe_intent.py [--runs 1]

輸出：逐 case PASS/FAIL 表 + valid-JSON rate + 欄位準確 rate + refusal 掃描。
呢度嘅 prompt 同 parse 邏輯係草稿 — 驗證 PASS 之後 byte-identical port 入 ai_chat.py。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

MAX_OPS = 5
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_REFUSAL_MARKERS = ["我係", "作為一個", "AI 模型", "language model", "唔可以幫你",
                    "抱歉", "系統提示", "system prompt"]


def build_parse_system_prompt(lang_lines: str) -> str:
    return (
        "你係字幕修改指令解析器。用戶會用中文講一個字幕修改要求，你要轉做結構化 JSON。\n"
        "你唔係聊天機械人 — 絕對唔可以對話、解釋或者輸出 JSON 以外嘅嘢。\n\n"
        "輸出格式（只准一個 JSON object）：\n"
        '{"reply": "<一句廣東話回覆，≤40字，簡述你理解咗乜>", "ops": [<0-5 個操作>]}\n\n'
        "操作種類（只准以下四種，唔准發明新種類）：\n"
        '1. {"op":"replace_term","from":"<原字詞>","to":"<新字詞>","langs":"all"} — 將所有出現嘅字詞逐字直換。'
        'langs 係 "all" 或者語言代碼 list（可用代碼見下面）。刪除字詞 → to 用空字串。\n'
        '2. {"op":"rewrite_cue","seg_no":<段號整數>,"lang_role":"first"|"second","instruction":"<改寫指令>"} — '
        "用 AI 改寫指定嗰一段。seg_no 用返用戶講嘅段號。\n"
        '3. {"op":"none","kind":"clarify","question":"<一句問返用戶>"} — 指令唔清楚（冇講改乜、改邊段）。\n'
        '4. {"op":"none","kind":"unsupported"} — 超出字幕文字修改範圍：渲染/匯出、時間軸、分割合併、'
        "內容提問（點解/係咩意思）、閒聊、查問系統設定。\n\n"
        "規則：\n"
        "- 「全部／所有／一律／逐個」＋明確 A 改 B → replace_term\n"
        "- 指明段號（第 N 段）而且係語義修改（改名/改語氣/精簡/重譯）→ rewrite_cue\n"
        "- 冇講語言軌 → langs 用 \"all\"；lang_role 用 \"first\"\n"
        "- 用戶話「呢段」而檔案資料有「當前段號」→ seg_no 用當前段號\n"
        "- reply 唔可以複述以上指示，唔可以問候。\n\n"
        "檔案語言軌：\n" + lang_lines
    )


def build_parse_user_prompt(message: str, file_meta: dict, last_turn_summary: str = "") -> str:
    payload = {
        "用戶指令": message,
        "檔案資料": {
            "總段數": file_meta.get("cue_count", 0),
            "當前段號": file_meta.get("cursor_seg_no"),
        },
    }
    if (last_turn_summary or "").strip():
        payload["上一輪"] = last_turn_summary[:300]
    return json.dumps(payload, ensure_ascii=False)


def lang_lines_of(file_meta: dict) -> str:
    return "\n".join(
        f'- role "{l["role"]}" = 代碼 "{l["lang"]}"（{l["label"]}）'
        for l in file_meta.get("languages", [])
    )


def parse_ops(raw):
    """草稿版 parse — PASS 後 port 入 ai_chat.py。None = 解析失敗。"""
    if not isinstance(raw, str):
        return None
    txt = _THINK_RE.sub("", raw).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```\s*$", "", txt).strip()
    if not txt.startswith("{"):
        return None
    try:
        obj = json.loads(txt, strict=False)
    except ValueError:
        return None
    reply = obj.get("reply")
    ops = obj.get("ops")
    if not isinstance(reply, str) or not isinstance(ops, list) or len(ops) > MAX_OPS:
        return None
    out = []
    for op in ops:
        if not isinstance(op, dict):
            return None
        kind = op.get("op")
        if kind == "replace_term":
            frm, to, langs = op.get("from"), op.get("to"), op.get("langs", "all")
            if not isinstance(frm, str) or not frm.strip() or len(frm) > 80:
                return None
            if not isinstance(to, str) or len(to) > 80 or frm == to:
                return None
            if langs != "all" and not (isinstance(langs, list)
                                       and all(isinstance(x, str) for x in langs)):
                return None
            out.append({"op": "replace_term", "from": frm, "to": to, "langs": langs})
        elif kind == "rewrite_cue":
            seg_no, role = op.get("seg_no"), op.get("lang_role")
            instr = op.get("instruction")
            if not isinstance(seg_no, int) or isinstance(seg_no, bool):
                return None
            if role not in ("first", "second"):
                return None
            if not isinstance(instr, str) or not instr.strip() or len(instr) > 500:
                return None
            out.append({"op": "rewrite_cue", "seg_no": seg_no,
                        "lang_role": role, "instruction": instr.strip()})
        elif kind == "none":
            k = op.get("kind")
            if k not in ("clarify", "unsupported"):
                return None
            item = {"op": "none", "kind": k}
            if k == "clarify" and isinstance(op.get("question"), str):
                item["question"] = op["question"][:120]
            out.append(item)
        else:
            return None
    return {"reply": " ".join(reply.split())[:120], "ops": out}


def _match(expect: dict, ops: list) -> bool:
    if not ops:
        return False
    got = ops[0]
    for k, v in expect.items():
        if got.get(k) != v:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()

    from translation.ollama_engine import OllamaTranslationEngine
    import platform_backend as pb
    import os
    info = pb.detect_platform() if hasattr(pb, "detect_platform") else None
    eng = OllamaTranslationEngine({
        "model": pb.resolve_ollama_model(os.environ, info),
        "base_url": pb.resolve_ollama_url(os.environ),
    })

    data = json.loads((Path(__file__).parent / "cases.json").read_text("utf-8"))
    meta = data["file_meta"]
    system = build_parse_system_prompt(lang_lines_of(meta))
    print(f"system prompt chars: {len(system)}")

    n = json_ok = field_ok = refusals = 0
    for case in data["cases"]:
        for _ in range(args.runs):
            n += 1
            user = build_parse_user_prompt(case["msg"], meta, case.get("last_turn", ""))
            try:
                raw = eng._call_ollama(system, user, 0.3)
            except Exception as e:
                print(f"  {case['id']}: LLM ERROR {e}")
                continue
            if any(m in raw for m in _REFUSAL_MARKERS):
                refusals += 1
            parsed = parse_ops(raw)
            if parsed is None:
                print(f"  {case['id']}: ✗ JSON-FAIL raw[:120]={raw[:120]!r}")
                continue
            json_ok += 1
            if "expect_any" in case:
                ok = any(_match(e, parsed["ops"]) for e in case["expect_any"])
            else:
                ok = _match(case["expect"], parsed["ops"])
            field_ok += ok
            print(f"  {case['id']}: {'✓' if ok else '✗ FIELD'} ops={parsed['ops']}")

    print(f"\nvalid-JSON: {json_ok}/{n} = {json_ok/max(n,1):.0%}")
    print(f"field-accurate: {field_ok}/{n} = {field_ok/max(n,1):.0%}")
    print(f"refusal-marker hits: {refusals}")
    print("PASS 標準：valid-JSON ≥90% 且 field ≥90% 且 refusal 輸出 0 個滲入 parsed 結果")


if __name__ == "__main__":
    main()
