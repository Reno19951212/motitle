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
