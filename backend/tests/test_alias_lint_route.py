"""Route tests for POST /api/glossaries/alias-lint (§4.2b 別名警告安全網).

Pure lint route — login_required, zero writes; body {variant, kind} → {warnings}.
Used by the three frontend alias entry points for NON-BLOCKING advisory toasts.

Run:
    cd backend && ./venv/bin/python -m pytest tests/test_alias_lint_route.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _lint(client, payload):
    return client.post("/api/glossaries/alias-lint", json=payload)


def test_lint_route_common_word_warns(client):
    r = _lint(client, {"variant": "one more", "kind": "source"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert any("常用英文詞" in w for w in r.get_json()["warnings"])


def test_lint_route_short_cjk_warns(client):
    r = _lint(client, {"variant": "電流", "kind": "target"})
    assert r.status_code == 200
    assert any("太短" in w for w in r.get_json()["warnings"])


def test_lint_route_lexicon_side(client):
    r = _lint(client, {"variant": "尾指", "kind": "lexicon"})
    assert r.status_code == 200
    assert any("太短" in w for w in r.get_json()["warnings"])


def test_lint_route_clean_variant_empty_warnings(client):
    r = _lint(client, {"variant": "Speedy Smarty", "kind": "source"})
    assert r.status_code == 200
    assert r.get_json()["warnings"] == []


def test_lint_route_bad_kind_400(client):
    assert _lint(client, {"variant": "x", "kind": "bogus"}).status_code == 400


def test_lint_route_missing_variant_400(client):
    assert _lint(client, {"kind": "source"}).status_code == 400
    assert _lint(client, {"variant": "   ", "kind": "source"}).status_code == 400
