"""Entity recall for A3 ensemble selector.

Key entries map English aliases (lowercase) to a list of ZH variants.
Build runtime index by extending SEED with active glossary entries.
"""
import re
from typing import Dict, List, Set


SEED_NAME_INDEX: Dict[str, List[str]] = {
    "real madrid":     ["皇家馬德里", "皇馬", "馬德里"],
    "xabi alonso":     ["沙比阿朗素", "阿朗素"],
    "alonso":          ["阿朗素"],
    "ancelotti":       ["安察洛堤"],
    "carlo ancelotti": ["安察洛堤"],
    "vinicius":        ["雲尼素斯"],
    "bellingham":      ["貝靈鹹", "貝靈咸"],
    "rudiger":         ["盧迪加", "呂迪格"],
    "alaba":           ["阿拉巴"],
    "david alaba":     ["阿拉巴", "大衛·阿拉巴"],
    "antonio rudiger": ["盧迪加", "呂迪格"],
    "militao":         ["米利淘"],
    "carreras":        ["卡列拉斯"],
    "schlotterbeck":   ["史洛達碧"],
    "nico schlotterbeck": ["史洛達碧"],
    "dortmund":        ["多蒙特"],
    "borussia dortmund": ["多蒙特"],
    "hausson":         ["豪森"],
    "dean hausson":    ["豪森", "迪恩·豪森"],
    "asensio":         ["阿森西奧"],
    "raul asensio":    ["阿森西奧", "勞爾·阿森西奧"],
    "valverde":        ["華華迪"],
    "wharton":         ["華頓"],
    "adam wharton":    ["華頓", "亞當·華頓"],
    "amora":           ["阿莫拉"],
    "mohamed amora":   ["阿莫拉", "穆罕默德·阿莫拉"],
    "wolfsburg":       ["沃爾夫斯堡", "狼堡"],
    "crystal palace":  ["水晶宮"],
    "como":            ["科莫"],
    "nico paz":        ["帕斯", "尼科爾·帕斯"],
    "paz":             ["帕斯"],
    "brahim":          ["布拉希姆"],
    "rodrygo":         ["羅德里哥"],
    "mbappe":          ["姆巴比"],
    "modric":          ["莫迪歷"],
    "kroos":           ["告魯斯", "克羅斯"],
    "kane":            ["哈利·堅尼", "堅尼"],
    "harry kane":      ["哈利·堅尼", "堅尼"],
}


def find_en_entities(en_text: str, index: Dict[str, List[str]]) -> Set[str]:
    """Return set of normalized name keys present in en_text (word-boundary match)."""
    txt = (en_text or "").lower()
    found = set()
    for key in index:
        if re.search(r'\b' + re.escape(key) + r'\b', txt):
            found.add(key)
    return found


def check_zh_has_name(zh_text: str, key: str, index: Dict[str, List[str]]) -> bool:
    """True if any ZH variant for key appears in zh_text."""
    for v in index.get(key, []):
        if v in zh_text:
            return True
    return False


def build_runtime_index(glossary_entries: List[dict]) -> Dict[str, List[str]]:
    """Extend SEED_NAME_INDEX with glossary terms.

    Glossary entry shape: {en, zh, id} (or legacy {term_en, term_zh}).
    Glossary entries take precedence (extend variant list for same key; new keys created).
    """
    idx = {k: list(v) for k, v in SEED_NAME_INDEX.items()}
    for e in glossary_entries:
        en = (e.get("en") or e.get("term_en") or "").strip().lower()
        zh = (e.get("zh") or e.get("term_zh") or "").strip()
        if en and zh:
            if en not in idx:
                idx[en] = []
            if zh not in idx[en]:
                idx[en].append(zh)
    return idx
