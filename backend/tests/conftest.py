import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _isolate_app_data(tmp_path, monkeypatch):
    """Auto-isolate every test from the real DATA_DIR.

    Prevents tests from overwriting backend/data/registry.json when they
    call API endpoints that invoke _save_registry(). Applies to every test
    in the suite without requiring opt-in from individual fixtures.
    """
    import app

    test_data_dir = tmp_path / "data"
    (test_data_dir / "uploads").mkdir(parents=True)
    (test_data_dir / "renders").mkdir()
    (test_data_dir / "results").mkdir()

    monkeypatch.setattr(app, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(app, "UPLOAD_DIR", test_data_dir / "uploads")
    monkeypatch.setattr(app, "RENDERS_DIR", test_data_dir / "renders")
    monkeypatch.setattr(app, "RESULTS_DIR", test_data_dir / "results")

    original_registry = app._file_registry.copy()
    app._file_registry.clear()

    yield

    app._file_registry.clear()
    app._file_registry.update(original_registry)
