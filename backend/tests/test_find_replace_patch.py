"""PATCH /translations/<idx> keep_status 參數 — find-replace 嘅「取代（保持狀態）」用。"""
import pytest

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True
    appmod.app.config["LOGIN_DISABLED"] = True
    with appmod.app.test_client() as c:
        yield c
    appmod.app.config.pop("R5_AUTH_BYPASS", None)
    appmod.app.config.pop("LOGIN_DISABLED", None)


def _seed(fid="f-fr", statuses=("pending", "approved")):
    trans = []
    for i, st in enumerate(statuses):
        trans.append({
            "idx": i, "start": float(i), "end": float(i + 1), "status": st,
            "flags": ["[LONG]"],
            "by_lang": {"yue": {"text": f"粵{i}", "status": st, "flags": []},
                        "en": {"text": f"EN{i}", "status": st, "flags": []}},
            "yue_text": f"粵{i}", "en_text": f"EN{i}", "glossary_changes": [],
        })
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "id": fid, "user_id": "u1", "status": "done",
            "active_kind": "output_lang", "output_languages": ["yue", "en"],
            "translations": trans,
            "aligned_bilingual": [{"start": float(i), "end": float(i + 1),
                                   "by_lang": {"yue": f"粵{i}", "en": f"EN{i}"}}
                                  for i in range(len(statuses))],
        }
    return fid


def test_keep_status_preserves_pending(client):
    fid = _seed("f-fr-p")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "新粵0", "role": "first", "keep_status": True})
    assert r.status_code == 200, r.get_data(as_text=True)
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][0]
        assert row["status"] == "pending"                       # 狀態保持
        assert row["yue_text"] == "新粵0"                        # 文字有改
        assert row["by_lang"]["yue"]["text"] == "新粵0"
        assert row["by_lang"]["yue"]["status"] == "pending"      # by_lang 狀態都保持
        assert row["baseline_target"] == "新粵0"                 # baseline 照更新（防 glossary 還原）
        assert row["flags"] == []                                # flags 照清（文字已改）
        assert appmod._file_registry[fid]["aligned_bilingual"][0]["by_lang"]["yue"] == "新粵0"


def test_keep_status_preserves_approved(client):
    fid = _seed("f-fr-a")
    r = client.patch(f"/api/files/{fid}/translations/1",
                     json={"text": "新粵1", "role": "first", "keep_status": True})
    assert r.status_code == 200
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][1]
        assert row["status"] == "approved"
        assert row["by_lang"]["yue"]["status"] == "approved"


def test_keep_status_second_role(client):
    fid = _seed("f-fr-s")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "NewEN0", "role": "second", "keep_status": True})
    assert r.status_code == 200
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][0]
        assert row["status"] == "pending"
        assert row["en_text"] == "NewEN0"
        assert row["by_lang"]["en"]["text"] == "NewEN0"
        assert row["by_lang"]["en"]["status"] == "pending"
        assert appmod._file_registry[fid]["aligned_bilingual"][0]["by_lang"]["en"] == "NewEN0"


def test_default_still_auto_approves(client):
    # regression — 唔傳 keep_status 必須照舊 auto-approve
    fid = _seed("f-fr-d")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "改0", "role": "first"})
    assert r.status_code == 200
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][0]
        assert row["status"] == "approved"
        assert row["by_lang"]["yue"]["status"] == "approved"
