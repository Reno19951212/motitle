"""glossary-preview must reject a non-list glossary_ids override with 400, not 500.

Bug-sweep #12: `list(data["glossary_ids"])` raised TypeError (→ 500) when the
override was a non-iterable scalar (int/bool/float). The route now type-checks
the override before using it.
"""
import pytest


@pytest.fixture
def seeded_ol_file():
    import app as app_module
    fid = "bugsweep_ol_guard"
    app_module._file_registry[fid] = {
        "id": fid,
        "active_kind": "output_lang",
        "user_id": 0,
        "translations": [],
        "content_asr_segments": [],
        "output_languages": ["zh"],
        "source_language": "yue",
        "mt_style": "generic",
        "glossary_ids": [],
    }
    yield fid
    app_module._file_registry.pop(fid, None)


@pytest.mark.parametrize("bad", [42, "x", True, 3.5])
def test_nonlist_glossary_ids_returns_400(client, seeded_ol_file, bad):
    r = client.post(f"/api/files/{seeded_ol_file}/glossary-preview",
                    json={"glossary_ids": bad})
    assert r.status_code == 400, r.get_data(as_text=True)[:150]
    assert r.headers["Content-Type"].startswith("application/json")


def test_empty_list_glossary_ids_ok(client, seeded_ol_file):
    r = client.post(f"/api/files/{seeded_ol_file}/glossary-preview",
                    json={"glossary_ids": []})
    assert r.status_code == 200, r.get_data(as_text=True)[:150]
