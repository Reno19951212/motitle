import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_is_cross_language_matrix():
    f = _app._is_cross_language
    assert f("yue", ["zh", "en"]) is True
    assert f("en", ["en", "zh"]) is True
    assert f("cmn", ["cmn", "en"]) is True
    assert f("ja", ["ja", "zh"]) is True
    assert f("yue", ["zh"]) is False
    assert f("yue", ["yue"]) is False
    assert f("cmn", ["zh", "cmn"]) is False
    assert f("yue", ["zh", "cmn", "yue"]) is False
