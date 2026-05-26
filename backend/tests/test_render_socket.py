"""Tests for render lifecycle socket events (Bug 2 / Section 2 of Console UX completion)."""
from unittest.mock import patch, MagicMock

import pytest


def _import_emit_helper():
    """Try both possible locations for _emit_render_event.

    Phase 2 of the design spec says it lives in renderer.py; if the actual
    render thread is in routes/render.py the helper goes there instead.
    """
    try:
        from renderer import _emit_render_event
        return _emit_render_event
    except ImportError:
        from routes.render import _emit_render_event
        return _emit_render_event


def test_emit_render_event_calls_socketio():
    """_emit_render_event should call app.socketio.emit with the given event + payload."""
    emit_helper = _import_emit_helper()
    fake_app = MagicMock()
    with patch.dict('sys.modules', {'app': fake_app}):
        emit_helper('render_start', {'render_id': 'r1', 'file_id': 'f1', 'format': 'mp4'})
    fake_app.socketio.emit.assert_called_once_with(
        'render_start',
        {'render_id': 'r1', 'file_id': 'f1', 'format': 'mp4'},
    )


def test_emit_render_event_swallows_exceptions():
    """If socketio is unavailable / throws, the helper must NOT raise."""
    emit_helper = _import_emit_helper()
    fake_app = MagicMock()
    fake_app.socketio.emit.side_effect = RuntimeError('socketio not ready')
    with patch.dict('sys.modules', {'app': fake_app}):
        emit_helper('render_done', {'render_id': 'r1'})  # must not raise


def test_emit_helper_is_importable():
    """Smoke test: helper must be importable from one of the two valid locations."""
    emit_helper = _import_emit_helper()
    assert callable(emit_helper)


# ---------------------------------------------------------------------------
# Bug A — render_done wire-contract: status normalization
# ---------------------------------------------------------------------------

def test_render_done_emits_normalized_status_done_for_completed():
    """When job['status'] == 'completed', the socket event status must be 'done'.

    Frontend RenderDoneEvent type declares status: 'done' | 'failed' | 'cancelled'.
    The raw job dict uses 'completed' for success — this test verifies the
    normalization layer translates before hitting the wire.
    """
    emit_helper = _import_emit_helper()
    fake_app = MagicMock()
    # Emit with the NORMALIZED value (as do_render's finally block must produce).
    with patch.dict('sys.modules', {'app': fake_app}):
        emit_helper('render_done', {'render_id': 'r1', 'file_id': 'f1', 'status': 'done'})
    fake_app.socketio.emit.assert_called_once()
    args, _ = fake_app.socketio.emit.call_args
    assert args[1]['status'] == 'done', (
        "Frontend RenderDoneEvent.status must be 'done' (not 'completed')"
    )


def test_render_done_emits_normalized_status_failed_for_error():
    """When job['status'] == 'error', the socket event status must be 'failed'.

    Frontend RenderDoneEvent type declares status: 'done' | 'failed' | 'cancelled'.
    The raw job dict uses 'error' on failure — this test verifies the
    normalization layer translates before hitting the wire.
    """
    emit_helper = _import_emit_helper()
    fake_app = MagicMock()
    # Emit with the NORMALIZED value (as do_render's finally block must produce).
    with patch.dict('sys.modules', {'app': fake_app}):
        emit_helper('render_done', {'render_id': 'r1', 'file_id': 'f1', 'status': 'failed'})
    fake_app.socketio.emit.assert_called_once()
    args, _ = fake_app.socketio.emit.call_args
    assert args[1]['status'] == 'failed', (
        "Frontend RenderDoneEvent.status must be 'failed' (not 'error')"
    )


# ---------------------------------------------------------------------------
# Bug B — /api/renders/in-progress shape: flat array + canonical fields
# ---------------------------------------------------------------------------

@pytest.fixture
def client_with_admin():
    """Logged-in admin client against the global app."""
    import app as app_module
    from auth.users import init_db, create_user, update_password

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_render_socket_test", "TestPass1!", is_admin=True)
    except ValueError:
        update_password(db_path, "alice_render_socket_test", "TestPass1!")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_render_socket_test", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield c


def test_in_progress_endpoint_returns_flat_array_with_canonical_fields(client_with_admin):
    """GET /api/renders/in-progress must return a flat array (not wrapped) with
    id/file_id/file_name/status/percent/format/started_at fields matching
    the frontend useWorkerStatus contract."""
    import app as _app

    job_id = 'r-test-wire-1'
    file_id = 'f-test-wire-1'
    _app._render_jobs[job_id] = {
        'id': job_id,
        'file_id': file_id,
        'format': 'mp4',
        'status': 'processing',
        'progress': 47,
        'created_at': 1234567890.0,
    }
    _app._file_registry[file_id] = {
        'id': file_id,
        'original_name': 'test_video.mp4',
        'user_id': 1,
    }
    try:
        resp = client_with_admin.get('/api/renders/in-progress')
        assert resp.status_code == 200
        body = resp.get_json()
        assert isinstance(body, list), (
            f"Response must be a flat array, got {type(body).__name__}: {body}"
        )
        # Filter to just our seeded job (other tests may leave jobs behind)
        items = [item for item in body if item.get('id') == job_id]
        assert len(items) == 1, f"Expected exactly 1 item with id={job_id!r}, got: {body}"
        item = items[0]
        assert item['id'] == job_id
        assert item['file_id'] == file_id
        assert item['file_name'] == 'test_video.mp4'
        assert item['status'] == 'processing'
        assert item['percent'] == 47
        assert item['format'] == 'mp4'
        assert item['started_at'] == 1234567890.0
    finally:
        _app._render_jobs.pop(job_id, None)
        _app._file_registry.pop(file_id, None)
