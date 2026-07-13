"""確定性正規化：單位 pass（spec §5.1）。"""
import output_lang_normalize as oln


def test_gongchi_to_mi():
    segs = [{"start": 0, "end": 1, "text": "二千公尺又是另一程。"}]
    out, ch = oln.normalize_units(segs)
    assert out[0]["text"] == "二千米又是另一程。"
    assert ch[0][0]["before"] == "公尺" and ch[0][0]["after"] == "米"
    assert ch[0][0]["glossary"] == oln.UNIT_TAG
    assert segs[0]["text"] == "二千公尺又是另一程。"   # immutable


def test_number_prefixed_gongchi():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "1600公尺賽事"}])
    assert out[0]["text"] == "1600米賽事"


def test_gongli_variant_normalized():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "跑了兩公裏"}])
    assert out[0]["text"] == "跑了兩公里"


def test_gongli_kept():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "距離三公里"}])
    assert out[0]["text"] == "距離三公里" and ch[0] == []


def test_no_unit_unchanged():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "他表現出色。"}])
    assert out[0]["text"] == "他表現出色。" and ch[0] == []


def test_multiple_segments():
    out, ch = oln.normalize_units([
        {"start": 0, "end": 1, "text": "二千公尺"},
        {"start": 1, "end": 2, "text": "冇單位"}])
    assert out[0]["text"] == "二千米" and out[1]["text"] == "冇單位"
    assert len(ch) == 2 and ch[1] == []
