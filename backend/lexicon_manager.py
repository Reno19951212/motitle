"""系統行話表（phonetic lexicon）原子讀寫 — pure-ish manager。

config/phonetic_lexicons/<style>_terms.json 嘅 CRUD。dual-shape 保留：
term 可以係 bare string 或 {"term","variants"} object。variants 非空 → object；
空 → bare string（精簡）。原子寫 + per-style lock。管理員專屬（route 層 gate）。
Python 3.9 / immutable。
"""
import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from phonetic_correction import LEXICON_DIR  # 同一個 config 目錄

_STYLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LOCKS: Dict[str, threading.Lock] = {}
_MASTER = threading.Lock()


def _lock(style: str) -> threading.Lock:
    with _MASTER:
        if style not in _LOCKS:
            _LOCKS[style] = threading.Lock()
        return _LOCKS[style]


def _path(style: str) -> Optional[Path]:
    if not style or not _STYLE_RE.match(style):
        return None
    return LEXICON_DIR / "{}_terms.json".format(style)


def _read_raw(style: str) -> Optional[dict]:
    p = _path(style)
    if p is None or not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_terms(raw_terms) -> List[dict]:
    out: List[dict] = []
    for item in raw_terms or []:
        if isinstance(item, str) and item.strip():
            out.append({"term": item.strip(), "variants": []})
        elif isinstance(item, dict):
            term = (item.get("term") or "").strip()
            if not term:
                continue
            variants = [str(v).strip() for v in (item.get("variants") or [])
                        if v and str(v).strip()]
            out.append({"term": term, "variants": variants})
    return out


def get_lexicon(style: str) -> Optional[dict]:
    """正規化 view {"style", "terms":[{"term","variants"}]}；壞 style/冇檔 → None。"""
    data = _read_raw(style)
    if data is None:
        return None
    return {"style": style, "terms": _normalize_terms(data.get("terms"))}


def _write(style: str, data: dict) -> None:
    p = _path(style)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _to_raw_terms(terms: List[dict]) -> List:
    """正規化 terms → 磁碟 shape：variants 非空 → object，空 → bare string。"""
    raw: List = []
    for t in terms:
        term = (t.get("term") or "").strip()
        if not term:
            continue
        variants = [str(v).strip() for v in (t.get("variants") or []) if v and str(v).strip()]
        raw.append({"term": term, "variants": variants} if variants else term)
    return raw


def set_lexicon(style: str, terms: List[dict]) -> Optional[dict]:
    """管理員 bulk 覆寫 terms。回正規化 view；壞 style/冇檔 → None。"""
    with _lock(style):
        data = _read_raw(style)
        if data is None:
            return None
        data = dict(data)
        data["terms"] = _to_raw_terms(_normalize_terms(terms))
        _write(style, data)
        return {"style": style, "terms": _normalize_terms(data["terms"])}


def add_term_variant(style: str, term: str, variant: str) -> Optional[dict]:
    """為 term 追加一個 variant（dedupe）；term 唔存在就新增。回正規化 view。"""
    term = (term or "").strip()
    variant = (variant or "").strip()
    if not term or not variant:
        return get_lexicon(style)
    with _lock(style):
        data = _read_raw(style)
        if data is None:
            return None
        terms = _normalize_terms(data.get("terms"))
        found = next((t for t in terms if t["term"] == term), None)
        if found is None:
            terms.append({"term": term, "variants": [variant]})
        elif variant not in found["variants"]:
            found["variants"].append(variant)
        data = dict(data)
        data["terms"] = _to_raw_terms(terms)
        _write(style, data)
        return {"style": style, "terms": _normalize_terms(data["terms"])}
