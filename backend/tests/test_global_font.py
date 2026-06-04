"""Global subtitle-font preset (2026-06-04).

In V6 / output_lang modes there is no active profile, so the font (字幕設定) had no
home — 「儲存為預設」 no-op'd and render fell back to DEFAULT_FONT_CONFIG. The global
font preset (settings.json 'font') is the mode-independent source of truth.
"""
import json
import os

os.environ.setdefault("R5_AUTH_BYPASS", "1")

from profiles import ProfileManager
from renderer import DEFAULT_FONT_CONFIG


def test_get_global_font_default(tmp_path):
    pm = ProfileManager(tmp_path)
    f = pm.get_global_font()
    assert f["family"] == DEFAULT_FONT_CONFIG["family"]
    assert f["size"] == DEFAULT_FONT_CONFIG["size"]


def test_set_global_font_persists_and_merges(tmp_path):
    pm = ProfileManager(tmp_path)
    merged = pm.set_global_font({"size": 60, "color": "#ffe066"})
    assert merged["size"] == 60 and merged["color"] == "#ffe066"
    assert merged["family"] == DEFAULT_FONT_CONFIG["family"]      # unspecified → default
    assert ProfileManager(tmp_path).get_global_font()["size"] == 60  # persisted to disk


def test_set_global_font_preserves_other_settings(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"active_kind": "output_lang", "active_id": "x"}), encoding="utf-8")
    ProfileManager(tmp_path).set_global_font({"size": 55})
    s = json.loads((tmp_path / "settings.json").read_text())
    assert s["active_kind"] == "output_lang" and s["active_id"] == "x"   # untouched
    assert s["font"]["size"] == 55


def test_settings_font_endpoints(tmp_path, monkeypatch):
    import app as _app
    monkeypatch.setattr(_app, "_profile_manager", ProfileManager(tmp_path))
    _app.app.config["R5_AUTH_BYPASS"] = True
    c = _app.app.test_client()
    # GET default
    r = c.get("/api/settings/font")
    assert r.status_code == 200 and r.get_json()["font"]["family"]
    # PUT custom (accept either {font:{...}} or a bare font dict)
    r = c.put("/api/settings/font", json={"font": {"size": 60, "color": "#ffe066"}})
    assert r.status_code == 200 and r.get_json()["font"]["size"] == 60
    # GET reflects the saved preset
    assert c.get("/api/settings/font").get_json()["font"]["size"] == 60
    # out-of-range → 400
    assert c.put("/api/settings/font", json={"font": {"size": 999}}).status_code == 400
    assert c.put("/api/settings/font", json={"font": {"outline_width": 99}}).status_code == 400
