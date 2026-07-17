"""_write_output_lang_cue_text — 四庫寫入 helper 等價測試（Task 4）.

Run:
    cd backend && FLASK_SECRET_KEY=test-secret R5_AUTH_BYPASS=1 \
        ./venv/bin/python -m pytest tests/test_write_helper.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _entry():
    return {
        "id": "wh-1", "active_kind": "output_lang", "user_id": 1,
        "output_languages": ["zh", "en"],
        "translations": [{
            "idx": 0, "start": 0.0, "end": 2.0, "status": "approved",
            "by_lang": {"zh": {"text": "舊句", "status": "approved", "flags": []},
                        "en": {"text": "old", "status": "pending", "flags": []}},
            "zh_text": "舊句", "en_text": "old", "glossary_changes": [],
        }],
        "aligned_bilingual": [{"start": 0.0, "end": 2.0,
                               "by_lang": {"zh": "舊句", "en": "old"}}],
    }


def test_writes_three_stores_and_appends_change():
    import app as _app
    e = _entry()
    change = {"source": "AI 助手", "before": "舊句", "after": "新句",
              "glossary": "", "lang": "zh", "entry_id": None, "glossary_id": None}
    row = _app._write_output_lang_cue_text(e, 0, "zh", "新句", change)
    assert row["by_lang"]["zh"]["text"] == "新句"
    assert row["zh_text"] == "新句"
    assert e["aligned_bilingual"][0]["by_lang"]["zh"] == "新句"
    assert row["glossary_changes"][-1] == change
    # keep_status：status/flags 一律唔郁
    assert row["status"] == "approved"
    assert row["by_lang"]["zh"]["status"] == "approved"
    # 另一語言軌零影響
    assert row["en_text"] == "old" and e["aligned_bilingual"][0]["by_lang"]["en"] == "old"


def test_no_change_record_when_change_none():
    import app as _app
    e = _entry()
    _app._write_output_lang_cue_text(e, 0, "en", "new", None)
    assert e["translations"][0]["glossary_changes"] == []
    assert e["translations"][0]["en_text"] == "new"


def test_tolerates_missing_aligned_and_short_aligned():
    import app as _app
    e = _entry()
    e["aligned_bilingual"] = []          # 短過 idx — 唔可以 crash（apply-item 同款 guard）
    _app._write_output_lang_cue_text(e, 0, "zh", "新句", None)
    assert e["translations"][0]["zh_text"] == "新句"
    e2 = _entry()
    e2.pop("aligned_bilingual")
    _app._write_output_lang_cue_text(e2, 0, "zh", "新句", None)
    assert e2["translations"][0]["zh_text"] == "新句"
