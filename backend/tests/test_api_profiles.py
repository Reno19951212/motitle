import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def profile_client(tmp_path):
    from app import app, _init_profile_manager, _init_glossary_manager

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _create_profile(client, name="Font Test"):
    resp = client.post('/api/profiles', json={
        "name": name,
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "mock"},
        "font": {
            "family": "Arial",
            "size": 36,
            "color": "#FFFF00",
            "outline_color": "#000000",
            "outline_width": 3,
            "margin_bottom": 50
        }
    })
    assert resp.status_code == 201
    return resp.get_json()["profile"]["id"]


def test_activate_profile_emits_profile_updated(profile_client):
    """POST /api/profiles/<id>/activate emits profile_updated with font config."""
    profile_id = _create_profile(profile_client)

    with patch('app.socketio.emit') as mock_emit:
        resp = profile_client.post(f'/api/profiles/{profile_id}/activate')
        assert resp.status_code == 200

        event_names = [c[0][0] for c in mock_emit.call_args_list]
        assert 'profile_updated' in event_names

        update_call = next(c for c in mock_emit.call_args_list if c[0][0] == 'profile_updated')
        font = update_call[0][1]['font']
        assert font['family'] == 'Arial'
        assert font['size'] == 36
        assert font['color'] == '#FFFF00'


def test_patch_active_profile_emits_profile_updated(profile_client):
    """PATCH /api/profiles/<id> on the active profile emits profile_updated."""
    profile_id = _create_profile(profile_client, name="Active Profile")
    profile_client.post(f'/api/profiles/{profile_id}/activate')

    with patch('app.socketio.emit') as mock_emit:
        resp = profile_client.patch(f'/api/profiles/{profile_id}', json={
            "font": {"size": 60}
        })
        assert resp.status_code == 200

        event_names = [c[0][0] for c in mock_emit.call_args_list]
        assert 'profile_updated' in event_names

        update_call = next(c for c in mock_emit.call_args_list if c[0][0] == 'profile_updated')
        assert update_call[0][1]['font']['size'] == 60


def test_patch_inactive_profile_does_not_emit(profile_client):
    """PATCH on a non-active profile must NOT emit profile_updated."""
    active_id = _create_profile(profile_client, name="Active")
    inactive_id = _create_profile(profile_client, name="Inactive")
    profile_client.post(f'/api/profiles/{active_id}/activate')

    with patch('app.socketio.emit') as mock_emit:
        resp = profile_client.patch(f'/api/profiles/{inactive_id}', json={
            "font": {"size": 72}
        })
        assert resp.status_code == 200

        event_names = [c[0][0] for c in mock_emit.call_args_list]
        assert 'profile_updated' not in event_names
